# plan-test

一个 Claude Code **插件**，含三个 skill，把"优化 / 升级 / 重构需求"走完整闭环：

```
矛盾分析与验收标准  →  调查与写 plan（实践先行 spike）  →  子代理挑战迭代（重点论收窄）
  →  执行（集中/分兵自决 + 里程碑 demo + 矛盾转化再分析）+ 100% 完成度审计
  →  围绕主要矛盾的验收(MCP真人测试 / 自动化脚本)  →  收尾 DoD + 文档回写 + 自我批评
```

| Skill | 覆盖范围 | 适用场景 |
|-------|---------|---------|
| `/plan-bs` | 头脑风暴对话（挖主要矛盾）→ 验收标准 → 调查 + 共创 plan → 挑战迭代 + spike 验证 → 用户 review 定稿 | 想先和 AI 讨论清楚再定计划；**不实现业务代码**（会跑可丢弃的验证 spike） |
| `/plan-task` | 校验定稿 plan → 绿色基线 → 执行 + 审计 → 围绕主要矛盾的验收 + testcase 收尾 → DoD | 已有定稿 plan（通常来自 plan-bs），只要执行 + 测试 |
| `/plan-test` | 上面两段的一条龙自动版（需求澄清不走头脑风暴对话，走快速确认） | 需求已基本清楚，直接端到端做完 |

三个 skill 共享 `skills/plan-test/` 下的阶段文档、子代理提示词与配置。plan-bs 定稿时会在 `plan.md` 头部写 `<!-- plan-status: finalized -->` 标记，plan-task 开工前校验它——这是两段之间的交接契约。

灵感来自 superpowers 的 plan / test 系列 skill，针对"代码级可执行 plan + 子代理对抗迭代 + 真人测试"的工作流做了端到端编排。

## 设计原则

- **减少用户打断（v0.8.0）**：根据已有目标和授权调查、制定计划并自主执行，不重复询问阶段切换或是否继续修复。确需用户决策时，先提供事实、推荐、代价与剩余未知；保留明确的等待、停止和操作授权边界。详见 [注意力与决策规则](skills/plan-test/references/user-attention.md)。
- **按可交付能力切片（v0.8.0）**：整体目标 → 可用能力切片 → 片内技术任务。每片有真实入口、实现前测试预期、依赖和保留能力；当前片细化后实施，整体风险提前调查。每片实际验证并形成可追溯提交后自主推进，原始全部验收与必要组合验证保留；小需求可以只有一片。详见 [切片规则](skills/plan-test/references/delivery-slices.md)。
- **战略上藐视，战术上重视（v0.7.0 总纲）**：战略上敢裁剪仪式——默认 LEAN、默认一页 journal 收尾、挑战与测试力度按矛盾地位收窄、说不出理由的门跳过留痕；战术上每条声明必须有实测证据——决定性 AC 必须真验证、真人测试不降级、提交态必须干净。**砍的是仪式，不是证据。**
- **围绕主要矛盾（毛选方法论为流程骨架）**：acceptance 第一节是矛盾分析四问（主要矛盾是什么/产生原因/怎么解决+最小验证动作/矛盾的主要方面）；每条 AC 标注决定性/次要，挑战轮次、执行火力、测试深度全按它路由；关键假设实践先行（写 plan 时当场 spike 真跑）；价值里程碑 PASS 后 demo 给用户 + 矛盾转化再分析；收尾写一行自我批评进 retro.md（门禁退休评审的数据源）。
- **机器门是启用时的唯一完成 authority（`MACHINE_GATE: full-high-externality-only`，v0.7.0 起为 FULL 且高外部性的 opt-in；默认路径完成记录 = 一页 journal + DoD 逐条证据）**：启用时 Markdown 规则是给人读的视图，不是状态 authority。测试事实记入 `verification/<run-id>/plan-test-run.json` 唯一账本，状态由 `skills/plan-test/scripts/plan_test_gate.py`（deterministic validator）重算；最终交付判定只接受 `finalize` 的 exit code 与 `gate-receipt.json`（**exit 0 = 交付通过；exit 3 = fixture-only 通过，不可交付**），没有有效 receipt 的手写 `SHIP / 100% COMPLETE` 一律视为 `DELIVERY_VERDICT_CONTRADICTS_LEDGER`。稳定诊断码、状态机与 run 目录契约见 `skills/plan-test/gate/PROTOCOL.md`；当前 schema 见 `skills/plan-test/schemas/plan-test-run.schema.json`；完整自测使用 unittest discovery。
- **门要被调用才存在**：`hooks/` 提供三个强制层锚点——CI（最硬）、git pre-push（harness 无关）、harness 原生钩子（Claude Code Stop hook 随插件自动挂载；Codex 无阻断钩子，靠前两者兜），把"必须跑 finalize"从纪律变成强制。一个都不启用时，请如实说明机器门为自愿调用——Markdown 里写"必须跑"不构成强制。锚点 × harness 矩阵见 `hooks/README.md`。
- **适用性判定入账**：`input_sensitive` / `llm_payload_driven` / `stateful_init` 必须在 manifest 的 `applicability` 里显式声明（值 + 理由 + 判定人），冻结进账本与 receipt。判「不适用」合法但留痕可追责；判「适用」则场景矩阵必须真的兑现（`APPLICABILITY_GATE_UNSATISFIED`）。此前判一句"这是确定性 UI"就能让场景矩阵、正向价值、随机采样、冷启动四道门合法消失且无人知晓。
- **账本只能经 CLI 写**：每次写入追加 integrity 链，手改一行 `runs[].result` → `LEDGER_TAMPERED`（防顺手改，不防有决心的伪造）。审计产物里的 verdict 与命令行不一致 → 直接拒绝；`--engine` 与 executor 相同 → advisory 曝光自审自判。
- **风险路径（`FLOW_TIER`）**：DIRECT（不启动重流程）/ LEAN（单切面）/ FULL（高风险全套）。
  依据可逆性、信任边界、状态、公共契约和副作用判定，而不是按文件数；开场必须说明依据。
- **唯一真相来源**：一切（plan 收敛、完成度审计、testcase 覆盖）都回溯到 `acceptance.md` 的验收标准；事实源本身要过行为契约冻结 + acceptance challenger（防"单入口"被扩张成"单 Session"式语义跳跃），实现前冻结 black-box oracle（反转/放宽须用户批准的 `behavior_change_id`）。
- **每个声明可验证**：不靠"看起来做完了"，而是走可追溯矩阵 `AC ↔ 任务 ↔ 代码 ↔ testcase ↔ 结果`。
- **每个失败有出口**：所有"循环直到 100%"都有 `MAX_ROUNDS` 上限，超限标记 BLOCKED 升级，不空转烧 token。
- **已批准外部行为不缩水，内部实现按 Ponytail 最小化**；便宜测试在前，昂贵真实环境测试在后。
- **真架构问题优先重构，不小修小补**：迭代 plan 时若挑战出根因在结构层的问题（职责错位/边界穿透/循环依赖/抽象缺失），按最佳实践从结构上根治，不许用补丁绕过；判定须有证据、重构超范围时交用户拍板（防过度重写）。见 `phase-2-iterate-plan.md`。
- **调研有方法论**：调研阶段遵循毛选式问题解决纪律（没有调查没有发言权、抓主要矛盾、具体问题具体分析、解剖麻雀、实践—认识—再实践、集中优势兵力），见 `skills/plan-test/methods/research-method.md`。
- **循环判定结构化**：挑战/审计子代理末行统一 `VERDICT: PASS/FAIL`，编排者只按结论行判定循环去留，缺失按 FAIL 处理，不靠解读语气。
- **子代理带上下文包冷启动**：派发时嵌入验收条款、plan 片段与上轮结论，圈定读取范围；多轮迭代只挑战未闭环项，不重复烧 token。
- **调查并入写 plan（v0.7.0 起）**：不再维护独立 ARCHITECTURE.md（原 phase-0 已退休，见 `skills/plan-test/retired/`）；现状调查围绕主要矛盾圈定范围、解剖麻雀，结论直接写进 plan 的现状栏——调查为决策服务，不为存档服务。

## 安装

本仓库自带 `.claude-plugin/marketplace.json`，本身就是一个 marketplace。

### 方式 A：从 GitHub 安装（推荐）

```bash
claude plugin marketplace add DennyWanye/plan-test-skill
claude plugin install plan-test@plan-test-skill
```

### 方式 B：从本地 clone 安装（开发/离线）

```bash
git clone https://github.com/DennyWanye/plan-test-skill.git
claude plugin marketplace add ./plan-test-skill
claude plugin install plan-test@plan-test-skill
```

装插件即挂 Stop hook（`hooks/hooks.json`，无 gate 记账物的会话实测 0.04s 放行）。
注意：安装是**快照**（复制到 `~/.claude/plugins/cache/`），仓库更新后要
`claude plugin update plan-test@plan-test-skill`（同版本号不刷新，必要时先 uninstall 再 install）。
git pre-push 与 CI 锚点不随插件自动启用，见 `hooks/README.md`。

不想装插件也可以手工复制 `skills/` 下三个目录到 `~/.claude/skills/`——但 Stop hook
需要按 `hooks/README.md` 自行挂到 settings.json，且两种安装别同时存在（会漂移）。

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
EXECUTOR_ENGINE: claude     # 默认 current=跟随当前会话模型；这里固定为 Claude 子代理
PLAN_ITERATIONS: 5          # plan 至少迭代 5 轮
MANUAL_TEST: required
```

## 运行记录（log）在哪里

每次验证运行（run）的记录都存在**被测项目内**，不在插件目录：

```
<你的项目>/plans/<plan 目录>/verification/<run-id>/
├── plan-test-run.json     唯一状态账本（所有原始测试事实，只能经 CLI 写入）
├── auditor-input.json     终审冻结输入
├── auditor-output.json    终审结论
├── gate-receipt.json      finalize 通过后才存在（exit 0 的凭证）
├── artifacts/             证据文件（截图、日志、命令回执）
└── report.md              人读报告（需手动 render 生成）
```

常用查看命令：

```bash
# 生成/刷新人读报告
python3 skills/plan-test/scripts/plan_test_gate.py render --run-dir <run-dir>

# 查看某次运行的交付判定
python3 skills/plan-test/scripts/plan_test_gate.py finalize --run-dir <run-dir> --check-only
```

注意区分三类记录：run 目录是 plan-test 的**测试账本**；Claude 会话聊天记录在本机 `~/.claude/projects/` 下；plan 文档本身在 `<你的项目>/plans/` 下。

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
