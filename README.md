# agent-workflow-skills

> 一套可热插拔、跨工具(Cursor / OpenCode / Claude)的 AI 编码 agent 开发 workflow。**5 个按需 skill + 1 个强制常驻脊柱规则**,脚本一键安装,零手动拷贝。

## 简介

本仓库把一套"商业级质量优先"的开发 workflow 固化为两类资产:

- **1 个强制脊柱规则**(`rules/workflow-gate.mdc`,`alwaysApply: true`):每轮自动生效的 A/B/C/D 路径门控 + 主/子代理编排 + 全流程 + 质量/架构契约 + 模型路由 + 元认知检查点。它是**规则**,不是 skill —— 安装到项目后每轮强制触发,无需 agent 主动"拉取"。
- **5 个按需 skill**(`skills/`):`first-principles` / `code-review` / `research-routing` / `parallel-dispatch` / `memory-gate`,由 agent 按 `description` 在需要时自动发现调用。

模型路由由 `config/model-routing.md` 统一说明;OpenCode 的 build/reason/review 角色使用独立原生 agent 文件。安装/卸载全部走脚本,**不需要手动移动或合并任何文件**。

## 组成

| 路径 | 类型 | 角色 | 何时生效 |
| --- | --- | --- | --- |
| `rules/workflow-gate.mdc` | **强制规则** | 脊柱:每轮 A/B/C/D 门控 + 主/子编排 + 全流程 + 质量/架构契约 + 模型路由 + 元认知检查点 | 每轮**强制**自动生效(`alwaysApply: true`) |
| `skills/first-principles/` | 按需 skill | 第一性原理拆解:难/新/模糊问题拆到不可再分、从零推导 + 元认知收尾 | 方案非显然 / 架构定稿前(难/新/模糊,通常 path C) |
| `skills/code-review/` | 按需 skill | 分层 7 层审查 + no-false-negative 复验 + 瘦身/重构纪律;对抗式审查(高风险时叠加) | review diff / PR / 合并前 |
| `skills/research-routing/` | 按需 skill | Context7 / Tavily / GitHub 调研路由 | 查文献 / 文档 / 三方库 / 源码 |
| `skills/parallel-dispatch/` | 按需 skill | 并行 vs 串行拆解 + 角色化模型路由 + 上下文封顶 / 熔断 | 派发子代理前 |
| `skills/memory-gate/` | 按需 skill | AGENTS.md 记忆更新 diff-review 双轨 gate | 任何 agent 想改长期记忆时 |
| `config/model-routing.md` | 配置 | 模型路由**单一真源**(角色 → 模型) | 换模型时改这里 |
| `opencode/agents/{build,reason,review}.md` | 配置 | OpenCode 原生三角色 agent,不写主配置 | 安装后自动发现 |

## 一键安装(脚本,零手动拷贝)

安装脚本会自动复制全部 5 个 skill、注入强制脊柱并渲染全部 3 个 OpenCode 原生 agent,无需手动移动或编辑。文本按 UTF-8 处理,重复安装幂等。OpenCode 的 `opencode.json` / `opencode.jsonc` 只做 UTF-8 与语法预检,**始终逐字节保持不变**;两者同时存在或任一文件损坏时,在任何写入前失败。

Windows / Cursor(把强制脊柱写进某个项目):

```powershell
.\install.ps1 -Tool cursor -Project D:\path\to\your-repo
```

OpenCode(全局 AGENTS.md 自动注入脊柱 + 全局 skills + 三个已绑定模型的 agent):

```bash
./install.sh --tool opencode \
  --opencode-build-model provider/build-id \
  --opencode-reason-model provider/reason-id \
  --opencode-review-model different-provider/review-id
```

其它组合:

```powershell
.\install.ps1 -Tool all -Project D:\path\to\your-repo `
  -OpenCodeBuildModel provider/build-id -OpenCodeReasonModel provider/reason-id `
  -OpenCodeReviewModel different-provider/review-id
.\install.ps1 -Tool claude              # 仅 Claude
```

```bash
./install.sh --tool cursor --project /path/to/your-repo
./install.sh --tool all --project /path/to/your-repo --opencode-build-model provider/build-id --opencode-reason-model provider/reason-id --opencode-review-model different-provider/review-id
```

参数:`-Tool` / `--tool` 取 `cursor`(默认)`| opencode | claude | all`;安装 Cursor(含 `all`)时必须给 `-Project` / `--project`,避免出现只装 skill、遗漏强制脊柱的不完整状态。

OpenCode 安装(含 `all`)必须提供三个模型 ID:PowerShell 参数是 `-OpenCodeBuildModel` / `-OpenCodeReasonModel` / `-OpenCodeReviewModel`,bash 参数是 `--opencode-build-model` / `--opencode-reason-model` / `--opencode-review-model`。也可设环境变量 `AGENT_WORKFLOW_OPENCODE_BUILD_MODEL` / `AGENT_WORKFLOW_OPENCODE_REASON_MODEL` / `AGENT_WORKFLOW_OPENCODE_REVIEW_MODEL` 后执行同一命令。先运行 `opencode models`,传入其中准确的 provider/model ID;安装器只接受保守的单行 YAML 标量 `^[A-Za-z0-9][A-Za-z0-9._-]*(/[A-Za-z0-9][A-Za-z0-9._-]*)+$`,拒绝空值、控制字符和占位符。review ID 必须不同于 build/reason ID,但字符串不同不能证明模型家族不同,用户仍须选择真正不同的 provider/model family。

```bash
export AGENT_WORKFLOW_OPENCODE_BUILD_MODEL=provider/build-id AGENT_WORKFLOW_OPENCODE_REASON_MODEL=provider/reason-id AGENT_WORKFLOW_OPENCODE_REVIEW_MODEL=different-provider/review-id
./install.sh --tool opencode
```

## 模型路由(动态单点)

- **Cursor 单一真源** = `config/model-routing.md`(角色 → Cursor slug)。OpenCode 不自动映射 Terra / Sol / GLM slug,而是由安装命令绑定用户通过 `opencode models` 查得的等价 provider/model ID。
- 当前分配(Cursor slug):Terra `gpt-5.6-terra-xhigh` 负责实现/重构/调试与常规架构;Sol `gpt-5.6-sol-xhigh` 仅负责真正复杂、困难、需要深度推理的设计或诊断;GLM `glm-5.2-max` 负责审查/验证。
- **硬规则**:GLM reviewer 必须与 Terra implementer、Sol reasoner 都属于**不同模型家族**,规避同家族自我验证盲区。
- **换 Cursor 模型** = 改单一真源并同步 `rules/workflow-gate.mdc`、`skills/parallel-dispatch/SKILL.md`;**换 OpenCode 模型** = 带三个新 ID 重跑安装命令,它会只更新本包拥有的三份 agent,不向用户主配置注入 model key。

## 强制脊柱说明(诚实标注平台限制)

脊柱如何"每轮强制生效",取决于工具:

- **Cursor(项目级,脚本自动写入)**:`install.ps1 -Project <repo>` 把 `rules/workflow-gate.mdc`(`alwaysApply: true`)写进 `<repo>\.cursor\rules\`,该项目内每轮自动生效,纯文件、无需 GUI。
- **OpenCode(全局,脚本全自动)**:5 个 skill 写入 `~/.config/opencode/skills/`,脊柱幂等注入 `AGENTS.md`,并渲染 build/reason/review 到 `agents/*.md`;主配置 `.json` / `.jsonc` 不改、不新建且保持原始字节。完成后必须重启 OpenCode。
- **Cursor 平台边界**:Cursor 没有文件式跨项目全局规则,所以脚本要求明确项目路径并自动写入 `.cursor/rules/`;对每个项目执行一次即可,不需要手工移动或粘贴文件。

## 卸载(脚本)

`uninstall` 只删除本包拥有的 skill、OpenCode agent、Cursor 项目规则和 `AGENTS.md` / `CLAUDE.md` 标记块;保留其它内容及 `opencode.json` / `opencode.jsonc` 原始字节。重复卸载也安全。

```powershell
.\uninstall.ps1 -Tool cursor -Project D:\path\to\your-repo
.\uninstall.ps1 -Tool all -Project D:\path\to\your-repo
```

```bash
./uninstall.sh --tool opencode
./uninstall.sh --tool all --project /path/to/your-repo
```

## 验证已生效

- **Cursor 项目脊柱**:确认 `<repo>\.cursor\rules\workflow-gate.mdc` 存在且首部有 `alwaysApply: true`;新开一轮,agent 应在开头 announce 本轮 A/B/C/D 路径。
- **OpenCode**:确认 `~/.config/opencode/{skills,agents}` 与 `AGENTS.md` 标记块已自动生成,然后重启 OpenCode;无需手工复制。
- **按需 skill**:新开一轮发「按 code-review 走,分层审查这段 diff」,应能复述 7 层审查 + no-false-negative 复验。
- **模型路由**:发「说明你读到的模型路由与并行/串行规则」,应复述 Terra 负责常规实现、Sol 仅处理复杂深度推理、GLM 审查且换家族、并行需真正独立。

## 设计理念

- **hybrid 结构**:1 个强制常驻脊柱 + 5 个按需 skill,职责清晰、可单独增删。
- **质量优先、成本次要但主动管理**:默认 Terra,仅在满足复杂深度推理条件时升级 Sol,审查/验证固定 GLM;控制子代理数量与并行扇出。
- **角色化模型路由**:Terra / Sol 与 GLM reviewer 用**不同模型家族**,规避同家族自我验证盲区。
- **分层触发,不做仪式**:强力模式按需叠加,不是每轮都跑 —— `first-principles`(难/新/模糊设计,通常 path C)、`code-review` 的 adversarial mode(安全/性能/并发敏感或高风险审查,叠加在 7 层之上)、脊柱的 metacognition checkpoint(仅关键节点:派发并行前 / path C·D 设计决策 / 声称完成前);trivial path-A 轮次一律跳过,避免噪声。

## 更多

- 详细安装 / 自动目标路径 / 幂等性 / 卸载说明见 [`INSTALL.md`](./INSTALL.md)。
- 模型路由单点见 [`config/model-routing.md`](./config/model-routing.md)。
- License: MIT。
