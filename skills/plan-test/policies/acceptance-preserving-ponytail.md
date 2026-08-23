# Acceptance-preserving Ponytail（验收保底最小化）

> 本文件是 plan-test / plan-bs / plan-task 中所有“最小化判断”的单一权威。
> 各阶段文档只引用本文件，不复制规则正文，避免规则漂移。

## 最高规则

**Acceptance is the floor; Ponytail minimizes everything above the floor.**

用户批准的验收标准是不可降低的下限；在不降低该下限的前提下，最小化计划、实现、依赖、测试和流程。

## 决策阶梯（按顺序判断）

0. **不得削减**：已批准 MUST AC、assurance contract 的必要控制、frozen black-box oracle、
   Test Obligation Matrix 中有 AC/risk 绑定的 required tests。
1. 这个任务真的需要存在吗？
2. 当前代码库是否已有可复用实现？
3. 标准库或平台原生能力是否已经支持？
4. 已安装依赖是否已经支持？
5. 能否删除、内联或减少文件？
6. 最后才写最小的自定义实现。

## 保护清单

- 信任边界输入校验
- 防止数据丢失的错误处理
- 安全、隐私和可访问性要求
- 明确要求的迁移、回滚和兼容性
- 有 AC/risk 绑定的 required tests

## 可删除或简化

- 未绑定任何 AC 或范围内风险的任务
- speculative abstraction（“将来可能用到”的抽象）
- 重复 helper、纯转发 wrapper、只有一个实现的 interface/factory
- 不必要的新依赖、新配置项和无决策价值的流程文档
- 可由标准库、平台原生能力或现有代码替代的实现

## 权威分离

- **Ponytail 回答**：还有没有不必要的复杂度？
- **Gate 回答**：已声明的 required AC 是否有可信证据闭环？

Final 门禁只按确定性事实判定，不受 minimality 结论影响；minimality pass 也无权宣布完成。

## 阶段模式

| 阶段 | 模式 | 作用 |
|------|------|------|
| phase-A / plan-bs | lite | 只提出更简单的选项，不自行删需求 |
| phase-1 | lite | 用 Complexity inventory 暴露并绑定新增复杂度 |
| phase-2 挑战循环 | off | challenger 专注遗漏与风险，避免与最小化互相制造 finding |
| phase-2 收敛后 | full | 单独跑一次 plan minimality pass，不循环 |
| phase-3 执行 | full | 在保护清单约束下做最小实现 |
| phase-3 便宜检查后 | full | 单独跑一次 diff minimality review |
| 测试设计 | full | required testcase 是能改变交付决定的最小决定性测试 |
| Final gate | off | 只按账本事实判定 |

## 应用规则

- `scope_change=false` 且 AC/risk 不受影响：可自动应用；
- 改变用户可见行为：只能作为用户选项提出；
- 降低 assurance：拒绝；
- 没有可删内容：结束，不凑轮次。

本 policy 取代 `FEATURE_POLICY = only-add` 中与重构冲突的部分。行为策略统一为
`BEHAVIOR_POLICY = preserve-approved`：不静默减少已批准外部行为，但允许删除、替换或重构内部实现，
以及删除 acceptance 明确批准删除的旧行为。
