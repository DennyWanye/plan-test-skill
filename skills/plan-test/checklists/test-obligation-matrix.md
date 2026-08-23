# Test Obligation Matrix（测试义务矩阵）

## 目的

明确每个 required testcase 的必要性，防止无目标测试膨胀。每个 required testcase 必须能回答：
- 它证明哪个交付目标？
- 绑定哪条 AC？
- 防止哪个范围内失败？
- 为什么自动化/静态检查不能替代它？
- 如果不执行，哪个交付结论会无法成立？

## 最小决定性原则

规则权威见 `../policies/acceptance-preserving-ponytail.md`。required testcase 必须是能改变交付决定的
最小决定性测试。

应删除或降级为 exploratory：无 AC/risk 绑定、重复证明同一事实而无额外故障检测能力、仅为“更全面”
加入，以及 LEAN 路径下与本次改动无关的性能/恢复/并发/迁移测试。

不得删除：覆盖不同信任边界、不同业务终态、正向价值与负向安全、不同迁移路径或权限角色的测试，
以及随机系统所需的独立采样。

## Obligation 类型

### 1. delivery（交付证明）
- **用途**：直接证明用户目标的某条 MUST AC
- **是否 required**：是
- **示例**：
  - 目标 A：新增一个只读状态查询接口
  - Obligation TO-A1: 正常查询能返回 A 规定的字段
  - Obligation TO-A2: 目标不存在时返回 A 规定的错误

### 2. change-risk（变更风险防护）
- **用途**：防止本次改动破坏受影响行为或关键不变量
- **是否 required**：有明确风险绑定时是
- **示例**：
  - 改动：新增接口接入了既有路由
  - Obligation TO-R1: 验证新路由真实可达
  - Obligation TO-R2: 复测受影响的一个代表性既有接口

### 3. exploratory（探索性测试）
- **用途**：额外边界、未来风险、低概率场景
- **是否 required**：否，只做建议
- **示例**：
  - 高并发测试（当目标 A 没有写入、状态机）
  - 断电恢复测试（当目标 A 没有持久化）
  - 跨版本迁移测试（当目标 A 没有数据迁移）

## Obligation Matrix 结构

| obligation_id | 类型 | AC | 风险 | 最小决定性测试 | required 原因 |
|---------------|------|----|----|---------------|--------------|
| TO-A1 | delivery | AC-A1 | — | 正常查询一次 | 直接证明目标 A |
| TO-A2 | delivery | AC-A1 | — | 不存在时的错误 | 证明错误处理 |
| TO-R1 | change-risk | AC-A1 | FAIL-ROUTE | 新路由 smoke | 本次修改入口层 |
| TO-R2 | change-risk | — | FAIL-SERIALIZE | 既有接口 smoke | 复用公共序列化层 |
| TO-E1 | exploratory | — | 潜在性能 | 压测 | 不阻断本次交付 |

## 使用流程

### Phase A：acceptance 定义时

在 `acceptance.md` 中定义测试义务矩阵：

```markdown
## Test Obligations

| obligation_id | type | ac_id | risk | min_decisive_test | required_reason |
|---------------|------|-------|------|-------------------|-----------------|
| TO-A1 | delivery | AC-A1 | — | 正常查询 | 直接证明目标 |
| TO-A2 | delivery | AC-A1 | — | 错误查询 | 证明错误处理 |
| TO-R1 | change-risk | AC-A1 | FAIL-ROUTE | 路由可达 | 修改入口层 |
```

### Phase 1：plan 时

在 `plan.md` 中引用测试义务，说明如何满足每个 obligation。

### Phase 5：testcase 定义时

每个 testcase 必须绑定至少一个 obligation：

```markdown
## TC-001：正常查询

**绑定**: TO-A1 (delivery)
**AC**: AC-A1
**类型**: required

### 步骤
1. 调用 GET /api/status/123
2. 验证返回 200
3. 验证包含字段 id, status, created_at
```

### Gate 验证

Gate 检查以下诊断：

1. **AC_COVERAGE_MISSING**: MUST AC 没有 delivery testcase
2. **ORPHAN_REQUIRED_SCENARIO**: required 场景既不绑定 AC，也不绑定 in-scope risk
3. **UNJUSTIFIED_TEST_SCOPE**: 测试超出 acceptance/assurance 范围却被标为 required
4. **OBLIGATION_NOT_SATISFIED**: 定义的 obligation 没有对应的 testcase

## 判断指南

### 何时应该是 delivery（required）

- 直接证明 MUST AC 的正常路径
- 直接证明 MUST AC 的错误处理
- 证明 AC 声明的边界行为

### 何时应该是 change-risk（条件 required）

- 本次改动修改了入口层/路由
- 本次改动修改了共享基础设施（序列化、中间件、provider）
- 本次改动可能影响既有功能的关键不变量
- 有明确的 impact_paths 指向受影响范围

### 何时应该是 exploratory（不 required）

- 并发：当没有共享可变状态时
- 幂等：当没有副作用或已有幂等机制时
- 边界值：当不在 AC 声明的边界内时
- 性能：当 AC 没有性能要求时
- 恢复：当没有状态持久化时
- 迁移：当没有数据迁移时

## 常见反模式

### ❌ 反模式 1：为了"全面"而测试

```markdown
## TC-050：并发写入测试
**绑定**: 无
**原因**: "应该测试并发"
```

问题：目标 A 是只读接口，没有并发写入风险。

### ❌ 反模式 2：测试超出目标范围

```markdown
## TC-080：跨版本数据迁移
**绑定**: 无
**原因**: "未来可能需要"
```

问题：当前目标没有数据迁移，这是 exploratory。

### ❌ 反模式 3：重复测试同一个 AC

```markdown
## TC-010：正常查询 - 场景 1
## TC-011：正常查询 - 场景 2  
## TC-012：正常查询 - 场景 3
```

问题：三个测试都证明同一个 AC-A1 的正常路径，没有增量价值。

### ✅ 正确模式：最小充分测试集

```markdown
## TC-001：正常查询
**绑定**: TO-A1 (delivery, AC-A1)

## TC-002：不存在的资源
**绑定**: TO-A2 (delivery, AC-A1)

## TC-003：新路由可达性
**绑定**: TO-R1 (change-risk, FAIL-ROUTE)
```

每个测试都有明确的目标绑定，共同构成最小充分集。

## 与 acceptance.md 的关系

Test Obligation Matrix 是 acceptance.md 的一部分，位于 AC 定义之后：

```markdown
# Acceptance Criteria

## MUST

### AC-A1：状态查询接口
...

## Test Obligations

（此处定义测试义务矩阵）
```

这样确保测试义务在实现前就已经明确，而不是实现后倒推。
