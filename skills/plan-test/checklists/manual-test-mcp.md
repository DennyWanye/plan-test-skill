# MCP 真人测试规程

对有 UI 的被测对象，**必须**用 MCP 模拟真人鼠标点击 + 键盘输入，在真实页面上测试。不可用"读代码推断它能跑"代替。

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
- `run_id`、`actual_terminal`（completed/partial/insufficient/failed）
- 证据：截图 + 关键 log 位置
- `result`：PASS / FAIL / PARTIAL

**计数纪律**：同一个 `input_class` + 归一化后相同意图的输入（含改写），只能记为 retry/replay，**不得记为新的 root run 场景**。判断标准："换个问法"不算新场景，"换领域/难度/风险形态"才算。

## 测试后

- 全部 testcase 通过后，派终审子代理确认"是否真按 testcase 跑了全部任务"，漏的补齐。
- 清理 / 隔离测试数据，避免污染。
