# ERRATA — 本 plan 冻结产物的勘误（正文不改，错在这里认）

## E-1：acceptance.md 判档依据措辞失实（审计 F-001）

acceptance.md 的判档依据写了"改动全部为纯新增（git diff 无删改 hunk）"。**不实**：
commit 147980c 实有 40 行删除、分布在 9 个文件，其中含门禁组件 `hooks/stop-gate-check.sh`
的 3 行删改（路径解析候选列表重写）。正确的判档理由应为**"删改面已被回归覆盖"**
（该文件的拦/放两条路径由 AC-6 E2E 端到端钉住）。

**为什么不直接改 acceptance.md**：`retire` 要求继任 run 的 acceptance 与被退役 run
**逐字节相同**。本 plan 的 run 以 retire 链式接棒（run-001 → run-002 → …），acceptance.md
一旦变更，后续 run 就永远失去退役前任的资格——**同一 plan 谱系内的 acceptance 是
终身冻结的**，勘误只能落在这里。这也是给未来 plan 的教训：判档依据下笔前先核对 diff。

## E-2：schema 提示（2026-08-27 记）

同谱系冻结还意味着：required 场景集只能超集扩展、不能改名（retire 要求覆盖前任全部
required 场景）。写第一个 run 的 manifest 时就要按"这些 ID 会陪伴整个谱系"来起名。
