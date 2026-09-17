# Phase 3 — FULL / `MACHINE_GATE` 附加步骤

只在 FULL 或 `MACHINE_GATE` 启用时读；与 `phase-3-execute.md` 同步执行。

## 开场
- 体量检查用 `{GATE_SCRIPT} check-release-unit` 机检，并 `phase-start` 入账（超限处理同 phase-3 开场 1）。

## A. 执行
- FULL 路径已冻结的 black-box testcase，执行者**无权删除、反转、放宽**；失败只能改实现，或上报"疑似行为变更"走用户批准（判据正文 RULES R3）。

## A2. 计划失效即回炉
- A2 事件除写 `a2-events.md` 外，另用 `{GATE_SCRIPT} record-plan-defect` 入账，并 `check-plan-stability` 机检。
