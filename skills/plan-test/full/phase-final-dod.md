# 收尾 FULL 追加（`MACHINE_GATE` 启用时读）

## 收尾固定顺序（顺序错了会死锁）

1. 文档回写。
2. `re-attest --reason "收尾文档回写"`；判定 `kind=behavioral` 时 required 场景须重跑入账（push 前修复触及用户可见行为时也由此机器强制）。
3. 启用 active-run 绑定时重新 `activate-run`。
4. 重跑独立 full-audit 并 `audit` 入账（re-attest 改变了 fact，旧审计已 stale）。
5. `finalize` exit 0 拿 receipt → `render`。

- 最终交付判定只接受 `finalize` 的 exit code；exit 3 = fixture-only 不是完成。
- 无有效 receipt 的手写 SHIP/100% = `DELIVERY_VERDICT_CONTRADICTS_LEDGER`。
- FAIL 后又改了代码 → 回第 1 步重来。
- run-dir 产物不参与内容指纹与提交态检查（排除口径见 RULES R6）。

## DoD 追加

- [ ] `finalize` exit 0 + `GATE RECEIPT: <digest>` —— `gate-receipt.json`
- [ ] auditor open/deferred P0/P1 为零 —— `list-audit-findings`

## 交付措辞

FULL 路径用 receipt 模板：TESTED HEAD / SCOPE / 各 lane / KNOWN GAPS / GATE RECEIPT（见 `gate/PROTOCOL.md`）。
