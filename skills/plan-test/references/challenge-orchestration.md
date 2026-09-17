# Plan challenge orchestration protocol

挑战子代理的共同协议：派发时把本文件原文与对应 role prompt 一起放入上下文包；子代理不自行全仓扫描。主 agent 的流程与各阶段动作在 `challenge-main-agent.md`（LEAN 必读）。FULL 入账命令与 gate 集成见 `full/phase-2-iterate-plan.md`。

## 流程位置

`primary breadth → specialist fan-out → synthesis → plan/spike 修订 → closure diff`；各角色职责以对应 role prompt 为准。

## 共同边界

- 唯一范围事实源是用户已批准的 `acceptance.md` 与 `assurance-contract.json`。不得自行扩大产品范围、保障等级、攻击者能力、失败域或 trusted boundary。
- 上下文不足以形成 P0/P1 → 输出待补证据或 `scope-change-proposal`，不得猜测。
- `out-of-scope` 只能是 advisory；需改 contract 时输出 `scope-change-proposal` 等用户批准。
- 同一结构根因只保留一个 stable finding ID 并列全部影响面；换措辞不换 ID。
- 根因确实独立才新建 ID；第二轮后出现 `pre-existing` finding 必须填 `why_not_found_in_round_one`。
- 不得用修改 black-box oracle 绕过失败；行为变化仍须绑定用户批准。
- 追踪到 contract 声明的 trusted boundary 即停止，不做无范围依据的理论外推。
- 任何 reviewer 的 PASS/FAIL、新增数或完成度自报都没有 authority；状态由 gate 从 ledger 推导（LEAN 由主 agent 对照 findings 清单核对）。

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

- `P0`：阻止 required AC、造成超过 maximum impact 的副作用，或结构上不可执行；
- `P1`：会造成明显返工或验证缺口，但有确定修法；
- `P2`：不阻断的局部质量问题。

`P0/P1 + in-scope` 必须同时绑定 AC 与 assurance contract ID。复核已关闭 finding 时复用 ID 并将 `status` 改为 `resolved`。

## Cluster schema

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

所有范围内 P0/P1 必须至少出现在一个 cluster 的 `parent_finding_ids` 中。Primary 只能在已有充分原始证据、无需进一步判断时写 `specialist_required=false`。

## Cross-cluster 与冲突处理

专项 challenger 遇到其他 cluster 的问题时不重复创建 finding，只输出：

```json
{ "cross_cluster_ref": "cluster-id", "finding_ids": ["stable-id"], "reason": "为什么会影响本 cluster" }
```

Synthesis 负责去重与裁决。意见冲突未解决时对应 canonical finding 保持 `open`，不得靠多数意见关闭。需要真实运行才能决定时记录 required spike，spike 命令与实际输出回写 plan 后再 closure。
