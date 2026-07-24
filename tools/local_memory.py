"""Local-only, transactional memory for OpenCode workflow users.

Only compact, scrubbed summaries and one-way evidence hashes are persisted.
Raw prompts, source code, tool output, paths, and secrets remain transient.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
import threading
import time
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path


SCHEMA_VERSION = 1
SECRET_RE = re.compile(
    r"(?i)(?:api[_ -]?key|password|secret|token|private[_ -]?key)\s*[:=]\s*\S+|"
    r"-----BEGIN [A-Z ]+PRIVATE KEY-----|AKIA[0-9A-Z]{16}"
)
CODE_RE = re.compile(r"(?s)(?:```|[{};]{2,}|^\s*(?:def|class|import|const|let|function)\s)")
PATH_RE = re.compile(r"(?<!\w)(?:[A-Za-z]:[\\/]|/[\w.-]+/|~[\\/])[\w./\\-]+")
SPACE_RE = re.compile(r"\s+")
WORD_RE = re.compile(r"[a-z0-9]{3,}", re.IGNORECASE)
STOP_WORDS = {
    "and", "are", "before", "changes", "detail", "every", "for", "from", "implementation",
    "into", "prefer", "please", "project", "remember", "summary", "summaries", "tests",
    "the", "this", "use", "with", "you",
}
SCHEMA_STATEMENTS = (
    """
    CREATE TABLE generations (
      id INTEGER PRIMARY KEY,
      created_at TEXT NOT NULL,
      reason TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE candidates (
      id INTEGER PRIMARY KEY,
      kind TEXT NOT NULL,
      summary TEXT NOT NULL,
      summary_hash TEXT NOT NULL UNIQUE,
      evidence_hash TEXT NOT NULL,
      session_hashes TEXT NOT NULL,
      recurrence INTEGER NOT NULL,
      state TEXT NOT NULL,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE memories (
      id INTEGER PRIMARY KEY,
      kind TEXT NOT NULL,
      summary TEXT NOT NULL,
      evidence_hash TEXT NOT NULL,
      confidence REAL NOT NULL,
      recurrence INTEGER NOT NULL,
      sensitivity TEXT NOT NULL,
      state TEXT NOT NULL,
      generation INTEGER NOT NULL REFERENCES generations(id),
      created_at TEXT NOT NULL,
      expires_at TEXT
    )
    """,
    """
    CREATE TABLE relations (
      source_id INTEGER NOT NULL REFERENCES memories(id),
      target_id INTEGER NOT NULL REFERENCES memories(id),
      relation TEXT NOT NULL,
      PRIMARY KEY (source_id, target_id, relation)
    )
    """,
    """
    CREATE TABLE telemetry (
      id INTEGER PRIMARY KEY,
      prompt_hash TEXT NOT NULL,
      predicted_policy_ids TEXT NOT NULL,
      selected_agent TEXT NOT NULL,
      selected_skills TEXT NOT NULL,
      result TEXT NOT NULL,
      created_at TEXT NOT NULL
    )
    """,
    "CREATE VIRTUAL TABLE memories_fts USING fts5(summary)",
)


class MemoryError(ValueError):
    """Raised when a local-memory operation cannot preserve its contract."""


def token_proxy(text: str) -> int:
    return (len(text) + 3) // 4


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def default_data_root() -> Path:
    if os.name == "nt" and os.environ.get("LOCALAPPDATA"):
        return Path(os.environ["LOCALAPPDATA"]) / "agent-workflow-skills"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "agent-workflow-skills"


def project_identity(project_root: str | Path | None) -> str:
    if project_root is None:
        raise MemoryError("project memory requires a project root")
    root = Path(project_root).resolve()
    if not root.is_dir():
        raise MemoryError("project memory root is not a directory")
    remote = ""
    try:
        remote = subprocess.run(
            ["git", "-C", str(root), "config", "--get", "remote.origin.url"],
            capture_output=True,
            encoding="utf-8",
            check=False,
        ).stdout.strip()
    except OSError:
        pass
    return _hash(remote or root.as_posix())[:32]


def _safe_summary(text: str) -> str | None:
    if not isinstance(text, str) or SECRET_RE.search(text) or CODE_RE.search(text):
        return None
    summary = SPACE_RE.sub(" ", PATH_RE.sub("[path]", text)).strip(" .")
    if not summary or len(summary) > 240:
        return None
    return summary


def _extract(text: str, scope: str) -> tuple[str, str, bool] | None:
    if SECRET_RE.search(text) or CODE_RE.search(text):
        return None
    normalized = SPACE_RE.sub(" ", text).strip()
    patterns = (
        (r"(?i)^(?:please remember:\s*)?i prefer\s+(.+)$", "preference", True),
        (r"(?i)^i tend to prefer\s+(.+)$", "habit", False),
        (r"(?i)^project convention:\s*(.+)$", "project_fact", True),
        (r"^(?:我偏好|我喜欢)\s*(.+)$", "preference", True),
        (r"^我通常(?:会)?\s*(.+)$", "habit", False),
        (r"^项目约定[:：]\s*(.+)$", "project_fact", True),
    )
    for pattern, kind, explicit in patterns:
        match = re.match(pattern, normalized)
        if not match or (kind == "project_fact") != (scope == "project"):
            continue
        prefix = {
            "preference": "Preference",
            "habit": "Habit",
            "project_fact": "Project convention",
        }[kind]
        summary = _safe_summary(f"{prefix}: {match.group(1)}")
        if summary:
            return kind, summary, explicit
    return None


def _keywords(text: str) -> set[str]:
    return {word.lower() for word in WORD_RE.findall(text) if word.lower() not in STOP_WORDS}


def _conflicts(left: str, right: str) -> bool:
    left_words, right_words = _keywords(left), _keywords(right)
    if not left_words or not right_words:
        return False
    overlap = len(left_words & right_words) / min(len(left_words), len(right_words))
    pairs = (("concise", "exhaustive"), ("concise", "detailed"), ("minimal", "exhaustive"))
    opposed = any(
        (a in left_words and b in right_words) or (b in left_words and a in right_words)
        for a, b in pairs
    )
    return overlap >= 0.5 and opposed


class MemoryStore:
    """One isolated global or project SQLite namespace."""

    _initialization_lock = threading.Lock()

    def __init__(
        self,
        data_root: str | Path | None = None,
        *,
        scope: str = "global",
        project_root: str | Path | None = None,
    ):
        if scope not in {"global", "project"}:
            raise MemoryError("memory scope must be global or project")
        root = Path(data_root) if data_root is not None else default_data_root()
        self.scope = scope
        self.namespace = "global" if scope == "global" else project_identity(project_root)
        directory = root / "memory" / scope
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.database_path = directory / f"{self.namespace}.sqlite3"
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        for attempt in range(20):
            connection = sqlite3.connect(self.database_path, timeout=10, isolation_level=None)
            try:
                connection.row_factory = sqlite3.Row
                connection.execute("PRAGMA busy_timeout = 10000")
                connection.execute("PRAGMA foreign_keys = ON")
                return connection
            except sqlite3.OperationalError:
                connection.close()
                if attempt == 19:
                    raise
                time.sleep(0.05)
        raise AssertionError("unreachable SQLite connection retry")

    def _initialize(self) -> None:
        with self._initialization_lock:
            with closing(self._connect()) as connection:
                connection.execute("PRAGMA journal_mode = WAL")
                connection.execute("PRAGMA synchronous = FULL")
                version = connection.execute("PRAGMA user_version").fetchone()[0]
                if version > SCHEMA_VERSION:
                    raise MemoryError("local memory schema is newer than this workflow")
                if version == SCHEMA_VERSION:
                    return
                if version != 0:
                    backup = self.database_path.with_suffix(f".v{version}.backup.sqlite3")
                    if backup.exists():
                        raise MemoryError("local memory migration backup already exists")
                    with sqlite3.connect(backup) as destination:
                        connection.backup(destination)
                connection.execute("BEGIN IMMEDIATE")
                try:
                    for statement in SCHEMA_STATEMENTS:
                        connection.execute(statement)
                    connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
                    connection.commit()
                except BaseException:
                    connection.rollback()
                    raise
        try:
            os.chmod(self.database_path, 0o600)
        except OSError:
            pass

    def _rebuild_fts(self, connection: sqlite3.Connection) -> None:
        connection.execute("DELETE FROM memories_fts")
        connection.execute(
            """
            INSERT INTO memories_fts(rowid, summary)
            SELECT id, summary FROM memories
            WHERE state = 'active'
              AND (expires_at IS NULL OR expires_at > ?)
            """,
            (_now(),),
        )

    def _generation(self, connection: sqlite3.Connection, reason: str) -> int:
        cursor = connection.execute(
            "INSERT INTO generations(created_at, reason) VALUES (?, ?)", (_now(), reason)
        )
        return int(cursor.lastrowid)

    def _active_conflict(
        self, connection: sqlite3.Connection, kind: str, summary: str
    ) -> sqlite3.Row | None:
        rows = connection.execute(
            "SELECT id, summary FROM memories WHERE kind = ? AND state = 'active'",
            (kind,),
        ).fetchall()
        return next((row for row in rows if _conflicts(summary, row["summary"])), None)

    def capture(self, text: str, *, session_id: str = "", outcome: str = "pending") -> dict:
        extracted = _extract(text, self.scope)
        if extracted is None:
            return {"promoted": 0, "quarantined": 0, "rejected": 1}
        kind, summary, explicit = extracted
        if kind == "project_fact" and outcome != "completed":
            return {"promoted": 0, "quarantined": 0, "rejected": 1}
        source_hash = _hash(text)
        session_hash = _hash(session_id or source_hash)
        summary_hash = _hash(f"{kind}\0{summary.casefold()}")
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                row = connection.execute(
                    "SELECT * FROM candidates WHERE summary_hash = ?", (summary_hash,)
                ).fetchone()
                if row:
                    hashes = set(json.loads(row["session_hashes"]))
                    hashes.add(session_hash)
                    recurrence = len(hashes)
                    connection.execute(
                        """
                        UPDATE candidates
                        SET session_hashes = ?, recurrence = ?, updated_at = ?
                        WHERE id = ?
                        """,
                        (json.dumps(sorted(hashes)), recurrence, _now(), row["id"]),
                    )
                    candidate_id = row["id"]
                else:
                    recurrence = 1
                    cursor = connection.execute(
                        """
                        INSERT INTO candidates(
                          kind, summary, summary_hash, evidence_hash, session_hashes,
                          recurrence, state, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, 'collecting', ?, ?)
                        """,
                        (
                            kind,
                            summary,
                            summary_hash,
                            source_hash,
                            json.dumps([session_hash]),
                            recurrence,
                            _now(),
                            _now(),
                        ),
                    )
                    candidate_id = int(cursor.lastrowid)

                conflict = self._active_conflict(connection, kind, summary)
                if conflict is not None:
                    connection.execute(
                        "UPDATE candidates SET state = 'quarantined' WHERE id = ?",
                        (candidate_id,),
                    )
                    connection.commit()
                    return {"promoted": 0, "quarantined": 1, "rejected": 0}

                should_promote = (
                    kind == "preference" and explicit
                ) or recurrence >= 3
                if not should_promote:
                    connection.commit()
                    return {"promoted": 0, "quarantined": 0, "rejected": 0}

                generation = self._generation(connection, "automatic-memory-promotion")
                expires_at = (
                    (datetime.now(UTC) + timedelta(days=180)).isoformat(timespec="seconds")
                    if kind == "project_fact"
                    else None
                )
                cursor = connection.execute(
                    """
                    INSERT INTO memories(
                      kind, summary, evidence_hash, confidence, recurrence, sensitivity,
                      state, generation, created_at, expires_at
                    ) VALUES (?, ?, ?, ?, ?, 'low', 'active', ?, ?, ?)
                    """,
                    (
                        kind,
                        summary,
                        source_hash,
                        0.95 if explicit else 0.75,
                        recurrence,
                        generation,
                        _now(),
                        expires_at,
                    ),
                )
                memory_id = int(cursor.lastrowid)
                for previous in connection.execute(
                    "SELECT id FROM memories WHERE kind = ? AND state = 'active' AND id != ?",
                    (kind, memory_id),
                ).fetchall():
                    if _conflicts(summary, connection.execute(
                        "SELECT summary FROM memories WHERE id = ?", (previous["id"],)
                    ).fetchone()["summary"]):
                        connection.execute(
                            "UPDATE memories SET state = 'superseded' WHERE id = ?", (previous["id"],)
                        )
                        connection.execute(
                            "INSERT OR IGNORE INTO relations(source_id, target_id, relation) VALUES (?, ?, 'supersedes')",
                            (memory_id, previous["id"]),
                        )
                connection.execute(
                    "UPDATE candidates SET state = 'promoted' WHERE id = ?", (candidate_id,)
                )
                self._rebuild_fts(connection)
                connection.commit()
                return {"promoted": 1, "quarantined": 0, "rejected": 0}
            except BaseException:
                connection.rollback()
                raise

    def search(self, query: str, *, limit: int = 5) -> list[dict]:
        if limit < 1 or limit > 20:
            raise MemoryError("memory search limit must be between 1 and 20")
        terms = " ".join(WORD_RE.findall(query))
        if not terms:
            return []
        with closing(self._connect()) as connection:
            try:
                rows = connection.execute(
                    """
                    SELECT m.* FROM memories_fts f
                    JOIN memories m ON m.id = f.rowid
                    WHERE memories_fts MATCH ?
                      AND m.state = 'active'
                      AND (m.expires_at IS NULL OR m.expires_at > ?)
                    ORDER BY bm25(memories_fts), m.confidence DESC, m.recurrence DESC
                    LIMIT ?
                    """,
                    (terms, _now(), limit),
                ).fetchall()
            except sqlite3.OperationalError:
                escaped = f"%{terms.replace('%', '')}%"
                rows = connection.execute(
                    """
                    SELECT * FROM memories
                    WHERE state = 'active' AND summary LIKE ?
                      AND (expires_at IS NULL OR expires_at > ?)
                    ORDER BY confidence DESC, recurrence DESC LIMIT ?
                    """,
                    (escaped, _now(), limit),
                ).fetchall()
        return [
            {
                "id": row["id"],
                "kind": row["kind"],
                "summary": row["summary"],
                "confidence": row["confidence"],
                "recurrence": row["recurrence"],
            }
            for row in rows
        ]

    def context(self, query: str, *, token_budget: int = 320) -> str:
        if token_budget < 16:
            raise MemoryError("memory context budget must be at least 16 tokens")
        lines = ["## Durable local memory"]
        for row in self.search(query, limit=20):
            line = f"- [{row['kind']}; confidence={row['confidence']:.2f}] {row['summary']}"
            if token_proxy("\n".join([*lines, line])) > token_budget:
                break
            lines.append(line)
        return "" if len(lines) == 1 else "\n".join(lines)

    def rollback(self, generation: int) -> None:
        if generation < 0:
            raise MemoryError("rollback generation must be non-negative")
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute(
                    "UPDATE memories SET state = 'rolled_back' WHERE generation > ? AND state = 'active'",
                    (generation,),
                )
                connection.execute(
                    """
                    UPDATE memories SET state = 'active'
                    WHERE id IN (
                      SELECT target_id FROM relations r
                      JOIN memories source ON source.id = r.source_id
                      WHERE r.relation = 'supersedes' AND source.generation > ?
                    ) AND generation <= ? AND state = 'superseded'
                    """,
                    (generation, generation),
                )
                self._rebuild_fts(connection)
                connection.commit()
            except BaseException:
                connection.rollback()
                raise

    def record_telemetry(
        self,
        prompt: str,
        *,
        predicted_policy_ids: list[str],
        selected_agent: str,
        selected_skills: list[str],
        result: str,
    ) -> None:
        if not all(isinstance(item, str) and re.fullmatch(r"P0[0-7]", item) for item in predicted_policy_ids):
            raise MemoryError("telemetry policy identifiers are invalid")
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", selected_agent):
            raise MemoryError("telemetry agent identifier is invalid")
        if result not in {"observed", "completed", "failed"}:
            raise MemoryError("telemetry result is invalid")
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute(
                    """
                    INSERT INTO telemetry(
                      prompt_hash, predicted_policy_ids, selected_agent, selected_skills, result, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        _hash(prompt),
                        json.dumps(sorted(set(predicted_policy_ids))),
                        selected_agent,
                        json.dumps(sorted(set(selected_skills))),
                        result,
                        _now(),
                    ),
                )
                connection.commit()
            except BaseException:
                connection.rollback()
                raise

    def status(self) -> dict:
        with closing(self._connect()) as connection:
            return {
                "scope": self.scope,
                "namespace": self.namespace,
                "schema_version": connection.execute("PRAGMA user_version").fetchone()[0],
                "generation": connection.execute("SELECT COALESCE(MAX(id), 0) FROM generations").fetchone()[0],
                "active": connection.execute(
                    "SELECT COUNT(*) FROM memories WHERE state = 'active'"
                ).fetchone()[0],
                "quarantined": connection.execute(
                    "SELECT COUNT(*) FROM candidates WHERE state = 'quarantined'"
                ).fetchone()[0],
                "telemetry": connection.execute("SELECT COUNT(*) FROM telemetry").fetchone()[0],
            }


def _payload() -> dict:
    try:
        value = json.load(sys.stdin)
    except json.JSONDecodeError as error:
        raise MemoryError(f"local-memory input must be JSON: {error}") from error
    if not isinstance(value, dict):
        raise MemoryError("local-memory input must be a JSON object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("capture", "context", "search", "status", "rollback", "telemetry"))
    parser.add_argument("--data-root", type=Path)
    parser.add_argument("--scope", choices=("global", "project"), default="global")
    parser.add_argument("--project-root")
    args = parser.parse_args()
    try:
        payload = _payload()
        store = MemoryStore(args.data_root, scope=args.scope, project_root=args.project_root)
        if args.command == "capture":
            result = store.capture(
                str(payload.get("text", "")),
                session_id=str(payload.get("session_id", "")),
                outcome=str(payload.get("outcome", "pending")),
            )
        elif args.command == "context":
            result = {"context": store.context(str(payload.get("query", "")), token_budget=int(payload.get("token_budget", 320)))}
        elif args.command == "search":
            result = {"results": store.search(str(payload.get("query", "")), limit=int(payload.get("limit", 5)))}
        elif args.command == "rollback":
            store.rollback(int(payload["generation"]))
            result = {"rolled_back_to": int(payload["generation"])}
        elif args.command == "telemetry":
            store.record_telemetry(
                str(payload.get("prompt", "")),
                predicted_policy_ids=list(payload.get("predicted_policy_ids", [])),
                selected_agent=str(payload.get("selected_agent", "")),
                selected_skills=list(payload.get("selected_skills", [])),
                result=str(payload.get("result", "")),
            )
            result = {"recorded": True}
        else:
            result = store.status()
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    except (MemoryError, OSError, sqlite3.Error, TypeError, ValueError) as error:
        print(f"local memory failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
