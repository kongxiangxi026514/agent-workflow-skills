# agent-workflow-skills

> 一套可热插拔、跨工具(Cursor / OpenCode / Claude)的 AI 编码 agent 开发 workflow skills。

## 简介

本仓库把一套“商业级质量优先”的开发 workflow 固化成 **5 个自包含、可热插拔的 skill**。每个 skill 是一个独立文件夹,插上(拷进 skills 目录)即生效,拔掉(删文件夹)即卸载。

每个 `SKILL.md` **完全自包含、无交叉引用**:不依赖本仓库里的任何其它文件,单独增删互不影响,脱离本仓库也能直接用,所以换机器直接拷即可。

## 5 个 skill

| skill 文件夹 | 角色 | 何时触发 |
| --- | --- | --- |
| `workflow-gate` | **脊柱**:每轮 A/B/C/D 路径门控 + 主/子代理编排 + 全流程 + 质量/架构契约 | 每个非平凡编码轮次开头 |
| `code-review` | 分层 7 层审查 + no-false-negative 复验 + 瘦身/重构纪律 | review diff / PR / 合并前 |
| `research-routing` | Context7 / Tavily / GitHub 调研路由 | 查文献 / 文档 / 三方库 / 源码 |
| `parallel-dispatch` | 并行 vs 串行拆解 + 角色化模型路由 + 上下文封顶 / 熔断 | 派发子代理前 |
| `memory-gate` | AGENTS.md 记忆更新 diff-review 双轨 gate | 任何 agent 想改长期记忆时 |

## 安装(分工具)

把 `skills/` 下的 5 个文件夹整体拷到对应工具的全局 skills 目录即可。目标目录:

| 工具 | 目标目录 |
| --- | --- |
| Cursor | `~/.cursor/skills/`(Windows: `%USERPROFILE%\.cursor\skills\`) |
| OpenCode | `~/.config/opencode/skills/`(Windows: `%USERPROFILE%\.config\opencode\skills\`) |
| Claude | `~/.claude/skills/` |

一键拷贝示例(以 Cursor 目标目录为例,换工具只改目标路径):

PowerShell:

```powershell
Copy-Item -Recurse -Force .\skills\* "$env:USERPROFILE\.cursor\skills\"
```

bash:

```bash
mkdir -p ~/.cursor/skills && cp -r ./skills/* ~/.cursor/skills/
```

`SKILL.md` 的 frontmatter 只有通用字段(`name` / `description`),各工具会忽略未知字段,无需改写。

## 让脊柱“每轮强制触发”(可选)

skill 是 **pull 型**,不保证每轮触发。要拿到强制每轮 announce 路径的效果,把 `workflow-gate/SKILL.md` 的**第 1-2 节**放进 always-on 规则:

- **Cursor**:粘到 Settings → Rules(User Rules)。
- **OpenCode**:放进全局 `~/.config/opencode/AGENTS.md`(始终加载)。

其余 4 个按需 skill 保持 pull 型即可,不必进 always-on。

## 热插拔 / 卸载

- 停用某个能力:删除对应 skill 文件夹。
- 全部停用:删除这 5 个文件夹。
- 因为每个 skill 自包含且无交叉引用,单独增删任意一个都不影响其余。

## 设计理念

- **hybrid 结构**:1 个 always-on 脊柱(`workflow-gate`)+ 4 个按需 skill(`code-review` / `research-routing` / `parallel-dispatch` / `memory-gate`)。
- **质量优先、成本次要但主动管理**:优先保证输出质量,同时主动控制 token / 时间成本(控制子代理数量与并行扇出,机械活用够用的便宜模型,顶级模型留给设计 / 审查 / 验证)。
- **角色化模型路由**:implementer 与 reviewer 用**不同模型家族**,规避同模型自我验证的盲区。

## 更多

- 更详细的安装 / 验证 / 卸载说明见 [`INSTALL.md`](./INSTALL.md)。
- License: MIT。
