# 安装 / 幂等性 / 卸载

本仓库的 v3 安装包由 `policy-v3/registry.json`、唯一 fragments 与 renderer 生成；安装/卸载全部走脚本,**不再手动拷贝任何文件**。模型 ID 仍只放在目标机器的 binding。

## Profile 行为

- Cursor 默认 `lean`，OpenCode 与 Claude 默认 `balanced`；可用 PowerShell `-Profile lean|balanced` 或 bash `--profile lean|balanced` 覆盖。
- `lean` 与 `balanced` 只改变 R0/R1 升级阈值和 L0/capsule budget，绝不维护两套 policy 正文。
- R2 Strict 触发、`P01,P04` 加载与独立审查在两个 profile 中相同。
- 生成的 adapter/skills 写入 fragment ID/hash、registry hash、profile 与 ownership manifest。下一次 install 会在任何写入前检查 drift，手改受管生成物会 fail-loud。

## 组成

| 路径 | 类型 | 角色 |
| --- | --- | --- |
| `rules/workflow-gate.mdc` | **强制规则** | 脊柱:每轮 A/B/C/D 门控 + 主/子编排 + 全流程 + 质量/架构契约 + 模型路由 + 元认知检查点 |
| `policy-v3/generated/skills/` | 6 个按需 skills | `workflow-lifecycle`、`first-principles`、`code-review`、`research-routing`、`parallel-dispatch`、`memory-gate` |
| `config/model-routing.jsonc` | 模板 | build/reason/review 的无默认 provider binding 格式 |
| OpenCode `agent.build/reason/review` | 受管 JSON/JSONC 字段 | 在显式 migration opt-in 后保存角色 model、mode、permission 与 description |

## 脚本参数

| 平台 | 脚本 | 参数 |
| --- | --- | --- |
| Windows / PowerShell | `install.ps1` / `uninstall.ps1` | `-Tool ...`;Cursor/all 必须给 `-Project`;OpenCode config 可用 `-OpenCodeConfigDir` 覆盖 |
| macOS / Linux / bash | `install.sh` / `uninstall.sh` | `--tool ...`;Cursor/all 必须给 `--project`;OpenCode config 可用 `--opencode-config-dir` 覆盖 |

脚本以自身所在目录为 REPO_ROOT,可从任意工作目录调用。

## Cursor checkout 与本机 binding

`-Project` / `--project` 是一个明确的 Cursor 项目 checkout，而不是本安装包的 source checkout。每个独立项目或 worktree 都要单独执行 Cursor 安装，规则和 binding 才会写到该 checkout。

Cursor binding 位于 `<project>/.cursor/agent-workflow-skills/model-routing.jsonc`（Windows 使用等价的反斜杠路径）。这是机器本地配置，勿提交；需要忽略时使用该 checkout 的 `.git/info/exclude`，不要为了安装器改写共享的用户配置。

## Cursor 安装(逐步)

1. 装 6 个按需 skill(全局)并把强制脊柱写进某个项目:

   ```powershell
   .\install.ps1 -Tool cursor -Project D:\path\to\your-repo -BuildModel cursor-build-slug -ReviewModel cursor-review-slug
   # 默认 lean；需要时显式改为 balanced
   .\install.ps1 -Tool cursor -Project D:\path\to\your-repo -Profile balanced -BuildModel cursor-build-slug -ReviewModel cursor-review-slug
   ```

   - `policy-v3/generated/skills/` → `%USERPROFILE%\.cursor\skills\<skill>\SKILL.md`(覆盖式,自动建目录),Cursor 按 `description` 自动发现调用。
   - `rules/workflow-gate.mdc` 与渲染后的 model adapter → `<repo>\.cursor\rules\`;binding → `<repo>\.cursor\agent-workflow-skills\model-routing.jsonc`。

2. 不带 `-Project` 会在任何写入前失败,避免只装 skill 却遗漏强制脊柱。Cursor 没有文件式跨项目全局规则;对每个项目执行脚本即可全自动安装。

## 自动放置清单

| 工具 | 仓库来源 | 自动目标 |
| --- | --- | --- |
| Cursor | `policy-v3/generated/skills/`（6 个） | `%USERPROFILE%\.cursor\skills\<skill>\` / `~/.cursor/skills/<skill>/` |
| Cursor(带 Project) | `rules/workflow-gate.mdc` | `<project>/.cursor/rules/workflow-gate.mdc` |
| Cursor(带 Project) | binding + resolver + adapter template | `<project>/.cursor/agent-workflow-skills/{model-routing.jsonc,dispatch_resolver.py}` + `.cursor/rules/model-routing.mdc` |
| OpenCode | `policy-v3/generated/skills/`（6 个） | `~/.config/opencode/skills/<skill>/` |
| OpenCode | `rules/workflow-gate.mdc` | `~/.config/opencode/AGENTS.md` 标记块 |
| OpenCode | binding + resolver + ownership state | `~/.config/opencode/agent-workflow-skills/{model-routing.jsonc,dispatch_resolver.py,install-state.json}` |
| OpenCode（显式迁移） | 选定 `opencode.json` / `opencode.jsonc` | `agent.{build,reason,review}`；原字节 backup 和 SHA-256 audit 写入 `agent-workflow-skills/` |
| Claude | `policy-v3/generated/{skills,adapters/claude}` | `~/.claude/skills/<skill>/` + `~/.claude/CLAUDE.md` 标记块 + `~/.claude/agent-workflow-skills/install-state.json` |

脚本自动完成全部复制和注入,无需 agent 或用户再手工移动文件。OpenCode 运行中的会话需在安装后重启。

## OpenCode 安装(逐步)

```bash
./install.sh --tool opencode \
  --migrate-opencode-model-config \
  --build-model provider/build-id --review-model other/review-id
# 默认 balanced；需要时显式改为 lean
./install.sh --tool opencode --profile lean \
  --migrate-opencode-model-config \
  --build-model provider/build-id --review-model other/review-id
```

- `policy-v3/generated/skills/` → `~/.config/opencode/skills/<skill>/SKILL.md`。
- 脊柱正文(已剥离 `.mdc` frontmatter)幂等注入 `~/.config/opencode/AGENTS.md`(全局始终加载),用 `<!-- BEGIN agent-workflow-skills spine -->` / `<!-- END agent-workflow-skills spine -->` 标记块包裹。
- 首次安装用 CLI 明确给 `build` 与 `review`;`reason` 省略即以 JSONC `null` 复用 build。角色配置写入 OpenCode 主配置 `agent` 映射，而不是 bundle Markdown role agent；未命名的 Markdown agent 继承会话模型。之后编辑 `<config-dir>/agent-workflow-skills/model-routing.jsonc` 并带相同 migration flag 重跑，三个角色的 JSON 字段会刷新；review 保持 `edit: deny`。
- 默认 config dir 是字面 `~/.config/opencode`;覆盖参数同时适用于 install/uninstall。默认不改主配置并 fail-loud；`--migrate-opencode-model-config` / `-MigrateOpenCodeModelConfig` 是唯一 opt-in。`--opencode-model-config` / `-OpenCodeModelConfig` 可选择 `opencode.json` 或 `opencode.jsonc`；未指定时只能使用唯一现存文件，无文件时创建 JSONC，双文件或损坏内容均拒绝且不改写。
- 迁移保留非模型 JSON 语义，将原字节备份到 `<config-dir>/agent-workflow-skills/migration-backups/`，并在 `opencode-model-migration.json` 记录前后 SHA-256 与 managed role fields。它会移走 `agents/{build,reason,review}.md` 脱离发现目录，并从其余 Markdown agent（例如 `github-helper`）剥离 `model:`。安装器只验证 review ID 不等于 build/effective-reason;provider 字符串不同不能证明模型家族不同。全部 UTF-8 无 BOM;先临时 staging/校验再替换目标,失败校验不改变既有 bundle 状态。完成后必须重启 OpenCode。

## 模型路由

`build` 处理实现/重构/调试/常规架构;`reason` 仅处理非显然跨系统权衡、不确定根因或契约级多步推理;`review` 独立验证。策略可移植,具体 ID 只在各目标 binding 中。

Cursor 与 OpenCode binding 完全独立。`all` 安装必须分别提供 `CursorBuild/Reason/ReviewModel` 与 `OpenCodeBuild/Reason/ReviewModel`（bash 使用对应的 `--cursor-*` / `--opencode-*`），通用参数会因存在跨平台误用风险而失败。每次原生派发前运行目标中的 `dispatch_resolver.py`;若平台提供模型列表则完整传入并验证,然后原样使用 resolver 返回的原生参数。派发后保留 receipt；看不到 `actual_model` 时 `cross_model` 只能是 `unverified`。

## Claude 安装(逐步)

```bash
./install.sh --tool claude
```

- 生成的 v3 skills → `~/.claude/skills/<skill>/SKILL.md`，不会复制 legacy `skills/`。
- 带 provenance/profile 的生成 v3 adapter 幂等注入 `~/.claude/CLAUDE.md`(同样的标记块方式)，默认 `balanced`。
- `~/.claude/agent-workflow-skills/install-state.json` 记录 adapter 与 skills 的 ownership/hash；刷新前会检测 drift，手改受管生成物 fail-loud。

## 幂等性(可重复运行)

- **ownership**:`install-state.json` 与 marker 标识本包资产;同名非本包 skill/agent/rule 失败且不覆盖,卸载也保留。
- **AGENTS.md / CLAUDE.md 脊柱注入**:用标记块定位。若标记块已存在则**原地替换**,否则追加;文件不存在则创建。因此重复运行只会保留**一个**脊柱块,不会累积。文件里标记块以外的内容原样保留。
- **OpenCode role map**:仅在明确 migration opt-in 时更新 `agent.build/reason/review`;其它 agent 字段保留。三角色 Markdown 文件移出 discovery，其余 Markdown role 的 `model:` 被剥离以继承会话模型。
- **opencode.json / opencode.jsonc**:默认零读取、零改写；迁移模式只选择一个安全路径，拒绝双文件、损坏 JSONC 或 reparse/symlink 路径，并留下逐字节 backup 与 SHA audit。

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
- 只删除 audit 证明仍由本包管理的 OpenCode `agent.build/reason/review` 字段；字段漂移时保留用户改动，且绝不恢复 Markdown `model:` 硬编码。
- `-Project` 给定时删掉 `<repo>\.cursor\rules\workflow-gate.mdc`。
- OpenCode 主配置不会被删除；仅在显式 migration 后由 uninstall 删除校验通过的受管角色字段。
- 已不存在的项直接跳过,不报错。

## 从 installer-v2 迁移

1. 不要复制/合并旧 AGENTS、rule 或 skill，也不要删除现有 `model-routing.jsonc` / ownership state。
2. 使用含 `policy-v3/generated/` 的版本，并显式传 `-MigrateOpenCodeModelConfig` / `--migrate-opencode-model-config`；先审阅自动选择的主配置，必要时用 `OpenCodeModelConfig` / `--opencode-model-config` 指定。migration audit 和 byte backup 是回滚检查证据，不要删除它们绕过冲突。
3. 记录默认 profile（Cursor `lean`、OpenCode `balanced`）；若需要统一行为，显式传 `Profile`，然后重启 OpenCode。
4. 若 drift 检查报错，先审阅受管生成物是否被手改；要回到受支持状态时运行对应 uninstall 后重装，禁止通过删除 state/marker 绕过检查。

## 验证已生效

- Cursor 项目 adapter:`<repo>\.cursor\rules\workflow-gate.mdc` 存在且首部 `alwaysApply: true`;新开一轮只执行短路由，普通 R0 不产生强制流程公告。
- 按需 skill:新开一轮发「按 `code-review` 走,分层审查这段 diff」,应复述 7 层审查 + no-false-negative 复验。
- 模型路由:应复述 build/reason/review 职责及本机/项目 binding。

仓库回归测试使用临时中文路径作为 `HOME` / `USERPROFILE`,覆盖 config 选择、JSONC 注释语义/byte backup/SHA audit、binding 刷新/null fallback、markdown sanitization、reparse 路径拒绝、failure injection rollback、drift/uninstall、UTF-8、重复安装/卸载及 config-dir override,不会访问真实用户目录。
