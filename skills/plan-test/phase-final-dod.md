# Phase 收尾 — Definition of Done + 文档回写

**目的**：合上闭环。全部勾选才宣布完成；并把文档回写，让下次从最新基线起步。

## DoD 清单（全绿才算完成——每条必须附证据，不许口头打勾）

> **逐条列出并在每条后附证据位置**（文件路径 / 截图 / log 行 / 命令输出）。任何一条附不上证据 → 标 BLOCKED 升级，**不得宣布完成**。"我确认过了""逻辑上没问题""同类已验证"都不算证据。

- [ ] `{ACCEPTANCE_FILE}` 全部"必须"条款都有测试证据通过 —— 证据：phase-4 ①b **兑现表**（每条 AC 一行；含 UI 的须有真机 MCP 证据）
- [ ] 无回归：构建/测试/lint/类型检查不低于 phase-2 绿色基线 —— 证据：命令输出对比
- [ ] 测试已按策略路由完成：UI 走 MCP 真人测试，逻辑走脚本，两者皆有则都做 —— 证据：兑现表**无 ❌、无未经用户批准的降级**
- [ ] 幂等性审查清单已逐条过 —— 证据：`checklists/idempotency-review.md` 逐条结论
- [ ] 可追溯矩阵无断点：AC ↔ 任务 ↔ 代码 ↔ testcase ↔ 场景 ↔ root run ↔ 证据 ↔ 终态 —— 证据：终审 auditor VERDICT（含场景计数摘要）
- [ ] testcase 已存盘、index.md 与 README 已同步、脚本已纳入回归套件 —— 证据：文件路径

**真人测试广度硬门**（输入语义敏感功能，任一不满足 → DoD FAIL；确定性 UI 不适用）：

- [ ] 场景矩阵中全部 required 场景 100% 执行，每个至少 1 次真实 UI root run —— 证据：phase-4 ①c **覆盖账本** + 截图/log
- [ ] distinct scenario 执行数 ≥ 矩阵 required 数，且 ≥ `{MANUAL_MIN_DISTINCT_CLASSES}` —— 证据：账本汇总计数行
- [ ] retry/重放/改写/continuation 未被计入 distinct 数 —— 证据：账本分列计数（auditor 已复核）
- [ ] required 行无 PENDING/PARTIAL/NOT RUN —— 证据：账本状态列全 ✅
- [ ] 状态一致：README / 详细 testcase 头 / RESULTS / 可追溯矩阵 / Gate 报告五处口径相同 —— 证据：phase-5 状态一致性审查结论
- [ ] 未执行项仅有两种合法来源：acceptance 预标 optional/out-of-scope，或用户 chat 显式批准缩减（已回写 acceptance；交付结论按**缩减后范围**表述，不得写成原范围全绿）—— 证据：acceptance 范围节 + 用户批准记录

> **末尾自检（长任务尤其做）**：宣布完成前回看 phase-4 兑现表——有没有把 required UI 测试悄悄换成代码审计？有没有"环境受阻就找了个等价替代而没升级"？有没有把同一个问题的多次重跑写成"多场景验收充分"？只要有一条这样，就不是 100%，回去补或标 BLOCKED。

## 文档回写（闭环回到 phase-0）

- 代码改完后，`{ARCH_DIR}/ARCHITECTURE.md` 可能又过期：更新它，使其反映新架构。
- 更新 README / changelog（若项目维护）。
- 这样下次跑本 skill 时，phase-0 从最新基线开始，闭环真正合上。

## 升级与交付

- 任何 DoD 项无法达成 → 标记 BLOCKED，说明卡点，交给用户决策，**不谎报完成**。
- 全绿 → 输出最终总结：做了什么、覆盖哪些 AC、测试证据在哪、文档更新在哪、回归套件新增了什么。
