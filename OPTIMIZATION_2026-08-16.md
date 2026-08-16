# Plan-Test Skill 优化：防止过度测试

**日期**: 2026-08-16  
**优化目标**: 解决"测试过多"问题，从 coverage-maximizing 转向 goal-and-risk-driven minimal sufficient testing

## 问题诊断

### 当前存在的问题

1. **Testcase challenger 目标是"尽量增强"**
   - 默认检查正常态、错误态、空态、边界值、非法输入、并发、幂等
   - 即使目标是简单只读展示，也会建议全套测试
   - 没有先问：这些风险是否真的存在于目标的行为、数据流和 assurance contract 中？

2. **FULL_SURFACE_SMOKE 对所有任务都强制**
   - S/M/L 三档都不能裁掉 FULL_SURFACE_SMOKE
   - 要求测试所有历史用户入口，不只是本次目标
   - 对于单文件内部调整、不影响入口的局部算法，全量打遍历史端点成本大于收益

3. **ac_ids 存在但没有成为硬门**
   - Schema 已经允许 testcase 绑定 ac_ids
   - 但 validator 没有强制：required testcase 必须绑定至少一条 AC
   - 没有阻止"无目标绑定的 required testcase"

4. **固定 testcase 挑战轮次鼓励扩张**
   - 当前默认至少挑战 2 轮
   - Challenger 的成功标准是"还能不能找到更多边界"
   - 第二轮通常很容易继续增加测试，而不是判断边际价值

## 已完成的优化

### 1. 修改 testcase-iterator.md ✅

**位置**: `/Users/denny/planSkill/plan-test/skills/plan-test/prompts/testcase-iterator.md`

**改动**:
- 将目标从"挑战并增强"改为"验证并优化最小充分测试集"
- 增加"核心原则"部分，强调目标导向测试
- 每个 required testcase 必须回答：
  * 它直接证明哪个 MUST AC？（delivery 测试）
  * 它防止本次改动破坏哪个受影响的行为？（change-risk 测试）
- 增加"目标相关性审查"，明确哪些测试只在实际适用时才是 required
- 增加"最小充分性审查"步骤，防止测试膨胀
- 修改输出格式，要求列出：
  * AC 覆盖审查
  * 应删除或降级的测试
  * 最小充分性评估
- 修改 PASS 标准，增加"测试集是最小充分的"要求

### 2. 修改 config.md - Full Surface Smoke ✅

**位置**: `/Users/denny/planSkill/plan-test/skills/plan-test/config.md`

**改动**:
- 将 FULL_SURFACE_SMOKE 分为三级：
  * **critical-surface-smoke**（必做）：少量核心历史入口
  * **affected-surface-smoke**（条件触发）：根据 impact_paths 运行受影响端点
  * **full-surface-smoke**（高风险触发）：仅在路由层、共享基础设施、正式 release 时强制
- 单文件改动且有明确 impact_paths 时，只跑 critical + affected

### 3. 修改 config.md - Testcase 迭代策略 ✅

**位置**: `/Users/denny/planSkill/plan-test/skills/plan-test/config.md`

**改动**:
- 修改 TESTCASE_ITERATIONS 的说明
- 明确收敛条件：
  * 所有 MUST AC 都有 required testcase 覆盖
  * 所有 required testcase 都有明确的 AC 或 risk 绑定
  * 没有新增 required obligation
- 继续条件：只能新增 exploratory testcase 时，不阻断定稿
- 不再固定"至少两轮必须继续加内容"

### 4. 创建 Test Obligation Matrix 文档 ✅

**位置**: `/Users/denny/planSkill/plan-test/skills/plan-test/checklists/test-obligation-matrix.md`

**内容**:
- 定义三种 obligation 类型：delivery、change-risk、exploratory
- 提供 Obligation Matrix 结构和示例
- 说明使用流程（Phase A/1/5/Gate）
- 提供判断指南和常见反模式

### 5. 更新 phase-A-acceptance.md ✅

**位置**: `/Users/denny/planSkill/plan-test/skills/plan-test/phase-A-acceptance.md`

**改动**:
- 增加 4c 步骤：测试义务矩阵（所有任务必做）
- 明确每个 test obligation 必须说明的字段
- 提供适用性判断指南
- 更新 acceptance.md 模板，增加 Test Obligation Matrix 部分
- 更新 DoD，要求所有 delivery 和 change-risk obligation 都有对应 testcase

### 6. 更新 phase-5-testcase.md ✅

**位置**: `/Users/denny/planSkill/plan-test/skills/plan-test/phase-5-testcase.md`

**改动**:
- 在步骤 1 中要求每个 testcase 明确绑定至少一个 test obligation
- 在步骤 4（子代理迭代）中强调检查 obligation 绑定
- 增加收敛条件说明

### 7. 更新 phase-4-stage-gate.md ✅

**位置**: `/Users/denny/planSkill/plan-test/skills/plan-test/phase-4-stage-gate.md`

**改动**:
- 增加"昂贵层前置 1b：Test Obligation Matrix 验证"
- 要求在 testcase 冻结后验证测试义务矩阵
- 列出需要检查的诊断码

## 还需要完成的优化

### 1. 更新 Gate Validator - 增加诊断 ⏳ → 🔶 需要 Python 代码实现

**位置**: `/Users/denny/planSkill/plan-test/skills/plan-test/scripts/plan_test_gate.py`

**需要增加的诊断**:
- `AC_COVERAGE_MISSING`: MUST AC 没有 delivery testcase
- `ORPHAN_REQUIRED_SCENARIO`: required 场景既不绑定 AC，也不绑定 in-scope risk
- `UNJUSTIFIED_TEST_SCOPE`: 测试超出 acceptance/assurance 范围却被标为 required
- `OBLIGATION_NOT_SATISFIED`: 定义的 obligation 没有对应的 testcase

**状态**: 需要修改 Python 代码，涉及：
- 解析 acceptance.md 中的 Test Obligation Matrix
- 验证 testcase 与 obligation 的绑定关系
- 实现新的诊断逻辑

### 2. 更新 Schema - 支持 Test Obligation ⏳ → 🔶 需要 Schema 扩展

**位置**: `/Users/denny/planSkill/plan-test/skills/plan-test/schemas/plan-test-run.schema.json`

**需要增加的字段**:
- 在 scenario 中增加 `obligation_ids` 数组
- 在账本中增加 `test_obligations` 数组，记录所有定义的 obligation
- 增加 obligation 的 schema 定义

**状态**: 需要扩展 JSON Schema

### 3. 更新文档和示例 ⏳ → 📝 文档工作

- 更新 README.md：说明新的测试策略
- 更新 HANDOFF.md：说明 Test Obligation Matrix 的使用
- 创建示例 acceptance.md：展示完整的 Test Obligation Matrix
- 更新 SKILL.md：说明新的测试收敛条件

**状态**: 需要文档更新

## 预期效果

### 优化前

- Testcase 会尽可能覆盖所有可能出错的方向
- 即使简单只读功能也会有大量并发、幂等、边界测试
- 所有任务都要跑全量历史端点冒烟
- 没有机制判断测试是否必要

### 优化后

- Testcase 首先证明用户目标，然后覆盖受影响范围内的风险
- 只读功能不会有无意义的并发、幂等测试
- 单文件改动只跑核心 + 受影响的端点
- 每个 required testcase 都能说明它的必要性
- 无法说明必要性的测试被标记为 exploratory

## 质量保证

### 保留的严格机制

- acceptance 唯一真相
- frozen oracle
- primary evidence
- UI 必须真实点击
- 正向价值必须真实达成
- 范围变化必须用户批准
- 不确定时 fail closed

### 优化的部分

- 从"尽可能全面"转向"最小充分"
- 从"所有任务全量冒烟"转向"分级冒烟"
- 从"固定轮次挑战"转向"边际收益收敛"
- 从"可选的 ac_ids"转向"强制的 obligation 绑定"

## 下一步行动

1. ✅ 修改 testcase-iterator.md
2. ✅ 修改 config.md（Full Surface Smoke + Testcase Iterations）
3. ✅ 创建 test-obligation-matrix.md
4. ✅ 更新 phase-A-acceptance.md
5. ⏳ 更新 plan_test_gate.py（增加新诊断）
6. ⏳ 更新 plan-test-run.schema.json（支持 obligation）
7. ⏳ 更新 phase-5-testcase.md
8. ⏳ 更新 phase-4-stage-gate.md
9. ⏳ 更新 README.md 和 HANDOFF.md
10. ⏳ 创建示例 acceptance.md 展示 Test Obligation Matrix

## 风险评估

### 低风险

- 优化不会降低质量，只是让测试更聚焦
- 所有 MUST AC 仍然必须有测试覆盖
- 关键的安全机制（frozen oracle、primary evidence）没有变化

### 需要注意

- 需要更新现有的 acceptance.md 示例文件
- 需要在 SKILL.md 或 README 中说明新的测试策略
- Gate validator 的新诊断需要完整测试
