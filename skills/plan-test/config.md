# plan-test 配置

本文件是 skill 的**默认配置**。运行时，若项目根存在 `.claude/plan-test.config.md`，其中出现的同名键**覆盖**这里的默认值（只需写要改的键）。

所有 `{大写变量}` 在各阶段文档里被引用，运行时替换为下面的值。

## 子代理引擎

- `EXECUTOR_ENGINE`: codex-gpt5.5
  - 执行阶段并行实现用。若当前环境未安装 codex 插件，**优雅回退到 claude 子代理**。
- `CHALLENGER_ENGINE`: claude
  - 挑战 plan / 挑战架构文档 / 迭代 testcase 的子代理。
- `AUDITOR_ENGINE`: opus-4.8
  - 完成度终审、测试覆盖最终确认。

## 路径

- `ARCH_DIR`: ./ARCHITECTURE
- `PLANS_DIR`: ./plans
- `TESTCASE_DIR`: ./testcase
- `ACCEPTANCE_FILE`: ./acceptance.md

## 轮次与出口

- `PLAN_ITERATIONS`: 3
  - plan 挑战迭代的**最少**轮数；未达 phase-2 收敛判据则继续，不设上限（受 `MAX_ROUNDS` 兜底）。
- `TESTCASE_ITERATIONS`: 2
  - testcase 迭代最少轮数。
- `AUDIT_RETRY`: until-100
  - 完成度未达 100% 就循环补完（受 `MAX_ROUNDS` 兜底）。
- `MAX_ROUNDS`: 15
  - 任一"循环直到"的硬上限。超限 → 标记 BLOCKED，升级给用户，**不再空转烧 token**。

## 测试

- `MANUAL_TEST`: required
  - MCP 真人点击/输入测试。对有 UI 的被测对象不可省略、不可降级。
- `MCP_DRIVER`: auto
  - auto = 按平台与被测对象自动选：Web→Claude-in-Chrome MCP，原生桌面→computer-use/macos-mcp。
- `TEST_STRATEGY`: route
  - route = 按被测对象路由（见 phase-4）：UI→手工；API/CLI/库/管道→脚本；两者皆有→都做。

## 真人测试广度门禁（只对"输入语义敏感"功能生效）

> **输入语义敏感的判定**：功能的输出质量随输入语义变化——LLM 对话/生成、搜索、调研/agent、推荐、分类等。反之，设置页、开关、单按钮、CRUD 表单、导航等**确定性 UI 不适用**，一个场景即可，不许把多问题门槛错误套给它们。

- `MANUAL_SCENARIO_MATRIX`: required-for-input-sensitive
  - 输入敏感功能必须在 acceptance 里有"测试场景矩阵"（见 phase-A）；没有 → plan-task 开工即 BLOCKED。
- `MANUAL_MIN_DISTINCT_CLASSES`: 3
  - 真人测试最少覆盖的**语义不等价输入类别**数。重试、重放、同意图改写、continuation 都不增加此计数。
- `MANUAL_REQUIRE_NEGATIVE_CLASS`: when-applicable
  - 适用时额外包含 1 个错误态/低证据/对抗场景（验证诚实降级），计入类别数之外。
- `MANUAL_REQUIRED_PENDING_POLICY`: block
  - 任何 required 场景处于 PENDING/PARTIAL/NOT RUN 时，门禁与 DoD 一律 FAIL/BLOCKED，不得用"核心 PASS"掩盖。

## 行为开关

- `EXECUTE_AUTONOMY`: high
  - high = 执行阶段遇分歧按最佳实践自决、不打断用户（BLOCKED 例外）。
- `FEATURE_POLICY`: only-add
  - 功能只能多做，不可少做。
