# Phase 5 — testcase 维护

**目的**：把本次功能写成可长期复用的手工/脚本测试用例，分步骤、含预期结果，纳入回归。

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

3c. **状态一致性审查**
   - 以下各处的场景/测试状态必须**完全一致**：README、每个详细 testcase 文件头部状态、RESULTS（若维护）、可追溯矩阵、Gate 报告。
   - 典型病灶：RESULTS 已记 PASS，而详细 testcase 顶部还是初始 PENDING——发现即修正到一致，**以实际执行证据为准**，改文档而不是改结论。
   - 存在不一致时本阶段不得出口。

4. **子代理迭代**
   - 派 `{CHALLENGER_ENGINE}`，用 `prompts/testcase-iterator.md` 挑战并迭代 testcase（最少 `{TESTCASE_ITERATIONS}` 轮），直到覆盖率能测出各种 bug 与边界情况。
   - 按 SKILL.md"上下文包"规则派发（附 acceptance.md 条款与上轮已补齐的场景清单）；以末行 `VERDICT` 判定去留，缺结论行按 FAIL 处理。

5. **终审**
   - 派 `{AUDITOR_ENGINE}` 确认 testcase 覆盖了 `{ACCEPTANCE_FILE}` 全部条款，以末行 `VERDICT` 为准。

## 测试目标

- 以"通过测试即可上生产"为标准。覆盖正常态、错误态、空态、边界、并发、幂等。

## 出口

- testcase 定稿、index.md/README 已同步、回归套件已登记 → 进入收尾 DoD。
