# eagle-map 强制层安装（备好未装，2026-08-26）

三个锚点的文件都已备好，但**都没有装进 eagle-map**——R1 检查时三个账本
（exec-001 / exec-002 / plan-loop-001）`finalize --check-only` 全 FAIL 且均未
retire / acknowledge，装上任何一个会拦 push 的锚点都会堵死业主自己的 push。

## 启用前置条件（必须先做）

对每个账本三选一：闭环（补测到 check-only PASS）、`retire --superseded-by <已
SHIPPABLE 的继任轮>`、或业主拍板后 `acknowledge --run-dir <dir> --reason "…"
--approval-hash <批准原话的 sha256>`（不可撤销，该 run 永远拿不到 receipt）。
确认命令：

```bash
cd ~/projects/eagle-map
for d in plans/eagle-gateway/verification/*/; do
  python3 ~/projects/plan-test-skill/skills/plan-test/scripts/plan_test_gate.py finalize --run-dir "$d" --check-only \
    && echo "PASS $d" || echo "FAIL $d"
done
```

## 全绿之后，按外部性从硬到软装

1. **pre-push**（本地，一条命令）：

   ```bash
   ~/projects/plan-test-skill/hooks/adapters/git/install-pre-push.sh ~/projects/eagle-map
   cd ~/projects/eagle-map && git push --dry-run   # 验证放行（不真推）
   ```

2. **风险声明**：把本目录 `plan-test-risk.globs` 复制到 eagle-map 的
   `.claude/plan-test-risk.globs` 并提交。glob 是 2026-08-26 现场对照的
   （凭据面 = `app/Models/Store.php` + `app/Services/Platforms/**` +
   `app/Services/Selection/AmazonCredentials.php`），结构变了要跟着改。

3. **CI**：把本目录 `plan-test-gate.yml` 复制到 eagle-map 的
   `.github/workflows/plan-test-gate.yml`，把 `PIN_TO_COMMIT_SHA` 替换成
   **已推送到 GitHub 的** skill 仓库 commit SHA（`git -C ~/projects/plan-test-skill
   rev-parse HEAD`，前提是该 commit 已 push），提交。
   验收：开一条改 `database/migrations/**` 但不带账本的测试分支 PR → tier_check 红；
   正常分支 → 绿。

## 本地已模拟过的验收

- tier_check 对"改 migration 无账本"红、"同 diff 带账本"绿：
  `skills/plan-test/scripts/test_tier_check.py`（11 用例）+ eagle-map 克隆上的实测。
- CI 的逐账本 step 语义与 pre-push 适配器同构，pre-push 已在临时仓库实测
  （失败账本拦、fixture_only 拦、干净仓库放行）。
