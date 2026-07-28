# plan-test 机器门禁协议（gate protocol）

> 来源：2026-07-27 plan-test/plan-task 完成质量复盘 handoff（DeskPet Companion 计划的错误 oracle、
> 冻结 testcase 与最终结论冲突、终点式 E2E、Markdown-only gate 四类逃逸）。
> 定位：Markdown 是给人读的视图，**不再是状态 authority**；唯一状态 authority 是结构化账本 +
> deterministic validator。qualitative auditor 负责发现未知问题；validator 负责阻止已知违规。

## 1. run 目录（固定布局）

每次 plan-task/plan-test 验证使用一个固定 run 目录：

```text
<plan-folder>/verification/<run-id>/
  plan-test-run.json       # 唯一状态账本（只存 fact；状态由 validator 重算）
  artifacts/               # 截图、原始日志、命令回执等 primary 证据
  auditor-input.json       # 独立审计的冻结输入
  auditor-output.json      # 独立审计原始输出
  gate-receipt.json        # finalize 成功后才存在
  report.md                # render 从 ledger + receipt 生成的人读视图
```

## 2. canonical command（唯一判定入口）

```bash
python skills/plan-test/scripts/plan_test_gate.py finalize --run-dir <run-dir>
```

- plan-task/plan-test 的最终交付判定**只接受本命令的 exit code 与结构化 stdout**，不接受代理手写结论。
- `finalize --check-only` 是审计前预检：检查除 auditor/receipt 外的全部输入与测试完整性，
  成功只输出 `READY_FOR_AUDIT`——预检不因"审计尚未执行"而永远无法进入审计阶段。
- 正式 `finalize`：额外要求 auditor PASS，重新校验全部 hash/HEAD/runtime 后生成
  `gate-receipt.json`（幂等：同输入复用同 receipt digest 与首次 finalized_at）。
- `attach-evidence --replace`：重测后证据文件更新时顶替同路径旧条目，旧条目连同旧 sha256 转入 `superseded_evidence`，动作进 integrity 链并在 report 显形——**不是静默覆盖**，也换不绿场景（状态由 append-only 的 `runs[]` 重算）。
- 记账辅助命令：`record-timing`（时间成本入账，--exec 实测 / declared 申报两模式）、
  `checkpoint`（工作检查点）与 `re-attest`（收尾期改动后重新采集运行时身份）——见 §5 规则 10 与 8b。
- `render`：重新运行同一 validator、复验 receipt digest，失效时**不渲染 SHIPPABLE**。
- 没有有效 receipt 的手写 `SHIP / 100% COMPLETE` 一律视为
  `DELIVERY_VERDICT_CONTRADICTS_LEDGER`。

### exit code（交付判定只看这个）

| code | 含义 |
|------|------|
| 0 | 真实交付通过（唯一可用于宣布完成的返回值） |
| 1 | 门禁 FAIL（stdout 有 DIAG 行） |
| 2 | 用法/IO 错误 |
| 3 | **fixture-only run 通过**——合成数据，receipt 标 FIXTURE-ONLY，**不可作为交付证据** |

exit 3 是刻意与 0 分开的：`fixture_only: true` 会跳过全部 git 校验，此前它同样返回 0，
"在真实项目里给 manifest 加一个字段"就是最省事的一条绕过路径。现在它绿得很显眼，但绿不进交付。

## 3. 状态机（validator 计算，不可手写）

```text
DRAFT → ACCEPTED → IMPLEMENTED → TESTED → VALIDATED → SHIPPABLE
```

- ACCEPTED：source_request + acceptance 已冻结（hash）。
- IMPLEMENTED：baseline HEAD/dirty 指纹已记录。
- TESTED：全部 required 场景重算为 PASS。
- VALIDATED：check-only 无诊断（auditor 除外）。
- SHIPPABLE：auditor PASS + 全部硬门通过 + receipt 生成。

## 4. 稳定诊断码（stable diagnostic codes）

**输出有序**：同一账本状态重跑，诊断序列逐字节相同。第一键 = 下表行序（canonical 序，
即 `CANONICAL_ORDER`）；第二键 = 类别内 scenario_id / evidence_id / 路径字典序，三者皆无
以 detail 全文兜底。severity=error 的行以 `DIAG` 前缀输出并拦截；severity=advisory 的行
以 `ADVISORY` 前缀输出、**不拦截**（不影响状态机与 receipt）。

| # | code | severity | 触发条件 |
|---|---|---|---|
| 1 | `SCHEMA_INVALID` | error | 账本结构不合 schema，或 schema_version major 与 validator 不符 |
| 2 | `LEDGER_TAMPERED` | error | integrity 链断裂或末条 facts_digest ≠ 当前 fact——账本在 CLI 之外被改过 |
| 3 | `REQUIRED_SCENARIO_NOT_RUN` | error | required 场景为 NOT_RUN/PARTIAL/BLOCKED/FAIL |
| 4 | `STATUS_CONFLICT` | error | 文档口径（declared）与账本重算结果冲突 |
| 5 | `DELIVERY_VERDICT_CONTRADICTS_LEDGER` | error | 手写 SHIP/COMPLETE 但 required 未全 PASS |
| 6 | `UI_EVIDENCE_MISSING` | error | UI 场景判 PASS 但无真实 UI action 的 primary 证据 |
| 7 | `RUN_CREATION_UNVERIFIED` | error | expected_run_created 声明未被正/负向证据兑现 |
| 8 | `EVIDENCE_MISSING` | error | 证据文件不存在 / 依赖不存在 |
| 9 | `EVIDENCE_HASH_MISMATCH` | error | 证据文件被改动 |
| 10 | `EVIDENCE_DEPENDENCY_CYCLE` | error | 证据循环引用（互引的两个汇总不能构成独立证据） |
| 11 | `DERIVED_EVIDENCE_ONLY` | error | required 场景只有 derived report，无 primary 证据 |
| 12 | `FROZEN_ORACLE_CHANGED` | error | 冻结 black-box testcase byte 级变化且无 behavior_change_id |
| 13 | `BEHAVIOR_APPROVAL_REQUIRED` | error | 行为变更缺少用户批准 artifact（exact old/new + 消息 hash + scope） |
| 14 | `APPLICABILITY_UNDECLARED` | error | 适用性三维未显式声明，或缺 rationale（≥10 字）/ decided_by |
| 15 | `APPLICABILITY_GATE_UNSATISFIED` | error | 声明某维「适用」但场景矩阵未兑现对应条件（见 §5.12） |
| 16 | `RISK_CLOSURE_MISSING` | error | required lane 无通过的 root run |
| 17 | `STABILITY_SAMPLES_INSUFFICIENT` | error | 非确定性场景采样不足或 FLAKY |
| 18 | `RELEASE_UNIT_TOO_LARGE` | error | 交付体量超阈值，须拆 program plan + 垂直 slice |
| 19 | `TESTED_RUNTIME_MISMATCH` | error | 被测**内容**指纹与当前不一致，或 adapter UNKNOWN |
| 19b | `RETEST_REQUIRED_AFTER_CHANGE` | error | behavioral re-attest 之后，required 场景没有更晚的 root PASS |
| 20 | `AUDITOR_MISSING` | error | full-audit 未执行或 verdict 非 PASS |
| 21 | `AUDITOR_VERDICT_MISMATCH` | error | auditor 产物里的 verdict 与入账 verdict 不符（命令行改判） |
| 22 | `AUDITOR_INPUT_STALE` | error | audit 后账本 fact 又变化——旧 PASS 失效 |
| 23 | `RECEIPT_STALE` | error | receipt digest 与当前输入不符 / 已 invalidate / 缺失 |
| 24 | `AUDITOR_INDEPENDENCE_UNVERIFIED` | **advisory** | auditor engine 未标注或与 executor 相同——自审自判，曝光不拦截 |
| 25 | `TIMING_GAP` | **advisory** | 相邻 timing/checkpoint 锚点间隔 > 120 分钟（长时间无记账） |
| - | `REVISION_CONFLICT`（stderr） | - | 并发写 CAS 冲突——重读后重试，不静默覆盖 |
| - | `LEDGER_LOCKED`（stderr） | - | 文件锁被占用 |

## 5. 硬规则摘要

1. **required rows 由 init 自动创建为 NOT_RUN**；命令只记录事实（record-run /
   attach-evidence），状态由 validator 计算，调用者不能把 NOT_RUN 改成 PASS。
2. **retry / replay / 同意图改写 / continuation 不是 root run**——只有 root 计入场景状态。
3. **证据分级**：截图、原始日志、命令回执、DB 记录是 primary；auditor 报告、delivery
   汇总是 derived。derived 只辅助审计，不能单独满足 AC/testcase。
4. **engine 终态 ≠ 业务成功**：positive-value 场景的 root run 业务终态为空/insufficient/
   partial → 场景只能 PARTIAL。
5. **冻结 oracle**：实现前 init 冻结 black-box testcase 逐文件 hash；任何 byte 变化默认
   FAIL；唯一例外是绑定 exact old/new + 用户消息 hash + scope/expiry 的批准 artifact。
6. **audit 冻结 facts_digest**：审计后代码、配置、testcase 或结果有任何变化，旧 auditor
   PASS 与 receipt 自动失效（AUDITOR_INPUT_STALE / RECEIPT_STALE）。
7. **运行时身份按「被测内容」判定，不按提交身份**（schema 1.2.0 起）：`content_digest` =
   工作树全部 tracked + 未忽略 untracked 文件的逐文件内容 hash 与可执行位。
   `git add`/`git commit` 不改内容 → 指纹不变 → 门不拦；改一个字节 → `TESTED_RUNTIME_MISMATCH`。
   HEAD 与 dirty patch 仍记录，但只作展示与溯源。
   **为什么按内容而非提交身份**：原来按 HEAD+dirty 判定时，「测完 → 提交 → finalize」必然
   MISMATCH，而不提交又过不了提交态门，形成无出口的死结（由独立审计在真实仓库实测发现）。

   **排除范围在 init 时冻结，只认显式声明**：`exclusion_scope` = 当前 run-dir +
   manifest 的 `related_run_dirs`（拆 slice 时用来声明兄弟 run 目录）。声明项必须是**已存在的**
   `.../verification/<单层>` 目录，否则 init 直接拒绝（直接声明 `src` 这类路径会被挡下）。范围进账本、
   进 receipt digest、在 `report.md` 逐条显形；**事后往仓库里塞任何文件都不改变它**。
   指纹只对文件条目取，排除范围本身不参与 digest 计算（否则新开一个 slice 会把别的 slice 判红）。

   **为什么必须冻结（三次教训，都是独立审计实测打穿的）**：
   - 按「目录里有 `plan-test-run.json`」判定 → 在 `src/` 塞一个假账本，整个 src 从指纹里消失；
   - 按路径形态 `.../verification/<单层>` 判定 → 项目里真有 `src/verification/rules/` 业务目录时，
     它的代码被整体排除，audit 之后改实现、加后门仍拿到逐字相同的 receipt；
   - 按「文件名恰为记账物」+「含账本目录的 `artifacts/`」判定 → 把业务文件命名成 `manifest.json`，
     或事后 `mkdir -p src/verification/z/artifacts` 再塞一个空账本，照样藏住后门。

   **共同根因：判定输入来自被测者可写的工作树。** 只要排除范围是校验时现算的，被测者就能
   通过写文件影响它。冻结声明把它变成事前的、可见的、可审计的选择——想排除什么，必须在
   init 时说出来，并留在 receipt 里。

   **仍未消除的剩余面（如实标注）**：形态校验挡得住「声明 `src`」，挡不住「**先造出**一个
   `src/verification/lib/` 再声明它」——那样该目录的代码会合法地不进指纹，audit 之后改动
   不会被发现。缓解只有可见性：声明范围逐条列在 `report.md` 与 receipt digest 里，人一眼
   能看出排除了什么；但**范围内事后新增的文件不会出现在报告里**。审阅 receipt 时必须把
   `exclusion_scope` 当作重点看，而不是当作噪声跳过。

   **指纹覆盖什么、不覆盖什么（如实列出，不要按字面理解成"任何文件"）**：
   - 覆盖：tracked 文件 + 未被 .gitignore 忽略的 untracked 文件的**内容 hash 与可执行位**；
     文件新增、删除、改名同样体现为变化。
   - **不覆盖**：被 .gitignore 忽略的文件（构建产物、本地 `.env`、缓存）——它们不是交付内容，
     但**若你的运行行为依赖某个被忽略的文件，这个门照不出它的变化**；symlink 只指纹化
     目标路径字符串，不跟随读取目标内容。
   - 超大仓（文件数 > `CONTENT_DIGEST_FILE_LIMIT`，默认 20000）**退回 HEAD+dirty 旧口径**，
     init 会打印警告、`render` 的报告顶部会标注。注意：退回之后「测完→提交→finalize」的
     死结也一并回来，此时必须靠 `re-attest` 走收尾。

8c. **`retire`：被取代的历史 run 的唯一合法退场方式**，且必须有继任者。

   ```bash
   python skills/plan-test/scripts/plan_test_gate.py retire --run-dir OLD \
     --reason "已被 slice-a/b 取代" --superseded-by NEW
   ```

   - `--superseded-by` **必填**：继任 run 必须是非 fixture、当前 SHIPPABLE、receipt 未失效、
     **在同一仓库内**、**acceptance 相同**、且**覆盖被退役 run 的全部 required 场景**，
     否则直接拒绝（exit 2）。**退役不是赦免，是把举证责任转移给另一个已通过的 run**——
     少了「覆盖」这一条，就成了拿一张无关的 receipt 背书（独立审计实测：用一个唯一场景是
     `Z-9` 的同仓 run 就能退役掉 `S-1` FAIL 的 run）。
   - 退役后账本仍如实是未闭环状态：`finalize --check-only` 照样 FAIL。它只影响一件事——
     Stop hook / CI 不再因这个已被取代的 run 阻断收尾。
   - 判定统一走 `retire-status --run-dir D`（exit 0 = 退役成立）；hook 与 CI **不得自行解读
     `retired` 字段**，且必须在 `finalize --check-only` **之后**才询问退役状态。
   - **为什么要这么绕**：无守卫的第一版 `retire` 本身就是一个新绕过——独立审计实测
     `retire --reason "这个先不做了"` 即可让一个 required 场景 FAIL 的 run 从门前消失；
     手写 `"retired": true` 也一样，因为当时 hook 把该判断放在 check-only 之前，
     `LEDGER_TAMPERED` 根本没机会打印。这与更早被堵掉的 `fixture_only` 是同一形态：
     **给账本加一个字段就让门消失**。任何新增的「豁免」都要先问一句：它会不会变成下一个这样的字段。
   - 确实要放弃一次验证而没有继任者 → **直接删除该 run 目录**。删除会出现在 git diff 里，
     是可见动作；用一个静默字段让它消失不是。

8b. **`re-attest`：收尾期改动的唯一合法出口**。attestation 原本只在 init 写一次，
   而收尾流程强制要求文档回写与状态同步——于是任何合规执行都会把 run 永久锁死，
   唯一出路 `init --force` 会清空 runs/evidence/auditor（第二轮独立审计实测）。
   现在：

   ```bash
   python skills/plan-test/scripts/plan_test_gate.py re-attest --run-dir D --reason "文档回写"
   ```

   - 变更集**全部**命中文档白名单 → 记 `doc-only`，既有测试结论继续有效。白名单默认只认
     叙述性文档（`README*`/`CHANGELOG*`/`docs/**`/`ARCHITECTURE*`/`*.rst`），且
     `prompts/`、`skills/`、`config/`、`.claude/`、`hooks/` 前缀与 `requirements.txt`、
     `package.json`、`Dockerfile` 等**永远算行为文本**（改依赖版本、改系统提示都不是「改文档」）。
     manifest 的 `doc_only_globs` **只能收窄不能放宽**（最终判定 = 默认 ∩ 自定义）——
     manifest 由被测者自写，自报即生效的开关等于把门交回被测者；
   - 只要有一个非文档文件变了 → 记 `behavioral`，validator 要求**每条 required 场景都有一次
     发生在该次 attestation 之后的 root PASS**，否则 `RETEST_REQUIRED_AFTER_CHANGE`。
   - doc-only **由路径规则机器判定，不接受调用者自报**；"我这次只改了文档"不再是一句话的事。
   - 判定用账本的追加序号锚定，不用时钟（`now_iso()` 精度到秒，同秒重跑会被误判成已重测）。
8. **fixture_only**：跳过 git 校验的 run 永远标 FIXTURE-ONLY，receipt/report 不可作为
   真实交付证据。
9. **"100%" 只表示某个明确 scope 的 required gates 全绿**，不表示未来绝无缺陷。
10. **时间是一等证据**（schema 1.1.0 起）：机器活动用 `record-timing --exec -- <cmd>`
    包裹执行——wall clock 记 RFC 3339 UTC 起止、monotonic clock 实测 `elapsed_ms`，
    调用者不可覆写实测值；真人 E2E 等外部活动用 `--declared-start/--declared-end`
    申报，CLI 强制 `measured:false`，report 单列"declared time"、不混入实测聚合。
    连续工作每 90–120 分钟跑一次 `checkpoint`（记 HEAD/dirty/当前 slice/下一动作）；
    间隔超 120 分钟触发 advisory 级 `TIMING_GAP` 提示。render 的报告按七类
    activity_class（implementation / automated_test / manual_e2e / provider_wait /
    user_wait / interruption_recovery / rework）分解耗时。
11. **legacy fixture 溯源**：`provenance.json` 的 `source_sha256` 未采集（null）时，
    fixture 只能作为合成 dogfood 运行，输出强制标 `PROVENANCE: UNVERIFIED`；
    不得为让历史变绿而修改历史证据文件。
12. **适用性判定是 fact，不是口头判断**（schema 1.2.0 起）：`input_sensitive` /
    `llm_payload_driven` / `stateful_init` 三维必须在 manifest 里显式声明
    `{value, rationale(≥10 字), decided_by(agent|user)}`，由 init 冻结进账本、
    进 receipt digest、进 render 报告。判「不适用」合法且不拦截——但理由留痕、可追责；
    判「适用」则场景矩阵必须真的兑现：
    - `input_sensitive=true` → required 场景的 `input_class` 去重数 ≥
      `thresholds.min_distinct_input_classes`（默认 3），且至少一条 `gate_type=positive-value`；
    - `llm_payload_driven=true` → 至少一条 required 场景 `min_root_runs ≥ 2`；
    - `stateful_init=true` → 矩阵含 `cold_start: true` 场景。

    **病根**：这三个判定此前只写在 config.md 里由代理口头自决且不留痕——判一句
    「这是确定性 UI」，场景矩阵、正向价值门、随机采样、冷启动四道门就合法消失，
    validator 完全不知道发生过这件事。现在它至少是一条被冻结、被展示、可被审计的记录。
13. **账本只能经 CLI 写**：每次写入追加 integrity 链条目
    （`chain_n = sha256(chain_{n-1} + op + facts_digest_n)`）；validator 重算全链并核对
    末条 `facts_digest` 是否等于当前 fact 快照。手工改一行 `runs[].result` 即
    `LEDGER_TAMPERED`。**写入前先验链**：链一旦对不上，任何后续 CLI 写入都被拒绝（exit 2）——
    否则篡改检测是一次性的：改完再敲一条无害命令（`checkpoint` 就行），新条目会拿被篡改的
    快照重新盖章，痕迹永久消失并照常拿到有效 receipt（独立审计实测，成本只是「改一行 +
    多敲一条命令」）。
    **它能做什么、不能做什么（第九轮独立审计实测后如实改写，此前两版估计都被证伪）**：
    validator 只把**末条** `facts_digest` 与当前快照对账，中间条目从不与真实状态比对。
    因此改一条事实之后，只需重算末条 `facts_digest`、末条 `chain` 与 `integrity.chain`——
    **四行、O(1)，与链长无关**。链首必须是 `init`、链长下界这些结构不变量只封住了
    「把链压短」和「删链重建」两种最省事的形态，**都不构成防篡改**。
    早先文档写的「必须重算整条链」「必须逐条重放」都是被证伪的乐观估计。

    **准确的定位**：链只能发现「改了文件但没同步链」的编辑——顺手改、脚本误写、合并冲突残留。
    它发现不了任何愿意多写四行的对手，这是**本地无密钥哈希链的固有上限**：文件与校验逻辑
    都在被测者手里，怎么设计都一样。**要真正防篡改，锚点必须在被测者写不到的地方**——
    CI 从 git 历史重算并比对 receipt，或把 receipt 推到 append-only 的远端存储。
    只启用 Stop hook 而不接 CI 时，请按「链只防手滑」来理解它，不要按「防伪造」来宣传。
14. **审计产物 > 命令行**：`audit --verdict` 与 `auditor-output`（JSON 的 `verdict`
    字段或文末 `VERDICT: PASS/FAIL` 行）不一致 → `audit` 直接拒绝（exit 2），
    事后不一致 → `AUDITOR_VERDICT_MISMATCH`。`--engine` 必填；与 `executor_engine`
    相同或标 unknown → advisory `AUDITOR_INDEPENDENCE_UNVERIFIED`（曝光而非拦截：
    审计者与实现者是否真的独立，机器证明不了，只能让它在报告里显形）。

## 6. 交付措辞（有效 receipt 才能填）

```text
REQUIRED GATES: PASS
TESTED HEAD: <sha>
TESTED SCOPE: <AC / slice>
FRESH LANE: PASS | NOT_REQUIRED(<risk/policy ref>)
HISTORY/UPGRADE LANE: PASS | NOT_REQUIRED(<risk/policy ref>)
TEMPORAL/FAULT LANE: PASS | NOT_REQUIRED(<risk/policy ref>)
EXPLORATORY LANE: PASS | NOT_REQUIRED(<risk/policy ref>)
KNOWN GAPS: 0 / 明确列表
GATE RECEIPT: <content_digest>
```

禁止再写无作用域的 `100% COMPLETE，DECISION: SHIP`。用户后续发现生产缺陷 →
`invalidate` 对应 receipt；修复、永久回归和受影响 lane 复测完成后才生成新 receipt。

## 6b. 本门禁**堵不住**什么（如实标注，别把它当保险箱）

validator 能重算的只有"已入账事实之间的自洽性"，事实本身是否真的发生过，它无从判断：

- **证据可伪造**：`attach-evidence` 只校验文件存在与 hash，不看内容来源。代理自己造一张
  截图、写一行假日志，门禁看不出来。`--ui-action` 只是一个 bool。
- **result 是自陈**：`record-run --result pass` 的 engine/业务终态是自由文本。
- **oracle 由被测者定义**：场景全部来自代理自写的 manifest。**漏写一个风险场景，
  门禁根本不知道它存在**——这是本协议最大的剩余缺口，适用性判定（§5.12）只覆盖了
  其中"条件门被口头判掉"这一类。
- **不跑脚本就没有门**：canonical command 是否被调用，取决于流程被遵守。要真正闭合，
  必须在 harness 侧强制（见 `hooks/README.md` 的 Stop hook 与 CI 片段），
  单靠 Markdown 里写"必须跑"不构成强制。

因此准确的说法是：**它对"已入账事实之间的自洽性"是真门，对"事实是否发生"是高成本的自觉提醒。**
凡是宣称它能防住上面四类的说法，都是过度承诺。

## 7. 自测

```bash
python skills/plan-test/scripts/test_plan_test_gate.py
```

94 个用例（曾对外称 57，其中 23 条是被 `TimingTestCase(GateTestCase)` 继承重跑的重复项，
拆 `GateHarness` 基类后为 50；此后五轮独立审计逐次打穿实现，补齐攻击回归用例至 94）。

覆盖：状态矛盾 FAIL、required NOT_RUN、证据缺失/hash 不符、循环证据、frozen oracle
变异、audit 后 stale、receipt 幂等、适用性未声明/理由缺失/判「适用」未兑现矩阵、
账本手改与链条目缺失、审计产物与命令行改判冲突、自审自判 advisory 曝光、
Companion 历史三冲突 dogfood
（REQUIRED_SCENARIO_NOT_RUN + STATUS_CONFLICT + DELIVERY_VERDICT_CONTRADICTS_LEDGER）、
以及多条证据完整的 PASS 路径（防 gate 只会拒绝）。
CI/self-test 用同一 canonical finalize 路径重跑，不另写一套判断。
