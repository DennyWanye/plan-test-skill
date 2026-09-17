# Phase 收尾 — DoD + 文档回写 + 自我批评

## 片交付与整体收尾

- 按 `references/delivery-slices.md` 定片交付还是整体完成；program 多片 → `conditional/phase-final-dod.md`。
- 整体收尾覆盖原始全部 MUST、跨片组合能力和必要累计回归，缺证据即未完成。
- 片交付后按现有授权自主推进；生产发布不由切片自动授权。

## 收尾顺序

1. 文档回写：README / changelog / `{TESTCASE_DIR}/index.md`（项目自有架构文档顺手更新）。
2. DoD 清单逐条核对（下节）。
3. `journal.md` 末尾写终态行（RULES R12）。
4. 自我批评（RULES R12 各项＋哪些用户打断可消除）写 `{PLANS_DIR}/<feature>/retro.md`。
5. 提交：全部改动提交，工作树干净（RULES R6）。
5b. **交接复核（`HANDOFF_CHECK`）**：第 6 步之后、发完成消息之前，按 `checklists/handoff.md` H1 真实入口对照原话表、H0 消息结构，派评估员 `MODE: full`；硬伤修好重评 PASS 才发，文字类改完即发；记录行写 journal。
6. push 前 code review（仅推送远程时；不推送留理由）：P0/P1 修完再推；修复动代码 → 分层复验，触及用户可见行为 → 重跑受影响场景 + 至少 1 个未受影响类别；结论入 journal（RULES R7、R8）。
7. FULL（`MACHINE_GATE`）→ `full/phase-final-dod.md` 固定顺序。
8. 存储卫生：`du` 查大体积证据，超保留策略的只留可追溯指针或摘要；不删 active run、唯一证据、用户要求留存的；清理已完成且无未提交改动的临时 worktree，不动用户在用或来源不明的。

## DoD 清单（全绿才算完成，每条附证据位置）

> 附不上证据 → BLOCKED 升级（RULES R9）；验证针对已提交状态（RULES R6）。

- [ ] 决定性 AC 实测达成 —— 价值 smoke 输出 + 审计结论；此条 FAIL 不可救场（RULES R4）
- [ ] 整体可用性：核心路径整机走通（`checklists/handoff.md` H2.2–H2.3）—— journal/审计
- [ ] MUST AC 全有测试证据 —— phase-4 兑现表，无 ❌、无未批准降级（RULES R5）
- [ ] `a2-events.md` 全部已回炉闭环
- [ ] 工作树干净已提交 —— porcelain 空 + `git log -1`；警惕未跟踪接线文件（RULES R6）
- [ ] 多代理/worktree 实现时：干净态重启重跑价值 smoke + 分级冒烟，证明通过的代码 == HEAD
- [ ] 分级冒烟通过 —— 脚本输出 + 范围判断（RULES R8）
- [ ] 构建/测试/lint/类型不低于 phase-2 基线 —— 输出对比
- [ ] 幂等性审查逐条过 —— 审查结论
- [ ] AC ↔ 任务 ↔ 代码 ↔ testcase ↔ 证据无断点 —— 审计 VERDICT
- [ ] testcase 存盘、index 同步、脚本入回归套件 —— 路径
- [ ] 终态行与 DoD 结论一致 —— journal 末行（RULES R12）
- [ ] code review（A4 + push 前）P0/P1 全闭环且各有决定性测试 —— journal
- [ ] retro.md 自我批评 —— 路径
- [ ] 最近一次交接评估 PASS/文字类已改/DISPUTED 已记录（`HANDOFF_CHECK`）—— journal + 评估输出
- 追加：输入语义敏感 → `conditional/phase-final-dod.md`；FULL → `full/phase-final-dod.md`。

> **末尾自检**：UI 测试被换成审计？受阻场景未升级就替代？重跑充多场景？验证的 ≠ 交付的？命中 → 补或 BLOCKED。

## 升级与交付措辞

- 升级按 `checklists/handoff.md` H0/H3（首段写用户要做什么），走轻量评估（RULES R9）。
- "100%"只指声明范围内 required 门全绿；总体 BLOCKED 时用户要启动测试 → 先告知是已知失败版本、目的、已知失败场景。
- 交付措辞：写明"完成判定依据 journal 与 DoD 清单（无机器 receipt）"+ 测试范围 + 证据位置 + KNOWN GAPS（RULES R12）。
- 全绿总结：做了什么、主要矛盾如何被验证、覆盖哪些 AC、证据/文档更新在哪、新增回归。
