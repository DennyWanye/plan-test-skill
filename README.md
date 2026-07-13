# plan-test

一个 Claude Code **插件**，含三个 skill，把"优化 / 升级 / 重构需求"走完整闭环：

```
需求澄清 & 验收标准  →  架构基线  →  写 plan  →  子代理挑战迭代
  →  并行执行 + 100% 完成度审计  →  测试策略路由(MCP真人测试 / 自动化脚本)
  →  收尾 DoD + 文档回写
```

| Skill | 覆盖范围 | 适用场景 |
|-------|---------|---------|
| `/plan-bs` | 头脑风暴对话 → 验收标准 → 架构基线 → 共创 plan → 挑战迭代 → 用户 review 定稿 | 想先和 AI 讨论清楚再定计划，**不执行代码** |
| `/plan-task` | 校验定稿 plan → 绿色基线 → 并行执行 + 审计 → 阶段门禁测试 → testcase → DoD | 已有定稿 plan（通常来自 plan-bs），只要执行 + 测试 |
| `/plan-test` | 上面两段的一条龙自动版（需求澄清不走头脑风暴对话，走快速确认） | 需求已基本清楚，直接端到端做完 |

三个 skill 共享 `skills/plan-test/` 下的阶段文档、子代理提示词与配置。plan-bs 定稿时会在 `plan.md` 头部写 `<!-- plan-status: finalized -->` 标记，plan-task 开工前校验它——这是两段之间的交接契约。

灵感来自 superpowers 的 plan / test 系列 skill，针对"代码级可执行 plan + 子代理对抗迭代 + 真人测试"的工作流做了端到端编排。

## 设计原则

- **唯一真相来源**：一切（plan 收敛、完成度审计、testcase 覆盖）都回溯到 `acceptance.md` 的验收标准。
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
├── methods/
│   └── research-method.md          调研方法论（毛选式：主要矛盾/反本本/解剖麻雀/实践论）
├── prompts/                        各子代理提示词（末行统一 VERDICT: PASS/FAIL 结论行）
└── checklists/                     幂等审查 / MCP 真人测试规程
```

## License

MIT
