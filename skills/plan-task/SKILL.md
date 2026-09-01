---
name: plan-task
description: 执行一份已定稿的 plan 并完成测试闭环：锁定绿色基线 → 执行（集中/分兵自决）+ 100% 完成度审计 → 围绕主要矛盾的验收（测试策略路由：MCP 真人测试/自动化脚本）+ testcase 收尾 → 收尾 DoD + 文档回写。当用户说"执行这份 plan""按计划执行并测试""把 plans/xxx 跑了""实施这个计划""/plan-task"时使用。输入是一份现成的 plan（通常由 plan-bs 产出）。注意：还没有 plan、需要先讨论或先写 → 用 plan-bs 或 plan-test；只想写 plan 不执行 → writing-plans。
---

# plan-task — 执行 plan + 测试闭环

拿一份**已定稿的 plan**，走完执行与验证的全部闭环。**本 skill 不写 plan、不做需求澄清**——那是 `/plan-bs` 的活。

本 skill 与 plan-test 共享阶段文档与配置，共享文件都在 `../plan-test/` 下。

## 开场（每次必做）

1. **Announce**：输出 "I'm using the plan-task skill to execute and test the finalized plan."
2. **读配置**：读 `../plan-test/config.md`；项目根有 `.claude/plan-test.config.md` 则覆盖。`{大写变量}` 运行时替换。
2b. **判任务类型**（`TASK_TYPE`，见 config"流程路径"）：运维/部署任务（交付物是"让服务/环境处于目标状态"）走 OPS 路径——快照/回滚出口先行、1 轮实测挑战、journal 收尾，不套软件交付的 oracle 冻结/manifest 编译/finalize receipt。
3. **建 TodoWrite**：按下面 5 步建 todo。

## 流程

> **每阶段开工前必做（防跳步硬闸）**：进入下面每一步前，**先完整读该步引用的 `../plan-test/phase-X.md`**，并列出这一阶段的必做项清单（例：phase-4 ⑤ = 分步 testcase / 结果回写 / 幂等审查 / 语义等价审查 / index 同步），逐项打勾推进。**不许凭"我大概懂了"跳过子步骤**——本 skill 的漏测几乎都源于没读阶段文档就动手。

### 1. 定位并校验输入（不许带病开工）

- **定位 plan**：斜杠命令后给了路径就用它；没给则找 `{PLANS_DIR}/` 下最近修改的文件夹，**和用户确认**是不是这份。
- **校验五件事**：
  1. `plan.md` 存在，且头部**包含** `plan-status: finalized` 标记（按包含匹配——plan-bs 产出的标记可能带 `(plan-bs)` 等来源后缀）。没有标记 → 告知用户"这份 plan 未经迭代定稿"，用户确认后才继续。
  2. `{ACCEPTANCE_FILE}` 存在——它是完成度审计与测试覆盖的唯一真相来源。**缺失 → BLOCKED**，建议先跑 `/plan-bs` 补出验收标准，不许拿 plan 反推验收标准凑数。
  3. plan 里的任务与 AC 有追溯关系（任务标注了覆盖哪条 AC）。
  4. **输入语义敏感功能必须有测试场景矩阵**（判定见 `../plan-test/config.md`"真人测试广度门禁"）：被测对象含 LLM/搜索/调研/推荐等输入敏感功能，但 acceptance 里没有场景矩阵 → **BLOCKED**，回 `/plan-bs` 补矩阵并经用户确认，不许自己现编。
  5. **LLM 载荷驱动功能必须有「LLM 行为变异清单」**（`LLM_PAYLOAD_ADVERSARIAL`，判定见 `../plan-test/config.md`"LLM 载荷对抗门禁"）：功能含"LLM 输出驱动端侧状态机/卡片/流程推进"，但 acceptance 里没有 LLM 行为变异清单（乱序/重复/schema 违约/超长/拒不调工具，各含端侧容错断言）→ **BLOCKED**，回 `/plan-bs` 补清单，不许自己现编。同理，功能依赖异步注册服务/远程配置/登录态而场景矩阵缺冷路径场景（`COLD_START_SCENARIO`）→ **BLOCKED**。
- 什么都找不到 → 停下，提示用户先跑 `/plan-bs`（要讨论）或 `plan-test`（要一条龙）。

### 2. 锁定绿色基线

- 按 `../plan-test/phase-2-iterate-plan.md` 的 **B 节**执行：跑现有构建/测试/lint/类型检查，快照记入 plan 文件夹 `baseline.md`；基线本身是红的要先如实告知用户。

### 3. 执行 + 完成度审计

- 按 `../plan-test/phase-3-execute.md` 执行：**执行模式自决**（任务真独立且量大→分兵并行子代理 + worktree 隔离；环环相扣或量小→集中兵力当前 session 串行打歼灭战，决策一行留痕）、与本机 hook 共处、`{AUDITOR_ENGINE}` 可追溯矩阵审计（主要矛盾优先）、回归门对照 baseline。
- **oracle 先于实现**（普适铁律）：动手写某条 AC 的实现前，先写下它的"什么算对"（plan 验证栏 / testcase 草稿）；禁止实现后照实现补预期。
- **代码 review（phase-3 A4，`CODE_REVIEW = required-for-code`）**：便宜检查绿后、完成度审计前，对累计 diff 做正确性 review（执行者不自审——harness 自带 code review 或独立 challenger）；P0/P1 修完、每个修复配决定性测试、并按 A4 第 4 步分层复验（便宜层全量 + 受影响决定性测试 + 价值 smoke）才进审计。
- **价值里程碑 PASS 后**：demo 给用户（跑起来的实物 + 一句用户语言汇报）+ 矛盾转化再分析（重答三问、重排剩余任务）。

### 4. 验收（重点论测试 + testcase 收尾）

- 按 `../plan-test/phase-4-stage-gate.md` 执行：便宜门在前（类型检查→lint→接线断言→脚本测试→
  核心价值 smoke→按路径分级冒烟→provider 契约门），贵的真实环境测试在后。
- **重点论排布**：决定性 AC 场景先测深测——任一 FAIL 立即停止一切收尾动作（BLOCKED）；次要 AC 各过一遍；兑现表逐条照见每条必须 AC。
- **完成记录按路径分档**（config `MACHINE_GATE`）：默认记一页 journal（核心价值 smoke 结果 + 兑现表 + 冒烟输出 + 遗留清单）；FULL 且高外部性 → gate 机器账本全流程（`compile-manifest` + `init` 开账、`applicability` 三维判定、每条测试 `record-run` + `attach-evidence` 当场入账、测完 `finalize --check-only` 出 `READY_FOR_AUDIT`、结果回写后 `declare-status` 对账、末尾独立 full-audit 入账）。
- **testcase 收尾**（phase-4 ⑤）：分步 testcase 归档绑定 AC、实际结果回写（冻结集之外）、脚本纳入回归套件、幂等/语义等价审查、index.md/README 同步。

### 5. 收尾 DoD + 文档回写 + 自我批评

- 按 `../plan-test/phase-final-dod.md` 执行：文档回写（README / changelog / testcase index）→ DoD 清单逐条附证据核对 → **journal 终态行**（`JOURNAL_VERDICT`，格式见 phase-final；没有终态行 = run 未闭环）→ **自我批评一行**写进 `{PLANS_DIR}/<feature>/retro.md`（本次哪些门空转、哪里被仪式拖慢）→ 提交 →（要推送远程时）**push 前 code review 硬门**：对外发 diff 再过一遍 review，P0/P1 修完并按分层复验后再推（phase-final 第 6 步）。
- **默认路径**：完成判定 = DoD 清单全绿（每条附证据位置），交付措辞如实写"完成判定依据 journal 与 DoD 清单，无机器 receipt"。
- **FULL（`MACHINE_GATE` 启用）**：额外按固定顺序过机器门——文档回写 → `re-attest` → 重新 full-audit 入账 → `python {GATE_SCRIPT} finalize --run-dir <run-dir>`。**最终交付状态只取该命令的 exit code**（exit 0 + `GATE RECEIPT` 才是完成；exit 3 = fixture-only 不是完成）；跳过 re-attest 会 `TESTED_RUNTIME_MISMATCH`，跳过重新 audit 会 `AUDITOR_INPUT_STALE`；没有有效 receipt 的手写 SHIP/100% = `DELIVERY_VERDICT_CONTRADICTS_LEDGER`。交付措辞用 receipt 模板。
- 任何 DoD 项达不成 → BLOCKED 升级，**不谎报完成**。

## 推进规则

- **⚠️ 末尾警戒（最重要）**：长任务越接近收尾，越容易用便宜的代码审计替昂贵的真机测试来"尽快合上"。**`MANUAL_TEST=required` 的 UI 测试不许降级**；测不了就 BLOCKED 升级，不许静默换等价方案（见 phase-4 ①b 兑现表）。**"功能主流程通过"≠"每条 AC 都测了"**——收尾前必回看兑现表，把设置项/开关态/角色隔离/空态/错误态逐条照见。
- **广度计数纪律（不许自行解释）**：同一问题的重跑/改写/continuation **不得**被解释成"测了多个场景"——distinct scenario 只按 acceptance 场景矩阵 + phase-4 ①c 账本计数。任何 required 场景仍为 PENDING/PARTIAL/NOT RUN 时，**不得宣布 complete**（`MANUAL_REQUIRED_PENDING_POLICY = block`）。
- **计划失效即回炉，不许打补丁绕**（phase-3 A2）：执行中若"补丁能让任务完成、但不能让对应 AC 真达成"，那是 plan 层缺陷——停该执行线、回 phase-2 重迭代该部分（重挑战 + 补 spike），回写 plan 后再继续。执行子代理只能上报，无权自行绕行；审计以**原始需求 AC 达成**为锚，不以 plan 任务打勾为锚，主要矛盾未解决 = 整体 FAIL。
- **价值优先，blocker 早停**：进入打包/全量回归/完整真人矩阵等昂贵步骤前，先过 phase-4 门序的核心价值 smoke（`VALUE_SMOKE_GATE = required`）。**"主要矛盾"对应的必须 AC 一旦 FAIL，立即停止一切收尾动作**（打包、发布、DoD 推进、"接近完成"的表述），状态只能是 BLOCKED——可以继续诊断修复，但不许边挂着已知 BLOCKER 边收尾。
- **交付一致性**：验证必须针对已提交 HEAD，工作树须为空。会话续接先重跑当前路径声明范围的
  分级冒烟；新 AC 先进 acceptance。分级冒烟和提交态硬门不得豁免。
- **成本纪律**：记录各阶段耗时；复测按 change-impact 路由——只重跑受本次改动影响的层，未变化的昂贵检查（全量构建/打包/全量回归）不重复执行。
- **已知失败版本启动警告**：总体 BLOCKED 时用户要求启动测试，必须先告知"这是已知失败版本、目的是复现/补证、非验收版本、已知这些场景会失败"，不许只说"已启动"。
- **缩小测试范围必须用户显式批准**：批准后回写 acceptance 的范围节（标注"用户批准缩减：原 S-x 移出范围"），交付结论只能表述为**用户批准后的范围**全绿，不得写成原范围全绿。
- 按 SKILL.md（plan-test）"推进规则"执行：执行模式自决（集中兵力/分兵），oracle 先于实现贯穿始终；每阶段收尾过"100% 完成度审计 + 对应测试"才算完成，门的强度不因并行而降。
- 所有"循环直到"受 `{MAX_ROUNDS}` 兜底，超限 → BLOCKED 升级。
- `EXECUTE_AUTONOMY = high`：执行中的分歧按最佳实践自决（BLOCKED 例外）；
  `BEHAVIOR_POLICY = preserve-approved`：保持已批准外部行为，内部按 Ponytail policy 最小化。

## 何时不要用

- 还没有 plan，需要先讨论/先写 → `plan-bs`（要共创）或 `writing-plans`（直接写）。
- 要从需求澄清到测试一条龙 → `plan-test`。
- 单文件小改、一次性脚本 → 直接做。
