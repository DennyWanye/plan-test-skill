#!/usr/bin/env python3
"""plan-test 机器门禁（canonical gate command）。

唯一状态账本 = <run-dir>/plan-test-run.json。
所有 status/state 由本 validator 从原始 fact 重算，任何手写结论不作数。

用法（canonical，plan-task/plan-test 的最终判定只接受本命令的 exit code 与 stdout）：

  python plan_test_gate.py init            --run-dir D --manifest manifest.json
  python plan_test_gate.py record-run      --run-dir D --scenario S-1 --kind root ...
  python plan_test_gate.py attach-evidence --run-dir D --path artifacts/x.png ...
  python plan_test_gate.py declare-status  --run-dir D --source RESULTS.md --scenario S-1 --status PASS
  python plan_test_gate.py set-delivery    --run-dir D --verdict SHIP
  python plan_test_gate.py audit           --run-dir D --verdict PASS --input f --output f
  python plan_test_gate.py finalize        --run-dir D [--check-only]
  python plan_test_gate.py render          --run-dir D
  python plan_test_gate.py invalidate      --run-dir D --reason "..."

exit code：0 = 通过；1 = 门禁 FAIL（stdout 有 DIAG 行）；2 = 用法/IO 错误。
仅 stdlib，无第三方依赖。
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time

SCHEMA_VERSION = "1.1.0"
VALIDATOR_VERSION = "1.1.0"
LEDGER_NAME = "plan-test-run.json"
RECEIPT_NAME = "gate-receipt.json"
REPORT_NAME = "report.md"
LOCK_NAME = ".ledger.lock"

# 状态机（由 validator 计算，不可手写）
STATES = ["DRAFT", "ACCEPTED", "IMPLEMENTED", "TESTED", "VALIDATED", "SHIPPABLE"]

# 交付措辞里视为"宣布完成"的 verdict（与 ledger 冲突时触发硬门）
SHIP_VERDICTS = {"SHIP", "100% COMPLETE", "COMPLETE", "DONE", "SHIPPABLE"}

# release-unit 默认阈值（handoff P1-8；manifest.thresholds 可覆盖）
DEFAULT_THRESHOLDS = {
    "must_ac_count": 8,
    "task_count": 10,
    "plan_lines": 2000,
    "high_risk_subsystems": 3,
    "concurrent_layer_kinds": 3,
}

RESULT_VALUES = {"pass", "fail", "partial", "blocked", "not_run"}
KIND_VALUES = {"root", "retry", "continuation", "replay"}

# timing contract（plan 2026-07-27-plan-test-gate-slice-1a §2）
ACTIVITY_CLASSES = {"implementation", "automated_test", "manual_e2e", "provider_wait",
                    "user_wait", "interruption_recovery", "rework"}
WAIT_CLASSES = {"provider_wait", "user_wait"}
WAIT_REASONS = {"provider_latency", "quota_limit", "user_review", "user_input",
                "environment_provision"}
TIMING_GAP_MINUTES = 120  # advisory 门槛

# canonical 诊断排序（plan §3 唯一权威序；同类内按 hint/detail 字典序）
CANONICAL_ORDER = [
    "SCHEMA_INVALID", "REQUIRED_SCENARIO_NOT_RUN", "STATUS_CONFLICT",
    "DELIVERY_VERDICT_CONTRADICTS_LEDGER", "UI_EVIDENCE_MISSING",
    "RUN_CREATION_UNVERIFIED", "EVIDENCE_MISSING", "EVIDENCE_HASH_MISMATCH",
    "EVIDENCE_DEPENDENCY_CYCLE", "DERIVED_EVIDENCE_ONLY", "FROZEN_ORACLE_CHANGED",
    "BEHAVIOR_APPROVAL_REQUIRED", "RISK_CLOSURE_MISSING",
    "STABILITY_SAMPLES_INSUFFICIENT", "RELEASE_UNIT_TOO_LARGE",
    "TESTED_RUNTIME_MISMATCH", "AUDITOR_MISSING", "AUDITOR_INPUT_STALE",
    "RECEIPT_STALE", "TIMING_GAP",
]
_ORDER_INDEX = {c: i for i, c in enumerate(CANONICAL_ORDER)}


# ---------------------------------------------------------------- utilities

def die(msg, code=2):
    print("ERROR: %s" % msg, file=sys.stderr)
    sys.exit(code)


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def canonical_json(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def canonical_digest(obj):
    return sha256_text(canonical_json(obj))


def now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def atomic_write_json(path, obj):
    d = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".tmp-gate-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, sort_keys=True, indent=2)
            f.write("\n")
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


class LedgerLock(object):
    """单写者文件锁：O_CREAT|O_EXCL，带退避重试；防并行代理互相覆盖。"""

    def __init__(self, run_dir, timeout=10.0):
        self.path = os.path.join(run_dir, LOCK_NAME)
        self.timeout = timeout

    def __enter__(self):
        deadline = time.time() + self.timeout
        while True:
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, str(os.getpid()).encode())
                os.close(fd)
                return self
            except FileExistsError:
                if time.time() > deadline:
                    die("LEDGER_LOCKED: %s 被其他进程持有（并发写冲突，稍后重试）" % self.path)
                time.sleep(0.1)

    def __exit__(self, *exc):
        try:
            os.unlink(self.path)
        except OSError:
            pass


def ledger_path(run_dir):
    return os.path.join(run_dir, LEDGER_NAME)


def load_ledger(run_dir):
    p = ledger_path(run_dir)
    if not os.path.exists(p):
        die("run-dir 缺少 %s，先执行 init" % LEDGER_NAME)
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def save_ledger(run_dir, ledger, expect_revision=None):
    """CAS 写回：expect_revision 不匹配 → 稳定错误，不静默覆盖。"""
    p = ledger_path(run_dir)
    if os.path.exists(p):
        with open(p, "r", encoding="utf-8") as f:
            on_disk = json.load(f)
        if expect_revision is not None and on_disk.get("revision") != expect_revision:
            die("REVISION_CONFLICT: 磁盘 revision=%s 期望=%s（另一写者已更新，请重读后重试）"
                % (on_disk.get("revision"), expect_revision))
    ledger["revision"] = int(ledger.get("revision", 0)) + 1
    atomic_write_json(p, ledger)


def git(args, cwd):
    try:
        out = subprocess.run(["git"] + args, cwd=cwd, capture_output=True,
                             text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as e:
        return None, str(e)
    if out.returncode != 0:
        return None, out.stderr.strip()
    return out.stdout.strip(), None


def repo_head(repo):
    head, err = git(["rev-parse", "HEAD"], repo)
    return head


def repo_dirty_digest(repo, exclude_run_dir):
    """dirty patch hash：diff HEAD + untracked 清单；显式排除 verification run-dir
    （否则写 receipt/report 会让 receipt 自己立即 stale）。排除规则进 digest。"""
    rel_exclude = None
    if exclude_run_dir:
        try:
            rel_exclude = os.path.relpath(os.path.abspath(exclude_run_dir),
                                          os.path.abspath(repo))
        except ValueError:
            rel_exclude = None
        if rel_exclude and rel_exclude.startswith(".."):
            rel_exclude = None  # run-dir 在仓库外，无需排除
    diff_args = ["diff", "HEAD"]
    untracked_args = ["ls-files", "--others", "--exclude-standard"]
    if rel_exclude:
        diff_args += ["--", ".", ":(exclude)%s" % rel_exclude]
    diff, err = git(diff_args, repo)
    if diff is None:
        return None, err
    untracked, err = git(untracked_args, repo)
    if untracked is None:
        return None, err
    untracked_files = [u for u in untracked.splitlines()
                       if not (rel_exclude and (u == rel_exclude or u.startswith(rel_exclude + "/")))]
    payload = {"diff": diff, "untracked": sorted(untracked_files),
               "exclude_rule": rel_exclude or ""}
    return canonical_digest(payload), None


# ---------------------------------------------------------------- schema check

def _req(obj, key, typ, where, errors):
    if key not in obj:
        errors.append("SCHEMA_INVALID: %s 缺少字段 %s" % (where, key))
        return None
    if typ is not None and not isinstance(obj[key], typ):
        errors.append("SCHEMA_INVALID: %s.%s 类型错误（期望 %s）" % (where, key, typ))
        return None
    return obj[key]


def parse_rfc3339(s):
    """解析 RFC 3339 UTC（须 Z 或 +00:00 结尾），返回 epoch 秒；失败返回 None。"""
    import datetime
    try:
        dt = datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            return None
        return dt.timestamp()
    except (ValueError, AttributeError):
        return None


def structural_check(ledger):
    """最小结构校验（normative 契约见 schemas/plan-test-run.schema.json）。"""
    errors = []
    sv = _req(ledger, "schema_version", str, "ledger", errors)
    if sv:
        major = sv.split(".")[0]
        if major != SCHEMA_VERSION.split(".")[0]:
            errors.append("SCHEMA_INVALID: schema_version=%s 与 validator major=%s 不兼容"
                          % (sv, SCHEMA_VERSION.split(".")[0]))
    for i, t in enumerate(ledger.get("timing") or []):
        ac = _req(t, "activity_class", str, "timing[%d]" % i, errors)
        if ac is not None and ac not in ACTIVITY_CLASSES:
            errors.append("SCHEMA_INVALID: timing[%d].activity_class=%r 非法" % (i, ac))
        el = t.get("elapsed_ms")
        if el is not None and (not isinstance(el, int) or el < 0):
            errors.append("SCHEMA_INVALID: timing[%d].elapsed_ms 须为非负整数" % i)
        if "measured" in t and not isinstance(t["measured"], bool):
            errors.append("SCHEMA_INVALID: timing[%d].measured 须为 bool" % i)
    _req(ledger, "run_id", str, "ledger", errors)
    _req(ledger, "source_request", dict, "ledger", errors)
    scenarios = _req(ledger, "scenarios", list, "ledger", errors) or []
    _req(ledger, "runs", list, "ledger", errors)
    _req(ledger, "evidence", list, "ledger", errors)
    for i, s in enumerate(scenarios):
        _req(s, "scenario_id", str, "scenarios[%d]" % i, errors)
        _req(s, "required", bool, "scenarios[%d]" % i, errors)
    for i, r in enumerate(ledger.get("runs") or []):
        _req(r, "scenario_id", str, "runs[%d]" % i, errors)
        kind = _req(r, "kind", str, "runs[%d]" % i, errors)
        if kind is not None and kind not in KIND_VALUES:
            errors.append("SCHEMA_INVALID: runs[%d].kind=%r 非法" % (i, kind))
        result = _req(r, "result", str, "runs[%d]" % i, errors)
        if result is not None and result not in RESULT_VALUES:
            errors.append("SCHEMA_INVALID: runs[%d].result=%r 非法" % (i, result))
    for i, e in enumerate(ledger.get("evidence") or []):
        _req(e, "evidence_id", str, "evidence[%d]" % i, errors)
        _req(e, "path", str, "evidence[%d]" % i, errors)
        _req(e, "sha256", str, "evidence[%d]" % i, errors)
        kind = _req(e, "kind", str, "evidence[%d]" % i, errors)
        if kind is not None and kind not in ("primary", "derived"):
            errors.append("SCHEMA_INVALID: evidence[%d].kind=%r 非法" % (i, kind))
    return errors


# ---------------------------------------------------------------- validator

class Diag(object):
    def __init__(self, code, detail, hint=None, severity="error"):
        self.code = code
        self.detail = detail
        self.hint = hint or ""   # 类别内排序键（scenario_id/evidence_id/路径）
        self.severity = severity  # error=阻塞；advisory=提示不拦截

    def as_dict(self):
        return {"code": self.code, "detail": self.detail, "severity": self.severity}

    def sort_key(self):
        return (_ORDER_INDEX.get(self.code, len(CANONICAL_ORDER)),
                self.hint or self.detail, self.detail)


def sort_diags(diags):
    return sorted(diags, key=lambda d: d.sort_key())


def blocking(diags):
    return [d for d in diags if d.severity == "error"]


def compute_scenario_status(scenario, runs):
    """从原始 run fact 计算场景状态；调用者不能直接写状态。"""
    sid = scenario["scenario_id"]
    mine = [r for r in runs if r.get("scenario_id") == sid]
    roots = [r for r in mine if r.get("kind") == "root"]
    if not mine:
        return "NOT_RUN"
    if any(r.get("result") == "blocked" for r in mine):
        return "BLOCKED"
    if not roots:
        return "PARTIAL"  # 只有 retry/continuation，没有独立 root run
    if any(r.get("result") == "fail" for r in roots):
        return "FAIL"
    if all(r.get("result") == "pass" for r in roots):
        gate_type = scenario.get("gate_type", "")
        if gate_type == "positive-value":
            ok = [r for r in roots if r.get("result") == "pass"
                  and r.get("business_terminal") not in (None, "", "insufficient", "empty", "partial")]
            if not ok:
                return "PARTIAL"  # engine 绿但业务终态无效
        return "PASS"
    return "PARTIAL"


def auditor_facts_digest(ledger):
    """auditor 冻结输入指纹：除 auditor/delivery/receipt 事件外的全部 fact。"""
    facts = {k: v for k, v in ledger.items()
             if k not in ("auditor", "revision", "events")}
    return canonical_digest(facts)


def validate(run_dir, ledger, mode="full", fixture=False):
    """核心 validator。mode: check-only | full | render。返回 (diags, computed)。"""
    diags = []
    for err in structural_check(ledger):
        diags.append(Diag("SCHEMA_INVALID", err))
    scenarios = ledger.get("scenarios") or []
    runs = ledger.get("runs") or []
    evidence = ledger.get("evidence") or []
    ev_by_id = {e.get("evidence_id"): e for e in evidence}

    # 1. 场景状态重算 + required 硬门
    statuses = {}
    for s in scenarios:
        st = compute_scenario_status(s, runs)
        statuses[s["scenario_id"]] = st
        if s.get("required") and st in ("NOT_RUN", "PARTIAL", "BLOCKED", "FAIL"):
            diags.append(Diag("REQUIRED_SCENARIO_NOT_RUN",
                              "required 场景 %s 状态=%s（须 PASS）" % (s["scenario_id"], st),
                              hint=s["scenario_id"]))

    # 2. UI 场景必须有真实 UI action 的 primary evidence
    for s in scenarios:
        if not s.get("ui"):
            continue
        sid = s["scenario_id"]
        has_ui_ev = any(e.get("scenario_id") == sid and e.get("kind") == "primary"
                        and e.get("ui_action") for e in evidence)
        if s.get("required") and statuses.get(sid) == "PASS" and not has_ui_ev:
            diags.append(Diag("UI_EVIDENCE_MISSING",
                              "UI 场景 %s 判 PASS 但无 ui_action=primary 证据" % sid,
                              hint=sid))

    # 3. expected_run_created 正反向核对
    for s in scenarios:
        sid = s["scenario_id"]
        if "expected_run_created" not in s or statuses.get(sid) != "PASS":
            continue
        roots = [r for r in runs if r.get("scenario_id") == sid and r.get("kind") == "root"]
        if s["expected_run_created"]:
            if not any(r.get("run_id_under_test") for r in roots):
                diags.append(Diag("RUN_CREATION_UNVERIFIED",
                                  "场景 %s 声明应创建 root Run，但未记录 run_id_under_test" % sid,
                                  hint=sid))
        else:
            if not any(e.get("scenario_id") == sid and e.get("negative_assertion")
                       for e in evidence):
                diags.append(Diag("RUN_CREATION_UNVERIFIED",
                                  "场景 %s 声明不应创建 Run，但缺少负向证据（negative_assertion）" % sid,
                                  hint=sid))

    # 4. 证据存在性 + hash + 依赖图
    for e in evidence:
        p = os.path.join(run_dir, e.get("path", ""))
        if not os.path.exists(p):
            diags.append(Diag("EVIDENCE_MISSING", "证据文件不存在: %s" % e.get("path"), hint=e.get("path")))
        elif sha256_file(p) != e.get("sha256"):
            diags.append(Diag("EVIDENCE_HASH_MISMATCH", "证据被改动: %s" % e.get("path"), hint=e.get("path")))
        for dep in e.get("depends_on") or []:
            if dep not in ev_by_id:
                diags.append(Diag("EVIDENCE_MISSING",
                                  "%s 依赖不存在的证据 %s" % (e.get("evidence_id"), dep)))
    # 依赖环检测（derived report 相互引用不能构成独立证据）
    color = {}

    def has_cycle(eid, stack):
        color[eid] = 1
        for dep in (ev_by_id.get(eid, {}).get("depends_on") or []):
            if color.get(dep) == 1:
                return stack + [dep]
            if color.get(dep, 0) == 0 and dep in ev_by_id:
                r = has_cycle(dep, stack + [dep])
                if r:
                    return r
        color[eid] = 2
        return None

    for eid in ev_by_id:
        if color.get(eid, 0) == 0:
            cyc = has_cycle(eid, [eid])
            if cyc:
                diags.append(Diag("EVIDENCE_DEPENDENCY_CYCLE",
                                  "证据循环引用: %s" % " -> ".join(cyc)))
                break
    # required 场景仅有 derived 证据 → 不算证明
    for s in scenarios:
        sid = s["scenario_id"]
        if not s.get("required") or statuses.get(sid) != "PASS":
            continue
        mine = [e for e in evidence if e.get("scenario_id") == sid]
        if mine and not any(e.get("kind") == "primary" for e in mine):
            diags.append(Diag("DERIVED_EVIDENCE_ONLY",
                              "场景 %s 只有 derived report，无 primary 证据" % sid,
                              hint=sid))

    # 5. 冻结 black-box oracle 变异审计
    for tc in (ledger.get("testcase_lock") or {}).get("files") or []:
        p = tc.get("abs_path") or tc.get("path")
        if p and not os.path.isabs(p):
            p = os.path.join(run_dir, p)
        if not p or not os.path.exists(p):
            diags.append(Diag("FROZEN_ORACLE_CHANGED",
                              "冻结 testcase 文件缺失: %s" % tc.get("path")))
            continue
        if sha256_file(p) != tc.get("sha256"):
            change_id = tc.get("behavior_change_id")
            approved = False
            for bc in ledger.get("behavior_changes") or []:
                if bc.get("behavior_change_id") == change_id and bc.get("approval"):
                    approved = True
            if change_id and not approved:
                diags.append(Diag("BEHAVIOR_APPROVAL_REQUIRED",
                                  "testcase %s 变更引用 %s 但无用户批准 artifact"
                                  % (tc.get("path"), change_id)))
            elif not change_id:
                diags.append(Diag("FROZEN_ORACLE_CHANGED",
                                  "冻结 testcase %s 内容已变且无 behavior_change_id"
                                  % tc.get("path")))
    for bc in ledger.get("behavior_changes") or []:
        if not bc.get("approval"):
            diags.append(Diag("BEHAVIOR_APPROVAL_REQUIRED",
                              "行为变更 %s 缺少批准 artifact（exact old/new + 用户消息 hash + scope）"
                              % bc.get("behavior_change_id")))

    # 6. declared status（README/RESULTS/Gate 报告等文档口径）与重算结果对账
    declared = ledger.get("declared_statuses") or []
    for d in declared:
        sid = d.get("scenario_id")
        if sid and sid in statuses:
            norm = str(d.get("status", "")).strip().upper().replace(" ", "_")
            if norm in ("PASS", "PASSED", "✅") and statuses[sid] != "PASS":
                diags.append(Diag("STATUS_CONFLICT",
                                  "%s 声称 %s=%s，但账本重算=%s"
                                  % (d.get("source"), sid, d.get("status"), statuses[sid]),
                                  hint=sid))
            if norm in ("NOT_RUN", "PENDING", "PARTIAL", "BLOCKED") and statuses[sid] == "PASS":
                diags.append(Diag("STATUS_CONFLICT",
                                  "%s 声称 %s=%s，但账本重算=PASS——文档未同步"
                                  % (d.get("source"), sid, d.get("status")),
                                  hint=sid))

    # 7. 交付结论 vs 账本
    required_all_pass = all(statuses.get(s["scenario_id"]) == "PASS"
                            for s in scenarios if s.get("required"))
    delivery = ledger.get("delivery") or {}
    verdict = str(delivery.get("verdict") or "").strip().upper()
    if verdict and verdict in SHIP_VERDICTS and not (required_all_pass and scenarios):
        diags.append(Diag("DELIVERY_VERDICT_CONTRADICTS_LEDGER",
                          "交付结论 %r 与账本冲突（required 未全 PASS 或无场景）" % delivery.get("verdict")))

    # 8. required lanes closure
    for s in scenarios:
        sid = s["scenario_id"]
        for lane in s.get("required_lanes") or []:
            if not any(r.get("scenario_id") == sid and r.get("lane") == lane
                       and r.get("kind") == "root" and r.get("result") == "pass"
                       for r in runs):
                diags.append(Diag("RISK_CLOSURE_MISSING",
                                  "场景 %s 缺少 required lane=%s 的通过 root run" % (sid, lane),
                                  hint="%s/%s" % (sid, lane)))

    # 9. 非确定性稳定性（stochastic）：min_root_runs 未达 → 采样不足
    for s in scenarios:
        need = s.get("min_root_runs")
        if not need:
            continue
        sid = s["scenario_id"]
        ok_roots = [r for r in runs if r.get("scenario_id") == sid
                    and r.get("kind") == "root" and r.get("result") == "pass"]
        all_roots = [r for r in runs if r.get("scenario_id") == sid and r.get("kind") == "root"]
        if statuses.get(sid) == "PASS" and len(ok_roots) < need:
            diags.append(Diag("STABILITY_SAMPLES_INSUFFICIENT",
                              "场景 %s 需要 ≥%d 次独立 root run，仅 %d 次通过"
                              % (sid, need, len(ok_roots))))
        if all_roots and ok_roots and len(ok_roots) < len(all_roots):
            statuses[sid] = "FLAKY" if statuses.get(sid) == "PASS" else statuses[sid]
            if s.get("required") and statuses[sid] == "FLAKY":
                diags.append(Diag("STABILITY_SAMPLES_INSUFFICIENT",
                                  "场景 %s FLAKY（%d/%d 通过且有未解释失败），不得 SHIP"
                                  % (sid, len(ok_roots), len(all_roots))))

    # 10. release-unit 大小
    metrics = ledger.get("release_unit") or {}
    thresholds = dict(DEFAULT_THRESHOLDS)
    thresholds.update(ledger.get("thresholds") or {})
    for key, limit in thresholds.items():
        val = metrics.get(key)
        if val is not None and val > limit:
            diags.append(Diag("RELEASE_UNIT_TOO_LARGE",
                              "%s=%s 超过阈值 %s——拆成 program plan + 垂直 slice" % (key, val, limit)))

    # 11. runtime attestation / HEAD 一致性
    att = ledger.get("runtime_attestation") or {}
    baseline = ledger.get("baseline") or {}
    if not fixture:
        repo = ledger.get("repo_root") or os.getcwd()
        head = repo_head(repo)
        if head is None:
            diags.append(Diag("TESTED_RUNTIME_MISMATCH",
                              "无法读取当前 git HEAD（repo_root=%s）" % repo))
        else:
            tested = att.get("head") or baseline.get("head")
            if tested and tested != head:
                diags.append(Diag("TESTED_RUNTIME_MISMATCH",
                                  "tested HEAD=%s 当前 HEAD=%s（测试后有新提交/换树）" % (tested, head)))
            dirty, err = repo_dirty_digest(repo, run_dir)
            tested_dirty = att.get("dirty_patch_sha256") or baseline.get("dirty_patch_sha256")
            if dirty is not None and tested_dirty and tested_dirty != dirty:
                diags.append(Diag("TESTED_RUNTIME_MISMATCH",
                                  "工作树 dirty 指纹与测试时不一致（排除 run-dir 后仍有差异）"))
    if att.get("adapter_status") == "UNKNOWN":
        diags.append(Diag("TESTED_RUNTIME_MISMATCH",
                          "runtime adapter 返回 UNKNOWN——真实 E2E 只能记 BLOCKED，不得口头确认"))

    # 12. auditor（仅 full/render 模式要求）
    auditor = ledger.get("auditor") or {}
    if mode in ("full", "render"):
        if not auditor:
            diags.append(Diag("AUDITOR_MISSING", "独立 full-audit 尚未执行（先 audit 再 finalize）"))
        else:
            if str(auditor.get("verdict", "")).upper() != "PASS":
                diags.append(Diag("AUDITOR_MISSING",
                                  "auditor verdict=%s（须 PASS）" % auditor.get("verdict")))
            expected = auditor_facts_digest(ledger)
            if auditor.get("facts_digest") != expected:
                diags.append(Diag("AUDITOR_INPUT_STALE",
                                  "audit 之后 ledger fact 已变化——旧审计 PASS 失效，须重审"))
            for key in ("input_sha256", "output_sha256"):
                fname = auditor.get(key.replace("_sha256", "_path"))
                if fname:
                    p = os.path.join(run_dir, fname)
                    if not os.path.exists(p):
                        diags.append(Diag("EVIDENCE_MISSING", "auditor 文件缺失: %s" % fname))
                    elif sha256_file(p) != auditor.get(key):
                        diags.append(Diag("EVIDENCE_HASH_MISMATCH",
                                          "auditor 文件被改动: %s" % fname))

    # 13. TIMING_GAP（advisory，不拦截）：相邻 timing/checkpoint 锚点间隔 > 120 分钟
    anchors = []
    for t in ledger.get("timing") or []:
        for k in ("started_at", "ended_at"):
            ts = parse_rfc3339(t.get(k) or "")
            if ts is not None:
                anchors.append(ts)
    for ev in ledger.get("events") or []:
        if ev.get("type") == "checkpoint":
            ts = parse_rfc3339(ev.get("at") or "")
            if ts is not None:
                anchors.append(ts)
    anchors.sort()
    for a, b in zip(anchors, anchors[1:]):
        gap_min = (b - a) / 60.0
        if gap_min > TIMING_GAP_MINUTES:
            diags.append(Diag("TIMING_GAP",
                              "相邻记账锚点间隔 %.0f 分钟（>%d）——长时间无 record-timing/checkpoint"
                              % (gap_min, TIMING_GAP_MINUTES), severity="advisory"))
            break

    diags = sort_diags(diags)
    computed = {
        "scenario_statuses": statuses,
        "required_all_pass": required_all_pass and bool(scenarios),
        "state": compute_state(ledger, statuses, diags, mode),
    }
    return diags, computed


def compute_state(ledger, statuses, diags, mode):
    codes = {d.code for d in blocking(diags)}  # advisory 不影响状态机
    scenarios = ledger.get("scenarios") or []
    if not scenarios or "SCHEMA_INVALID" in codes:
        return "DRAFT"
    state = "DRAFT"
    if ledger.get("source_request", {}).get("sha256") and ledger.get("acceptance", {}).get("sha256"):
        state = "ACCEPTED"
    if state == "ACCEPTED" and (ledger.get("baseline") or {}).get("head"):
        state = "IMPLEMENTED"
    required = [s for s in scenarios if s.get("required")]
    if state == "IMPLEMENTED" and required and all(
            statuses.get(s["scenario_id"]) == "PASS" for s in required):
        state = "TESTED"
    pre_audit_codes = codes - {"AUDITOR_MISSING"}
    if state == "TESTED" and not pre_audit_codes:
        state = "VALIDATED"
    if state == "VALIDATED" and mode in ("full", "render") and not codes:
        state = "SHIPPABLE"
    return state


# ---------------------------------------------------------------- receipt

RECEIPT_IDENTITY_EXCLUDE = ("finalized_at", "content_digest")


def build_receipt(run_dir, ledger, computed):
    evidence_manifest = sorted(
        [{"path": e.get("path"), "sha256": e.get("sha256")} for e in ledger.get("evidence") or []],
        key=lambda x: (x["path"] or ""))
    auditor = ledger.get("auditor") or {}
    att = ledger.get("runtime_attestation") or {}
    baseline = ledger.get("baseline") or {}
    receipt = {
        "receipt_version": 1,
        "run_id": ledger.get("run_id"),
        "schema_version": ledger.get("schema_version"),
        "validator_version": VALIDATOR_VERSION,
        "state": computed["state"],
        "ledger_sha256": canonical_digest({k: v for k, v in ledger.items() if k != "revision"}),
        "evidence_manifest_sha256": canonical_digest(evidence_manifest),
        "acceptance_sha256": (ledger.get("acceptance") or {}).get("sha256"),
        "testcase_lock_sha256": canonical_digest(ledger.get("testcase_lock") or {}),
        "auditor_input_sha256": auditor.get("input_sha256"),
        "auditor_output_sha256": auditor.get("output_sha256"),
        "head": att.get("head") or baseline.get("head"),
        "dirty_patch_sha256": att.get("dirty_patch_sha256") or baseline.get("dirty_patch_sha256"),
        "fixture_only": bool(ledger.get("fixture_only")),
        "scenario_statuses": computed["scenario_statuses"],
    }
    identity = {k: v for k, v in receipt.items() if k not in RECEIPT_IDENTITY_EXCLUDE}
    receipt["content_digest"] = canonical_digest(identity)
    return receipt


def load_receipt(run_dir):
    p = os.path.join(run_dir, RECEIPT_NAME)
    if not os.path.exists(p):
        return None
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def receipt_is_stale(run_dir, ledger, computed, receipt):
    fresh = build_receipt(run_dir, ledger, computed)
    return fresh["content_digest"] != receipt.get("content_digest")


# ---------------------------------------------------------------- commands

def emit(diags, computed=None, extra=None):
    for d in diags:
        prefix = "DIAG" if d.severity == "error" else "ADVISORY"
        print("%s %s: %s" % (prefix, d.code, d.detail))
    if computed:
        print("STATE: %s" % computed["state"])
    for line in extra or []:
        print(line)


def cmd_init(args):
    run_dir = args.run_dir
    os.makedirs(os.path.join(run_dir, "artifacts"), exist_ok=True)
    if os.path.exists(ledger_path(run_dir)) and not args.force:
        die("run-dir 已 init（%s 存在）；重开新 run 请换目录" % LEDGER_NAME)
    with open(args.manifest, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    repo = os.path.abspath(manifest.get("repo_root") or os.getcwd())
    fixture = bool(manifest.get("fixture_only"))
    ledger = {
        "schema_version": SCHEMA_VERSION,
        "run_id": manifest.get("run_id") or ("run-" + time.strftime("%Y%m%d-%H%M%S")),
        "created_at": now_iso(),
        "repo_root": repo,
        "fixture_only": fixture,
        "source_request": {},
        "behavior_contract": manifest.get("behavior_contract") or {},
        "behavior_changes": manifest.get("behavior_changes") or [],
        "acceptance": {},
        "testcase_lock": {"files": [], "locked_at": None},
        "scenarios": [],
        "runs": [],
        "evidence": [],
        "declared_statuses": [],
        "delivery": {},
        "release_unit": manifest.get("release_unit") or {},
        "thresholds": manifest.get("thresholds") or {},
        "baseline": {},
        "runtime_attestation": manifest.get("runtime_attestation") or {},
        "events": [],
        "revision": 0,
    }
    # 冻结原始需求
    sr = manifest.get("source_request_file")
    if sr:
        ledger["source_request"] = {"path": sr, "sha256": sha256_file(sr)}
    elif manifest.get("source_request_text"):
        ledger["source_request"] = {"inline": True,
                                    "sha256": sha256_text(manifest["source_request_text"])}
    # 冻结 acceptance
    acc = manifest.get("acceptance_file")
    if acc:
        ledger["acceptance"] = {"path": acc, "sha256": sha256_file(acc)}
    # 冻结 black-box testcase oracle
    for tc in manifest.get("testcase_files") or []:
        ledger["testcase_lock"]["files"].append(
            {"path": tc, "abs_path": os.path.abspath(tc), "sha256": sha256_file(tc)})
    if ledger["testcase_lock"]["files"]:
        ledger["testcase_lock"]["locked_at"] = now_iso()
    # required rows 由 init 自动创建为 NOT_RUN（不可由调用者直接置 PASS）
    for s in manifest.get("scenarios") or []:
        if "scenario_id" not in s:
            die("manifest.scenarios 每项必须有 scenario_id")
        s.setdefault("required", True)
        ledger["scenarios"].append(s)
    # baseline attestation
    if not fixture:
        head = repo_head(repo)
        if head is None:
            die("repo_root=%s 不是 git 仓库；fixture 请在 manifest 里设 fixture_only=true" % repo)
        dirty, err = repo_dirty_digest(repo, run_dir)
        ledger["baseline"] = {"head": head, "dirty_patch_sha256": dirty,
                              "recorded_at": now_iso()}
    else:
        ledger["baseline"] = manifest.get("baseline") or {}
    with LedgerLock(run_dir):
        save_ledger(run_dir, ledger)
    print("INIT OK run_id=%s scenarios=%d (全部 NOT_RUN)" % (
        ledger["run_id"], len(ledger["scenarios"])))


def _append(run_dir, mutate):
    with LedgerLock(run_dir):
        ledger = load_ledger(run_dir)
        rev = ledger.get("revision")
        mutate(ledger)
        # 任何 fact 变化都会使既有 receipt stale（finalize 会重算）；此处只记事实
        save_ledger(run_dir, ledger, expect_revision=rev)
        return ledger


def cmd_record_run(args):
    rec = {
        "scenario_id": args.scenario,
        "kind": args.kind,
        "lane": args.lane,
        "driver": args.driver,
        "result": args.result,
        "command": args.command,
        "engine_terminal": args.engine_terminal,
        "business_terminal": args.business_terminal,
        "session_id": args.session_id,
        "run_id_under_test": args.run_id_under_test,
        "recorded_at": now_iso(),
    }
    rec = {k: v for k, v in rec.items() if v is not None}

    def mutate(ledger):
        if args.scenario not in {s["scenario_id"] for s in ledger.get("scenarios", [])}:
            die("场景 %s 不在 init 冻结的场景清单里（不许测后补场景，需重新 init/批准）" % args.scenario)
        ledger["runs"].append(rec)

    _append(args.run_dir, mutate)
    print("RECORDED run scenario=%s kind=%s result=%s" % (args.scenario, args.kind, args.result))


def cmd_attach_evidence(args):
    p = os.path.join(args.run_dir, args.path)
    if not os.path.exists(p):
        die("证据文件不存在: %s（路径须相对 run-dir）" % p)
    ev = {
        "evidence_id": args.id or ("ev-" + sha256_file(p)[:12]),
        "path": args.path,
        "sha256": sha256_file(p),
        "kind": args.kind,
        "scenario_id": args.scenario,
        "ui_action": args.ui_action,
        "negative_assertion": args.negative_assertion,
        "depends_on": args.depends_on or [],
        "attached_at": now_iso(),
    }
    ev = {k: v for k, v in ev.items() if v not in (None, False, [])}

    def mutate(ledger):
        ledger["evidence"].append(ev)

    _append(args.run_dir, mutate)
    print("ATTACHED %s kind=%s sha256=%s" % (args.path, args.kind, ev["sha256"][:12]))


def cmd_declare_status(args):
    def mutate(ledger):
        ledger.setdefault("declared_statuses", []).append(
            {"source": args.source, "scenario_id": args.scenario,
             "status": args.status, "recorded_at": now_iso()})

    _append(args.run_dir, mutate)
    print("DECLARED %s: %s=%s（将与账本重算结果对账）" % (args.source, args.scenario, args.status))


def cmd_set_delivery(args):
    def mutate(ledger):
        ledger["delivery"] = {"verdict": args.verdict, "recorded_at": now_iso()}

    _append(args.run_dir, mutate)
    print("DELIVERY VERDICT RECORDED: %s（是否成立由 finalize 判定）" % args.verdict)


def _utc_iso(epoch):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


def cmd_record_timing(args):
    if args.activity_class not in ACTIVITY_CLASSES:
        die("activity_class=%r 非法（合法：%s）" % (args.activity_class,
                                                  "/".join(sorted(ACTIVITY_CLASSES))))
    if args.activity_class in WAIT_CLASSES:
        wr = args.wait_reason or ""
        if wr not in WAIT_REASONS and not wr.startswith("other:"):
            die("%s 类必须给受控 --wait-reason（%s 或 other:<说明>）"
                % (args.activity_class, "/".join(sorted(WAIT_REASONS))))
    elif args.wait_reason:
        die("--wait-reason 只用于 %s" % "/".join(sorted(WAIT_CLASSES)))

    if args.exec_cmd and args.exec_cmd[0] == "--":
        args.exec_cmd = args.exec_cmd[1:]
    exec_exit = None
    if args.exec_cmd:
        # 实测模式：wall clock 记起止（RFC3339 UTC），monotonic 测时长；调用者不可覆写
        if args.declared_start or args.declared_end:
            die("--exec 与 --declared-start/--declared-end 互斥")
        start_wall = time.time()
        t0 = time.monotonic_ns()
        proc = subprocess.run(args.exec_cmd)
        elapsed_ms = int((time.monotonic_ns() - t0) // 1_000_000)
        end_wall = time.time()
        started_at, ended_at = _utc_iso(start_wall), _utc_iso(end_wall)
        measured = True
        exec_exit = proc.returncode
        command = " ".join(args.exec_cmd)
    else:
        # 申报模式（真人 E2E 等外部活动）：强制 measured=false，report 单列曝光
        if not (args.declared_start and args.declared_end):
            die("须给 --exec -- <cmd> 或 --declared-start/--declared-end（RFC 3339 UTC）")
        s, e = parse_rfc3339(args.declared_start), parse_rfc3339(args.declared_end)
        if s is None or e is None:
            die("申报时间必须是 RFC 3339 UTC（例 2026-07-27T09:00:00Z）")
        if e < s:
            die("declared-end 早于 declared-start")
        started_at, ended_at = args.declared_start, args.declared_end
        elapsed_ms = int((e - s) * 1000)
        measured = False
        command = args.command or ""

    def mutate(ledger):
        for eid in args.evidence_ids or []:
            if eid not in {ev.get("evidence_id") for ev in ledger.get("evidence", [])}:
                die("evidence_id %s 不存在于账本" % eid)
        fixture = bool(ledger.get("fixture_only"))
        identity = {}
        if not fixture:
            identity["head"] = repo_head(ledger.get("repo_root") or os.getcwd())
        rec = {
            "timing_id": "t-%04d" % (len(ledger.get("timing") or []) + 1),
            "phase": args.phase,
            "slice": args.slice,
            "task": args.task,
            "tool": args.tool,
            "command": command,
            "activity_class": args.activity_class,
            "wait_reason": args.wait_reason,
            "started_at": started_at,
            "ended_at": ended_at,
            "elapsed_ms": elapsed_ms,
            "measured": measured,
            "retry": args.retry,
            "abort": bool(args.abort),
            "test_count": args.test_count,
            "runtime_identity": identity,
            "evidence_ids": args.evidence_ids or [],
            "exec_exit_code": exec_exit,
            "recorded_at": now_iso(),
        }
        ledger.setdefault("timing", []).append(
            {k: v for k, v in rec.items() if v is not None})

    _append(args.run_dir, mutate)
    print("TIMING RECORDED class=%s elapsed_ms=%d measured=%s"
          % (args.activity_class, elapsed_ms, str(measured).lower()))
    if exec_exit is not None and exec_exit != 0:
        sys.exit(exec_exit)  # 被包裹命令失败：如实透传 exit code


def cmd_checkpoint(args):
    def mutate(ledger):
        fixture = bool(ledger.get("fixture_only"))
        ev = {"type": "checkpoint", "slice": args.slice, "note": args.note,
              "at": _utc_iso(time.time())}
        if not fixture:
            repo = ledger.get("repo_root") or os.getcwd()
            ev["head"] = repo_head(repo)
            dirty, _err = repo_dirty_digest(repo, args.run_dir)
            ev["dirty_patch_sha256"] = dirty
        ledger.setdefault("events", []).append(ev)

    _append(args.run_dir, mutate)
    print("CHECKPOINT RECORDED slice=%s" % (args.slice or "-"))


def cmd_audit(args):
    for f in (args.input, args.output):
        if not os.path.exists(os.path.join(args.run_dir, f)):
            die("auditor 文件不存在（须已写入 run-dir）: %s" % f)

    def mutate(ledger):
        ledger["auditor"] = {
            "verdict": args.verdict,
            "engine": args.engine,
            "input_path": args.input,
            "input_sha256": sha256_file(os.path.join(args.run_dir, args.input)),
            "output_path": args.output,
            "output_sha256": sha256_file(os.path.join(args.run_dir, args.output)),
            "audited_at": now_iso(),
        }
        ledger["auditor"]["facts_digest"] = auditor_facts_digest(ledger)

    _append(args.run_dir, mutate)
    print("AUDIT RECORDED verdict=%s（facts 已冻结，此后任何 fact 变化审计即 stale）" % args.verdict)


def cmd_finalize(args):
    ledger = load_ledger(args.run_dir)
    fixture = bool(ledger.get("fixture_only"))
    mode = "check-only" if args.check_only else "full"
    diags, computed = validate(args.run_dir, ledger, mode=mode, fixture=fixture)
    if args.check_only:
        ok = not blocking(diags)
        emit(diags, computed,
             ["CHECK-ONLY RESULT: %s" % ("READY_FOR_AUDIT" if ok else "NOT_READY")])
        sys.exit(0 if ok else 1)
    if blocking(diags):
        emit(diags, computed, ["FINALIZE: FAIL（不生成 receipt）"])
        sys.exit(1)
    if computed["state"] != "SHIPPABLE":
        emit(diags, computed, ["FINALIZE: FAIL state=%s（须 SHIPPABLE）" % computed["state"]])
        sys.exit(1)
    receipt = build_receipt(args.run_dir, ledger, computed)
    existing = load_receipt(args.run_dir)
    if existing and existing.get("content_digest") == receipt["content_digest"]:
        receipt["finalized_at"] = existing.get("finalized_at")  # 幂等：复用首次时间
    else:
        receipt["finalized_at"] = now_iso()
    if fixture:
        receipt["fixture_only"] = True
    atomic_write_json(os.path.join(args.run_dir, RECEIPT_NAME), receipt)
    emit(diags, computed, ["FINALIZE: PASS",
                           "GATE RECEIPT: %s" % receipt["content_digest"],
                           "RECEIPT FILE: %s" % os.path.join(args.run_dir, RECEIPT_NAME)])
    sys.exit(0)


def cmd_render(args):
    ledger = load_ledger(args.run_dir)
    fixture = bool(ledger.get("fixture_only"))
    diags, computed = validate(args.run_dir, ledger, mode="render", fixture=fixture)
    receipt = load_receipt(args.run_dir)
    stale = False
    if receipt is None:
        diags.append(Diag("RECEIPT_STALE", "无 gate-receipt.json——先 finalize"))
    else:
        if receipt.get("invalidated"):
            stale = True
            diags.append(Diag("RECEIPT_STALE", "receipt 已被 invalidate: %s"
                              % receipt.get("invalidated_reason")))
        elif receipt_is_stale(args.run_dir, ledger, computed, receipt):
            stale = True
            diags.append(Diag("RECEIPT_STALE", "receipt digest 与当前输入不符——输入已变化"))
    shippable = (not blocking(diags)) and computed["state"] == "SHIPPABLE" and receipt and not stale
    lines = ["# plan-test gate report", "",
             "RUN: %s" % ledger.get("run_id"),
             "STATE: %s" % ("SHIPPABLE" if shippable else "BLOCKED"),
             "TESTED HEAD: %s" % ((ledger.get("runtime_attestation") or {}).get("head")
                                  or (ledger.get("baseline") or {}).get("head")),
             "GATE RECEIPT: %s" % (receipt.get("content_digest") if (receipt and shippable) else "无（不得宣布 SHIP）"),
             ""]
    lines.append("## 场景状态（由 validator 重算）")
    for s in ledger.get("scenarios") or []:
        sid = s["scenario_id"]
        lines.append("- %s [%s]%s: %s" % (
            sid, "required" if s.get("required") else "optional",
            " (ui)" if s.get("ui") else "", computed["scenario_statuses"].get(sid)))
    timing = ledger.get("timing") or []
    if timing:
        lines.append("")
        lines.append("## 耗时分解（measured=CLI 单调时钟实测；declared=申报值，低信任）")
        agg = {}
        for t in timing:
            ac = t.get("activity_class", "unknown")
            row = agg.setdefault(ac, {"measured_ms": 0, "declared_ms": 0,
                                      "retry": 0, "abort": 0, "test_count": 0})
            key = "measured_ms" if t.get("measured") else "declared_ms"
            row[key] += int(t.get("elapsed_ms") or 0)
            row["retry"] += int(t.get("retry") or 0)
            row["abort"] += 1 if t.get("abort") else 0
            row["test_count"] += int(t.get("test_count") or 0)
        for ac in sorted(agg):
            r = agg[ac]
            lines.append("- %s: measured %.1f min / declared %.1f min / retry %d / abort %d / tests %d"
                         % (ac, r["measured_ms"] / 60000.0, r["declared_ms"] / 60000.0,
                            r["retry"], r["abort"], r["test_count"]))
        checkpoints = [e for e in (ledger.get("events") or []) if e.get("type") == "checkpoint"]
        lines.append("- checkpoints: %d" % len(checkpoints))
    if diags:
        lines.append("")
        lines.append("## 未闭环诊断")
        for d in diags:
            tag = "" if d.severity == "error" else "（advisory，不拦截）"
            lines.append("- %s%s: %s" % (d.code, tag, d.detail))
    if fixture:
        lines.append("")
        lines.append("> FIXTURE-ONLY run：本报告不可作为真实交付证据。")
    with open(os.path.join(args.run_dir, REPORT_NAME), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    emit(diags, computed, ["RENDER: %s -> %s" % ("SHIPPABLE" if shippable else "BLOCKED",
                                                 os.path.join(args.run_dir, REPORT_NAME))])
    sys.exit(0 if shippable else 1)


def cmd_invalidate(args):
    receipt = load_receipt(args.run_dir)
    if receipt is None:
        die("无 receipt 可 invalidate")
    receipt["invalidated"] = True
    receipt["invalidated_reason"] = args.reason
    receipt["invalidated_at"] = now_iso()
    atomic_write_json(os.path.join(args.run_dir, RECEIPT_NAME), receipt)

    def mutate(ledger):
        ledger.setdefault("events", []).append(
            {"type": "receipt_invalidated", "reason": args.reason, "at": now_iso()})

    _append(args.run_dir, mutate)
    print("RECEIPT INVALIDATED: %s" % args.reason)


# ---------------------------------------------------------------- main

def main(argv=None):
    ap = argparse.ArgumentParser(prog="plan_test_gate.py")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("init")
    p.add_argument("--run-dir", required=True)
    p.add_argument("--manifest", required=True)
    p.add_argument("--force", action="store_true")
    p.set_defaults(fn=cmd_init)

    p = sub.add_parser("record-run")
    p.add_argument("--run-dir", required=True)
    p.add_argument("--scenario", required=True)
    p.add_argument("--kind", required=True, choices=sorted(KIND_VALUES))
    p.add_argument("--result", required=True, choices=sorted(RESULT_VALUES))
    p.add_argument("--lane", default="fresh")
    p.add_argument("--driver", default="ai", choices=["ai", "human"])
    p.add_argument("--command")
    p.add_argument("--engine-terminal")
    p.add_argument("--business-terminal")
    p.add_argument("--session-id")
    p.add_argument("--run-id-under-test")
    p.set_defaults(fn=cmd_record_run)

    p = sub.add_parser("attach-evidence")
    p.add_argument("--run-dir", required=True)
    p.add_argument("--path", required=True, help="相对 run-dir 的证据路径")
    p.add_argument("--kind", required=True, choices=["primary", "derived"])
    p.add_argument("--scenario")
    p.add_argument("--id")
    p.add_argument("--ui-action", action="store_true")
    p.add_argument("--negative-assertion", action="store_true")
    p.add_argument("--depends-on", nargs="*")
    p.set_defaults(fn=cmd_attach_evidence)

    p = sub.add_parser("declare-status")
    p.add_argument("--run-dir", required=True)
    p.add_argument("--source", required=True)
    p.add_argument("--scenario", required=True)
    p.add_argument("--status", required=True)
    p.set_defaults(fn=cmd_declare_status)

    p = sub.add_parser("set-delivery")
    p.add_argument("--run-dir", required=True)
    p.add_argument("--verdict", required=True)
    p.set_defaults(fn=cmd_set_delivery)

    p = sub.add_parser("record-timing")
    p.add_argument("--run-dir", required=True)
    p.add_argument("--phase", required=True)
    p.add_argument("--slice")
    p.add_argument("--task")
    p.add_argument("--tool")
    p.add_argument("--activity-class", required=True)
    p.add_argument("--wait-reason")
    p.add_argument("--retry", type=int, default=0)
    p.add_argument("--abort", action="store_true")
    p.add_argument("--test-count", type=int, default=0)
    p.add_argument("--evidence-ids", nargs="*")
    p.add_argument("--command", help="申报模式下的活动描述")
    p.add_argument("--declared-start", help="RFC 3339 UTC；申报模式（真人 E2E 等）")
    p.add_argument("--declared-end", help="RFC 3339 UTC")
    # --exec -- <cmd...> 在 main() 里预切分（argparse REMAINDER 对 -- 的处理不可靠）
    p.set_defaults(fn=cmd_record_timing, exec_cmd=None)

    p = sub.add_parser("checkpoint")
    p.add_argument("--run-dir", required=True)
    p.add_argument("--slice")
    p.add_argument("--note")
    p.set_defaults(fn=cmd_checkpoint)

    p = sub.add_parser("audit")
    p.add_argument("--run-dir", required=True)
    p.add_argument("--verdict", required=True, choices=["PASS", "FAIL"])
    p.add_argument("--engine", default="unknown")
    p.add_argument("--input", required=True, help="auditor-input.json（相对 run-dir）")
    p.add_argument("--output", required=True, help="auditor-output.json（相对 run-dir）")
    p.set_defaults(fn=cmd_audit)

    p = sub.add_parser("finalize")
    p.add_argument("--run-dir", required=True)
    p.add_argument("--check-only", action="store_true")
    p.set_defaults(fn=cmd_finalize)

    p = sub.add_parser("render")
    p.add_argument("--run-dir", required=True)
    p.set_defaults(fn=cmd_render)

    p = sub.add_parser("invalidate")
    p.add_argument("--run-dir", required=True)
    p.add_argument("--reason", required=True)
    p.set_defaults(fn=cmd_invalidate)

    argv = list(sys.argv[1:] if argv is None else argv)
    exec_cmd = None
    if argv and argv[0] == "record-timing" and "--exec" in argv:
        i = argv.index("--exec")
        exec_cmd = argv[i + 1:]
        argv = argv[:i]
    args = ap.parse_args(argv)
    if exec_cmd is not None:
        args.exec_cmd = exec_cmd
    args.fn(args)


if __name__ == "__main__":
    main()
