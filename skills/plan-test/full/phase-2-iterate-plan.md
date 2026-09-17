# Phase 2 — FULL 细则（`MACHINE_GATE` 启用时读）

LEAN 主流程见 `../phase-2-iterate-plan.md`；挑战角色边界与 schema 见 `../references/challenge-orchestration.md`。

## 记账原则

- 用 gate CLI 全程入账；收敛由 gate 从 finding ledger 推导，reviewer 自报 PASS 没有 authority。
- 开始前已有 `acceptance.md` 与同目录 `assurance-contract.json`。已冻结的 contract 变化仍走原批准机制。
- 启动循环时冻结 contract、scope hash、threat-model hash 和 plan baseline。

## 启动与轮次闸

```bash
loop_id=$(python3 "${CLAUDE_PLUGIN_ROOT}/skills/plan-test/scripts/plan_test_gate.py" start-challenge-loop \
  --run-dir <run-dir> --loop-type plan-iteration --orchestration clustered \
  --target-file <plan.md> --assurance-contract <assurance-contract.json> \
  --baseline-hash $(sha256sum <plan.md> | cut -d' ' -f1))
```

`--orchestration clustered` 启用新流程；默认 `legacy` 只用于兼容旧 ledger。以下 `GATE` = 同一 `python3` + 脚本路径。

每轮挑战前：`GATE check-loop-limit --run-dir <run-dir> --loop-id $loop_id`
- exit 0：允许进入下一轮；
- exit 1：按输出状态完成 specialist、synthesis、closure 或控制动作；不得跳过状态直接推进。

## 各阶段入账

1. **Primary**：把唯一 JSON 输出中的 `round` 与 `clusters` 原样拆成两个文件，先后入账；`record-challenge-clusters` 紧接 primary round 1，记录完整 cluster 集：

```bash
GATE record-challenge-round --run-dir <run-dir> --loop-id $loop_id --round 1 \
  --plan-hash $(sha256sum <plan.md> | cut -d' ' -f1) --findings primary-round.json
GATE record-challenge-clusters --run-dir <run-dir> --loop-id $loop_id --input primary-clusters.json
```

Gate 校验 coverage、finding ID、AC/assurance binding、parent finding、plan/contract hash，拒绝漏聚类的范围内 P0/P1。

2. **Specialist**：逐 required cluster 完成后立即记 `completed`；只有用户批准跳过时才记 `waived`：

```bash
GATE record-specialist-challenge --run-dir <run-dir> --loop-id $loop_id \
  --cluster-id <cluster-id> --status completed --output specialist-<cluster-id>.json
GATE record-specialist-challenge --run-dir <run-dir> --loop-id $loop_id --cluster-id <cluster-id> \
  --status waived --waiver-reason "<reason>" --approval-hash <64-char-message-sha256>
```

3. **Synthesis**：`GATE record-challenge-synthesis --run-dir <run-dir> --loop-id $loop_id --input challenge-synthesis.json`（记录 cluster 输入集合、canonical finding 决策与后续动作）。
4. **Closure**：同 `record-challenge-round`，round 用 `$N`、findings 用 `closure-round-$N.json`，另加 `--based-on-plan-hash <上一轮-plan-hash>`；改 `consolidated` 需已记录对应 control。

## clustered 挑战的 `contradiction_role`

- synthesis 里可把次要且已闭环的 canonical finding 标 `contradiction_role: secondary`，closure 轮只须逐 ID 复核其余 finding。
- gate 按该 finding 全部历史推导地位：没绑 AC、碰到 `primary_contradiction.acceptance_ids`、任一轮是 P0、仍 open、曾是 scope-change-proposal 的，标了 secondary 也必须复核；不标 = 全部复核。
- 字段与模板：`print-schema --target synthesis`。

## 控制状态

- `CONTINUE`：修订 plan 后进入下一轮；
- `CONVERGED`：无 open in-scope P0/P1，核对授权；需要用户决定时进入合并 review；
- `SPECIALIST_CHALLENGE_REQUIRED`：完成所有 required cluster 的专项挑战；
- `SYNTHESIS_REQUIRED`：完成并记录统一 synthesis；
- `CLOSURE_REVIEW_REQUIRED`：修订 plan 后执行统一 closure diff review；
- `SCOPE_AUDIT_REQUIRED` / `USER_REVIEW_REQUIRED` / `BLOCKED`：3/5/8 轮出口（RULES R9）——先审计范围/根因 / 向用户报告原因 / 当前 loop 阻断；
- `ARCHITECTURE_RESET_REQUIRED`：连续两轮 patch-induced P0 或 scope audit 判定结构重置；
- `USER_SCOPE_APPROVAL_REQUIRED`：需要改变 profile/scope/trusted boundary。

控制动作必须入账并附证据：

```bash
GATE record-challenge-control --run-dir <run-dir> --loop-id $loop_id \
  --action scope-audit --outcome <continue|architecture-reset|scope-change> --evidence "<审计证据>"
```

- 用户批准 scope change：`--action scope-change-approved --approval-hash <消息 SHA-256>`；acceptance/contract 变化同时给 `--acceptance <新文件>` / `--assurance-contract <新文件>`。
- Gate 每轮复验两者 hash；未经批准的静默改写直接拒绝。
- Architecture reset 留在同一 loop，随后做 consolidated review，不得重开 loop 规避轮次。

## 收敛推导

Gate 只在以下结构条件同时成立时允许 closure 后推导 `CONVERGED`：primary coverage 完整；所有 primary 范围内 P0/P1 已聚类；required specialist 全部完成或有用户批准的 waiver；synthesis 覆盖全部 required cluster；closure 后没有 open in-scope P0/P1；acceptance/contract hash 未静默变化。Required spike 是否真实完成仍按原始证据审查，不能因 gate 结构状态而省略。机器语义以 `gate/PROTOCOL.md` 与 CLI `--help` 为准。

## 行为契约入账

行为契约与用户批准另写进 gate 账本：原始用户消息 hash、行为契约、批准事件（init manifest 的 `behavior_contract` / `source_request`，见 `gate/PROTOCOL.md`）。

## oracle 冻结

- 定稿后、实现前冻结 black-box testcase 逐文件 hash（init manifest `testcase_files` → `testcase_lock`）；冻结语义与唯一例外（`behavior_changes` 批准 artifact）在 RULES R3（`ORACLE_FREEZE`），"看起来只是重写文案"不自动放行。
- repo 内部 unit/integration test 的 mutation report 只能作审计信号，不能替代冻结的 black-box oracle，也不能单独证明行为变更获授权。
