# Phase 4 FULL 附录（`MACHINE_GATE` 启用时读，判定见 config）

## 机器账本
- 机器 required 始终取该 run 冻结范围，不因进入某片而缩小。
- 复用实现前已 `compile-manifest` + `init` 的账本（冻结 testcase hash、场景矩阵、`applicability` 三维判定、release_unit；机器挑战要求先开账，见 delivery-slices），不在每片测试时重新 init。
- 每条测试当场 `record-run` + `attach-evidence`（脚本测试优先 `record-run --exec`）；时间用 `record-timing` 入账。
- 测完 `finalize --check-only` 输出 `READY_FOR_AUDIT` 才进收尾。命令与语义：`gate/PROTOCOL.md`、`references/evidence-audit-lifecycle.md`。
- 临时受阻保持 NOT_RUN，不要记机器 blocked（`BLOCKED_SEMANTICS`，RULES R9）。
- 完成记录走机器账本全流程，替代"无机器 receipt"口径。

## testcase 收尾额外
- 实际结果不许回填进被冻结的 oracle 文件（会触发 `FROZEN_ORACLE_CHANGED`，设计如此非误报）；确需改期望走 `behavior_changes`（phase-4 ⑤2）。
- 状态一致性机检：`declare-status` 五处口径对账，`STATUS_CONFLICT` 即修文档。
- 改动后 `re-attest`；末尾独立 full-audit（`{AUDITOR_ENGINE}` 声明 `MODE: full-audit`，全链闭环核查后 `audit` 入账；整改循环见 `references/evidence-audit-lifecycle.md` §3）。
- 测试义务 Gate 校验码：`AC_COVERAGE_MISSING` / `ORPHAN_REQUIRED_SCENARIO` / `UNJUSTIFIED_TEST_SCOPE` / `OBLIGATION_NOT_SATISFIED`（目前 `scripts/plan_test_gate.py` 只实现第一个）。

## 出口
- 默认出口全部条件 + `finalize --check-only` 输出 `READY_FOR_AUDIT` + full-audit PASS 已入账 → 当前片进入交付 DoD；有后续片做片终点核对回 phase-2，整体完成另核全部原始 AC。
