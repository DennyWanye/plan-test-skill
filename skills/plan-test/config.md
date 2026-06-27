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
- `MAX_ROUNDS`: 6
  - 任一"循环直到"的硬上限。超限 → 标记 BLOCKED，升级给用户，**不再空转烧 token**。

## 测试

- `MANUAL_TEST`: required
  - MCP 真人点击/输入测试。对有 UI 的被测对象不可省略、不可降级。
- `MCP_DRIVER`: auto
  - auto = 按平台与被测对象自动选：Web→Claude-in-Chrome MCP，原生桌面→computer-use/macos-mcp。
- `TEST_STRATEGY`: route
  - route = 按被测对象路由（见 phase-4）：UI→手工；API/CLI/库/管道→脚本；两者皆有→都做。

## 行为开关

- `EXECUTE_AUTONOMY`: high
  - high = 执行阶段遇分歧按最佳实践自决、不打断用户（BLOCKED 例外）。
- `FEATURE_POLICY`: only-add
  - 功能只能多做，不可少做。
