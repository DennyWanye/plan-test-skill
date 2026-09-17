# 挑战循环：主 agent 流程与动作

phase-2 挑战循环时读（LEAN 必读）。子代理共同边界、finding/cluster schema、冲突处理在 `challenge-orchestration.md`，派发时随 prompt 原文附上。

## 固定流程

```text
primary breadth → specialist fan-out → synthesis → plan/spike 修订 → closure diff
```

- **Primary breadth**：一个 challenger 完成固定八维 coverage，找出主要矛盾与全部当前可发现的范围内 P0/P1，按结构根因形成 `challenge_clusters`。
- **Specialist fan-out**：每个 `specialist_required=true` 的 cluster 由一个专项 challenger 深挖；一个 challenger 只处理一个 cluster。最多同时 4 个，超出分批，不合并 cluster 省调用。
- **Synthesis**：主 agent 合并 stable finding、裁决冲突，结论分类为 plan 修改 / 补证据 / spike / scope-change proposal。专项代理自报 verdict 没有 authority。
- **Closure diff**：修订后由一个统一 challenger 只复核 open findings、修订 diff、专项结论冲突与 patch-induced 风险。只有 architecture/scope/trust boundary/high-risk entry 重大变化时才改做 `consolidated` review；历史 ID 和轮次始终保留。

primary 没产生 required cluster 也要记录空 cluster 集与 synthesis，之后才能 closure。子代理数量不是质量指标；P2 默认不触发专项挑战，除非影响多个 MUST AC 或高风险边界。

## 主 agent 动作（各阶段）

1. **Primary**：派一个 `{CHALLENGER_ENGINE}` + `prompts/plan-primary-challenger.md`。Primary 不得把预设修法写成 cluster 问题要专项代理背书。
2. **Specialist**：每个 required cluster 派一个 `{CHALLENGER_ENGINE}` + `prompts/plan-specialist-challenger.md`，只给该 cluster、parent findings、相关 contract 原文、`required_evidence`。`specialist_required=false` 不派；required 不得事后自行降级，确需跳过须用户明确批准并记录理由与原始消息 SHA-256（waiver）。
3. **Synthesis**：主 agent 按 `prompts/plan-synthesis-reviewer.md` 合并，不是再派 reviewer 投票。记录 synthesis 前不得改 plan 后直接进 closure；记录后修订 plan，关键技术假设先跑真代码 spike，命令与实际输出回写 plan。
4. **Closure**：派一个 `{CHALLENGER_ENGINE}` + `prompts/plan-closure-challenger.md`；只复核 open findings、当前 diff、专项冲突、patch-induced 风险和 primary 不可知的新事实，不无理由重做全量 breadth。通常 `review_mode=diff`，改 consolidated 按上文条件。仍有 open P0/P1 → 修订后继续 closure 轮，不重跑无关 specialist；暴露新主要结构根因 → scope audit 或 architecture reset，不用局部补丁强行收敛。

## Minimality pass

Gate/主 agent 判定收敛后、用户 review 前只跑一次；正确性 challenger 与最小化 reviewer 不在同一轮混跑。

1. 派子代理读 `prompts/minimality-reviewer.md`，声明 `MODE: plan-pass`；上下文只附定稿 plan、acceptance、assurance contract 与 Ponytail policy。
2. JSON 存 plan 目录 `minimality-plan-pass.json`。
3. 仅自动应用 `scope_change=false`、不改变用户行为、不降低 assurance 且保持 AC/risk 覆盖的建议；用户可见行为变化仅带入 review 作为选项。
4. 修改后同步 AC/任务映射，不得制造 MUST AC 覆盖空洞。无建议即结束，不循环、不凑 finding。
