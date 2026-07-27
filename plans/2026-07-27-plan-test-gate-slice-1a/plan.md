# Slice 1A（delta）技术 plan — timing contract + fixture 溯源 + 诊断排序 + 设计问题闭环

<!-- plan-status: draft（用户 review 后定稿） -->

> 基线：`main` @ `75ce2b4`。OPTIMIZATION-HANDOFF 基线 `5a4ea7c` 已漂移；本 plan 按
> handoff §3 规则完成对账。产物固定在本目录；实现代码在用户 review 通过并授权后进行。

## 0. 对账：handoff 要求 vs 当前仓库事实

| handoff 要求 | 状态 @ 75ce2b4 | 本 plan 处置 |
|---|---|---|
| schema（§5、§8-1A） | ✅ `skills/plan-test/schemas/plan-test-run.schema.json` | 增补 `timing` 段（本 plan §2） |
| run-dir 契约（§5） | ✅ `skills/plan-test/gate/PROTOCOL.md` §1 | 不变 |
| canonical CLI 八命令（§6） | ✅ `scripts/plan_test_gate.py`（另有 declare-status/set-delivery） | 增补 `record-timing`/`checkpoint`（归 1B-delta） |
| 稳定错误码 12 个（§7） | ✅ 全部实现 + `STABILITY_SAMPLES_INSUFFICIENT` 等 | 排序契约成文（本 plan §3） |
| 有序 diagnostic（§7） | ⚠️ 确定性来自实现顺序，未成文 | 本 slice 冻结规则；1B-delta 实现显式排序 |
| required rows 自动 NOT_RUN、状态重算、锁/CAS（§8-1B） | ✅ 实现并有用例 | 不变 |
| receipt/stale/幂等（§8-1C） | ✅ 实现并有用例（audit 后 fact/commit 变化即失效） | 不变 |
| plan-task 接入 canonical command（§8-1D） | ✅ SKILL.md/phase 文档已接线 | 不变 |
| Companion dogfood 三错误码（§10） | ⚠️ 已有测试用例，但为**合成数据**，无冻结来源 hash | 本 slice 冻结溯源契约；1D-delta 在可达 F:\ 的机器补 hash |
| 最小 PASS fixture（§10） | ⚠️ 测试内程序化构造，无静态磁盘 fixture | 本 slice 冻结磁盘格式；1B-delta 落盘 |
| timing fact contract（§11、§9.12） | ❌ 完全缺失（ledger 只有 `recorded_at` 时间戳） | **本 slice 核心增量**（§2） |
| checkpoint 机制（§11） | ❌ 缺失 | contract 本 slice；实现 1B-delta |
| Slice 2A/2B/3A–3C | ❌ 未做（gate/ROADMAP.md 已登记） | 不在本 slice |

## 1. handoff §9 十三个设计问题的答案

1. **schema 的 producer/consumer/migration**：producer 只有 `plan_test_gate.py`（init 创建、
   record-* 追加）；consumer 是同一脚本的 validate/render 与人读 report。版本策略
   （**目标态，非现状**——当前 validator 对 `schema_version` 取值完全不检查，未知段被
   `structural_check` 静默忽略、无警告；这是实现缺口，不是已有行为）：validator 校验
   major==自身 major，不符即 `SCHEMA_INVALID`；同 major 的旧 minor 兼容（缺段视为空）；
   ledger minor 高于 validator 时输出警告行。该校验列入 §4 实施步骤 2（owner：1B-delta
   执行者）。跨 major 须显式 `migrate` 命令（未来 slice，出现 breaking 变更时才建）。
   本次加 `timing` 段是向后兼容的 minor 升级：`1.0.0 → 1.1.0`，旧 ledger 无 timing 段
   仍合法。
2. **单文件 facts+projection 还是 event list**：维持 75ce2b4 的选择——单文件、分节
   append-only facts（runs/evidence/timing/events），**不存任何 projection**；全部状态
   检查时重算。理由：projection 落盘就会出现第二事实源，正是要消灭的病根。
3. **可写边界**：调用者可写 = 原始 fact 的描述性字段（scenario/kind/lane/driver/
   business_terminal、timing 的 phase/task/activity_class/受控 wait_reason）；validator
   派生 = 场景状态、state、diagnostics、receipt digest；CLI 测量 = 证据 hash、文件锁、
   revision、timing 的 started_at/ended_at/elapsed_ms（--exec 模式）。任何"结论"字段
   （declared_statuses、delivery.verdict）只是登记待对账的口径，不是状态。
4. **锁/原子写/CAS**：已实现——`O_CREAT|O_EXCL` 锁文件 + 退避重试；tempfile +
   `os.replace` 原子写；revision CAS，冲突返回 `REVISION_CONFLICT` 稳定错误。不变。
5. **primary vs derived**：已实现——evidence.kind 枚举；derived 不能单独作证
   （`DERIVED_EVIDENCE_ONLY`）；依赖环拒绝（`EVIDENCE_DEPENDENCY_CYCLE`）。不变。
6. **required AC/scenario 从哪里导入**：init manifest 的 `scenarios[]`（源自 acceptance
   场景矩阵），init 后不可增删（record-run 拒绝未知场景）；变更需重新 init 新 run-dir
   并说明原因。不变。
7. **legacy 规范化与 provenance**：本 slice 冻结 provenance 记录格式（见
   fixture-contract.md §3）：每个来源文件记 `source_path`（原机绝对路径）、
   `source_sha256`、`captured_at`、`captured_on`（机器标识）、`normalized_by`（工具/
   人 + 版本）。normalized fixture 与原文的对应关系必须可复核；**不能为让历史变绿而改
   历史证据**。实际 hash 采集 = 1D-delta，在可访问 F:\ 的机器执行。
8. **diagnostic 排序、结构化 stdout、exit code**：exit 0/1/2 已实现；stdout 行格式
   `DIAG <CODE>: <detail>` + `STATE:` 行已实现。排序契约（本 slice 冻结，1B-delta 实现）：
   见 §3。
9. **跨平台路径**：ledger 内证据路径一律**相对 run-dir、正斜杠**（Windows 写入时
   `os.path` 归一为 POSIX 风格）；`abs_path` 仅作本机提示信息，不参与 digest；身份靠
   sha256 不靠路径。1B-delta 给 attach-evidence 加路径归一化（现状 macOS 下天然 POSIX，
   Windows 未验证——列为 1B-delta 测试项）。
10. **第三方依赖**：不需要。现有实现纯 stdlib（json/hashlib/subprocess/os/tempfile）；
    timing 采集用 `time.monotonic_ns()`，仍是 stdlib。若未来需要（如 jsonschema 严格
    校验），须在 config.md 声明安装与版本锁定方式——当前不引入。
11. **三入口 skill 兼容**：plan-test/plan-task 已接线（phase-4 init/check-only、phase-5
    audit、final-dod finalize）；plan-bs 不产生验证 run，不受影响。timing 增量只加可选
    段与可选命令，不改变现有命令签名——兼容。1B-delta 回归跑现有 23 用例证明。
12. **timing contract**：见 §2（本 plan 核心）。
13. **回滚**：见 §5。

## 2. timing fact contract（冻结；采集实现归 1B-delta）

### 2.1 ledger 新增段（schema 1.1.0）

```jsonc
"timing": [
  {
    "timing_id": "t-0001",             // producer 生成，run 内唯一
    "phase": "phase-4",                // 调用者声明（phase-A/0/1/2/3/4/5/final）
    "slice": "slice-1a",               // 可选，调用者声明
    "task": "S-2 真人 E2E",            // 调用者声明
    "command": "record-run ...",       // producer 记录（--exec 模式下为被测命令）
    "tool": "mcp-chrome",              // 可选，调用者声明
    "activity_class": "manual_e2e",    // 枚举，调用者声明，见 2.2
    "wait_reason": null,               // 仅 *_wait 类必填，受控词表，见 2.2
    "started_at": "2026-07-27T09:00:00Z",  // RFC 3339 UTC；producer 写入
    "ended_at":   "2026-07-27T09:12:34Z",  // 同上
    "elapsed_ms": 754321,              // 非负整数；--exec 模式由 monotonic clock 测得
    "measured": true,                  // true=CLI monotonic 实测；false=调用者申报
    "retry": 0,                        // 第几次重试（0=首次）
    "abort": false,                    // 是否中途放弃
    "test_count": 1,                   // 本段覆盖的测试执行数
    "runtime_identity": {"head": "<sha>"}, // producer 从 git 读取
    "evidence_ids": ["ev-abc"],        // 关联证据
    "recorded_at": "..."               // producer 写入
  }
]
```

### 2.2 枚举与受控词表

- `activity_class`（七类，final report 必须分列聚合）：`implementation`、
  `automated_test`、`manual_e2e`、`provider_wait`、`user_wait`、
  `interruption_recovery`、`rework`。
- `wait_reason`（仅 `provider_wait`/`user_wait` 必填）：`provider_latency`、
  `quota_limit`、`user_review`、`user_input`、`environment_provision`、`other:<自由文本>`。

### 2.3 producer / consumer / authority（AC-1 核对表）

| 字段 | producer | 调用者可写？ | consumer | authority |
|---|---|---|---|---|
| timing_id, recorded_at, command | CLI | 否 | validator（唯一性）、render | ledger |
| phase, slice, task, tool | 调用者经 CLI 参数 | 是 | render 聚合分组 | ledger |
| activity_class, wait_reason | 调用者经 CLI 参数（枚举校验，非法值 exit 2） | 是（受控） | render 七类分解 | ledger |
| started_at, ended_at, elapsed_ms（measured=true） | CLI `--exec` 包裹执行：wall clock 记起止（RFC 3339 UTC），`time.monotonic_ns()` 测 elapsed_ms | **否** | validator（TIMING_GAP）、render | ledger |
| started_at, ended_at（measured=false） | 调用者申报（真人 E2E 等外部活动） | 是 | 同上（低信任列） | ledger |
| elapsed_ms（measured=false） | CLI 由申报起止相减计算并写入 | 否（派生自申报值） | render "declared time" 列 | ledger |
| measured | CLI 按模式强制（--exec→true，申报→false），不可由参数指定 | 否 | validator、render | ledger |
| retry, abort, test_count | 调用者经 CLI 参数 | 是 | render | ledger |
| runtime_identity | CLI 从 git 读取 | 否 | validator | ledger |
| evidence_ids | 调用者经 CLI 参数；CLI 校验 id 存在于 evidence[] | 是（受校验） | validator | ledger |
| 聚合（各 class 总时长、active vs wait） | validator/render 重算 | 否 | report 读者 | **不落盘** |

规则：`measured:false` 的条目不计入"measured active time"聚合，report 单列
"declared time"。"`elapsed_ms` 不得由 wall-clock 相减"这条铁律**只约束
measured=true**（--exec 强制 monotonic）；measured=false 的 elapsed_ms 本质就是申报
起止的差值——它的不可信不靠禁止产生，靠 measured 标记 + report 分列曝光。

### 2.4 新命令（1B-delta 实现，签名本 slice 冻结）

```bash
# 包裹执行并实测计时（推荐路径）
python plan_test_gate.py record-timing --run-dir D --phase phase-4 --task "S-2" \
  --activity-class automated_test [--retry N] [--test-count N] --exec -- <command...>

# 申报外部活动（真人 E2E、用户等待）
python plan_test_gate.py record-timing --run-dir D --phase phase-4 --task "S-2" \
  --activity-class manual_e2e --declared-start <RFC3339> --declared-end <RFC3339>

# 检查点（目标：连续工作每 90–120 分钟一次）
python plan_test_gate.py checkpoint --run-dir D --slice slice-1a \
  --note "当前活动/测试状态/下一动作"
```

`checkpoint` 写入 events：HEAD、dirty 指纹、当前 slice、note、时间。validator 增加
**advisory 级**诊断 `TIMING_GAP`（相邻 timing/checkpoint fact 间隔 > 120 分钟时提示，
不阻塞 finalize——阻塞版待实际使用数据后再定，防止一开始就把门做成摆设或噪声）。

### 2.5 report 聚合（render，1B-delta）

report.md 增加"耗时分解"节：按 activity_class 分列 measured / declared 总时长、
retry 次数、abort 次数、checkpoint 数与最大间隔——对应 handoff §11 的最终报告分解
要求（implementation / automated test / manual E2E / provider wait / user wait /
interruption recovery / rework）。

## 3. 诊断排序契约（本 slice 冻结；1B-delta 实现显式排序）

同一 ledger 状态重跑 validator，diagnostic 序列必须逐字节相同。排序键：

1. 第一键：**canonical 类别固定序（本节即唯一权威定义）**——注意：这**不是**当前
   `validate()` 的实现发射顺序，也**不是**当前 PROTOCOL.md §4 表格的行序；1B-delta
   必须同时改实现（收尾 `sorted(diags, key=...)`）并把 PROTOCOL.md §4 表格重排为此序
   （实现排序列入 §4 实施步骤 2；PROTOCOL §4 表格重排列入步骤 1）：

   ```text
    1 SCHEMA_INVALID
    2 REQUIRED_SCENARIO_NOT_RUN
    3 STATUS_CONFLICT
    4 DELIVERY_VERDICT_CONTRADICTS_LEDGER
    5 UI_EVIDENCE_MISSING
    6 RUN_CREATION_UNVERIFIED
    7 EVIDENCE_MISSING
    8 EVIDENCE_HASH_MISMATCH
    9 EVIDENCE_DEPENDENCY_CYCLE
   10 DERIVED_EVIDENCE_ONLY
   11 FROZEN_ORACLE_CHANGED
   12 BEHAVIOR_APPROVAL_REQUIRED
   13 RISK_CLOSURE_MISSING
   14 STABILITY_SAMPLES_INSUFFICIENT
   15 RELEASE_UNIT_TOO_LARGE
   16 TESTED_RUNTIME_MISMATCH
   17 AUDITOR_MISSING
   18 AUDITOR_INPUT_STALE
   19 RECEIPT_STALE
   20 TIMING_GAP（advisory，恒排最后）
   ```

2. 第二键：类别内按 scenario_id / evidence_id / 文件路径的字典序；三者皆无的诊断
   （如 TESTED_RUNTIME_MISMATCH、RECEIPT_STALE）以 detail 全文字典序兜底 tiebreak，
   保证任何组合下序列仍逐字节确定。

自洽性核对：Companion fixture 期望的前三类
`REQUIRED_SCENARIO_NOT_RUN(2) → STATUS_CONFLICT(3) → DELIVERY_VERDICT_CONTRADICTS_LEDGER(4)`
以及其后的 `EVIDENCE_DEPENDENCY_CYCLE(9) → RELEASE_UNIT_TOO_LARGE(15)` 在此全局序下
严格递增，与 fixture-contract.md §3.3 的期望文件逐行一致——三处契约（本节、PROTOCOL
§4 重排后、expected-diagnostics.txt）共用同一序，消除互斥。1B-delta 加用例：同一
fixture 连跑两次，stdout 全等。

## 4. 实施步骤（用户 review 通过后执行；每步一个 commit）

1. schema `1.0.0 → 1.1.0`：加 `timing` 段定义 + `events` 里 checkpoint 形态；
   PROTOCOL.md 增补 timing/排序/TIMING_GAP 契约（文档与 schema 同 commit）。
2. `plan_test_gate.py`：`record-timing`（--exec 与 declared 两模式）、`checkpoint`、
   validate() 显式排序、`TIMING_GAP` advisory、render 耗时分解节。
3. 自测：新增用例——--exec 实测（monotonic 非负、measured=true）、declared 强制
   measured=false、枚举拒绝非法 activity_class/wait_reason、排序幂等（同 fixture 两跑
   stdout 全等）、TIMING_GAP 触发；回归跑既有 23 用例。
4. 静态 fixture 落盘：`skills/plan-test/fixtures/gate/pass-minimal/` 与
   `fixtures/gate/fail-companion-conflict/`（格式见 fixture-contract.md），自测改为
   同时驱动静态 fixture 与程序化构造。
5. phase 文档接线：phase-3/4/5 的"入账"要求补 record-timing/checkpoint 一句话引用；
   phase-final-dod 报告模板加耗时分解行。
6. （1D-delta，另一台机器）Companion 来源文件 hash 采集 → 填入
   `fail-companion-conflict/provenance.json` → dogfood 断言三错误码有序输出。

步骤 1–5 全部在 target repo；不碰 DeskPet；不 push（用户要求后另行推送）。

## 5. 回滚方案（AC-8）

- 本 slice（纯规划文档）：`git revert` 单个 plan commit 即可，无运行时影响。
- 1B-delta 实现：每步独立 commit，可逐个 revert。`timing` 段是可选字段：revert 回
  1.0.x validator 后，含 timing 段的新 ledger 仍可被读取——**当前 `structural_check`
  对未知段静默忽略（无警告，见 §1.1 的实现缺口说明）**，因此不会解析失败；ledger
  内容 digest 不变，已生成的 receipt 的 `ledger_sha256` 仍匹配。
- **VALIDATOR_VERSION 联动（显式假设）**：receipt 绑定 `validator_version`。1B-delta
  会 bump 该版本号，因此 revert validator 代码后，用新版本 finalize 过的 receipt 其
  `content_digest` 复算值改变 → `RECEIPT_STALE`。这是**设计使然**（validator 变了，
  旧判定不应继续有效），不是回滚缺陷；回滚后须对活跃 run 重新 finalize。
- schema minor 升级不迁移旧文件；出现需要破坏性变更时才建 `migrate` 命令（未来 slice）。

## 6. 风险与开放问题

- **TIMING_GAP 的门槛与级别**：先 advisory，等真实 run 数据再决定是否升级为阻塞——
  写死 120 分钟阻塞可能在长时间真人测试/等待场景产生大量误报。**升级决策的 owner 与
  时点**：1D-delta 收尾时由执行代理汇总首批真实 run 的 gap 分布交用户拍板；在此之前
  不得擅自升级为阻塞。
- **申报式 timing 的可信度**：无法机器强制，只能靠 measured 标记 + report 分列曝光；
  这是诚实的边界，不假装能验证。
- **Windows 路径归一化**：本机（macOS）无法真实验证，1B-delta 用例只能纯逻辑覆盖；
  在 Windows 机器跑一遍自测列为 1D-delta 检查项。
- **Companion 溯源 hash 不可在本机采集**：如实 BLOCKED 在 1D-delta，依赖 F:\ 可达机器。
