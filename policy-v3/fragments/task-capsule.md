# Task Capsule

## Goal

{{GOAL}}

## Non-goals

{{NON_GOALS}}

## Risk

{{RISK}}

## Allowed scope

{{ALLOWED_SCOPE}}

## Forbidden scope

{{FORBIDDEN_SCOPE}}

## Acceptance

{{ACCEPTANCE}}

## Loaded policies

{{LOADED_POLICIES}}

## Artifact pointers

{{ARTIFACT_POINTERS}}

## Execution contract

Work only inside the allowed scope and preserve existing public, safety, ownership, rollback, encoding, and model-binding behavior unless the goal explicitly changes one of those contracts. Inspect the listed artifacts first, then pull only the additional context needed to complete the task. Do not copy a full workflow, hidden history, or unrelated repository prose into the response.

For code changes, follow test-first development: add a focused test, run it and confirm the expected feature-missing failure, implement the smallest passing behavior, then run the focused test and relevant regressions. Report exact commands and outcomes. Keep generated output deterministic and preserve declared source identifiers and hashes.

Stop and report a blocker if a required choice would be destructive, a permission or authentication denial is definitive, an allowed file is missing, or repeated attempts cannot make the declared acceptance checks pass. Do not widen scope to investigate unrelated cleanup.

Return a concise result containing changed files, verification evidence, unresolved risks, and any dependency the parent must carry into the next task. The parent owns integration, cross-worker conflict checks, final review, commit selection, and user communication.
