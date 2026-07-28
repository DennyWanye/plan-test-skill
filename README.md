# plan-test

一个 Claude Code **插件**，含三个 skill，把"优化 / 升级 / 重构需求"走完整闭环：

```
需求澄清 & 验收标准  →  架构基线  →  写 plan  →  子代理挑战迭代
  →  并行执行 + 100% 完成度审计  →  测试策略路由(MCP真人测试 / 自动化脚本)
  →  收尾 DoD + 文档回写
```

| Skill | 覆盖范围 | 适用场景 |
|-------|---------|---------|
| `/plan-bs` | 头脑风暴对话 → 验收标准 → 架构基线 → 共创 plan → 挑战迭代 + spike 验证 → 用户 review 定稿 | 想先和 AI 讨论清楚再定计划；**不实现业务代码**（会跑可丢弃的验证 spike） |
| `/plan-task` | 校验定稿 plan → 绿色基线 → 并行执行 + 审计 → 阶段门禁测试 → testcase → DoD | 已有定稿 plan（通常来自 plan-bs），只要执行 + 测试 |
| `/plan-test` | 上面两段的一条龙自动版（需求澄清不走头脑风暴对话，走快速确认） | 需求已基本清楚，直接端到端做完 |

三个 skill 共享 `skills/plan-test/` 下的阶段文档、子代理提示词与配置。plan-bs 定稿时会在 `plan.md` 头部写 `<!-- plan-status: finalized -->` 标记，plan-task 开工前校验它——这是两段之间的交接契约。

灵感来自 superpowers 的 plan / test 系列 skill，针对"代码级可执行 plan + 子代理对抗迭代 + 真人测试"的工作流做了端到端编排。

## 设计原则

- **机器门是唯一完成 authority**：Markdown 规则是给人读的视图，不是状态 authority。测试事实记入 `verification/<run-id>/plan-test-run.json` 唯一账本，状态由 `skills/plan-test/scripts/plan_test_gate.py`（deterministic validator）重算；最终交付判定只接受 `finalize` 的 exit code 与 `gate-receipt.json`（**exit 0 = 交付通过；exit 3 = fixture-only 通过，不可交付**），没有有效 receipt 的手写 `SHIP / 100% COMPLETE` 一律视为 `DELIVERY_VERDICT_CONTRADICTS_LEDGER`。稳定诊断码（25 类）、状态机与 run 目录契约见 `skills/plan-test/gate/PROTOCOL.md`；schema（1.2.0）见 `skills/plan-test/schemas/plan-test-run.schema.json`；自测 `python skills/plan-test/scripts/test_plan_test_gate.py`（50 个用例）。
- **门要被调用才存在**：`hooks/` 提供 Stop hook 与 CI 片段，把"必须跑 finalize"从纪律变成强制。两者都不启用时，请如实说明机器门为自愿调用——Markdown 里写"必须跑"不构成强制。
- **适用性判定入账**：`input_sensitive` / `llm_payload_driven` / `stateful_init` 必须在 manifest 的 `applicability` 里显式声明（值 + 理由 + 判定人），冻结进账本与 receipt。判「不适用」合法但留痕可追责；判「适用」则场景矩阵必须真的兑现（`APPLICABILITY_GATE_UNSATISFIED`）。此前判一句"这是确定性 UI"就能让场景矩阵、正向价值、随机采样、冷启动四道门合法消失且无人知晓。
- **账本只能经 CLI 写**：每次写入追加 integrity 链，手改一行 `runs[].result` → `LEDGER_TAMPERED`（防顺手改，不防有决心的伪造）。审计产物里的 verdict 与命令行不一致 → 直接拒绝；`--engine` 与 executor 相同 → advisory 曝光自审自判。
- **流程分档（`FLOW_TIER`）**：S（单文件小改）/ M（≤3 文件单切面）/ L（全套 8 阶段）。开场必须宣布判档与依据——裁剪是明示选择，不是跑到一半偷偷省略。不可裁剪项：acceptance 唯一真相、提交态硬门、全表面冒烟、只增不减、BLOCKED 升级。
- **唯一真相来源**：一切（plan 收敛、完成度审计、testcase 覆盖）都回溯到 `acceptance.md` 的验收标准；事实源本身要过行为契约冻结 + acceptance challenger（防"单入口"被扩张成"单 Session"式语义跳跃），实现前冻结 black-box oracle（反转/放宽须用户批准的 `behavior_change_id`）。
- **每个声明可验证**：不靠"看起来做完了"，而是走可追溯矩阵 `AC ↔ 任务 ↔ 代码 ↔ testcase ↔ 结果`。
- **每个失败有出口**：所有"循环直到 100%"都有 `MAX_ROUNDS` 上限，超限标记 BLOCKED 升级，不空转烧 token。
- **功能只增不减**，**便宜的测试门在前、贵的真人测试在后**。
- **真架构问题优先重构，不小修小补**：迭代 plan 时若挑战出根因在结构层的问题（职责错位/边界穿透/循环依赖/抽象缺失），按最佳实践从结构上根治，不许用补丁绕过；判定须有证据、重构超范围时交用户拍板（防过度重写）。见 `phase-2-iterate-plan.md`。
- **调研有方法论**：调研阶段遵循毛选式问题解决纪律（没有调查没有发言权、抓主要矛盾、具体问题具体分析、解剖麻雀、实践—认识—再实践、集中优势兵力），见 `skills/plan-test/methods/research-method.md`。
- **循环判定结构化**：挑战/审计子代理末行统一 `VERDICT: PASS/FAIL`，编排者只按结论行判定循环去留，缺失按 FAIL 处理，不靠解读语气。
- **子代理带上下文包冷启动**：派发时嵌入验收条款、plan 片段与上轮结论，圈定读取范围；多轮迭代只挑战未闭环项，不重复烧 token。
- **架构文档增量校准**：ARCHITECTURE.md 带 `last-calibrated` commit 锚点，按 git diff 圈定过期章节增量更新，避免每次全仓重建。

## 安装

### 方式 A：本地目录加载

把本仓库 clone 到本地，在交互式 `claude` 终端用 `/plugin` 加载这个插件目录。

```bash
git clone https://github.com/DennyWanye/<repo>.git
# 然后在 claude 里 /plugin → 加载本地插件 → 选中该目录
```

### 方式 B：作为 marketplace 插件

把本仓库加入你的插件 marketplace 仓库后，通过 `/plugin` 搜索安装。

## 使用

装载后，三种触发方式：

1. **斜杠触发（推荐）**：
   ```
   /plan-bs 我想给登录模块加 OAuth，但没想清楚方案，和我讨论一下
   /plan-task plans/oauth-login          # 执行 plan-bs 定稿的 plan
   /plan-test 把登录模块从短信验证码升级为 OAuth + 短信双通道，要求：1.保留旧入口 2.……
   ```
2. **自然语言自动触发**：
   ```
   和我头脑风暴一下支付模块怎么升级，讨论好了出一份能 100% 执行的 plan   → plan-bs
   按 plans/pay-upgrade 这份计划并行执行，做完真人测试                  → plan-task
   帮我调研支付模块的升级方向，出 plan 并迭代好后并行执行，再做真人测试     → plan-test
   ```
3. **手动指名**："用 plan-bs / plan-task / plan-test 这个 skill 处理 XX"。

## 配置

默认值见 `skills/plan-test/config.md`。要按项目覆盖，在**项目根**放 `.claude/plan-test.config.md`，只写要改的键。参考 `examples/plan-test.config.md`。

常用覆盖：

```markdown
EXECUTOR_ENGINE: claude     # 本项目没装 codex，用 Claude 子代理执行
PLAN_ITERATIONS: 5          # plan 至少迭代 5 轮
MANUAL_TEST: required
```

## 目录结构

```
.claude-plugin/plugin.json          插件清单
hooks/                              Stop hook + CI 片段（把机器门变成强制调用）
skills/plan-bs/
└── SKILL.md                        头脑风暴 & 计划共创入口（引用 plan-test 的共享文档）
skills/plan-task/
└── SKILL.md                        执行 + 测试闭环入口（引用 plan-test 的共享文档）
skills/plan-test/
├── SKILL.md                        端到端一条龙入口（带 frontmatter）
├── config.md                       可配置默认值
├── phase-A-acceptance.md           需求澄清 & 验收标准
├── phase-0-architecture.md         架构基线
├── phase-1-plan.md                 写 plan
├── phase-2-iterate-plan.md         迭代 plan + 锁定绿色基线
├── phase-3-execute.md              并行执行 + 完成度审计
├── phase-4-stage-gate.md           阶段门禁 + 测试策略路由
├── phase-5-testcase.md             testcase 维护
├── phase-final-dod.md              收尾 DoD + 文档回写
├── gate/
│   ├── PROTOCOL.md                 门禁协议（诊断码/状态机/硬规则/**堵不住什么**）
│   └── ROADMAP.md                  已完成与未完成清单
├── scripts/
│   ├── plan_test_gate.py           canonical gate command
│   └── test_plan_test_gate.py      自测（50 用例）
├── methods/
│   └── research-method.md          调研方法论（毛选式：主要矛盾/反本本/解剖麻雀/实践论）
├── prompts/                        各子代理提示词（末行统一 VERDICT: PASS/FAIL 结论行）
└── checklists/                     幂等审查 / MCP 真人测试规程
```

## License

MIT
