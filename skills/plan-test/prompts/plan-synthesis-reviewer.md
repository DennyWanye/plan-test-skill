# 主代理工作提示：Plan challenge synthesis

这是主 agent 的确定性汇总清单，不派一个新 reviewer 来投票。先遵守
`references/challenge-orchestration.md`，输入 primary 结果、完整 cluster 账本和全部 specialist 输出。

按 stable ID 与结构根因去重；合并影响面；列出意见冲突并保留 open；把后续动作分类为
`plan-change`、`evidence`、`spike` 或 `scope-change-proposal`。不得改变 acceptance/assurance contract，
不得用多数意见关闭 finding，也不得把专项 agent 的自报结论当 authority。

记录到 gate 的 synthesis artifact 至少包含：

```json
{
  "source_cluster_ids": ["all-specialist-required-cluster-ids"],
  "canonical_findings": [],
  "resolved_finding_ids": [],
  "open_finding_ids": [],
  "decisions": [
    {
      "canonical_finding_id": "stable-id",
      "source_finding_ids": ["stable-id"],
      "action": "plan-change|evidence|spike|scope-change-proposal",
      "rationale": "evidence-backed decision"
    }
  ],
  "conflicts": [
    {
      "canonical_finding_id": "stable-id",
      "resolution": "evidence-backed conflict resolution; unresolved conflicts keep status=open"
    }
  ],
  "required_spikes": [],
  "plan_actions": []
}
```

Synthesis 入账后才修订 plan、运行 required spike；完成后派 closure challenger。
每个 specialist finding ID 必须进入 `canonical_findings`；每个 canonical finding 必须有一个
`decisions` 项。`open_finding_ids` 与 `resolved_finding_ids` 必须按 status 完整分区 actionable
findings，closure diff 也必须逐 ID 复核同一 canonical 集，不能靠省略 finding 收敛。Decision
必须有非空 `source_finding_ids`、合法 action 和 rationale；`evidence`/`spike` 分别绑定
`evidence_refs`/`spike_ids`。只要存在 `plan-change`，closure 的 plan hash 必须实际变化。
