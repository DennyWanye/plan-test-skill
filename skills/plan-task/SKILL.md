---
name: plan-task
description: 执行一份已定稿的 plan 并完成测试闭环：锁定绿色基线 → 执行（主 Agent 亲手写代码，子代理只评测）+ 100% 完成度审计 → 围绕主要矛盾的验收（测试策略路由：MCP 真人测试/自动化脚本）+ testcase 收尾 → 收尾 DoD + 文档回写。当用户说"执行这份 plan""按计划执行并测试""把 plans/xxx 跑了""实施这个计划""/plan-task"时使用。输入是一份现成的 plan（通常由 plan-bs 产出）。注意：还没有 plan、需要先讨论或先写 → 用 plan-bs 或 plan-test；只想写 plan 不执行 → writing-plans。
---

# plan-task

本 skill 不重做已批准的整体方案；负责当前片必要的调查、任务细化和挑战；真实目标变更按决策简报处理。共享文档在 `../plan-test/`。

## 开场（每次必做）

1. Announce：输出 "我正在使用 plan-task skill 执行并测试已定稿的 plan。"
2. 读配置：`../plan-test/config.md`；`.claude/plan-test.config.md` 则覆盖；`{大写变量}` 运行时替换。
3. 读 `../plan-test/RULES.md`；执行指令与历史批准按范围沿用，不逐阶段索取确认。
4. 判任务类型（`TASK_TYPE`，见 config"流程分档"）：ops 走 OPS（快照/回滚先行、1 轮实测挑战、journal 收尾，不套交付仪式）；delivery 读 `../plan-test/references/delivery-slices.md`：当前片就绪后实施，每片真实验证后再推进
5. 建 TodoWrite：按下面 5 步

**交接前检查（`HANDOFF_CHECK`）**：结束本轮回复前按 `../plan-test/RULES.md` R10 交接卡走（四问 → 档位 → 派评估员 → fix_class 处置 → 末行）。

上下文压缩后重读 `RULES.md` 与 `{PLANS_DIR}/<feature>/checklist.md`（当前步必做项清单）；phase 文档只在清单不够用时再读。

## 流程

> 防跳步：每步开工前读一次对应 `../plan-test/phase-X.md`，必做项清单写进 `{PLANS_DIR}/<feature>/checklist.md` 逐项打勾；之后按清单推进，不为同一步重读。

### 1. 定位并校验输入

- 定位 plan：有路径用路径，否则从会话/交接定位；多候选→问最小问题，不单凭最近修改时间猜。
- 校验：
  1. `plan.md` 头部包含 `plan-status: finalized`（包含匹配，可带来源后缀）。无标记→查定稿与授权记录，证据齐则注明来源补标记，确未定稿则补调查与挑战；不把格式缺失当成未授权。
  2. `{ACCEPTANCE_FILE}` 存在；缺失→BLOCKED，建议先跑 `/plan-bs`，不许拿 plan 反推验收标准凑数。
  3. 任务标注覆盖哪条 AC。
  4. 条件门命中（输入语义敏感→场景矩阵；LLM 载荷→行为变异清单；异步注册/远程配置/登录态→冷路径场景；格式见 `../plan-test/conditional/phase-A-acceptance.md`）而 acceptance 缺→暂停依赖任务：能从明确需求推导且未冻结→主 Agent 补齐并挑战（不改预期、不重复批准）；否则走决策简报/原批准机制。未补齐不得开工或宣称通过。
- 都找不到→停下，提示先跑 `/plan-bs` 或 `plan-test`。
- 整体 finalized≠未来片可开工：先核当前片交付表、前序能力、oracle/假设，未就绪自主补；原始 MUST 不得从片 scope 消失。

### 2. 锁定绿色基线

按 `../plan-test/phase-2-iterate-plan.md` B 节跑基线，快照记入 `baseline.md`；基线本身是红的要先如实告知用户。

### 3. 执行+完成度审计

按 `../plan-test/phase-3-execute.md`：主 Agent 亲手写全部代码、不派执行子代理（R15）、主体跑通前只跑便宜层与单次价值 smoke（R16）、与本机 hook 共处、A4 code review、`{AUDITOR_ENGINE}` 审计、回归门对照 baseline；里程碑 PASS 后异步 demo+矛盾再分析。plan 失效即回炉（A2），评测子代理只能上报，无权自行改代码或绕行。

### 4. 验收

按 `../plan-test/phase-4-stage-gate.md`：便宜门→价值 smoke→决定性深测（FAIL 即停，R9）→次要各一遍→兑现表→journal/`MACHINE_GATE`→testcase 收尾（⑤）。

### 5. 收尾

按 `../plan-test/phase-final-dod.md`：文档回写→DoD 逐条证据→终态行（R12）→retro→提交→push 前 review；FULL 按其机器门顺序。交付消息按 R10 `MODE: full` 评估。DoD 达不成→BLOCKED，不谎报完成。

## 推进规则

- 广度计数：重跑/改写/continuation 不算多场景（`../plan-test/conditional/phase-4-stage-gate.md`）。
- 成本纪律：记录各阶段耗时；复测范围 R8（续接先重跑声明范围分级冒烟），缩测试范围 R1/R5。
- 已知失败版本启动警告：总体 BLOCKED 时用户要启动测试，先说明已知失败/非验收版本/复现补证目的/会失败场景（R10 `MODE: full`）。

## 何时不要用

- 没有 plan→`plan-bs`/`writing-plans`；要一条龙→`plan-test`；单文件小改、一次性脚本→直接做。
