# Plan challenger compatibility router

旧入口仅用于已有调用兼容。新 phase-2 不直接派发本文件；先读取
`references/challenge-orchestration.md`，再按阶段选择：

- 第一轮主要挑战：`prompts/plan-primary-challenger.md`；
- 单个 root-cause cluster 深挖：`prompts/plan-specialist-challenger.md`；
- 主 agent 汇总：`prompts/plan-synthesis-reviewer.md`；
- 修订后闭环复核：`prompts/plan-closure-challenger.md`。

不要把四个 prompt 同时交给同一个子代理；共享的 finding、scope 和 stable-ID 纪律只以
`references/challenge-orchestration.md` 为准。
