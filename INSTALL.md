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
| `config/model-routing.jsonc` | 模板 | build/reason/review 的无默认 provider binding 格式 |
| `opencode/agents/{build,reason,review}.md` | 配置 | OpenCode 原生三角色 agent;不写用户主配置 |

## 脚本参数

| 平台 | 脚本 | 参数 |
| --- | --- | --- |
| Windows / PowerShell | `install.ps1` / `uninstall.ps1` | `-Tool ...`;Cursor/all 必须给 `-Project`;OpenCode config 可用 `-OpenCodeConfigDir` 覆盖 |
| macOS / Linux / bash | `install.sh` / `uninstall.sh` | `--tool ...`;Cursor/all 必须给 `--project`;OpenCode config 可用 `--opencode-config-dir` 覆盖 |

脚本以自身所在目录为 REPO_ROOT,可从任意工作目录调用。

## Cursor 安装(逐步)

1. 装 5 个按需 skill(全局)并把强制脊柱写进某个项目:

   ```powershell
   .\install.ps1 -Tool cursor -Project D:\path\to\your-repo -BuildModel provider/build-id -ReviewModel other/review-id
   ```

   - `skills/*` → `%USERPROFILE%\.cursor\skills\<skill>\SKILL.md`(覆盖式,自动建目录),Cursor 按 `description` 自动发现调用。
   - `rules/workflow-gate.mdc` 与渲染后的 model adapter → `<repo>\.cursor\rules\`;binding → `<repo>\.cursor\agent-workflow-skills\model-routing.jsonc`。

2. 不带 `-Project` 会在任何写入前失败,避免只装 skill 却遗漏强制脊柱。Cursor 没有文件式跨项目全局规则;对每个项目执行脚本即可全自动安装。

## 自动放置清单

| 工具 | 仓库来源 | 自动目标 |
| --- | --- | --- |
| Cursor | `skills/*` | `%USERPROFILE%\.cursor\skills\<skill>\` / `~/.cursor/skills/<skill>/` |
| Cursor(带 Project) | `rules/workflow-gate.mdc` | `<project>/.cursor/rules/workflow-gate.mdc` |
| Cursor(带 Project) | binding + adapter template | `<project>/.cursor/agent-workflow-skills/model-routing.jsonc` + `.cursor/rules/model-routing.mdc` |
| OpenCode | `skills/*` | `~/.config/opencode/skills/<skill>/` |
| OpenCode | `rules/workflow-gate.mdc` | `~/.config/opencode/AGENTS.md` 标记块 |
| OpenCode | `opencode/agents/{build,reason,review}.md` | `~/.config/opencode/agents/{build,reason,review}.md` |
| OpenCode | binding + ownership state | `~/.config/opencode/agent-workflow-skills/{model-routing.jsonc,install-state.json}` |
| Claude | `skills/*` + spine | `~/.claude/skills/<skill>/` + `~/.claude/CLAUDE.md` 标记块 |

脚本自动完成全部复制和注入,无需 agent 或用户再手工移动文件。OpenCode 运行中的会话需在安装后重启。

## OpenCode 安装(逐步)

```bash
./install.sh --tool opencode \
  --build-model provider/build-id --review-model other/review-id
```

- `skills/*` → `~/.config/opencode/skills/<skill>/SKILL.md`。
- 脊柱正文(已剥离 `.mdc` frontmatter)幂等注入 `~/.config/opencode/AGENTS.md`(全局始终加载),用 `<!-- BEGIN agent-workflow-skills spine -->` / `<!-- END agent-workflow-skills spine -->` 标记块包裹。
- 首次安装用 CLI 明确给 `build` 与 `review`;`reason` 省略即以 JSONC `null` 复用 build。之后编辑 `<config-dir>/agent-workflow-skills/model-routing.jsonc` 并重跑,三个 OpenCode agent 自动刷新;review 保持 `edit: deny`。
- 默认 config dir 是字面 `~/.config/opencode`;覆盖参数同时适用于 install/uninstall。`opencode.json` 和 `opencode.jsonc` 从不读取或改写,双文件、注释、未知字段、损坏内容均逐字节保留。
- 安装器只验证 review ID 不等于 build/effective-reason;provider 字符串不同不能证明模型家族不同。全部 UTF-8 无 BOM;先临时 staging/校验再替换目标,失败校验不改变既有 bundle 状态。完成后必须重启 OpenCode。

## 模型路由

`build` 处理实现/重构/调试/常规架构;`reason` 仅处理非显然跨系统权衡、不确定根因或契约级多步推理;`review` 独立验证。策略可移植,具体 ID 只在各目标 binding 中。

## Claude 安装(逐步)

```bash
./install.sh --tool claude
```

- `skills/*` → `~/.claude/skills/<skill>/SKILL.md`。
- 脊柱正文幂等注入 `~/.claude/CLAUDE.md`(同样的标记块方式)。

## 幂等性(可重复运行)

- **ownership**:`install-state.json` 与 marker 标识本包资产;同名非本包 skill/agent/rule 失败且不覆盖,卸载也保留。
- **AGENTS.md / CLAUDE.md 脊柱注入**:用标记块定位。若标记块已存在则**原地替换**,否则追加;文件不存在则创建。因此重复运行只会保留**一个**脊柱块,不会累积。文件里标记块以外的内容原样保留。
- **OpenCode agents**:仅更新 state/marker 所有的三角色文件;改 binding 后重跑刷新。
- **opencode.json / opencode.jsonc**:零读取、零改写、零竞争文件。

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

- 只删除 ownership state/marker 证明属于本包的 skill/agent/rule/binding;同名用户文件保留。
- 移除 `AGENTS.md` / `CLAUDE.md` 里的脊柱标记块,保留文件其余内容。
- 只删除带 ownership marker 的 OpenCode `agents/build.md` / `agents/reason.md` / `agents/review.md`,不删同名用户文件。
- `-Project` 给定时删掉 `<repo>\.cursor\rules\workflow-gate.mdc`。
- `opencode.json` / `opencode.jsonc` **不会被修改或删除**。
- 已不存在的项直接跳过,不报错。

## 验证已生效

- Cursor 项目脊柱:`<repo>\.cursor\rules\workflow-gate.mdc` 存在且首部 `alwaysApply: true`;新开一轮,agent 应在开头 announce 本轮 A/B/C/D 路径。
- 按需 skill:新开一轮发「按 `code-review` 走,分层审查这段 diff」,应复述 7 层审查 + no-false-negative 复验。
- 模型路由:应复述 build/reason/review 职责及本机/项目 binding。

仓库回归测试使用临时中文路径作为 `HOME` / `USERPROFILE`,覆盖 binding 刷新/null fallback、主配置字节不变、ownership 冲突、rollback-safe validation、UTF-8、重复安装/卸载及 config-dir override,不会访问真实用户目录。
