# 收尾条件追加（phase-final-dod）

## program 多片

- 同一整体 run 内的片里程碑：只核该片能力、review/回归与提交身份，保持整体未完成，不执行整个 run 的终态/receipt 收尾。
- 各片独立 run：用 DoD 清单核该片完整冻结范围；片 receipt 不能扩大为整体 PASS。

## 输入语义敏感

任一不满足 → DoD FAIL（确定性 UI 不适用）：

- [ ] 至少 `{MANUAL_MIN_POSITIVE_SAMPLES}` 个 positive-value 场景达成（自然语言 + 真实入口 + 真实 provider + 非空有效结果 + 人工检查达 quality_bar）—— 广度账本业务终态列
- [ ] 没有任何正向 AC 靠负向安全行为（诚实降级/fail-closed）作证
- [ ] required 场景无 PENDING/PARTIAL/NOT RUN；distinct 计数达标且 retry/改写未混入
- [ ] 未执行项仅两种合法来源：acceptance 预标 optional/out-of-scope，或用户 chat 显式批准缩减（已回写 acceptance；结论按缩减后范围表述）
