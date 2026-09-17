# Phase A — FULL 附录（仅 FULL / `MACHINE_GATE` 启用时读）

## assurance-contract.json
- FULL 路径额外生成与 `{ACCEPTANCE_FILE}` 同目录的 `assurance-contract.json`，每条使用稳定 ID。
- 默认 `profile=standard`，challenger 不得自行升级。
- `hardened`/`hostile-host`、可信边界变化必须用户明确确认。
- phase-A 出口：FULL 路径 acceptance 草案须附 `assurance-contract.json` 才进 phase-1。

结构：

```json
{
  "profile": "standard",
  "acceptance_ids": ["AC-1"],
  "protected_assets": [{"id": "ASSET-1", "description": "..."}],
  "trusted_assumptions": [{"id": "TRUST-1", "description": "..."}],
  "in_scope_failures": [{"id": "FAIL-1", "description": "..."}],
  "in_scope_adversaries": [],
  "out_of_scope_conditions": [{"id": "OOS-1", "description": "..."}],
  "maximum_acceptable_impact": "..."
}
```
