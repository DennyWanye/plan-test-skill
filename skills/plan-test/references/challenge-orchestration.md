# Plan challenge orchestration protocol

本 reference 只在 phase-2 的 plan 挑战循环中读取。派发子代理时，必须把本文件原文与对应的
role prompt 一起放入上下文包；子代理不自行全仓扫描。

## 固定流程

```text
primary breadth → specialist fan-out → synthesis → plan/spike 修订 → closure diff
```

- **Primary breadth**：一个 challenger 完成固定八维 coverage，找出主要矛盾、全部当前可发现的
  范围内 P0/P1，并按结构根因形成 `challenge_clusters`。
- **Specialist fan-out**：每个 `specialist_required=true` 的 cluster 由一个专项 challenger 深挖；
  一个 challenger 只处理一个 cluster。最多同时运行 4 个，超出时分批，不合并 cluster 来省调用。
- **Synthesis**：主 agent 合并 stable finding、裁决冲突，并把结论分类为 plan 修改、补证据、spike
  或 scope-change proposal。专项代理的自报 verdict 没有 authority。
- **Closure diff**：修订后由一个统一 challenger 只复核 open findings、修订 diff、专项结论冲突与
  patch-induced 风险。只有 architecture/scope/trust boundary/high-risk entry 发生重大变化时，
  才改做 `consolidated` review；历史 ID 和轮次始终保留。

即使 primary 没有产生 required cluster，也要记录空 cluster 集与 synthesis，之后才能 closure。
子代理数量不是质量指标；P2 默认不触发专项挑战，除非它影响多个 MUST AC 或高风险边界。

## 共同边界

- 唯一范围事实源是用户已批准的 `acceptance.md` 与 `assurance-contract.json`。不得自行扩大产品范围、
  保障等级、攻击者能力、失败域或 trusted boundary。
- 缺少足以形成 P0/P1 的上下文时，输出待补证据或 `scope-change-proposal`，不得猜测。
- `out-of-scope` 只能是 advisory；需要改变 contract 时输出 `scope-change-proposal`，等待用户批准。
- 同一结构根因只保留一个 stable finding ID，并列出全部影响面。后续换措辞不得换 ID。
- 新 finding 只有在根因确实独立时才新建 ID。第二轮后出现 `pre-existing` finding，必须解释
  `why_not_found_in_round_one`。
- 不得用修改 black-box oracle 绕过失败；行为变化仍须绑定用户批准。
- 追踪到 contract 声明的 trusted boundary 即停止，不做无范围依据的理论外推。
- 任何 reviewer 的 PASS/FAIL、新增数或完成度自报都没有 authority；gate 从 ledger 推导状态。

## Finding schema

所有角色输出的 `findings` 使用同一字段：

```json
{
  "id": "stable-lowercase-id",
  "severity": "P0|P1|P2",
  "scope_relation": "in-scope|out-of-scope|scope-change-proposal",
  "origin": "pre-existing|patch-induced|new-external-fact",
  "violated_acceptance_ids": ["AC-1"],
  "assurance_contract_ids": ["FAIL-1"],
  "evidence": "source pointer, reproduction, or raw spike artifact",
  "status": "open|resolved|advisory",
  "root_cause": "structural cause",
  "why_not_found_in_round_one": "required only for later pre-existing findings"
}
```

严重度：

- `P0`：阻止 required AC、造成超过 maximum impact 的副作用，或结构上不可执行；
- `P1`：会造成明显返工或验证缺口，但有确定修法；
- `P2`：不阻断的局部质量问题。

`P0/P1 + in-scope` 必须同时绑定 AC 与 assurance contract ID。复核已关闭 finding 时复用 ID 并将
`status` 改为 `resolved`。

## Cluster schema

Primary 输出的每个 cluster 使用：

```json
{
  "cluster_id": "cluster-public-api-boundary",
  "parent_finding_ids": ["public-api-not-executable"],
  "specialty": "architecture|data-state|failure-recovery|security-privacy|testability-evidence|release-rollback|performance-third-party",
  "question": "只描述要挑战的问题边界，不预设答案",
  "required_evidence": ["public exports", "runtime call chain"],
  "specialist_required": true
}
```

所有范围内 P0/P1 必须至少出现在一个 cluster 的 `parent_finding_ids` 中。Primary 只能在已有充分原始
证据、无需进一步判断时写 `specialist_required=false`。已标为 required 的 cluster 不得事后自行降级；
若确需跳过，`record-specialist-challenge --status waived` 必须同时记录理由和用户批准消息 SHA-256。

## Cross-cluster 与冲突处理

专项 challenger 遇到其他 cluster 的问题时，不重复创建 finding；只输出：

```json
{
  "cross_cluster_ref": "cluster-id",
  "finding_ids": ["stable-id"],
  "reason": "为什么会影响本 cluster"
}
```

Synthesis 负责去重与裁决。意见冲突未解决时，对应 canonical finding 保持 `open`；不得靠多数意见
关闭。需要真实运行才能决定时记录 required spike，spike 的命令与实际输出回写 plan 后再 closure。

## Gate integration contract

Phase-2 文档使用以下账本动作；具体机器语义以 `gate/PROTOCOL.md` 和 CLI `--help` 为准：

1. `start-challenge-loop --orchestration clustered` 启用新流程；默认 `legacy` 只用于兼容旧 ledger；
2. `record-challenge-round` 记录 primary breadth 或 closure diff/consolidated finding round；
3. `record-challenge-clusters` 紧接 primary round 1，记录 primary 产生的完整 cluster 集；
4. `record-specialist-challenge` 逐 required cluster 记录 `completed`；用户批准跳过时才记录 `waived`；
5. `record-challenge-synthesis` 记录 cluster 输入集合、canonical finding 决策和后续动作。

Gate 只在以下结构条件同时成立时允许 closure 后推导 `CONVERGED`：primary coverage 完整；所有
primary 范围内 P0/P1 已聚类；required specialist 全部完成或有用户批准的 waiver；synthesis 覆盖全部
required cluster；closure 后没有 open in-scope P0/P1；acceptance/contract hash 未静默变化。
Required spike 是否真实完成仍按本 phase 的原始证据规则审查，不能因 gate 结构状态而省略。
