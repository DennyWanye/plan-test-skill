# 机器门禁改造进度（来源：2026-07-27 完成质量复盘 handoff）

## 已完成（本仓库，Slice 1A–1D + P0 流程接线）

- **1A schema 与 run-dir 契约**：`schemas/plan-test-run.schema.json` + `gate/PROTOCOL.md`
  （fact/projection 分离、primary/derived 证据分级、revision CAS 并发契约）。
- **1B ledger CLI 与 deterministic validator**：`scripts/plan_test_gate.py`
  （init/record-run/attach-evidence/declare-status/set-delivery/audit/finalize/render/invalidate；
  文件锁 + 原子写 + CAS；稳定诊断码；required rows 自动 NOT_RUN，状态只能重算）。
- **1C receipt 与 stale 机制**：receipt 绑定 ledger/证据/auditor/HEAD/dirty 指纹 digest，
  幂等 finalize；audit 后任一 fact 变化 → `AUDITOR_INPUT_STALE` / `RECEIPT_STALE`；
  dirty 指纹排除 run-dir 自身且排除规则进 digest。
- **1D 集成与 dogfood**：canonical command 接入 plan-task/plan-test/phase-2/3/4/5/final-dod；
  `scripts/test_plan_test_gate.py` 23 个用例，含 Companion 历史三冲突 normalized fixture
  （`REQUIRED_SCENARIO_NOT_RUN` + `STATUS_CONFLICT` + `DELIVERY_VERDICT_CONTRADICTS_LEDGER`，
  另暴露证据循环与 `RELEASE_UNIT_TOO_LARGE`）与完整 PASS 路径（防 gate 只会拒绝）。
- **P0-2/P0-3 流程规则**：phase-2 行为契约冻结 + black-box oracle 冻结；phase-3 执行子代理
  无权动 frozen oracle；plan-challenger 增加 oracle 反转质疑项；新增
  `prompts/acceptance-challenger.md`（P1-1，qualitative，不替代 gate）。
- **P0-4 时序修正**：full-audit 从 phase-4 移到 phase-5 末尾（结果回写与证据冻结之后）；
  phase-4 出口改为 `finalize --check-only` 预检。
- **§11 交付措辞**：phase-final-dod 增加 receipt 模板，禁止无作用域 `100% COMPLETE / SHIP`。

## 已完成（第二轮，2026-07-27：slice-1a delta，plan 见 plans/2026-07-27-plan-test-gate-slice-1a/）

- **timing contract（schema 1.1.0）**：`record-timing`（--exec monotonic 实测 /
  declared 申报强制 measured=false）+ `checkpoint` + advisory 级 `TIMING_GAP` +
  render 七类 activity_class 耗时分解。
- **诊断排序契约**：canonical 20 类固定序 + 类别内 hint/detail 字典序，输出幂等；
  advisory（`ADVISORY` 前缀）不拦截、不影响状态机。
- **schema_version major 校验**（不符即 SCHEMA_INVALID）。
- **静态 fixture 落盘**：`fixtures/gate/pass-minimal/`（正式 finalize → SHIPPABLE +
  receipt）与 `fixtures/gate/fail-companion-conflict/`（check-only → 15 条有序 DIAG，
  前三类为 handoff 冻结序列）；回放器 + provenance null-hash → `PROVENANCE: UNVERIFIED`
  强制标注。自测全绿（第三轮去重后为 50 用例）。

## 已完成（第三轮，2026-07-27：1D-delta，Windows 溯源与兼容闭环）

- **Companion provenance 已实采**：三份 F:\ 历史来源的 SHA-256、RFC 3339 UTC
  `captured_at` 与匿名 Windows host 标识已写入
  `fixtures/gate/fail-companion-conflict/provenance.json`；回放在来源可达时复算 hash。
- **normalized fixture 已纠偏**：required 真人集合改为真实的 `S-1～S-5、S-8`；
  manual-test 的 S-1=`PARTIAL`、S-2～S-5/S-8=`NOT RUN` 与 manual-results 的
  `6/6 PASS` 逐项入账；不再把已自动化 PASS 的 S-6 伪装成 NOT_RUN。
- **Windows 自测兼容**：所有文本 fixture 显式 UTF-8；静态 PASS fixture 使用当前
  `sys.executable`，不再写死 `python3`；evidence 路径统一规范化为 run-dir 相对 POSIX
  形式并拒绝绝对路径/目录逃逸。Windows 自测全绿（当时口径 57；第三轮去重后为 50）。

## 已完成（第四轮，2026-08-04：schema 1.3.0，DeskPet session-model-run-visibility 复盘）

依据：DeskPet 2026-08-03 实际执行（12h24m）的四源交叉审计——git 历史、文件 mtime、
workflow.db、会话日志互证。实锤：timing 全 0、账本在 finalize 前 2.5 分钟整体补写、
证据重复 36.8%、改任意文件全场景 stale、audit engine 填方法名、全 AI 驾驶叙述成真人。

- **时间记账硬门**：`TIMING_MISSING`/`TIMING_GAP` 升 error（真实 run；fixture 免检时钟门）；
  区间覆盖模型替换点距模型（点距算法会把申报区间的两端误判成空洞）；
  `phase-start`/`phase-end` + `PHASE_UNPAIRED`。TIMING_GAP 升级决策据此已由真实数据拍板。
- **先测后补账侦测**：attach 记录证据文件 mtime → `EVIDENCE_PREDATES_LEDGER`；
  历史证据唯一入口 `import-evidence --from-run`（chain of custody 入账显形）。
- **影响范围复测**：`scenario.impact_paths`（fail-closed）；receipt 增
  tested_code_head/content_basis/exclusion_scope/timing_summary；report 增"身份说明"。
- **驾驶与审计身份**：`DRIVER_APPROVAL_MISSING` + `record-approval`（绑定用户消息 hash）；
  `audit --engine` 拒绝方法名。
- **挑战收敛状态机（1.4）**：acceptance + assurance contract 冻结范围；第一轮 breadth、
  后续 open+diff；真实 finding ID 去重，gate 推导新增/收敛；3/5/8 分别触发 scope audit、
  user review、hard stop，architecture reset 不清零历史。
- **baseline runner**：`scripts/baseline_runner.py`（分片清单/心跳/超时精确杀进程树/
  既有失败签名/新红即停/--resume）。自测 137 用例全绿。
- **阶段依赖图并行化（P1-6）**：SKILL.md 推进规则从全局串行改为双轨依赖图——实现轨
  与验证准备轨（phase-3 D：testcase/fixture/冒烟/manifest 草案）并行，汇合闸后才进
  昂贵层；验证准备轨 black-box 纪律（禁读实现代码，防 oracle 被实现污染）。
  DeskPet 数据：3h27m 准备段与 2h30m 实现段几乎可完全重叠。

## 未完成（后续独立 slice，勿打包成超大 plan）

- **内容寻址证据仓库（CAS）**：证据按 SHA-256 存一次、slice/ledger 只引用 artifact ID、
  跨 run 引用不复制文件（DeskPet 实测重复 714KB/36.8%）。收益只省磁盘不省墙钟，
  且要动 EVIDENCE_MISSING/HASH 校验路径与 path traversal 防线——独立 slice 做，
  不与其他改动打包。

- **2A 行为契约批准 artifact 细化**：目前 `behavior_contract`/`behavior_changes` 已有 schema
  与校验，但批准事件的采集流程（用户消息 event ID/hash 自动采集）仍是手工填 manifest。
- **2B internal test mutation report**：repo 内部 unit/integration 测试被删/放宽的 diff 审计
  信号尚未自动化（现在只覆盖冻结 black-box oracle 文件）。
- **3A runtime adapter protocol**：`runtime_attestation.adapter_status` 已有 UNKNOWN→BLOCKED
  语义，但 project attest command 协议与正反 fixture 未定义。
- **3B/3C 项目侧**：DeskPet `.plan-test/policy.json`、core-user-journeys manifest、
  change-impact → required lanes/edges/sample budget 计算、R-01～R-14 永久回归矩阵
  （R-12 blocked：需产品先定义 autonomy policy）。属于 DeskPet 仓库，不在本 skill 仓库做。
- **escaped-defects 自动回灌**（P1-9）与 exploratory tester 编排。
