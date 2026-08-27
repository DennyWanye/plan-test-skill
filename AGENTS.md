# plan-test-skill 代理/开发者须知（指针，规则正文不在本文件）

本仓库既是 plan-test 工作流的实现，也是它自己的被管对象（dogfooding）。规则正文只有一份，
在 `skills/plan-test/`（入口：`SKILL.md`、`config.md`、`gate/PROTOCOL.md`）。
本文件只做指针，**不要把规则复制进来**。

对任何 harness（Claude Code / Codex / Cursor / 手工）一致的硬约束：

1. 改动门禁资产（`skills/plan-test/scripts/plan_test_gate.py` 及配套）必须过它自己的
   全部测试套件：`python3 -m unittest discover -s skills/plan-test/scripts -p 'test*.py'`。
2. 行为性改动须走 plan-test 验证 run（唯一状态账本 + deterministic validator）；
   交付判定**只接受** `plan_test_gate.py finalize --run-dir <run-dir>` 的 exit code，
   手写 SHIP/100% COMPLETE 无效。
3. 在册 run 的账本只能经 gate CLI 写（手改即 `LEDGER_TAMPERED`）。注意生命周期耦合：
   receipt 绑定**全仓内容指纹**，任何提交都会让既有 receipt 过期；历史轮处置
   （retire/acknowledge）本身也是内容变更——新 run 的 manifest 应把既有
   `plans/**/verification/<run>` 目录列入 `related_run_dirs` 来解耦。
4. 强制层锚点（CI / git pre-push / Claude Code Stop hook）的唯一说明书是
   `hooks/README.md`（含锚点 × harness 能力矩阵与如实标注的残余缺口）。
