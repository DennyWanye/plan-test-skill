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

## 交付一致性门禁（防"半截提交"：验证过的代码 ≠ 提交了的代码）

> **病根**：多代理 + git worktree 工作法下，验证可以在一棵脏工作树上全绿，而关键文件（尤其"把服务层接到端点上"的路由接线层）未提交，随后被 worktree 清理 / `git clean` / 硬 reset 抹掉——git 里留下**能编译、能过类型检查、单测也绿**的"半截健康"状态，但用户路径根本没接通。以下门专堵这条路。

- `COMMIT_STATE_GATE`: required
  - 提交态硬门：宣布完成前 `git status --porcelain` 必须为空，且验证针对的是 HEAD 的代码；
    **对未提交工作树的任何 PASS 一律不作数**。多代理/worktree 参与实现时，
    额外要求"干净态复验"（见 phase-final-dod）。
- `FULL_SURFACE_SMOKE`: required
  - 全表面冒烟：对**每一个用户可达的端点/入口**（含历史功能，不只本次改动链路）
    各打最小一枪（一条 curl 或一次 MCP 点击），断言非 404 / 非 500 / 非"未接通"降级码。
    脚本存盘、可复跑、纳入回归套件（见 phase-4 ②）。
    会话续接/压缩恢复/换 agent 接手时，推进前先跑一遍（见 SKILL.md 推进规则）。
- `WIRING_CHECK`: required
  - 服务层-路由接线断言：services / prompts 等处新 `export` 的函数/枚举/新增入参，
    routes / 入口层必须有真实引用；运行时白名单数组必须与对应类型全集同步
    （`satisfies` + exhaustiveness 断言测试，见 phase-4 ②）。
- `INCREMENTAL_AC_MODE`: on
  - 增量 AC 模式：后续会话增量加功能时，新 AC 必须先进 `{ACCEPTANCE_FILE}` 唯一真相；
    允许只跑受影响 AC 的兑现表与 DoD 对应行，但**全表面冒烟 + 提交态硬门不得豁免**。
    "小功能就不走流程"不被允许。

## 行为开关

- `EXECUTE_AUTONOMY`: high
  - high = 执行阶段遇分歧按最佳实践自决、不打断用户（BLOCKED 例外）。
- `FEATURE_POLICY`: only-add
  - 功能只能多做，不可少做。
