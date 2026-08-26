# plan-test gate report

RUN: enforcement-anchors-001
STATE: SHIPPABLE
TESTED HEAD: 147980cce6ed08cbed0b4b50f3ca4e6856b417c0
GATE RECEIPT: c52a8dc51a3e9ca044cf7eaf56eb562c3122c662f9d5ffe083e00109c6532ab3

## 身份说明（tested vs delivery，读 receipt 前必看）
- TESTED HEAD 是**测试时**的代码提交；把本 run-dir 的账本/截图/receipt 提交进仓库
  的后续提交（evidence-only descendant）**不改变被测内容指纹**，receipt 依然有效。
- 所以「receipt 的 head 早于仓库最终 HEAD」可以是完全合法的状态——判定依据是
  内容指纹（排除下方声明范围），不是提交号。若 tested HEAD 之后还改了任何非 run-dir
  文件，validator 会以 TESTED_RUNTIME_MISMATCH / RETEST_REQUIRED_AFTER_CHANGE 拦截。

## 适用性判定（判「不适用」等于放弃对应条件门，理由须可追责）
- input_sensitive: 不适用（agent 判定）理由：被测对象是确定性 CLI 与 shell hook，输出不随输入语义变化，无 LLM 生成路径
- llm_payload_driven: 不适用（agent 判定）理由：不存在 LLM 结构化载荷驱动端侧状态机或卡片渲染的路径
- stateful_init: 不适用（agent 判定）理由：纯 stdlib 脚本与 git 钩子，无异步注册服务、远程配置或登录态依赖

## 指纹排除范围（init 时冻结的显式声明；事后往仓库塞文件不改变它）
- 声明范围：plans/2026-08-26-enforcement-anchors/verification/run-001

## 本次命中排除的文件
- plans/2026-08-26-enforcement-anchors/verification/run-001/manifest.json（declared-scope:plans/2026-08-26-enforcement-anchors/verification/run-001）

## Evidence 计数（引用不等于独立证明）
- evidence records: 6
- distinct artifacts（按 sha256）: 6
- distinct root runs: 6
- shared artifact hashes: 0

## 审计与账本完整性
- 审计：verdict=PASS engine=claude-fable-5-subagent（产物 auditor-output.json）
- 账本链：自洽（12 条写入，链首 init）

## 场景状态（由 validator 重算）
- S-AC1-gate-selftest [required]: PASS
- S-AC2-stats [required]: PASS
- S-AC3-tier-check [required]: PASS
- S-AC4-phase-cost [required]: PASS
- S-AC5-pre-push-e2e [required]: PASS
- S-AC6-stop-hook-e2e [required]: PASS

## 未闭环诊断
- AUDITOR_ENGINE_MISMATCH（advisory，不拦截）: init 冻结 auditor_engine=claude-fable-5(subagent-auditor)，实际审计引擎=claude-fable-5-subagent——引擎配置被静默偏离

## 本 run 开销表（阶段 × 耗时 × 子代理数）

| 阶段 | 事件跨度(min) | timing 实测(min) | 子代理派发 | 轮次 |
|---|---|---|---|---|
| phase-4-stage-gate | 1.3 | 0.0 | 0 | 1 |
| audit | 3.8 | 0.0 | 1 | 1 |

> 遥测口径：跨度=配对 phase-start/end 时间差合计；实测=该阶段 measured timing；子代理/轮次=phase-end --subagents/--rounds 自报（未报=0）。供 LEAN 档压缩效果比对，不参与门判定。
