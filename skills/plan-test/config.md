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
- `MANUAL_MIN_POSITIVE_SAMPLES`: 1
  - **正向价值样本**下限：自然用户语言、走真实生产入口、真实 provider、得到**非空有效业务结果**、内容经人工检查、达到 acceptance 声明的最低质量线。所有样本都是 partial/insufficient/空结果时，**即使系统没崩也不得完成**——"诚实降级成功"只是负向安全门 PASS，不等于产品质量 PASS。
- `VALUE_SMOKE_GATE`: required
  - 价值优先 smoke：输入敏感功能在进入打包、全量回归、完整真人矩阵等**昂贵步骤之前**，必须先跑 2–5 个自然语言正向 smoke 验证主要矛盾（核心价值真的可用）；失败 → 立即 BLOCKED 早停，不继续投入昂贵收尾。

## LLM 载荷对抗门禁（只对"LLM 生成结构化载荷驱动 UI/状态机"的功能生效）

> **LLM 载荷驱动的判定**：功能里存在"LLM 输出（结构化 payload / 工具调用 / 生成内容）直接驱动端侧状态机、卡片渲染或流程推进"。LLM 只做纯文本展示、不驱动端侧状态的，不适用。

- `LLM_PAYLOAD_ADVERSARIAL`: required-for-llm-driven
  - 功能含"LLM 输出驱动端侧状态机/卡片/流程推进"时，acceptance 必须含
    「LLM 行为变异清单」：乱序、重复、schema 违约（必填字段缺失/写错位置）、
    超长文本、拒不调用工具——每类至少一条端侧容错断言（容错/自救/降级出口）。
    缺失 → plan-task 开工 BLOCKED（同场景矩阵门禁待遇）。
- `STOCHASTIC_MIN_RUNS`: 2
  - LLM 驱动的多步流程（测验/多轮会话），真机 root run 至少 2 次独立完整跑，
    且至少 1 次在**长上下文会话**（≥10 轮历史）中进行；两次都完整收尾才计 PASS。
    单次跑过记 PASS = 对随机性故障采样不足，不达标。
- `COLD_START_SCENARIO`: required-for-stateful-init
  - 功能行为依赖"异步注册的服务/远程配置/登录态"时，场景矩阵必须含一条
    冷路径场景：**全新安装（或清数据）→ 首次登录 → 直达功能页**，断言功能
    在该路径可用。**暖重启（杀进程重进）不算冷路径。**

## 行为开关

- `EXECUTE_AUTONOMY`: high
  - high = 执行阶段遇分歧按最佳实践自决、不打断用户（BLOCKED 例外）。
- `FEATURE_POLICY`: only-add
  - 功能只能多做，不可少做。
