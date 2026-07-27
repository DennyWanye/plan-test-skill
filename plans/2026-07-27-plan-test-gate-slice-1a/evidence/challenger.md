# Slice 1A（delta）plan challenger 审计
> 审计者：独立子代理（与 plan 作者不同会话）；日期 2026-07-27；基线 HEAD 75ce2b4

审计方法：全文细读 acceptance.md / plan.md / fixture-contract.md；逐行对照
`skills/plan-test/scripts/plan_test_gate.py`（939 行）、`gate/PROTOCOL.md`、
`schemas/plan-test-run.schema.json`、`scripts/test_plan_test_gate.py`；实际运行自测
（23 用例，OK）。

## 致命问题

- **F1：排序契约三方互相矛盾，1B-delta 一实现必炸。**
  (a) plan.md §3 声称其类别固定序"与 PROTOCOL.md §4 表格顺序一致"——**不实**。
  PROTOCOL.md §4 的表序是 SCHEMA_INVALID → REQUIRED_SCENARIO_NOT_RUN →
  **STATUS_CONFLICT → DELIVERY_VERDICT_CONTRADICTS_LEDGER**（第 3、4 位）→
  EVIDENCE_MISSING → … → RECEIPT_STALE → RISK_CLOSURE_MISSING → …；而 plan §3 列出的
  序（UI_EVIDENCE_MISSING/RUN_CREATION_UNVERIFIED 在第 3、4 位，STATUS_CONFLICT/
  DELIVERY 在第 11、12 位）实际上是 `plan_test_gate.py` `validate()` 的**实现发射顺序**，
  与 PROTOCOL §4 完全不同。两个"权威顺序"到底哪个是冻结契约？plan 把两者说成同一个。
  (b) fixture-contract.md §3.3 冻结的 expected-diagnostics.txt 序列
  （REQUIRED → STATUS_CONFLICT → DELIVERY → **EVIDENCE_DEPENDENCY_CYCLE** →
  RELEASE_UNIT_TOO_LARGE）在 plan §3 的全局序下**不可能出现**：plan §3 中
  EVIDENCE_DEPENDENCY_CYCLE（第 7 位）排在 STATUS_CONFLICT（第 11 位）**之前**。
  该文件要求逐字节比对，冻结的期望文件与冻结的排序规则互斥。
  (c) plan §3 末句称 Companion 期望序列"在此全局序下天然成立"——只在**相对序**意义上
  成立；在 plan §3 序下三个码并**不连续**（EVIDENCE_DEPENDENCY_CYCLE 必然插在
  REQUIRED_SCENARIO_NOT_RUN 与 STATUS_CONFLICT 之间），与 §3.3 展示的连续序列矛盾。
  结论：必须三选一收敛（PROTOCOL §4 序 / plan §3 序 / 重写 §3.3），当前三个文档互相打架。
- **F2：pass-minimal 的期望状态在冻结的回放路径下不可达。** fixture-contract §1 冻结
  回放器"最后跑 `finalize --check-only`"，§2 冻结 expected-state.txt =
  `STATE: SHIPPABLE`。但实现 `compute_state()`（plan_test_gate.py:537）规定
  SHIPPABLE 仅在 `mode in ("full", "render")` 时可达——check-only 模式封顶
  **VALIDATED**（PROTOCOL §3 也是这么写的："VALIDATED：check-only 无诊断"）。
  两条冻结条款互斥：要么回放器对 PASS fixture 跑 full finalize（fixture_only 允许），
  要么期望状态改为 VALIDATED。照现契约实现，用例第一次跑就 FAIL。

## 事实性错误（plan 声称与仓库实现不符处）

- **E1（对应 F1a）**：plan.md §3 "与 PROTOCOL.md §4 表格顺序一致"为假，见上。
- **E2**：plan.md §5 回滚："旧 ledger（无 timing）与新 ledger（有 timing）都被 1.0.x
  validator 接受（**未知段忽略 + 警告**）"。核对 `structural_check()`
  （plan_test_gate.py:212-239）：只校验必需字段与枚举，对未知顶层段**静默忽略**，
  整个代码库不存在任何"未知段警告"机制。"忽略"属实，"警告"是无中生有。
- **E3**：plan.md §1.1 把版本策略（"validator 接受同 major 的旧 minor（缺段视为空），
  跨 major 须显式 migrate"）写成现行为。现实现对 `schema_version` 的**取值完全不检查**
  （structural_check 只要求它是 string）——任何 minor、任何 major、任何乱写的版本号都
  静默接受。该策略是待实现项，但 §4 实施步骤 1–5 **没有任何一步**实现版本接受检查或
  未知段警告，政策无 owner（另见 M2）。
- **E4**：acceptance.md AC-1 的验证条款要求 plan.md timing 表"逐字段有
  producer/consumer/**authority 三列**"。plan.md §2.3 实际表列是
  字段 / producer / 调用者可写? / authority——**没有 consumer 列**（consumer 只在 §1.1
  笼统提过）；且 `measured`、`evidence_ids` 两个 §2.1 字段在表中**没有对应行**。
  按 AC-1 自己的验证方法核对，AC-1 不通过。

## 次要问题与建议

- **M1（溯源铁律无机器强制）**：fixture-contract §3.1 的铁律（sha256 为 null 时输出必须
  标 `PROVENANCE: UNVERIFIED`）没有指定 enforcement 组件——validator 不读
  provenance.json，回放器归 1B-delta 但其检查项清单（plan §4 步骤 3）未包含
  "provenance null → 强制 UNVERIFIED 标注"用例。当前铁律靠自觉。建议：1B-delta 明确
  由回放器/render 校验，并加一条负向用例（伪填 hash 无 captured_at/captured_on → 拒绝）。
- **M2（模糊收尾无 owner）**：(a) TIMING_GAP 是否升级为阻塞"待实际使用数据后再定"
  （plan §2.4、§6）——无归属 slice，未进 fixture-contract §4 backlog 表；(b) E3 所述
  版本接受检查/未知段警告的实现无归属；建议都显式登记 owner + slice。
- **M3（回滚隐含假设未声明）**：receipt 的 `content_digest` identity 包含
  `validator_version`（build_receipt，plan_test_gate.py:558）。若 1B-delta 按惯例升
  VALIDATOR_VERSION，revert 后 render 重算 digest 必不同 → `RECEIPT_STALE`，与 plan §5
  "不会让已生成的 receipt 失效"直接冲突。plan 需声明"1B-delta 不改 VALIDATOR_VERSION"
  或修正回滚承诺。
- **M4（措辞自相矛盾）**：plan §2.3 规则"elapsed_ms 不允许由两个 wall-clock 相减得出"
  ——但 declared 模式（§2.4 第二形态）只收 --declared-start/--declared-end，其
  elapsed_ms 必然由两个 wall-clock 相减得出。该禁令应限定于 measured:true 条目。
- **M5（计数偏差）**：plan §0 对账表沿用"canonical CLI 八命令"。实现是 **9 个**子命令
  （init/record-run/attach-evidence/declare-status/set-delivery/audit/finalize/render/
  invalidate）；括号补注"另有 declare-status/set-delivery"仍对不上账。小事，但对账表
  自称对账，数字应当准。
- **M6（AC-7 循环激励）**：把"challenger 末行 VERDICT: PASS"写进验收标准，等于把审计
  结论预设为验收目标，对审计独立性有结构性压力。建议改为"存在 challenger 审计且其
  致命/事实性发现已全部闭环"。
- **M7（§3.3 潜在遗漏）**：fail-companion fixture 若把两份 derived 证据挂到任何 PASS
  场景（如 S-1），会额外触发 DERIVED_EVIDENCE_ONLY；§3.2 未禁止 scenario_id 挂载，
  §3.3 期望清单未含该码。1B 落盘时需明确 derived 证据不带 scenario_id（现有合成
  dogfood 测试正是如此），并写进 §3.2。

## 逐项核对结论（对应 8 个质疑点）

1. **对账诚实性：基本属实。** 逐项核实：schema ✅（plan-test-run.schema.json 存在且含
   全部所述段）；PROTOCOL.md §1 run-dir 契约 ✅；CLI 命令 ✅（但计 9 不计 8，见 M5）；
   锁（O_CREAT|O_EXCL + 退避）/原子写（tempfile+os.replace）/CAS（REVISION_CONFLICT）✅；
   receipt 幂等/stale/invalidate ✅；23 用例实测全绿 ✅；"dogfood 为合成数据"的自认属实
   （test_companion_history_dogfood_three_conflicts 全部数据由测试代码构造，且只
   assertIn 不断言顺序——plan 称"确定性来自实现顺序、未成文"甚至偏保守）。未见夸大。
2. **timing contract 完整性：字段覆盖齐全，表格不合 AC-1 自订标准。** handoff §11 各
   字段（phase/slice/task、command/tool、RFC3339 起止、monotonic elapsed_ms、
   activity_class 七类、wait_reason、retry/abort、test_count、runtime_identity、
   evidence 经 evidence_ids→evidence.sha256）在 §2.1 均有定义；declared 模式边界总体
   诚实（强制 measured:false、不计入 measured active、report 分列、§6 明认"无法机器
   强制"）。但 §2.3 表缺 consumer 列、缺 measured/evidence_ids 行（E4），且 M4 措辞
   自相矛盾。**部分不达标。**
3. **排序契约可实现性：自相矛盾，不可同时满足。** 见 F1。三码相对序在两种候选序下都
   成立，但逐字节 expected 文件只在 PROTOCOL §4 序下成立，而 plan §3 冻结的是另一个序
   并谎称与 PROTOCOL 一致。**FAIL。**
4. **溯源契约诚实性：区分诚实，强制缺位。** "合成 dogfood（现状）"与"带溯源
   （1D-delta BLOCKED）"在三个文档一致如实标注；null hash 铁律、"不许伪造"、
   "不改历史证据"均明文；未发现任何伪称已带溯源执行之处。但铁律 enforcement 无机器
   落点（M1），绕过只需"不自觉"。**方向 PASS，留洞。**
5. **范围纪律：干净。** 无实现代码混入；§4 全部标注 post-review；record-timing/
   checkpoint/排序实现/fixture 落盘明确归 1B-delta，hash 采集/Windows 验证归 1D-delta，
   2A/2B/3A–3C 明确排除；不 push、不碰 DeskPet。规划文档冻结契约不等于实现。**PASS。**
6. **模糊收尾：存在两处无 owner 的"到时候再看"。** TIMING_GAP 阻塞化决策、schema 版本
   接受策略的实现均无归属（M2/E3）。其余待定项（精确文案 1B 冻结、Windows 1D、hash
   1D BLOCKED）归属清楚。**部分不达标。**
7. **回滚方案：与实现不符。** "未知段忽略 + 警告"中"警告"失实（E2）；所依赖的版本
   策略未实现且无实现步骤（E3）；receipt 不失效的承诺隐含 VALIDATOR_VERSION 不变的
   未声明假设（M3）。"receipt digest 只绑定 ledger 实际内容"这半句经核对 build_receipt
   属实，但整体回滚叙述失实。**FAIL。**
8. **验收可核验性：大体可核验，两条有病。** AC-2/3/4/5/6/8 的验证均能对着具体文件
   章节逐条核对（本审计即照此执行）；AC-5 的 13 问在 plan §1 逐条有结论与归属。但
   AC-1 的验证条款与 plan 实文不符（E4——按其字面核对必 FAIL），AC-7 把审计结论写成
   验收目标（M6）。**部分不达标。**

## 结论

对账与溯源部分的诚实度良好，范围纪律干净；但排序契约三方互斥（F1）、PASS fixture
期望状态在冻结回放路径下不可达（F2）是会让 1B-delta 首次实现即失败的硬伤，加上
回滚叙述与实现不符（E2/E3）、AC-1 按自订标准核对不过（E4），致命问题与事实性错误
均未闭环。修复方向明确：统一排序权威（建议以 PROTOCOL §4 为准并同步 plan §3 与
§3.3）、修正 pass-minimal 期望状态或回放路径、删掉"+警告"或补实现步骤、补齐 §2.3
consumer 列与缺失行。闭环后可复审。

（第 1 轮结论：FAIL——已被第 2 轮复审取代，见下节。）

## 复审（第 2 轮）
> 增量复审：只核第 1 轮缺口与新改动；日期 2026-07-27；基线不变 HEAD 75ce2b4。
> 方法：全文重读修订后的 plan.md / fixture-contract.md，关键声明再次对照
> plan_test_gate.py（compute_state:520-539、structural_check:212-239、
> build_receipt:547-573）核验。

### 第 1 轮致命问题核销

- **F1（排序契约三方互斥）→ 已闭环。** plan.md §3 现为唯一权威 canonical 序
  （20 类编号列表，TIMING_GAP 恒排最后），并**明文承认**它既非当前 `validate()`
  发射顺序、也非当前 PROTOCOL §4 表序——消除了第 1 轮"谎称一致"的失实。
  STATUS_CONFLICT(3)/DELIVERY(4) 前移后，fixture-contract §3.3 期望序列
  REQUIRED(2) → STATUS_CONFLICT(3) → DELIVERY(4) → CYCLE(9) → RELEASE(15)
  在全局序下严格递增，逐行核对属实；§3 自带自洽性核对段。三处契约收敛为一个序。
- **F2（pass-minimal SHIPPABLE 不可达）→ 已闭环。** fixture-contract §1 现规定终结
  命令由 steps.jsonl 末行显式声明、回放器不隐含追加，并正确引用了
  `compute_state()` 的实际行为（check-only 封顶 VALIDATED，仅 full/render 可达
  SHIPPABLE——与 plan_test_gate.py:537 一致）；§2 明确 pass-minimal 以正式
  `finalize` 终结、fail fixture 以 `--check-only` 终结。核对实现：fixture_only=true
  下正式 finalize 跳过 git 校验、audit PASS 后无后续 fact 变更，SHIPPABLE 可达。

### 第 1 轮事实性错误核销

- **E1** 与 F1 同源，随 F1 闭环。
- **E2（"未知段忽略＋警告"失实）→ 已闭环。** §5 回滚现表述为"当前 structural_check
  对未知段静默忽略（无警告，见 §1.1 的实现缺口说明）"——与实现相符，且
  "ledger 内容 digest 不变、receipt 的 ledger_sha256 仍匹配"经 build_receipt 核对属实。
- **E3（版本策略冒充现状、无 owner）→ 已闭环。** §1.1 现明确标注"目标态，非现状"、
  如实陈述当前 validator 对 schema_version 取值不检查，校验实现列入 §4 步骤 2 并有
  owner（1B-delta 执行者）。
- **E4（AC-1 三列不齐、字段缺行）→ 已闭环。** §2.3 表现为五列（含 consumer），并补齐
  `measured`（CLI 按模式强制、不可由参数指定——好设计）、`evidence_ids`（CLI 校验
  存在性）、`elapsed_ms(measured=false)`（CLI 由申报起止相减派生）三行；§2.1 全部
  字段均有对应行。按 AC-1 验证条款逐字段核对通过。

### 第 1 轮次要项核销（coordinator 声称修复的部分）

- **M1（溯源铁律无机器强制）→ 已闭环。** fixture-contract §3.1 新增机器强制落点：
  回放器遇任一 null hash 打印并**断言** `PROVENANCE: UNVERIFIED`（1B-delta），全非
  null 时 1D importer 复核 hash 与 normalized representation 对应关系，伪 hash 在复核
  时暴露。绕过路径已堵。
- **M2（TIMING_GAP 升级无 owner）→ 已闭环。** §6 定为 1D-delta 收尾时汇总首批真实
  run 的 gap 分布交用户拍板，此前不得擅自升级。
- **M3（VALIDATOR_VERSION 隐含假设）→ 已闭环。** §5 新增联动段：明确 1B-delta 会
  bump 版本号、revert 后 receipt 因 content_digest 复算改变而 RECEIPT_STALE 是设计
  使然，需对活跃 run 重新 finalize。与 receipt identity 含 validator_version 的实现
  一致，且语义合理（validator 变了旧判定不应存续）。
- **M4（elapsed_ms 措辞自相矛盾）→ 已闭环。** §2.3 规则现限定铁律只约束
  measured=true；measured=false 的差值语义与"靠标记曝光而非禁止"的边界表述诚实。

### 残留问题（均为次要，不阻塞）

- plan §3 说 PROTOCOL §4 重排"列入 §4 实施步骤 2/5"，但按步骤实文，PROTOCOL.md 的
  改动落在步骤 1（"PROTOCOL.md 增补 timing/排序/TIMING_GAP 契约"），步骤 5 是 phase
  文档接线——交叉引用应为"步骤 1/2"。工作本身有归属，指针不准，1 处文字修正即可。
- pass-minimal 期望 SHIPPABLE，但 §2 内容清单未列 manifest 须含
  source_request/acceptance/baseline.head——按 compute_state，缺任一则状态停在
  DRAFT/ACCEPTED，SHIPPABLE 不可达。1B 落盘者会被期望文件逼着补上，但契约按理应
  写全；建议 §2 补一行。
- 排序第二键（scenario_id/evidence_id/路径字典序）对不含这三者的类别（如
  RELEASE_UNIT_TOO_LARGE 按指标名多行、TESTED_RUNTIME_MISMATCH）无 tiebreak 定义；
  实践上稳定排序 + 确定性发射可保幂等，但建议补"兜底按 detail 字典序"一句。
- 第 1 轮 M5（"八命令"计数）、M6（AC-7 把 challenger PASS 写进验收的循环激励）、
  M7（fail fixture derived 证据不得挂 scenario_id 未成文）未在本轮修复范围内声明，
  维持次要级，不阻塞。

### 复审结论

第 1 轮全部致命问题（F1、F2）与事实性错误（E1–E4）经逐条对照修订文本与实现代码
核销，声称的修复均真实存在且与仓库事实相符，未发现新引入的失实声明。残留四条均为
文字/完备性级别的次要项，已列明归属，不构成 1B-delta 实现时的必然失败点。

VERDICT: PASS
