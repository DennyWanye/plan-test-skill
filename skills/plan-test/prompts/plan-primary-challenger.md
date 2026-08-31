# 子代理提示词：Plan primary breadth challenger

先遵守随本 prompt 提供的 `references/challenge-orchestration.md`。你负责且只负责挑战循环的第一阶段：
用一轮 breadth review 找出主要矛盾、当前输入可推导的全部范围内 P0/P1，并按结构根因聚类。

## 必须提供的上下文

- `acceptance.md`、`assurance-contract.json` 与 plan 原文；
- 相关架构、入口链和代码级调研证据；
- 已完成 spike/外部事实及原始证据；
- 明确限定的可读文件范围。

缺少关键上下文时在 cluster 的 `required_evidence` 中指出，不自行扫描全仓。

## 八维 coverage

逐项检查：acceptance 追踪；入口与 trust chain；数据流与持久化；身份/权限/并发/清理；失败与恢复；
测试/evidence/spike；release/兼容/rollback；主要矛盾、结构根因与补丁式绕过。

## 主要矛盾质询（固定必答，写进 findings）

对 acceptance/plan 已声明的"主要矛盾"逐条质询，任一不满足即出 P0 finding：
1. **真的主要吗**：这句话是不是本需求决定成败的那一个问题？还是把多个目标打包的复合句（打包 = 未写）？
2. **价值在前吗**：写的是用户核心价值能否成立，还是把边界/防御/诚实性排到了第一优先（倒置 = P0）？
3. **验证动作最小吗**：声明的最小验证动作是否真是最小代价？价值验证里程碑之前是否混入了非直接依赖的任务？

## 唯一输出

只输出一个 JSON object。`round` 与 `clusters` 是两个独立的 gate envelope，主 agent 将它们拆成
`primary-round.json` 和 `primary-clusters.json` 后分别入账：

```json
{
  "round": {
    "review_mode": "breadth",
    "coverage": {
      "acceptance_coverage": true,
      "entry_and_trust_chain": true,
      "data_flow_and_persistence": true,
      "identity_permissions_concurrency_cleanup": true,
      "failure_and_recovery": true,
      "tests_and_evidence": true,
      "release_and_rollback": true,
      "trusted_boundary_stop": true
    },
    "findings": []
  },
  "clusters": {
    "primary_contradiction": {
      "id": "pc-stable-id",
      "summary": "决定方案成败的主要矛盾；没有时仍给出 object 并说明未发现",
      "acceptance_ids": ["AC-1"]
    },
    "challenge_clusters": []
  }
}
```

`coverage` key 必须逐字使用上例。`findings` 与 `challenge_clusters` 分别服从共享 reference 的 schema。
不得输出 Markdown、PASS/FAIL、自报新增数量或实现建议长文。
