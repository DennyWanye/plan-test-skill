# Slice 1A（delta）fixture contract

> 本文件冻结两份 normalized fixture 的**格式、来源与 expected diagnostics**。
> 本 slice 不执行 finalize、不运行 importer、不声称 dogfood 已带真实溯源执行。
> 现状如实说明：`75ce2b4` 的自测里已有 Companion 三冲突用例，但其数据是**测试代码内
> 合成的**，未绑定历史来源文件 hash——本契约就是为补齐这一步而立。

## 1. 磁盘格式（两份 fixture 共用）

```text
skills/plan-test/fixtures/gate/<fixture-name>/
  manifest.json            # 可直接喂给 plan_test_gate.py init 的 manifest（fixture_only=true）
  steps.jsonl              # 逐行 CLI 步骤：{"cmd": "record-run", "args": {...}}，按序回放
  artifacts/               # 需要落盘的证据文件（内容固定，hash 可复算）
  expected-diagnostics.txt # 期望的有序 DIAG 行（逐字节比对 stdout 中 DIAG 部分）
  expected-state.txt       # 期望 STATE 行
  provenance.json          # 仅 legacy fixture 需要，见 §3
```

回放器（1B-delta 实现，自测的一部分）：读 steps.jsonl 依序调 canonical CLI。**终结
命令由 fixture 自身在 steps.jsonl 最后一行显式声明**（`finalize --check-only` 或正式
`finalize`），回放器不隐含追加；断言该终结命令 stdout 的 DIAG 序列与
expected-diagnostics.txt 逐字节相同、STATE 行与 expected-state.txt 相同。
**同一 fixture 重跑两次输出必须全等**（诊断排序契约见 plan.md §3）。
冻结比对只针对 `DIAG`（error）行与 STATE 行；`ADVISORY` 行（如 TIMING_GAP）包含运行时
实测值（分钟数随 --exec 实测时刻变化），**不入逐字节冻结比对**——advisory 本就不拦截，
其存在性由专门用例断言而非 fixture 期望文件。
状态可达性约束（防冻结出不可达期望）：`finalize --check-only` 模式下 state 封顶
`VALIDATED`（现实现 `compute_state()` 只在 full/render 模式给 SHIPPABLE）——因此
期望 `STATE: SHIPPABLE` 的 fixture **必须**以正式 `finalize` 终结。

## 2. 最小 PASS fixture：`pass-minimal/`

目的：证明 schema 能表达 required rows、primary evidence、auditor、runtime identity、
timing 与预期 receipt 输入。**本 slice 不执行 finalize**；1B-delta 落盘后由自测执行。

内容要求：

- manifest.json 含 SHIPPABLE 状态机所需的全部前置：`source_request_text`（或文件）、
  `acceptance_file`（fixture 内置的 acceptance 样例文件）、`fixture_only: true` 及
  `baseline.head`（合成值，fixture 模式不校验 git）——缺任一项 state 停在 DRAFT，
  期望不可达；
- 1 个 required UI 场景（`gate_type: positive-value`、`expected_run_created: true`）；
- 1 条 root run（含 business_terminal、session_id、run_id_under_test）；
- 1 份 primary 证据（`ui_action: true`，artifacts/ 下真实文件）；
- auditor-input/output + `audit --verdict PASS`；
- **timing 两条样例**（对应 acceptance AC-2）：
  - `measured: true`：由 `record-timing --exec` 包裹一条无害命令实测；
  - `measured: false`：declared 模式申报一段 manual_e2e；
- steps.jsonl 以**正式 `finalize`** 终结（fixture_only=true，receipt/report 恒标
  FIXTURE-ONLY，不可作真实交付证据）；expected-state.txt = `STATE: SHIPPABLE`，
  expected-diagnostics.txt 为空。fail fixture（§3）则以 `finalize --check-only` 终结。

## 3. Companion normalized FAIL fixture：`fail-companion-conflict/`

目的：机器 gate 必须对 2026-07-24 Companion 计划的真实矛盾给出**三个具体错误码**，
不允许退化成模糊的 `MANIFEST_MISSING`。

### 3.1 provenance.json（溯源契约——本 slice 冻结格式，hash 归 1D-delta 采集）

```jsonc
{
  "sources": [
    {
      "source_path": "F:\\projects\\deskpet\\testcase\\2026-07-24-human-anchored-companion-growth\\manual-test.md",
      "source_sha256": null,          // ← 1D-delta 在可达 F:\ 的机器采集；采集前必须为 null，不许伪造
      "captured_at": null,            // RFC 3339 UTC
      "captured_on": null,            // 机器标识
      "role": "frozen testcase（PARTIAL/BLOCKED/NOT RUN 口径）"
    },
    {
      "source_path": "F:\\projects\\deskpet\\plans\\2026-07-24-human-anchored-companion-growth\\evidence\\manual-results.md",
      "source_sha256": null, "captured_at": null, "captured_on": null,
      "role": "RESULTS（6/6 PASS 口径；与 delivery-audit 互引）"
    },
    {
      "source_path": "F:\\projects\\deskpet\\plans\\2026-07-24-human-anchored-companion-growth\\evidence\\task16-delivery-audit.md",
      "source_sha256": null, "captured_at": null, "captured_on": null,
      "role": "交付审计（100% COMPLETE / SHIP 口径；与 RESULTS 互引）"
    }
  ],
  "normalized_by": "手工规范化（本 slice）；1D-delta importer 版本号回填",
  "normalization_rules": "declared_statuses 逐条对应原文状态行；scenario 集合取 manual-test.md 的 S-1..S-6；不修改任何历史结论"
}
```

**铁律**：`source_sha256` 为 null 时，fixture 只能作为**合成 dogfood**运行（与 75ce2b4
现状相同），输出必须标注 `PROVENANCE: UNVERIFIED`；hash 回填后才可声称"带溯源
dogfood 通过"。不能为让历史变绿而修改历史证据文件。
**机器强制落点**（不靠自觉）：回放器读到 provenance.json 时——任一 `source_sha256`
为 null → 在自测输出与 report 打印 `PROVENANCE: UNVERIFIED`，且自测**断言该行存在**
（1B-delta 实现）；全部非 null → 1D-delta importer 负责复核 hash 与 normalized
representation 的对应关系，复核不过即 fixture 无效。伪造路径被堵死：想去掉
UNVERIFIED 标记只能真实填 hash，而假 hash 会在 1D-delta 复核时暴露。

### 3.2 normalized representation（steps.jsonl 内容要求）

- 6 个 required 场景 S-1..S-6；仅 S-1 有 root run（对应"终点式 E2E 只真跑了算术问答"）；
- `declare-status`：manual-results.md 口径对 S-1..S-6 全部声明 PASS；
  manual-test.md 口径对 S-2 声明 NOT RUN；
- 两份互引的 derived 证据（manual-results ↔ task16-delivery-audit）；
- `set-delivery --verdict SHIP`；
- release_unit：must_ac_count=16、task_count=17、plan_lines=4676。

### 3.3 expected-diagnostics.txt（有序，前三行为 handoff §10 冻结序列）

```text
DIAG REQUIRED_SCENARIO_NOT_RUN: <S-2..S-6 按字典序逐条>
DIAG STATUS_CONFLICT: <manual-results 声称 PASS vs 账本 NOT_RUN，按 scenario 字典序>
DIAG DELIVERY_VERDICT_CONTRADICTS_LEDGER: ...
DIAG EVIDENCE_DEPENDENCY_CYCLE: ...
DIAG RELEASE_UNIT_TOO_LARGE: ...
```

精确文案在 1B-delta 落盘时由首次运行输出冻结（先审文案再入库）；**错误码序列**本 slice
即冻结如上——排序规则见 plan.md §3，该序列是全局序的自然结果，非特例。

## 4. fixture backlog（本 slice 只登记，不实现、不声称已跑）

| 待验证场景 | 归属 slice | 现状 @ 75ce2b4 |
|---|---|---|
| required scenario=NOT_RUN | 1B | ✅ 已有程序化用例；静态 fixture 待落盘 |
| evidence 缺失/hash 不符/依赖环 | 1B | ✅ 程序化用例已有 |
| input 与 result 不是同一 testcase | 1B | ⚠️ 部分（declare-status 对账）；细粒度输入绑定待 2B |
| full-audit 后改结果 / audit 后新增 commit | 1C | ✅ 程序化用例已有 |
| frozen oracle 变化无批准 | 2B | ✅ 基础用例已有；mutation report 未做 |
| wrong worktree / old binary attestation | 3A | ⚠️ 仅 adapter_status=UNKNOWN 语义 |
| required history/upgrade lane 未执行 | 3B/3C | ✅ RISK_CLOSURE_MISSING 用例已有 |
| 非确定性 1/3 成功声称 PASS | 3B/3C | ✅ 基础用例已有 |
| timing：--exec 实测 / declared 分离 / 排序幂等 / TIMING_GAP | **1B-delta（本 plan）** | ❌ 待实现 |
| Companion fixture 带真实溯源 hash | **1D-delta（本 plan）** | ❌ BLOCKED：依赖 F:\ 可达机器 |
| Windows 路径归一化自测 | 1D-delta | ❌ 本机 macOS 无法真实验证 |
