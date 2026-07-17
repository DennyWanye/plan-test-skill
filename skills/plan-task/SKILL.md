---
name: plan-task
description: 执行一份已定稿的 plan 并完成全套测试闭环：锁定绿色基线 → 并行执行 + 100% 完成度审计 → 阶段门禁（测试策略路由：MCP 真人测试/自动化脚本）→ testcase 维护 → 收尾 DoD + 文档回写。当用户说"执行这份 plan""按计划执行并测试""把 plans/xxx 跑了""实施这个计划""/plan-task"时使用。输入是一份现成的 plan（通常由 plan-bs 产出）。注意：还没有 plan、需要先讨论或先写 → 用 plan-bs 或 plan-test；只想写 plan 不执行 → writing-plans。
---

# plan-task — 执行 plan + 测试闭环

拿一份**已定稿的 plan**，走完执行与验证的全部闭环。**本 skill 不写 plan、不做需求澄清**——那是 `/plan-bs` 的活。

本 skill 与 plan-test 共享阶段文档与配置，共享文件都在 `../plan-test/` 下。

## 开场（每次必做）

1. **Announce**：输出 "I'm using the plan-task skill to execute and test the finalized plan."
2. **读配置**：读 `../plan-test/config.md`；项目根有 `.claude/plan-test.config.md` 则覆盖。`{大写变量}` 运行时替换。
3. **建 TodoWrite**：按下面 6 步建 todo。

## 流程

> **每阶段开工前必做（防跳步硬闸）**：进入下面每一步前，**先完整读该步引用的 `../plan-test/phase-X.md`**，并列出这一阶段的必做项清单（例：phase-5 = 分步 testcase / 幂等审查 / challenger 迭代 / 终审 / index 同步），逐项打勾推进。**不许凭"我大概懂了"跳过子步骤**——本 skill 的漏测几乎都源于没读阶段文档就动手。

### 1. 定位并校验输入（不许带病开工）

- **定位 plan**：斜杠命令后给了路径就用它；没给则找 `{PLANS_DIR}/` 下最近修改的文件夹，**和用户确认**是不是这份。
- **校验四件事**：
  1. `plan.md` 存在，且头部有 `<!-- plan-status: finalized -->` 标记。没有标记 → 告知用户"这份 plan 未经迭代定稿"，用户确认后才继续。
  2. `{ACCEPTANCE_FILE}` 存在——它是完成度审计与测试覆盖的唯一真相来源。**缺失 → BLOCKED**，建议先跑 `/plan-bs` 补出验收标准，不许拿 plan 反推验收标准凑数。
  3. plan 里的任务与 AC 有追溯关系（任务标注了覆盖哪条 AC）。
  4. **输入语义敏感功能必须有测试场景矩阵**（判定见 `../plan-test/config.md`"真人测试广度门禁"）：被测对象含 LLM/搜索/调研/推荐等输入敏感功能，但 acceptance 里没有场景矩阵 → **BLOCKED**，回 `/plan-bs` 补矩阵并经用户确认，不许自己现编。
- 什么都找不到 → 停下，提示用户先跑 `/plan-bs`（要讨论）或 `plan-test`（要一条龙）。

### 2. 锁定绿色基线

- 按 `../plan-test/phase-2-iterate-plan.md` 的 **B 节**执行：跑现有构建/测试/lint/类型检查，快照记入 plan 文件夹 `baseline.md`；基线本身是红的要先如实告知用户。

### 3. 并行执行 + 完成度审计

- 按 `../plan-test/phase-3-execute.md` 执行：`{EXECUTOR_ENGINE}` 并行派发、worktree 隔离、与本机 hook 共处、`{AUDITOR_ENGINE}` 可追溯矩阵审计、VERDICT 判定、回归门对照 baseline。

### 4. 阶段门禁（测试策略路由）

- 按 `../plan-test/phase-4-stage-gate.md` 执行：便宜的门在前（类型检查→lint→脚本测试），贵的真人测试在后；UI 走 MCP 真人点击（`MANUAL_TEST = required` 不可降级），逻辑走可复跑脚本。

### 5. testcase 维护

- 按 `../plan-test/phase-5-testcase.md` 执行：分步 testcase + 预期结果、幂等性审查、challenger 迭代（VERDICT 判定）、终审覆盖确认。

### 6. 收尾 DoD + 文档回写

- 按 `../plan-test/phase-final-dod.md` 执行：DoD 全绿才宣布完成；回写 ARCHITECTURE.md（推进 last-calibrated 锚点）、README、changelog。
- 任何 DoD 项达不成 → BLOCKED 升级，**不谎报完成**。

## 推进规则

- **⚠️ 末尾警戒（最重要）**：长任务越接近收尾，越容易用便宜的代码审计替昂贵的真机测试来"尽快合上"。**`MANUAL_TEST=required` 的 UI 测试不许降级**；测不了就 BLOCKED 升级，不许静默换等价方案（见 phase-4 ①b 兑现表）。**"功能主流程通过"≠"每条 AC 都测了"**——收尾前必回看兑现表，把设置项/开关态/角色隔离/空态/错误态逐条照见。
- **广度计数纪律（不许自行解释）**：同一问题的重跑/改写/continuation **不得**被解释成"测了多个场景"——distinct scenario 只按 acceptance 场景矩阵 + phase-4 ①c 账本计数。任何 required 场景仍为 PENDING/PARTIAL/NOT RUN 时，**不得宣布 complete**（`MANUAL_REQUIRED_PENDING_POLICY = block`）。
- **价值优先，blocker 早停**：进入打包/全量回归/完整真人矩阵等昂贵步骤前，先过 phase-4 门序第 4 层的核心价值 smoke（`VALUE_SMOKE_GATE = required`）。**"主要矛盾"对应的必须 AC 一旦 FAIL，立即停止一切收尾动作**（打包、发布、DoD 推进、"接近完成"的表述），状态只能是 BLOCKED——可以继续诊断修复，但不许边挂着已知 BLOCKER 边收尾。
- **成本纪律**：记录各阶段耗时；复测按 change-impact 路由——只重跑受本次改动影响的层，未变化的昂贵检查（全量构建/打包/全量回归）不重复执行。
- **已知失败版本启动警告**：总体 BLOCKED 时用户要求启动测试，必须先告知"这是已知失败版本、目的是复现/补证、非验收版本、已知这些场景会失败"，不许只说"已启动"。
- **缩小测试范围必须用户显式批准**：批准后回写 acceptance 的范围节（标注"用户批准缩减：原 S-x 移出范围"），交付结论只能表述为**用户批准后的范围**全绿，不得写成原范围全绿。
- 严格顺序执行，每阶段过"100% 完成度审计 + 对应测试"才进下一阶段。
- 所有"循环直到"受 `{MAX_ROUNDS}` 兜底，超限 → BLOCKED 升级。
- `EXECUTE_AUTONOMY = high`：执行中的分歧按最佳实践自决（BLOCKED 例外）；`FEATURE_POLICY = only-add`：不少做。

## 何时不要用

- 还没有 plan，需要先讨论/先写 → `plan-bs`（要共创）或 `writing-plans`（直接写）。
- 要从需求澄清到测试一条龙 → `plan-test`。
- 单文件小改、一次性脚本 → 直接做。
