# Phase 4 — 验收（围绕主要矛盾）

- 失败先自修；BLOCKED 不自动要求用户接管，升级消息按 `checklists/handoff.md` 轻量评估；只有实际解锁需要用户时才给调查结果与最小动作，保持未通过事实（RULES R9）。
- **便宜的门在前，贵的门在后**；**主要矛盾先测深测，次要 AC 各过一遍**（RULES R2）。
- 条件命中读 `conditional/phase-4-stage-gate.md`；FULL 读 `full/phase-4-stage-gate.md`。

## 片验收
按 `references/delivery-slices.md` 先明确片承诺、原始 AC 映射、继承风险、run 对应；真实入口与承诺必须实测；不机械重跑无变化的昂贵项目（RULES R8）；UI/provider/机器门不因切片降级。

## ① 路由（`TEST_STRATEGY = route`）
- 有 UI：MCP 真人点击/输入（`checklists/manual-test-mcp.md`），`MANUAL_TEST = required`。
- API/CLI/数据管道/库/定时任务：自动化脚本（正确手段非降级），必须存盘、可复跑、纳入回归套件。
- 兼有：两者都做（脚本验逻辑，MCP 验交互）。

## ② 便宜门序（红则先修，不进下一层；冷启动适用时排最前）
1 类型检查 → 2 lint →
3 接线断言（`WIRING_CHECK = required`）：新 export/枚举/入参在入口层须有真实引用（无引用→人工确认，漏接即 FAIL）；运行时白名单用 `satisfies` + exhaustiveness 断言与类型全集同步 →
4 单元/集成 →
5 核心价值 smoke：跑 acceptance 声明的最小验证动作，失败立即 BLOCKED 早停，不进任何昂贵步骤（RULES R4）→
6 分级冒烟（`FULL_SURFACE_SMOKE`）：范围内每个入口打一枪，任一 404/500/未接通即 FAIL；点了没反应先 grep 路由是否存在/挂载/取用新入参 →
7 含 LLM 结构化输出：provider 契约门（conditional）。

## ③ 场景测试
1. 决定性 AC 先测深测；任一 FAIL → 停一切收尾（打包/发布/DoD/"接近完成"），只能 BLOCKED，修后重过门序。已知 BLOCKER 还继续收尾 = 谎报进度。
2. 次要 AC 各一个场景；确定性 UI（设置/开关/CRUD/导航）不套多问题门槛。"一个场景"只指输入类别数，不豁免 `checklists/handoff.md` H2 证据。
3. **兑现表（必产出）**，每条必须 AC 一行：AC | 矛盾地位 | 含 UI | 方式 | 驾驶者 | 真机证据位置 | 状态。
   - 含 UI 的 AC 证据须是实际 MCP 操作，"代码审计/逻辑等价"记 ❌；后端 AC 用可复跑脚本断言。
   - 任何 required 测试无法执行（环境受阻、设备缺失）→ BLOCKED 升级（发前按 `checklists/handoff.md` 轻量评估）不静默降级，等价方案须用户批准并表注（RULES R5）。
   - 待批项（等价方案/全 AI 驾驶/豁免/范围缩减）攒一批一次问（RULES R11）；发出前按 `checklists/handoff.md` 轻量评估。
   - 主流程外逐条照见设置项、开关态、权限隔离、空态、错误态。
4. 输入语义敏感：广度账本见 conditional。全 AI 驾驶须用户批准，否则至少 1 个 required 场景由用户亲自驾驶，排在交接评估 PASS 之后作用户验收。
5. **`HANDOFF_CHECK`**：叫用户验收、给 demo 或宣布完成前，按 `checklists/handoff.md` H0–H4 自查后派 `MODE: full` 评估（评估员自跑 `scripts/handoff_evidence.py`；fix_class 与轮次按该文件）；排在 ⑤ 之后、发消息之前。

## ④ journal.md
1 核心 smoke 命令+摘要；2 兑现表；3 冒烟脚本路径+摘要；4 广度账本（适用时）；5 遗留问题（不许悬空"留待后续"）；5b 交接记录行（每次一行：时间|类型|模式|轮次|verdict|fix_class 处置|HEAD|草稿 sha256|评估文件）；6 终态行，phase-final 填（RULES R12）。
完成判定 = journal + phase-final DoD；交付说明如实写"无机器 receipt"。

## ⑤ testcase 收尾
1. 分步、每步给预期，头部标绑定 AC 与矛盾地位；存 `{TESTCASE_DIR}/<测试范围>/`，维护 `{TESTCASE_DIR}/index.md`。先查已有资产（`references/testcase-lifecycle.md`），复用 oracle 但当前 run 仍须重新执行取证；必要性判据见 conditional。
2. 实际结果写 `<组>/results/` 或 journal。改期望本身走 `behavior_changes` 用户批准，不挂起：记待决项，下一交接点 H3 一次问，仅阻塞全部工作才立即问（RULES R11）。
3. API/CLI/库类用例落成可复跑脚本进回归套件。4. 对照 `checklists/idempotency-review.md` 审"遍历 + 写副作用"代码。
5. 决定性 AC 覆盖存疑或 FULL → `{CHALLENGER_ENGINE}` 跑 `prompts/testcase-iterator.md`（`TESTCASE_ITERATIONS`）；次要 AC 清晰不派。

## 出口
- 中间片：见 conditional，不声称 receipt 或整体完成。
- 默认：便宜门全绿 + 决定性 PASS + 兑现表无 ❌ 无未批准降级 + journal 完整 + testcase 归档 + 最近交接评估 PASS 或文字类已改 → 交付 DoD；有后续片做片终点核对回 phase-2；整体完成另核全部原始 AC。
- FULL：另加 full 出口。
