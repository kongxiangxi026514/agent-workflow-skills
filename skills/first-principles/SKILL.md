---
name: first-principles
description: First-principles analysis for hard, novel, or ambiguous design problems. Use when the approach is non-obvious, requirements/constraints are tangled, or before committing to an architecture. Decompose to irreducible elements and derive a solution from zero. Not for routine changes.
---

# First-Principles Analysis

**何时用 / 何时跳过**:用于真正难 / 新 / 模糊的问题(方案非显然、需求约束纠缠、架构定稿前,通常 path C);日常改动(path A/B)直接跳过,别仪式化。

把问题拆到不可再分,再从零推导 —— 而不是照搬既有代码类比。四步:

1. **核心需求与约束** — 列出核心需求 + 硬约束(系统架构、合规 / 安全、性能预算、数据 / 契约不变量),明确区分 MUST vs nice-to-have。
2. **拆解为不可再分要素** — 把问题拆到不可再分的粒度(如请求链路各阶段、CPU / IO / 锁 / 网络、数据流、失败模式),不允许复合含糊的整块。
3. **从零推导方案 + 标注不确定假设** — 从不可再分要素自底向上推导,而非类比既有实现;每个不确定点显式标 `假设: … (待验证)`。
4. **优先级建议** — 按 影响 × 确定性 × 成本 排序,指出先做什么、可延后什么。

## 收尾自检

回答两个元认知问题:(1) 你最没把握的是什么?(2) 最大的遗漏 / 我没意识到什么?
