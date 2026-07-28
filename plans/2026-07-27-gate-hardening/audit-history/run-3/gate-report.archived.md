# plan-test gate report

RUN: gate-hardening-run-3
STATE: BLOCKED
TESTED HEAD: ffd9c13c3a1fe4b3fd142681c8b47924c6a8a216
GATE RECEIPT: 无（不得宣布 SHIP）

## 适用性判定（判「不适用」等于放弃对应条件门，理由须可追责）
- input_sensitive: 不适用（agent 判定）理由：被测对象是确定性 CLI 与 shell hook，输出不随输入语义变化，无 LLM 生成路径
- llm_payload_driven: 不适用（agent 判定）理由：不存在 LLM 结构化载荷驱动端侧状态机或卡片渲染的路径
- stateful_init: 不适用（agent 判定）理由：纯 stdlib 脚本，无异步注册服务、远程配置或登录态依赖，无冷启动路径

## 场景状态（由 validator 重算）
- AC-1-applicability [required]: PASS
- AC-2-ledger-integrity [required]: PASS
- AC-3-auditor-consistency [required]: PASS
- AC-4-fixture-exit3 [required]: PASS
- AC-5-no-regression [required]: PASS
- AC-7-hook-enforcement [required]: PASS
- AC-8-content-attestation [required]: PASS
- AC-9-auditor-artifact [required]: PASS
- AC-10-reattest [required]: PASS
- AC-11-honest-gaps [required]: PASS

## 耗时分解（measured=CLI 单调时钟实测；declared=申报值，低信任）
- automated_test: measured 0.2 min / declared 0.0 min / retry 0 / abort 0 / tests 65
- checkpoints: 0

## 未闭环诊断
- RELEASE_UNIT_TOO_LARGE: task_count=12 超过阈值 10——拆成 program plan + 垂直 slice
- AUDITOR_MISSING: 独立 full-audit 尚未执行（先 audit 再 finalize）
- RECEIPT_STALE: 无 gate-receipt.json——先 finalize
