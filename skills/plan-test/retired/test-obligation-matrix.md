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

## Obligation 类型与判断指南

### 1. delivery（交付证明，required）

- **用途**：直接证明用户目标的某条 MUST AC——正常路径、错误处理、AC 声明的边界行为。
- **示例**：目标 A 是新增一个只读状态查询接口 → TO-A1 正常查询能返回 A 规定的字段；
  TO-A2 目标不存在时返回 A 规定的错误。

### 2. change-risk（变更风险防护，有明确风险绑定时 required）

- **用途**：防止本次改动破坏受影响行为或关键不变量。何时适用：本次改动修改了入口层/路由、
  共享基础设施（序列化、中间件、provider）、可能影响既有功能的关键不变量，或有明确
  impact_paths 指向受影响范围。
- **示例**：新增接口接入了既有路由 → TO-R1 验证新路由真实可达；TO-R2 复测受影响的一个
  代表性既有接口。

### 3. exploratory（探索性测试，不 required，只做建议）

- **用途**：额外边界、未来风险、低概率场景。以下情况属于 exploratory 而非 required：
  并发（当没有共享可变状态时）、幂等（当没有副作用或已有幂等机制时）、边界值（当不在 AC
  声明的边界内时）、性能（当 AC 没有性能要求时）、恢复（当没有状态持久化时，如断电恢复）、
  迁移（当没有数据迁移时，如跨版本迁移）。

## Obligation Matrix 结构

| obligation_id | 类型 | AC | 风险 | 最小决定性测试 | required 原因 |
|---------------|------|----|----|---------------|--------------|
| TO-A1 | delivery | AC-A1 | — | 正常查询一次 | 直接证明目标 A |
| TO-A2 | delivery | AC-A1 | — | 不存在时的错误 | 证明错误处理 |
| TO-R1 | change-risk | AC-A1 | FAIL-ROUTE | 新路由 smoke | 本次修改入口层 |
| TO-R2 | change-risk | — | FAIL-SERIALIZE | 既有接口 smoke | 复用公共序列化层 |
| TO-E1 | exploratory | — | 潜在性能 | 压测 | 不阻断本次交付 |

## 使用流程

- **Phase A（acceptance 定义时）**：矩阵是 `acceptance.md` 的一部分，位于 AC 定义之后
  （字段与模板见 `phase-A-acceptance.md`）——测试义务在实现前就已明确，不是实现后倒推。
- **Phase 1（plan 时）**：在 `plan.md` 中引用测试义务，说明如何满足每个 obligation。
- **Phase 5（testcase 定义时）**：每个 testcase 必须绑定至少一个 obligation，头部格式：

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

- **Gate 验证**：`AC_COVERAGE_MISSING` / `ORPHAN_REQUIRED_SCENARIO` / `UNJUSTIFIED_TEST_SCOPE` /
  `OBLIGATION_NOT_SATISFIED`（各码含义见 phase-4“昂贵层前置 1b”）。

## 常见反模式

- ❌ **为了“全面”而测试**：无绑定的并发写入测试，理由只有“应该测试并发”——而目标是只读
  接口，没有并发写入风险。
- ❌ **测试超出目标范围**：“未来可能需要”的跨版本数据迁移测试——当前目标没有数据迁移，
  这是 exploratory。
- ❌ **重复测试同一个 AC**：三个测试（场景 1/2/3）都证明同一个 AC-A1 的正常路径，没有增量价值。
- ✅ **正确模式：最小充分测试集**：每个测试都有明确的目标绑定（TC-001→TO-A1、TC-002→TO-A2、
  TC-003→TO-R1），共同构成最小充分集。
