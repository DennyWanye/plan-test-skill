# 历史与病根：phase-4 / manual-test-mcp / idempotency-review / testcase-lifecycle / test-obligation-matrix（SL-3 瘦身移出）

- phase-4 ⑤ testcase 收尾原为独立的 phase-5，后并入 phase-4；旧文档里的"phase-4 ①b/①c"指现在的 ③4 与 conditional §输入语义敏感。
- 冷路径排最前：环境准备（服务启动、数据准备、全端点冒烟）会把系统弄成暖态，遮蔽冷启动缺陷。
- 接线断言：类型检查绿 ≠ 运行时白名单同步——数组少一个枚举值 tsc 不报错，所以要用 exhaustiveness 断言让它变红。
- 价值 smoke 早停：主要矛盾没验证前，别的测了也白测。
- 兑现表是本 skill 最常被偷工的一环（用代码审计冒充真机证据）。
- 交接评估排在 ⑤ 之后：⑤ 的修复会让上一次 PASS 失效。
- 分级冒烟排查口诀原文：功能点了没反应 → 先 `grep -rn <路由名> <routes目录>`。
- manual-test-mcp 驾驶者偏差原委：AI 会话总是新鲜（登录态不过期）；单日测试撞不到新周/新月自动流程（周测/月测/账单）；测试循环里进程始终活着；AI 路径固定、节奏快、会话短，不会误点切页停顿、不会把 LLM 上下文带偏。
- test-obligation-matrix.md 全仓零引用，SL-3 退休到 retired/；其规则并入 `conditional/phase-4-stage-gate.md` §testcase 设计与 `full/phase-4-stage-gate.md`。原文附的示例（只读状态查询接口的 TO-A1/A2/R1/R2/E1 矩阵、TC-001 头部样例）留在 retired 原件。原文称 Gate 码含义见 phase-4"昂贵层前置 1b"，该节早已不存在。
- testcase-lifecycle.md 原为英文，SL-3 译为中文压缩；frontmatter 完整示例（TC-MEM-RESTART-001）从正文移除。
