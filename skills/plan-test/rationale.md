# plan-test 设计背景（冷路径）

> 本文件解释“为什么”，不属于执行热路径。日常运行只读 `SKILL.md`、`config.md` 和当前 phase；
> 修改规则或做门禁退休评审时再读本文件，节省上下文与 token。

## 风险路径而非文件数

文件数不是风险：一个鉴权中间件可能比二十个文案文件更危险。DIRECT / LEAN / FULL 以可逆性、
信任边界、状态、公共契约和副作用判定，避免小改被全流程成本压垮，也避免单文件高风险改动被低估。

## Acceptance-preserving Ponytail

“只增不减”会把内部实现也误当成不可删除，最终鼓励重复 helper、wrapper 和防御性流程膨胀。
正确下限是已批准外部行为、assurance 和 required oracle；下限之上应尽量复用、删除和简化。
统一规则见 `policies/acceptance-preserving-ponytail.md`。

## 提交态与内容身份

脏工作树上的 PASS 不能证明交付提交。Gate 使用被测内容 digest，并把 run-dir 排除在 digest 外，
使“不改字节的提交”不使 receipt 失效，同时仍能拦截漏提交的代码和接线文件。

## Fanout 证据深度

一次 pytest/smoke 被复制登记到多条 AC，不等于多个场景都获得了独立断言。required 场景在 fanout
组中必须各有 primary evidence；使用 `record-run --exec` 或逐场景 attach 独立日志。

## 真人覆盖为何分开记账（phase-4 ①c 的病根）

同一个问题重复跑 4 次 + 一次 continuation，很容易被写成"真人验收充分"。深度（失败→重试→
恢复）证的是可靠性，广度（语义不等价的输入）证的是覆盖，两者混记就会用深度冒充广度。
W6-20 起账本表由 `render` 自动生成，人只补业务终态与 quality_bar 结论。

## 判档与遥测为何入账（W6-22/23 的病根）

FLOW_TIER 判 LEAN 使 phase-0 架构挑战、多轮 closure、testcase 多轮挑战合法消失，
却不留痕——enforcement-anchors run-001 实测判档理由失实（声称"无删改 hunk"实有 40 行
删除跨 9 文件），只靠人肉 auditor 事后发现。phase 遥测自愿制下 18 本真实账本仅 9 本有
阶段事件（user_wait declared 896.9min / measured 0），档位压缩效果永远无法评估，
"实践—认识—再实践"的循环是断的。两者与 applicability 同一待遇：判定是 fact，入账可追责。

## 门禁退休评审

真实复盘容易形成“发现绕过 → 再加一道门”的累积。每道门单看合理，整体可能成本过高。定期运行：

```bash
python skills/plan-test/scripts/gate_usage_report.py --repo-dir <repo>
```

真实 run 从未触发、只在 fixture 触发的门，应优先评估合并、降级或删除；时效性诊断单独看，避免
把随代码前进自然出现的 stale 当成门禁价值。
