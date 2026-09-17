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

候选指针位于仓库根 `.plan-test/active-run.json`，不在 run-dir 内。compiled 真实交付默认启用；
旧 raw manifest 仅在声明 `active_run_required=true` 时生效，并且只由 `activate-run` 显式更新。

## 2. canonical command（唯一判定入口）

```bash
python "${CLAUDE_PLUGIN_ROOT}/skills/plan-test/scripts/plan_test_gate.py" finalize --run-dir <run-dir>
```

- plan-task/plan-test 的最终交付判定**只接受本命令的 exit code 与结构化 stdout**，不接受代理手写结论。
- `finalize --check-only` 是审计前预检：检查除 auditor/receipt 外的全部输入与测试完整性，
  成功只输出 `READY_FOR_AUDIT`——预检不因"审计尚未执行"而永远无法进入审计阶段。
- 正式 `finalize`：额外要求 auditor PASS，重新校验全部 hash/HEAD/runtime 后生成
  `gate-receipt.json`（幂等：同输入复用同 receipt digest 与首次 finalized_at）。
- `attach-evidence --replace`：重测后证据文件更新时顶替同路径旧条目，旧条目连同旧 sha256 转入 `superseded_evidence`，动作进 integrity 链并在 report 显形——**不是静默覆盖**，也换不绿场景（状态由 append-only 的 `runs[]` 重算）。
- `invalidate-run --run-index N --reason <operator_error|upstream_unavailable|test_harness_bug>
  --detail <≥10 字>`：事后把一条 root fail 标记为非产品原因（追加式链条目；不改 result、不许改写；
  report/receipt 单列；不进 FLAKY 分母）。
- 记账辅助命令：`record-timing`（时间成本入账，--exec 实测 / declared 申报两模式）、
  `checkpoint`（工作检查点）、`phase-start`/`phase-end`（阶段事件，finalize 要求配对）
  与 `re-attest`（收尾期改动后重新采集运行时身份）——见 §5 规则 10 与 8b。
- `import-evidence --from-run <来源说明>`：**开账之前**产生的历史证据的唯一合法入口
  （chain of custody 入账并在 report 显形）。普通 `attach-evidence` 会记录证据文件 mtime，
  早于开账即 `EVIDENCE_PREDATES_LEDGER`——DeskPet 复盘实锤"先测三小时、账本两分半补写完"
  这条路径后新增。
- `record-approval --kind all-ai-driving --message-hash <sha256>`：登记用户在 chat 中的
  显式批准，绑定批准消息原文 hash。输入语义敏感 + required UI 场景全 AI 驾驶时必须有
  （或至少 1 次 `--driver human` 的 root run），否则 `DRIVER_APPROVAL_MISSING`。
- `render`：重新运行同一 validator、复验 receipt digest，失效时**不渲染 SHIPPABLE**。
- 没有有效 receipt 的手写 `SHIP / 100% COMPLETE` 一律视为
  `DELIVERY_VERDICT_CONTRADICTS_LEDGER`。
- plan challenge：`start-challenge-loop` 冻结 `assurance-contract.json`；
  `record-challenge-round` 只接收结构化 finding envelope 并按真实 ID 推导状态；
  `record-challenge-control` 记录 scope audit、architecture reset、user review/scope approval。
  Reviewer 自报 verdict 不参与收敛。
- `compile-manifest --spec verification-spec.json --output manifest.json`：从结构化 AC/obligation/
  testcase/scenario 映射编译 manifest，冻结输入 hash 与完整 required case set；不解析 Markdown。
- `attach-evidence` / `import-evidence --metadata <json 文件或内联 JSON>`：给场景级
  `evidence_contract` 提供 producer、artifact kind、identity、生成时间和 business facts；
  非标准字段自动折进 `extra`。`record-run --exec` 自动生成 gate-exec provenance；
  单独声明 `kind=primary` 不足以满足 contract。
- `audit`：JSON output 中的 findings 与 verdict 原子入账。用 `list-audit-findings` 查看 obligation，
  用 `resolve-audit-finding` 绑定 resolution、证据和必要的 fresh retest；闭环后必须重新审计。
- `activate-run`：仅供 `active_run_required=true` 的 run 显式绑定候选内容；init 不自动抢占，
  re-attest 后需重新执行。

以上输入格式与完整示例见 `../references/evidence-audit-lifecycle.md`。

### exit code（交付判定只看这个）

| code | 含义 |
|------|------|
| 0 | 真实交付通过（唯一可用于宣布完成的返回值） |
| 1 | 门禁 FAIL（stdout 有 DIAG 行） |
| 2 | 用法/IO 错误 |
| 3 | **fixture-only run 通过**——合成数据，receipt 标 FIXTURE-ONLY，**不可作为交付证据** |

exit 3 是刻意与 0 分开的：`fixture_only: true` 会跳过全部 git 校验，此前它同样返回 0，
"在真实项目里给 manifest 加一个字段"就是最省事的一条绕过路径。现在它绿得很显眼，但绿不进交付。

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

**输出有序**：同一账本状态重跑，诊断序列逐字节相同。第一键 = 下表行序（canonical 序，
即 `CANONICAL_ORDER`）；第二键 = 类别内 scenario_id / evidence_id / 路径字典序，三者皆无
以 detail 全文兜底。severity=error 的行以 `DIAG` 前缀输出并拦截；severity=advisory 的行
以 `ADVISORY` 前缀输出、**不拦截**（不影响状态机与 receipt）。

| # | code | severity | 触发条件 |
|---|---|---|---|
| 1 | `SCHEMA_INVALID` | error | 账本结构不合 schema，或 schema_version major 与 validator 不符 |
| 2 | `LEDGER_TAMPERED` | error | integrity 链断裂或末条 facts_digest ≠ 当前 fact——账本在 CLI 之外被改过 |
| 2b | `RUN_ABANDONED` | error | 用户已用 `acknowledge` 确认放弃这一轮——不再阻断 hook，但永远不产出 receipt（见 §5.8d） |
| 2c | `SIBLING_RUN_UNRESOLVED` | error | 同一 `verification/` 下有**测同一批必测场景**、已有 run fact、却既未 retire 也未 acknowledge、也没有 receipt 的兄弟轮——这段历史没有交代，本轮不得发 receipt（见 §5.8e） |
| 3 | `REQUIRED_SCENARIO_NOT_RUN` | error | required 场景为 NOT_RUN/PARTIAL/BLOCKED/FAIL |
| 4 | `STATUS_CONFLICT` | error | 文档口径（declared）与账本重算结果冲突 |
| 5 | `DELIVERY_VERDICT_CONTRADICTS_LEDGER` | error | 手写 SHIP/COMPLETE 但 required 未全 PASS |
| 6 | `UI_EVIDENCE_MISSING` | error | UI 场景判 PASS 但无真实 UI action 的 primary 证据 |
| 7 | `RUN_CREATION_UNVERIFIED` | error | expected_run_created 声明未被正/负向证据兑现 |
| 8 | `EVIDENCE_MISSING` | error | 证据文件不存在 / 依赖不存在 |
| 9 | `EVIDENCE_HASH_MISMATCH` | error | 证据文件被改动 |
| 9b | `PRIMARY_EVIDENCE_MISSING` | error | 声明 evidence contract 的场景缺少 primary evidence |
| 9c | `EVIDENCE_CONTRACT_UNSATISFIED` | error | primary evidence 未满足 contract 的 artifact/identity/time/business facts |
| 9d | `EVIDENCE_PRODUCER_UNTRUSTED` | error | primary evidence producer 不在场景 contract 允许集合 |
| 10 | `EVIDENCE_DEPENDENCY_CYCLE` | error | 证据循环引用（互引的两个汇总不能构成独立证据） |
| 10b | `EVIDENCE_PREDATES_LEDGER` | error | 证据文件 mtime 早于开账时刻且未经 import-evidence 导入——先测后补账 |
| 11 | `DERIVED_EVIDENCE_ONLY` | error | required 场景只有 derived report，无 primary 证据 |
| 12 | `FROZEN_ORACLE_CHANGED` | error | 冻结 black-box testcase byte 级变化且无 behavior_change_id |
| 13 | `BEHAVIOR_APPROVAL_REQUIRED` | error | 行为变更缺少用户批准 artifact（exact old/new + 消息 hash + scope） |
| 14 | `APPLICABILITY_UNDECLARED` | error | 适用性三维未显式声明，或缺 rationale（≥10 字）/ decided_by |
| 15 | `APPLICABILITY_GATE_UNSATISFIED` | error | 声明某维「适用」但场景矩阵未兑现对应条件（见 §5.12） |
| 15b | `DRIVER_APPROVAL_MISSING` | error | 输入语义敏感 + required UI 场景全 AI 驾驶，且无真人 root run、无用户批准记录 |
| 16 | `RISK_CLOSURE_MISSING` | error | required lane 无通过的 root run |
| 17 | `STABILITY_SAMPLES_INSUFFICIENT` | error | 非确定性场景采样不足，或**当前被测 HEAD 上**有未解释失败（FLAKY；切点前 / 已标 invalid_reason 的失败不计） |
| 18 | `RELEASE_UNIT_TOO_LARGE` | error | 交付体量超阈值，须拆 program plan + 垂直 slice |
| 19 | `TESTED_RUNTIME_MISMATCH` | error | 被测**内容**指纹与当前不一致，或 adapter UNKNOWN |
| 19b | `RETEST_REQUIRED_AFTER_CHANGE` | error | behavioral re-attest 之后，required 场景没有更晚的 root PASS |
| 20 | `AUDITOR_MISSING` | error | full-audit 未执行或 verdict 非 PASS |
| 21 | `AUDITOR_VERDICT_MISMATCH` | error | auditor 产物里的 verdict 与入账 verdict 不符（命令行改判） |
| 22 | `AUDITOR_INPUT_STALE` | error | audit 后账本 fact 又变化——旧 PASS 失效 |
| 22b | `OPEN_AUDIT_FINDINGS` | error | 结构化 auditor findings 中仍有 open/deferred P0/P1 |
| 23 | `RECEIPT_STALE` | error | receipt digest 与当前输入不符 / 已 invalidate / 缺失 |
| 23b | `ACTIVE_RUN_MISMATCH` | error | opt-in active-run registry 缺失、指向其他 run，或候选内容已变化 |
| 24 | `TIMING_MISSING` | error | 真实 run 活动跨度 > 30 分钟而 timing 覆盖 < 20%（1.3.0 起；fixture 免检时钟门） |
| 25 | `TIMING_GAP` | error | 记账覆盖区间合并后仍有 > 120 分钟空洞（1.3.0 起升 error；申报 timing 可补覆盖） |
| 26 | `PHASE_UNPAIRED` | error | phase-start 无配对 phase-end（或反之）；check-only 不查，full/render 查 |
| 27 | `AUDITOR_INDEPENDENCE_UNVERIFIED` | **advisory** | auditor engine 未标注或与 executor 相同——自审自判，曝光不拦截 |
| 28 | `RUN_ATTESTATION_FANOUT` | **条件 error** | 同一命令同一时间戳扇出 ≥2 个 root pass，且任一 required 场景缺独立 primary 证据；每个场景都有独立断言日志则放行（fixture 免检） |
| 29 | `EVIDENCE_FREE_FINALIZE` | **advisory** | required 全 PASS 但整本账零 primary 证据——所有结论均为自报（1.4.0 起；fixture 免检） |
| 30 | `EXECUTOR_ENGINE_UNDECLARED` | **advisory** | manifest 未声明 `executor_engine`——独立性检查无从对照（1.4.0 起；fixture 免检） |
| 31 | `AUDITOR_ENGINE_MISMATCH` | **advisory** | 实际审计引擎偏离 init 冻结的 `auditor_engine` 声明——引擎配置被静默偏离（1.4.0 起；fixture 免检） |
| 32 | `OPEN_DEFERRALS` | **advisory** | auditor 产物含 deferred findings（`"status": "deferred"` 或 `"deferred": true`）——"留待后续"不许悬空（1.4.0 起；fixture 免检） |
| - | `REVISION_CONFLICT`（stderr） | - | 并发写 CAS 冲突——重读后重试，不静默覆盖 |
| - | `LEDGER_LOCKED`（stderr） | - | 文件锁被占用 |
| 33 | `PLAN_CHALLENGE_UNRESOLVED` | error | 账本存在挑战循环但 `_challenge_state` 现场重算 ≠ CONVERGED——未经收敛的 plan 不得交付（W2，2026-08-29） |

### 4b. 门禁登记（GATE_REGISTRY_DISCIPLINE 四问）与退休记录

**`PLAN_CHALLENGE_UNRESOLVED`（2026-08-29 新增）**
- 防的诊断码：本码。防的实测逃逸：第 5 轮审计 §4.2——4 张历史 receipt 全部发在
  **没有**挑战循环的账本上，跑过循环的 7 本一张都没有（两集合零交集）；validate()
  此前零引用 `challenge_loops`，「计划被严格挑战过」从未进过成绩单。
- 复审日期：2026-11-29。
- **第四问（被拦时的合法出口）**：把循环推进到 CONVERGED（修 plan 消掉 open P0/P1），
  或 `acknowledge` 放弃整轮（绑业主原话 hash）。W3 的 decision 原语落地后，
  亦可由带 hash 的 decision 显式豁免并在 receipt 的 waivers 里公示。

**W6 新增（2026-08-29，登记四问）**
- `FLOW_TIER_UNDECLARED`（advisory）：判档不入账。防的逃逸：判 LEAN 使 phase-0/
  多轮 closure/testcase 挑战合法消失且不留痕（enforcement-anchors run-001 实测判档理由
  失实仅靠人肉发现）。advisory 起步：存量 manifest 全未声明，error 会一夜打红全部现役 run。
  出口：manifest 补 `flow_tier{value,rationale,decided_by}`。复审 2026-11-29。
- `FLOW_TIER_BASIS_FALSE`（error）：判 LEAN 却 `input_sensitive=true`——config.md 明定
  该条件命中即 FULL，两值同在账本，交叉校验零成本。出口：改判 FULL，或修正
  applicability 判定（各带理由）。复审 2026-11-29。
- `PHASE_TELEMETRY_MISSING`（advisory）：全 run 零 phase 事件。防的逃逸：18 本真实账本
  仅 9 本有阶段事件，档位压缩效果无法评估（"再实践"环节断裂）。出口：各阶段
  phase-start/end 配对记录。复审 2026-11-29。

**v0.6.1 refusal 专码（2026-09-01，登记四问）**——这批不是新增门，是给**既有拒绝**上码：
实测 36 条真实 refusal 里 18 条（50%）无码，全是人机工程摩擦而非策略违规；无码在 stats
里只剩一个"（无诊断码）"桶，"降出口成本"没有度量。防的逃逸：出口成本不可见 → 下轮优化
只能拍脑袋。均为 die() 即时拒绝（exit 2），不进 validate 诊断序。复审 2026-12-01。
- `USAGE_ERROR`（兜底，die() 对无码消息自动冠）：出口 = 按消息文本修正调用。
- `TIMING_CLASS_INVALID`（实测 6 次）：activity_class 猜错。出口 = 消息附直觉词对照表
  （testing→automated_test/manual_e2e，coding/tooling→implementation）。
- `WAIT_REASON_REQUIRED`（实测 2 次）：wait 类缺 --wait-reason。出口 = 消息列出受控枚举
  与 other:<说明> 逃生口。
- `CLUSTER_ID_NOT_FOUND`（实测 6 次）：cluster_id 不存在。出口 = 用 primary-clusters
  记录里的真实 id，或先 record-challenge-clusters 入账。
- `EVIDENCE_PATH_NOT_FOUND`（实测 3 次）：把内联 JSON 当路径传。出口 = 先写文件再 attach。
- `ARGS_INVALID`（2026-09-01 追加）：argparse 层参数错误（缺必填/参数名写错）此前走
  argparse 自有退出路径、不经 die()，refusal 账本对这一类完全不可见（复验 handoff 实测
  连撞三次零记录）。现改经 die() 入账；usage 照旧打印、退出码仍 2。出口 = 按 usage 修正调用。

**v0.8.1 出口降本（2026-09-10，v0.6.0→v0.7.3 runlog 复盘）**——不新增门，消除既有拒绝里的
纯摩擦。事实：106 条真实 refusal 中约 75% 是 CLI 用法错误而非质量拦截（attach-evidence 元数据
32、缺必填参数 11、timing 错词 9、路径猜错 10）；另有 9 条 `LEDGER_TAMPERED` 是 gate 自己的
序号配对误报（见 §6 链长下界一节），代理误判为并发写、删掉两本账（r1/r2-s5b，100+ 条事实）。
- `attach-evidence --metadata`：接受内联 JSON（以 `{` 开头即解析，否则当文件路径）；
  `identity`/`facts` 信封抬到顶层；其他自定义字段**原样留在证据顶层**并在 stderr 声明——
  `evidence_contract.required_identity` 允许任意字段名并从顶层读，折进子对象会让契约看不见
  （review 抓出）。与已知字段"长得像"的（difflib ≥0.9，`root_runid`）和与账本自有字段同名的
  （`sha256`）仍拒绝。防的实测逃逸：16 次把 JSON 当路径 + 16 次 identity/host_head/sdk_run_id/
  tested_head/seam_count 被拒，全是有用 provenance，无一是打错的已知字段。
- `record-timing --activity-class`：小写、`-`→`_`、**无二义**同义词表归一（automated-test-execution
  →automated_test、manual-ui→manual_e2e、documentation→implementation…），归一时 stderr 打 NOTE，
  账本只存规范值；`test`/`testing` 这类自动化与真人都说得通的词仍 `TIMING_CLASS_INVALID` 并给
  二选一（render 的 manual/automated 拆分靠这一字段，不替人猜）。缺 `--wait-reason` 时
  user_wait→user_input、provider_wait→provider_latency 并声明；给了非法值仍 `WAIT_REASON_REQUIRED`。
- `--run-dir` 可省略：回落到当前仓库（`_find_repo_root_for`，含 worktree 的 `.git` 文件形态）
  `.plan-test/active-run.json` 指向的 run，解析后的目标写进 refusal 账本；没有 active run 则
  `ARGS_INVALID` 并告知 activate-run。**不回落**的子命令：init / retire / retire-status /
  activate-run / invalidate / acknowledge / ack-status——它们的 --run-dir 天然不是 active run
  （retire 回落会让继任者退役自己；另加守卫：继任者不得是本 run）。
- 缺账本 / run-dir 不存在 / 输入文件不存在：拒绝消息附解析后的绝对路径、cwd、本仓库内已有账本的
  run-dir、仓库内同名文件（≤5 个）、当前 active run。扫描有深度/条目/命中三重上限且只在仓库内
  （review 实测无预算版本把错路径拒绝从 0.08s 拖到 67s+）；不在仓库里只看最近存在的祖先两层。
- `record-run --exec` 写账被拒时执行日志以 `exec-<场景>-unrecorded-<pid>.log` 原地保留并在
  stderr 指出（gate 亲眼看过的输出不作废）。
- **稳定性只看当前被测 HEAD**（`STABILITY_SAMPLES_INSUFFICIENT`）：窗口从该场景最近一次
  behavioral re-attest 的 runs 下标起算（与 9a 重测义务同一切点，受 impact_paths 收窄；非 required
  场景用全局最近切点，只影响状态列）。窗口内：`min_root_runs` 个 root pass 才够样本（切点前的通过
  是另一份代码的样本，不计）、有未解释失败即 FLAKY。失败可标记为非产品原因：自报时
  `record-run --result fail --invalid-reason operator_error|upstream_unavailable|test_harness_bug
  --invalid-detail <≥10 字>`，`--exec` 的失败跑完才知道，用 `invalidate-run --run-index N --reason
  --detail` 事后标记（追加式链条目，不改 result、不许改写）。标记的失败仍是 fail、仍入链，
  只是不进 FLAKY 分母；**标记是留痕不是赦免**：窗口内被标记的失败多于真实通过仍判 FLAKY。
  切点前失败数 / 被标记数 / 窗口内通过数写进 receipt 的 `stability`（信息项，不进 digest）与
  report 的"稳定性窗口"一节——"碰一行代码重开窗口"与"把失败标成手误"都在成绩单上可见。
  底线不动：同一代码上时通时挂照样拦。防的实测逃逸：此前按全历史判，s5a r2 因 4 条旧 root fail
  （6 条里 5 条是 cwd/路径/marker 手误）永远到不了 SHIPPABLE、s5b r3 判 FLAKY 21/26 而 5 次失败
  成因全已修复，两次都只能开新 run-dir 干净重跑——失败史留在被 retire 的旧账里，与规则初衷相反，
  且正是 §5.8e 要堵的"换目录洗账"。
- 两处让 re-attest 静默退化为全量复测的病根：①doc-only 默认白名单补 `ARCHITECTURE/*.md`（根目录
  `ARCHITECTURE.md` 本就在，目录形态漏了；只放行 md，目录里的生成器/图表代码仍是行为文本；
  s4/s5b 各因此重测一轮）；②`init` 拒绝绝对路径或非列表的 `impact_paths`（绝对路径永远匹配不上
  仓库相对的变更清单，s5a retro 实测每次 re-attest 都退化为全量；字符串会被逐字符迭代，`*` 匹配一切）。
- `ARGS_INVALID`：缺必填参数时附该子命令的一行示例与 `--help` 指引。
- `RETIRE 拒绝`：继任者未 SHIPPABLE 时列出其阻塞诊断码，并说明不必先 finalize。
- `init` 仓库之外：消息给出 run-dir 绝对路径与仓库根，点名双仓 cwd 错配的常见病因。
- 复审日期：2026-12-10。合法出口：以上全部是放宽/提示，无新堵死态；折叠与归一均在 stderr 显形，
  账本可审计。守护测试：`test_cli_friction.py`（本文件自有用例，含链长配对的存量账本回归、
  并发 --exec、worktree 回落、拒绝时日志保留、retire 自继任守卫）。

**v0.6.1 追溯补丁（2026-09-01，同日复验 handoff）**：`strip_stored_repo_prefix`——
v0.6.1 的相对化只对新账本生效，存量账本的绝对 path 命中绝对分支后走不到"新根重接"，
12 条 sha256 完好的 testcase 仍被判缺失（exec-004 实测）。修法：剥掉账本自记的旧
repo_root 前缀、用解析出的新根重接（确定信息，不做 basename 模糊匹配）；命中后仍过
exists + sha256 双重校验，宽松只影响"能不能找到"，放不过真实删除/篡改（反向控制入测试）。

**v0.6.1 路径可移植（2026-09-01，非新码，修既有码的假阳性面）**：账本此前存开账机器的
绝对 `repo_root` 与 testcase `abs_path`，跨机器/挪目录后 `TESTED_RUNTIME_MISMATCH` /
`FROZEN_ORACLE_CHANGED` / `ACTIVE_RUN_MISMATCH` 全成假阳性且污染 stats（Windows 账本在
Mac 复验实锤）。修法：`resolve_repo_root`（存储值可达用存储值，否则从 run-dir 向上找
.git，都不行按原语义失败留证）；`testcase_lock.files[].path` 改存仓库相对 POSIX（与
evidence 路径 1D-delta 同款处理），读端按"仓库相对 → run-dir 相对 → abs_path"顺序解析，
旧账本兼容。check-only 的 HISTORICAL RECEIPT 提示自此区分"内容漂移"与"仓库不可达"两种
成因——把不可达说成漂移是安抚性错误解释。

**v0.9.0 closure 按矛盾地位路由（2026-09-17，放宽既有门 `CLOSURE_FINDING_COVERAGE_INVALID`，非新码）**
- 放宽了什么：clustered closure 此前要求复核集合 == synthesis canonical 集合。现在 synthesis canonical finding
  可带可选字段 `contradiction_role`（`decisive` | `secondary`，缺省 decisive = 旧行为）；同时满足
  标 secondary、非 P0、synthesis 里已 resolved/advisory、`violated_acceptance_ids` **非空**且与 loop
  `primary_contradiction.acceptance_ids` 无交集的 finding，closure 可不复核，其 latest 状态取 synthesis 闭环状态。
  地位由 AC 绑定推导，agent 自标 secondary 不能豁免碰到主要矛盾、P0 或仍 open 的 finding；严重度、scope 与 AC 绑定
  按该 ID **全部历史记录**（各轮 + specialist + synthesis）取最严——只看 synthesis 自填字段时，把第 1 轮 P0 改写成 P2
  或把主要矛盾 AC 换绑就能跳过复核（SL-2 code review F-1 实测判成 CONVERGED）；曾是 scope-change-proposal 的不省；
  synthesis 之后记过 architecture-reset 的整轮不省（F-2）。
- 防的实测逃逸（该门原本防什么，放宽后仍防住）：closure 只挑好复核的 finding 做、把决定性问题留在 open 却宣称收敛。
  放宽只覆盖"次要 + 已闭环 + 不碰主要矛盾"，决定性侧判定不变。
- 为什么放宽：phase-2 重点论规定次要部分 primary 覆盖一次即收，gate 却强制每轮重审全部 finding；
  一次 FULL 运行对 2 条次要 AC 跑了 5 轮挑战，挑战循环占 FULL 耗时 20–37%。回放见私有 plan 记录 AC-7(c)。
- 合法出口：被拒时错误列出缺少/多余 ID；要省略就在 synthesis 标 secondary（`print-schema --target synthesis`），
  碰主要矛盾的只能复核。账本字段是唯一新增（acceptance 已批准的例外），旧账本不带该字段判定不变
  （36 个本机历史账本 `finalize --check-only` 改动前后逐字一致）。
- 回放实测（一次 FULL 运行的 5 轮真实挑战）：没绑 AC 的 finding 不许省——唯一可省的 P1 语义上支撑决定性 AC，
  只因没填绑定才"不碰主要矛盾"；收紧后该记录可省 0 条，本门放宽对它**不省时间**，收益取决于 synthesis 是否认真填绑定。
  复审时用 refusal log 与账本统计实际被省条数，零收益则退回。
- 守护测试：`test_closure_routing.py`（放行 + 6 种拒绝 + 旧行为）。复审日期：2026-12-17。

**v0.9.0 CLI 摩擦（2026-09-17，非新码，改报错与路径解析）**：v0.8.1 后 13 条真实拒绝 10 条是摩擦、0 条防住真问题。
- `attach-evidence` / `import-evidence --path`、`audit --input/--output`：接受 run 相对、仓库/cwd 相对或绝对路径，
  落在 run-dir 内自动转 run 相对存储（账本格式不变；run-dir 判定逐级 samefile，兼容 macOS 大小写与符号链接 run-dir）；
  找不到时列出两种解析结果；在 run-dir 外拒绝并给出做法。行为变化：`audit` 此前会接受 run-dir 外的绝对路径并原样入账，
  现在拒绝——与其报错原文"须已写入 run-dir"的本意一致，账本里的审计产物必须在 run 目录内才进得了指纹链。
- 未知子命令：refusal 记下敲错的命令名（此前 cmd=null）；`record-behavior-change` 等按意图给正确做法，不再被 difflib 导向字面相近的错误命令。
- `CLOSURE_FINDING_COVERAGE_INVALID` 列缺少/多余 ID；`CLOSURE_PLAN_UNCHANGED` 提示先改 plan 再算 hash；
  `CHALLENGE_SYNTHESIS_ALREADY_RECORDED` 补冒号使 refusal 码可识别（此前被冠 USAGE_ERROR）并给下一步；
  `PRIMARY_CHALLENGE_REQUIRED` 给当前轮次与下一步；`print-schema --target clusters|synthesis`。
- 合法出口：全部是提示/放宽，无新堵死态。守护测试：`test_cli_friction_v09.py`。复审日期：2026-12-17。


**v0.9.0 零触发诊断码复审表（2026-09-17 登记，不删代码；复审日期 2026-12-17）**
数据来源：本机 36 个 run 账本 `finalize --check-only` 当前诊断 + 本机 refusal log（62 行）；全部 56 个 canonical 码减去触发过的 = 34 个。
口径局限：check-only 不跑 full/render 分支，审计阶段专有码在此口径下结构上出不来——**零触发 ≠ 无用**；另 plan 调研时估计 39 个，数据范围不同，以本表为准。
行号为 2026-09-17 版本（G=scripts/plan_test_gate.py，P=本文件，R=rationale.md），代码改动后以码名 grep 为准。复审时按 GATE_REGISTRY_DISCIPLINE 对照"当初防的逃逸"再决定退不退。

| 码 | 当初防的逃逸（出处） | 产生点 | 零触发的可能原因 |
|---|---|---|---|
| `LEDGER_TAMPERED` | 在 CLI 之外手改账本（如改一行 `runs[].result`），改完再敲一条无害命令，用新条目把篡改痕迹盖掉（P:104、P:498-504） | Diag 1867（validate，所有 mode 都查）；die 3079（`_append` 写入前先验链） | 本机样本没走到：本机账本没有被手改或链错位，refusal 里也没有这个码。P:190、P:521-527 记录过其他数据源里的真实触发（`--exec` 序号配对误报），说明这个码结构上能出现 |
| `DELIVERY_VERDICT_CONTRADICTS_LEDGER` | 没有有效 receipt、required 也没全 PASS，却手写 SHIP / 100% COMPLETE（P:51-52、P:109；R:47-48） | Diag 2120 | 本机样本没走到：要先用 `set-delivery --verdict SHIP` 之类的命令写入交付结论（G:3331）。skill 的 md 流程文档里没搜到调用 `set-delivery` 的地方（只出现在 G 头部示例和测试里），真实流程基本不写这个字段 |
| `UI_EVIDENCE_MISSING` | UI 场景判 PASS，却没有真实 UI 操作的 primary 证据（P:110；具体逃逸案例未找到出处） | Diag 1939 | 本机样本没走到 / 被前置门遮蔽：条件是 required 且 `ui` 且 PASS 且没有 `ui_action` 的 primary 证据。compiled 流程要求 UI 场景的 contract 含 `ui-capture` 和 `session_id`（G:2743-2747），缺证据时通常先报 `EVIDENCE_CONTRACT_UNSATISFIED`（本机触发过） |
| `EVIDENCE_MISSING` | 登记过的证据文件不存在，或 `depends_on` 指向不存在的证据（P:112；具体逃逸案例未找到出处） | Diag 1968、1987；1987 查依赖；2382 查 auditor 文件（只在 full/render 查） | 本机样本没走到：attach 时文件必须存在才能算 sha256（G:3281-3283），所以要事后删掉证据文件、或 `--depends-on` 填了不存在的 ID 才会触发；auditor 文件那一支只在 full/render 查 |
| `PRIMARY_EVIDENCE_MISSING` | 声明了 evidence contract 的场景拿不出 primary 证据；单独声明 `kind=primary` 不够（P:114、P:62、P:308-309） | Diag 1252（`validate_evidence_contract`，从 validate 2021 调用，所有 mode） | 本机样本没走到：只有场景一条 primary 证据都没有时才报；本机有 contract 的场景至少挂了一条 primary，缺口表现为 `EVIDENCE_CONTRACT_UNSATISFIED`（本机触发过） |
| `EVIDENCE_PRODUCER_UNTRUSTED` | primary 证据的 producer 不在 contract 允许的集合里（比如代理自报冒充 gate-exec）（P:116；G:1264-1265 注释：防"可信空记录与不可信自报拼接洗白"） | Diag 1260 | 本机样本没走到：要 contract 声明了 `producer_types`，而且所有 primary 证据的 producer 都不在集合里（全部不合格才报）；任意一条合格就不触发 |
| `EVIDENCE_DEPENDENCY_CYCLE` | 两份汇总互相引用，冒充独立证据（P:117） | Diag 2008 | 本机样本没走到：要用 `--depends-on` 构造出环；skill 的 md 流程文档没搜到 `--depends-on` 的用法（只在测试里有，如 test_plan_test_gate.py:317） |
| `EVIDENCE_PREDATES_LEDGER` | 先测后补账："先测三小时、账本两分半补写完"（P:45-46；G:1971-1974 DeskPet 截图早于开账） | Diag 1980 | 本机样本没走到：attach 的证据文件 mtime 要早于开账超过 300 秒宽限（G:213），而且没走 `import-evidence` |
| `DERIVED_EVIDENCE_ONLY` | required 场景只有 auditor 报告、交付汇总这类 derived 证据，没有 primary（P:119、P:306-307） | Diag 2018 | 本机样本没走到：要"有证据但全是 derived"；G:2513 注释说零证据时反而不触发，本机样本不满足这个组合 |
| `BEHAVIOR_APPROVAL_REQUIRED` | 冻结的 oracle 被改动，只挂一个 behavior_change_id，却没有用户批准的 artifact（P:121、P:314-315） | Diag 2084、2093 | 本机样本没走到：`behavior_changes` 只能在 init 时从 manifest 带入（G:2928），G:176-177 拒绝事后登记；本机 testcase 变更表现为不带 change_id 的 `FROZEN_ORACLE_CHANGED`（本机触发过） |
| `RELEASE_UNIT_TOO_LARGE` | 交付体量超阈值却不拆成 program plan + 垂直 slice（P:127；G:4744 "Phase 3 开工前硬门"；具体逃逸案例未找到出处） | Diag 2288（validate 读 manifest 带入的 `release_unit` 指标，G:2948）；print 4805（`check-release-unit` 子命令） | 其他 / 只在 FULL 出现：validate 分支要 manifest 填了 `release_unit` 数值指标才有输入；子命令按 phase-3-execute.md:12 只在 FULL 调用，而且结果打到 stdout，不进账本，账本扫描看不到 |
| `RELEASE_UNIT_UNDECLARED` | release_unit 缺 slice_id / parent_program / scope_hash 声明（G:4824-4831 docstring；P §4 表没有登记；具体逃逸案例未找到出处） | 无 Diag/die 产生点；print 4837、4849（`validate-release-unit` 子命令） | 结构上不进账本诊断：只在独立子命令里 print；skill 的 md 流程文档没搜到调用 `validate-release-unit` 的地方 |
| `WIP_ACCUMULATION_UNSAFE` | 未提交的 WIP 超过行数或文件数阈值（G:4862-4868 docstring；具体逃逸案例未找到出处） | 无 Diag/die 产生点；print 4922（`check-wip-limit` 子命令） | 结构上不进账本诊断：只在独立子命令里 print；skill 的 md 流程文档没搜到调用 `check-wip-limit` 的地方 |
| `LOOP_RESET_EVASION` | 改名或换 loop_id 重开挑战循环，绕过轮次限制（G:6401-6407；P:286 说明它有真实产生点，所以不退休） | 无 Diag/die 产生点；print 6429（`detect-loop-reset` 子命令） | 结构上不进账本诊断，本机也没走到：要显式传 `--check-target-file`，还要存在 status=active 的循环、且新旧文件相似度 >0.8；skill 流程文档只在 P:286 提到这个命令，没有调用步骤 |
| `SCOPE_AUDIT_REQUIRED` | 挑战轮次失控：到第 3 轮仍有新 critical 却不做范围审计（P:284-285 "3/5/8 阶梯"；phase-2-iterate-plan.md:127-128） | 无 Diag/die 产生点；是 `_challenge_state` 的返回值 5574，由 `check-loop-limit` 以 `LOOP_STATE:` 行打印（5644；另 5744、6378 同样打印） | 结构上不可达（作为诊断码）：它是循环状态字符串，不是 Diag。进账本诊断时被 `PLAN_CHALLENGE_UNRESOLVED` 包起来（G:2257-2263，只出现在 detail 文本里），本机触发的是外层码 |
| `ARCHITECTURE_RESET_REQUIRED` | 连续两轮 patch-induced P0 还在打补丁，不做结构重置（phase-2-iterate-plan.md:129；P:284-285） | 无 Diag/die 产生点；状态返回 5539、5561 | 同 `SCOPE_AUDIT_REQUIRED`：只是循环状态，进账本诊断时被 `PLAN_CHALLENGE_UNRESOLVED` 包住 |
| `USER_REVIEW_REQUIRED` | 到第 5 轮仍有新 critical，却不向用户报告（phase-2-iterate-plan.md:127-128；P:284-285） | 无 Diag/die 产生点；状态返回 5569 | 同上：只是循环状态，不是 Diag |
| `USER_SCOPE_APPROVAL_REQUIRED` | 未经用户批准就改 scope/profile/trusted boundary；也防预先记一条批准来预授权（phase-2-iterate-plan.md:130；G:5486-5491） | 无 Diag/die 产生点；状态返回 5536、5554 | 同上：只是循环状态，不是 Diag |
| `PLAN_UNSTABLE` | 执行期 plan defect（A2）累计 ≥3 条仍继续叠加 WIP，phase-2 其实没收敛（phase-3-execute.md:65-67；G:5071-5074） | 无 Diag/die 产生点；print 5084（`check-plan-stability` 子命令） | 结构上不进账本诊断，而且只在 FULL 出现：独立子命令按 phase-3-execute.md:65 只在 FULL 路径调用，还要先用 `record-plan-defect` 入账 ≥3 条未解决的 defect |
| `LEDGER_STALLED` | 账本长时间零增长，可能在绕过 gate 或空转（G:4939-4942、G:4972） | 无 Diag/die 产生点；print 4970、5001（`check-ledger-progress` 子命令） | 结构上不进账本诊断：只在独立子命令里 print；skill 的 md 流程文档没搜到调用 `check-ledger-progress` 的地方 |
| `AUDITOR_MISSING` | 没做独立 full-audit（或审计判 FAIL）就交付；full-audit 放在输入冻结之后（P:130；R:56-60） | Diag 2346、2349 | 只在 FULL+审计阶段出现：只在 mode full/render 查（G:2344），check-only 明确不查（P:32-33）；`compute_state` 在审计前还专门把它扣掉（G:2585） |
| `AUDITOR_VERDICT_MISMATCH` | 审计报告写 FAIL，命令行敲 PASS（P:131、P:543-545；G:2355-2356） | Diag 2359、2363（full/render）；die 1719（`audit` 命令里 JSON verdict 与 report_markdown 结论不一致，G:3617 调用） | 只在 FULL+审计阶段出现；而且 `audit` 写入时已先把不一致拒掉，要事后改 auditor-output 才能到 Diag 分支（这时同时会报 EVIDENCE_HASH_MISMATCH） |
| `AUDITOR_INPUT_STALE` | 审计之后又改代码、testcase 或结果，继续沿用旧的 PASS（P:132、P:316-317；R:56-58） | Diag 2353 | 只在 FULL+审计阶段出现：要 mode full/render 且账本里已有 auditor 记录 |
| `RECEIPT_STALE` | 拿到 receipt 后输入又变了（如文档回写后提交），旧 receipt 继续当交付证据（P:134、P:316-317；R:39-43） | Diag 3833、3837、3841（只在 `cmd_render` 里） | 只在 FULL+审计阶段出现：只有 render 会产生；finalize 和 check-only 都不输出这个码 |
| `PHASE_UNPAIRED` | 阶段没收尾就 finalize，耗时归属不完整（P:138、P:476；G:3451 DeskPet 3.5 小时只能靠会话日志考古） | Diag 2504、2508 | 只在 FULL+审计阶段出现：P:138 写明 check-only 不查，G:2483 只在 full/render 查 |
| `PHASE_TELEMETRY_MISSING` | 全 run 零 phase 事件，档位压缩效果无法评估（P:168-170；R:82-85 "18 本仅 9 本有阶段事件"） | Diag 2489（advisory） | 只在 FULL+审计阶段出现：只在 full/render 查（G:2483）；按 P:168-170 的实测，存量账本里本该大量命中，check-only 扫描看不到 |
| `FLOW_TIER_BASIS_FALSE` | 判 LEAN 却 `input_sensitive=true`，判档依据失实，让 FULL 的环节合法消失（P:165-167；R:81-83） | Diag 2242 | 本机样本没走到：要 manifest 同时声明 `flow_tier.value=LEAN` 和 `input_sensitive=true`；本机触发的是 `FLOW_TIER_UNDECLARED`，说明多数账本根本没声明 flow_tier，这个交叉校验没有输入 |
| `PLAN_SCOPE_EXPANSION` | plan 体量比 baseline 增长 >1.5 倍，scope 悄悄扩张（G:6450-6452 docstring；具体逃逸案例未找到出处） | 无 Diag/die 产生点；print 6471（`check-plan-growth` 子命令，advisory，exit 0） | 结构上不进账本诊断：只在独立子命令里 print；skill 的 md 流程文档没搜到调用 `check-plan-growth` 的地方 |
| `AUDITOR_INDEPENDENCE_UNVERIFIED` | 审计者和实现者是同一个引擎，自审自判（P:139、P:545-547） | Diag 2370、2374（advisory） | 只在 FULL+审计阶段出现：要 full/render 且有 auditor；另外 `audit --engine` 必填并过正则（G:214），"未标注"一支只剩 engine 填 unknown/self/same 才进得去 |
| `RUN_ATTESTATION_FANOUT` | 一次 smoke 或 pytest 复制成多个场景的 root pass，冒充独立断言（P:140、P:576-577；R:68-71） | Diag 2043（条件 error，所有 mode，fixture 免检） | 本机样本没走到：要同一 command 且同一 `recorded_at` 扇出 ≥2 个场景，并且其中有 required 场景缺 primary 证据；`record-run --exec` 会逐条自动产生 primary 日志，自然避开这个条件 |
| `EVIDENCE_FREE_FINALIZE` | required 全 PASS，但整本账零 primary 证据，结论全靠自报（P:141；G:2511-2514 simple_harness 4 个 slice evidence=0） | Diag 2518（advisory） | 只在 FULL+审计阶段出现：只在 full/render 查（G:2515），还要 required 全 PASS |
| `EXECUTOR_ENGINE_UNDECLARED` | manifest 不声明实现引擎，独立性核对没有对照对象（P:142；G:2388-2390 "executor_engine 全部 None"） | Diag 2394（advisory） | 只在 FULL+审计阶段出现：只在 full/render 查（G:2392）；按 G:2389 的描述，存量账本里本该常见，check-only 看不到 |
| `AUDITOR_ENGINE_MISMATCH` | 实际审计引擎偏离 init 冻结的声明，引擎配置被静默换掉（P:143；G:2388-2389 "默认 opus-4.8，实际 4 次审计全是 gpt-5"） | Diag 2402（advisory） | 只在 FULL+审计阶段出现：要 full/render、manifest 声明了 `auditor_engine`、并且已有 audit 记录 |
| `OPEN_DEFERRALS` | 审计里"留待后续 slice"的承诺在 run 收尾后悬空（P:144；G:2406-2408 simple_harness run-4） | Diag 2411（advisory） | 只在 FULL+审计阶段出现：只在 full/render 查（G:2392 块内），还要 auditor-output 里有 deferred 项 |

**退休记录（2026-08-29）**：`LOOP_LIMIT_EXCEEDED` / `LOOP_REGRESSION` / `LOOP_NO_PROGRESS`
- 三码自 2026-08-14 登记以来**从未有产生点**（第 5 轮审计实证：全文件仅 `CANONICAL_ORDER`
  声明处 1 次引用；1888 次真实调用零触发）。它们从未防住过任何东西——
  不是"防住了所以没触发"，是**结构上不可能触发**。
- 守备面移交：轮次失控由 `_challenge_state` 的 SCOPE_AUDIT/USER_REVIEW/BLOCKED 阶梯
  （3/5/8）承担；"循环烂尾"由 `PLAN_CHALLENGE_UNRESOLVED` 承担。
- `LOOP_RESET_EVASION` **不退**：`detect-loop-reset` 有真实产生点。

## 5. 硬规则摘要

1. **required rows 由 init 自动创建为 NOT_RUN**；命令只记录事实（record-run /
   attach-evidence），状态由 validator 计算，调用者不能把 NOT_RUN 改成 PASS。
2. **retry / replay / 同意图改写 / continuation 不是 root run**——只有 root 计入场景状态。
2b. **`blocked` 与 `fail` 都是非粘性的**（blocked 2026-08-09 修；fail W4-15 2026-08-29 修）。
   语义都是"此刻没过"，被**其后的一条 root pass** 覆盖即解除；解除的唯一方式是真的补一条
   root pass，该有的证据/UI/negative-assertion 硬门一条不少，因此不构成绕过。代码变更后的重测
   义务由 `TESTED_RUNTIME_MISMATCH` / `RETEST_REQUIRED_AFTER_CHANGE` 独立把守。非确定性场景的
   抖动由 `STABILITY_SAMPLES_INSUFFICIENT` 把守，且 v0.8.1 起只看当前被测 HEAD 上的样本
   （见 §4b v0.8.1）。**历史**：fail 曾是粘性的，那时改完代码只能开新 run——这正是 §8e 要
   收拾的换目录洗账的源头。
   **旧实现是个语义陷阱**：`blocked` 排在 `fail` 之前、扫的还是全部 run 而非 root，于是记一条
   blocked = 该场景永久钉死、整轮报废；而 Stop hook 当时的文案恰恰是"做不到的项标 BLOCKED"，
   文案 + 实现的组合等于诱导代理毁掉自己正在跑的轮次（simple_harness r7/r9 实测）。
   **注意两个 BLOCKED 不是一回事**：流程层的"标记 BLOCKED 升级给用户"是写在报告里给人看的
   结论；`record-run --result blocked` 是机器事实。临时受阻请保持 NOT_RUN + 在证据里写明原因
   并升级给用户，不要用机器 blocked 当逃生口。
3. **证据分级**：截图、原始日志、命令回执、DB 记录是 primary；auditor 报告、delivery
   汇总是 derived。derived 只辅助审计，不能单独满足 AC/testcase。
   场景声明 `evidence_contract` 后，还须满足 producer/artifact/identity/time/business facts；
   统一结构与 metadata 格式见 `../references/evidence-audit-lifecycle.md`。
   Artifact 去重采用已有 `sha256` 的逻辑统计，不移动原文件：receipt 分别给出 evidence record、
   distinct artifact、distinct root run 与共享 hash；同一内容的多个路径不算多份独立 artifact。
4. **engine 终态 ≠ 业务成功**：positive-value 场景的 root run 业务终态为空/insufficient/
   partial → 场景只能 PARTIAL。
5. **冻结 oracle**：实现前 init 冻结 black-box testcase 逐文件 hash；任何 byte 变化默认
   FAIL；唯一例外是绑定 exact old/new + 用户消息 hash + scope/expiry 的批准 artifact。
6. **audit 冻结 facts_digest**：审计后代码、配置、testcase 或结果有任何变化，旧 auditor
   PASS 与 receipt 自动失效（AUDITOR_INPUT_STALE / RECEIPT_STALE）。
   JSON findings 会随 audit 原子入账；open/deferred P0/P1 是硬门。`resolve-audit-finding` 要求
   resolution、已存在 evidence ID，以及 `required_retest=true` 时导入后的 fresh root PASS；
   resolution 本身会令旧 audit stale。
7. **运行时身份按「被测内容」判定，不按提交身份**（schema 1.2.0 起）：`content_digest` =
   工作树全部 tracked + 未忽略 untracked 文件的逐文件内容 hash 与可执行位。
   `git add`/`git commit` 不改内容 → 指纹不变 → 门不拦；改一个字节 → `TESTED_RUNTIME_MISMATCH`。
   HEAD 与 dirty patch 仍记录，但只作展示与溯源。
   **为什么按内容而非提交身份**：原来按 HEAD+dirty 判定时，「测完 → 提交 → finalize」必然
   MISMATCH，而不提交又过不了提交态门，形成无出口的死结（由独立审计在真实仓库实测发现）。

   **排除范围在 init 时冻结，只认显式声明**：`exclusion_scope` = 当前 run-dir +
   manifest 的 `related_run_dirs`（拆 slice 时用来声明兄弟 run 目录）。声明项必须是**已存在的**
   `.../verification/<单层>` 目录，否则 init 直接拒绝（直接声明 `src` 这类路径会被挡下）。范围进账本、
   进 receipt digest、在 `report.md` 逐条显形；**事后往仓库里塞任何文件都不改变它**。
   指纹只对文件条目取，排除范围本身不参与 digest 计算（否则新开一个 slice 会把别的 slice 判红）。

   **为什么必须冻结（三次教训，都是独立审计实测打穿的）**：
   - 按「目录里有 `plan-test-run.json`」判定 → 在 `src/` 塞一个假账本，整个 src 从指纹里消失；
   - 按路径形态 `.../verification/<单层>` 判定 → 项目里真有 `src/verification/rules/` 业务目录时，
     它的代码被整体排除，audit 之后改实现、加后门仍拿到逐字相同的 receipt；
   - 按「文件名恰为记账物」+「含账本目录的 `artifacts/`」判定 → 把业务文件命名成 `manifest.json`，
     或事后 `mkdir -p src/verification/z/artifacts` 再塞一个空账本，照样藏住后门。

   **共同根因：判定输入来自被测者可写的工作树。** 只要排除范围是校验时现算的，被测者就能
   通过写文件影响它。冻结声明把它变成事前的、可见的、可审计的选择——想排除什么，必须在
   init 时说出来，并留在 receipt 里。

   **仍未消除的剩余面（如实标注）**：形态校验挡得住「声明 `src`」，挡不住「**先造出**一个
   `src/verification/lib/` 再声明它」——那样该目录的代码会合法地不进指纹，audit 之后改动
   不会被发现。缓解只有可见性：声明范围逐条列在 `report.md` 与 receipt digest 里，人一眼
   能看出排除了什么；但**范围内事后新增的文件不会出现在报告里**。审阅 receipt 时必须把
   `exclusion_scope` 当作重点看，而不是当作噪声跳过。

   **指纹覆盖什么、不覆盖什么（如实列出，不要按字面理解成"任何文件"）**：
   - 覆盖：tracked 文件 + 未被 .gitignore 忽略的 untracked 文件的**内容 hash 与可执行位**；
     文件新增、删除、改名同样体现为变化。
   - **不覆盖**：被 .gitignore 忽略的文件（构建产物、本地 `.env`、缓存）——它们不是交付内容，
     但**若你的运行行为依赖某个被忽略的文件，这个门照不出它的变化**；symlink 只指纹化
     目标路径字符串，不跟随读取目标内容。
   - 超大仓（文件数 > `CONTENT_DIGEST_FILE_LIMIT`，默认 20000）**退回 HEAD+dirty 旧口径**，
     init 会打印警告、`render` 的报告顶部会标注。注意：退回之后「测完→提交→finalize」的
     死结也一并回来，此时必须靠 `re-attest` 走收尾。

8c. **`retire`：被取代的历史 run 的唯一合法退场方式**，且必须有继任者。

   ```bash
   python "${CLAUDE_PLUGIN_ROOT}/skills/plan-test/scripts/plan_test_gate.py" retire --run-dir OLD \
     --reason "已被 slice-a/b 取代" --superseded-by NEW
   ```

   - `--superseded-by` **必填**：继任 run 必须是非 fixture、当前 SHIPPABLE、receipt 未失效、
     **在同一仓库内**、**acceptance 相同**、且**覆盖被退役 run 的全部 required 场景**，
     否则直接拒绝（exit 2）。**退役不是赦免，是把举证责任转移给另一个已通过的 run**——
     少了「覆盖」这一条，就成了拿一张无关的 receipt 背书（独立审计实测：用一个唯一场景是
     `Z-9` 的同仓 run 就能退役掉 `S-1` FAIL 的 run）。
   - 退役后账本仍如实是未闭环状态：`finalize --check-only` 照样 FAIL。它只影响一件事——
     Stop hook / CI 不再因这个已被取代的 run 阻断收尾。
   - 判定统一走 `retire-status --run-dir D`（exit 0 = 退役成立）；hook 与 CI **不得自行解读
     `retired` 字段**，且必须在 `finalize --check-only` **之后**才询问退役状态。
   - **为什么要这么绕**：无守卫的第一版 `retire` 本身就是一个新绕过——独立审计实测
     `retire --reason "这个先不做了"` 即可让一个 required 场景 FAIL 的 run 从门前消失；
     手写 `"retired": true` 也一样，因为当时 hook 把该判断放在 check-only 之前，
     `LEDGER_TAMPERED` 根本没机会打印。这与更早被堵掉的 `fixture_only` 是同一形态：
     **给账本加一个字段就让门消失**。任何新增的「豁免」都要先问一句：它会不会变成下一个这样的字段。
   - 确实要放弃一次验证而没有继任者 → 删除该 run 目录，或走 8d 的 `acknowledge`。

8d. **`acknowledge`：用户显式放弃一轮验证**（第二条出口，2026-08-09 加）。

   ```bash
   python "${CLAUDE_PLUGIN_ROOT}/skills/plan-test/scripts/plan_test_gate.py" acknowledge --run-dir OLD \
     --reason "<用户为什么放弃>" --approval-hash <用户批准原话的 sha256>
   ```

   - **为什么需要它**：`retire` 要求继任轮**已经** SHIPPABLE。而"继任轮正在跑"恰恰是最需要
     安静的阶段——simple_harness 实测：7 个历史 run-dir 每回合被完整刷一遍诊断，它们唯一的
     出口却要等新轮跑完，新轮跑完的成本又被这些噪音抬高，**历史轮越多，跑完新轮越贵**。
     这与 hook「保守、不误伤」的初衷相反。
   - 守卫：必须绑定**用户批准消息原文的 SHA-256**（与 `record-approval` 同口径——放弃一轮
     验证是用户的决定，不是代理的自决）；写入走 integrity 链（op=acknowledge），手写
     `"acknowledged": true` 被 `ack-status` 判无效；已有 receipt 的 run 不许用它注销
     （那是 `invalidate` 的事）；**不可撤销**。
   - **放弃 ≠ 通过**：该 run 从此报 `RUN_ABANDONED`（error），永远拿不到 receipt，
     因而也不可能被 `retire --superseded-by` 认成别人的继任 run。`render` 顶部打横幅。
   - 判定统一走 `ack-status --run-dir D`（exit 0 = 成立）；hook 与 CI 不得自行解读字段。
   - 局限如实说明：hash 由代理计算，它挡的是"顺手放弃"，不是存心伪造——与
     `record-approval` 完全同源的局限，真正的锚点仍在 CI。

8e. **`SIBLING_RUN_UNRESOLVED`：换目录洗账本**（2026-08-28 加）。

   - **问题（当时）**：`fail` 是粘性的——一条 root fail 记进去，这个 run-dir 就永远拿不到 receipt，
     代理唯一能往前走的动作是新建 `run-00N+1`，轮换是**设计内的正路**。问题在于配套的
     `retire --superseded-by`（把举证责任转移给继任轮）**没有任何东西检查它做没做**。
     （W4-15 起 fail 非粘性、v0.8.1 起 FLAKY 只看当前 HEAD，轮换不再是必经之路；本门仍保留，
     因为历史上开出来的兄弟轮仍要交代。）
   - **实测数据**（18 本真实账本 + 8 处轮换现场）：5 次轮换里 4 次没挂账；`retire` /
     `acknowledge` 全局使用次数为 **0**；被丢弃的账本里躺着 **75 条测试事实、142 份证据、
     16 条 root fail**——比进了 receipt 的 65 条事实还多。两张历史 SHIPPABLE receipt
     （`s1-relay-foundation/run-006`、`s1-lan-relay/run-003`）都是在旁边躺着红账本的情况下
     发出的。**receipt 没撒谎，但它把失败史藏起来了。**
   - **判据是「必测场景集是否相交」，不是「是否同一个目录」**。这一条是被真实反例逼出来的：
     `plans/2026-08-18-memory-sdk-integration/verification/` 下并排躺着 run-1..run-4，分别测
     AC-1..4 / AC-5..8 / AC-9..11 / AC-12..14，用四份不同 manifest——那是四个不同 slice
     各测各的，互不欠账。只按目录判会把它们全判成互相欠账，谁都发不出 receipt。按场景集判，
     8 处轮换现场里 7 处判为真轮换、这 1 处正确放行。
   - 也**不能**用 acceptance 哈希判：`s1-relay-foundation` 那 6 轮里 acceptance.md 被改过两次
     （3 个不同哈希）而场景集 6 轮完全一致——用哈希判，改一下验收文档就溜过去了。
   - 只算**有 run fact 的**兄弟：纯 init 的空账本不藏失败史（`plan-iteration-*` 这类挑战循环
     账本同样因零 run fact 天然出局）。`fixture_only` 两侧都豁免。
   - 兄弟轮的 `retired` / `acknowledged` 必须**链里真有那一笔 op** 才算数——兄弟轮的
     integrity 链不由本 run 的 validate 核对，只看字段的话"手加一行 `retired: true`"
     就是绕过本门最省事的路径。
   - **时序死锁与解法**：若 `retire` 仍要求继任者「已有 receipt」，就会死锁——继任轮因兄弟轮
     未了结拿不到 receipt，兄弟轮又因继任轮没有 receipt 而退役不掉。故 `retire` 改为接受
     **全绿但尚未盖章**的继任者（`allow_pending`），放宽的只是"盖没盖章"这一条：继任者仍须
     通过除本诊断外的全部阻塞门、state 仍须算到 SHIPPABLE、仍须同仓非 fixture、且自己不能是
     已退役/已放弃的轮次（否则退役链可以首尾相接）。
   - 与之配套：`retire-status` 在这个中间态输出 **`PENDING` 且 exit 1**。若 PENDING 也判
     exit 0，就多出一条静默出口——造个全绿继任者、把红账本退役进去、然后永远不 finalize，
     红账本从此对 hook 隐身而交付从未发生。真要放弃请走 `acknowledge`（需用户批准原话 hash）。
   - **合法收尾顺序**：兄弟轮红 → 本轮做到全绿 → `retire` 兄弟轮（指向本轮）→ 本轮
     `finalize` 盖章 → 兄弟轮的 `retire-status` 此时才转 VALID。注意 `retire` 会改写兄弟轮
     账本，若它不在本轮 init 冻结的 `related_run_dirs` 里，本轮随后会报
     `TESTED_RUNTIME_MISMATCH`，需要 `re-attest`。

8b. **`re-attest`：收尾期改动的唯一合法出口**。attestation 原本只在 init 写一次，
   而收尾流程强制要求文档回写与状态同步——于是任何合规执行都会把 run 永久锁死，
   唯一出路 `init --force` 会清空 runs/evidence/auditor（第二轮独立审计实测）。
   现在：

   ```bash
   python "${CLAUDE_PLUGIN_ROOT}/skills/plan-test/scripts/plan_test_gate.py" re-attest --run-dir D --reason "文档回写"
   ```

   - 变更集**全部**命中文档白名单 → 记 `doc-only`，既有测试结论继续有效。白名单默认只认
     叙述性文档（`README*`/`CHANGELOG*`/`docs/**`/`ARCHITECTURE*`/`*.rst`），且
     `prompts/`、`skills/`、`config/`、`.claude/`、`hooks/` 前缀与 `requirements.txt`、
     `package.json`、`Dockerfile` 等**永远算行为文本**（改依赖版本、改系统提示都不是「改文档」）。
     manifest 的 `doc_only_globs` **只能收窄不能放宽**（最终判定 = 默认 ∩ 自定义）——
     manifest 由被测者自写，自报即生效的开关等于把门交回被测者；
   - 只要有一个非文档文件变了 → 记 `behavioral`，validator 要求**受影响的 required 场景
     都有一次发生在该次 attestation 之后的 root PASS**，否则 `RETEST_REQUIRED_AFTER_CHANGE`。
     **影响范围按 `scenario.impact_paths` 映射缩小**（1.3.0 起，DeskPet 复盘 P1：改任意
     文件即全场景 stale 是墙钟浪费最大单点）：manifest 里每个场景可声明关联代码路径 glob
     （如 `backend/**`），只有命中变更的场景 stale，其余场景沿用既有结论并在 re-attest
     输出里解释原因。**fail-closed**：映射由被测者自写，是新的绕过面——没有任何场景声明
     映射、变更清单被截断、或任一非文档变更未被任何映射覆盖，一律退回全量复测；未声明
     映射的场景永远算受影响。映射随场景在 init 冻结，事后改映射即 `LEDGER_TAMPERED`。
   - doc-only **由路径规则机器判定，不接受调用者自报**；"我这次只改了文档"不再是一句话的事。
   - 判定用账本的追加序号锚定，不用时钟（`now_iso()` 精度到秒，同秒重跑会被误判成已重测）。
8. **fixture_only**：跳过 git 校验的 run 永远标 FIXTURE-ONLY，receipt/report 不可作为
   真实交付证据。
9. **"100%" 只表示某个明确 scope 的 required gates 全绿**，不表示未来绝无缺陷。
10. **时间是一等证据，且 1.3.0 起是硬门**（DeskPet 复盘：12h24m 真实执行四本账 timing
    全 0，phase 文档写的"必须"只是 advisory——文档说必须而机器不拦，规则权威一起塌）：
    机器活动用 `record-timing --exec -- <cmd>` 包裹执行——wall clock 记 RFC 3339 UTC
    起止、monotonic clock 实测 `elapsed_ms`，调用者不可覆写实测值；真人 E2E 等外部活动
    用 `--declared-start/--declared-end` 申报，CLI 强制 `measured:false`，report 单列
    "declared time"、不混入实测聚合。连续工作每 90–120 分钟跑一次 `checkpoint`；
    阶段进出用 `phase-start`/`phase-end`（finalize 查配对，`PHASE_UNPAIRED`）。
    **真实 run**（非 fixture）活动跨度超 30 分钟而 timing 覆盖不足 20% →
    `TIMING_MISSING`（error）；记账覆盖区间合并后仍有超 120 分钟的空洞 →
    `TIMING_GAP`（error）。漏记时段的合法出路是申报模式补记（user_wait/provider_wait
    等，低信任单列），不是把门关掉。**这是流程门不是防伪门**：申报值本就是自陈，
    它保证"有账"，不保证"账真"。render 的报告按七类 activity_class 分解耗时。
11. **legacy fixture 溯源**：`provenance.json` 的 `source_sha256` 未采集（null）时，
    fixture 只能作为合成 dogfood 运行，输出强制标 `PROVENANCE: UNVERIFIED`；
    不得为让历史变绿而修改历史证据文件。
12. **适用性判定是 fact，不是口头判断**（schema 1.2.0 起）：`input_sensitive` /
    `llm_payload_driven` / `stateful_init` 三维必须在 manifest 里显式声明
    `{value, rationale(≥10 字), decided_by(agent|user)}`，由 init 冻结进账本、
    进 receipt digest、进 render 报告。判「不适用」合法且不拦截——但理由留痕、可追责；
    判「适用」则场景矩阵必须真的兑现：
    - `input_sensitive=true` → required 场景的 `input_class` 去重数 ≥
      `thresholds.min_distinct_input_classes`（默认 3），且至少一条 `gate_type=positive-value`；
    - `llm_payload_driven=true` → 至少一条 required 场景 `min_root_runs ≥ 2`；
    - `stateful_init=true` → 矩阵含 `cold_start: true` 场景。

    **病根**：这三个判定此前只写在 config.md 里由代理口头自决且不留痕——判一句
    「这是确定性 UI」，场景矩阵、正向价值门、随机采样、冷启动四道门就合法消失，
    validator 完全不知道发生过这件事。现在它至少是一条被冻结、被展示、可被审计的记录。
13. **账本只能经 CLI 写**：每次写入追加 integrity 链条目
    （`chain_n = sha256(chain_{n-1} + op + facts_digest_n)`）；validator 重算全链并核对
    末条 `facts_digest` 是否等于当前 fact 快照。手工改一行 `runs[].result` 即
    `LEDGER_TAMPERED`。**写入前先验链**：链一旦对不上，任何后续 CLI 写入都被拒绝（exit 2）——
    否则篡改检测是一次性的：改完再敲一条无害命令（`checkpoint` 就行），新条目会拿被篡改的
    快照重新盖章，痕迹永久消失并照常拿到有效 receipt（独立审计实测，成本只是「改一行 +
    多敲一条命令」）。
    **它能做什么、不能做什么（第九轮独立审计实测后如实改写，此前两版估计都被证伪）**：
    validator 只把**末条** `facts_digest` 与当前快照对账，中间条目从不与真实状态比对。
    因此改一条事实之后，只需重算末条 `facts_digest`、末条 `chain` 与 `integrity.chain`——
    **四行、O(1)，与链长无关**。链首必须是 `init`、链长下界这些结构不变量只封住了
    「把链压短」和「删链重建」两种最省事的形态，**都不构成防篡改**。
    早先文档写的「必须重算整条链」「必须逐条重放」都是被证伪的乐观估计。

    **准确的定位**：链只能发现「改了文件但没同步链」的编辑——顺手改、脚本误写、合并冲突残留。
    它发现不了任何愿意多写四行的对手，这是**本地无密钥哈希链的固有上限**：文件与校验逻辑
    都在被测者手里，怎么设计都一样。**要真正防篡改，锚点必须在被测者写不到的地方**——
    CI 从 git 历史重算并比对 receipt，或把 receipt 推到 append-only 的远端存储。
    只启用 Stop hook 而不接 CI 时，请按「链只防手滑」来理解它，不要按「防伪造」来宣传。

    **链长下界的误报风险，以及为什么它由测试而不是补丁来守（2026-08-28 加）**：
    `expected_chain_length` 是一份**手工维护的枚举**——它假设"一次 CLI 写入 = 一条事实"。
    任何在单次写入里追加两条事实的新命令都会打破这个下界，让**下一条**命令报
    `LEDGER_TAMPERED`。这不是假想：`record-run --exec`（一次写入同时追加 run 与它抓到的
    执行日志）2026-08-19 上线，给它补的折扣 2026-08-24 才上线，中间 5 天真实日志里
    5 次 `LEDGER_TAMPERED` 全部由此产生，其中一次连跑 17 次 `--exec`、缺口正好 16。

    **同一根病的第二次发作（2026-09-02 实测，v0.8.1 修）**：折扣按"run 在账本里的位置 ==
    日志文件序号"配对，而序号取自**开跑前**的账本快照。后台 `--exec` 跑 10 分钟全量回归
    期间别人先入账一条 run，位置就错开一位，配对失败 → 下界多算 1 → `LEDGER_TAMPERED`。
    s5b 的 r1/r2 两本账都这么死的，代理判成"并发写"并删目录重开（100+ 条事实作废）。
    修法两条：①序号改在 `_append` 的锁内按账本当前长度定，日志先以 unrecorded 名落盘再改名，
    两条同场景后台 `--exec` 也不再互相覆盖日志；②`expected_chain_length` 改按场景计数配对——
    每场景折扣 min(exec run 数, 同形态 exec 日志数)，与位置无关，存量错位账本自愈。配对只看
    路径形态 `EXEC_LOG_RE`（写读两端共用一份定义），**不看 producer_type**：该戳 08-24 才加，
    08-19～08-24 的存量 exec 证据没有它。折扣上限仍是 exec run 数，手工 attach 一条同形态的
    日志最多让下界松 1。

    症状为什么必须当回事：`LEDGER_TAMPERED` 是阻塞级、**没有任何修复命令**（有的话就等于
    "重算链即洗白"），账本一旦被误判就是死的，代理唯一的出路是换 run-dir 重开——而那正是
    §5.8e 的 `SIBLING_RUN_UNRESOLVED` 要堵的行为。**一个门的误报直接喂给另一个门。**

    因此约束写在测试里而不是文档里：`ChainLengthInvariantTestCase` 逐条执行全部写入命令，
    断言 Δ(expected_chain_length) ≤ Δ(链长)。**新增写入命令时必须在那份清单里补一行**；
    漏补的代价是让下一个用户的账本报废，而不是让 CI 变红。
14. **审计产物 > 命令行**：`audit --verdict` 与 `auditor-output`（JSON 的 `verdict`
    字段或文末 `VERDICT: PASS/FAIL` 行）不一致 → `audit` 直接拒绝（exit 2），
    事后不一致 → `AUDITOR_VERDICT_MISMATCH`。`--engine` 必填；与 `executor_engine`
    相同或标 unknown → advisory `AUDITOR_INDEPENDENCE_UNVERIFIED`（曝光而非拦截：
    审计者与实现者是否真的独立，机器证明不了，只能让它在报告里显形）。

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

## 6b. 本门禁**堵不住**什么（如实标注，别把它当保险箱）

validator 能重算的只有"已入账事实之间的自洽性"，事实本身是否真的发生过，它无从判断：

- **证据可伪造**：`attach-evidence` 只校验文件存在与 hash，不看内容来源。代理自己造一张
  截图、写一行假日志，门禁看不出来。`--ui-action` 只是一个 bool。
- **result 是自陈**：`record-run --result pass` 的 engine/业务终态是自由文本。
  缓解（1.4.0 起）：脚本测试改用 `record-run --exec -- <cmd>`——gate 亲自执行命令，
  result 由 exit code 决定（0=pass 非 0=fail，与 `--result` 互斥），stdout/stderr 落盘
  `artifacts/exec-*.log` 自动记为 primary 证据，被包裹命令的 exit code 如实透传。
  一次执行扇出成 N 条自报 pass 时，required 场景缺独立 primary 证据会被
  `RUN_ATTESTATION_FANOUT` 拦截；每场景有独立断言证据则放行。
- **oracle 由被测者定义**：场景全部来自代理自写的 manifest。**漏写一个风险场景，
  门禁根本不知道它存在**——这是本协议最大的剩余缺口，适用性判定（§5.12）只覆盖了
  其中"条件门被口头判掉"这一类。
- **不跑脚本就没有门**：canonical command 是否被调用，取决于流程被遵守。要真正闭合，
  必须在 harness 侧强制（见 `hooks/README.md` 的 Stop hook 与 CI 片段），
  单靠 Markdown 里写"必须跑"不构成强制。

因此准确的说法是：**它对"已入账事实之间的自洽性"是真门，对"事实是否发生"是高成本的自觉提醒。**
凡是宣称它能防住上面四类的说法，都是过度承诺。

## 6c. refusal log（s1a：拒绝也是事实）

每次 `die()` 向 `$PLAN_TEST_REFUSAL_HOME/refusals.jsonl`（默认 `~/.plan-test/`）追加一条
**原始**记录：`at / cwd / cmd / code / run_dir / detail` 六字段，原文不加工。`stats` 末尾
按码/按命令计数（零账本时也输出——"有拒绝、无账本"正是 init 被拒的形态）。
动机：run log 实证 56% 的测试执行因"换 run-dir 重来"作废，而 `die()` 160 处调用点
一处都不留痕，系统看不见自己在拒绝什么（`AUDIT-2026-08-28-gate-authority.md`）。

**落点纪律**：绝不写进任何 git 仓库——仓库内任何落点都会进 `repo_content_digest`，
一次拒绝就可能把同仓其他 run 打成 `TESTED_RUNTIME_MISMATCH`（rev1/rev2 两轮实测）。
默认路径若竟落在某 git 仓库内（`$HOME` 是 dotfiles 仓库），**跳过写入**；
显式设 `PLAN_TEST_REFUSAL_HOME` 则不设防，责任归操作者。

**覆盖面（实测，2026-08-28）**：记录 = `die()` 被调用。四类记不到，如实列出：
1. `parse_args` 之前的 die——当前 **0 处**（spike 实测），防线保留；
2. 无 die 可达路径的子命令（如 `print-schema`，rc 恒 0）——无失败可记属正常；
3. argparse "invalid choice"（敲错子命令名）——不经过 `die()`，归 s5 的 `status`；
4. 不经 `die()` 的裸异常（实测例：`LedgerLock` 对**不存在**的 run-dir 抛
   `FileNotFoundError` traceback、rc=1——与"存在但空"的 die rc=2 是两条路径）。
   这类本身是待修的粗糙面，修法是让它们走 die，而不是让 refusal 去兜 traceback。

**已知局限（别当保险箱，同 §6b 的精神）**：
- 记录含本机路径**明文**；文件不进 git、不出机器。跨机器分析等 s1c 的导出+脱敏。
- "记录了" ≠ "进程失败了"：全仓唯一吞 `SystemExit` 的 `cmd_stats` 内部的 die
  会留下记录而进程 rc=0。做配对分析（s1b）须知此口径。
- 可被手工删改**无检测**——它是诊断数据不是交付事实；防篡改若需要归 s3 的
  decision 原语，不要回头给它加链。
- 单文件 512 KB，超限原子地丢最旧一半（诊断数据不得阻塞交付）。
- 测试隔离：套件经 `refusal_guard.py` 把写入引到 tmpdir，并由
  `test_zz_refusal_guard.py` 在字母序最后对账真实账本基线。

## 7. 自测

```bash
python3 -m unittest discover -s skills/plan-test/scripts -p 'test*.py'
```

使用 discovery 避免新增测试文件未进入固定命令；测试数量随能力增长，不在文档中硬编码。

覆盖：状态矛盾 FAIL、required NOT_RUN、证据缺失/hash 不符、循环证据、frozen oracle
变异、audit 后 stale、receipt 幂等、适用性未声明/理由缺失/判「适用」未兑现矩阵、
账本手改与链条目缺失、审计产物与命令行改判冲突、自审自判 advisory 曝光、
Companion 历史三冲突 dogfood
（REQUIRED_SCENARIO_NOT_RUN + STATUS_CONFLICT + DELIVERY_VERDICT_CONTRADICTS_LEDGER）、
以及多条证据完整的 PASS 路径（防 gate 只会拒绝）。
CI/self-test 用同一 canonical finalize 路径重跑，不另写一套判断。
