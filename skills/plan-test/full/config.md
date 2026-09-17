# config — FULL / `MACHINE_GATE` 细则

只在 FULL 或 `MACHINE_GATE` 启用时读；键名索引在 `config.md`。项目 `.claude/plan-test.config.md` 同名键覆盖。协议与诊断码全文见 `gate/PROTOCOL.md`。

## 启用条件与 authority
- `MACHINE_GATE`: full-high-externality-only — 机器账本层（manifest 编译 / init 开账 / record-run / attach-evidence / re-attest / finalize receipt / 独立 full-audit）仅 `FLOW_TIER=FULL` 且命中高外部性（权限/身份/支付、schema/迁移、公共 Provider/API、共享基础设施、不可逆副作用）时启用；未启用时本文件全部键不生效。
- 启用时：Markdown 只是给人读的视图；状态 authority = 结构化账本 + deterministic validator。

## FULL 挑战轮次出口（`PLAN_CHALLENGE_*`，摘要 RULES R9）
- `PLAN_CHALLENGE_SOFT_LIMIT`: 3 — 第 3 轮仍有**新增** in-scope P0/P1 → `SCOPE_AUDIT_REQUIRED`；记录控制事件后才能续轮。
- `PLAN_CHALLENGE_USER_REVIEW_ROUND`: 5 — 第 5 轮仍有新增问题 → `USER_REVIEW_REQUIRED`，不得静默继续（向用户报告按 `checklists/handoff.md`）。
- `PLAN_CHALLENGE_HARD_LIMIT`: 8 — 第 8 轮仍有 open in-scope P0/P1 → 当前 plan loop `BLOCKED`。

## gate 命令与 run 目录
- `GATE_SCRIPT`: `${CLAUDE_PLUGIN_ROOT}/skills/plan-test/scripts/plan_test_gate.py`
  - 装为插件时 `${CLAUDE_PLUGIN_ROOT}` 由 harness 注入；源码仓库内开发或手工复制安装（未装插件）时依次退回 `skills/plan-test/scripts/plan_test_gate.py`、`~/.claude/skills/plan-test/scripts/plan_test_gate.py`。
  - 最终交付判定只接受 `python {GATE_SCRIPT} finalize --run-dir <run-dir>` 的 exit code 与结构化 stdout，不接受代理手写结论；无有效 `gate-receipt.json` 的手写 SHIP/100% COMPLETE 一律视为 `DELIVERY_VERDICT_CONTRADICTS_LEDGER`。
- `RUN_DIR`: `<plan-folder>/verification/<run-id>/` — 每次验证固定 run 目录；唯一账本 `plan-test-run.json` 只存原始 fact，所有 status/state 由 validator 重算。
- `BLOCKED_SEMANTICS`（机器语义，§5.2b；流程纪律 RULES R9）
  - 流程层"BLOCKED 升级给用户" = 给人看的结论；`record-run --result blocked` = 机器事实，场景保持 BLOCKED 直到补上一条 root pass，required 场景因此过不了门。
  - 临时受阻（用户本人输密码/系统授权等 AI 代不了的步骤）→ 保持 NOT_RUN，原因写进证据，报告里 BLOCKED 升级（按 `checklists/handoff.md`）；不拿机器 blocked 当逃生口。
- `RUN_EXIT_PATHS`：历史 run 只有两条正当出口，其余一律不算
  - `retire --superseded-by <继任轮>`：继任轮须已 SHIPPABLE、同 acceptance、覆盖前轮全部 required 场景——举证责任转移，不是赦免。
  - `acknowledge --reason ... --approval-hash <用户批准原话 sha256>`：继任轮未跑完、用户决定放弃这一轮时用。放弃≠通过：该 run 从此报 `RUN_ABANDONED`，永远拿不到 receipt，也不能当别人的继任轮；不可撤销，须用户显式拍板（按 `checklists/handoff.md` H3 问）。

## oracle 冻结（判据 RULES R3）
- `ORACLE_FREEZE`: required — 实现前 init 冻结 black-box testcase 逐文件 hash（`testcase_lock`）；任何 byte 变化默认 `FROZEN_ORACLE_CHANGED`；唯一例外：绑定 exact old/new + 用户消息 hash + scope/expiry 的 `behavior_changes` 批准 artifact。

## 体量与适用性
- `RELEASE_UNIT_LIMITS`（阈值见 `config.md`）：超限 validator 返回 `RELEASE_UNIT_TOO_LARGE`，要求拆 program plan + 垂直 slice、每 slice 独立验收；阈值可在 manifest `thresholds` 覆盖（须用户知情），不许为卡数字压缩文字。
- `APPLICABILITY_DECLARATION`: required
  - 输入语义敏感 / LLM 载荷驱动 / 冷启动三维适用性写进 manifest `applicability`，各一条 `{value, rationale(≥10 字), decided_by}`；init 冻结、进 receipt digest 与 report.md；缺任一维 → `APPLICABILITY_UNDECLARED`。
  - 判「不适用」合法不拦截，理由留痕可追责；判「适用」则场景矩阵必须兑现（input_class 去重 ≥ `MANUAL_MIN_DISTINCT_CLASSES` 且含 positive-value 场景 / 至少一条 `min_root_runs ≥ 2` / 含 `cold_start` 场景），否则 `APPLICABILITY_GATE_UNSATISFIED`。
- `AI_DRIVING_APPROVAL`: required-for-input-sensitive — 输入语义敏感 + required UI 场景全 AI 驾驶时，须至少 1 次 `--driver human` root run，或 `record-approval --kind all-ai-driving --message-hash <用户批准消息 sha256>`（请用户验收/批准按 `checklists/handoff.md`）；否则 `DRIVER_APPROVAL_MISSING`。`audit --engine` 必须是引擎身份（拒绝方法名）。

## 账本完整性与审计
- `LEDGER_INTEGRITY`: on — 每次 CLI 写入追加 integrity 链条目；手工改 `runs[].result` → `LEDGER_TAMPERED`（防顺手改，不防有决心的伪造，§5.13）。
- `AUDITOR_INDEPENDENCE`: expose
  - `audit --engine` 必填；与 `executor_engine` 相同或未标注 → advisory `AUDITOR_INDEPENDENCE_UNVERIFIED`（曝光不拦截）。审计产物 verdict 与命令行不一致 → 直接拒绝 `AUDITOR_VERDICT_MISMATCH`，以产物为准。
  - manifest 可声明 `executor_engine` / `auditor_engine` / `challenger_engine`（init 冻结）；executor 未声明 → advisory `EXECUTOR_ENGINE_UNDECLARED`；实际审计引擎偏离声明 → advisory `AUDITOR_ENGINE_MISMATCH`。
- `SELF_REPORT_EXPOSURE`: on — 脚本测试优先 `record-run --exec -- <cmd>`（gate 亲自执行，exit code 定 result，日志自动记 primary 证据）。自报模式：同命令同时间戳扇出 ≥2 场景 root pass → advisory `RUN_ATTESTATION_FANOUT`；required 全 PASS 但零 primary 证据 → advisory `EVIDENCE_FREE_FINALIZE`；auditor 产物含 deferred findings → advisory `OPEN_DEFERRALS`（"留待后续"不许悬空）。均曝光不拦截、fixture 免检。
- `EVIDENCE_CLASSES`: primary / derived — 截图、原始日志、命令回执、DB 记录是 primary；auditor 报告与交付汇总是 derived，只辅助审计，不能单独满足 AC/testcase；证据依赖图有环 → `EVIDENCE_DEPENDENCY_CYCLE`。
- `MANIFEST_COMPILATION`: structured — 新 run 从 `verification-spec.json` 编译 manifest；编译器核对 assurance AC、obligation、reuse decision、testcase inventory 与 scenario 双向映射，冻结 `case_sets.full`；不解析 Markdown 猜映射（命令见 `references/evidence-audit-lifecycle.md`）。
- `EVIDENCE_CONTRACT`: per-scenario — 每个 required scenario 按证明需要声明统一 `evidence_contract`；手工证据用 `attach-evidence/import-evidence --metadata <json 文件或内联 JSON>` 提供 provenance（自定义字段留顶层）；`record-run --exec` 自动生成 gate-exec metadata；旧场景无 contract 保持旧语义。
- `AUDIT_FINDINGS`: structured-json — JSON auditor findings 由 `audit` 原子导入；open/deferred P0/P1 为硬门；整改用 `list-audit-findings` / `resolve-audit-finding`，闭环后必须重审。
- `ACTIVE_RUN_BINDING`: compiled-default — `compile-manifest` 对真实交付默认 `active_run_required=true`；旧 raw manifest 需显式开启；init 不自动抢占（适合并行 slice）；每次 re-attest 后重新 activate。
- `ARTIFACT_DEDUPE`: logical-sha256 — 不移动 evidence 文件；receipt 按 SHA-256 区分 record、distinct artifact、distinct root run，并列出共享 artifact hash。

## 计时、实时性与复测
- `TIMING_HARD_GATE`: on — 真实 run 活动跨度 > 30 分钟而 timing 覆盖 < 20% → `TIMING_MISSING`；覆盖区间合并后仍有 > 120 分钟空洞 → `TIMING_GAP`（均 error）；漏记用 `record-timing --declared-start/--declared-end` 补；阶段进出 `phase-start`/`phase-end` 必须配对（`PHASE_UNPAIRED`）。
- `EVIDENCE_REALTIME`: on — `attach-evidence` 记证据文件 mtime，早于开账 → `EVIDENCE_PREDATES_LEDGER`；历史证据必须走 `import-evidence --from-run`（chain of custody 入账并在 report 显形）。
- `IMPACT_SCOPED_RETEST`: on — manifest 场景可声明 `impact_paths` glob，behavioral re-attest 只 stale 命中场景；fail-closed：无映射/清单截断/变更未覆盖 → 全量复测；未声明映射的场景永远算受影响。
