# Workflow Skills Bundle — 安装 / 热插拔 / 卸载

把我的开发 workflow 固化成 5 个自包含、可热插拔的个人 skill。每个 skill 是一个独立文件夹,插上(拷进 skills 目录)即生效,拔掉(删文件夹)即卸载,互不依赖。

## 组成(5 个 skill)

| skill 文件夹 | 角色 | 何时触发 |
| --- | --- | --- |
| `workflow-gate/` | **脊柱**:每轮 A/B/C/D 路径门控 + 主/子代理编排 + 全流程 + 质量/架构契约 | 每个非平凡编码轮次开头 |
| `code-review/` | 分层 7 层审查 + no-false-negative 复验 + 瘦身/重构纪律 | review diff / PR / 合并前 |
| `research-routing/` | Context7 / Tavily / GitHub 调研路由 | 查文献/文档/三方库/源码 |
| `parallel-dispatch/` | 并行 vs 串行拆解 + 角色化模型路由 + 上下文封顶/熔断 | 派发子代理前 |
| `memory-gate/` | AGENTS.md 记忆更新 diff-review 双轨 gate | 任何 agent 想改长期记忆时 |

每个 `SKILL.md` **完全自包含**:不引用仓库里的 `sop.md §x`,脱离本仓库也能用,所以两台机器直接拷即可。

## 本机(Cursor,已安装)

已写入 `~/.cursor/skills/<skill>/SKILL.md`,重启/重载对话后 Cursor 即可按 description 自动发现并调用。

## 拷到另一台 Windows 的 OpenCode 机器

把这 5 个文件夹整体拷到该机器的全局 skills 目录(任选其一,OpenCode 均会发现):

- `%USERPROFILE%\.config\opencode\skills\<skill>\SKILL.md`(OpenCode 全局)
- 或 `%USERPROFILE%\.claude\skills\<skill>\SKILL.md`(兼容 Claude 约定)

`SKILL.md` 的 frontmatter 只有通用字段(`name` / `description`),OpenCode 会忽略未知字段,无需改写。

## 让脊柱“每轮强制触发”(可选,推荐)

skill 是 pull 型,不保证每轮触发。要拿到强制每轮 announce 路径:

- Cursor:把 `workflow-gate/SKILL.md` 的第 1-2 节粘到 Settings → Rules(User Rules)。
- OpenCode:把同样内容放进 `~/.config/opencode/AGENTS.md`(全局,始终加载)。

其余 4 个按需 skill 保持 pull 型即可,不必进 always-on。

## 卸载 / 热插拔

- 停用某个能力:删除对应文件夹(如 `del /s /q code-review\`)。
- 全部停用:删除这 5 个文件夹。
- 因为自包含且无交叉引用,单独增删任意一个都不影响其余。

## 验证已生效

新开一轮,发:「按 workflow-gate 走,先 announce 本轮路径,并说明你读到的模型路由(build/review)和并行/串行规则」。它应能复述 A/B/C/D 判断 + implement 用强模型 / review 换家族 + 并行需真正独立 —— 说明 skill 已被发现并加载。
