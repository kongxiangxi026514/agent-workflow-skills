# agent-workflow-skills

> 一套可热插拔、跨工具(Cursor / OpenCode / Claude)的 AI 编码 agent 开发 workflow。v3 使用**短 L0 路由 + 按需 policy fragments**，安装器从唯一 `policy-v3/registry.json` 生成产物，零手动拷贝。

## 简介

本仓库把一套"商业级质量优先"的开发 workflow 固化为两类资产:

- **1 个强制脊柱规则**(`rules/workflow-gate.mdc`,`alwaysApply: true`):每轮自动生效的 A/B/C/D 路径门控 + 主/子代理编排 + 全流程 + 质量/架构契约 + 模型路由 + 元认知检查点。它是**规则**,不是 skill —— 安装到项目后每轮强制触发,无需 agent 主动"拉取"。
- **5 个按需 skill**(`skills/`):`first-principles` / `code-review` / `research-routing` / `parallel-dispatch` / `memory-gate`,由 agent 按 `description` 在需要时自动发现调用。

仓库只定义 `build` / `reason` / `review` 三个可移植角色;具体模型 ID 保存在各安装目标的可编辑 JSONC binding 中。安装/卸载全部走脚本,**不需要手动移动或合并任何文件**。

## 组成

| 路径 | 类型 | 角色 | 何时生效 |
| --- | --- | --- | --- |
| `rules/workflow-gate.mdc` | **强制规则** | 脊柱:每轮 A/B/C/D 门控 + 主/子编排 + 全流程 + 质量/架构契约 + 模型路由 + 元认知检查点 | 每轮**强制**自动生效(`alwaysApply: true`) |
| `skills/first-principles/` | 按需 skill | 第一性原理拆解:难/新/模糊问题拆到不可再分、从零推导 + 元认知收尾 | 方案非显然 / 架构定稿前(难/新/模糊,通常 path C) |
| `skills/code-review/` | 按需 skill | 分层 7 层审查 + no-false-negative 复验 + 瘦身/重构纪律;对抗式审查(高风险时叠加) | review diff / PR / 合并前 |
| `skills/research-routing/` | 按需 skill | Context7 / Tavily / GitHub 调研路由 | 查文献 / 文档 / 三方库 / 源码 |
| `skills/parallel-dispatch/` | 按需 skill | 并行 vs 串行拆解 + 角色化模型路由 + 上下文封顶 / 熔断 | 派发子代理前 |
| `skills/memory-gate/` | 按需 skill | AGENTS.md 记忆更新 diff-review 双轨 gate | 任何 agent 想改长期记忆时 |
| `config/model-routing.jsonc` | 模板 | 不含 provider 默认值的三角色 binding 格式 | 安装器首次生成本机副本 |
| `opencode/agents/{build,reason,review}.md` | 配置 | OpenCode 原生三角色 agent,不写主配置 | 安装后自动发现 |

## 一键安装(脚本,零手动拷贝)

安装器先在临时目录渲染/校验,再自动复制全部资产并写 ownership state。文本使用 UTF-8 无 BOM,重复安装/卸载幂等;同名非本包 skill/agent/rule 会在写入前报错。OpenCode 的 `opencode.json` / `opencode.jsonc` **从不读取、修改或创建**:双文件并存或内容损坏都不阻塞安装,原始字节保持不变。

### v3 profile

Cursor 默认安装 `lean`; OpenCode 默认安装 `balanced`。也可用 `-Profile lean|balanced` 或 `--profile lean|balanced` 显式覆盖。profile **只**调整 R0/R1 的升级阈值与 L0/capsule token budget，不复制或改写任何 policy 正文；所有 R2 Strict 触发、加载 `P01,P04` 与独立审查行为完全一致。

生成的 Cursor/OpenCode adapter、按需 skills 和 ownership state 都记录 `policy_id`、fragment hash、registry hash 与 profile。手改已安装生成物或仓库生成物会在下一次刷新前 fail-loud，避免静默覆盖。

Windows / Cursor(把强制脊柱写进某个项目):

```powershell
.\install.ps1 -Tool cursor -Project D:\path\to\your-repo -BuildModel provider/build-id -ReviewModel other/review-id
# 可选：显式覆盖 Cursor 默认 lean
.\install.ps1 -Tool cursor -Project D:\path\to\your-repo -Profile balanced -BuildModel provider/build-id -ReviewModel other/review-id
```

OpenCode(全局 AGENTS.md 自动注入脊柱 + 全局 skills + 三个已绑定模型的 agent):

```bash
./install.sh --tool opencode \
  --build-model provider/build-id --review-model other/review-id
# 可选：显式覆盖 OpenCode 默认 balanced
./install.sh --tool opencode --profile lean \
  --build-model provider/build-id --review-model other/review-id
```

其它组合:

```powershell
.\install.ps1 -Tool all -Project D:\path\to\your-repo `
  -BuildModel provider/build-id -ReasonModel provider/reason-id -ReviewModel other/review-id
.\install.ps1 -Tool claude              # 仅 Claude
```

```bash
./install.sh --tool cursor --project /path/to/your-repo --build-model provider/build-id --review-model other/review-id
./install.sh --tool all --project /path/to/your-repo --build-model provider/build-id --reason-model provider/reason-id --review-model other/review-id
```

参数:`-Tool` / `--tool` 取 `cursor`(默认)`| opencode | claude | all`;安装 Cursor(含 `all`)时必须给 `-Project` / `--project`,避免出现只装 skill、遗漏强制脊柱的不完整状态。

首次安装必须显式提供 `build` 与 `review` ID;`reason` 可省略,此时 binding 写入 `null` 并复用 `build`。PowerShell 使用 `-BuildModel/-ReasonModel/-ReviewModel`(兼容旧 `-OpenCode*Model` 名称),bash 使用 `--build-model/--reason-model/--review-model`。以后直接编辑目标中的 `model-routing.jsonc` 并重跑安装即可刷新生成物。安装器只强制 review ID 不等于 build/effective-reason;任意 provider 字符串不能证明模型家族不同,独立家族仍由用户保证。

```bash
export AGENT_WORKFLOW_OPENCODE_BUILD_MODEL=provider/build-id AGENT_WORKFLOW_OPENCODE_REASON_MODEL=provider/reason-id AGENT_WORKFLOW_OPENCODE_REVIEW_MODEL=different-provider/review-id
./install.sh --tool opencode
```

## 模型路由

`build` 负责实现/重构/调试/常规架构;`reason` 仅用于非显然跨系统权衡、不确定根因或契约级多步推理;`review` 独立审查验证。策略文件不含机器 ID,本机 binding 才是具体映射。

## 强制脊柱说明(诚实标注平台限制)

脊柱如何"每轮强制生效",取决于工具:

- **Cursor(仅项目级)**:`-Project/--project` 自动写入 `.cursor/rules/{workflow-gate,model-routing}.mdc`,binding 位于 `.cursor/agent-workflow-skills/model-routing.jsonc`;脚本不声称存在可编程的全局 Cursor rule。
- **OpenCode(全局)**:默认 config dir 是字面 `~/.config/opencode`,可用 `-OpenCodeConfigDir/--opencode-config-dir` 覆盖。binding/state、skills、`AGENTS.md` 标记块和 `agents/{build,reason,review}.md` 全部自动落位;完成后必须重启 OpenCode。
- **Cursor 平台边界**:Cursor 没有文件式跨项目全局规则,所以脚本要求明确项目路径并自动写入 `.cursor/rules/`;对每个项目执行一次即可,不需要手工移动或粘贴文件。

## 卸载(脚本)

`uninstall` 只删除 state/marker 证明由本包拥有的 skill、agent、binding、Cursor 项目规则和 spine 标记块;同名非本包文件及 OpenCode 主配置保持不变。

```powershell
.\uninstall.ps1 -Tool cursor -Project D:\path\to\your-repo
.\uninstall.ps1 -Tool all -Project D:\path\to\your-repo
```

```bash
./uninstall.sh --tool opencode
./uninstall.sh --tool all --project /path/to/your-repo
```

## 从 installer-v2 安全迁移

1. 不要手动复制 `AGENTS.md`、rules 或 skills；保留现有 machine-local `model-routing.jsonc`。
2. 在仓库更新到包含 `policy-v3/generated/` 的版本后，直接重跑对应安装命令。已有 bundle-owned v2 资产会由 staging 后的 v3 生成物原子替换；`opencode.json` / `opencode.jsonc` 仍零修改。
3. Cursor 默认得到 `lean`，OpenCode 默认得到 `balanced`；如需统一策略，显式传 `Profile`。随后重启 OpenCode。
4. 若提示 generated policy drift，先检查是否手改了受管 adapter/skill；不保留该手改时，运行对应 `uninstall` 后再重装。不要删除 ownership state 或 marker 来绕过检查。

## 验证已生效

- **Cursor 项目脊柱**:确认 `<repo>\.cursor\rules\workflow-gate.mdc` 存在且首部有 `alwaysApply: true`;新开一轮,agent 应在开头 announce 本轮 A/B/C/D 路径。
- **OpenCode**:确认 `~/.config/opencode/{skills,agents}` 与 `AGENTS.md` 标记块已自动生成,然后重启 OpenCode;无需手工复制。
- **按需 skill**:新开一轮发「按 code-review 走,分层审查这段 diff」,应能复述 7 层审查 + no-false-negative 复验。
- **模型路由**:发「说明你读到的模型路由」,应复述 build/reason/review 职责及项目/本机 binding。

## 设计理念

- **hybrid 结构**:1 个强制常驻脊柱 + 5 个按需 skill,职责清晰、可单独增删。
- **质量优先、成本次要但主动管理**:默认 build,仅满足复杂推理条件时升级 reason,并由独立 review 验证。
- **分层触发,不做仪式**:强力模式按需叠加,不是每轮都跑 —— `first-principles`(难/新/模糊设计,通常 path C)、`code-review` 的 adversarial mode(安全/性能/并发敏感或高风险审查,叠加在 7 层之上)、脊柱的 metacognition checkpoint(仅关键节点:派发并行前 / path C·D 设计决策 / 声称完成前);trivial path-A 轮次一律跳过,避免噪声。

## 更多

- 详细安装 / 自动目标路径 / 幂等性 / 卸载说明见 [`INSTALL.md`](./INSTALL.md)。
- 模型路由单点见 [`config/model-routing.md`](./config/model-routing.md)。
- License: MIT。
