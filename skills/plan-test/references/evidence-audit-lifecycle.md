# Evidence、Manifest 与 Audit 生命周期（FULL / `MACHINE_GATE` 专用）

编译 manifest、声明场景证据契约、处理结构化审计 finding、启用 active-run 绑定时读。机器语义以 `gate/PROTOCOL.md` 与 `plan_test_gate.py` 为准；这里只给最小输入格式。

## 1. 从结构化 spec 编译 manifest

- 不要解析 Markdown 来猜 AC/testcase 映射：维护 `verification-spec.json`，由 gate 生成 manifest：
  `python {GATE_SCRIPT} compile-manifest --spec verification-spec.json --output manifest.json`
- spec 必含字段：

```json
{
  "acceptance_file": "acceptance.md",
  "assurance_contract": "assurance-contract.json",
  "testcase_inventory": "testcase/index.json",
  "reuse_report": "verification/run-x/testcase-reuse-report.json",
  "obligations": [{"obligation_id": "TO-1", "ac_ids": ["AC-1"]}],
  "scenarios": [{
    "scenario_id": "S-1", "required": true, "testcase_ids": ["TC-1"], "gate_type": "positive-value",
    "evidence_contract": {
      "producer_types": ["gate-exec", "runtime-probe"],
      "required_artifact_kinds": ["execution-log"],
      "required_identity": ["root_run_id", "session_id"],
      "required_timestamps": true,
      "required_business_facts": ["business_terminal"]
    }
  }],
  "manifest": {"repo_root": ".", "source_request_text": "...", "applicability": {}, "release_unit": {}}
}
```

- `assurance-contract.json.acceptance_ids` 必须被 obligations 覆盖；每条 obligation 必须在 reuse report 中选中有效 testcase；选中的 testcase 须在 inventory 中且至少映射一个 scenario。
- 编译器把输入 hash、选中 testcase、完整 required case set 写入 `compiled_manifest`，并生成覆盖 scenarios/testcase_files/严格模式开关的 canonical seal。`init` 重算 seal 并确认 required scenarios 与 `case_sets.full` 完全相等——不能同步截短两份集合后用任意子集开账。
- 路径：inventory 内相对 testcase path 以 inventory 文件所在目录为基准；其余 spec 路径按当前目录解析，应从项目根执行或用绝对路径。

## 2. 场景级 evidence contract

- `compile-manifest` 对每个 required 场景强制要求 contract（仅未经 compiler 的旧 1.x raw manifest/ledger 保留无 contract 兼容）。字段按实际证明需求声明，不要因为模板方便而要求无意义的 identity。
- 字段判据：
  - `producer_types`：至少一份 primary evidence 的 producer 必须在允许集合中；其余字段也只从可信 producer 记录计算，不能跨不可信记录拼接洗白。
  - `required_artifact_kinds`：所列 kind 必须全部出现。
  - `required_identity`：所列字段至少在一份 primary evidence 顶层非空（允许任意字段名）。
  - `required_timestamps: true` → 至少一份 primary evidence 有 `generated_at`。
  - `required_business_facts`：所列 key 须在 primary evidence 的 `business_facts` 中且值非空。
- Compiled required scenario 最低 contract（按场景类型合并）：producer/artifact 集合非空、identity 含 `root_run_id`、要求 timestamp；`positive-value` 加 `business-result` artifact 与 `business_terminal` fact；UI 额外要求 `ui-capture` 与 `session_id`；含 `temporal-fault` lane 的场景加 `fault-recovery-log` 与 `recovered_state`。
- 手工 attach/import：通过 `--metadata`（文件路径或内联 JSON）入账 provenance：
  `python {GATE_SCRIPT} attach-evidence --run-dir <run-dir> --path artifacts/result.json --kind primary --scenario S-1 --metadata evidence-metadata.json`
  - 已知字段：`producer_type`、`producer_version`、`artifact_kind`、`generated_at`、`root_run_id`、`session_id`、object 型 `business_facts`。
  - `identity`/`facts` 信封抬到顶层（`identity.root_run_id` → `root_run_id`，`facts.*` → `business_facts`）。
  - 其他自定义字段（如 `host_head`、`sdk_run_id`）原样保留在证据条目顶层并在 stderr 声明；只拒绝形似已知字段的（如 `root_runid`）和与账本自有字段同名的（如 `sha256`）。
- `record-run --exec` 自动生成 `producer_type=gate-exec`、`artifact_kind=execution-log` 和时间戳，并从 `--run-id-under-test`、`--session-id`、`--business-terminal` 映射其余 metadata。
- contract 不看 JSON 像不像原始证据，也不把 `--kind primary` 当作充分证明。缺 primary / producer 不可信 / 字段不足 → `PRIMARY_EVIDENCE_MISSING` / `EVIDENCE_PRODUCER_UNTRUSTED` / `EVIDENCE_CONTRACT_UNSATISFIED`。

## 3. 结构化 audit findings

`auditor-output.json` 在 verdict 外可给 findings：

```json
{"verdict": "FAIL", "findings": [{"id": "audit-memory-lineage", "severity": "P1", "status": "open",
  "type": "evidence", "summary": "缺少跨重启 lineage 证据", "ac_ids": ["AC-3"], "scenario_ids": ["S-3"],
  "required_retest": true}]}
```

- `audit` 会原子导入 JSON findings，无需另跑 import。Compiled 1.5 强制结构化 JSON，且 FAIL 至少有一个 open/deferred finding；Markdown 末行格式只为旧 raw ledger 兼容读取。
- `required_retest=true` 必须绑定非空 scenario_ids；P0/P1 必须绑定 AC 或 scenario。
- JSON 中 PASS 与 open/deferred P0/P1 并存会被拒绝；账本存在 open/deferred P0/P1 时 `OPEN_AUDIT_FINDINGS` 阻止通过。
- 整改循环：`list-audit-findings --run-dir <run-dir>` → 修复补证据（`required_retest=true` 时先给绑定的每个 scenario 追加 fresh root PASS）→ `resolve-audit-finding --run-dir <run-dir> --finding-id <id> --resolution "<说明>" --evidence-ids <ev-id>`。
- resolution 必须绑定至少一个当前 ledger evidence ID，并记录修复时的 candidate content digest；它改变 ledger fact，旧 audit 自动 stale → 闭环后必须重新生成 auditor 输入/输出并再次 `audit`。最终 PASS audit 应输出空 findings，或只含 resolved/P2 项。

## 4. Active run（显式 opt-in）

- 并行 slice 不会被 `init` 自动抢占。`compile-manifest` 对真实交付默认 `active_run_required: true`；旧 raw manifest 须显式开启。
- 启用时 validator 要求 `.plan-test/active-run.json` 精确绑定本 run：`python {GATE_SCRIPT} activate-run --run-dir <run-dir>`。registry 绑定 repo-relative run-dir、run ID、acceptance hash、候选内容 digest。
- `re-attest` 改变候选内容后必须再次 `activate-run`。
- 内容指纹只排除精确的 `.plan-test/active-run.json`（receipt `exclusion_scope` 可见），不会排除整个 `.plan-test/`。
- `finalize` 成功后回写 `latest_valid_receipt_digest/path` 到同一 registry（"当前候选 + 最新有效 receipt"入口）。

## 5. Artifact 逻辑去重

- Evidence 文件仍保留原路径，不移动到内容寻址目录。Receipt `evidence_summary` 按 SHA-256 计算：`records`（record 数）、`distinct_artifacts`（不同内容 hash 数）、`distinct_root_runs`（不同 root run identity 数）、`shared_artifact_sha256`（被多条 record 引用的 hash）。
- 同一日志复制到多路径算一个 distinct artifact；不要用 record 数量冒充独立证据数量。
