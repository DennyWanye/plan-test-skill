# Evidence、Manifest 与 Audit 生命周期

在需要编译 gate manifest、声明场景证据契约、处理结构化审计 finding，或启用 active-run
绑定时读取本文件。机器语义以 `gate/PROTOCOL.md` 和 `plan_test_gate.py` 为准；这里给出最小输入格式。

## 1. 从结构化 spec 编译 manifest

不要解析 Markdown 来猜 AC/testcase 映射。维护一份 `verification-spec.json`，再由 gate 生成
`manifest.json`：

```bash
python {GATE_SCRIPT} compile-manifest \
  --spec verification-spec.json \
  --output manifest.json
```

spec 必须包含：

```json
{
  "acceptance_file": "acceptance.md",
  "assurance_contract": "assurance-contract.json",
  "testcase_inventory": "testcase/index.json",
  "reuse_report": "verification/run-x/testcase-reuse-report.json",
  "obligations": [
    {"obligation_id": "TO-1", "ac_ids": ["AC-1"]}
  ],
  "scenarios": [
    {
      "scenario_id": "S-1",
      "required": true,
      "testcase_ids": ["TC-1"],
      "gate_type": "positive-value",
      "evidence_contract": {
        "producer_types": ["gate-exec", "runtime-probe"],
        "required_artifact_kinds": ["execution-log"],
        "required_identity": ["root_run_id", "session_id"],
        "required_timestamps": true,
        "required_business_facts": ["business_terminal"]
      }
    }
  ],
  "manifest": {
    "repo_root": ".",
    "source_request_text": "...",
    "applicability": {},
    "release_unit": {}
  }
}
```

`assurance-contract.json.acceptance_ids` 必须被 obligations 覆盖；每条 obligation 必须在 reuse
report 中选中有效 testcase；选中的 testcase 必须存在于 inventory，并至少映射到一个 scenario。
编译器把输入 hash、选中的 testcase 和完整 required case set 写入 `compiled_manifest`，并生成覆盖
scenarios/testcase_files/严格模式开关的 canonical seal。`init` 重算 seal 并再次确认 required scenarios
与 `case_sets.full` 完全相等，不能同步截短两份集合后用任意子集开账。

`testcase_inventory` 中相对 testcase path 以 inventory 文件所在目录为基准。其余 spec 路径按
执行命令时的当前目录解析；因此应从项目根执行，或使用绝对路径。

## 2. 场景级 evidence contract

`evidence_contract` 是统一结构。`compile-manifest` 对每个 required 场景强制要求 contract；只有
未经过 compiler 的旧 1.x raw manifest/ledger 才保留“无 contract”的兼容行为。字段按实际证明需求
声明，不要因为模板方便而要求无意义的 identity。

- `producer_types`：至少一份 primary evidence 的 producer 必须在允许集合中；其余 contract 字段
  也只从可信 producer 的记录计算，不能跨不可信记录拼接洗白。
- `required_artifact_kinds`：所列 artifact kind 必须全部出现。
- `required_identity`：所列 evidence 顶层字段至少在一份 primary evidence 中非空。
- `required_timestamps: true`：至少一份 primary evidence 有 `generated_at`。
- `required_business_facts`：所列 key 必须出现在 primary evidence 的 `business_facts` 中且值非空。

Compiled required scenario 的最低 contract 不是空 object：producer/artifact 集合必须非空，identity
必须含 `root_run_id`，并要求 timestamp。`positive-value` 额外要求 `business-result` artifact 与
`business_terminal` fact；UI 额外要求 `ui-capture` 与 `session_id`；包含 `temporal-fault` lane 的
场景额外要求 `fault-recovery-log` 与 `recovered_state`。这些是按场景类型合并的最低证明，不是八套
重复 evidence 模板。

手工 attach/import 时，把 provenance 放在 JSON 文件，通过 `--metadata` 入账：

```json
{
  "producer_type": "runtime-probe",
  "producer_version": "probe-v2",
  "artifact_kind": "business-result",
  "generated_at": "2026-08-24T01:02:03Z",
  "root_run_id": "run-123",
  "session_id": "session-456",
  "business_facts": {
    "business_terminal": "completed+valid",
    "result_sha256": "..."
  }
}
```

```bash
python {GATE_SCRIPT} attach-evidence --run-dir <run-dir> \
  --path artifacts/result.json --kind primary --scenario S-1 \
  --metadata evidence-metadata.json
```

metadata 只接受 `producer_type`、`producer_version`、`artifact_kind`、`generated_at`、
`root_run_id`、`session_id` 和 object 类型的 `business_facts`；未知字段会被拒绝。
`record-run --exec` 会自动生成 `producer_type=gate-exec`、`artifact_kind=execution-log` 和时间戳，
并从 `--run-id-under-test`、`--session-id`、`--business-terminal` 映射其余 metadata。

contract 不检查 JSON “看起来像不像原始证据”，也不把 `--kind primary` 当作充分证明。缺 primary、
producer 不可信或 contract 字段不足分别产生 `PRIMARY_EVIDENCE_MISSING`、
`EVIDENCE_PRODUCER_UNTRUSTED`、`EVIDENCE_CONTRACT_UNSATISFIED`。

## 3. 结构化 audit findings

`auditor-output.json` 可在 verdict 之外提供：

```json
{
  "verdict": "FAIL",
  "findings": [
    {
      "id": "audit-memory-lineage",
      "severity": "P1",
      "status": "open",
      "type": "evidence",
      "summary": "缺少跨重启 lineage 证据",
      "ac_ids": ["AC-3"],
      "scenario_ids": ["S-3"],
      "required_retest": true
    }
  ]
}
```

`audit` 会原子导入 JSON findings；无需另跑 import 命令。Compiled 1.5 workflow 强制结构化 JSON，
且 FAIL 至少有一个 open/deferred finding；Markdown 末行格式只为旧 raw ledger 保留兼容读取。
`required_retest=true` 必须绑定非空 scenario_ids，P0/P1 必须绑定 AC 或 scenario。JSON 中 PASS 与
open/deferred P0/P1 并存会被拒绝；账本中存在 open/deferred P0/P1 时，`OPEN_AUDIT_FINDINGS` 阻止通过。

整改循环：

```bash
python {GATE_SCRIPT} list-audit-findings --run-dir <run-dir>

# 修复并补证据；required_retest=true 时，先给 finding 绑定的每个 scenario 追加 fresh root PASS
python {GATE_SCRIPT} resolve-audit-finding --run-dir <run-dir> \
  --finding-id audit-memory-lineage \
  --resolution "补齐跨重启探针和 lineage 断言" \
  --evidence-ids ev-abc123
```

resolution 必须绑定至少一个当前 ledger evidence ID，并记录修复时的 candidate content digest；
它会改变 ledger fact，因此旧 audit 自动 stale。闭环后必须重新生成 auditor 输入/输出并
再次执行 `audit`；最终 PASS audit 应输出空 findings，或只含 resolved/P2 项。

## 4. Active run（显式 opt-in）

并行 slice 不会被 `init` 自动抢占。`compile-manifest` 对真实交付默认设置
`active_run_required: true`；旧 raw manifest 只有显式开启时才启用。validator 要求
`.plan-test/active-run.json` 精确绑定本 run：

```bash
python {GATE_SCRIPT} activate-run --run-dir <run-dir>
```

registry 绑定 repo-relative run-dir、run ID、acceptance hash 和候选内容 digest。`re-attest` 改变候选
内容后必须再次 `activate-run`。启用时 gate 只把精确的 `.plan-test/active-run.json` 排除在内容
指纹之外，并在 receipt 的 `exclusion_scope` 中显示；不会排除整个 `.plan-test/`。`finalize`
成功后还会把 `latest_valid_receipt_digest/path` 回写到同一 registry，因此仓库有一个低成本、
可机器读取的“当前候选 + 最新有效 receipt”入口。

## 5. Artifact 逻辑去重

Evidence 文件仍保留原路径，不移动到内容寻址目录。Receipt 的 `evidence_summary` 按已有 SHA-256
计算：

- `records`：evidence record 数；
- `distinct_artifacts`：不同内容 hash 数；
- `distinct_root_runs`：不同 root run identity 数；
- `shared_artifact_sha256`：被多个 evidence record 引用的内容 hash。

同一日志复制到多个路径可以有多条 record，但只算一个 distinct artifact。不要用 record 数量冒充
独立证据数量。
