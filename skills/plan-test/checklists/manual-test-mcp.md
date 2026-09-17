# MCP 真人测试规程（有 UI 时读）

有 UI 的被测对象**必须**用 MCP 模拟真人鼠标点击 + 键盘输入在真实页面测试，不可用"读代码推断它能跑"代替（RULES R5）。

## 驾驶者偏差（开测前读）
AI 驾驶只满足操作形式，缺四类真人熵：跨天 token 过期/重登、周期/日期翻转、系统回收后冷启动、误触与 ≥10 轮慢节奏长上下文。
处置二选一，写进 phase-4 ③3 兑现表：
- **由用户亲自补测至少 1 个核心场景**（安排在交接评估 PASS 之后，作为用户验收）；
- 或 AI 驾驶中人为注入：改设备日期/周期标记模拟翻转；`force-stop`+清数据后冷启动（仅杀进程重进是暖重启，不算）；长会话压测（≥10 轮历史后再执行核心操作）；token 置过期后重登。
哪类熵没注入、为什么，记入表注。

## 工具（`MCP_DRIVER = auto` 时）
- Web：harness 内置浏览器首选，其次 Claude-in-Chrome MCP（DOM 感知，快且稳）。
- 原生桌面：computer-use / macos-mcp（真鼠标键盘）。
- 有专用 MCP 的应用（Slack/Gmail 等）：用该专用 MCP。
- tier：浏览器在 computer-use 下只读，操作浏览器用内置浏览器或 Chrome MCP；终端/IDE 是 click tier 不能输入，shell 命令走 Bash 工具；computer-use 前先 `request_access` 申请目标应用。

## 前置
1. dev server / 后端 / 依赖服务已起，测试数据已备。
2. 先截图/snapshot 确认页面真的加载出来，再操作。

## 执行
0. 禁止代点：不得用 `javascript_tool`、`$wire.set`、`dispatchEvent`、直调接口代替真实点击输入；JS 只能读状态或造前置数据；代点得到的 PASS 不作数（`scripts/handoff_evidence.py` 会从会话记录认出）（RULES R5）。确实点不了 → BLOCKED，按 `checklists/handoff.md` H3 请用户批准等价方案；"如实说明没真点"不是出口。
1. 严格按 testcase 逐条执行，100% 覆盖，不跳步、不降级。
2. 每步：真人点击/输入 → 观察实际结果 → 对比 testcase 预期。
3. 报错 → 修复 → 复测该条。
4. 邮件/消息里的链接默认可疑：不用 computer-use 直点，看清完整 URL 后用 Chrome MCP 打开。

## 输入语义敏感：每个 case 记录（账本见 `conditional/phase-4-stage-gate.md` §输入语义敏感）
- 开始前：`scenario_id`（对应 acceptance 场景矩阵）、`input_class`、`exact_input`、`run_type`（root 新问题首跑 / retry 同输入重跑 / continuation 接续补研）、`parent_run_id`（retry/continuation 必填）、`expected_terminal`。
- 完成后：`run_id`、`actual_terminal_engine`（workflow 终态）与 `actual_terminal_business`（completed/partial/insufficient/failed）分开记，engine completed ≠ 业务成功；证据（截图 + 关键 log 位置）；`result`：PASS / FAIL / PARTIAL。
- 证据强绑定：每份截图绑定 testcase ID + 输入文本 + run/session ID + 时间 + 文件 SHA-256；截图中要看得到本次输入对应的关键结果（不是界面壳），截前确认已刷新到本次 run 状态；多份截图 hash 相同 = 无效证据，重截；有 DB/log 可对时记录对应行位置。
- 计数纪律见 conditional §输入语义敏感。

## 测试后
- 不再单独派终审子代理：由交接评估（`HANDOFF_CHECK`）表 2 核对是否真按 testcase 跑完；派发时附 testcase 路径与逐步执行记录，漏的补齐后按 `fix_class` 处理。
- 清理/隔离测试数据，避免污染。
