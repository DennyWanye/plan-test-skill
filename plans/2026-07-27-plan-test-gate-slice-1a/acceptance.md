# Slice 1A（delta）验收标准 — schema、run-dir 与 fixture contract

> 基线：`main` @ `75ce2b42fb95cc70b0ea20e369150ad54056b631`（2026-07-27）。
> handoff（OPTIMIZATION-HANDOFF）写于 HEAD `5a4ea7c`，其"当前不存在 schema/validator/receipt"
> 的基线描述已过时——`75ce2b4` 已实现 Slice 1A–1D 核心（schema、gate CLI、validator、
> receipt、23 用例自测）。本 slice 是**对账后的 delta**：只覆盖 handoff 中尚未落地的
> contract 级内容，不重做已实现部分，不宣称已有可信 timing 采集。

## 范围内（本 slice 只做 contract 冻结与规划，代码实现须用户 review 后授权）

- **AC-1（必须）timing fact contract 已冻结**：`plan-test-run.json` 新增 `timing` 段的
  字段、类型、producer、consumer、authority、单位与时钟语义全部写入
  `plan.md` 与 schema 草案，覆盖 handoff §11 全部字段：
  phase/slice/task、command/tool、`started_at`/`ended_at`（RFC 3339 UTC）、
  `elapsed_ms`（非负整数、monotonic clock 测量）、activity_class、wait_reason、
  retry/abort、test count、runtime identity、evidence hash。
  验证：plan.md"timing contract"节逐字段有 producer/consumer/authority 三列；
  activity_class 枚举含 implementation / automated_test / manual_e2e / provider_wait /
  user_wait / interruption_recovery / rework 七类。
- **AC-2（必须）调用者可写与 validator 派生的边界已冻结**：明确哪些 timing 字段调用者
  可声明（phase/slice/task、activity_class、受控 wait_reason），哪些只能由 canonical CLI
  测量产生（started_at/ended_at/elapsed_ms via monotonic clock），声明式 timing（如真人
  E2E 外部计时）必须带 `measured: false` 标记且不计入"measured active"聚合。
  验证：plan.md 有显式规则表；fixture-contract.md 的 PASS fixture 含两类样例。
- **AC-3（必须）Companion normalized FAIL fixture 的格式与溯源契约已冻结**：
  fixture-contract.md 定义 normalized representation、provenance 记录
  （source_path + source_sha256 + normalized_by + captured_at）与 expected **有序**
  diagnostics（依次 `REQUIRED_SCENARIO_NOT_RUN` → `STATUS_CONFLICT` →
  `DELIVERY_VERDICT_CONTRADICTS_LEDGER`）。来源文件在另一台机器（F:\ / DeskPet），
  本机不可达——hash 采集步骤显式登记为 1D-delta 在该机器上的 BLOCKED 依赖，
  **不伪造 hash、不声称 dogfood 已带溯源执行**（现有 75ce2b4 的 dogfood 用例是合成
  数据，此事实在 plan.md 中如实标注）。
- **AC-4（必须）诊断排序契约已冻结**：同一 fixture 重跑必须得到相同且**有序**的
  diagnostic 序列；排序规则（按检查类别的固定序 + 类别内按 scenario/evidence id 字典序）
  写入 fixture-contract.md，并登记为 1B-delta 的实现项（现状：确定性来自实现顺序，
  未成文、未显式排序）。
- **AC-5（必须）handoff §9 的 13 个设计问题逐条有答案**：schema 版本迁移、facts/event
  取舍、可写边界、锁/CAS、证据分级、场景导入、legacy 规范化、diagnostic 结构、
  跨平台路径、零第三方依赖、三入口 skill 兼容、timing contract、回滚——每条在 plan.md
  有明确结论（已由 75ce2b4 实现的注明实现位置；未实现的注明归属 slice）。
- **AC-6（必须）静态 fixture 文件契约已定义**：最小 PASS fixture 与 Companion FAIL
  fixture 的**磁盘格式**（manifest.json + 期望诊断清单文件）在 fixture-contract.md 冻结，
  落盘实现归 1B/1D-delta；本 slice 不执行 finalize、不宣称 fixture 已运行。
- **AC-7（必须）规划产物齐备且有独立 challenger 审计**：本目录含 acceptance.md、
  plan.md、fixture-contract.md、evidence/challenger.md，challenger 末行 `VERDICT: PASS`。
- **AC-8（必须）回滚方案明确**：本 slice 及后续 1B-delta 的回滚步骤（git revert 粒度、
  schema_version 兼容策略、旧 receipt 的有效性）写入 plan.md。

## 范围外（明确不做，防 scope 蔓延）

- 不实现 timing 采集代码（`record-timing`/`checkpoint` 命令）——归 1B-delta，须用户
  review 本 plan 后授权。
- 不实现 legacy importer、不在本机执行带真实溯源的 Companion dogfood——归 1D-delta，
  且依赖能访问 F:\ 材料的机器。
- 不修改 DeskPet 产品代码；不做 Slice 2A/2B/3A–3C（behavior contract 采集自动化、
  internal test mutation report、runtime adapter 协议、project policy/lane closure）。
- 不 push（用户明确要求后才推送）。
- 不重做 75ce2b4 已实现并自测通过的部分（ledger CLI、validator、receipt/stale、
  现有 23 用例）。

## 完成定义

全部"必须"AC 有证据（文件路径 + 章节），challenger `VERDICT: PASS`，交用户 review。
用户批准前不进入实现。
