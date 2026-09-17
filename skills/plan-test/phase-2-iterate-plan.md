# Phase 2 — 迭代 plan + 锁定绿色基线

目标"100% 代码可执行" + 绿色基线。FULL（`MACHINE_GATE`）入账见 `full/phase-2-iterate-plan.md`；条件细则见 `conditional/phase-2-iterate-plan.md`（下称 conditional）。

切片（`references/delivery-slices.md`）：先挑战整体 AC 归属、依赖、架构/可行性/重大成本假设，再挑战当前片；代码级收敛只针对当前片，不得缺整体 AC 或藏全局风险。进下一片前补足其调查、spike、挑战、基线差异检查。

## A. 迭代 plan

### 挑战范围（重点论）

- 主要矛盾相关（决定性 AC 任务、解法核心链路）→ 完整四阶段，到无 open P0/P1。
- 其余（次要 AC、外围）→ 一轮 primary breadth，无 in-scope P0 即收，不派 specialist、不多轮 closure，这轮不许跳过；出 in-scope P0 或与主要矛盾解法结构耦合 → 升完整范围。
- 增量补丁（已上线功能只动已有次要 AC，不新增/不改决定性 AC 行为）→ primary + closure 各一轮，决定性 AC 只回归。
- challenger 固定质询：主要矛盾写成复合句、防御排第一 = P0 打回；是否用补丁绕过真架构问题。

### 记账与编排（LEAN）

- 不用 gate 记账：findings 存 `round-N-findings.json` / `closure-N.json`，主 agent 自维护 open/resolved 清单；3/5/8 轮出口人判（RULES R9）。首轮可用标明待决项的草案，实现前核对授权或合并 review（RULES R11）。
- 派子代理给 `references/challenge-orchestration.md` 原文 + role prompt + 最小上下文包，不抄规则进 prompt；流程与各阶段动作见 `references/challenge-main-agent.md`。
- primary → specialist → synthesis → closure；specialist/closure 只围绕主要矛盾 cluster。closure 仍有 open P0/P1、出现新主要结构根因或需 architecture reset → 立即升级 FULL。

### 收敛判据（当前片全满足才实施）

0. 每片承诺经实际入口可验，前片产物可用，整体 MUST AC 无漏；底层准备不冒充交付，只有 mock 不证明真实入口。
1. Primary coverage 完整，范围内 P0/P1 均进 root-cause cluster。
2. required cluster 均完成专项，或有理由 + 用户批准 hash 的 waiver。
3. Synthesis 已记录、冲突已裁决、required spike 已成显式动作。
4. 关键假设（含 phase-1 清单）有 spike 实测（命令+输出）在 plan，新暴露的当轮补；"理论可行"不算；spike 即弃。
5. Closure 完成，open in-scope P0/P1 为零。
6. 当前片代码层已真读并写进 plan（怎么做、为什么），改动点确认到代码级；不确定项不许模糊收尾，调研闭环补回 plan。
7. 功能可达预期且满足 `BEHAVIOR_POLICY = preserve-approved`（RULES R13）。
8. 无绕过真架构问题的补丁式收尾。
9. acceptance/assurance contract 无未批准变化。
10. 不打无把握之仗：逐任务核对假设已 spike、现状已真读，没把握回去补，不靠开工后回炉。

收敛不靠 reviewer PASS 或轮数：LEAN 主 agent 逐条核对，FULL 由 gate 推导。

### 强约束：真架构问题优先重构

- 判定须证据全中：根因在结构层、补丁造技术债、同类会复发。
- 命中 → 写最佳实践结构改法 + 适配分析，禁"临时绕过/hack/TODO 再重构"；不受 preserve-approved 阻挡（保已批准行为 + 回归兜底）。
- 范围闸：显著超原需求 → 列补丁 vs 重构代价，标 BLOCKED 请用户拍板（plan-bs 直接讨论）；可控直接纳入。局部实现问题改对即可。

### 行为契约与 oracle

- 触及易混实体或改变既有行为 → 定稿前做 conditional §行为契约。
- 每个 AC 预期结果先于实现写下；frozen oracle 删/反转/放宽走批准（RULES R3）。

### Minimality pass（收敛后、用户 review 前，只一次）

不与正确性挑战混跑；`MODE: plan-pass` 存 `minimality-plan-pass.json`，只自动应用不改范围/行为/assurance 的建议，无建议即结束。步骤见 orchestration reference §Minimality pass。

### 定稿

需确认时一并展示 acceptance、行为差异、plan、决策简报并等（R11；按 `checklists/handoff.md` 轻量评估 + 表 1 原话对照）；已授权覆盖则直接定稿。写 `<!-- plan-status: finalized -->` 并记真实授权来源与范围，不自造批准记录。

## B. 锁定绿色基线（执行前必做）

1. 首片改代码前跑 build、测试、lint/类型检查并记录。大仓（测试文件 ≥200 或单套件 >5 分钟）→ conditional §大仓基线。
2. 基线已红 → 先如实告知用户，区分本次回归与既有；既有红记失败签名，新红永远阻断。
3. 快照（命令、结果摘要、状态/签名文件路径）存 `baseline.md`。
4. 后续片按内容身份与影响范围查差异、补 smoke；身份未知或新风险才扩大，不机械重跑（RULES R8）。

## 出口

plan 定稿且授权覆盖 + 绿色基线已记录 → phase-3。
