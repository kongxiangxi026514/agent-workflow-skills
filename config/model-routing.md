# 模型路由(单点配置 / single source of truth)

本文件是**唯一**需要改的地方,用来定义"哪个角色用哪个模型"。改这里,workflow 脊柱与各工具的模型路由随之生效。

## 角色 → 模型

| 角色 | 职责 | Cursor slug |
| --- | --- | --- |
| implementer | 实现 / 重构 / 调试 | `claude-opus-4-8-thinking-xhigh`(难任务升级 → `claude-opus-4-8-thinking-max`) |
| reviewer | 审查 / 验证 | `gpt-5.5-extra-high` |

## 硬规则

- **reviewer 必须与 implementer 属于不同模型家族**,规避同模型自我验证的盲区(cross-model verification)。
- 非平凡改动:implementer 先实现 → reviewer 跨模型审查 → 主代理独立复验;契约级(D-risk)改动必须走完这三步,不接受 implementer 自我批准作为最终结论。

## 动态换模型(改这里 = 单点)

- **Cursor**:改本文件的"角色 → 模型"表,并同步 `rules/workflow-gate.mdc` 里 `## Model routing (dynamic single point)` 段的 slug。派发子代理时,build 任务传 implementer 模型,review 任务传 reviewer 模型。
- **OpenCode**:改 `opencode/opencode.json` 的 `agent.build.model` / `agent.review.model`。真实可用 id 用 `opencode models` 查(例:build 用 GLM 5.2、review 用 Kimi K2.6 —— 不同家族)。

## 成本策略

质量优先、成本次要但**主动管理**:机械活(格式化 / 批量改名 / 简单迁移)用够用的便宜快模型,设计 / 审查 / 验证等高价值环节用强模型;控制子代理数量与并行扇出,避免无意义的重复调研与重跑。
