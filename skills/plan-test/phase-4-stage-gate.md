# Phase 4 — 验收门禁（测试策略路由）

**目的**：执行完成后的**统一终验关卡**（本流程走一次；plan 若含多个独立交付批次，则每批次收尾各过一次）。**便宜的门在前，贵的门在后**——别在编译都过不了时就上昂贵的真人测试。

## ① 测试策略路由（先决定怎么测）

按被测对象选择测试方式（`TEST_STRATEGY = route`）：

| 被测对象 | 测试方式 |
|----------|----------|
| 有 UI 的 Web / 桌面应用 | **MCP 真人点击/输入**（见 `checklists/manual-test-mcp.md`），`MANUAL_TEST = required`，不可省略/降级 |
| 后端 API / CLI / 数据管道 / 库 / 定时任务 | **写自动化测试脚本**（单元/集成/e2e/API），可重复运行 |
| 既有 UI 又有后端逻辑 | **两者都做**：脚本兜底逻辑，MCP 验交互 |

> 自动化脚本不是"手工测不了时的降级"，而是某些被测对象的**正确手段**。脚本必须**存盘、可复跑、纳入回归套件**（不是跑完即弃）。

## ①b 真人测试逐条兑现（防降级硬闸）

**这是本 skill 最常被偷工的一环，长任务末尾尤甚——必须机制化，不靠自觉。**

1. **产出兑现表**（不产出此表不得进入本阶段出口）：逐条列 `{ACCEPTANCE_FILE}` 的每条"必须" AC——

   | AC | 是否含 UI | 测试方式 | 真机证据（截图/log/DB 位置） | 状态 |
   |----|----------|----------|------------------------------|------|
   | AC-x | 是 | MCP 真人点击 | testcase/.../s3.png + logcat 行 | ✅/❌ |

   - **含 UI 的 AC，"真机证据"列必须是实际 MCP 点击证据**（截图/交互）。填"代码审计""逻辑等价""同类壳等价验证"的，一律记 **❌ 未完成**，不是通过。
   - 后端逻辑 AC 用可复跑脚本断言作证据。
2. **禁止静默降级**：任何 `required` 真人测试**无法执行**（环境受阻、设备缺失、数据造不出、标记删不掉等）→ **必须标 BLOCKED 升级给用户**，讲清卡点与解锁条件。**不许自行改用代码审计/等价验证替代**；确需等价方案，须用户在 chat 中**显式批准**，并在兑现表注明"用户批准降级"。
3. **"功能通过 ≠ 测试充分"**：核心链路跑通只覆盖了少数 AC。兑现表要照见**每一条**，尤其设置项、开关态、角色/权限隔离、空态、错误态——这些最容易被"主流程通过"掩盖。

## ①c 真人覆盖账本（输入语义敏感功能必做，接在兑现表之下）

**病根**：同一个问题重复跑 4 次 + 一次 continuation，很容易被写成"真人验收充分"。深度（失败→重试→恢复）和广度（语义不等价的输入）是两回事，**必须分开记账**。

1. **账本**（对照 acceptance 的场景矩阵逐行记）：

   | scenario_id | gate_type | input_class | root runs | retry runs | continuation runs | engine 终态 | 业务终态 | 状态 |
   |-------------|-----------|------------|-----------|------------|-------------------|-------------|----------|------|
   | S-1 | positive-value | …… | 1 | 2 | 1 | completed | completed+有效报告 | ✅ |

   末尾一行汇总计数：`distinct_scenarios=N / ui_submissions=N / root_runs=N / retry=N / continuation=N / completed=N / partial=N / insufficient=N / failed=N`。

   **engine 终态 ≠ 业务成功**：workflow `status=completed` 只表示流程图正常收敛，业务结果可能是 completed/partial/insufficient。**必须按业务终态判定**：
   - `positive-value` 场景：业务终态必须是"非空有效结果 + 达 quality_bar（人工检查过）"才算 ✅；engine completed 但业务 insufficient/空结果 → **安全行为 PASS、产品质量 FAIL**，场景记 ❌。
   - `negative-safety` 场景：insufficient/诚实失败才是预期 ✅。
   - **insufficient_evidence 不得被拿来证明任何正向 AC**。
   - **fallback 成功 ≠ 功能正确**：fallback 不崩只是可靠性 PASS；fallback 后的**语义是否仍然正确**（没把专业意图退化成 generic 查询）是独立判定项，语义错了场景记 ❌。

2. **计数纪律（不许自行解释）**：
   - **retry/重放/同意图改写只证可靠性**，不增加 distinct scenario 数；
   - **continuation 只证 lineage/补研**，不算新问题；
   - 每个 required distinct scenario **至少 1 次真实 UI root run**（含证据）。

3. **门禁规则**：
   - distinct 已执行数 < 矩阵 required 数，或 < `{MANUAL_MIN_DISTINCT_CLASSES}` → **Gate FAIL**；
   - 任何 required 场景 PENDING/PARTIAL/NOT RUN → **Gate FAIL/BLOCKED**（`{MANUAL_REQUIRED_PENDING_POLICY} = block`），不得以"核心交付 PASS"表述掩盖；
   - **修复后的复测广度**：修好某场景后，除复测该场景外，**至少再复测 1 个未受影响的类别**（防修复引入回归）。
   - 确定性 UI（判定见 config）不适用本节，不许反向强套。

## ② 门的顺序（红则先修，不进下一层；主要矛盾优先于昂贵收尾）

1. 类型检查（tsc --noEmit / dart analyze 等）
2. lint
3. 单元 / 集成测试脚本
4. **核心价值 smoke（`VALUE_SMOKE_GATE = required`，输入敏感功能必做）**：跑 2–5 个自然语言正向问题，走真实入口 + 真实 provider，验证主要矛盾（核心价值真的能产出有效结果）。**失败 → 立即 BLOCKED 早停**，不进入打包、全量回归、完整真人矩阵等昂贵步骤——别在核心价值未证实前先烧几 GB 的构建。
5. **真实 provider 契约门（含 LLM 结构化输出的功能必做）**：用**当前真实 provider 的实际输出**过一遍生产 validator，确认 schema 兼容（字段、枚举值、大小写不漂移）。手工构造的合法/非法 payload 只能测 validator 本身，**不能证明真实输出能通过**。
6. （以上全绿后）→ 昂贵层：MCP 真人完整矩阵测试

**昂贵层前置：testcase 冻结**。进入第 6 层前，本阶段要执行的 testcase 必须已**编写完成并通过 challenger 挑战**（即 phase-5 的编写与迭代动作前移到此刻完成）；不许拿临时、未经挑战的 testcase 跑昂贵验收，测完再补定义。phase-5 收尾时只做实际结果回写与回归登记。

**Blocker 早停铁律**：一旦"主要矛盾"对应的必须 AC 判 FAIL，**立即停止一切完成收尾**（打包、发布、DoD 推进、"接近完成"的表述），状态只能是 BLOCKED；可以继续做诊断与修复，修复后从本门序重新过。**已知 BLOCKER 还继续收尾 = 谎报进度**。

## ③ 测试环境就绪（真人测试前必做）

- 起服务（dev server / 后端 / 依赖服务）。
- 准备测试数据 / fixtures / 种子数据。
- 测完清理或隔离测试数据，避免污染。

## 执行测试与修复

- 严格按已冻结的 testcase 逐条测：UI 用 MCP 真人点击，逻辑用脚本断言。
- 报错 → 修复 → **复测**（含"至少复测 1 个未受影响类别"的广度要求，见 ①c）。
- 全部通过后 → 进入 ④ 全链终审（"是否真按 testcase 跑了全部任务"并入终审核查，不再单独派发确认代理）。

## ④ 100% 完成度终审（测试全部执行完后走全链）

- 派 `{AUDITOR_ENGINE}`，用 `prompts/completion-auditor.md`，**派发时声明 `MODE: full-audit`**：每条 AC ↔ 任务 ↔ 代码 ↔ testcase ↔ 场景 ↔ root run ↔ 证据 ↔ 业务终态，逐条确认闭环；含场景计数、状态一致性、整体可用性、"是否真按 testcase 跑全"核查。
- 按 SKILL.md"上下文包"规则派发；以末行 `VERDICT` 判定，缺结论行按 FAIL 处理。
- 有断点 → 补完 → 复审（复审只核上轮断点与新改动）。超 `{MAX_ROUNDS}` → BLOCKED 升级。

## 出口

- 所有测试通过 + full-audit 终审 100% → 进入 phase-5。
