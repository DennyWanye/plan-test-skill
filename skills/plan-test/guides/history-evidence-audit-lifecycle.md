# evidence-audit-lifecycle 瘦身移出的内容（SL-3；存档非规范）

- 最低 contract 按场景类型合并，是为了避免"八套重复 evidence 模板"。
- `--metadata` 示例 JSON（原 §2）：`{"producer_type":"runtime-probe","producer_version":"probe-v2","artifact_kind":"business-result","generated_at":"2026-08-24T01:02:03Z","root_run_id":"run-123","session_id":"session-456","business_facts":{"business_terminal":"completed+valid","result_sha256":"..."}}`
- active-run registry 回写 receipt digest 的动机：仓库有一个低成本、可机器读取的"当前候选 + 最新有效 receipt"入口。
