# 审计历史（已归档，不是活跃 run）

这三个目录是本次交付被拆成 slice 之前的整体验证 run，以及它们各自的独立审计报告。

**为什么移出 `verification/`**：它们的账本永远处于未闭环状态（工作已由 slice-a / slice-b 承接），
留在 `verification/` 下会让 Stop hook 永久阻断收尾。协议给的两条合法出路是：

1. `retire --superseded-by <已通过的继任 run>`——但那要求继任者**当时已有有效 receipt**，
   而本次是先归档、后验收，存在先有鸡还是先有蛋的问题；
2. **直接移出/删除该 run 目录**——删除与移动都会出现在 git 状态里，是可见动作。

这里走的是第 2 条。账本、证据、审计报告一字未改，只是换了位置。

**顺序陷阱（如实记录，供后来者避坑）**：这些账本文件位于 slice 的内容指纹范围内
（`exclusion_scope` 只含 slice-a / slice-b）。**在 slice 拿到 receipt 之后**再来移动或退役它们，
会被判成 behavioral 变更并触发全量重测。要处理历史 run，必须在 slice 的 attestation 之前做完。

## 内容

- `run-1/` —— 第一次整体验证 + 第一轮独立审计（判 FAIL：四处时序死结只修了说法）
- `run-2/` —— 第二次 + 第二轮审计（判 FAIL：attestation 只在 init 写一次，收尾必然锁死）
- `run-3/` —— 第三次，被 `RELEASE_UNIT_TOO_LARGE` 拦下（task_count=12 > 10），因此拆成两个 slice
