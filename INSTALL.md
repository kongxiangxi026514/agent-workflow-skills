# 安装 / 幂等性 / 卸载

本仓库 = **5 个按需 skill**(`skills/`)+ **1 个强制常驻脊柱规则**(`rules/workflow-gate.mdc`,`alwaysApply: true`)+ 模型路由单点配置。安装/卸载全部走脚本,**不再手动拷贝任何文件**。

## 组成

| 路径 | 类型 | 角色 |
| --- | --- | --- |
| `rules/workflow-gate.mdc` | **强制规则** | 脊柱:每轮 A/B/C/D 门控 + 主/子编排 + 全流程 + 质量/架构契约 + 模型路由 + 元认知检查点 |
| `skills/first-principles/` | 按需 skill | 第一性原理拆解:难/新/模糊问题拆到不可再分、从零推导 + 元认知收尾 |
| `skills/code-review/` | 按需 skill | 分层 7 层审查 + no-false-negative 复验 + 瘦身/重构纪律;对抗式审查(高风险时叠加) |
| `skills/research-routing/` | 按需 skill | Context7 / Tavily / GitHub 调研路由 |
| `skills/parallel-dispatch/` | 按需 skill | 并行 vs 串行拆解 + 角色化模型路由(引用单点)+ 上下文封顶/熔断 |
| `skills/memory-gate/` | 按需 skill | AGENTS.md 记忆更新 diff-review 双轨 gate |
| `config/model-routing.md` | 配置 | 模型路由单一真源(角色 → 模型) |
| `opencode/agents/{build,reason,review}.md` | 配置 | OpenCode 原生三角色 agent;不写用户主配置 |

## 脚本参数

| 平台 | 脚本 | 参数 |
| --- | --- | --- |
| Windows / PowerShell | `install.ps1` / `uninstall.ps1` | `-Tool cursor|opencode|claude|all`;Cursor/all 安装必须给 `-Project <path>` |
| macOS / Linux / bash | `install.sh` / `uninstall.sh` | `--tool cursor|opencode|claude|all`;Cursor/all 安装必须给 `--project <path>` |

脚本以自身所在目录为 REPO_ROOT,可从任意工作目录调用。

## Cursor 安装(逐步)

1. 装 5 个按需 skill(全局)并把强制脊柱写进某个项目:

   ```powershell
   .\install.ps1 -Tool cursor -Project D:\path\to\your-repo
   ```

   - `skills/*` → `%USERPROFILE%\.cursor\skills\<skill>\SKILL.md`(覆盖式,自动建目录),Cursor 按 `description` 自动发现调用。
   - `rules/workflow-gate.mdc` → `<repo>\.cursor\rules\workflow-gate.mdc`,`alwaysApply: true`,该项目内**每轮强制**自动生效,纯文件、无需 GUI。

2. 不带 `-Project` 会在任何写入前失败,避免只装 skill 却遗漏强制脊柱。Cursor 没有文件式跨项目全局规则;对每个项目执行脚本即可全自动安装。

## 自动放置清单

| 工具 | 仓库来源 | 自动目标 |
| --- | --- | --- |
| Cursor | `skills/*` | `%USERPROFILE%\.cursor\skills\<skill>\` / `~/.cursor/skills/<skill>/` |
| Cursor(带 Project) | `rules/workflow-gate.mdc` | `<project>/.cursor/rules/workflow-gate.mdc` |
| OpenCode | `skills/*` | `~/.config/opencode/skills/<skill>/` |
| OpenCode | `rules/workflow-gate.mdc` | `~/.config/opencode/AGENTS.md` 标记块 |
| OpenCode | `opencode/agents/{build,reason,review}.md` | `~/.config/opencode/agents/{build,reason,review}.md` |
| Claude | `skills/*` + spine | `~/.claude/skills/<skill>/` + `~/.claude/CLAUDE.md` 标记块 |

脚本自动完成全部复制和注入,无需 agent 或用户再手工移动文件。OpenCode 运行中的会话需在安装后重启。

## OpenCode 安装(逐步)

```bash
./install.sh --tool opencode \
  --opencode-build-model provider/build-id \
  --opencode-reason-model provider/reason-id \
  --opencode-review-model different-provider/review-id
```

- `skills/*` → `~/.config/opencode/skills/<skill>/SKILL.md`。
- 脊柱正文(已剥离 `.mdc` frontmatter)幂等注入 `~/.config/opencode/AGENTS.md`(全局始终加载),用 `<!-- BEGIN agent-workflow-skills spine -->` / `<!-- END agent-workflow-skills spine -->` 标记块包裹。
- `opencode/agents/{build,reason,review}.md` → `~/.config/opencode/agents/`,安装器按三个 ID 渲染 frontmatter 的 `model:`;无需手动移动或编辑。每次都复制 5 个 skill、注入脊柱并渲染三份 agent。
- 先运行 `opencode models`,传入其中准确的 provider/model ID。PowerShell 用 `-OpenCodeBuildModel` / `-OpenCodeReasonModel` / `-OpenCodeReviewModel`;bash 用上述三个 `--opencode-*-model`。环境变量后备是 `AGENT_WORKFLOW_OPENCODE_BUILD_MODEL` / `AGENT_WORKFLOW_OPENCODE_REASON_MODEL` / `AGENT_WORKFLOW_OPENCODE_REVIEW_MODEL`。ID 必须匹配保守单行 YAML 标量 `^[A-Za-z0-9][A-Za-z0-9._-]*(/[A-Za-z0-9][A-Za-z0-9._-]*)+$`,且拒绝空值、控制字符与占位符;review ID 必须不同于 build/reason。字符串不同不能证明家族不同,用户必须选择真实不同 provider/model family 进行 review。
- 用户的 `opencode.json` 或 `opencode.jsonc` 仅做严格 UTF-8 + JSON/JSONC 语法预检,安装前后字节完全相同;不存在时也不会创建。若两者同时存在、配置损坏、标记块损坏或任一同名 agent 不是本包所有,脚本在任何写入前失败并给出路径。安装后重启 OpenCode。
- PowerShell 5.1 使用显式 UTF-8 无 BOM 读写和 UTF-8 console encoding;已有主配置的语法预检需要 Python 3,bash/Python 均强制 UTF-8。注入文件采用临时文件后替换,降低中断写入风险。

## 模型路由

- Cursor:Terra `gpt-5.6-terra-xhigh` 负责实现/重构/调试与常规架构;Sol `gpt-5.6-sol-xhigh` 仅处理真正复杂、困难、需要深度推理的设计或诊断;GLM `glm-5.2-max` 负责审查/验证。
- GLM reviewer 必须与 Terra implementer、Sol reasoner 都属于不同模型家族。具体升级条件和单一真源见 `config/model-routing.md`;修改后同步 `rules/workflow-gate.mdc` 与 `skills/parallel-dispatch/SKILL.md`。
- OpenCode 使用安装器绑定的 provider/model ID,不自动映射上述 Cursor slug,也不修改或创建主配置。

## Claude 安装(逐步)

```bash
./install.sh --tool claude
```

- `skills/*` → `~/.claude/skills/<skill>/SKILL.md`。
- 脊柱正文幂等注入 `~/.claude/CLAUDE.md`(同样的标记块方式)。

## 幂等性(可重复运行)

- **skills**:每次安装先删同名目标文件夹再拷贝,保证内容与仓库一致、不残留旧文件。
- **AGENTS.md / CLAUDE.md 脊柱注入**:用标记块定位。若标记块已存在则**原地替换**,否则追加;文件不存在则创建。因此重复运行只会保留**一个**脊柱块,不会累积。文件里标记块以外的内容原样保留。
- **OpenCode agents**:仅覆盖带本包 ownership marker 的 `build.md` / `reason.md` / `review.md`;遇到任一同名用户文件会失败,不会猜测。带新 ID 重装时只更新本包拥有的 agent。
- **opencode.json / opencode.jsonc**:永不改写;支持注释和尾逗号的 JSONC,也不会创建竞争文件。

## 卸载 / 热插拔

`uninstall` 是 `install` 的逆操作,同样幂等:

```powershell
.\uninstall.ps1 -Tool cursor -Project D:\path\to\your-repo
.\uninstall.ps1 -Tool all -Project D:\path\to\your-repo
```

```bash
./uninstall.sh --tool opencode
./uninstall.sh --tool all --project /path/to/your-repo
```

- 删掉本包拷入的 skill 文件夹(只删本包自带的 5 个名字,不动目标目录里的其它 skill)。
- 移除 `AGENTS.md` / `CLAUDE.md` 里的脊柱标记块,保留文件其余内容。
- 只删除带 ownership marker 的 OpenCode `agents/build.md` / `agents/reason.md` / `agents/review.md`,不删同名用户文件。
- `-Project` 给定时删掉 `<repo>\.cursor\rules\workflow-gate.mdc`。
- `opencode.json` / `opencode.jsonc` **不会被修改或删除**。
- 已不存在的项直接跳过,不报错。

## 验证已生效

- Cursor 项目脊柱:`<repo>\.cursor\rules\workflow-gate.mdc` 存在且首部 `alwaysApply: true`;新开一轮,agent 应在开头 announce 本轮 A/B/C/D 路径。
- 按需 skill:新开一轮发「按 `code-review` 走,分层审查这段 diff」,应复述 7 层审查 + no-false-negative 复验。
- 模型路由:发「说明你读到的模型路由与并行/串行规则」,应复述 Terra 负责常规实现、Sol 仅处理复杂深度推理、GLM 审查且换家族、并行需真正独立。

仓库回归测试使用临时中文路径作为 `HOME` / `USERPROFILE`,覆盖 `.json`、带注释/尾逗号 `.jsonc`、双文件歧义、损坏配置、UTF-8、重复安装/卸载及全部目标路径,不会访问真实用户目录。
