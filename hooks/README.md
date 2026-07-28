# 让机器门变成"跑不掉"的门

`gate/PROTOCOL.md` 的 validator 只在**被调用时**才存在。Markdown 里写一百遍"必须跑
finalize"，也挡不住一个想尽快收尾的代理直接不跑——这是整套门禁最大的单点缺口。

本目录提供两种把调用变成强制的方式。**至少启用一种**，否则请在交付说明里如实写明
"机器门为自愿调用"。

## 方式 A：Claude Code Stop hook（本地开发时）

把 `stop-gate-check.sh` 接到 harness 的 Stop 事件上：代理准备结束回合时，脚本扫描仓库里
本次涉及的 run-dir，若存在 run-dir 而没有**有效 receipt**，就阻止"完成"表述。

```jsonc
// ~/.claude/settings.json 或项目 .claude/settings.json
{
  "hooks": {
    "Stop": [
      {
        "matcher": "*",
        "hooks": [
          { "type": "command",
            "command": "$CLAUDE_PROJECT_DIR/.claude/hooks/stop-gate-check.sh" }
        ]
      }
    ]
  }
}
```

安装：把 `stop-gate-check.sh` 复制到项目的 `.claude/hooks/` 并 `chmod +x`。

它检查什么（故意保守，避免误伤）：

- 只对**真正的 gate 记账物**生效：已 init 的账本（`plan-test-run.json`）、含 gate manifest
  的半截 run 目录（manifest 须有 `scenarios` 列表**且**含 `applicability` / `acceptance_file` /
  `source_request_*` 之一），或「账本被删但 `auditor-*.json` / `gate-receipt.json` 还在」的残留
  目录（那是让失败 run 悄悄消失的最便宜路径）。业务代码目录即使叫 `verification/`、里面的
  `manifest.json` 即使含 `run_id` 键，也不会触发——**这两种误报都是独立审计实测抓到后才修的**。
  没开账本的会话（S 档、纯问答、探索）不受影响；
- **仍会漏掉的**：`manifest.json` 内容为 `{}`、run 目录里只有 `artifacts/`、或只剩 `report.md`
  ——`report.md` 是通用文件名（业务的「来料检验报告」也叫这个），把它当 gate 信号会误伤
  `docs/verification/**`，所以刻意不认它。这些形态与普通目录无法区分，hook 放行；
- 对每个 run-dir 跑 `finalize --check-only`；FAIL 则以非零退出并打印诊断，让代理必须回去补；
- 它**不判断代理说了什么**，只判断账本状态。措辞类违规（手写 SHIP）仍由
  `DELIVERY_VERDICT_CONTRADICTS_LEDGER` 在账本侧兜。

## 方式 B：CI（团队协作时，更硬）

CI 跑在代理够不着的地方，是唯一真正外部的锚点。

```yaml
# .github/workflows/plan-test-gate.yml
name: plan-test gate
on: [push, pull_request]
jobs:
  gate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.11' }
      - name: gate self-test
        run: python skills/plan-test/scripts/test_plan_test_gate.py
      - name: verify every run ledger
        run: |
          set -e
          found=0
          for led in $(git ls-files '*/verification/*/plan-test-run.json'); do
            found=1
            dir=$(dirname "$led")
            echo "::group::$dir"
            python skills/plan-test/scripts/plan_test_gate.py finalize --run-dir "$dir" --check-only
            echo "::endgroup::"
          done
          [ "$found" = 1 ] || echo "本次没有提交任何 run 账本，跳过（S 档交付不建账本）"
```

注意 CI 里跑的是 `--check-only`：正式 `finalize` 需要 auditor 产物与当时的 HEAD/dirty 指纹，
在 CI 的干净 checkout 上会因 `TESTED_RUNTIME_MISMATCH` 而失败，那是预期行为，不是 bug。
要在 CI 校验完整交付，改为核对提交进仓库的 `gate-receipt.json` 的 `head` 是否等于该次提交。

## 这两种方式各自堵住什么

| | 建了账本却不闭环 | 压根不建账本 | 账本自相矛盾 | fixture 冒充交付 | 伪造证据 |
|---|---|---|---|---|---|
| 只有 Markdown 规则 | ✗ | ✗ | ✗ | ✗ | ✗ |
| Stop hook | ✓（除非经守卫校验的正当退役） | **✗** | ✓ | ✓ | ✗ |
| CI | ✓ | **✗** | ✓ | ✓ | ✗ |

两列必须如实标 ✗：

- **压根不建账本**：hook 只在发现 `*/verification/*/plan-test-run.json` 时才生效。代理若判成
  S 档（或干脆不开账本）直接收尾，hook 无感。要堵这一列，只能在项目侧规定"什么改动必须开账本"
  并由 CI 按改动面反查（例如：diff 命中 `src/routes/**` 却没有新 run 账本即 FAIL）——
  本目录不提供该规则，因为它依赖项目结构。
- **伪造证据**：截图/日志由代理自己生产，门只能校验它没被事后改动。

**已退役的历史 run 会被跳过，但退役本身有守卫**：hook 先跑 `finalize --check-only`，失败后才
询问 `retire-status`——后者要求账本链自洽、retire 经 CLI 执行、且继任 run 已 SHIPPABLE。
手写 `"retired": true` 不生效（会打印 `LEDGER_TAMPERED`），无继任者的退役被直接拒绝。
第一版无守卫的 retire 曾被独立审计实测成「加个字段就让门消失」，与 `fixture_only` 同形态。

**fixture 冒充交付**这一列是后补的：`finalize --check-only` 对 `fixture_only: true` 的账本
同样返回 0，只看退出码会被"给 manifest 加一个字段"整个绕过。hook 因此额外直接读账本的
`fixture_only` 字段，命中即阻止。
