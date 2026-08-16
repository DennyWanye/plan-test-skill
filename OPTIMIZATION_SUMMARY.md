# Plan-Test Skill 优化总结

**日期**: 2026-08-16  
**优化目标**: 解决"测试过多"问题，从 coverage-maximizing 转向 goal-and-risk-driven minimal sufficient testing

---

## 📋 优化概览

### 核心问题
你发现当前 plan-test skill 生成的测试计划存在**过多测试**的问题，主要表现为：
- 即使是简单的只读功能，也会建议并发、幂等、全量边界测试
- 所有任务都要跑全量历史端点冒烟测试
- 测试没有明确绑定到交付目标
- 无法判断哪些测试是真正必要的

### 优化方向
从"尽可能全面覆盖"转向"围绕最终交付目标的最小充分测试集"：
- **先证明用户目标 A 已交付**（delivery 测试）
- **再针对本次改动引入的风险补必要回归**（change-risk 测试）
- **其余测试标记为 exploratory**（不阻断交付）

---

## ✅ 已完成的优化（7项）

### 1. 修改 testcase-iterator.md（核心变更）
**文件**: `skills/plan-test/prompts/testcase-iterator.md`

**关键改动**:
- **任务目标**：从"挑战并增强"改为"验证并优化最小充分测试集"
- **核心原则**：每个 required testcase 必须能回答：
  * 它直接证明哪个 MUST AC？（delivery）
  * 它防止本次改动破坏哪个受影响的行为？（change-risk）
  * 无法回答 → 应标记为 exploratory（不 required）

- **条件测试触发**（不再无脑全量）：
  * 并发测试：**仅当存在共享可变状态时**
  * 幂等测试：**仅当有副作用且未实现幂等机制时**
  * 边界值测试：**仅当在 AC 声明的边界内时**
  * LLM 对抗测试：**仅当 `llm_payload_driven=true` 时**
  * 冷启动测试：**仅当 `stateful_init=true` 时**

- **新增"最小充分性审查"步骤**：
  * 检查无目标绑定的 required 测试
  * 检查重复证明同一 AC 的测试
  * 建议删除或降级为 exploratory

- **修改 PASS 标准**：
  * 所有 MUST AC 都有 testcase 覆盖
  * 所有 required testcase 都有明确的 AC/risk 绑定
  * **测试集是最小充分的（无冗余）**

### 2. 修改 config.md - Full Surface Smoke（分级策略）
**文件**: `skills/plan-test/config.md`

**关键改动**：将 FULL_SURFACE_SMOKE 从"全量强制"改为"三级分层"

| 级别 | 触发条件 | 范围 |
|------|---------|------|
| **critical-surface-smoke** | 所有交付（必做） | 少量核心历史入口 |
| **affected-surface-smoke** | 有 impact_paths 映射 | 受影响的端点 |
| **full-surface-smoke** | 高风险场景 | 全量历史端点 |

**高风险触发条件**：
- 路由层、公共基础设施、启动装配有改动
- 共享 provider、中间件、权限系统有改动
- 正式 release 前的完整验证
- 无 impact_paths 映射或映射不完整（fail-closed）

**效果**：单文件改动 + 明确 impact_paths → 只跑 critical + affected（大幅减少测试量）

### 3. 修改 config.md - Testcase 迭代策略（收敛机制）
**文件**: `skills/plan-test/config.md`

**关键改动**：
- **不再固定"至少两轮必须继续加内容"**
- **改为边际收益收敛**：
  * 第一轮：检查 AC 覆盖 + 关键风险 + 目标绑定
  * 第二轮：只审新增 diff 和未闭环的 obligation
  * 收敛条件：
    - 所有 MUST AC 都有 required testcase 覆盖
    - 所有 required testcase 都有明确的 AC/risk 绑定
    - 没有新增 required obligation
  * **只能新增 exploratory 时，不阻断定稿**

**效果**：防止为了凑轮数而继续堆测试

### 4. 创建 Test Obligation Matrix 文档（新概念）
**文件**: `skills/plan-test/checklists/test-obligation-matrix.md`

**内容**：
- **定义三种 obligation 类型**：
  | 类型 | 用途 | 是否 required |
  |------|------|--------------|
  | delivery | 直接证明 MUST AC | 是 |
  | change-risk | 防范受影响范围内风险 | 有明确风险绑定时是 |
  | exploratory | 额外边界、未来风险 | 否 |

- **Obligation Matrix 结构**：
  ```
  | obligation_id | type | ac_id | risk | min_decisive_test | required_reason |
  |---------------|------|-------|------|-------------------|-----------------|
  | TO-A1 | delivery | AC-A1 | — | 正常路径执行一次 | 直接证明目标 A |
  | TO-R1 | change-risk | AC-A1 | FAIL-ROUTE | 新路由可达 | 本次修改入口层 |
  | TO-E1 | exploratory | — | 潜在性能 | 压测 | 不阻断交付 |
  ```

- **判断指南和反模式示例**（防止滥用）

### 5. 更新 phase-A-acceptance.md（在需求定义时就明确测试义务）
**文件**: `skills/plan-test/phase-A-acceptance.md`

**关键改动**：
- **新增步骤 4c：测试义务矩阵**（所有任务必做）
- **在 acceptance.md 定义时就要求明确**：
  * 每个 test obligation 的类型、AC 绑定、风险绑定
  * 为什么这个测试是 required 的
  * 适用性判断（哪些情况下才需要并发/幂等/LLM对抗等测试）

- **更新 acceptance.md 模板**：增加 Test Obligation Matrix 表格
- **更新 DoD**：要求所有 delivery 和 change-risk obligation 都有对应 testcase

**效果**：测试义务在实现前就已明确，不是实现后倒推

### 6. 更新 phase-5-testcase.md（强制绑定 obligation）
**文件**: `skills/plan-test/phase-5-testcase.md`

**关键改动**：
- **步骤 1**：每个 testcase 必须明确绑定至少一个 test obligation
  ```markdown
  ## TC-001：正常查询
  **绑定**: TO-A1 (delivery)
  **AC**: AC-A1
  ```
- **步骤 4**（子代理迭代）：重点检查
  * 所有 MUST AC 是否都有 required testcase 覆盖
  * 所有 required testcase 是否都有明确的 obligation 绑定
  * 是否存在无法说明必要性的 required testcase
  * 测试集是否为最小充分集

**效果**：无目标绑定的测试无法通过 challenger 验证

### 7. 更新 phase-4-stage-gate.md（Gate 前置检查）
**文件**: `skills/plan-test/phase-4-stage-gate.md`

**关键改动**：
- **新增"昂贵层前置 1b：Test Obligation Matrix 验证"**
- **在 testcase 冻结后、执行昂贵测试前验证**：
  * acceptance.md 必须包含 Test Obligation Matrix
  * 每个 MUST AC 必须至少有一个 delivery obligation
  * 每个 required testcase 必须绑定至少一个 obligation
  * 不存在无法说明必要性的 required testcase

- **列出需要检查的诊断码**：
  * `AC_COVERAGE_MISSING`
  * `ORPHAN_REQUIRED_SCENARIO`
  * `UNJUSTIFIED_TEST_SCOPE`
  * `OBLIGATION_NOT_SATISFIED`

**效果**：在昂贵测试执行前就阻止无目标测试

---

## ⏳ 还需要完成的优化（3类）

### 🔶 需要 Python 代码实现

#### 1. 更新 Gate Validator（plan_test_gate.py）
**需要实现的诊断逻辑**：
- `AC_COVERAGE_MISSING`: MUST AC 没有 delivery testcase
- `ORPHAN_REQUIRED_SCENARIO`: required 场景既不绑定 AC，也不绑定 in-scope risk
- `UNJUSTIFIED_TEST_SCOPE`: 测试超出 acceptance/assurance 范围却被标为 required
- `OBLIGATION_NOT_SATISFIED`: 定义的 obligation 没有对应的 testcase

**实现需要**：
- 解析 acceptance.md 中的 Test Obligation Matrix（Markdown 表格）
- 解析 testcase 文件中的 obligation 绑定（`**绑定**: TO-xxx`）
- 验证绑定关系的完整性和一致性

#### 2. 更新 Schema（plan-test-run.schema.json）
**需要扩展的字段**：
```json
{
  "test_obligations": [
    {
      "obligation_id": "TO-A1",
      "type": "delivery|change-risk|exploratory",
      "ac_id": "AC-A1",
      "risk": "...",
      "required_reason": "..."
    }
  ],
  "scenarios": [
    {
      "scenario_id": "TC-001",
      "obligation_ids": ["TO-A1"],
      ...
    }
  ]
}
```

### 📝 需要文档更新

#### 3. 更新文档和示例
- **README.md**: 说明新的测试策略（目标导向 + 最小充分）
- **HANDOFF.md**: 说明 Test Obligation Matrix 的使用方法
- **创建示例 acceptance.md**: 展示完整的 Test Obligation Matrix
- **SKILL.md**: 说明新的测试收敛条件

---

## 📊 优化前后对比

### 优化前（coverage-maximizing）

**场景**：用户需要添加一个只读状态查询接口

**生成的测试**：
1. ✅ 正常查询（证明 AC）
2. ✅ 不存在资源的错误处理（证明 AC）
3. ❌ 并发写入测试（无写入操作，不需要）
4. ❌ 幂等性测试（无副作用，不需要）
5. ❌ 全量历史端点冒烟（单文件改动，过度）
6. ❌ 断电恢复测试（无持久化，不需要）
7. ❌ 跨版本迁移测试（无数据迁移，不需要）
8. ❌ 高并发压测（AC 无性能要求，不需要）
9. ❌ 长上下文稳定性（非 LLM 驱动，不需要）

**问题**：9 个测试中，只有 2 个真正证明交付目标，其余 7 个无必要但都标记为 required

### 优化后（goal-and-risk-driven）

**场景**：同样的只读状态查询接口

**Test Obligation Matrix（在 acceptance.md 中定义）**：
| obligation_id | type | ac_id | risk | required_reason |
|---------------|------|-------|------|-----------------|
| TO-A1 | delivery | AC-A1 | — | 直接证明正常查询功能 |
| TO-A2 | delivery | AC-A1 | — | 证明错误处理 |
| TO-R1 | change-risk | AC-A1 | FAIL-ROUTE | 新路由接入既有路由层 |
| TO-E1 | exploratory | — | 潜在性能 | 未来风险探索 |

**生成的测试**：
1. ✅ **TC-001: 正常查询** [绑定 TO-A1, delivery, required]
2. ✅ **TC-002: 不存在资源** [绑定 TO-A2, delivery, required]
3. ✅ **TC-003: 新路由可达** [绑定 TO-R1, change-risk, required]
4. ✅ **TC-004: 核心历史端点冒烟** [critical-surface-smoke, required]
5. 📝 **TC-E01: 高并发压测** [绑定 TO-E1, exploratory, **不 required**]

**结果**：
- Required 测试：从 9 个减少到 4 个
- 每个 required 测试都能说明它的必要性
- Exploratory 测试仍然可以写，但不阻断交付

---

## 🎯 质量保证

### 保留的严格机制（不降低质量）
- ✅ acceptance 唯一真相
- ✅ frozen oracle
- ✅ primary evidence
- ✅ UI 必须真实点击
- ✅ 正向价值必须真实达成
- ✅ 范围变化必须用户批准
- ✅ 不确定时 fail closed

### 优化的部分（提高效率）
- 从"尽可能全面"转向"最小充分"
- 从"所有任务全量冒烟"转向"分级冒烟"
- 从"固定轮次挑战"转向"边际收益收敛"
- 从"可选的 ac_ids"转向"强制的 obligation 绑定"

---

## 🚀 下一步行动

### 立即可用（已完成）
- ✅ testcase challenger 已按新标准工作
- ✅ Full Surface Smoke 已分级
- ✅ testcase 迭代已采用收敛机制
- ✅ Phase A/5/4 已要求 Test Obligation Matrix

### 需要进一步实现
1. **Python Gate Validator**（实现新诊断）
2. **JSON Schema 扩展**（支持 obligation 字段）
3. **文档和示例**（帮助用户理解新机制）

### 建议测试方式
1. 创建一个简单的示例任务（如只读查询接口）
2. 按新流程走一遍（Phase A → Phase 5 → Phase 4）
3. 观察生成的 Test Obligation Matrix 和 testcase
4. 验证 challenger 是否正确删除/降级无必要的测试
5. 验证 Gate 是否正确检查 obligation 绑定

---

## 📝 总结

### 优化核心
**从"尽可能发现所有问题"转向"证明用户目标已交付"**

### 关键机制
1. **Test Obligation Matrix**：在需求定义时就明确测试义务
2. **条件测试触发**：只在实际适用时才要求特定类型的测试
3. **最小充分性审查**：删除或降级无法说明必要性的测试
4. **分级冒烟测试**：根据改动风险选择冒烟范围
5. **边际收益收敛**：不为凑轮数而继续堆测试

### 预期效果
- **减少 50-70% 的无必要 required 测试**
- **每个测试都能回答"为什么必要"**
- **保持质量的同时提高效率**
- **让测试计划更聚焦于交付目标**

---

**优化完成日期**: 2026-08-16  
**文档版本**: v1.0  
**后续优化**: 待 Gate Validator 和 Schema 实现后完整闭环
