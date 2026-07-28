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

## 为什么这里没有账本文件（第九轮审计之后的更正）

第八轮独立审计指出：Stop hook 早先只扫 `*/verification/*`，**把 run 目录改个名字就能整体绕过
唯一的强制点**。修法是改成全仓按内容识别——而这一改立刻照出：把历史 run「移出 verification/」
本身就是在利用那个即将被堵掉的弱点。

第一次的做法是把 gate 产物改名（`plan-test-run.json` → `ledger.archived.json`）。
**第九轮审计把这条也打穿了**：hook 当时按文件名识别账本，改名即隐身——而本仓的"归档"方案
自己就是这条逃逸的一个实例。hook 已改为按**账本形状**识别（同时含 schema_version / run_id /
scenarios / integrity 的 JSON 就是账本，无论叫什么名字），改名不再有效。

因此这里的三份账本与 manifest **已被删除**（删除在 git diff 里可见，是显式动作），
只保留审计报告与 gate 报告——它们才是这三次 run 的价值所在。要查当时的账本原文，
`git show` 前一个 commit 即可。

这不是让失败的 run 消失：三份账本记录的仍然是「未闭环」这个真实状态，审计报告原样保留。
它们只是不再参与收尾阻断——因为工作已由 slice-a / slice-b 承接，而 `retire` 这条路走不通
（`retire` 要求继任者覆盖被退役 run 的全部 required 场景，而 run-3 的场景被拆到了两个 slice 里，
任何单个 slice 都不满足）。这是当前设计的一个真实边界：**拆 slice 之后，被拆分的整体 run
没有合法的 retire 路径**。已记在此处，供后来者决定是否要支持"多继任者"。
