# Phase A — 条件矩阵（命中判定才读、才写；不许套模板）

## 输入语义敏感
- 判定见 `conditional/config.md` §输入语义敏感。命中 → acceptance 必写**测试场景矩阵**。
- 预先定义语义不等价的输入类别，≥ `{MANUAL_MIN_DISTINCT_CLASSES}` 个。
- 区分 `positive-value` / `negative-safety` 两类门；正向门声明 quality_bar；exact_input 用自然用户语言。
- **决定性 AC 对应的场景排在最前。**
- 计数纪律：重试/改写/continuation 不增加 distinct 数。
- 确定性 UI（设置页/开关/CRUD/导航）不适用，acceptance 删除本节。

矩阵列（填进 acceptance「测试场景矩阵」节）：

| scenario_id | input_class | exact_input（自然用户语言） | 矛盾地位 | gate_type | required | terminal_expectation | quality_bar |
|-------------|------------|------------------------------|----------|-----------|----------|----------------------|-------------|

## LLM 载荷
- `LLM_PAYLOAD_ADVERSARIAL` 适用 → 必写 **LLM 行为变异清单**：乱序 / 重复 / schema 违约 / 超长载荷 / 拒不调工具五类，每类至少一条端侧容错断言。

## 冷启动
- `COLD_START_SCENARIO` 适用 → 必含**冷路径场景**：全新安装→首次登录→直达功能页；暖重启不算。
