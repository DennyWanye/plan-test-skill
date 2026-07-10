# plan-test

一个 Claude Code **插件 skill**，把"优化 / 升级 / 重构需求"走完整闭环：

```
需求澄清 & 验收标准  →  架构基线  →  写 plan  →  子代理挑战迭代
  →  并行执行 + 100% 完成度审计  →  测试策略路由(MCP真人测试 / 自动化脚本)
  →  收尾 DoD + 文档回写
```

灵感来自 superpowers 的 plan / test 系列 skill，针对"代码级可执行 plan + 子代理对抗迭代 + 真人测试"的工作流做了端到端编排。

## 设计原则

- **唯一真相来源**：一切（plan 收敛、完成度审计、testcase 覆盖）都回溯到 `acceptance.md` 的验收标准。
- **每个声明可验证**：不靠"看起来做完了"，而是走可追溯矩阵 `AC ↔ 任务 ↔ 代码 ↔ testcase ↔ 结果`。
- **每个失败有出口**：所有"循环直到 100%"都有 `MAX_ROUNDS` 上限，超限标记 BLOCKED 升级，不空转烧 token。
- **功能只增不减**，**便宜的测试门在前、贵的真人测试在后**。
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

1. **斜杠触发（推荐）** —— 斜杠后的文字就是需求：
   ```
   /plan-test 把登录模块从短信验证码升级为 OAuth + 短信双通道，要求：1.保留旧入口 2.……
   ```
2. **自然语言自动触发**：
   ```
   帮我调研支付模块的升级方向，出一份能 100% 执行的 plan，迭代好后并行执行，再做真人测试
   ```
3. **手动指名**："用 plan-test 这个 skill 处理 XX"。

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
skills/plan-test/
├── SKILL.md                        主编排入口（带 frontmatter）
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
