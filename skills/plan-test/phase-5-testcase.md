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

4. **子代理迭代**
   - 派 `{CHALLENGER_ENGINE}`，用 `prompts/testcase-iterator.md` 挑战并迭代 testcase（最少 `{TESTCASE_ITERATIONS}` 轮），直到覆盖率能测出各种 bug 与边界情况。

5. **终审**
   - 派 `{AUDITOR_ENGINE}` 确认 testcase 覆盖了 `{ACCEPTANCE_FILE}` 全部条款。

## 测试目标

- 以"通过测试即可上生产"为标准。覆盖正常态、错误态、空态、边界、并发、幂等。

## 出口

- testcase 定稿、index.md/README 已同步、回归套件已登记 → 进入收尾 DoD。
