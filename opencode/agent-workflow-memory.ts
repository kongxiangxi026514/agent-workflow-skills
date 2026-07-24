import { tool } from "@opencode-ai/plugin"
import { join } from "path"

const MAX_TRANSIENT_CHARS = 2048
const MAX_CONTEXT_TOKENS = 320
const LOCAL_MEMORY_HOOKS = [
  "chat.message",
  "event",
  "experimental.chat.system.transform",
  "experimental.session.compacting",
] as const
const LOCAL_MEMORY_EVENTS = ["session.idle", "session.deleted"] as const

type PluginContext = {
  directory: string
  worktree: string
}

const lastPrompt = new Map<string, string>()
const captureInFlight = new Set<string>()

function python(): string {
  return process.env.AGENT_WORKFLOW_MEMORY_PYTHON ?? (
    process.platform === "win32" ? "python" : "python3"
  )
}

function memoryTool(): string {
  return join(import.meta.dir, "..", "agent-workflow-skills", "local_memory.py")
}

function memoryArgs(command: string, scope: "global" | "project", worktree: string): string[] {
  const args = [python(), memoryTool(), command, "--scope", scope]
  const dataRoot = process.env.AGENT_WORKFLOW_MEMORY_DIR
  if (dataRoot) args.push("--data-root", dataRoot)
  if (scope === "project") args.push("--project-root", worktree)
  return args
}

async function invoke(
  command: string,
  payload: Record<string, unknown>,
  scope: "global" | "project",
  worktree: string,
): Promise<Record<string, unknown>> {
  const child = Bun.spawn(memoryArgs(command, scope, worktree), {
    stdin: JSON.stringify(payload),
    stdout: "pipe",
    stderr: "pipe",
  })
  const [stdout, exitCode] = await Promise.all([
    new Response(child.stdout).text(),
    child.exited,
  ])
  if (exitCode !== 0) throw new Error(`local memory ${command} failed`)
  const value = JSON.parse(stdout)
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("local memory returned an invalid payload")
  }
  return value as Record<string, unknown>
}

function textParts(parts: Array<{ type?: string; text?: string }>): string {
  return parts
    .filter((part) => part.type === "text" && typeof part.text === "string")
    .map((part) => part.text ?? "")
    .join("\n")
    .slice(0, MAX_TRANSIENT_CHARS)
}

async function contextFor(query: string, ctx: PluginContext): Promise<string> {
  if (!query) return ""
  const [global, project] = await Promise.all([
    invoke("context", { query, token_budget: Math.floor(MAX_CONTEXT_TOKENS / 2) }, "global", ctx.worktree),
    invoke("context", { query, token_budget: Math.floor(MAX_CONTEXT_TOKENS / 2) }, "project", ctx.worktree),
  ])
  const values = [global.context, project.context].filter((value): value is string => typeof value === "string" && value.length > 0)
  return values.join("\n")
}

export const AgentWorkflowLocalMemory = async (ctx: PluginContext) => ({
  "chat.message": async (
    input: { sessionID: string; agent?: string },
    output: { parts: Array<{ type?: string; text?: string }> },
  ) => {
    const text = textParts(output.parts)
    if (!text || captureInFlight.has(input.sessionID)) return
    lastPrompt.set(input.sessionID, text)
    captureInFlight.add(input.sessionID)
    try {
      await Promise.all([
        invoke("capture", { text, session_id: input.sessionID, outcome: "pending" }, "global", ctx.worktree),
        invoke("capture", { text, session_id: input.sessionID, outcome: "pending" }, "project", ctx.worktree),
        invoke(
          "telemetry",
          {
            prompt: text,
            predicted_policy_ids: [],
            selected_agent: input.agent ?? "unknown",
            selected_skills: [],
            result: "observed",
          },
          "global",
          ctx.worktree,
        ),
      ])
    } catch {
      // Memory must fail closed and never block an OpenCode session.
    } finally {
      captureInFlight.delete(input.sessionID)
    }
  },

  event: async ({ event }: { event: { type?: string; properties?: { sessionID?: string; info?: { id?: string } } } }) => {
    const sessionID = event.properties?.sessionID ?? event.properties?.info?.id
    if (!sessionID) return
    if (event.type === "session.deleted") lastPrompt.delete(sessionID)
    if (event.type === "session.idle") {
      const text = lastPrompt.get(sessionID)
      if (!text || captureInFlight.has(sessionID)) return
      captureInFlight.add(sessionID)
      try {
        await Promise.all([
          invoke("capture", { text, session_id: sessionID, outcome: "completed" }, "global", ctx.worktree),
          invoke("capture", { text, session_id: sessionID, outcome: "completed" }, "project", ctx.worktree),
        ])
      } catch {
        // Memory must fail closed and never block an OpenCode session.
      } finally {
        captureInFlight.delete(sessionID)
        lastPrompt.delete(sessionID)
      }
    }
  },

  "experimental.chat.system.transform": async (
    input: { sessionID?: string },
    output: { system: string[] },
  ) => {
    const context = await contextFor(lastPrompt.get(input.sessionID ?? "") ?? "", ctx)
    if (context) output.system.push(context)
  },

  "experimental.session.compacting": async (
    input: { sessionID: string },
    output: { context: string[] },
  ) => {
    const context = await contextFor(lastPrompt.get(input.sessionID) ?? "", ctx)
    if (context) output.context.push(context)
  },

  tool: {
    local_memory_search: tool({
      description: "Search local, scrubbed workflow memories without reading raw sessions.",
      args: { query: tool.schema.string() },
      async execute(args: { query: string }) {
        const [global, project] = await Promise.all([
          invoke("search", { query: args.query, limit: 5 }, "global", ctx.worktree),
          invoke("search", { query: args.query, limit: 5 }, "project", ctx.worktree),
        ])
        return JSON.stringify({ global: global.results, project: project.results })
      },
    }),
    local_memory_status: tool({
      description: "Show local memory health, namespace counts, and schema versions.",
      args: {},
      async execute() {
        const [global, project] = await Promise.all([
          invoke("status", {}, "global", ctx.worktree),
          invoke("status", {}, "project", ctx.worktree),
        ])
        return JSON.stringify({ global, project })
      },
    }),
  },
})

export { LOCAL_MEMORY_EVENTS, LOCAL_MEMORY_HOOKS }
