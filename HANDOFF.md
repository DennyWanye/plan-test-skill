# Handoff：plan-test 机器门禁——已完成两轮实施，剩余 1D-delta 与后续 slice

> 日期：2026-07-27
> 状态：GATE 核心已上线；READY FOR 1D-DELTA（需 F:\ 可达机器）与 Slice 2A/2B/3A–3C 规划
> 目标仓库：`plan-test-skill`（GitHub: DennyWanye/plan-test-skill，main）
> 本文生成时 HEAD：`f8b1e77`（其前依次为 `3a3f7d0` 规划、`75ce2b4` 门禁核心）
> Windows 机器上的 junction 路径：`C:\Users\Administrator\.codex\skill-repos\plan-test-skill`
> 本文用途：直接交给下一位代理继续；不是可跳过 review 直接实现全部后续 slice 的授权

## 0. 一句话现状

plan-test 已从"Markdown 规则 + 代理自觉"升级为**机器可执行的门禁协议**：唯一状态账本
（`plan-test-run.json`）+ deterministic validator + gate receipt + timing 一等证据。
手写 `100% COMPLETE / SHIP` 已失效——交付判定只认 canonical finalize 的 exit code 与
receipt。两份此前的 handoff（质量复盘版 + OPTIMIZATION 版）的 P0 与 Slice 1A–1D 核心
均已落地并有 57 个自测用例作证。

## 1. 开工前必须完整阅读

以 target repo 为根：

1. `skills/plan-test/gate/PROTOCOL.md` —— 门禁协议 normative 契约（run-dir 布局、
   canonical command、状态机、20 类有序诊断码、11 条硬规则、交付措辞模板）
2. `skills/plan-test/gate/ROADMAP.md` —— 两轮已完成清单 + 未完成清单（唯一进度 authority）
3. `plans/2026-07-27-plan-test-gate-slice-1a/`（acceptance.md / plan.md /
   fixture-contract.md / evidence/challenger.md）—— 第二轮的技术 plan 与两轮 challenger 审计
4. `skills/plan-test/schemas/plan-test-run.schema.json` —— 账本 schema 1.1.0
5. `skills/plan-test/scripts/plan_test_gate.py` 与 `scripts/test_plan_test_gate.py`
6. 三个入口 skill：`skills/plan-test/SKILL.md`、`skills/plan-task/SKILL.md`、
   `skills/plan-bs/SKILL.md`，以及 `skills/plan-test/config.md`"机器门禁"节
7. 历史背景（在 DeskPet 侧，只作证据源）：
   `F:\projects\deskpet\plans\2026-07-27-plan-test-quality-retrospective\HANDOFF.md` 与
   `TIMING-AUDIT.md`

## 2. 当前基线（截至 f8b1e77，不要当成你开工时的事实）

### 已存在并自测通过

- **canonical CLI**（`skills/plan-test/scripts/plan_test_gate.py`，纯 stdlib）：
  `init / record-run / attach-evidence / declare-status / set-delivery /
  record-timing / checkpoint / audit / finalize [--check-only] / render / invalidate`
- **唯一账本**：只存 fact；required 场景由 init 自动建为 NOT_RUN；所有状态由 validator
  重算；文件锁 + 原子写 + revision CAS（冲突返回 `REVISION_CONFLICT`）
- **20 类有序诊断码**（PROTOCOL §4；输出幂等，advisory 级 `TIMING_GAP` 不拦截）
- **gate receipt**：绑定 ledger/证据/auditor/HEAD/dirty 指纹 digest；幂等 finalize；
  audit 后任一 fact 或 commit 变化 → `AUDITOR_INPUT_STALE` / `RECEIPT_STALE`；
  dirty 指纹排除 run-dir 自身且排除规则进 digest
- **冻结 oracle**：testcase 逐文件 hash 入账，byte 变化默认 `FROZEN_ORACLE_CHANGED`，
  反转/放宽须绑定用户批准的 `behavior_change_id`
- **timing contract（schema 1.1.0）**：`record-timing --exec`（monotonic 实测，调用者
  不可覆写）/ declared 申报（强制 `measured:false` 单列曝光）；`checkpoint`；render
  按七类 activity_class 分解耗时
- **静态 fixture**：`skills/plan-test/fixtures/gate/pass-minimal/`（正式 finalize →
  SHIPPABLE + receipt）与 `fail-companion-conflict/`（check-only → 15 条有序 DIAG，
  前三类 = REQUIRED_SCENARIO_NOT_RUN → STATUS_CONFLICT →
  DELIVERY_VERDICT_CONTRADICTS_LEDGER）
- **流程接线**：phase-2 行为契约/oracle 冻结；phase-3 执行子代理无权动 frozen oracle；
  phase-4 gate init + 当场入账 + 出口 `finalize --check-only`；phase-5 末尾 full-audit
  入账；phase-final-dod 机器门 + receipt 交付措辞模板；plan-task 最终判定只认 canonical
  command
- **自测**：`python3 skills/plan-test/scripts/test_plan_test_gate.py` → 57 用例，
  含 Companion 三冲突 dogfood（合成数据）与双 fixture 回放

### 已知如实标注的缺口（不是隐藏问题）

- Companion fixture 的 `provenance.json` 三个 `source_sha256` 均为 **null**——来源文件
  在 F:\（DeskPet），macOS 侧不可达；回放时强制输出 `PROVENANCE: UNVERIFIED`
- Windows 路径归一化只有纯逻辑设计，未在 Windows 真机跑过自测
- `TIMING_GAP` 为 advisory 级；升级为拦截需真实 gap 分布数据 + 用户拍板

## 3. 开工时必做的仓库校验（照抄两份前 handoff 的纪律）

写入任何文件前，在 target repo 执行：

```bash
git rev-parse HEAD
git branch --show-current
git status --short
```

- HEAD ≠ `f8b1e77`：先看新提交、更新你计划里的 baseline，不能照抄本文快照；
- worktree 不 clean：保护未知改动，确认安全边界前停止写入并报告用户；
- Windows 机器上三个 skill 是 junction 指向本仓库——改仓库即改生效 skill，
  不要去改 `C:\Users\Administrator\.codex\skills\<name>` 的复制品；
- Windows PowerShell 里 git 可能不在 PATH：
  `C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\git\cmd\git.exe`
- **未经用户明确要求不 push**（本文生成前的推送均经用户逐次确认）。

## 4. 已确认、不要重新争论的结论

1. 问题根因不是"测试太少"，是错误 acceptance oracle、被反转的测试、终点式 E2E、
   Markdown-only gate、超大 release unit——机器门禁是对症解，已实现。
2. Markdown 是人读视图，不是状态 authority；不要再造第二份可写状态文件。
3. retry/重放/改写/continuation 不算 distinct；engine 终态 ≠ 业务成功；derived 报告
   不能单独作证；两份互引汇总构成证据环必须拒绝。
4. 真人测试耗时采用"申报 + 强制 measured:false 曝光"而非强制计时命令（用户已拍板）；
   TIMING_GAP 先 advisory（用户已拍板）。
5. `fixture_only` run 的 receipt/report 永远标 FIXTURE-ONLY，不可作真实交付证据。
6. 不能为让历史 Companion 计划变绿而修改历史证据；provenance hash 采集前只能标
   `PROVENANCE: UNVERIFIED`。

## 5. Canonical 用法速查

```bash
# 自测（改动 gate 后必跑；57 用例须全绿）
python3 skills/plan-test/scripts/test_plan_test_gate.py

# 真实 run 的生命周期
python3 skills/plan-test/scripts/plan_test_gate.py init            --run-dir <plan>/verification/<run-id> --manifest manifest.json
python3 skills/plan-test/scripts/plan_test_gate.py record-run      --run-dir D --scenario S-1 --kind root --result pass ...
python3 skills/plan-test/scripts/plan_test_gate.py attach-evidence --run-dir D --path artifacts/x.png --kind primary --ui-action
python3 skills/plan-test/scripts/plan_test_gate.py record-timing   --run-dir D --phase phase-4 --activity-class automated_test --exec -- <cmd>
python3 skills/plan-test/scripts/plan_test_gate.py checkpoint      --run-dir D --slice <s> --note "..."
python3 skills/plan-test/scripts/plan_test_gate.py finalize        --run-dir D --check-only   # READY_FOR_AUDIT 才能进审计
python3 skills/plan-test/scripts/plan_test_gate.py audit           --run-dir D --verdict PASS --input auditor-input.json --output auditor-output.json
python3 skills/plan-test/scripts/plan_test_gate.py finalize        --run-dir D               # exit 0 + GATE RECEIPT 才算完成
python3 skills/plan-test/scripts/plan_test_gate.py render          --run-dir D
```

exit code：0 通过 / 1 门禁 FAIL / 2 用法错误。交付措辞只能用 phase-final-dod 的
receipt 模板；没有有效 receipt 的 SHIP = `DELIVERY_VERDICT_CONTRADICTS_LEDGER`。

## 6. 下一步工作（按优先级；每项独立小 slice，不要合并成超大 plan）

### 6.1 【1D-delta，需 F:\ 可达的 Windows 机器】溯源回填 + Windows 验证

1. 对三份历史文件各算 sha256，回填
   `skills/plan-test/fixtures/gate/fail-companion-conflict/provenance.json`
   （同时填 `captured_at`（RFC 3339 UTC）与 `captured_on`）：
   - `F:\projects\deskpet\testcase\2026-07-24-human-anchored-companion-growth\manual-test.md`
   - `F:\projects\deskpet\plans\2026-07-24-human-anchored-companion-growth\evidence\manual-results.md`
   - `F:\projects\deskpet\plans\2026-07-24-human-anchored-companion-growth\evidence\task16-delivery-audit.md`
   PowerShell：`Get-FileHash -Algorithm SHA256 <path>`。
   回填后核对 normalized representation（steps.jsonl 的 declared_statuses 等）与原文
   状态行一一对应；对不上 → 修 fixture 的 normalized 数据（**不是**修历史文件）。
2. 在 Windows 真机跑 `python skills\plan-test\scripts\test_plan_test_gate.py`，
   57 用例全绿；路径相关失败按 plan.md §1.9 的"相对 run-dir、正斜杠归一"原则修。
3. （可选）收集首批真实 run 的 TIMING_GAP 分布，交用户决定是否升级为拦截。

### 6.2 【Slice 2A】行为契约批准 artifact 自动采集

现状：`behavior_contract`/`behavior_changes` 有 schema 与校验，但批准事件
（用户消息 event ID/hash）靠手工填 manifest。目标：定义批准 artifact 的采集与绑定流程。
先写小型 plan（含 acceptance + challenger 审计）再实现。

### 6.3 【Slice 2B】internal test mutation report

repo 内部 unit/integration 测试被删/放宽/反转的 diff 审计信号（只作报告，不替代
frozen black-box oracle）。

### 6.4 【Slice 3A】runtime adapter protocol

project attest command → components/source/process/artifact digest/health identity；
现只有 `adapter_status=UNKNOWN → BLOCKED` 语义。需正反 fixture。

### 6.5 【Slice 3B/3C，DeskPet 仓库侧】project policy 与 lane closure

`F:\projects\deskpet\.plan-test\policy.json`、core-user-journeys manifest、
change-impact → required lanes/edges/sample budget、R-01～R-14 永久回归矩阵
（R-12 blocked：需产品先定义 autonomy policy）。**不在 skill 仓库做。**

## 7. 明确禁止

- 不要再增加"请认真检查"式 prompt 然后宣称问题解决——已知违规必须进 validator；
- 不要允许任何人手写 PASS/状态字段（账本只收 fact，状态一律重算）；
- 不要绕过 `finalize` 的 exit code 另立交付判定；
- 不要为让历史变绿修改历史证据或 fixture 期望；
- 不要把 declared timing 混入 measured 聚合，或去掉 `measured:false` 标记；
- 不要在 Slice 2/3 之前修改 DeskPet 产品代码；
- 不要把 6.1–6.5 打包成一个超大 plan；每个 slice 先小 plan + challenger 审计 +
  用户 review，再实现；
- 不要未经用户要求 push。

## 8. 验证你接手后没有弄坏东西

```bash
python3 skills/plan-test/scripts/test_plan_test_gate.py   # 57 用例全绿
```

两份静态 fixture 是行为契约的冻结快照：`pass-minimal` 必须走到
`STATE: SHIPPABLE` + receipt；`fail-companion-conflict` 必须输出与
`expected-diagnostics.txt` 逐字节相同的 15 条 DIAG（前三类顺序不可变）。
任何 gate 改动使这两份 fixture 变化，都必须先审文案再更新期望文件，并在 commit
message 说明理由。

## 9. 最终判断（延续两份前 handoff 的结论）

> 流程要求已经从"给代理看的文章"变成了"代理无法绕过的执行协议"。

剩余工作不再是造门，而是：把门接到真实历史证据（6.1）、扩展到行为批准与运行物身份
（6.2–6.4）、落到具体项目的旅程与 lane（6.5）。每一步都保持小 slice、先 plan 后实现、
机器 gate 收口。
