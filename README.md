# agent-workflow-skills

> 一套可热插拔、跨工具(Cursor / OpenCode / Claude)的 AI 编码 agent 开发 workflow。**4 个按需 skill + 1 个强制常驻脊柱规则**,脚本一键安装,零手动拷贝。

## 简介

本仓库把一套"商业级质量优先"的开发 workflow 固化为两类资产:

- **1 个强制脊柱规则**(`rules/workflow-gate.mdc`,`alwaysApply: true`):每轮自动生效的 A/B/C/D 路径门控 + 主/子代理编排 + 全流程 + 质量/架构契约 + 模型路由。它是**规则**,不是 skill —— 安装到项目后每轮强制触发,无需 agent 主动"拉取"。
- **4 个按需 skill**(`skills/`):`code-review` / `research-routing` / `parallel-dispatch` / `memory-gate`,由 agent 按 `description` 在需要时自动发现调用。

模型路由是**动态单点配置**:改一个地方(`config/model-routing.md` + OpenCode 的 `opencode.json`)即可换模型。安装/卸载全部走脚本,**不再需要手动拷贝任何文件**。

## 组成

| 路径 | 类型 | 角色 | 何时生效 |
| --- | --- | --- | --- |
| `rules/workflow-gate.mdc` | **强制规则** | 脊柱:每轮 A/B/C/D 门控 + 主/子编排 + 全流程 + 质量/架构契约 + 模型路由 | 每轮**强制**自动生效(`alwaysApply: true`) |
| `skills/code-review/` | 按需 skill | 分层 7 层审查 + no-false-negative 复验 + 瘦身/重构纪律 | review diff / PR / 合并前 |
| `skills/research-routing/` | 按需 skill | Context7 / Tavily / GitHub 调研路由 | 查文献 / 文档 / 三方库 / 源码 |
| `skills/parallel-dispatch/` | 按需 skill | 并行 vs 串行拆解 + 角色化模型路由 + 上下文封顶 / 熔断 | 派发子代理前 |
| `skills/memory-gate/` | 按需 skill | AGENTS.md 记忆更新 diff-review 双轨 gate | 任何 agent 想改长期记忆时 |
| `config/model-routing.md` | 配置 | 模型路由**单一真源**(角色 → 模型) | 换模型时改这里 |
| `opencode/opencode.json` | 配置 | OpenCode 的 `agent.build` / `agent.review` 模型 + instructions 单点 | OpenCode 换模型时改这里 |

## 一键安装(脚本,零手动拷贝)

安装脚本会:拷 `skills/*` 到工具的全局 skills 目录;把脊柱写成对应工具的常驻规则(Cursor 项目 `.cursor/rules/` / OpenCode 全局 `AGENTS.md`)。**幂等**,重复运行不会重复写入。

Windows / Cursor(把强制脊柱写进某个项目):

```powershell
.\install.ps1 -Tool cursor -Project D:\path\to\your-repo
```

不带 `-Project` 只装 4 个 skill,并提示脊柱的写入方式(见下方"强制脊柱说明"):

```powershell
.\install.ps1 -Tool cursor
```

OpenCode(全局 AGENTS.md 自动注入脊柱 + 全局 skills):

```bash
./install.sh --tool opencode
```

其它组合:

```powershell
.\install.ps1 -Tool all                 # cursor + opencode + claude 全装
.\install.ps1 -Tool claude              # 仅 Claude
```

```bash
./install.sh --tool cursor --project /path/to/your-repo
./install.sh --tool all
```

参数:`-Tool` / `--tool` 取 `cursor`(默认)`| opencode | claude | all`;`-Project` / `--project` 为可选项目路径(仅 Cursor 用来写项目级强制规则)。

## 模型路由(动态单点)

- **单一真源** = `config/model-routing.md`(角色 → 模型)。OpenCode 另有 `opencode/opencode.json` 的 `agent.build.model` / `agent.review.model`。
- 当前分配(Cursor slug):implementer(实现/重构/调试)= `claude-opus-4-8-thinking-xhigh`(难任务 → `claude-opus-4-8-thinking-max`);reviewer(审查/验证)= `gpt-5.5-extra-high`。
- **硬规则**:reviewer 必须与 implementer 属于**不同模型家族**,规避同模型自我验证盲区。
- **换模型 = 只改单点**:Cursor 改 `config/model-routing.md`(并同步 `rules/workflow-gate.mdc` 的 Model routing 段);OpenCode 改 `opencode/opencode.json` 的两个 `REPLACE_WITH_*_MODEL_ID`(真实 id 用 `opencode models` 查,例:build 用 GLM 5.2 / review 用 Kimi K2.6 —— 不同家族)。

## 强制脊柱说明(诚实标注平台限制)

脊柱如何"每轮强制生效",取决于工具:

- **Cursor(项目级,脚本自动写入)**:`install.ps1 -Project <repo>` 把 `rules/workflow-gate.mdc`(`alwaysApply: true`)写进 `<repo>\.cursor\rules\`,该项目内每轮自动生效,纯文件、无需 GUI。
- **OpenCode(全局,脚本自动注入)**:`install.sh --tool opencode` 把脊柱正文幂等注入 `~/.config/opencode/AGENTS.md`(全局始终加载),用 `<!-- BEGIN/END agent-workflow-skills spine -->` 标记块包裹,可重复运行、可被 uninstall 精确移除。
- **唯一需要手动的一步(Cursor 平台限制,不隐瞒)**:Cursor **没有**基于文件的"跨项目全局常驻规则"。若想让脊柱对**所有** Cursor 项目生效,需要一次性在 Settings → Rules 里手动粘贴 `rules/workflow-gate.mdc` 的内容。这是 Cursor 平台目前唯一无法脚本化的动作;按项目 `.cursor/rules/` 写入则完全自动。

## 卸载(脚本)

`uninstall` 是 `install` 的逆操作:删掉本包拷入的 skill 文件夹、移除 `AGENTS.md` / `CLAUDE.md` 里的脊柱标记块(保留文件其余内容),`-Project` 给定时删掉项目里的 `workflow-gate.mdc`。幂等,已不存在也不报错。`opencode.json` 不会被删(可能被你改过)。

```powershell
.\uninstall.ps1 -Tool cursor -Project D:\path\to\your-repo
.\uninstall.ps1 -Tool all
```

```bash
./uninstall.sh --tool opencode
./uninstall.sh --tool all
```

## 验证已生效

- **Cursor 项目脊柱**:确认 `<repo>\.cursor\rules\workflow-gate.mdc` 存在且首部有 `alwaysApply: true`;新开一轮,agent 应在开头 announce 本轮 A/B/C/D 路径。
- **按需 skill**:新开一轮发「按 code-review 走,分层审查这段 diff」,应能复述 7 层审查 + no-false-negative 复验。
- **模型路由**:发「说明你读到的 build/review 模型路由与并行/串行规则」,应复述 implementer 用强模型 / reviewer 换家族 / 并行需真正独立。

## 设计理念

- **hybrid 结构**:1 个强制常驻脊柱 + 4 个按需 skill,职责清晰、可单独增删。
- **质量优先、成本次要但主动管理**:顶级模型留给设计 / 审查 / 验证,机械活用够用的便宜快模型;控制子代理数量与并行扇出。
- **角色化模型路由**:implementer 与 reviewer 用**不同模型家族**,规避同模型自我验证盲区。

## 更多

- 详细安装 / 幂等性 / 卸载 / Cursor GUI 说明见 [`INSTALL.md`](./INSTALL.md)。
- 模型路由单点见 [`config/model-routing.md`](./config/model-routing.md)。
- License: MIT。
