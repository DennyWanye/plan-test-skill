# Acceptance-preserving Ponytail（验收保底最小化）

最小化判断单一权威，他处只引用。

**Acceptance is the floor; Ponytail minimizes everything above the floor.** 验收不降，最小化计划/实现/依赖/测试/流程。

## 阶梯（按序）

0. 不得削减：MUST AC、assurance contract 必要控制、frozen black-box oracle、Test Obligation Matrix 中 AC/risk 绑定的 required tests。
1. 任务真需要存在？ 2. 代码库已有可复用实现？ 3. 标准库/平台原生已支持？ 4. 已装依赖已支持？ 5. 能删除、内联或减少文件？ 6. 最后才写最小自定义实现。

- **保护**：信任边界输入校验；防数据丢失的错误处理；安全/隐私/可访问性；要求的迁移/回滚/兼容；AC/risk 绑定的 required tests。
- **可删**：未绑定 AC/范围内风险的任务；speculative abstraction；重复 helper、纯转发 wrapper、单实现 interface/factory；多余依赖/配置项/无决策价值流程文档；标准库/原生/现有代码可替代的实现。
- **权威分离**：Ponytail 管多余复杂度；Gate 管 required AC 证据闭环。Final 门禁只按确定性事实判定；minimality 无权宣布完成。

## 阶段模式

- lite（只提更简单选项，不删需求）：phase-A / plan-bs；phase-1 用 Complexity inventory 绑定新复杂度。
- off：phase-2 挑战循环（challenger 专注遗漏风险）；Final gate。
- full：phase-2 收敛后一次 plan minimality pass（不循环）；phase-3 执行守保护清单最小实现；phase-3 便宜检查后一次 diff minimality review；测试设计：required testcase = 能改变交付决定的最小决定性测试。

## 应用

`scope_change=false` 且 AC/risk 不受影响 → 自动应用；改变用户可见行为 → 只作用户选项；降低 assurance → 拒绝；无可删 → 结束，不凑轮次。
取代 `FEATURE_POLICY = only-add` 中与重构冲突的部分；`BEHAVIOR_POLICY` 见（RULES R13）。
