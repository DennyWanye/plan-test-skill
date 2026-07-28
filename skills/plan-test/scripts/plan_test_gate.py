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

exit code：0 = 真实交付通过；1 = 门禁 FAIL（stdout 有 DIAG 行）；2 = 用法/IO 错误；
3 = fixture-only run 通过（合成数据，**不可作为交付证据**）。
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

SCHEMA_VERSION = "1.2.0"
VALIDATOR_VERSION = "1.2.0"
FIXTURE_EXIT = 3  # fixture-only run 通过：与真实交付的 exit 0 分开，堵"设个字段就绿"
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
CONTENT_DIGEST_FILE_LIMIT = 20000  # 超过此文件数退回 HEAD+dirty 口径并显式标注

# 适用性判定（applicability）：哪几道条件门适用于本次交付，必须显式入账。
# 病根：config.md 的"输入语义敏感 / LLM 载荷驱动 / 依赖异步初始化"此前由代理口头自决且不留痕，
# 判一句"不适用"就能让场景矩阵/正向价值门/随机采样/冷启动四道门合法消失，validator 无从知道。
# 现在：判定本身是 fact，进账本、进 receipt digest、进 report；判"适用"则矩阵必须真的兑现。
APPLICABILITY_DIMENSIONS = {
    # 维度 -> (说明, 声明 true 时必须兑现的场景矩阵条件)
    "input_sensitive": "输出质量随输入语义变化（LLM 对话/生成、搜索、调研、推荐、分类）",
    "llm_payload_driven": "LLM 输出的结构化载荷直接驱动端侧状态机/卡片/流程推进",
    "stateful_init": "行为依赖异步注册的服务/远程配置/登录态（存在冷启动路径）",
}
APPLICABILITY_DECIDERS = {"agent", "user"}
MIN_RATIONALE_CHARS = 10
DEFAULT_MIN_DISTINCT_INPUT_CLASSES = 3  # 对齐 config.md 的 MANUAL_MIN_DISTINCT_CLASSES

# canonical 诊断排序（plan §3 唯一权威序；同类内按 hint/detail 字典序）
CANONICAL_ORDER = [
    "SCHEMA_INVALID", "LEDGER_TAMPERED", "REQUIRED_SCENARIO_NOT_RUN", "STATUS_CONFLICT",
    "DELIVERY_VERDICT_CONTRADICTS_LEDGER", "UI_EVIDENCE_MISSING",
    "RUN_CREATION_UNVERIFIED", "EVIDENCE_MISSING", "EVIDENCE_HASH_MISMATCH",
    "EVIDENCE_DEPENDENCY_CYCLE", "DERIVED_EVIDENCE_ONLY", "FROZEN_ORACLE_CHANGED",
    "BEHAVIOR_APPROVAL_REQUIRED", "APPLICABILITY_UNDECLARED",
    "APPLICABILITY_GATE_UNSATISFIED", "RISK_CLOSURE_MISSING",
    "STABILITY_SAMPLES_INSUFFICIENT", "RELEASE_UNIT_TOO_LARGE",
    "TESTED_RUNTIME_MISMATCH", "RETEST_REQUIRED_AFTER_CHANGE",
    "AUDITOR_MISSING", "AUDITOR_VERDICT_MISMATCH",
    "AUDITOR_INPUT_STALE", "RECEIPT_STALE",
    "AUDITOR_INDEPENDENCE_UNVERIFIED", "TIMING_GAP",
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


def normalize_run_relative_path(path):
    """把 run-dir 内路径规范化为相对 POSIX 形式，并拒绝绝对路径/目录逃逸。"""
    if not isinstance(path, str) or not path:
        raise ValueError("路径不能为空")
    portable = path.replace("\\", "/")
    if (portable.startswith("/") or re.match(r"^[A-Za-z]:", portable)
            or portable.startswith("//")):
        raise ValueError("路径须相对 run-dir，不能是绝对路径: %s" % path)
    normalized = os.path.normpath(portable).replace("\\", "/")
    if normalized in ("", ".", "..") or normalized.startswith("../"):
        raise ValueError("路径不能逃逸 run-dir: %s" % path)
    return normalized


def run_relative_abspath(run_dir, path):
    normalized = normalize_run_relative_path(path)
    return os.path.join(run_dir, *normalized.split("/"))


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
            rel_exclude = os.path.relpath(os.path.realpath(exclude_run_dir),
                                          os.path.realpath(repo))
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


def _rel_exclude(repo, exclude_run_dir):
    """run-dir 相对 repo 的路径。两侧都走 realpath——macOS 的 /var → /private/var 软链
    会让 abspath 两侧不一致，排除规则静默失效，run-dir 自身被当成"内容变化"。"""
    if not exclude_run_dir:
        return None
    try:
        rel = os.path.relpath(os.path.realpath(exclude_run_dir), os.path.realpath(repo))
    except ValueError:
        return None
    return None if rel.startswith("..") else rel.replace(os.sep, "/")


def declared_exclusion_scope(ledger_or_manifest, repo, run_dir):
    """排除范围 = **init 时冻结的显式清单**：当前 run-dir + manifest 声明的 related_run_dirs。

    为什么不再在校验时现算（三轮独立审计接连打穿了三个现算版本）：
      - 按"目录里有 plan-test-run.json"判定 → 在 src/ 塞一个假账本即可藏掉整个目录；
      - 按路径形态 `.../verification/<x>/` 判定 → 项目里真有这样的业务目录就整体消失；
      - 按"文件名恰为记账物"+"含真实账本的 artifacts/" 判定 → 把业务文件命名成 manifest.json，
        或事后 `mkdir -p src/verification/z/artifacts` 再塞一个空账本，照样藏掉后门，
        且 receipt 逐字不变。

    共同根因：**判定输入是被测者可写的工作树**。现在改为冻结声明——排除哪些路径在 init 时
    定死、进账本、进 receipt digest、在报告里逐条显形；事后往仓库里塞任何文件都不改变排除范围。
    """
    scope = []
    cur = _rel_exclude(repo, run_dir)
    if cur:
        scope.append(cur)
    for rel in (ledger_or_manifest.get("related_run_dirs") or []):
        rel = str(rel).replace(os.sep, "/").rstrip("/")
        if rel and rel not in scope:
            scope.append(rel)
    return sorted(scope)


def validate_related_run_dirs(repo, related):
    """related_run_dirs 只能是 gate run 目录形态，且必须真实存在 —— 防止声明成 `src` 把代码排掉。"""
    bad = []
    for rel in related or []:
        rel = str(rel).replace(os.sep, "/").rstrip("/")
        parts = rel.split("/")
        shaped = len(parts) >= 2 and parts[-2] == "verification"
        exists = os.path.isdir(os.path.join(repo, rel))
        if not (shaped and exists):
            bad.append(rel)
    return bad


def _excluded_reason(rel_path, scope):
    """只有落在冻结声明范围内的路径才被排除。返回原因或 None。"""
    for s in scope:
        if rel_path == s or rel_path.startswith(s + "/"):
            return "declared-scope:%s" % s
    return None


def repo_content_digest(repo, scope):
    """**被测内容**指纹：工作树里全部 tracked + 未忽略 untracked 文件的逐文件内容 hash。

    为什么不是 HEAD + dirty patch（原设计）：那两者描述的是**提交身份**，不是内容。
    `git add`/`git commit` 不改一个字节却会让 HEAD 与 diff 同时变化，于是「测完 → 提交 →
    finalize」必然 TESTED_RUNTIME_MISMATCH，而不提交又过不了提交态门——这正是独立审计
    实测出来的死结（AC-6）。改按内容取指纹后：

      - 文档/代码改一个字   → 内容变 → 必须重测（**这是要保留的严格性**）
      - 只是 git add/commit → 内容不变 → 门依然绿（死结解开）
      - 提交 run-dir 自身   → 被排除 → 内容不变（receipt 不会自己打脸自己）

    代价：要逐文件 hash 一遍工作树。小仓可忽略；超大仓可用 CONTENT_DIGEST_FILE_LIMIT 兜底，
    超限时退回 HEAD+dirty 口径并在报告里标注（宁可显式降级，不要静默）。
    """
    listing, err = git(["ls-files", "-c", "-o", "--exclude-standard"], repo)
    if listing is None:
        return None, None, err
    files, excluded = [], []
    for rel in listing.splitlines():
        rel = rel.strip()
        if not rel:
            continue
        why = _excluded_reason(rel, scope)
        if why:
            excluded.append([rel, why])
            continue
        files.append(rel)
    files = sorted(set(files))
    if len(files) > CONTENT_DIGEST_FILE_LIMIT:
        return None, None, "FILE_LIMIT_EXCEEDED:%d" % len(files)
    entries = []
    for rel in files:
        p = os.path.join(repo, rel)
        if os.path.islink(p):
            entries.append([rel, "symlink:" + sha256_text(os.readlink(p))])
        elif os.path.isfile(p):
            entries.append([rel, file_content_token(p)])
        else:
            entries.append([rel, "absent"])  # tracked 但已删除：删除本身也是内容变化
    # 指纹只取文件条目，不含排除范围本身（否则新开一个 slice 会把别的 slice 判红）。
    # 排除范围不是派生的，是 init 时冻结的显式声明（见 declared_exclusion_scope）。
    # **剩余面（如实说明）**：事前造出 `.../verification/<单层>` 形态的目录再声明它，
    # 可以合法地把该目录排除在指纹之外。形态校验挡得住直接声明 `src`，挡不住"先造目录再声明"。
    # 缓解只有可见性：范围进账本、进 receipt digest、在 report.md 逐条列出——但范围内**事后新增**
    # 的文件不会出现在报告里。这是当前设计已知的、未消除的剩余风险。
    # 排除命中清单进账本与报告（此前既不进指纹也不进账本，无人能看见排除了什么）
    globals()["_LAST_EXCLUSIONS"] = sorted(excluded)
    return canonical_digest({"files": entries}), entries, None


def classify_changed_paths(paths, globs=None):
    """把变更文件分成 doc-only 与 behavioral 两类——**机器判定，不接受自报**。

    doc-only 的判据只有一条：全部变更路径都命中文档白名单。只要有一个不是，
    就是 behavioral，必须重测。这样"我这次只改了文档"不再是一句可以随口说的话。
    """
    non_doc = [p for p in paths if not DOC_ONLY_PATTERNS_MATCH(p, globs)]
    return ("doc-only" if not non_doc else "behavioral"), non_doc


# doc-only 默认白名单：**只认叙述性文档**，不认任何可能改变行为的文本。
# 独立审计实测过两个反例：`requirements.txt`（改依赖版本）与 `prompts/system.md`
# （把系统提示改成"忽略所有规则"）在旧规则下都被判 doc-only 免重测。
# 对本仓尤其致命——plan-test 的交付物本身就是 skills/**/*.md。
DOC_ONLY_DEFAULT_GLOBS = ["README*", "CHANGELOG*", "CONTRIBUTING*", "LICENSE*",
                          "docs/**", "doc/**", "ARCHITECTURE.md", "*.rst"]
# 无论后缀如何，命中这些前缀一律视为行为文本（提示词、skill、配置、依赖清单）
BEHAVIORAL_TEXT_PREFIXES = ("prompts/", "skills/", "config/", ".claude/", "hooks/")
BEHAVIORAL_TEXT_NAMES = ("requirements.txt", "constraints.txt", "pyproject.toml",
                         "package.json", "dockerfile", "makefile")


def _match_globs(low, base, globs):
    import fnmatch
    for g in globs:
        gl = g.lower()
        if fnmatch.fnmatch(low, gl) or fnmatch.fnmatch(base, gl):
            return True
        if gl.endswith("/**") and low.startswith(gl[:-2]):
            return True
    return False


def DOC_ONLY_PATTERNS_MATCH(path, globs=None):
    """是否是叙述性文档。

    **项目自定义的 `doc_only_globs` 只能收窄、不能放宽**：最终判定是「默认白名单 ∩ 自定义」。
    独立审计实测过放宽的后果——manifest 里写一个全匹配 glob，往 src/app.py 追加后门也会被
    报成「仅文档变更（路径规则判定）」，重测门完全不触发。manifest 是被测者自己写的，
    任何"自报即生效"的开关都等于把门交回给被测者。
    """
    p = path.replace(os.sep, "/")
    low = p.lower()
    base = low.rsplit("/", 1)[-1]
    if low.startswith(BEHAVIORAL_TEXT_PREFIXES) or base in BEHAVIORAL_TEXT_NAMES:
        return False        # 行为文本永远不算 doc-only，哪怕是 .md
    if not _match_globs(low, base, DOC_ONLY_DEFAULT_GLOBS):
        return False        # 不在默认白名单里 → 自定义 glob 救不了它
    if globs is not None and not _match_globs(low, base, globs):
        return False        # 自定义只用于进一步收窄
    return True


def changed_paths_since(repo, scope, previous_entries):
    """列出与上次 attestation 相比内容变了的文件（逐文件 hash 对比）。"""
    listing, err = git(["ls-files", "-c", "-o", "--exclude-standard"], repo)
    if listing is None:
        return None, err
    prev = dict(previous_entries or [])
    current = {}
    for rel in sorted(set(x.strip() for x in listing.splitlines() if x.strip())):
        if _excluded_reason(rel, scope):
            continue
        p = os.path.join(repo, rel)
        if os.path.islink(p):
            current[rel] = "symlink:" + sha256_text(os.readlink(p))
        elif os.path.isfile(p):
            current[rel] = file_content_token(p)
        else:
            current[rel] = "absent"
    changed = sorted(set(
        [k for k, v in current.items() if prev.get(k) != v] +
        [k for k in prev if k not in current]))
    return changed, None


def file_content_token(path):
    """内容 token = 内容 hash + 可执行位（模式变化也是交付差异，独立审计点名的缺口）。"""
    mode = "x" if os.access(path, os.X_OK) else "-"
    return "%s:%s" % (mode, sha256_file(path))


def attest_runtime(repo, scope):
    """采集一次运行时身份：内容指纹（阻塞判据）+ HEAD/dirty（只作展示与溯源）。"""
    content, entries, cerr = repo_content_digest(repo, scope)
    exclusions = list(globals().get("_LAST_EXCLUSIONS") or [])
    dirty, _derr = repo_dirty_digest(repo, scope[0] if scope else None)
    att = {
        "head": repo_head(repo),
        "dirty_patch_sha256": dirty,
        "content_digest": content,
        "content_entries": entries,
        "content_digest_error": cerr,
        "exclusions": exclusions,
        "exclusion_count": len(exclusions),
        "exclusion_scope": list(scope),
        "recorded_at": now_iso(),
    }
    return {k: v for k, v in att.items() if v is not None}


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
        t = s.replace("Z", "+00:00")
        # now_iso() 产出的是 %z 形式（+0800，无冒号），Python 3.9 的 fromisoformat 不认；
        # 账本自己写的时间戳必须能被自己解析，否则依赖时序的门会静默失效。
        m = re.search(r"([+-])(\d{2})(\d{2})$", t)
        if m:
            t = t[:m.start()] + "%s%s:%s" % (m.group(1), m.group(2), m.group(3))
        dt = datetime.datetime.fromisoformat(t)
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
        path = _req(e, "path", str, "evidence[%d]" % i, errors)
        if path is not None:
            try:
                normalized = normalize_run_relative_path(path)
                if path != normalized:
                    errors.append("SCHEMA_INVALID: evidence[%d].path 须为规范化 POSIX 相对路径（应为 %s）"
                                  % (i, normalized))
            except ValueError as exc:
                errors.append("SCHEMA_INVALID: evidence[%d].path 非法（%s）" % (i, exc))
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
             if k not in ("auditor", "revision", "events", "integrity")}
    return canonical_digest(facts)


# ------------------------------------------------- 账本完整性链（tamper-evident）

def integrity_facts_digest(ledger):
    """当前 fact 快照指纹（不含链本身与 revision）。"""
    facts = {k: v for k, v in ledger.items() if k not in ("revision", "integrity")}
    return canonical_digest(facts)


def integrity_append(ledger, op):
    """每次写入追加一条链条目：chain_n = sha256(chain_{n-1} + op + facts_digest_n)。

    作用不是防有决心的伪造（代理能重算整条链），而是让"悄悄手改一条 run 记录"
    从 1 步变成"必须显式重写整条链"——把无意/顺手的篡改变成有意为之。
    """
    integ = ledger.setdefault("integrity", {"chain": "", "log": []})
    if op == "init":
        integ["genesis"] = integrity_genesis(ledger)
    fd = integrity_facts_digest(ledger)
    prev = integ.get("chain") or ""
    entry = {"seq": len(integ.get("log") or []) + 1, "op": op,
             "facts_digest": fd, "at": now_iso()}
    entry["chain"] = sha256_text(prev + op + fd)
    integ.setdefault("log", []).append(entry)
    integ["chain"] = entry["chain"]


def integrity_genesis(ledger):
    """开账锚：init 时刻的不可变身份。链被删掉重建时，重建者必须连它一起伪造。"""
    return canonical_digest({
        "run_id": ledger.get("run_id"),
        "created_at": ledger.get("created_at"),
        "repo_root": ledger.get("repo_root"),
        "source_request": ledger.get("source_request"),
        "acceptance": ledger.get("acceptance"),
    })


def integrity_check(ledger):
    """重算链并核对末条 facts_digest == 当前 fact 快照。返回 detail 或 None。

    结构不变量与链值同等重要（否则"删掉 integrity 键再写一条命令"就能重建一条自洽的新链）：
    链必须非空、首条 op 必须是 init、genesis 锚必须与开账身份一致。
    """
    integ = ledger.get("integrity")
    if not integ:
        return "账本缺少 integrity 链——账本无效（删掉链不是绕过，是把账本作废）"
    log = integ.get("log") or []
    if not log:
        return "integrity.log 为空"
    if log[0].get("op") != "init":
        return "integrity 链首条不是 init（op=%s）——链被删除后重建过" % log[0].get("op")
    if integ.get("genesis") and integ["genesis"] != integrity_genesis(ledger):
        return "integrity genesis 与开账身份不符——账本被替换或链被重建"
    # 缺 genesis 不单独判死：真正的不变量是"链首必须是 init"（上面已查）。
    # 把"缺 genesis"也当篡改，会让上一版 validator 建的账本集体作废——严格性不能靠制造
    # 迁移断裂来实现，那只会逼人 `init --force` 重来，反而丢掉真实的测试事实。
    chain = ""
    for i, e in enumerate(log):
        expect = sha256_text(chain + str(e.get("op")) + str(e.get("facts_digest")))
        if e.get("chain") != expect:
            return "integrity 链在第 %d 条（op=%s）断裂——账本被绕过 CLI 手工改动" % (
                i + 1, e.get("op"))
        chain = e["chain"]
    if integ.get("chain") != chain:
        return "integrity.chain 与重算结果不符"
    if log[-1].get("facts_digest") != integrity_facts_digest(ledger):
        return "当前 fact 与最后一条链条目不符——账本在 CLI 之外被改动过"
    return None


# ------------------------------------------------- 适用性判定（applicability）

def validate_applicability(ledger, scenarios, thresholds):
    """适用性判定必须显式入账；判"适用"则场景矩阵必须真的兑现对应条件。"""
    diags = []
    app = ledger.get("applicability") or {}
    required_sc = [s for s in scenarios if s.get("required")]
    for dim, desc in sorted(APPLICABILITY_DIMENSIONS.items()):
        d = app.get(dim)
        if not isinstance(d, dict) or "value" not in d:
            diags.append(Diag("APPLICABILITY_UNDECLARED",
                              "适用性维度 %s 未声明（%s）——不许靠口头自决让条件门消失" % (dim, desc),
                              hint=dim))
            continue
        if not isinstance(d.get("value"), bool):
            diags.append(Diag("APPLICABILITY_UNDECLARED",
                              "%s.value 须为 bool" % dim, hint=dim))
            continue
        rationale = str(d.get("rationale") or "")
        if len(rationale.strip()) < MIN_RATIONALE_CHARS:
            diags.append(Diag("APPLICABILITY_UNDECLARED",
                              "%s 缺少判定理由（rationale ≥%d 字）——判「不适用」尤其要写清依据"
                              % (dim, MIN_RATIONALE_CHARS), hint=dim))
        if d.get("decided_by") not in APPLICABILITY_DECIDERS:
            diags.append(Diag("APPLICABILITY_UNDECLARED",
                              "%s.decided_by 须为 agent 或 user" % dim, hint=dim))
        if not d.get("value"):
            continue  # 判"不适用"：理由已入账并进 receipt digest，供审计与事后追责
        # 判"适用" → 场景矩阵必须兑现
        if dim == "input_sensitive":
            need = int(thresholds.get("min_distinct_input_classes")
                       or DEFAULT_MIN_DISTINCT_INPUT_CLASSES)
            classes = {s.get("input_class") for s in required_sc if s.get("input_class")}
            if len(classes) < need:
                diags.append(Diag("APPLICABILITY_GATE_UNSATISFIED",
                                  "input_sensitive=true 但 required 场景只有 %d 类语义不等价输入"
                                  "（需 ≥%d，见 config MANUAL_MIN_DISTINCT_CLASSES）"
                                  % (len(classes), need), hint=dim))
            if not any(s.get("gate_type") == "positive-value" for s in required_sc):
                diags.append(Diag("APPLICABILITY_GATE_UNSATISFIED",
                                  "input_sensitive=true 但无 required 的 positive-value 场景"
                                  "——「诚实降级成功」不等于产品质量 PASS", hint=dim))
        elif dim == "llm_payload_driven":
            if not any((s.get("min_root_runs") or 0) >= 2 for s in required_sc):
                diags.append(Diag("APPLICABILITY_GATE_UNSATISFIED",
                                  "llm_payload_driven=true 但无 min_root_runs≥2 的 required 场景"
                                  "（随机性单次跑过不算采样充分）", hint=dim))
        elif dim == "stateful_init":
            if not any(s.get("cold_start") for s in required_sc):
                diags.append(Diag("APPLICABILITY_GATE_UNSATISFIED",
                                  "stateful_init=true 但矩阵无 cold_start 场景"
                                  "（暖重启不算冷路径）", hint=dim))
    return diags


def read_output_verdict(run_dir, output_path):
    """从 auditor 原始产物里读 verdict（JSON 的 verdict 字段，或文末 VERDICT: X 行）。

    读不出来返回 None——不臆测，交给人看；读得出来就必须与入账值一致。
    """
    if not output_path:
        return None
    p = os.path.join(run_dir, output_path)
    if not os.path.exists(p):
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return None
    try:
        obj = json.loads(text)
        if isinstance(obj, dict) and obj.get("verdict"):
            return str(obj["verdict"]).strip().upper()
    except ValueError:
        pass
    m = re.findall(r"^VERDICT:\s*(PASS|FAIL)\s*$", text, re.MULTILINE)
    return m[-1].upper() if m else None


def validate(run_dir, ledger, mode="full", fixture=False):
    """核心 validator。mode: check-only | full | render。返回 (diags, computed)。"""
    diags = []
    for err in structural_check(ledger):
        diags.append(Diag("SCHEMA_INVALID", err))
    tamper = integrity_check(ledger)
    if tamper:
        diags.append(Diag("LEDGER_TAMPERED", tamper))
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
        try:
            p = run_relative_abspath(run_dir, e.get("path", ""))
        except ValueError:
            continue  # structural_check 已输出 SCHEMA_INVALID
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

    # 9a. behavioral re-attest 之后，required 场景必须重测（时间戳晚于该次 attestation）
    atts = [a for a in (ledger.get("attestations") or [])
            if a.get("change_kind") == "behavioral"]
    if atts:
        cutoff = max(int(a.get("runs_index") or 0) for a in atts)
        when = max(str(a.get("recorded_at") or "") for a in atts)
        for s in scenarios:
            if not s.get("required"):
                continue
            sid = s["scenario_id"]
            fresh = any(r.get("scenario_id") == sid and r.get("kind") == "root"
                        and r.get("result") == "pass"
                        for r in runs[cutoff:])
            if not fresh:
                diags.append(Diag("RETEST_REQUIRED_AFTER_CHANGE",
                                  "场景 %s 的通过记录早于最近一次 behavioral 变更（%s）——"
                                  "代码/配置改过就必须重跑，不能沿用旧结论" % (sid, when),
                                  hint=sid))

    # 9b. 适用性判定入账 + 判"适用"时矩阵必须兑现
    diags.extend(validate_applicability(ledger, scenarios,
                                        dict(ledger.get("thresholds") or {})))

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
            # 阻塞判据 = **被测内容**是否变了，不是提交身份变没变。
            # git add/commit 不改内容 → 门不该拦（否则「测完→提交→finalize」是死结）；
            # 改一个字节 → 必须拦。
            tested_content = att.get("content_digest") or baseline.get("content_digest")
            current, _entries, cerr = repo_content_digest(
                repo, declared_exclusion_scope(ledger, repo, run_dir))
            if tested_content and current is not None:
                if tested_content != current:
                    diags.append(Diag("TESTED_RUNTIME_MISMATCH",
                                      "被测内容指纹与测试时不一致——工作树文件在测试后被改动，须重测"))
            elif tested_content and current is None:
                diags.append(Diag("TESTED_RUNTIME_MISMATCH",
                                  "无法重算被测内容指纹（%s）——不得凭旧指纹放行" % cerr))
            else:
                # 旧账本（schema <1.2.0 或超大仓降级）：退回 HEAD + dirty 口径，并显式标注降级
                tested = att.get("head") or baseline.get("head")
                if tested and tested != head:
                    diags.append(Diag("TESTED_RUNTIME_MISMATCH",
                                      "tested HEAD=%s 当前 HEAD=%s（无内容指纹，退回提交身份口径）"
                                      % (tested, head)))
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
            # auditor 原始产物里的 verdict 必须与命令行申报一致：
            # 防"审计报告写着 FAIL、命令行敲个 PASS"这一步之遥的绕过
            file_verdict = read_output_verdict(run_dir, auditor.get("output_path"))
            if file_verdict is None:
                diags.append(Diag("AUDITOR_VERDICT_MISMATCH",
                                  "auditor-output（%s）里读不到 verdict——审计结论无产物支撑，"
                                  "不接受命令行代为申报" % auditor.get("output_path")))
            elif file_verdict != str(auditor.get("verdict", "")).upper():
                diags.append(Diag("AUDITOR_VERDICT_MISMATCH",
                                  "auditor-output 里 verdict=%s，但入账 verdict=%s"
                                  % (file_verdict, auditor.get("verdict"))))
            # 独立性无法被机器证明，只能曝光：同引擎/未标注引擎 → advisory，进 report 与 receipt
            engine = str(auditor.get("engine") or "").strip().lower()
            executor = str(ledger.get("executor_engine") or "").strip().lower()
            if not engine or engine in ("unknown", "self", "same"):
                diags.append(Diag("AUDITOR_INDEPENDENCE_UNVERIFIED",
                                  "auditor engine 未标注——无法说明审计者与实现者不是同一个",
                                  severity="advisory"))
            elif executor and engine == executor:
                diags.append(Diag("AUDITOR_INDEPENDENCE_UNVERIFIED",
                                  "auditor engine=%s 与 executor 相同——自审自判，结论仅供参考"
                                  % engine, severity="advisory"))
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
        "applicability": manifest.get("applicability") or {},
        "doc_only_globs": manifest.get("doc_only_globs"),
        "executor_engine": manifest.get("executor_engine"),
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
        bad = validate_related_run_dirs(repo, manifest.get("related_run_dirs"))
        if bad:
            die("related_run_dirs 只能是已存在的 `.../verification/<单层>` 目录，"
                "不许用它把代码排除掉；非法项：%s" % ", ".join(bad))
        ledger["related_run_dirs"] = manifest.get("related_run_dirs") or []
        scope = declared_exclusion_scope(ledger, repo, run_dir)
        ledger["exclusion_scope"] = scope
        ledger["baseline"] = attest_runtime(repo, scope)
        ledger["runtime_attestation"] = dict(ledger["baseline"])
        if ledger["baseline"].get("content_digest_error"):
            print("警告：内容指纹不可用（%s）——退回 HEAD+dirty 口径，提交会触发 "
                  "TESTED_RUNTIME_MISMATCH" % ledger["baseline"]["content_digest_error"])
    else:
        ledger["baseline"] = manifest.get("baseline") or {}
    integrity_append(ledger, "init")
    with LedgerLock(run_dir):
        save_ledger(run_dir, ledger)
    undeclared = [d for d in APPLICABILITY_DIMENSIONS
                  if not isinstance((ledger.get("applicability") or {}).get(d), dict)]
    print("INIT OK run_id=%s scenarios=%d (全部 NOT_RUN)" % (
        ledger["run_id"], len(ledger["scenarios"])))
    if undeclared:
        print("提醒：适用性维度未声明 %s——finalize 会以 APPLICABILITY_UNDECLARED 拦截"
              % "/".join(sorted(undeclared)))


def _append(run_dir, mutate, op="append"):
    with LedgerLock(run_dir):
        ledger = load_ledger(run_dir)
        # **写入前先验链**：否则篡改检测是一次性的——手改一行 result 之后随便敲一条无害命令
        # （checkpoint 都行），新条目会拿被篡改的 fact 快照重新盖章，`LEDGER_TAMPERED` 永久消失，
        # 随后照常拿到有效 receipt。独立审计实测过，成本只是"改一行 + 多敲一条命令"。
        # 现在：链一旦对不上，任何写入都被拒绝，篡改痕迹留在原地，只能显式修复或重开 run。
        broken = integrity_check(ledger)
        if broken:
            die("LEDGER_TAMPERED: %s\n"
                "账本已在 CLI 之外被改动，拒绝继续写入（不许用新记录把篡改盖过去）。\n"
                "处理方式：还原被改动的内容，或换一个 run-dir 重新 init 并如实说明。" % broken)
        rev = ledger.get("revision")
        mutate(ledger)
        # 任何 fact 变化都会使既有 receipt stale（finalize 会重算）；此处只记事实
        integrity_append(ledger, op)
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

    _append(args.run_dir, mutate, op="record-run")
    print("RECORDED run scenario=%s kind=%s result=%s" % (args.scenario, args.kind, args.result))


def cmd_attach_evidence(args):
    try:
        rel_path = normalize_run_relative_path(args.path)
    except ValueError as exc:
        die(str(exc))
    p = run_relative_abspath(args.run_dir, rel_path)
    if not os.path.exists(p):
        die("证据文件不存在: %s（路径须相对 run-dir）" % p)
    ev = {
        "evidence_id": args.id or ("ev-" + sha256_file(p)[:12]),
        "path": rel_path,
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
        if args.replace:
            # 重测后证据文件会更新，旧 hash 必然对不上。没有合法的更新路径时，
            # 唯一出路是整轮重来——这正是前几轮审计反复抓到的那类死结。
            # --replace 显式顶替同路径的旧条目；动作本身进 integrity 链，不是静默覆盖。
            kept = [e for e in ledger["evidence"] if e.get("path") != ev["path"]]
            ledger["superseded_evidence"] = (ledger.get("superseded_evidence") or []) + [
                {"path": e.get("path"), "sha256": e.get("sha256"),
                 "superseded_at": now_iso()}
                for e in ledger["evidence"] if e.get("path") == ev["path"]]
            ledger["evidence"] = kept
        ledger["evidence"].append(ev)

    _append(args.run_dir, mutate, op="attach-evidence")
    print("ATTACHED %s kind=%s sha256=%s" % (rel_path, args.kind, ev["sha256"][:12]))


def cmd_declare_status(args):
    def mutate(ledger):
        ledger.setdefault("declared_statuses", []).append(
            {"source": args.source, "scenario_id": args.scenario,
             "status": args.status, "recorded_at": now_iso()})

    _append(args.run_dir, mutate, op="declare-status")
    print("DECLARED %s: %s=%s（将与账本重算结果对账）" % (args.source, args.scenario, args.status))


def cmd_set_delivery(args):
    def mutate(ledger):
        ledger["delivery"] = {"verdict": args.verdict, "recorded_at": now_iso()}

    _append(args.run_dir, mutate, op="set-delivery")
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

    _append(args.run_dir, mutate, op="record-timing")
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

    _append(args.run_dir, mutate, op="checkpoint")
    print("CHECKPOINT RECORDED slice=%s" % (args.slice or "-"))


def cmd_re_attest(args):
    """收尾期合法改动后重新采集运行时身份。

    死结背景（第二轮独立审计实测）：attestation 原本只在 init 写一次，此后任何 run-dir 之外
    的改动都让整个 run 永久 `TESTED_RUNTIME_MISMATCH`，而收尾流程**强制要求**改（文档回写、
    状态同步）；唯一出路 `init --force` 会清空 runs/evidence/auditor，等于整轮重来。

    本命令不是"把红灯按绿"：
      - 变更集全部命中文档白名单 → 记 `doc-only`，既有测试结论继续有效；
      - 只要有一个非文档文件变了 → 记 `behavioral`，validator 要求**每条 required 场景
        都有一次晚于本次 attestation 的 root PASS**，否则 `RETEST_REQUIRED_AFTER_CHANGE`。
    doc-only 由路径规则机器判定，不接受调用者自报。
    """
    ledger = load_ledger(args.run_dir)
    if ledger.get("fixture_only"):
        die("fixture-only run 无 git 运行时身份，无需 re-attest")
    repo = ledger.get("repo_root") or os.getcwd()
    prev = (ledger.get("runtime_attestation") or ledger.get("baseline") or {})
    scope = declared_exclusion_scope(ledger, repo, args.run_dir)
    changed, err = changed_paths_since(repo, scope, prev.get("content_entries"))
    if changed is None:
        die("无法计算变更集：%s" % err)
    kind, non_doc = classify_changed_paths(changed, (ledger.get("doc_only_globs") or None))
    if not changed:
        print("NO CHANGE：内容与上次 attestation 一致，无需 re-attest")
        return
    att = attest_runtime(repo, scope)
    att["reason"] = args.reason
    att["change_kind"] = kind
    att["changed_paths"] = changed[:200]
    att["changed_count"] = len(changed)

    def mutate(led):
        # 用账本自身的追加序号锚定"这次 attestation 之后跑的 run"，不用时钟：
        # now_iso() 精度到秒，同秒内的重跑会被误判成"已重测"（自测实测过）。
        att["runs_index"] = len(led.get("runs") or [])
        led.setdefault("attestations", []).append(
            {k: v for k, v in att.items() if k != "content_entries"})
        led["runtime_attestation"] = att

    _append(args.run_dir, mutate, op="re-attest")
    print("RE-ATTEST OK kind=%s changed=%d" % (kind, len(changed)))
    if kind == "behavioral":
        print("非文档变更 %d 个（如 %s）——**每条 required 场景都必须重跑并 record-run**，"
              "否则 finalize 会以 RETEST_REQUIRED_AFTER_CHANGE 拦截。"
              % (len(non_doc), ", ".join(non_doc[:3])))
    else:
        print("仅文档变更（路径规则判定）——既有测试结论继续有效。")


def cmd_audit(args):
    for f in (args.input, args.output):
        if not os.path.exists(os.path.join(args.run_dir, f)):
            die("auditor 文件不存在（须已写入 run-dir）: %s" % f)
    file_verdict = read_output_verdict(args.run_dir, args.output)
    if file_verdict is None:
        # 读不出结论时**不能**静默采信命令行——那等于"审计产物随便写，verdict 我说了算"。
        # 与子代理契约一致：缺结论行按 FAIL 处理，这里直接拒绝入账。
        die("auditor-output（%s）里读不到 verdict：需要 JSON 的 \"verdict\" 字段，"
            "或文末独立一行 `VERDICT: PASS|FAIL`。缺结论行按 FAIL 处理，不接受命令行代为申报。"
            % args.output)
    if file_verdict != args.verdict.upper():
        die("auditor-output 里 verdict=%s，与 --verdict %s 不符——"
            "以审计产物为准，不许命令行改判" % (file_verdict, args.verdict))

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

    _append(args.run_dir, mutate, op="audit")
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
    emit(diags, computed, ["FINALIZE: PASS%s" % (" (FIXTURE-ONLY)" if fixture else ""),
                           "GATE RECEIPT: %s" % receipt["content_digest"],
                           "RECEIPT FILE: %s" % os.path.join(args.run_dir, RECEIPT_NAME)])
    if fixture:
        # exit 3 ≠ exit 0：合成 run 不许冒充交付通过（设一个 fixture_only 字段就跳过
        # git 校验并拿到 exit 0，此前是最省事的一条绕过路径）
        print("FIXTURE-ONLY：exit=%d，本 receipt 不可作为真实交付证据" % FIXTURE_EXIT)
        sys.exit(FIXTURE_EXIT)
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
    app = ledger.get("applicability") or {}
    if app:
        lines.append("## 适用性判定（判「不适用」等于放弃对应条件门，理由须可追责）")
        for dim in sorted(APPLICABILITY_DIMENSIONS):
            d = app.get(dim) or {}
            lines.append("- %s: %s（%s 判定）%s" % (
                dim, "适用" if d.get("value") else "不适用",
                d.get("decided_by") or "未标注", ("理由：" + str(d.get("rationale") or "缺")) ))
        lines.append("")
    att_now = ledger.get("runtime_attestation") or ledger.get("baseline") or {}
    if att_now.get("content_digest_error"):
        lines.append("> ⚠ 内容指纹不可用（%s）——已退回 HEAD+dirty 口径：此时"
                     "「测完→提交→finalize」会重新变成死结，须用 re-attest 或缩小仓库范围。"
                     % att_now["content_digest_error"])
        lines.append("")
    excl = (att_now.get("exclusions") or [])
    lines.append("## 指纹排除范围（init 时冻结的显式声明；事后往仓库塞文件不改变它）")
    for sc in (ledger.get("exclusion_scope") or att_now.get("exclusion_scope") or []):
        lines.append("- 声明范围：%s" % sc)
    lines.append("")
    lines.append("## 本次命中排除的文件")
    if excl:
        for rel, why in excl[:20]:
            lines.append("- %s（%s）" % (rel, why))
        if len(excl) > 20:
            lines.append("- …… 共 %d 项" % len(excl))
    else:
        lines.append("- 无")
    if ledger.get("doc_only_globs"):
        lines.append("- doc-only 自定义收窄：%s（只能收窄，不能放宽）"
                     % ", ".join(ledger["doc_only_globs"]))
    lines.append("")
    atts = [a for a in (ledger.get("attestations") or [])]
    if atts:
        lines.append("## 收尾期改动（re-attest 记录）")
        for a in atts:
            lines.append("- %s｜%s｜变更 %s 个文件｜理由：%s" % (
                a.get("recorded_at"), a.get("change_kind"), a.get("changed_count"),
                a.get("reason")))
        lines.append("")
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
    if ledger.get("retired"):
        lines.append("> ⚠ 本 run 已退役：%s；继任 run = %s。退役只影响 hook/CI 是否阻断，"
                     "不改变账本状态（下方场景状态仍是真实结论）。"
                     % (ledger.get("retired_reason"), ledger.get("superseded_by")))
        lines.append("")
    sup = ledger.get("superseded_evidence") or []
    if sup:
        lines.append("## 被顶替的证据（attach-evidence --replace 留痕）")
        for e in sup:
            lines.append("- %s（旧 sha256 %s…，%s）" % (e.get("path"),
                         str(e.get("sha256"))[:12], e.get("superseded_at")))
        lines.append("")
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
    if shippable and fixture:
        sys.exit(FIXTURE_EXIT)
    sys.exit(0 if shippable else 1)


def successor_receipt_status(run_dir, repo=None):
    """继任 run 的 receipt 是否有效。返回 (ok, detail)。

    继任者必须在**同一仓库内**：允许指向别处（甚至另一个仓库）等于允许"借"一张无关的 receipt
    来给本次失败背书。同理，fixture-only 的账本不能靠退役退出阻断。
    """
    if repo:
        try:
            rel = os.path.relpath(os.path.realpath(run_dir), os.path.realpath(repo))
        except ValueError:
            return False, "继任 run 不在本仓库内: %s" % run_dir
        if rel.startswith(".."):
            return False, "继任 run 不在本仓库内: %s" % run_dir
    if not os.path.isdir(run_dir):
        return False, "继任 run 目录不存在: %s" % run_dir
    try:
        ledger = load_ledger_quiet(run_dir)
    except Exception as e:
        return False, "继任 run 账本不可读: %s" % e
    if ledger is None:
        return False, "继任 run 没有账本"
    if ledger.get("fixture_only"):
        return False, "继任 run 是 fixture-only，不能作为交付级继任者"
    receipt = load_receipt(run_dir)
    if receipt is None:
        return False, "继任 run 没有 gate-receipt.json（它自己都还没通过）"
    if receipt.get("invalidated"):
        return False, "继任 run 的 receipt 已被 invalidate"
    diags, computed = validate(run_dir, ledger, mode="render",
                              fixture=bool(ledger.get("fixture_only")))
    if blocking(diags) or computed["state"] != "SHIPPABLE":
        return False, "继任 run 当前并非 SHIPPABLE（state=%s）" % computed["state"]
    if receipt_is_stale(run_dir, ledger, computed, receipt):
        return False, "继任 run 的 receipt 已 stale"
    return True, receipt.get("content_digest")


def load_ledger_quiet(run_dir):
    p = ledger_path(run_dir)
    if not os.path.exists(p):
        return None
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def cmd_retire(args):
    """把**已被取代**的历史 run 标记退役。

    背景：拆 slice 后早先的整体 run 仍留在仓库里、账本永远未闭环，Stop hook 被它永久阻断，
    而 `invalidate` 只作用于 receipt（这些 run 根本没有 receipt）——没有任何 CLI 出路。

    但退役本身必须有守卫，否则它就是下一个 `fixture_only`：给账本加个字段就让门消失。
    独立审计实测过无守卫版本——`retire --reason "这个先不做了"` 即可让一个 required 场景
    FAIL 的 run 从 hook 前消失。因此现在**强制要求指明继任者**，且继任者必须自己是
    SHIPPABLE + 有未失效 receipt 的真实（非 fixture）run。退役不是赦免，是转移举证责任。
    """
    ledger_self = load_ledger(args.run_dir)
    if ledger_self.get("fixture_only"):
        die("RETIRE 拒绝：fixture-only run 不得以退役方式退出阻断（合成数据本就不是交付证据）")
    repo_self = ledger_self.get("repo_root") or os.getcwd()
    ok, detail = successor_receipt_status(args.superseded_by, repo_self)
    if not ok:
        die("RETIRE 拒绝：%s。退役只允许在工作已被另一个**通过的** run 承接时使用；"
            "确实要放弃这次验证，请直接删除该 run 目录（删除会出现在 git diff 里，是可见动作）。"
            % detail)

    def mutate(ledger):
        ledger["retired"] = True
        ledger["retired_reason"] = args.reason
        ledger["superseded_by"] = args.superseded_by
        ledger["superseded_by_receipt"] = detail
        ledger["retired_at"] = now_iso()

    _append(args.run_dir, mutate, op="retire")
    print("RETIRED: %s\n  继任 run: %s（receipt %s）" % (args.reason, args.superseded_by,
                                                          str(detail)[:16]))


def cmd_retire_status(args):
    """退役是否成立——供 hook / CI 调用，避免它们各自解读账本字段。

    exit 0 = 退役成立且账本自洽；1 = 不成立（含未退役、链断裂、继任者无效、fixture 冒充）。
    """
    ledger = load_ledger(args.run_dir)
    if not ledger.get("retired"):
        print("NOT_RETIRED")
        sys.exit(1)
    if ledger.get("fixture_only"):
        print("INVALID: fixture-only run 不得以退役方式退出阻断")
        sys.exit(1)
    tamper = integrity_check(ledger)
    if tamper:
        print("INVALID: %s" % tamper)   # 手写 retired:true 不经 CLI → 链对不上
        sys.exit(1)
    if not any(e.get("op") == "retire" for e in (ledger.get("integrity", {}).get("log") or [])):
        print("INVALID: integrity 链里没有 retire 操作——retired 字段是手写的")
        sys.exit(1)
    ok, detail = successor_receipt_status(ledger.get("superseded_by") or "",
                                          ledger.get("repo_root") or os.getcwd())
    if not ok:
        print("INVALID: %s" % detail)
        sys.exit(1)
    print("VALID superseded_by=%s receipt=%s" % (ledger.get("superseded_by"), str(detail)[:16]))
    sys.exit(0)


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

    _append(args.run_dir, mutate, op="invalidate")
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
    p.add_argument("--replace", action="store_true",
                   help="顶替同路径的旧证据条目（重测后证据文件更新时用；旧条目转入 superseded_evidence）")
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

    p = sub.add_parser("re-attest")
    p.add_argument("--run-dir", required=True)
    p.add_argument("--reason", required=True,
                   help="为什么在测试之后还改了内容（文档回写/状态同步/修复……）")
    p.set_defaults(fn=cmd_re_attest)

    p = sub.add_parser("audit")
    p.add_argument("--run-dir", required=True)
    p.add_argument("--verdict", required=True, choices=["PASS", "FAIL"])
    p.add_argument("--engine", required=True,
                   help="执行审计的引擎/代理标识；与 executor 相同会被标 AUDITOR_INDEPENDENCE_UNVERIFIED")
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

    p = sub.add_parser("retire")
    p.add_argument("--run-dir", required=True)
    p.add_argument("--reason", required=True)
    p.add_argument("--superseded-by", required=True,
                   help="继任 run 的目录：必须是非 fixture、当前 SHIPPABLE 且 receipt 未失效的 run")
    p.set_defaults(fn=cmd_retire)

    p = sub.add_parser("retire-status")
    p.add_argument("--run-dir", required=True)
    p.set_defaults(fn=cmd_retire_status)

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
