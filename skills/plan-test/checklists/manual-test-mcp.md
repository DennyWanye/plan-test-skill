# MCP 真人测试规程

对有 UI 的被测对象，**必须**用 MCP 模拟真人鼠标点击 + 键盘输入，在真实页面上测试。不可用"读代码推断它能跑"代替。

## ⚠️ 驾驶者偏差警示（开测前先读）

**AI 经 adb/MCP 驱动 ≠ 真人测试。** AI 驾驶满足的是操作形式，丢掉的是真人使用中的熵。四类系统性缺失：

1. **跨天 token 过期 / 重新登录**——AI 会话总是新鲜的，登录态从不过期；
2. **周期/日期翻转**——新周/新月自动触发的流程（周测/月测/账单），AI 单日测试永远撞不到；
3. **系统资源回收**——真机长期使用中 app 会被系统杀死后冷启动，AI 测试循环里进程始终活着；
4. **误触与慢节奏长上下文**——真人会误点、切页、停顿、拉出 ≥10 轮的长会话把 LLM 上下文"带偏"；AI 路径固定、节奏快、会话短。

**处置（二选一，写进 phase-4 ①b 兑现表）**：要么**真人补测至少 1 个核心场景**；要么在 AI 驾驶中**人为注入**这些熵——改设备日期/周期标记模拟翻转、`force-stop`+清数据后冷启动（注意：仅杀进程重进是暖重启，不算）、长会话压测（≥10 轮历史后再执行核心操作）、token 置过期后重登。哪类熵没注入、为什么，记入表注。

## 工具选择（MCP_DRIVER = auto 时按此选）

| 被测对象 | 工具 | 说明 |
|----------|------|------|
| Web 应用 | **Claude-in-Chrome MCP**（`mcp__claude-in-chrome__*`） | DOM 感知，比像素点击快且稳。首选。 |
| 原生桌面应用 | **computer-use / macos-mcp** | 真鼠标键盘。 |
| 有专用 MCP 的应用（Slack/Gmail 等） | 该应用的专用 MCP | API 级，最快最准。 |

## 权限 tier 注意（容易撞墙，先看清）

- **浏览器在 computer-use 下是只读 tier**：能截图看，但点击/输入被拦。要操作浏览器**必须走 Claude-in-Chrome MCP**。
- **终端 / IDE 是 click tier**：能点不能输入。shell 命令走 Bash 工具，别想在集成终端里打字。
- computer-use 前要先 `request_access` 申请目标应用。

## 测试前置

1. 环境就绪：dev server / 后端 / 依赖服务已起，测试数据已备（见 phase-4 ③）。
2. 确认页面真的加载出来了（先截图/snapshot 核对），再开始操作。

## 测试执行

1. **严格按 testcase 一条一条来**，100% 覆盖，不跳步、不降级。
2. 每步：真人点击/输入 → 观察实际结果 → 对比 testcase 预期。
3. 报错 → 修复 → **复测该条**。
4. 链接安全：邮件/消息里的链接默认可疑，不要用 computer-use 直接点；先看清完整 URL，用 Chrome MCP 打开。

## 每个真人 case 的记录规程（输入语义敏感功能必做，写进 phase-4 ①c 账本）

**开始前**记录：
- `scenario_id`（对应 acceptance 场景矩阵）、`input_class`、`exact_input`
- `run_type`：root（新问题首跑）/ retry（同输入重跑）/ continuation（接续补研）
- `parent_run_id`（retry/continuation 必填）、`expected_terminal`

**完成后**记录：
- `run_id`、`actual_terminal_engine`（workflow 终态）、`actual_terminal_business`（业务终态：completed/partial/insufficient/failed——两者分开记，engine completed ≠ 业务成功）
- 证据：截图 + 关键 log 位置
- `result`：PASS / FAIL / PARTIAL

**证据强绑定（防缓存旧帧/张冠李戴）**：每份截图必须绑定 testcase ID + 输入文本 + run/session ID + 时间 + 文件 SHA-256，且**截图中要看得到本次输入对应的关键结果**（不是只有个界面壳）。截图前确认页面已刷新到本次 run 的实际状态；多份截图 hash 相同 = 无效证据，重截。有 DB/log 可对时，记录对应行位置。

**计数纪律**：同一个 `input_class` + 归一化后相同意图的输入（含改写），只能记为 retry/replay，**不得记为新的 root run 场景**。判断标准："换个问法"不算新场景，"换领域/难度/风险形态"才算。

## 测试后

- 全部 testcase 通过后，派终审子代理确认"是否真按 testcase 跑了全部任务"，漏的补齐。
- 清理 / 隔离测试数据，避免污染。
