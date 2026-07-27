# plan-test 机器门禁协议（gate protocol）

> 来源：2026-07-27 plan-test/plan-task 完成质量复盘 handoff（DeskPet Companion 计划的错误 oracle、
> 冻结 testcase 与最终结论冲突、终点式 E2E、Markdown-only gate 四类逃逸）。
> 定位：Markdown 是给人读的视图，**不再是状态 authority**；唯一状态 authority 是结构化账本 +
> deterministic validator。qualitative auditor 负责发现未知问题；validator 负责阻止已知违规。

## 1. run 目录（固定布局）

每次 plan-task/plan-test 验证使用一个固定 run 目录：

```text
<plan-folder>/verification/<run-id>/
  plan-test-run.json       # 唯一状态账本（只存 fact；状态由 validator 重算）
  artifacts/               # 截图、原始日志、命令回执等 primary 证据
  auditor-input.json       # 独立审计的冻结输入
  auditor-output.json      # 独立审计原始输出
  gate-receipt.json        # finalize 成功后才存在
  report.md                # render 从 ledger + receipt 生成的人读视图
```

## 2. canonical command（唯一判定入口）

```bash
python skills/plan-test/scripts/plan_test_gate.py finalize --run-dir <run-dir>
```

- plan-task/plan-test 的最终交付判定**只接受本命令的 exit code 与结构化 stdout**，不接受代理手写结论。
- `finalize --check-only` 是审计前预检：检查除 auditor/receipt 外的全部输入与测试完整性，
  成功只输出 `READY_FOR_AUDIT`——预检不因"审计尚未执行"而永远无法进入审计阶段。
- 正式 `finalize`：额外要求 auditor PASS，重新校验全部 hash/HEAD/runtime 后生成
  `gate-receipt.json`（幂等：同输入复用同 receipt digest 与首次 finalized_at）。
- `render`：重新运行同一 validator、复验 receipt digest，失效时**不渲染 SHIPPABLE**。
- 没有有效 receipt 的手写 `SHIP / 100% COMPLETE` 一律视为
  `DELIVERY_VERDICT_CONTRADICTS_LEDGER`。

## 3. 状态机（validator 计算，不可手写）

```text
DRAFT → ACCEPTED → IMPLEMENTED → TESTED → VALIDATED → SHIPPABLE
```

- ACCEPTED：source_request + acceptance 已冻结（hash）。
- IMPLEMENTED：baseline HEAD/dirty 指纹已记录。
- TESTED：全部 required 场景重算为 PASS。
- VALIDATED：check-only 无诊断（auditor 除外）。
- SHIPPABLE：auditor PASS + 全部硬门通过 + receipt 生成。

## 4. 稳定诊断码（stable diagnostic codes）

| code | 触发条件 |
|---|---|
| `SCHEMA_INVALID` | 账本结构不合 schema |
| `REQUIRED_SCENARIO_NOT_RUN` | required 场景为 NOT_RUN/PARTIAL/BLOCKED/FAIL |
| `STATUS_CONFLICT` | 文档口径（declared）与账本重算结果冲突 |
| `DELIVERY_VERDICT_CONTRADICTS_LEDGER` | 手写 SHIP/COMPLETE 但 required 未全 PASS |
| `EVIDENCE_MISSING` | 证据文件不存在 / 依赖不存在 |
| `EVIDENCE_HASH_MISMATCH` | 证据文件被改动 |
| `EVIDENCE_DEPENDENCY_CYCLE` | 证据循环引用（互引的两个汇总不能构成独立证据） |
| `DERIVED_EVIDENCE_ONLY` | required 场景只有 derived report，无 primary 证据 |
| `UI_EVIDENCE_MISSING` | UI 场景判 PASS 但无真实 UI action 的 primary 证据 |
| `RUN_CREATION_UNVERIFIED` | expected_run_created 声明未被正/负向证据兑现 |
| `FROZEN_ORACLE_CHANGED` | 冻结 black-box testcase byte 级变化且无 behavior_change_id |
| `BEHAVIOR_APPROVAL_REQUIRED` | 行为变更缺少用户批准 artifact（exact old/new + 消息 hash + scope） |
| `TESTED_RUNTIME_MISMATCH` | tested HEAD/dirty 指纹与当前不一致，或 adapter UNKNOWN |
| `AUDITOR_MISSING` | full-audit 未执行或 verdict 非 PASS |
| `AUDITOR_INPUT_STALE` | audit 后账本 fact 又变化——旧 PASS 失效 |
| `RECEIPT_STALE` | receipt digest 与当前输入不符 / 已 invalidate / 缺失 |
| `RISK_CLOSURE_MISSING` | required lane 无通过的 root run |
| `STABILITY_SAMPLES_INSUFFICIENT` | 非确定性场景采样不足或 FLAKY |
| `RELEASE_UNIT_TOO_LARGE` | 交付体量超阈值，须拆 program plan + 垂直 slice |
| `REVISION_CONFLICT`（stderr） | 并发写 CAS 冲突——重读后重试，不静默覆盖 |
| `LEDGER_LOCKED`（stderr） | 文件锁被占用 |

## 5. 硬规则摘要

1. **required rows 由 init 自动创建为 NOT_RUN**；命令只记录事实（record-run /
   attach-evidence），状态由 validator 计算，调用者不能把 NOT_RUN 改成 PASS。
2. **retry / replay / 同意图改写 / continuation 不是 root run**——只有 root 计入场景状态。
3. **证据分级**：截图、原始日志、命令回执、DB 记录是 primary；auditor 报告、delivery
   汇总是 derived。derived 只辅助审计，不能单独满足 AC/testcase。
4. **engine 终态 ≠ 业务成功**：positive-value 场景的 root run 业务终态为空/insufficient/
   partial → 场景只能 PARTIAL。
5. **冻结 oracle**：实现前 init 冻结 black-box testcase 逐文件 hash；任何 byte 变化默认
   FAIL；唯一例外是绑定 exact old/new + 用户消息 hash + scope/expiry 的批准 artifact。
6. **audit 冻结 facts_digest**：审计后代码、配置、testcase 或结果有任何变化，旧 auditor
   PASS 与 receipt 自动失效（AUDITOR_INPUT_STALE / RECEIPT_STALE）。
7. **dirty 指纹排除 run-dir 自身**（否则写 receipt/report 会让 receipt 立即 stale）；
   排除规则本身进 digest。
8. **fixture_only**：跳过 git 校验的 run 永远标 FIXTURE-ONLY，receipt/report 不可作为
   真实交付证据。
9. **"100%" 只表示某个明确 scope 的 required gates 全绿**，不表示未来绝无缺陷。

## 6. 交付措辞（有效 receipt 才能填）

```text
REQUIRED GATES: PASS
TESTED HEAD: <sha>
TESTED SCOPE: <AC / slice>
FRESH LANE: PASS | NOT_REQUIRED(<risk/policy ref>)
HISTORY/UPGRADE LANE: PASS | NOT_REQUIRED(<risk/policy ref>)
TEMPORAL/FAULT LANE: PASS | NOT_REQUIRED(<risk/policy ref>)
EXPLORATORY LANE: PASS | NOT_REQUIRED(<risk/policy ref>)
KNOWN GAPS: 0 / 明确列表
GATE RECEIPT: <content_digest>
```

禁止再写无作用域的 `100% COMPLETE，DECISION: SHIP`。用户后续发现生产缺陷 →
`invalidate` 对应 receipt；修复、永久回归和受影响 lane 复测完成后才生成新 receipt。

## 7. 自测

```bash
python skills/plan-test/scripts/test_plan_test_gate.py
```

覆盖：状态矛盾 FAIL、required NOT_RUN、证据缺失/hash 不符、循环证据、frozen oracle
变异、audit 后 stale、receipt 幂等、Companion 历史三冲突 dogfood
（REQUIRED_SCENARIO_NOT_RUN + STATUS_CONFLICT + DELIVERY_VERDICT_CONTRADICTS_LEDGER）、
以及一条证据完整的 PASS 路径（防 gate 只会拒绝）。
CI/self-test 用同一 canonical finalize 路径重跑，不另写一套判断。
