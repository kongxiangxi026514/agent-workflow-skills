# agent-workflow-skills

一套面向 Cursor、OpenCode 和 Claude 的可移植 AI 编码工作流。v3 以短小的 L0 路由器决定风险和按需加载的策略片段；安装器从唯一的 `policy-v3/registry.json` 渲染受管产物，而不是要求手工复制规则。

## 适用场景与边界

适合希望在多个 AI 编码主机上保留一致的任务路由、审查和交付纪律的个人或团队：

- 将日常问答、小改动、普通实现和高风险变更区分处理；
- 让复杂工作按需加载生命周期、研究、推理、派发或审查指导；
- 将具体模型选择留在机器本地的 JSONC binding，而非固化到可移植策略中；
- 用安装器管理受管规则、skills 和 ownership state，并在刷新前发现漂移。

本项目不提供模型、模型访问权限、托管运行时、CI 服务或安全控制替代品；它也不保证某个主机实际选择的运行时模型。请把主机的权限、审批、代码审查和测试作为独立控制。

## v3 架构

`policy-v3/registry.json` 是唯一策略源。渲染后的 L0 adapter 始终保持短小，详细能力仅在任务匹配时加载：

| 层级 | 内容 | 作用 |
| --- | --- | --- |
| L0 | `workflow-gate` | 路由风险、加载所需策略，并约束 worker capsule。 |
| L1 | 六个 generated skills | 将生命周期、推理、审查、研究、派发和记忆保护按需提供。 |
| 本机 binding | `model-routing.jsonc` | 将 `build`、`reason`、`review` 角色映射到当前主机可用的 ID。 |

六个 skills 分别是 `workflow-lifecycle`、`first-principles`、`code-review`、`research-routing`、`parallel-dispatch` 和 `memory-gate`。它们是 agent 指导，不是运行时 Python/Node 依赖。

### 风险与模型角色

- **R0**：问答、只读检查或低风险小改动；只做轻量核验。
- **R1**：普通实现或多文件工作；加载 `P01`，执行针对性测试并检查 diff。
- **R2**：安全、持久化 schema、几何/坐标、训练或 ground-truth 语义、生产部署和破坏性操作；加载 `P01` 与 `P04`，并要求独立审查。

`build` 负责实现、重构和常规调试；`reason` 仅用于非显然权衡或未知根因；`review` 用于独立验证。安装后的 JSONC binding 可编辑：修改本机 binding 后重跑同一安装命令，即会刷新受管产物。`reason: null` 会复用 `build`；`review` ID 必须不同于 `build` 和有效 `reason`。安装器只验证 ID 不等性，不能从 provider 字符串推断模型家族独立性。

### Profiles

Cursor 默认 `lean`；OpenCode 和 Claude 默认 `balanced`。`lean`/`balanced` 仅改变 R0/R1 升级阈值与 L0/capsule 预算，**不会**复制两套策略正文，也不会改变 R2 的 strict 触发、`P01,P04` 加载或独立审查要求。使用 `-Profile lean|balanced`（PowerShell）或 `--profile lean|balanced`（bash）显式覆盖。

## 安装前提

支持的安装路径需要：

1. **Git**：获取、升级或回滚此 source checkout。
2. **可执行的 Python 3**：安装器用它校验 JSONC、binding 和生成物。
3. **至少一个主机**：Cursor、OpenCode 或 Claude。

Windows 使用 PowerShell 脚本；Linux 和 macOS 使用 bash 脚本。示例中的 `sample-*` / `sample/*` 是仅为通过 CLI 格式校验的示例 ID，不代表真实、可用或推荐的运行时模型。首次安装 Cursor 或 OpenCode 时必须提供 `build` 与 `review` ID。

### 可选集成（不安装、不配置）

本项目可在已由主机配置的外部工具存在时指导 agent 使用它们，但不会安装、认证或读取它们：

- [Cursor Rules](https://cursor.com/docs/rules)、[Agent Skills](https://cursor.com/docs/skills) 和 [MCP](https://cursor.com/docs/mcp)；
- [Context7](https://github.com/upstash/context7)；
- [Tavily MCP](https://docs.tavily.com/documentation/mcp)；
- [GitHub MCP Server](https://github.com/github/github-mcp-server)。

`continual-learning`、Trackio、grill-me、Trellis 和 Superpowers **不是**本项目的依赖；不需要安装它们来使用 v3。

## 安装

先在任意目录取得公开 source checkout：

```powershell
git clone https://github.com/kongxiangxi026514/agent-workflow-skills.git
Set-Location .\agent-workflow-skills
```

```bash
git clone https://github.com/kongxiangxi026514/agent-workflow-skills.git
cd agent-workflow-skills
```

### Cursor：每个项目 checkout 安装一次

Cursor 的 L0 adapter、规则和 binding 都写入传入的 `-Project` / `--project`。因此**每个 Cursor 项目 checkout**（包括每个独立 worktree）都要运行一次；source checkout 本身不是安装目标项目。

```powershell
.\install.ps1 -Tool cursor -Project "D:\src\my-project" `
  -BuildModel sample-build-v1 -ReviewModel sample-review-v1
```

```bash
./install.sh --tool cursor --project "/work/my-project" \
  --build-model sample-build-v1 --review-model sample-review-v1
```

受管规则写入 `<project>/.cursor/rules/`；Cursor binding 写入 `<project>\.cursor\agent-workflow-skills\model-routing.jsonc`（Windows）或 `<project>/.cursor/agent-workflow-skills/model-routing.jsonc`（Linux/macOS）。该 binding 是机器本地配置：不要提交它；如项目没有忽略规则，请在该 checkout 的 `.git/info/exclude` 中忽略 `.cursor/agent-workflow-skills/`。

### OpenCode：机器级安装

OpenCode 默认使用 `$HOME/.config/opencode`；可用 `-OpenCodeConfigDir` / `--opencode-config-dir` 指向另一个目录。它安装 generated skills、带标记的 `AGENTS.md` spine 和本机 binding，并且只在明确授权时将三角色写入一个 OpenCode JSON/JSONC `agent` 映射；完成后重启 OpenCode。

```powershell
.\install.ps1 -Tool opencode -OpenCodeConfigDir "$HOME\.config\opencode" `
  -MigrateOpenCodeModelConfig `
  -BuildModel sample/build-v1 -ReviewModel sample/review-v1
```

```bash
./install.sh --tool opencode --opencode-config-dir "$HOME/.config/opencode" \
  --migrate-opencode-model-config \
  --build-model sample/build-v1 --review-model sample/review-v1
```

OpenCode binding 位于 `<config-dir>/agent-workflow-skills/model-routing.jsonc`。为保护已有配置，默认安装会 fail-loud；只有带迁移 opt-in 才读取并修改一个选定的 `opencode.json` / `opencode.jsonc`。`-OpenCodeModelConfig` / `--opencode-model-config` 可显式选择其一；否则仅在恰好一个存在时自动选择，都不存在时新建 `opencode.jsonc`，两个同时存在时拒绝。迁移会在 `<config-dir>/agent-workflow-skills/migration-backups/` 逐字节备份原文件，并记录 SHA-256 audit。若 `agents/` 中已有自定义的 `build.md`、`reason.md` 或 `review.md`，安装器不会移动它：请先手动重命名或迁移该 agent，再重试。迁移使用排他 lock 和尽力的 no-follow/reparse identity 检查来防御正常并发；同一 OS 用户能在检查与提交之间恶意替换目录的场景超出此纯 Python 跨平台机制的安全保证。

### Claude：机器级安装

Claude 不接受本项目的模型参数；它安装 generated skills、`CLAUDE.md` 中带标记的 v3 spine 和 ownership state。

```powershell
.\install.ps1 -Tool claude
```

```bash
./install.sh --tool claude
```

目标是 Windows 的 `%USERPROFILE%\.claude\`，以及 Linux/macOS 的 `~/.claude/`。

### 同时安装所有主机

`all` 不能使用通用模型参数，避免把 Cursor 和 OpenCode binding 混在一起；必须使用平台专用参数。

```powershell
.\install.ps1 -Tool all -Project "D:\src\my-project" `
  -MigrateOpenCodeModelConfig `
  -CursorBuildModel sample-build-v1 -CursorReviewModel sample-review-v1 `
  -OpenCodeBuildModel sample/build-v1 -OpenCodeReviewModel sample/review-v1
```

```bash
./install.sh --tool all --project "/work/my-project" \
  --migrate-opencode-model-config \
  --cursor-build-model sample-build-v1 --cursor-review-model sample-review-v1 \
  --opencode-build-model sample/build-v1 --opencode-review-model sample/review-v1
```

可选的 `reason` 参数为 `-ReasonModel` / `--reason-model`，或 `all` 的对应平台专用形式。安装后可直接编辑本机 binding，再用相同的 OpenCode migration flag 重跑对应 host；不要将 binding、迁移备份或 audit 提交到 source checkout 或目标项目。

## 升级、卸载与回滚

### 升级

在干净的 source checkout 中更新到公开主线，再重跑原来使用的安装命令。安装器会验证受管生成物，保留已有有效 binding，并拒绝静默覆盖手改的受管文件。

```bash
git fetch origin
git switch main
git pull --ff-only origin main
```

如果 source checkout 或目标配置有未解决的本地改动，先检查并处理它们；不要用 `git reset --hard`、`git clean` 或删除 ownership state 来“修复”漂移。

### 卸载

卸载只移除 ownership state 或 marker 证明属于本项目的文件；OpenCode 仅删除 audit 中仍与受管值一致的 `agent.build/reason/review` 字段，绝不恢复或写回旧的 Markdown `model:` 硬编码。

```powershell
.\uninstall.ps1 -Tool cursor -Project "D:\src\my-project"
.\uninstall.ps1 -Tool opencode -OpenCodeConfigDir "$HOME\.config\opencode"
.\uninstall.ps1 -Tool claude
```

```bash
./uninstall.sh --tool cursor --project "/work/my-project"
./uninstall.sh --tool opencode --opencode-config-dir "$HOME/.config/opencode"
./uninstall.sh --tool claude
```

使用 `-Tool all` / `--tool all` 时，仍须为 Cursor 提供项目路径。卸载会删除 bundle-owned binding；若要在另一版本中复用它，先在安全的机器本地位置备份，且不要提交该副本。

Cursor 的 `~/.cursor/skills` 在多个项目间共享，因此项目卸载默认保留它们。确认不再被任何项目使用时，才显式传 `-RemoveGlobalSkills`（PowerShell）或 `--remove-global-skills`（bash）；脚本会先验证 marker 与生成内容，验证失败不会删除任何 global skill。

### 回滚

回滚先改变**干净的 source checkout**，再用该版本的文档重跑安装器：

```bash
git rev-parse HEAD
git switch --detach <known-good-commit>
```

`<known-good-commit>` 是需要替换的 Git 提交；它不是可直接执行的字面值。若已安装的 bundle 需要降级，先用当前版本执行对应卸载，再按旧版本 README 安装。这样不会假定不同版本的 ownership 格式互相兼容。

## 验证与故障排查

在 source checkout 根目录验证生成物、策略审计和完整测试：

```powershell
python .\tools\render_policy.py --check
python .\tools\audit_context_budget.py --json
python -m unittest discover -s tests -v
```

```bash
python3 tools/render_policy.py --check
python3 tools/audit_context_budget.py --json
python3 -m unittest discover -s tests -v
```

安装后，Cursor 检查 `<project>/.cursor/rules/workflow-gate.mdc` 是否存在且带 `alwaysApply: true`；OpenCode 检查 `<config-dir>/skills`、`AGENTS.md` 标记块、选定配置里的 `agent.build/reason/review` 和 migration audit 后重启；Claude 检查 `~/.claude/skills`、`CLAUDE.md` 标记块和 `agent-workflow-skills/install-state.json`。这些是文件安装检查，不是任何主机或模型实际行为的保证。

常见问题：

- **缺少 Python 3**：安装器会在写入前停止；安装可执行的 Python 3 后重试。
- **Cursor 提示缺少项目路径**：`cursor` 和 `all` 必须给 `-Project` / `--project`，因为 L0 规则按 checkout 写入。
- **generated policy drift**：不要手改 generated adapter 或 skill；审阅改动后运行对应卸载，再从 source checkout 重装。
- **ownership 冲突**：安装器拒绝覆盖不属于 bundle 的同名文件。选择另一个配置目录，或人工决定如何迁移，切勿删除 marker 绕过检查。
- **OpenCode 迁移被拒绝**：显式传 migration flag；检查仅有一个 `opencode.json` / `opencode.jsonc`，或用 `--opencode-model-config` 选择目标。不要删除 backup/audit 绕过冲突。
- **OpenCode 未加载新内容**：重启 OpenCode。MCP 未配置不会阻塞本项目安装。

## 隐私、安全与平台边界

- 安装脚本从当前 source checkout 渲染和复制文件；Git 更新是你显式执行的网络操作。脚本不配置 Context7、Tavily 或 GitHub MCP，也不要求或示例化 API token。
- 把 model ID、MCP 凭据和本机 binding 视为机器配置；保存在项目外或 `.git/info/exclude` 保护的路径中，避免提交、日志或截图泄露。
- MCP 服务器应只来自可信来源，并采用最小权限、受限 token 和代码审计；参见 [Cursor MCP security guidance](https://cursor.com/docs/mcp)。
- Cursor 安装是显式 target project 的按-checkout 行为；OpenCode 和 Claude 安装是各自用户配置目录的机器级行为。脚本不管理其他全局规则、主机设置或远程服务。
- 受管文件的 provenance/hash 用于漂移保护，不替代签名验证、备份、测试或独立安全审查。

## 进一步阅读

- 详细目标路径、幂等性和所有脚本参数：[INSTALL.md](./INSTALL.md)
- 角色与 binding 契约：[config/model-routing.md](./config/model-routing.md)
- License: [MIT](./LICENSE)
