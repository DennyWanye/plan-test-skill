# Phase 5 — testcase 维护

**目的**：把本次功能写成可长期复用的手工/脚本测试用例，分步骤、含预期结果，纳入回归。

> **时序说明（防先测后定义）**：testcase 的**编写与 challenger 迭代定稿必须发生在 phase-4 昂贵真人验收之前**——正常应在 phase-3 D 节的**并行验证准备轨**与实现同步完成（black-box 纪律），phase-4 昂贵层前只做核对与冻结。不许拿临时、未经挑战的用例跑昂贵验收，测完再回来补定义。本阶段收尾时做的是：把**实际执行结果回写**、修正与现实的出入、登记回归套件、同步 index/README。

> **回写去哪（防与 `ORACLE_FREEZE` 打架）**：被 `testcase_lock` 冻结的是 **oracle 文件本身**
> ——步骤与预期结果。**实际执行结果一律写在冻结集之外**：`{TESTCASE_DIR}/<组>/results/<run-id>.md`
> 或 run-dir 的 `report.md`。往冻结文件里回填"实际结果/状态"会直接触发 `FROZEN_ORACLE_CHANGED`
> ——这不是误报，是设计：**测完回头改期望文件正是最该防的那个动作**。
> 冻结集在 phase-4 `init` 的 manifest `testcase_files` 里显式列出；不列进去的文件（index.md、
> results/、README）不受冻结约束，随便改。确需修改期望本身 → 走 `behavior_changes` 用户批准，
> 不许绕。

## 步骤

1. **写分步 testcase**
   - 每个 testcase 一步一步来，**每步给出预期结果**。
   - 存放：`{TESTCASE_DIR}/<按测试范围命名的新文件夹>/`。
   - 维护 `{TESTCASE_DIR}/index.md`：把本组 testcase 的测试范围与目的更新进去。
   - 检查根 `README`：若未引用 `{TESTCASE_DIR}/index.md`，补进去。

2. **脚本化的部分纳入回归套件**
   - 对 API/CLI/库/管道类 testcase，落成可复跑脚本，登记进回归套件（下次跑这个 skill 时一并跑）。

3. **幂等性审查**
   - 对照 `checklists/idempotency-review.md`，逐条审查"遍历 + 写副作用"的代码：重复调用/重进页面会不会重复产生副作用？有没有去重/已处理标记？标记是否持久化？失败的能否重试？有没有幂等测试？

3b. **语义等价审查**（输入语义敏感功能必做）
   - 逐条核对 testcase 与 phase-4 ①c 账本：有没有**同一问题的改写、重跑或 continuation 被当成多个 distinct 场景**记账？
   - 有 → 合并计数（改记为 retry/replay），重查 distinct 数是否仍达 `{MANUAL_MIN_DISTINCT_CLASSES}`；不达 → 补真正不等价的类别并补测。

3c. **状态一致性审查（机检为准）**
   - 以下各处的场景/测试状态必须**完全一致**：README、每个详细 testcase 文件头部状态、RESULTS（若维护）、可追溯矩阵、Gate 报告。
   - 把各文档口径用 `declare-status` 登记进账本（source + scenario + status），由 validator 与重算结果对账——冲突即 `STATUS_CONFLICT`，本阶段不得出口。
   - 典型病灶：RESULTS 已记 PASS，而详细 testcase 顶部还是初始 PENDING——发现即修正到一致，**以实际执行证据（账本 record-run/attach-evidence）为准**，改文档而不是改结论。
   - 冻结 testcase 的输入、结果、证据路径必须逐项对得上（S-2 式"冻结第四话题 A、PASS 结果却记话题 B、证据路径又是第三处"即 FAIL）。
   - **本步任何文件改动都会让内容指纹变化**（结果回写、README 同步都算），所以顺序固定为：
     改完文件 → `re-attest --reason "状态同步"` → 再跑预检。**跳过 re-attest 直接跑预检必定
     `TESTED_RUNTIME_MISMATCH`，与有没有 STATUS_CONFLICT 无关**（独立审计实测）。
   - **登记完立刻重跑一次预检**——`declare-status` 是 `STATUS_CONFLICT` 的唯一来源，phase-4 那次 check-only 检不到它：

     ```bash
     python {GATE_SCRIPT} finalize --run-dir <run-dir> --check-only
     ```

     有 `STATUS_CONFLICT` → 改文档到与账本一致（**不是改账本**），再走一次上面的
     「改完 → re-attest → 预检」，直到 `READY_FOR_AUDIT`；这一步过了才做第 5 步的 full-audit（审计前输入必须已定型，否则 audit 完又变即 `AUDITOR_INPUT_STALE`）。

4. **子代理迭代**
   - 派 `{CHALLENGER_ENGINE}`，用 `prompts/testcase-iterator.md` 挑战并迭代 testcase（最少 `{TESTCASE_ITERATIONS}` 轮），直到覆盖率能测出各种 bug 与边界情况。
   - 按 SKILL.md"上下文包"规则派发（附 acceptance.md 条款与上轮已补齐的场景清单）；以末行 `VERDICT` 判定去留，缺结论行按 FAIL 处理。

5. **独立 full-audit（时序：本阶段最后一步——结果回写、状态一致性修正、证据冻结全部完成之后）**
   - 先把审计输入冻结进 run-dir：`auditor-input.json`（acceptance/testcase/账本摘要与 hash）；
   - 派 `{AUDITOR_ENGINE}`，用 `prompts/completion-auditor.md` 声明 `MODE: full-audit`：每条 AC ↔ 任务 ↔ 代码 ↔ testcase ↔ 场景 ↔ root run ↔ 证据 ↔ 业务终态逐条闭环，含场景计数、状态一致性、整体可用性、"是否真按 testcase 跑全"核查；同时确认 testcase 覆盖 `{ACCEPTANCE_FILE}` 全部条款。auditor 原始输出存 `auditor-output.json`。
   - 结果入账（此后任何 fact 变化审计即 stale，须重审）：

     ```bash
     python {GATE_SCRIPT} audit --run-dir <run-dir> --verdict PASS|FAIL --engine {AUDITOR_ENGINE} --input auditor-input.json --output auditor-output.json
     ```

   - 以末行 `VERDICT` 判定，缺结论行按 FAIL 处理。有断点 → 补完 → 复审（复审只核上轮断点与新改动；**补完动了任何输入就必须重新 audit**）。超 `{MAX_ROUNDS}` → BLOCKED 升级。
   - auditor 是 qualitative reviewer，负责发现未知问题；它的 PASS **不能替代**机器 validator——final DoD 只认 `finalize` 的 receipt。

## 测试目标

- 以"通过测试即可上生产"为标准。覆盖正常态、错误态、空态、边界、并发、幂等。

## 出口

- testcase 定稿、index.md/README 已同步、回归套件已登记、**full-audit PASS 且已 `audit` 入账** → 进入收尾 DoD。
