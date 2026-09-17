# Phase 4 条件细则（命中哪节读哪节）

## UI
- 规程、驾驶工具、禁代点、熵注入、证据绑定：`checklists/manual-test-mcp.md`。兑现表与"一个场景"口径见 phase-4 ③2–③3。

## 输入语义敏感（判定见 `conditional/config.md` §输入语义敏感）
- 深度（失败→重试→恢复）与广度（语义不等价输入）分开记账；distinct 场景数 ≥ `{MANUAL_MIN_DISTINCT_CLASSES}`。
- 计数纪律：retry/改写/continuation 不增加计数；同 `input_class` 且归一化意图相同（含改写）只记 retry/replay，不得记新 root 场景；换领域/难度/风险形态才算新场景。
- 业务终态：positive-value 场景须"非空有效结果 + 达 quality_bar（人工检查）"才 ✅；engine completed 但业务空结果 = 安全 PASS、产品 FAIL；negative-safety 的诚实失败不得证明任何正向 AC；fallback 不崩只算可靠性 PASS，语义退化照记 ❌。
- required 场景 PENDING/PARTIAL/NOT RUN → 门禁 FAIL/BLOCKED（`MANUAL_REQUIRED_PENDING_POLICY = block`）。
- 修好某场景后至少再复测 1 个未受影响类别。
- 随机性功能按 config `STOCHASTIC_MIN_RUNS` 采样。
- 全 AI 驾驶的批准与用户亲驾要求见 phase-4 ③4。
- 确定性 UI 不适用本节，不许反向强套。
- testcase 收尾做语义等价审查：同一问题的改写/重跑被记成多个 distinct → 合并计数，不达标就补真正不等价的类别并补测。

## LLM 载荷
- 真实 provider 契约门（含 LLM 结构化输出必做）：用当前真实 provider 的实际输出过生产 validator，确认 schema 兼容；手工构造的 payload 只能测 validator 本身。
- LLM 载荷驱动功能另按 `llm_variant`（载荷形态 × 场景）记账，required 形态未覆盖即 PENDING。

## 冷启动（`COLD_START_SCENARIO` 适用时）
- 冷路径场景必须排在便宜门序最前（环境准备会把系统弄成暖态）；暖重启不算冷路径。

## program 多片
- 启用机器门时 required 范围口径见 `full/phase-4-stage-gate.md`。
- 同一整体 run 内的片只是能力里程碑：未来 required 保留 NOT_RUN；READY_FOR_AUDIT/finalize 等整体出口等原 run 全范围完成才执行。
- 各片独立 run：对本片完整冻结范围执行全部适用出口。
- 中间片出口：本片真实入口、承诺、适用 review/回归与提交身份核对已完成 → 记片里程碑回 phase-2 准备下一片；未来 required 仍未完成，不要求整个 run 的最终出口，不声称 receipt 或整体完成。

## testcase 设计（写/迭代 testcase 时）
- 最小化权威：`policies/acceptance-preserving-ponytail.md`。
- 每个 required testcase 须能答：证明哪个交付目标？绑定哪条 AC？防哪个范围内失败？为何自动化/静态检查不能替代？不执行则哪个交付结论不成立？
- obligation 类型：
  - delivery（required）：直接证明某条 MUST AC 的正常路径、错误处理、AC 声明的边界行为。
  - change-risk（有明确风险绑定时 required）：改了入口层/路由、共享基础设施（序列化/中间件/provider）、关键不变量，或有明确 impact_paths。
  - exploratory（不 required，只建议）：无共享可变状态的并发、无副作用或已有幂等机制的幂等、AC 边界外的边界值、AC 无要求的性能、无状态持久化的恢复、无数据迁移的迁移。
- 删除或降为 exploratory：无 AC/risk 绑定；重复证明同一事实而无额外故障检测能力（如多个测试都证同一 AC 正常路径）；仅为"更全面"加入（如只读接口的并发写入测试）；超出目标范围的"未来可能需要"（如无迁移时的跨版本迁移测试）；LEAN 下与本次改动无关的性能/恢复/并发/迁移测试。
- 不得删除：覆盖不同信任边界、不同业务终态、正向价值与负向安全、不同迁移路径或权限角色的测试，以及随机系统所需的独立采样。
- 测试义务矩阵：Phase A 写进 `acceptance.md`（AC 定义之后，实现前明确）；字段 `obligation_id | 类型 | AC | 风险 | 最小决定性测试 | required 原因`。plan 阶段在 `plan.md` 引用并说明如何满足每个 obligation。
- 每个 testcase 绑定至少一个 obligation，头部写 `**绑定**: TO-xxx (类型)`、`**AC**`、`**类型**: required|exploratory`。
