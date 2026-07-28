# 验收标准 — 机器门禁第三轮加固（gate hardening）

来源：对 plan-test skill 的一次外部评估，结论为"机器门对已入账事实的自洽性是真门，
但适用性判定可口头绕过、账本可手改、auditor 可命令行改判、脚本非强制调用"。

## 必须（MUST）

- **AC-1 适用性判定入账**：三维（input_sensitive / llm_payload_driven / stateful_init）
  未声明或缺理由 → `APPLICABILITY_UNDECLARED` 拦截；声明「适用」但矩阵未兑现 →
  `APPLICABILITY_GATE_UNSATISFIED`。声明合规且矩阵兑现时不得误报。
  验证：自测用例 ApplicabilityTestCase（10 条，含 1 条正样本）。

- **AC-2 账本防手改**：绕过 CLI 修改 `runs[].result` 或删除链条目 → `LEDGER_TAMPERED`；
  全程走 CLI 的账本不得误报。
  验证：自测用例 IntegrityTestCase（3 条，含 1 条正样本）。

- **AC-3 审计产物优先于命令行**：`auditor-output` 的 verdict 与 `--verdict` 不一致 →
  `audit` 拒绝（exit 2），JSON 字段与文末 `VERDICT:` 行两种形式都识别；自审自判
  （auditor engine == executor engine）以 advisory 曝光但不拦截。
  验证：自测用例 AuditorIndependenceTestCase（3 条）。

- **AC-4 fixture 不得冒充交付**：`fixture_only: true` 的 finalize/render 通过时返回
  exit 3 而非 0。
  验证：pass-minimal fixture 回放断言 exit 3；GateTestCase 完整 PASS 路径同样断言 3。

- **AC-5 回归不减**：并行会话 `39c592c`（Windows 1D-delta）的全部用例保留，无一丢失；
  全量自测全绿。
  验证：`comm` 比对 39c592c 与当前的 test 函数集合 + 全量自测输出。

- **AC-6 流程时序死结已修**：receipt vs 文档回写、phase-4↔5 STATUS_CONFLICT、
  冻结 oracle vs 结果回写、冷路径 vs 全表面冒烟四处，各在对应 phase 文档给出明确顺序。
  验证：四份 phase 文档的对应段落（人工核对，非机器可判）。

- **AC-7 强制调用可用**：`hooks/stop-gate-check.sh` 在无账本时放行、在账本未闭环时以
  非零退出阻止收尾，且在 macOS 自带 bash 3.2 下可运行。
  验证：脚本 `bash -n` + 两种情形实跑。

## 不在范围内

- oracle 由被测者定义（场景矩阵漏写风险场景）——已在 PROTOCOL §6b 如实标注为剩余缺口。
- 证据伪造（截图/日志由代理生产）——同上，不在本轮解决。

## 追加（第一次独立审计判 FAIL 后新增；审计报告见 verification/run-1/auditor-output.json）

- **AC-8 运行时身份按被测内容判定**：`git add`/`git commit` 不改内容时门必须仍通过；
  改动任一文件内容（含新增未跟踪文件）必须触发 `TESTED_RUNTIME_MISMATCH`；
  提交 run-dir 自身不得使 receipt 失效。
  验证：`RealRepoAttestationTestCase` 4 条（真实 git 仓库，非 fixture）。

- **AC-9 审计结论必须有产物支撑**：`auditor-output` 读不出 verdict 时 `audit` 拒绝入账
  （exit 2），validator 侧同样报 `AUDITOR_VERDICT_MISMATCH`；
  hook 必须拦下 `fixture_only` 账本（`check-only` 对它返回 0，只看退出码可整个绕过）。
  验证：`AuditorVerdictSourceTestCase` + hook 三情形实跑日志。

## 追加（第二次独立审计判 FAIL 后新增；审计报告见 verification/run-2/auditor-output.json）

- **AC-10 收尾期改动有合法出口**：`re-attest` 在变更全为文档时记 `doc-only` 并保留既有测试
  结论；出现任何非文档变更即记 `behavioral`，此后每条 required 场景必须有一次更晚的 root
  PASS，否则 `RETEST_REQUIRED_AFTER_CHANGE`。doc-only 由路径规则机器判定，不接受自报。
  可执行位变化计入内容指纹；run-dir 用相对路径传入时同样被正确排除（macOS 软链回归）。
  验证：`ReAttestTestCase` 6 条（真实 git 仓库）。

- **AC-11 缺口如实标注**：内容指纹不覆盖 .gitignore 文件与 symlink 目标内容、超大仓退回旧
  口径会让死结回来、hook 对"压根不建账本"无效——这些必须写在 PROTOCOL / hooks README 里，
  不得以"已防住"的措辞掩盖。半截 init（有 run 目录无账本）须被 hook 拦下。
  验证：PROTOCOL §5.7/§5.8b + hooks/README 能力表 + hook 半截 init 实跑日志。

## Slice 划分（回应 `RELEASE_UNIT_TOO_LARGE`：交付体量超阈值须拆垂直 slice 分别验收）

门禁在 run-3 判定 `task_count=12 > 10`。**不压数字，改为拆分**——两个 slice 各自独立验收、
各自出 receipt：

- **Slice A｜机器门核心**：AC-1 适用性判定、AC-2 账本完整性链、AC-3 审计一致性与独立性、
  AC-4 fixture exit 3、AC-9 审计结论须有产物支撑。
- **Slice B｜运行时身份与流程**：AC-5 回归不减、AC-6 四处时序死结、AC-7 hook 强制、
  AC-8 内容指纹、AC-10 re-attest、AC-11 缺口如实标注。

AC-6 原标注为"人工核对"，在 Slice B 中以可复跑的文档断言脚本作为证据（检查四处修法各自的
关键段落是否存在），并由独立审计复核其是否只是"换了个说法"。

- **AC-12 slice 隔离**：多个 slice 并存时，兄弟 run 目录的记账不得让彼此的内容指纹失效；
  且不得通过"在目录里塞一个账本文件"把该目录排除掉来藏改动。
  验证：`ReAttestTestCase` 的 sibling / planted-ledger 两条用例（真实 git 仓库）。
