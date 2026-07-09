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
| `opencode/opencode.json` | 配置 | OpenCode `agent.build` / `agent.review` 模型 + instructions 单点 |

## 脚本参数

| 平台 | 脚本 | 参数 |
| --- | --- | --- |
| Windows / PowerShell | `install.ps1` / `uninstall.ps1` | `-Tool cursor|opencode|claude|all`(默认 `cursor`);`-Project <path>`(可选) |
| macOS / Linux / bash | `install.sh` / `uninstall.sh` | `--tool cursor|opencode|claude|all`(默认 `cursor`);`--project <path>`(可选) |

脚本以自身所在目录为 REPO_ROOT,可从任意工作目录调用。

## Cursor 安装(逐步)

1. 装 5 个按需 skill(全局)并把强制脊柱写进某个项目:

   ```powershell
   .\install.ps1 -Tool cursor -Project D:\path\to\your-repo
   ```

   - `skills/*` → `%USERPROFILE%\.cursor\skills\<skill>\SKILL.md`(覆盖式,自动建目录),Cursor 按 `description` 自动发现调用。
   - `rules/workflow-gate.mdc` → `<repo>\.cursor\rules\workflow-gate.mdc`,`alwaysApply: true`,该项目内**每轮强制**自动生效,纯文件、无需 GUI。

2. 若不带 `-Project`,只装 5 个 skill,并打印脊柱写入提示:

   ```powershell
   .\install.ps1 -Tool cursor
   ```

3. **唯一需要手动的一步(Cursor 平台限制)**:Cursor **没有**基于文件的"跨项目全局常驻规则"。要让脊柱对**所有** Cursor 项目生效,只能一次性在 **Settings → Rules** 里手动粘贴 `rules/workflow-gate.mdc` 的内容(User Rules)。逐项目用 `.cursor/rules/` 则完全自动、无需 GUI。这一点如实标注,不做假自动化。

## OpenCode 安装(逐步)

```bash
./install.sh --tool opencode
```

- `skills/*` → `~/.config/opencode/skills/<skill>/SKILL.md`。
- 脊柱正文(已剥离 `.mdc` frontmatter)幂等注入 `~/.config/opencode/AGENTS.md`(全局始终加载),用 `<!-- BEGIN agent-workflow-skills spine -->` / `<!-- END agent-workflow-skills spine -->` 标记块包裹。
- `opencode/opencode.json` → `~/.config/opencode/opencode.json`,**仅当该文件不存在时**才拷贝;已存在则不覆盖,并提示你手动合并其中的 `agent` 块(避免覆盖你已有的 OpenCode 配置)。
- 换模型:改 `opencode.json` 的 `agent.build.model` / `agent.review.model`(把 `REPLACE_WITH_*_MODEL_ID` 换成 `opencode models` 查到的真实 id;build 与 review 必须不同家族)。

## Claude 安装(逐步)

```bash
./install.sh --tool claude
```

- `skills/*` → `~/.claude/skills/<skill>/SKILL.md`。
- 脊柱正文幂等注入 `~/.claude/CLAUDE.md`(同样的标记块方式)。

## 幂等性(可重复运行)

- **skills**:每次安装先删同名目标文件夹再拷贝,保证内容与仓库一致、不残留旧文件。
- **AGENTS.md / CLAUDE.md 脊柱注入**:用标记块定位。若标记块已存在则**原地替换**,否则追加;文件不存在则创建。因此重复运行只会保留**一个**脊柱块,不会累积。文件里标记块以外的内容原样保留。
- **opencode.json**:已存在则不动(提示手动合并 `agent` 块)。

## 卸载 / 热插拔

`uninstall` 是 `install` 的逆操作,同样幂等:

```powershell
.\uninstall.ps1 -Tool cursor -Project D:\path\to\your-repo
.\uninstall.ps1 -Tool all
```

```bash
./uninstall.sh --tool opencode
./uninstall.sh --tool all
```

- 删掉本包拷入的 skill 文件夹(只删本包自带的 5 个名字,不动目标目录里的其它 skill)。
- 移除 `AGENTS.md` / `CLAUDE.md` 里的脊柱标记块,保留文件其余内容。
- `-Project` 给定时删掉 `<repo>\.cursor\rules\workflow-gate.mdc`。
- `opencode.json` **不会**被删(可能已被你修改)。
- 已不存在的项直接跳过,不报错。

## 验证已生效

- Cursor 项目脊柱:`<repo>\.cursor\rules\workflow-gate.mdc` 存在且首部 `alwaysApply: true`;新开一轮,agent 应在开头 announce 本轮 A/B/C/D 路径。
- 按需 skill:新开一轮发「按 `code-review` 走,分层审查这段 diff」,应复述 7 层审查 + no-false-negative 复验。
- 模型路由:发「说明你读到的 build/review 模型路由与并行/串行规则」,应复述 implementer 用强模型 / reviewer 换家族 / 并行需真正独立。
