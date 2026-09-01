# Phase 4 — 验收（围绕主要矛盾）

**目的**：执行完成后的统一终验关卡。两条排布原则：**便宜的门在前，贵的门在后**；**主要矛盾先测深测，次要 AC 各过一遍**（重点论 + 两点论兜底）。

## ① 测试策略路由（先决定怎么测）

按被测对象选择测试方式（`TEST_STRATEGY = route`）：

| 被测对象 | 测试方式 |
|----------|----------|
| 有 UI 的 Web / 桌面应用 | **MCP 真人点击/输入**（见 `checklists/manual-test-mcp.md`），`MANUAL_TEST = required` |
| 后端 API / CLI / 数据管道 / 库 / 定时任务 | **自动化测试脚本**（单元/集成/e2e/API），可重复运行 |
| 既有 UI 又有后端逻辑 | **两者都做**：脚本兜底逻辑，MCP 验交互 |

> 自动化脚本不是"手工测不了时的降级"，而是某些被测对象的**正确手段**。脚本必须存盘、可复跑、纳入回归套件。

## ② 便宜门序（红则先修，不进下一层）

> 冷路径场景适用时（`COLD_START_SCENARIO`）必须排在最前——环境准备会把系统弄成暖态，遮蔽冷启动缺陷；暖重启不算冷路径。

1. 类型检查（tsc --noEmit / dart analyze 等）
2. lint
3. **服务层-路由接线断言（`WIRING_CHECK = required`）**：本次新 `export` 的函数/枚举/新增入参，
   入口层必须有真实引用（`grep -rL "<新导出名>" <routes目录>` 命中"无引用"→ 人工确认，漏接即
   FAIL）；运行时白名单数组与类型全集同步（`satisfies` + exhaustiveness 断言——数组少一个枚举值
   tsc 不报错，必须让它变红）。**类型检查绿 ≠ 运行时白名单同步。**
4. 单元 / 集成测试脚本
5. **核心价值 smoke（`VALUE_SMOKE_GATE`，主要矛盾的最小验证动作）**：执行 acceptance 声明的
   最小验证动作（输入敏感功能为 2–5 个自然语言正向问题，走真实入口 + 真实 provider）。
   **失败 → 立即 BLOCKED 早停，不进任何昂贵步骤**——主要矛盾没验证前，别的测了也白测。
6. **分级冒烟（`FULL_SURFACE_SMOKE`，范围分级见 config）**：声明范围内每个用户入口各打一枪，
   任一 404/500/未接通即 FAIL。排查口诀：功能点了没反应 → 先 `grep -rn <路由名> <routes目录>`
   看路由在不在、挂没挂、有没有真的取用服务层新入参。脚本存盘、可复跑。
7. **真实 provider 契约门**（含 LLM 结构化输出的功能必做）：用当前真实 provider 的实际输出过
   生产 validator，确认 schema 兼容。手工构造的 payload 只能测 validator 本身。

## ③ 真人测试（重点论排布）

**测试顺序与深度跟随矛盾地位**：

1. **决定性 AC 场景先测、深测**：主要矛盾对应的场景排最前；任一决定性场景 FAIL →
   **立即停止一切收尾动作**（打包、发布、DoD 推进、"接近完成"的表述），状态只能是 BLOCKED，
   可以继续诊断修复，修复后从本门序重过。**已知 BLOCKER 还继续收尾 = 谎报进度。**
2. **次要 AC 各过一遍**：每条一个场景走通即可；确定性 UI（设置页/开关/CRUD/导航）一个场景即可，
   不许把多问题门槛错误套给它们。
3. **兑现表（防降级硬闸——本 skill 最常被偷工的一环，必须产出）**：逐条列 acceptance 每条
   "必须" AC：

   | AC | 矛盾地位 | 是否含 UI | 测试方式 | 驾驶者 | 真机证据（截图/log 位置） | 状态 |
   |----|----------|----------|----------|--------|---------------------------|------|

   - 含 UI 的 AC，"真机证据"列必须是实际 MCP 点击证据（截图/交互）。填"代码审计""逻辑等价"的
     一律记 ❌ 未完成。后端逻辑 AC 用可复跑脚本断言作证据。
   - **禁止静默降级**：任何 required 测试无法执行（环境受阻、设备缺失）→ BLOCKED 升级给用户，
     讲清卡点；确需等价方案须用户在 chat 显式批准并在表中注明。
   - **"主流程通过 ≠ 每条 AC 都测了"**：设置项、开关态、权限隔离、空态、错误态最容易被
     "主流程通过"掩盖，兑现表要照见每一条。
4. **输入语义敏感功能的广度账本**（适用性具体分析，判定见 config"真人测试广度门禁"）：
   - 深度（失败→重试→恢复）与广度（语义不等价输入）分开记账；distinct 场景数 ≥
     `{MANUAL_MIN_DISTINCT_CLASSES}`，retry/改写/continuation 不增加计数；
   - **业务终态判定**：positive-value 场景必须"非空有效结果 + 达 quality_bar（人工检查）"才 ✅；
     engine completed 但业务空结果 = 安全 PASS、产品 FAIL；negative-safety 的诚实失败不得拿来
     证明任何正向 AC；fallback 不崩只是可靠性 PASS，语义退化了照记 ❌；
   - required 场景 PENDING/PARTIAL/NOT RUN → 门禁 FAIL/BLOCKED（`MANUAL_REQUIRED_PENDING_POLICY = block`）；
   - 修好某场景后，至少再复测 1 个未受影响类别（防修复引入回归）；
   - LLM 载荷驱动功能另按 `llm_variant`（载荷形态 × 场景）记账，required 形态未覆盖即 PENDING；
     随机性采样见 config `STOCHASTIC_MIN_RUNS`。
   - 全 AI 驾驶须用户批准：至少 1 个 required 场景真人驾驶，或用户 chat 显式批准全 AI（表注）。
   - 确定性 UI 不适用本节，不许反向强套。

## ④ 完成记录（按路径分档）

- **默认（journal，一页）**：记入 plan 文件夹 `journal.md`——
  1. 核心价值 smoke 结果（命令 + 输出摘要）；
  2. 兑现表（上面 ③3）；
  3. 冒烟脚本路径与输出摘要；
  4. 广度账本（适用时）；
  5. 遗留问题清单（不许悬空的"留待后续"）。
  完成判定依据 = journal + phase-final 的 DoD 清单；交付说明如实写"无机器 receipt"。
- **FULL 且高外部性（`MACHINE_GATE` 启用，判定见 config）**：走机器账本全流程——
  测试前 `compile-manifest` + `init` 开账（冻结 testcase hash、场景矩阵、`applicability` 三维
  判定、release_unit）；每条测试当场 `record-run` + `attach-evidence`（脚本测试优先
  `record-run --exec`）；时间入账 `record-timing`；测完 `finalize --check-only` 输出
  `READY_FOR_AUDIT` 才进收尾。命令与语义见 `gate/PROTOCOL.md` 与
  `references/evidence-audit-lifecycle.md`；BLOCKED 语义陷阱见 config `BLOCKED_SEMANTICS`
  （临时受阻保持 NOT_RUN，不要记机器 blocked）。

## ⑤ testcase 收尾（原 phase-5 并入此处）

1. **写分步 testcase 并归档**：每个 testcase 一步一步、每步给预期结果；头部标注绑定的 AC
   （及矛盾地位）；存放 `{TESTCASE_DIR}/<按测试范围命名的文件夹>/`；维护 `{TESTCASE_DIR}/index.md`。
   设计前先查已有资产（`references/testcase-lifecycle.md`）：能复用 oracle 就复用，
   当前 run 仍须重新执行取证。
2. **实际结果回写**：写在 `{TESTCASE_DIR}/<组>/results/` 或 journal——FULL 路径**不许**回填进
   被冻结的 oracle 文件（会触发 `FROZEN_ORACLE_CHANGED`，这是设计不是误报）；确需修改期望
   本身 → 走 `behavior_changes` 用户批准。
3. **脚本纳入回归套件**：API/CLI/库类 testcase 落成可复跑脚本登记，下次跑本 skill 一并跑。
4. **幂等性审查**：对照 `checklists/idempotency-review.md`，逐条审"遍历 + 写副作用"的代码。
5. **语义等价审查**（输入敏感功能）：同一问题的改写/重跑有没有被记成多个 distinct 场景？
   有 → 合并计数，不达标就补真正不等价的类别并补测。
6. **challenger 迭代**（重点论）：决定性 AC 的 testcase 覆盖存疑、或 FULL 路径 → 派
   `{CHALLENGER_ENGINE}` 用 `prompts/testcase-iterator.md` 迭代一轮（收敛条件见 config
   `TESTCASE_ITERATIONS`）；次要 AC 覆盖清晰时不派。
7. **FULL 额外**：状态一致性机检（`declare-status` 五处口径对账，`STATUS_CONFLICT` 即修文档）、
   改动后 `re-attest`、末尾独立 full-audit（`{AUDITOR_ENGINE}` 声明 `MODE: full-audit`，
   全链闭环核查后 `audit` 入账；整改循环见 `references/evidence-audit-lifecycle.md` §3）。

## 出口

- **默认**：便宜门全绿 + 决定性场景 PASS + 兑现表无 ❌ 无未批准降级 + journal 完整 +
  testcase 已归档 → 进入收尾 DoD。
- **FULL**：以上 + `finalize --check-only` 输出 `READY_FOR_AUDIT` + full-audit PASS 已入账
  → 进入收尾 DoD。
