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

# Windows 中文系统 console 默认 GBK，中文诊断输出会乱码（无害但难读）。guarded：
# reconfigure 是 3.7+ 的 TextIOWrapper 方法，stdout 被替换/捕获时可能没有——失败就算了，
# 门的判定从不依赖 console 编码。
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError, OSError):
        pass

SCHEMA_VERSION = "1.5.0"
VALIDATOR_VERSION = "1.5.0"
FIXTURE_EXIT = 3  # fixture-only run 通过：与真实交付的 exit 0 分开，堵"设个字段就绿"
LEDGER_NAME = "plan-test-run.json"
RECEIPT_NAME = "gate-receipt.json"
REPORT_NAME = "report.md"
LOCK_NAME = ".ledger.lock"

# 状态机（由 validator 计算，不可手写）
STATES = ["DRAFT", "ACCEPTED", "IMPLEMENTED", "TESTED", "VALIDATED", "SHIPPABLE"]

# 交付措辞里视为"宣布完成"的 verdict（与 ledger 冲突时触发硬门）
SHIP_VERDICTS = {"SHIP", "100% COMPLETE", "COMPLETE", "DONE", "SHIPPABLE"}

# release-unit 默认阈值（与 config.md RELEASE_UNIT_LIMITS 保持单一口径）
DEFAULT_THRESHOLDS = {
    "must_ac_count": 8,
    "task_count": 10,
    "plan_lines": 2000,
    "high_risk_subsystems": 3,
    "concurrent_layer_kinds": 3,
    "max_wip_lines": 5000,
    "max_wip_files": 20,
}

# 循环控制：plan challenge 使用独立的 soft/review/hard limit；15 只保留给其他循环。
PLAN_CHALLENGE_SOFT_LIMIT = 3
PLAN_CHALLENGE_USER_REVIEW_ROUND = 5
PLAN_CHALLENGE_HARD_LIMIT = 8
MAX_CHALLENGE_ROUNDS = 15
MAX_A2_EVENTS = 3                  # Phase 3 中 A2 plan defect 累计上限
MIN_PROGRESS_INTERVAL_MINUTES = 90 # Ledger 零增长警告阈值

ASSURANCE_PROFILES = {"standard", "hardened", "hostile-host"}
FINDING_SEVERITIES = {"P0", "P1", "P2"}
FINDING_SCOPE_RELATIONS = {"in-scope", "out-of-scope", "scope-change-proposal"}
FINDING_ORIGINS = {"pre-existing", "patch-induced", "new-external-fact"}
FINDING_STATUSES = {"open", "resolved", "advisory"}
CHALLENGE_REVIEW_MODES = {"breadth", "diff", "consolidated"}
CHALLENGE_SPECIALTIES = {
    "architecture", "data-state", "failure-recovery", "security-privacy",
    "testability-evidence", "release-rollback", "performance-third-party",
}
BREADTH_COVERAGE_KEYS = {
    "acceptance_coverage",
    "entry_and_trust_chain",
    "data_flow_and_persistence",
    "identity_permissions_concurrency_cleanup",
    "failure_and_recovery",
    "tests_and_evidence",
    "release_and_rollback",
    "trusted_boundary_stop",
}
CHALLENGE_CONTROL_ACTIONS = {
    "scope-audit", "architecture-reset", "user-review", "scope-change-approved"
}

# Plan 增长警告阈值
MAX_PLAN_GROWTH_RATIO = 1.5        # Plan 体量增长超过此比例时主动报告

RESULT_VALUES = {"pass", "fail", "partial", "blocked", "not_run"}
KIND_VALUES = {"root", "retry", "continuation", "replay"}

# timing contract（plan 2026-07-27-plan-test-gate-slice-1a §2）
ACTIVITY_CLASSES = {"implementation", "automated_test", "manual_e2e", "provider_wait",
                    "user_wait", "interruption_recovery", "rework"}
WAIT_CLASSES = {"provider_wait", "user_wait"}
WAIT_REASONS = {"provider_latency", "quota_limit", "user_review", "user_input",
                "environment_provision"}
TIMING_GAP_MINUTES = 120  # 相邻记账锚点最大间隔（schema 1.3.0 起为 error，可用申报 timing 补覆盖）
TIMING_REQUIRED_MINUTES = 30   # 活动跨度超过此值必须有 timing 记录（DeskPet 复盘：12h24m 全程 0 条）
TIMING_MIN_COVERAGE = 0.2      # timing 总时长须覆盖活动跨度的最低比例（防"记一条 5 分钟糊弄 10 小时"）
EVIDENCE_MTIME_GRACE_SECONDS = 300  # 证据文件 mtime 允许早于开账的宽限（时钟偏差）
AUDIT_ENGINE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.\-]*$")  # 引擎身份：不接受下划线/空格（方法名）
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
    "SCHEMA_INVALID", "LEDGER_TAMPERED", "RUN_ABANDONED",
    "REQUIRED_SCENARIO_NOT_RUN", "STATUS_CONFLICT",
    "DELIVERY_VERDICT_CONTRADICTS_LEDGER", "UI_EVIDENCE_MISSING",
    "RUN_CREATION_UNVERIFIED", "EVIDENCE_MISSING", "EVIDENCE_HASH_MISMATCH",
    "PRIMARY_EVIDENCE_MISSING", "EVIDENCE_CONTRACT_UNSATISFIED",
    "EVIDENCE_PRODUCER_UNTRUSTED",
    "EVIDENCE_DEPENDENCY_CYCLE", "EVIDENCE_PREDATES_LEDGER",
    "DERIVED_EVIDENCE_ONLY", "FROZEN_ORACLE_CHANGED",
    "BEHAVIOR_APPROVAL_REQUIRED", "APPLICABILITY_UNDECLARED",
    "APPLICABILITY_GATE_UNSATISFIED", "DRIVER_APPROVAL_MISSING",
    "RISK_CLOSURE_MISSING",
    "STABILITY_SAMPLES_INSUFFICIENT", "RELEASE_UNIT_TOO_LARGE",
    "RELEASE_UNIT_UNDECLARED", "WIP_ACCUMULATION_UNSAFE",
    "LOOP_LIMIT_EXCEEDED", "LOOP_REGRESSION", "LOOP_NO_PROGRESS", "LOOP_RESET_EVASION",
    "SCOPE_AUDIT_REQUIRED", "ARCHITECTURE_RESET_REQUIRED",
    "USER_REVIEW_REQUIRED", "USER_SCOPE_APPROVAL_REQUIRED",
    "PLAN_UNSTABLE", "LEDGER_STALLED",
    "TESTED_RUNTIME_MISMATCH", "RETEST_REQUIRED_AFTER_CHANGE",
    "AUDITOR_MISSING", "AUDITOR_VERDICT_MISMATCH",
    "OPEN_AUDIT_FINDINGS",
    "AUDITOR_INPUT_STALE", "RECEIPT_STALE",
    "ACTIVE_RUN_MISMATCH",
    "TIMING_MISSING", "TIMING_GAP", "PHASE_UNPAIRED",
    "PLAN_SCOPE_EXPANSION",  # advisory
    "AUDITOR_INDEPENDENCE_UNVERIFIED",
    # fixture_only run 免检：合成回放的时间戳与证据分布不适用真实执行启发式。
    "RUN_ATTESTATION_FANOUT",      # 条件 error：required 场景缺独立 primary 证据
    "EVIDENCE_FREE_FINALIZE",      # required 全 PASS 但整本账零 primary 证据
    "EXECUTOR_ENGINE_UNDECLARED",  # manifest 未声明 executor_engine
    "AUDITOR_ENGINE_MISMATCH",     # 实际审计引擎偏离 init 冻结的 auditor_engine
    "OPEN_DEFERRALS",              # auditor 产物里留有"留待后续"的 deferred findings
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
    # 已初始化账本以冻结值为准；这也保留 active-run opt-in 在 init 时加入的精确 registry
    # 文件。若后续重新派生，会漏掉该文件并把 activate-run 自己误判成被测内容变化。
    frozen = ledger_or_manifest.get("exclusion_scope")
    if isinstance(frozen, list):
        return sorted({str(rel).replace(os.sep, "/").rstrip("/")
                       for rel in frozen if str(rel).strip()})
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
        # 已删除的文件**不记条目**：删除通过"条目从列表里消失"体现即可。
        # 记成 "absent" 会让指纹依赖索引状态——文件删了但未 git add 时索引里还有它（记 absent），
        # commit 之后索引里没有了（条目消失），同一份工作树内容却算出两个指纹，
        # 于是"提交"这个不改内容的动作会误触发 TESTED_RUNTIME_MISMATCH（提交本仓时实测到）。
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
        # 同上：已删除的文件不记条目
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
        if "testcase_ids" in s and not isinstance(s["testcase_ids"], list):
            errors.append("SCHEMA_INVALID: scenarios[%d].testcase_ids 须为数组" % i)
        contract = s.get("evidence_contract")
        if contract is not None and not isinstance(contract, dict):
            errors.append("SCHEMA_INVALID: scenarios[%d].evidence_contract 须为 object" % i)
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
        if "business_facts" in e and not isinstance(e["business_facts"], dict):
            errors.append("SCHEMA_INVALID: evidence[%d].business_facts 须为 object" % i)
    loops = ledger.get("challenge_loops", [])
    if not isinstance(loops, list):
        errors.append("SCHEMA_INVALID: challenge_loops 须为数组")
        loops = []
    for li, loop in enumerate(loops):
        where = "challenge_loops[%d]" % li
        if not isinstance(loop, dict):
            errors.append("SCHEMA_INVALID: %s 须为 object" % where)
            continue
        for key, typ in (("loop_id", str), ("loop_type", str), ("target_file", str),
                         ("baseline_hash", str), ("rounds", list)):
            _req(loop, key, typ, where, errors)
        orchestration = loop.get("orchestration", "legacy")
        if orchestration not in {"legacy", "clustered"}:
            errors.append("SCHEMA_INVALID: %s.orchestration=%r 非法" % (where, orchestration))
        if "specialist_challenges" in loop and not isinstance(
                loop["specialist_challenges"], list):
            errors.append("SCHEMA_INVALID: %s.specialist_challenges 须为数组" % where)
        snapshots = loop.get("contract_snapshots") or []
        if not isinstance(snapshots, list):
            errors.append("SCHEMA_INVALID: %s.contract_snapshots 须为数组" % where)
        modern_loop = bool(snapshots)
        for ri, round_record in enumerate(loop.get("rounds") or []):
            rw = "%s.rounds[%d]" % (where, ri)
            if not isinstance(round_record, dict):
                errors.append("SCHEMA_INVALID: %s 须为 object" % rw)
                continue
            _req(round_record, "round", int, rw, errors)
            _req(round_record, "plan_hash", str, rw, errors)
            if not modern_loop:
                # schema 1.3 legacy loop：findings 是数量 object；只读兼容，不允许再由新 CLI 续写。
                continue
            findings = _req(round_record, "findings", list, rw, errors) or []
            for fi, finding in enumerate(findings):
                fw = "%s.findings[%d]" % (rw, fi)
                if not isinstance(finding, dict):
                    errors.append("SCHEMA_INVALID: %s 须为 object" % fw)
                    continue
                _req(finding, "id", str, fw, errors)
                _req(finding, "severity", str, fw, errors)
                _req(finding, "scope_relation", str, fw, errors)
                _req(finding, "origin", str, fw, errors)
                _req(finding, "status", str, fw, errors)
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
    """从原始 run fact 计算场景状态；调用者不能直接写状态。

    **blocked 是非粘性的**（2026-08-09 修）：一条 blocked 只要被**其后**的一条 root pass
    覆盖就算解除。此前的实现是 `any(blocked for r in mine)` 且排在 fail 之前、扫的还是全部
    run 而非 root——于是"记一条 blocked"= 该场景永久钉死，整轮报废。而 Stop hook 当时的
    固定文案恰恰是"做不到的项标 BLOCKED"，等于诱导代理毁掉自己正在跑的轮次（simple_harness
    r7/r9 实测）。语义上 blocked 本就是"此刻做不到"，不是"永远不算数"，粘性没有依据。

    非粘性不引入绕过：解除 blocked 的唯一方式是**真的记一条 root pass**，而 root pass 该有的
    证据/UI/negative-assertion 等硬门一条不少——与从未 blocked 过的场景要求完全相同。
    fail 仍然粘性（root 一旦红，这一轮就是红的；改完代码 HEAD 会变，本来就该开新 run）。
    """
    sid = scenario["scenario_id"]
    mine = [(i, r) for i, r in enumerate(runs) if r.get("scenario_id") == sid]
    roots = [r for _, r in mine if r.get("kind") == "root"]
    if not mine:
        return "NOT_RUN"
    # runs 是 append-only，下标即时间序：取最后一条 root pass 的位置作为"解除线"。
    last_pass_at = max([i for i, r in mine
                        if r.get("kind") == "root" and r.get("result") == "pass"] or [-1])
    if any(r.get("result") == "blocked" and i > last_pass_at for i, r in mine):
        return "BLOCKED"
    if not roots:
        return "PARTIAL"  # 只有 retry/continuation，没有独立 root run
    if any(r.get("result") == "fail" for r in roots):
        return "FAIL"
    # 能走到这里，说明每一条 blocked 都已被其后的 root pass 覆盖——它们是"当时做不到"的历史
    # 记录，不再参与 PASS 判定；否则"先 blocked 后跑通"会永远卡在 PARTIAL，等于粘性换个名字。
    roots = [r for r in roots if r.get("result") != "blocked"] or roots
    if all(r.get("result") == "pass" for r in roots):
        gate_type = scenario.get("gate_type", "")
        if gate_type == "positive-value":
            ok = [r for r in roots if r.get("result") == "pass"
                  and r.get("business_terminal") not in (None, "", "insufficient", "empty", "partial")]
            if not ok:
                return "PARTIAL"  # engine 绿但业务终态无效
        return "PASS"
    return "PARTIAL"


def validate_evidence_contract(scenario, evidence):
    """Validate a scenario's explicit proof contract without content heuristics.

    A contract states which producers and facts are trusted.  It deliberately
    does not guess whether a JSON document "looks primary"; that is brittle and
    easy to game.  Legacy scenarios without a contract keep the 1.4 behavior.
    """
    contract = scenario.get("evidence_contract")
    if not isinstance(contract, dict):
        return []
    sid = scenario.get("scenario_id")
    primary = [e for e in evidence if e.get("scenario_id") == sid
               and e.get("kind") == "primary"]
    if not primary:
        return [Diag("PRIMARY_EVIDENCE_MISSING",
                     "场景 %s 缺少满足 contract 的 primary evidence" % sid, hint=sid)]
    diags = []
    allowed_producers = set(contract.get("producer_types") or [])
    eligible = [e for e in primary if not allowed_producers
                or e.get("producer_type") in allowed_producers]
    if allowed_producers and not eligible:
        diags.append(Diag(
            "EVIDENCE_PRODUCER_UNTRUSTED",
            "场景 %s 的 primary producer=%s，不在允许集合 %s" % (
                sid, sorted({str(e.get("producer_type")) for e in primary}),
                sorted(allowed_producers)), hint=sid))
    missing = []
    required_kinds = set(contract.get("required_artifact_kinds") or [])
    # 只有可信 producer 的记录能满足 contract 的其余字段；否则一条可信空记录可与
    # 一条不可信 self-report 拼接，把 producer 门洗白。
    present_kinds = {e.get("artifact_kind") for e in eligible}
    if not required_kinds.issubset(present_kinds):
        missing.append("artifact_kinds=%s" % sorted(required_kinds - present_kinds))
    for field in contract.get("required_identity") or []:
        if not any(e.get(field) not in (None, "") for e in eligible):
            missing.append("identity.%s" % field)
    if contract.get("required_timestamps") and not any(
            e.get("generated_at") for e in eligible):
        missing.append("generated_at")
    available_facts = set()
    for e in eligible:
        facts = e.get("business_facts")
        if isinstance(facts, dict):
            available_facts.update(k for k, v in facts.items() if v not in (None, ""))
    required_facts = set(contract.get("required_business_facts") or [])
    if not required_facts.issubset(available_facts):
        missing.append("business_facts=%s" % sorted(required_facts - available_facts))
    if missing:
        diags.append(Diag("EVIDENCE_CONTRACT_UNSATISFIED",
                          "场景 %s evidence contract 缺失: %s" % (
                              sid, ", ".join(missing)), hint=sid))
    return diags


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

    **它到底能做什么、不能做什么（第九轮独立审计实测后如实改写）**：
    链只把**末条** facts_digest 与当前快照对账，中间条目从不与真实状态比对。因此改一条事实后
    只需重算末条 facts_digest 与末条 chain、再同步 integrity.chain——**4 行、O(1)，与链长无关**。
    早先文档说的"必须重算整条链""必须逐条重放"都被证伪过，是把估计换措辞重述。

    正确的定位：**它只能发现"改了文件但没同步链"的编辑**（顺手改、脚本误写、合并冲突残留），
    发现不了任何愿意多写四行的对手。这是本地无密钥哈希链的固有上限——文件与校验逻辑都在
    被测者手里，怎么设计都一样。**要真正防篡改，锚点必须在被测者写不到的地方**：
    CI 从 git 历史重算并比对 receipt，或把 receipt 推到 append-only 的远端存储。
    见 hooks/README.md「方式 B：CI」。
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


def expected_chain_length(ledger):
    """账本里每一条可追加事实都对应一次 CLI 写入，因此链长有下界。

    这条不变量是"链截断/重建"这一类攻击的类级封堵：伪造者不能再把链压成一条 init，
    必须逐条重放全部写入才对得上——那已经是显式的、成本高得多的行为。
    """
    n = 1  # init
    for key in ("runs", "evidence", "declared_statuses", "timing", "attestations",
                "superseded_evidence", "approvals"):
        n += len(ledger.get(key) or [])
    # ``record-run --exec`` deliberately appends one run and its captured
    # primary log in the same atomic CLI write.  The chain therefore grows by
    # one, not two.  Only discount evidence whose generated path exactly
    # matches the run's immutable 1-based position and scenario slug; ordinary
    # attach-evidence writes must still contribute their own chain entry.
    evidence_paths = {
        str(e.get("path") or "") for e in (ledger.get("evidence") or [])
    }
    paired_exec_evidence = 0
    for seq, run in enumerate(ledger.get("runs") or [], start=1):
        if "exec_exit_code" not in run:
            continue
        safe_scenario = re.sub(
            r"[^A-Za-z0-9_.-]", "_", str(run.get("scenario_id") or "")
        )
        expected_path = "artifacts/exec-%s-%04d.log" % (safe_scenario, seq)
        if expected_path in evidence_paths:
            paired_exec_evidence += 1
    n -= paired_exec_evidence
    n += len(ledger.get("events") or [])
    for loop in ledger.get("challenge_loops") or []:
        n += 1
        n += len(loop.get("rounds") or [])
        n += len(loop.get("control_events") or [])
        if loop.get("challenge_clusters") is not None:
            n += 1
        n += len(loop.get("specialist_challenges") or [])
        if loop.get("synthesis"):
            n += 1
    if ledger.get("auditor"):
        n += 1
    if ledger.get("delivery"):
        n += 1
    if ledger.get("retired"):
        n += 1
    if ledger.get("acknowledged"):
        n += 1
    return n


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
    # 链长下界：只封"把链压短"这一个形态。**它不构成防篡改**——改末条即可 O(1) 洗白，
    # 与链长无关（第九轮独立审计实测）。保留它只是因为成本为零，能挡住最省事的那一种编辑。
    expected = expected_chain_length(ledger)
    if len(log) < expected:
        return ("integrity 链只有 %d 条，账本里的事实至少需要 %d 条——链被截断或重建"
                % (len(log), expected))
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


def impact_affected_scenarios(ledger, changed_paths, changed_count):
    """behavioral 变更影响哪些 required 场景。返回 (affected_ids, reason)。

    **fail-closed 设计**：映射（scenario.impact_paths）由被测者自写，是新的绕过面——
    把高危文件不映射到任何场景，就能让改动不触发任何复测。因此凡是无法证明"这个变更
    与某场景无关"的情况，一律按全量复测处理：
      - 没有任何场景声明 impact_paths → 全量（与 1.2.0 行为一致）；
      - 变更清单被截断（changed_count > 已存清单长度）→ 全量；
      - 任一非文档变更未命中任何场景的 impact_paths → 全量；
      - 未声明 impact_paths 的场景 → 永远算受影响（保守默认）。
    映射在 init 时随场景冻结进账本与 receipt digest，事后改映射即 LEDGER_TAMPERED。
    """
    scenarios = ledger.get("scenarios") or []
    required = [s for s in scenarios if s.get("required")]
    all_ids = {s["scenario_id"] for s in required}
    declared = [s for s in scenarios if s.get("impact_paths")]
    if not declared:
        return all_ids, "无 impact_paths 映射，按全量复测"
    changed_paths = changed_paths or []
    if changed_count and changed_count > len(changed_paths):
        return all_ids, ("变更清单被截断（%d>%d），无法证明范围，按全量复测"
                         % (changed_count, len(changed_paths)))
    non_doc = [p for p in changed_paths
               if not DOC_ONLY_PATTERNS_MATCH(p, ledger.get("doc_only_globs") or None)]
    affected = {s["scenario_id"] for s in required if not s.get("impact_paths")}
    uncovered = []
    for pth in non_doc:
        low = pth.replace(os.sep, "/").lower()
        base = low.rsplit("/", 1)[-1]
        hit = False
        for s in scenarios:
            ips = s.get("impact_paths")
            if ips and _match_globs(low, base, ips):
                hit = True
                if s.get("required"):
                    affected.add(s["scenario_id"])
        if not hit:
            uncovered.append(pth)
    if uncovered:
        return all_ids, ("变更 %s 未被任何 impact_paths 覆盖——fail-closed 按全量复测"
                         % ", ".join(uncovered[:3]))
    return affected, "按 impact_paths 映射缩小复测范围（未受影响场景沿用既有结论）"


def _mtime_iso(path):
    try:
        return _utc_iso(os.path.getmtime(path))
    except OSError:
        return None


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


def read_output_deferrals(run_dir, output_path):
    """从 auditor 原始产物（JSON）里收集 deferred findings 的标识列表。

    "留待 slice 5 / 后续兑现"这类承诺此前只写在审计文本里，run 一收尾就悬空——
    没有任何机制提醒它还没兑现。findings 项标了 "status": "deferred" 或
    "deferred": true 即视为待办 deferral，finalize/render 时曝光（OPEN_DEFERRALS）。
    返回 id（或截断 text）列表；非 JSON / 无 findings 返回空列表。
    """
    if not output_path:
        return []
    p = os.path.join(run_dir, output_path)
    if not os.path.exists(p):
        return []
    try:
        with open(p, "r", encoding="utf-8") as f:
            obj = json.load(f)
    except (OSError, ValueError):
        return []
    if not isinstance(obj, dict):
        return []
    out = []
    for f_ in obj.get("findings") or []:
        if not isinstance(f_, dict):
            continue
        if str(f_.get("status") or "").lower() == "deferred" or f_.get("deferred") is True:
            out.append(str(f_.get("id") or f_.get("text") or "")[:60])
    return out


def read_structured_audit_findings(run_dir, output_path):
    """Read the optional JSON audit finding envelope; never regex Markdown."""
    p = os.path.join(run_dir, output_path or "")
    try:
        with open(p, "r", encoding="utf-8") as f:
            obj = json.load(f)
    except (OSError, ValueError):
        return None
    if (not isinstance(obj, dict) or "findings" not in obj
            or not isinstance(obj.get("findings"), list)):
        return None
    raw_findings = obj.get("findings") or []
    # 1.4 的 advisory/deferral envelope 也使用 findings，但字段是
    # severity=info + text。它继续由 OPEN_DEFERRALS 曝光，不把旧格式强行按 1.5
    # remediation obligation 解释。出现任一 P0/P1/P2 则视为新格式并严格校验全部项。
    if raw_findings and not any(isinstance(item, dict) and
                                item.get("severity") in FINDING_SEVERITIES
                                for item in raw_findings):
        return None
    report = obj.get("report_markdown")
    if isinstance(report, str):
        matches = re.findall(r"(?m)^VERDICT:\s*(PASS|FAIL)\s*$", report)
        if matches and matches[-1] != str(obj.get("verdict") or "").upper():
            die("AUDITOR_VERDICT_MISMATCH: JSON verdict 与 report_markdown 文末结论不一致")
    normalized = []
    seen_ids = set()
    for i, item in enumerate(raw_findings):
        if not isinstance(item, dict):
            die("SCHEMA_INVALID: auditor findings[%d] 须为 object" % i)
        required = {"id", "severity", "status", "type", "summary"}
        if not required.issubset(item):
            die("SCHEMA_INVALID: auditor findings[%d] 缺少 %s" % (
                i, ", ".join(sorted(required - set(item)))))
        if item["severity"] not in FINDING_SEVERITIES:
            die("SCHEMA_INVALID: auditor finding severity=%r" % item["severity"])
        if item["status"] not in {"open", "resolved", "deferred"}:
            die("SCHEMA_INVALID: auditor finding status=%r" % item["status"])
        if str(item["id"]) in seen_ids:
            die("SCHEMA_INVALID: auditor finding id 重复: %s" % item["id"])
        seen_ids.add(str(item["id"]))
        if item["type"] not in {"plan", "code", "testcase", "evidence", "docs", "release"}:
            die("SCHEMA_INVALID: auditor finding type=%r" % item["type"])
        if item.get("required_retest") and not item.get("scenario_ids"):
            die("SCHEMA_INVALID: required_retest=true 必须绑定非空 scenario_ids")
        if (item["severity"] in {"P0", "P1"}
                and not (item.get("ac_ids") or item.get("scenario_ids"))):
            die("SCHEMA_INVALID: P0/P1 finding 必须绑定 ac_ids 或 scenario_ids")
        normalized.append({
            "id": str(item["id"]),
            "severity": item["severity"],
            "status": item["status"],
            "type": str(item["type"]),
            "summary": str(item["summary"]),
            "ac_ids": list(item.get("ac_ids") or []),
            "scenario_ids": list(item.get("scenario_ids") or []),
            "required_retest": bool(item.get("required_retest")),
        })
    return normalized


def validate(run_dir, ledger, mode="full", fixture=False):
    """核心 validator。mode: check-only | full | render。返回 (diags, computed)。"""
    diags = []
    for err in structural_check(ledger):
        diags.append(Diag("SCHEMA_INVALID", err))
    tamper = integrity_check(ledger)
    if tamper:
        diags.append(Diag("LEDGER_TAMPERED", tamper))
    if ledger.get("acknowledged"):
        # 用户已确认放弃这一轮：hook 不再拿它阻断收尾，但它**永远不能再产出 receipt**——
        # 否则 acknowledge 就成了"承认放弃即通过"，还能反过来去 retire 别的 run。
        diags.append(Diag("RUN_ABANDONED",
                          "本 run 已由用户确认放弃（%s）：不再阻断收尾，也不得作为交付证据或继任 run"
                          % (ledger.get("acknowledged_reason") or "未记理由")))
    if ledger.get("active_run_required"):
        repo = os.path.abspath(ledger.get("repo_root") or "")
        registry_path = os.path.join(repo, ".plan-test", "active-run.json")
        registry = None
        try:
            with open(registry_path, "r", encoding="utf-8") as f:
                registry = json.load(f)
        except (OSError, ValueError):
            pass
        try:
            expected_rel = os.path.relpath(os.path.realpath(run_dir), os.path.realpath(repo)).replace(
                os.sep, "/")
        except ValueError:
            expected_rel = ""
        current_att = ledger.get("runtime_attestation") or ledger.get("baseline") or {}
        if (not isinstance(registry, dict)
                or registry.get("run_dir") != expected_rel
                or registry.get("run_id") != ledger.get("run_id")
                or registry.get("acceptance_sha256") != (ledger.get("acceptance") or {}).get("sha256")
                or registry.get("candidate_content_digest") != current_att.get("content_digest")):
            diags.append(Diag(
                "ACTIVE_RUN_MISMATCH",
                "本 run 要求 active-run 绑定，但 registry 缺失、指向其他 run，或候选内容已变化；"
                "完成 re-attest 后重新执行 activate-run"))
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
        # 先测后开账侦测（DeskPet 复盘：截图 22:31 生成、账本 00:14/02:10 才建，整本补录）：
        # attach 时记录的文件 mtime 早于开账时刻 → 该证据产生于账本存在之前。历史证据必须走
        # import-evidence 显式导入（保留 chain of custody），不许当作当场采集的证据混入。
        # 这是流程门不是防伪门：mtime 可以被 touch 掉，但那是主动伪造，不是顺手偷懒。
        if not e.get("imported"):
            fm = parse_rfc3339(e.get("file_mtime") or "")
            created_ts = parse_rfc3339(ledger.get("created_at") or "")
            if fm is not None and created_ts is not None \
                    and fm < created_ts - EVIDENCE_MTIME_GRACE_SECONDS:
                diags.append(Diag("EVIDENCE_PREDATES_LEDGER",
                                  "证据 %s 的文件时间早于开账时刻 %.0f 分钟——先测后补账。"
                                  "历史证据须用 import-evidence --from-run 显式导入"
                                  % (e.get("path"), (created_ts - fm) / 60.0),
                                  hint=e.get("path")))
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
        diags.extend(validate_evidence_contract(s, evidence))

    # 4b. 同命令同时间戳扇出：若任一 required 场景缺独立 primary 证据则拦截。
    #     一次 smoke 不能仅靠复制自报记录证明 N 条 AC；每场景有独立断言证据则合法。
    if not fixture:
        fanout = {}
        for r in runs:
            if r.get("kind") != "root":
                continue
            cmd = str(r.get("command") or "").strip()
            when = str(r.get("recorded_at") or "")
            if not cmd or not when:
                continue
            fanout.setdefault((cmd, when), set()).add(r.get("scenario_id"))
        primary_sids = {e.get("scenario_id") for e in evidence
                        if e.get("kind") == "primary" and e.get("scenario_id")}
        required_sids = {s.get("scenario_id") for s in scenarios if s.get("required")}
        for (cmd, when), sids in sorted(fanout.items()):
            if len(sids) < 2:
                continue
            lacking = sorted((sids & required_sids) - primary_sids)
            if lacking:
                diags.append(Diag("RUN_ATTESTATION_FANOUT",
                                  "同一命令在同一时间戳（%s）扇出为 %d 个场景的 root pass，"
                                  "其中 %s 缺独立 primary 证据；用 record-run --exec 或"
                                  " attach-evidence 为每个场景保存独立断言日志"
                                  % (when, len(sids), "、".join(lacking)),
                                  severity="error"))

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

    # 9a. behavioral re-attest 之后，受影响的 required 场景必须重测（按 impact_paths 缩小范围，
    #     fail-closed：证明不了无关就算全量——见 impact_affected_scenarios）
    atts = [a for a in (ledger.get("attestations") or [])
            if a.get("change_kind") == "behavioral"]
    if atts:
        cutoffs, reasons = {}, {}
        for a in atts:
            aff, why = impact_affected_scenarios(
                ledger, a.get("changed_paths"), a.get("changed_count"))
            idx = int(a.get("runs_index") or 0)
            when = str(a.get("recorded_at") or "")
            for sid in aff:
                if idx >= cutoffs.get(sid, -1):
                    cutoffs[sid] = idx
                    reasons[sid] = (why, when)
        for s in scenarios:
            if not s.get("required"):
                continue
            sid = s["scenario_id"]
            if sid not in cutoffs:
                continue  # impact_paths 证明本场景与全部 behavioral 变更无关
            fresh = any(r.get("scenario_id") == sid and r.get("kind") == "root"
                        and r.get("result") == "pass"
                        for r in runs[cutoffs[sid]:])
            if not fresh:
                why, when = reasons[sid]
                diags.append(Diag("RETEST_REQUIRED_AFTER_CHANGE",
                                  "场景 %s 的通过记录早于最近一次 behavioral 变更（%s；%s）——"
                                  "代码/配置改过就必须重跑，不能沿用旧结论" % (sid, when, why),
                                  hint=sid))

    # 9b. 适用性判定入账 + 判"适用"时矩阵必须兑现
    diags.extend(validate_applicability(ledger, scenarios,
                                        dict(ledger.get("thresholds") or {})))

    # 9c. 全 AI 驾驶批准（phase-4 ①b 的机器化）：输入语义敏感功能的 required UI 场景，
    #     至少 1 次真人驾驶；确需全 AI 驾驶，须有用户批准 artifact（record-approval）。
    #     DeskPet 复盘：账本 12 条 run 全 driver=ai、叙述却写"真人 E2E"，且无批准记录——
    #     这条规则此前只写在文档里，validator 完全不知道。
    app_is = (ledger.get("applicability") or {}).get("input_sensitive") or {}
    if app_is.get("value") is True:
        ui_ids = {s["scenario_id"] for s in scenarios if s.get("required") and s.get("ui")}
        ui_runs = [r for r in runs if r.get("scenario_id") in ui_ids]
        if ui_runs and not any(r.get("driver") == "human" for r in ui_runs):
            approved = any(a.get("kind") == "all-ai-driving"
                           for a in ledger.get("approvals") or [])
            if not approved:
                diags.append(Diag("DRIVER_APPROVAL_MISSING",
                                  "输入语义敏感 + required UI 场景全部由 AI 驾驶，且无用户批准记录——"
                                  "至少 1 次真人驾驶，或用 record-approval --kind all-ai-driving "
                                  "登记用户在 chat 中的显式批准（绑定消息 hash）"))

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

    # 12. structured auditor findings are remediation obligations, not prose.
    open_audit = [f for f in (ledger.get("audit_findings") or [])
                  if f.get("severity") in {"P0", "P1"}
                  and f.get("status") in {"open", "deferred"}]
    if open_audit:
        diags.append(Diag(
            "OPEN_AUDIT_FINDINGS",
            "存在未闭环 auditor P0/P1: %s" %
            ", ".join(sorted(str(f.get("id")) for f in open_audit))))

    # 12b. auditor（仅 full/render 模式要求）
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

    # 12b. 引擎声明对账（2026-08-19 新增，均 advisory，fixture 免检）。
    # 病根：引擎选择此前纯靠代理自觉读 Markdown 配置——simple_harness 无项目级 override、
    # 默认 AUDITOR_ENGINE=opus-4.8，实际 4 次审计全是 gpt-5，executor_engine 全部 None，
    # 独立性检查因此形同虚设。现在：executor 未声明、实际审计引擎偏离 init 冻结声明，
    # 都要在 report/receipt 里看得见。
    if not fixture and mode in ("full", "render"):
        if not str(ledger.get("executor_engine") or "").strip():
            diags.append(Diag("EXECUTOR_ENGINE_UNDECLARED",
                              "manifest 未声明 executor_engine——实现引擎无记录，"
                              "AUDITOR_INDEPENDENCE 自审检查无从对照",
                              severity="advisory"))
        declared_auditor = str(ledger.get("auditor_engine") or "").strip().lower()
        if auditor and declared_auditor:
            actual_engine = str(auditor.get("engine") or "").strip().lower()
            if actual_engine and actual_engine != declared_auditor:
                diags.append(Diag("AUDITOR_ENGINE_MISMATCH",
                                  "init 冻结 auditor_engine=%s，实际审计引擎=%s——"
                                  "引擎配置被静默偏离" % (declared_auditor, actual_engine),
                                  severity="advisory"))
        # 12c. auditor 产物里的 deferred findings 曝光："留待 slice 5"这类承诺此前只在
        # 审计文本里，run 一收尾就悬空（simple_harness run-4 的"真实 LLM E2E 留待
        # slice 5"之后无人兑现）。曝光不拦截——关闭方式是后续 run 真的覆盖该承诺。
        deferred = read_output_deferrals(run_dir, auditor.get("output_path"))
        if deferred:
            diags.append(Diag("OPEN_DEFERRALS",
                              "审计留有 %d 条待办 deferral（%s）——后续 slice/run 必须兑现"
                              "或在交付说明里显式关闭，不许悬空"
                              % (len(deferred), "、".join(deferred)),
                              severity="advisory"))

    # 13. 时间记账硬门（schema 1.3.0：advisory → error）。
    # DeskPet 复盘实锤：12h24m 的真实执行，四本账 timing/checkpoint 全 0，phase-4 写的
    # "每 90–120 分钟 checkpoint" 只是 advisory——文档说必须、机器不拦，规则权威一起塌。
    # 现在：活动跨度（含证据文件时间）超过 TIMING_REQUIRED_MINUTES 却没有像样的 timing
    # 覆盖 → TIMING_MISSING；已有锚点之间超过 TIMING_GAP_MINUTES 的空洞 → TIMING_GAP。
    # 两者都是 error，且都有合法出路：漏记的时段用 record-timing 申报模式补
    # （--declared-start/--declared-end，自动标 measured=false，report 单列低信任）。
    # 这仍是流程门不是防伪门——申报值本就是自陈；它保证的是"有账"，不是"账真"。
    # fixture_only run 免检时钟门：fixture 回放在任意时刻重放历史 steps，created_at 与
    # 申报时间戳天然双峰，跨度没有意义；且 fixture receipt 本就不可作交付证据（exit 3）。
    if not fixture:
        timing = ledger.get("timing") or []
        activity_ts = []
        created_ts = parse_rfc3339(ledger.get("created_at") or "")
        if created_ts is not None:
            activity_ts.append(created_ts)
        for coll, key in ((runs, "recorded_at"), (evidence, "attached_at"),
                          (evidence, "file_mtime"),
                          (ledger.get("attestations") or [], "recorded_at")):
            for item in coll:
                ts = parse_rfc3339(item.get(key) or "")
                if ts is not None:
                    activity_ts.append(ts)
        intervals = []   # timing 区间 + checkpoint/phase 零宽点：覆盖模型，不是点距模型
        timed_ms = 0
        for t in timing:
            timed_ms += int(t.get("elapsed_ms") or 0)
            s = parse_rfc3339(t.get("started_at") or "")
            e = parse_rfc3339(t.get("ended_at") or "")
            if s is not None and e is not None:
                intervals.append((s, e))
                activity_ts += [s, e]
        for ev in ledger.get("events") or []:
            if ev.get("type") in ("checkpoint", "phase"):
                ts = parse_rfc3339(ev.get("at") or "")
                if ts is not None:
                    intervals.append((ts, ts))
                    activity_ts.append(ts)
        span_min = ((max(activity_ts) - min(activity_ts)) / 60.0) \
            if len(activity_ts) >= 2 else 0.0
        if span_min > TIMING_REQUIRED_MINUTES and \
                timed_ms < span_min * 60000.0 * TIMING_MIN_COVERAGE:
            diags.append(Diag("TIMING_MISSING",
                              "活动跨度 %.0f 分钟，timing 记账仅覆盖 %.0f 分钟（<%d%%）——"
                              "机器命令用 record-timing --exec 包裹，真人/等待时段用申报模式补记"
                              % (span_min, timed_ms / 60000.0, int(TIMING_MIN_COVERAGE * 100))))
        elif intervals:
            # 合并重叠区间后看**未覆盖的空洞**——申报一段 [t1,t2] 是对整段的覆盖，
            # 不能按端点点距误报（1.2.0 的点距算法在这里是错的，升 error 前必须修）。
            intervals.sort()
            merged = [list(intervals[0])]
            for s, e in intervals[1:]:
                if s <= merged[-1][1]:
                    merged[-1][1] = max(merged[-1][1], e)
                else:
                    merged.append([s, e])
            for (s1, e1), (s2, e2) in zip(merged, merged[1:]):
                gap_min = (s2 - e1) / 60.0
                if gap_min > TIMING_GAP_MINUTES:
                    diags.append(Diag("TIMING_GAP",
                                      "记账覆盖之间有 %.0f 分钟空洞（>%d）——空洞时段须用申报 timing "
                                      "补覆盖（user_wait/provider_wait 等），或如实说明后重开 run"
                                      % (gap_min, TIMING_GAP_MINUTES)))
                    break

    # 13b. phase 事件配对（只在 full/render 检查——check-only 时阶段可能尚未收尾）
    if mode in ("full", "render"):
        open_count = {}
        for ev in ledger.get("events") or []:
            if ev.get("type") != "phase":
                continue
            ph = str(ev.get("phase") or "")
            if ev.get("action") == "start":
                open_count[ph] = open_count.get(ph, 0) + 1
            elif ev.get("action") == "end":
                open_count[ph] = open_count.get(ph, 0) - 1
        for ph in sorted(open_count):
            if open_count[ph] > 0:
                diags.append(Diag("PHASE_UNPAIRED",
                                  "阶段 %s 有 phase-start 但没有配对的 phase-end——"
                                  "阶段没收尾就 finalize，耗时归属不完整" % ph, hint=ph))
            elif open_count[ph] < 0:
                diags.append(Diag("PHASE_UNPAIRED",
                                  "阶段 %s 有 phase-end 但没有 phase-start" % ph, hint=ph))

    # 14. 零证据 finalize 曝光（2026-08-19 新增，advisory，fixture 免检）。
    # simple_harness 实测：4 个 slice required 全 PASS、receipt 全拿到，但 evidence=0、
    # timing=0——DERIVED_EVIDENCE_ONLY 只在"有证据但全是 derived"时触发，"零证据"反而
    # 无声通过。所有 PASS 均为自报的交付，report/receipt 里必须看得见。
    if not fixture and mode in ("full", "render") \
            and scenarios and required_all_pass \
            and not any(e.get("kind") == "primary" for e in evidence):
        diags.append(Diag("EVIDENCE_FREE_FINALIZE",
                          "全部 required 场景 PASS 但账本零 primary 证据——所有结论均为自报；"
                          "脚本测试改用 record-run --exec（执行日志自动入账），"
                          "UI 测试 attach 截图/回执", severity="advisory"))

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


def summarize_evidence(ledger):
    evidence_rows = ledger.get("evidence") or []
    artifact_to_records = {}
    for e in evidence_rows:
        artifact_to_records.setdefault(e.get("sha256"), []).append(e.get("evidence_id"))
    root_runs = [r for r in (ledger.get("runs") or []) if r.get("kind") == "root"]
    return {
        "records": len(evidence_rows),
        "distinct_artifacts": len({e.get("sha256") for e in evidence_rows if e.get("sha256")}),
        "distinct_root_runs": len({
            r.get("run_id_under_test") or canonical_digest({
                "scenario_id": r.get("scenario_id"), "recorded_at": r.get("recorded_at"),
                "command": r.get("command"),
            }) for r in root_runs
        }),
        "shared_artifact_sha256": sorted(
            digest for digest, ids in artifact_to_records.items()
            if digest and len(ids) > 1),
    }


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
        "evidence_summary": summarize_evidence(ledger),
        "acceptance_sha256": (ledger.get("acceptance") or {}).get("sha256"),
        "testcase_lock_sha256": canonical_digest(ledger.get("testcase_lock") or {}),
        "auditor_input_sha256": auditor.get("input_sha256"),
        "auditor_output_sha256": auditor.get("output_sha256"),
        "head": att.get("head") or baseline.get("head"),
        # 身份三分（DeskPet 复盘 P0-2）：receipt 只证明 tested_code_head 时刻的**内容**通过了门；
        # 之后仅新增 run-dir 记账产物的提交（evidence-only descendant）不改变被测内容指纹，
        # receipt 依然有效——所以"receipt 的 head ≠ 仓库最终 HEAD"可以是完全合法的状态。
        "tested_code_head": att.get("head") or baseline.get("head"),
        "content_basis": ("worktree-content-excluding-declared-scope"
                          if (att.get("content_digest") or baseline.get("content_digest"))
                          else "head+dirty (degraded)"),
        "exclusion_scope": ledger.get("exclusion_scope") or [],
        "timing_summary": {
            "entries": len(ledger.get("timing") or []),
            "measured_ms": sum(int(t.get("elapsed_ms") or 0)
                               for t in ledger.get("timing") or [] if t.get("measured")),
            "declared_ms": sum(int(t.get("elapsed_ms") or 0)
                               for t in ledger.get("timing") or [] if not t.get("measured")),
        },
        "dirty_patch_sha256": att.get("dirty_patch_sha256") or baseline.get("dirty_patch_sha256"),
        "fixture_only": bool(ledger.get("fixture_only")),
        "retired": bool(ledger.get("retired")),
        "superseded_by": ledger.get("superseded_by"),
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


def compiled_manifest_seal(manifest):
    """Bind every compiled verification surface that init consumes."""
    compiled = dict(manifest.get("compiled_manifest") or {})
    compiled.pop("seal_sha256", None)
    return canonical_digest({
        "compiled_manifest": compiled,
        "scenarios": manifest.get("scenarios") or [],
        "testcase_files": sorted(manifest.get("testcase_files") or []),
        "active_run_required": bool(manifest.get("active_run_required")),
        "structured_audit_required": bool(manifest.get("structured_audit_required")),
    })


def validate_required_evidence_contract(scenario):
    contract = scenario.get("evidence_contract")
    sid = scenario.get("scenario_id")
    if not isinstance(contract, dict) or not contract:
        return ["REQUIRED_EVIDENCE_CONTRACT_MISSING: %s" % sid]
    errors = []
    arrays = {}
    for field in ("producer_types", "required_artifact_kinds", "required_identity",
                  "required_business_facts"):
        value = contract.get(field, [])
        if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
            errors.append("%s %s 必须是字符串数组" % (sid, field))
            value = []
        arrays[field] = set(value)
    producers = arrays["producer_types"]
    artifact_kinds = arrays["required_artifact_kinds"]
    identity = arrays["required_identity"]
    facts = arrays["required_business_facts"]
    if not producers:
        errors.append("%s producer_types 不能为空" % sid)
    if not artifact_kinds:
        errors.append("%s required_artifact_kinds 不能为空" % sid)
    if "root_run_id" not in identity:
        errors.append("%s required_identity 必须含 root_run_id" % sid)
    if contract.get("required_timestamps") is not True:
        errors.append("%s required_timestamps 必须为 true" % sid)
    if scenario.get("gate_type") == "positive-value":
        if "business-result" not in artifact_kinds:
            errors.append("%s positive-value 必须要求 business-result artifact" % sid)
        if "business_terminal" not in facts:
            errors.append("%s positive-value 必须要求 business_terminal fact" % sid)
    if scenario.get("ui"):
        if "ui-capture" not in artifact_kinds:
            errors.append("%s UI 场景必须要求 ui-capture artifact" % sid)
        if "session_id" not in identity:
            errors.append("%s UI 场景 required_identity 必须含 session_id" % sid)
    if "temporal-fault" in set(scenario.get("required_lanes") or []):
        if "fault-recovery-log" not in artifact_kinds:
            errors.append("%s fault/recovery 场景必须要求 fault-recovery-log artifact" % sid)
        if "recovered_state" not in facts:
            errors.append("%s fault/recovery 场景必须要求 recovered_state fact" % sid)
    return errors


def cmd_compile_manifest(args):
    """Compile a frozen gate manifest from structured verification inputs.

    Markdown remains the human view.  The compiler intentionally consumes a
    small JSON verification spec instead of attempting lossy Markdown parsing.
    """
    spec = _read_json_file(args.spec, "verification spec")
    required = {"acceptance_file", "assurance_contract", "testcase_inventory",
                "reuse_report", "obligations", "scenarios"}
    if not isinstance(spec, dict) or not required.issubset(spec):
        die("SCHEMA_INVALID: verification spec 缺少 %s" %
            ", ".join(sorted(required - set(spec or {}))))
    assurance = _read_json_file(spec["assurance_contract"], "assurance contract")
    inventory = _read_json_file(spec["testcase_inventory"], "testcase inventory")
    reuse = _read_json_file(spec["reuse_report"], "testcase reuse report")
    obligations = spec.get("obligations")
    scenarios = spec.get("scenarios")
    if not isinstance(obligations, list) or not isinstance(scenarios, list):
        die("SCHEMA_INVALID: obligations/scenarios 须为数组")
    testcase_rows = inventory.get("testcases") if isinstance(inventory, dict) else None
    decisions = reuse.get("decisions") if isinstance(reuse, dict) else None
    if not isinstance(testcase_rows, list) or not isinstance(decisions, list):
        die("SCHEMA_INVALID: inventory.testcases/reuse_report.decisions 须为数组")
    try:
        from testcase_inventory import validate_inventory, validate_reuse_report
        inventory_errors = validate_inventory(
            inventory, os.path.dirname(os.path.abspath(spec["testcase_inventory"])))
        reuse_errors = validate_reuse_report(
            inventory, reuse,
            [row.get("obligation_id") for row in obligations if isinstance(row, dict)])
    except (ImportError, ValueError) as exc:
        die("TESTCASE_INVENTORY_INVALID: %s" % exc)
    if inventory_errors or reuse_errors:
        die("TESTCASE_INVENTORY_INVALID: %s" % "; ".join(
            sorted(set(inventory_errors + reuse_errors))))
    by_tc = {row.get("id"): row for row in testcase_rows if isinstance(row, dict)}
    if len(by_tc) != len(testcase_rows):
        die("SCHEMA_INVALID: testcase inventory 含重复或缺失 ID")
    decision_by_obligation = {
        row.get("obligation_id"): row for row in decisions if isinstance(row, dict)
    }
    covered_ac = set()
    selected = set()
    for row in obligations:
        if not isinstance(row, dict) or not row.get("obligation_id"):
            die("SCHEMA_INVALID: obligation 须含 obligation_id")
        oid = row["obligation_id"]
        decision = decision_by_obligation.get(oid)
        ids = (decision or {}).get("selected_testcases")
        if not isinstance(ids, list) or not ids:
            die("TESTCASE_REUSE_DECISION_MISSING: %s" % oid)
        for reference in ids:
            testcase_id = str(reference).split("@rev", 1)[0]
            tc = by_tc.get(testcase_id)
            if not tc:
                die("SELECTED_TESTCASE_MISSING: %s" % testcase_id)
            if tc.get("status") in {"retired", "superseded"}:
                die("SELECTED_TESTCASE_INACTIVE: %s status=%s" % (
                    testcase_id, tc.get("status")))
            selected.add(testcase_id)
        covered_ac.update(row.get("ac_ids") or [])
    required_ac = set(assurance.get("acceptance_ids") or [])
    unknown_ac = covered_ac - required_ac
    if unknown_ac:
        die("OBLIGATION_AC_UNKNOWN: %s" % ", ".join(sorted(unknown_ac)))
    if not required_ac.issubset(covered_ac):
        die("AC_COVERAGE_MISSING: %s" % ", ".join(sorted(required_ac - covered_ac)))
    scenario_testcases = set()
    scenario_ids = set()
    for row in scenarios:
        if not isinstance(row, dict) or not row.get("scenario_id"):
            die("SCHEMA_INVALID: scenario 须含 scenario_id")
        if row["scenario_id"] in scenario_ids:
            die("SCHEMA_INVALID: scenario_id 重复: %s" % row["scenario_id"])
        scenario_ids.add(row["scenario_id"])
        testcase_ids = row.get("testcase_ids") or []
        normalized_ids = {str(value).split("@rev", 1)[0] for value in testcase_ids}
        unknown_testcases = normalized_ids - set(by_tc)
        if unknown_testcases:
            die("SCENARIO_TESTCASE_UNKNOWN: %s" % ", ".join(sorted(unknown_testcases)))
        if row.get("required", True):
            if not normalized_ids:
                die("REQUIRED_SCENARIO_TESTCASE_MISSING: %s" % row["scenario_id"])
            contract_errors = validate_required_evidence_contract(row)
            if contract_errors:
                die("EVIDENCE_CONTRACT_INVALID: %s" % "; ".join(contract_errors))
        scenario_testcases.update(normalized_ids)
    if not selected.issubset(scenario_testcases):
        die("TESTCASE_SCENARIO_MAPPING_MISSING: %s" %
            ", ".join(sorted(selected - scenario_testcases)))
    manifest = dict(spec.get("manifest") or {})
    manifest["acceptance_file"] = spec["acceptance_file"]
    manifest["scenarios"] = scenarios
    # 使用 compiler 即选择 1.5 严格工作流；raw 1.x manifest 继续兼容读取。
    manifest["active_run_required"] = not bool(manifest.get("fixture_only"))
    manifest["structured_audit_required"] = True
    inventory_dir = os.path.dirname(os.path.abspath(spec["testcase_inventory"]))
    manifest["testcase_files"] = sorted({
        (path if os.path.isabs(path) else os.path.join(inventory_dir, path))
        for testcase_id in selected
        for path in [by_tc[testcase_id].get("path")]
        if path
    })
    full = sorted(row["scenario_id"] for row in scenarios if row.get("required", True))
    manifest["compiled_manifest"] = {
        "tool_version": VALIDATOR_VERSION,
        "input_hashes": {
            "acceptance": sha256_file(spec["acceptance_file"]),
            "assurance_contract": sha256_file(spec["assurance_contract"]),
            "testcase_inventory": sha256_file(spec["testcase_inventory"]),
            "reuse_report": sha256_file(spec["reuse_report"]),
            "verification_spec": sha256_file(args.spec),
        },
        "input_paths": {
            "acceptance": os.path.abspath(spec["acceptance_file"]),
            "assurance_contract": os.path.abspath(spec["assurance_contract"]),
            "testcase_inventory": os.path.abspath(spec["testcase_inventory"]),
            "reuse_report": os.path.abspath(spec["reuse_report"]),
            "verification_spec": os.path.abspath(args.spec),
        },
        "case_sets": {"full": full},
        "selected_testcase_ids": sorted(selected),
    }
    manifest["compiled_manifest"]["seal_sha256"] = compiled_manifest_seal(manifest)
    atomic_write_json(args.output, manifest)
    print("MANIFEST_COMPILED scenarios=%d testcases=%d full=%d" % (
        len(scenarios), len(selected), len(full)))


def cmd_init(args):
    run_dir = args.run_dir
    os.makedirs(os.path.join(run_dir, "artifacts"), exist_ok=True)
    if os.path.exists(ledger_path(run_dir)) and not args.force:
        die("run-dir 已 init（%s 存在）；重开新 run 请换目录" % LEDGER_NAME)
    with open(args.manifest, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    compiled_input = manifest.get("compiled_manifest") or {}
    if compiled_input:
        expected_seal = compiled_input.get("seal_sha256")
        if not expected_seal or expected_seal != compiled_manifest_seal(manifest):
            die("COMPILED_MANIFEST_SEAL_MISMATCH: compiled manifest/scenarios/testcase_files 被改动；"
                "须从原 verification spec 重新 compile-manifest")
        for name, expected_hash in (compiled_input.get("input_hashes") or {}).items():
            source_path = (compiled_input.get("input_paths") or {}).get(name)
            if not source_path or not os.path.isfile(source_path) or sha256_file(
                    source_path) != expected_hash:
                die("COMPILED_INPUT_CHANGED: %s 与 compile 时 hash 不一致；须重新编译" % name)
    repo = os.path.abspath(manifest.get("repo_root") or os.getcwd())
    fixture = bool(manifest.get("fixture_only"))
    if not fixture:
        try:
            rel = os.path.relpath(os.path.realpath(run_dir), os.path.realpath(repo))
        except ValueError:
            rel = ".."
        if rel.startswith("..") and not args.allow_external_run_dir:
            die("run-dir 在仓库之外（%s）：这样仓库里不会留下任何记账痕迹，hook/CI 也看不见它。\n"
                "确需如此请显式加 --allow-external-run-dir，该选择会记入账本。" % run_dir)
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
        "external_run_dir": bool(getattr(args, "allow_external_run_dir", False)),
        "doc_only_globs": manifest.get("doc_only_globs"),
        "executor_engine": manifest.get("executor_engine"),
        # 引擎声明冻结（2026-08-19）：配置写在 Markdown 里代理未必遵守（实测默认 opus-4.8、
        # 实际 4 次审计全是 gpt-5）。声明进账本后，finalize 对账实际引擎并曝光偏离。
        "auditor_engine": manifest.get("auditor_engine"),
        "challenger_engine": manifest.get("challenger_engine"),
        "release_unit": manifest.get("release_unit") or {},
        "thresholds": manifest.get("thresholds") or {},
        "baseline": {},
        "runtime_attestation": manifest.get("runtime_attestation") or {},
        "events": [],
        "challenge_loops": [],
        "compiled_manifest": manifest.get("compiled_manifest"),
        "active_run_required": bool(manifest.get("active_run_required")),
        "structured_audit_required": bool(manifest.get("structured_audit_required")),
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
    compiled = ledger.get("compiled_manifest") or {}
    expected_full = set(((compiled.get("case_sets") or {}).get("full") or []))
    if expected_full:
        actual_full = {s["scenario_id"] for s in ledger["scenarios"] if s.get("required")}
        if actual_full != expected_full:
            die("COMPILED_FULL_SURFACE_MISMATCH: expected=%s actual=%s" % (
                ",".join(sorted(expected_full)), ",".join(sorted(actual_full))))
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
        if ledger.get("active_run_required") and ".plan-test/active-run.json" not in scope:
            # Exact workflow metadata file only; visible in receipt exclusion_scope.
            scope.append(".plan-test/active-run.json")
            scope.sort()
        ledger["exclusion_scope"] = scope
        attestation = attest_runtime(repo, scope)
        # content_entries 可占账本绝大部分；runtime_attestation 保留唯一全量副本，
        # baseline 只存摘要，避免 init 时逐字节复制一份。
        ledger["runtime_attestation"] = attestation
        ledger["baseline"] = {
            key: value for key, value in attestation.items() if key != "content_entries"
        }
        if attestation.get("content_digest_error"):
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


def cmd_activate_run(args):
    ledger = load_ledger(args.run_dir)
    repo = os.path.abspath(ledger.get("repo_root") or "")
    try:
        rel = os.path.relpath(os.path.realpath(args.run_dir), os.path.realpath(repo))
    except ValueError:
        rel = ".."
    if rel.startswith(".."):
        die("ACTIVE_RUN_EXTERNAL: active run 必须位于 repo 内，供 hook/CI 复核")
    att = ledger.get("runtime_attestation") or ledger.get("baseline") or {}
    record = {
        "run_dir": rel.replace(os.sep, "/"),
        "run_id": ledger.get("run_id"),
        "acceptance_sha256": (ledger.get("acceptance") or {}).get("sha256"),
        "candidate_content_digest": att.get("content_digest"),
        "updated_at": now_iso(),
    }
    target_dir = os.path.join(repo, ".plan-test")
    os.makedirs(target_dir, exist_ok=True)
    atomic_write_json(os.path.join(target_dir, "active-run.json"), record)
    print("ACTIVE_RUN_SET: %s content=%s" % (
        record["run_dir"], str(record["candidate_content_digest"] or "")[:12]))


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
    exec_exit = None
    exec_ev = None
    started_at = ended_at = None
    elapsed_ms = None
    if args.exec_cmd is not None:
        if args.exec_cmd and args.exec_cmd[0] == "--":
            args.exec_cmd = args.exec_cmd[1:]
        if not args.exec_cmd:
            die("--exec 后须给出要执行的命令（用法：record-run ... --exec -- <cmd...>）")
        if args.result:
            die("--exec 模式下 result 由被包裹命令的 exit code 决定（0=pass 非 0=fail），"
                "不许自报 --result——自报与实测并存等于给'假 pass'留门")
        # 病根（simple_harness 2026-08-18 实测）：一条 pytest 跑一遍，同一秒给 4 条 AC 各记
        # 一条 root pass，零证据零耗时，finalize 全绿。--exec 把"自报"变成"gate 亲眼执行"：
        # exit code 决定 result，stdout/stderr 落盘自动成为 primary 证据。
        pre = load_ledger(args.run_dir)
        if args.scenario not in {s["scenario_id"] for s in pre.get("scenarios", [])}:
            die("场景 %s 不在 init 冻结的场景清单里（不许测后补场景，需重新 init/批准）" % args.scenario)
        os.makedirs(os.path.join(args.run_dir, "artifacts"), exist_ok=True)
        start_wall = time.time()
        t0 = time.monotonic_ns()
        proc = subprocess.run(args.exec_cmd, capture_output=True, text=True)
        elapsed_ms = int((time.monotonic_ns() - t0) // 1_000_000)
        end_wall = time.time()
        exec_exit = proc.returncode
        started_at, ended_at = _utc_iso(start_wall), _utc_iso(end_wall)
        args.result = "pass" if exec_exit == 0 else "fail"
        args.command = " ".join(args.exec_cmd)
        seq = len(pre.get("runs") or []) + 1
        safe_scenario = re.sub(r"[^A-Za-z0-9_.-]", "_", args.scenario)
        log_rel = "artifacts/exec-%s-%04d.log" % (safe_scenario, seq)
        log_abs = os.path.join(args.run_dir, log_rel)
        with open(log_abs, "w", encoding="utf-8") as f:
            f.write("command: %s\nexit_code: %d\nstarted_at: %s\nended_at: %s\n"
                    "elapsed_ms: %d\n---- stdout ----\n%s\n---- stderr ----\n%s\n"
                    % (args.command, exec_exit, started_at, ended_at, elapsed_ms,
                       proc.stdout or "", proc.stderr or ""))
        exec_ev = {
            "evidence_id": "ev-" + sha256_file(log_abs)[:12],
            "path": log_rel,
            "sha256": sha256_file(log_abs),
            "kind": "primary",
            "scenario_id": args.scenario,
            "producer_type": "gate-exec",
            "producer_version": VALIDATOR_VERSION,
            "artifact_kind": "execution-log",
            "generated_at": ended_at,
            "root_run_id": args.run_id_under_test,
            "session_id": args.session_id,
            "business_facts": ({"business_terminal": args.business_terminal}
                               if args.business_terminal else {}),
            "file_mtime": _mtime_iso(log_abs),
            "attached_at": now_iso(),
        }
    elif not args.result:
        die("须给 --result（自报）或 --exec -- <cmd>（gate 真执行，result 由 exit code 决定）")
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
        "exec_exit_code": exec_exit,
        "started_at": started_at,
        "ended_at": ended_at,
        "elapsed_ms": elapsed_ms,
        "recorded_at": now_iso(),
    }
    rec = {k: v for k, v in rec.items() if v is not None}

    def mutate(ledger):
        if args.scenario not in {s["scenario_id"] for s in ledger.get("scenarios", [])}:
            die("场景 %s 不在 init 冻结的场景清单里（不许测后补场景，需重新 init/批准）" % args.scenario)
        ledger["runs"].append(rec)
        if exec_ev:
            ledger["evidence"].append(exec_ev)

    _append(args.run_dir, mutate, op="record-run")
    print("RECORDED run scenario=%s kind=%s result=%s" % (args.scenario, args.kind, args.result))
    if exec_exit is not None:
        print("EXEC log=%s exit=%d（result 由 exit code 决定，执行日志已自动记为 primary 证据）"
              % (exec_ev["path"], exec_exit))
        if exec_exit != 0:
            sys.exit(exec_exit)  # 与 record-timing --exec 一致：如实透传被包裹命令的 exit code


def cmd_attach_evidence(args):
    try:
        rel_path = normalize_run_relative_path(args.path)
    except ValueError as exc:
        die(str(exc))
    p = run_relative_abspath(args.run_dir, rel_path)
    if not os.path.exists(p):
        die("证据文件不存在: %s（路径须相对 run-dir）" % p)
    imported_from = getattr(args, "from_run", None)
    metadata = {}
    if getattr(args, "metadata", None):
        metadata = _read_json_file(args.metadata, "evidence metadata")
        if not isinstance(metadata, dict):
            die("evidence metadata 须为 object")
        allowed_metadata = {
            "producer_type", "producer_version", "artifact_kind", "generated_at",
            "root_run_id", "session_id", "business_facts",
        }
        unknown = sorted(set(metadata) - allowed_metadata)
        if unknown:
            die("evidence metadata 未知字段: %s" % ", ".join(unknown))
        if "business_facts" in metadata and not isinstance(metadata["business_facts"], dict):
            die("evidence metadata.business_facts 须为 object")
    ev = {
        "evidence_id": args.id or ("ev-" + sha256_file(p)[:12]),
        "path": rel_path,
        "sha256": sha256_file(p),
        "kind": args.kind,
        "scenario_id": args.scenario,
        "ui_action": args.ui_action,
        "negative_assertion": args.negative_assertion,
        "depends_on": args.depends_on or [],
        # attach 时刻的文件 mtime 入账：validator 用它侦测"先测后开账"（证据产生早于账本）。
        # 这是流程门——touch 能洗掉它，但那是主动伪造，不是顺手偷懒。
        "file_mtime": _mtime_iso(p),
        "imported": bool(imported_from),
        "imported_from": imported_from,
        "attached_at": now_iso(),
    }
    ev.update(metadata)
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

    op = "import-evidence" if imported_from else "attach-evidence"
    _append(args.run_dir, mutate, op=op)
    if imported_from:
        print("IMPORTED %s kind=%s sha256=%s from=%s（历史证据，chain of custody 已入账）"
              % (rel_path, args.kind, ev["sha256"][:12], imported_from))
    else:
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


def cmd_phase_event(args, action):
    """阶段级事件：phase-start / phase-end。配对性由 finalize 检查（PHASE_UNPAIRED）。

    DeskPet 复盘：19:04–22:31 的 3.5 小时事后只能靠会话日志考古。阶段事件 + timing
    让 report 直接给出每阶段耗时，用户在执行期也能从账本看到当前在哪一阶段。
    """
    def mutate(ledger):
        ev = {"type": "phase", "action": action, "phase": args.phase,
              "at": _utc_iso(time.time())}
        if action == "end":
            ev["status"] = args.status
            # T6 遥测（自报，不参与任何门判定）：本阶段派发的子代理数与轮次数。
            # 目的：给 LEAN 档的压缩效果攒实测数据，render 的"本 run 开销表"聚合它们。
            if getattr(args, "subagents", None) is not None:
                ev["subagents"] = int(args.subagents)
            if getattr(args, "rounds", None) is not None:
                ev["rounds"] = int(args.rounds)
        if getattr(args, "note", None):
            ev["note"] = args.note
        ledger.setdefault("events", []).append(ev)

    _append(args.run_dir, mutate, op="phase-" + action)
    print("PHASE %s: %s" % (action.upper(), args.phase))


def cmd_record_approval(args):
    """登记用户在 chat 中的显式批准（如"全 AI 驾驶"）。绑定用户消息 hash，事后可对质。"""
    if not re.match(r"^[0-9a-f]{64}$", args.message_hash or ""):
        die("--message-hash 须为用户批准消息原文的 SHA-256（64 位十六进制）——"
            "批准必须能回溯到具体的一句话，不接受一个笼统的\"用户同意了\"")

    def mutate(ledger):
        ledger.setdefault("approvals", []).append({
            "kind": args.kind,
            "approved_by": "user",
            "message_sha256": args.message_hash,
            "note": args.note,
            "recorded_at": now_iso(),
        })

    _append(args.run_dir, mutate, op="record-approval")
    print("APPROVAL RECORDED kind=%s（绑定消息 hash %s…）" % (args.kind, args.message_hash[:12]))


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
        led_now = load_ledger(args.run_dir)
        affected, why = impact_affected_scenarios(led_now, changed, len(changed))
        req_all = {s["scenario_id"] for s in (led_now.get("scenarios") or [])
                   if s.get("required")}
        if affected == req_all:
            print("非文档变更 %d 个（如 %s）——%s：**全部 required 场景必须重跑并 record-run**，"
                  "否则 finalize 会以 RETEST_REQUIRED_AFTER_CHANGE 拦截。"
                  % (len(non_doc), ", ".join(non_doc[:3]), why))
        else:
            spared = sorted(req_all - affected)
            print("非文档变更 %d 个——%s：受影响场景 %s 必须重跑；%s 经映射证明无关，"
                  "沿用既有结论。" % (len(non_doc), why,
                                     ", ".join(sorted(affected)) or "（无）",
                                     ", ".join(spared)))
    else:
        print("仅文档变更（路径规则判定）——既有测试结论继续有效。")


def cmd_audit(args):
    ledger_before = load_ledger(args.run_dir)
    # 引擎身份校验（DeskPet 复盘：engine 填了方法名 fault_seam_analysis，独立性核对失去对象）：
    # --engine 必须是引擎/模型身份（如 opus-4.8、codex-gpt5.5、claude-sonnet-4-6），
    # 不接受含下划线/空格的方法名。启发式规则，挡的是"填错字段"，不是防伪。
    if not AUDIT_ENGINE_RE.match(args.engine or ""):
        die("--engine 须为引擎/模型身份（小写字母数字加 - .，如 opus-4.8），不接受方法名或"
            "含下划线/空格的值: %r。审计方法写进 auditor-output，引擎身份写在这里。" % args.engine)
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
    findings = read_structured_audit_findings(args.run_dir, args.output)
    if ledger_before.get("structured_audit_required") and findings is None:
        die("STRUCTURED_AUDIT_REQUIRED: compiled 1.5 workflow 只接受 JSON findings envelope")
    if (ledger_before.get("structured_audit_required")
            and args.verdict.upper() == "FAIL"
            and not any(f.get("status") in {"open", "deferred"} for f in (findings or []))):
        die("AUDIT_FAIL_FINDING_REQUIRED: FAIL audit 至少需要一个 open/deferred 结构化 finding")
    if args.verdict.upper() == "PASS" and findings is not None and any(
            f["severity"] in {"P0", "P1"} and f["status"] in {"open", "deferred"}
            for f in findings):
        die("OPEN_AUDIT_FINDINGS: PASS 产物仍含 open/deferred P0/P1")

    def mutate(ledger):
        if ledger.get("audit_findings"):
            ledger.setdefault("audit_findings_history", []).append({
                "superseded_at": now_iso(),
                "findings": ledger["audit_findings"],
            })
        if findings is not None:
            ledger["audit_findings"] = [dict(f, imported_runs_index=len(
                ledger.get("runs") or [])) for f in findings]
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
    if findings is None:
        print("提醒：auditor output 非结构化 JSON；verdict 已入账，但 findings 无法形成机器 obligation")


def cmd_resolve_audit_finding(args):
    ledger = load_ledger(args.run_dir)
    finding = next((f for f in (ledger.get("audit_findings") or [])
                    if f.get("id") == args.finding_id), None)
    if not finding:
        die("AUDIT_FINDING_NOT_FOUND: %s" % args.finding_id)
    if finding.get("status") == "resolved":
        print("AUDIT_FINDING_ALREADY_RESOLVED: %s" % args.finding_id)
        return
    if not args.resolution.strip():
        die("RESOLUTION_REQUIRED")
    evidence_ids = set(args.evidence_ids or [])
    if not evidence_ids:
        die("RESOLUTION_EVIDENCE_REQUIRED: finding resolution 必须绑定至少一个 evidence ID")
    known_evidence = {e.get("evidence_id") for e in (ledger.get("evidence") or [])}
    if not evidence_ids.issubset(known_evidence):
        die("RESOLUTION_EVIDENCE_MISSING: %s" %
            ", ".join(sorted(evidence_ids - known_evidence)))
    if finding.get("required_retest"):
        after = int(finding.get("imported_runs_index") or 0)
        later = (ledger.get("runs") or [])[after:]
        missing = [sid for sid in (finding.get("scenario_ids") or []) if not any(
            r.get("scenario_id") == sid and r.get("kind") == "root"
            and r.get("result") == "pass" for r in later)]
        if missing:
            die("AUDIT_FINDING_RETEST_REQUIRED: %s" % ", ".join(sorted(missing)))

    def mutate(current):
        target = next(f for f in current.get("audit_findings") or []
                      if f.get("id") == args.finding_id)
        target.update({
            "status": "resolved",
            "resolution": args.resolution,
            "resolution_evidence_ids": sorted(evidence_ids),
            "resolved_at": now_iso(),
            "resolved_candidate_content_digest": (
                current.get("runtime_attestation") or current.get("baseline") or {}
            ).get("content_digest"),
        })

    _append(args.run_dir, mutate, op="resolve_audit_finding")
    print("AUDIT_FINDING_RESOLVED: %s（旧 audit 已 stale，须重新审计）" % args.finding_id)


def cmd_list_audit_findings(args):
    ledger = load_ledger(args.run_dir)
    rows = ledger.get("audit_findings") or []
    for finding in rows:
        print("%s\t%s\t%s\t%s" % (
            finding.get("id"), finding.get("severity"), finding.get("status"),
            finding.get("summary")))
    print("AUDIT_FINDINGS: %d" % len(rows))


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
    if ledger.get("active_run_required") and not fixture:
        repo = os.path.abspath(ledger.get("repo_root") or "")
        registry_path = os.path.join(repo, ".plan-test", "active-run.json")
        try:
            with open(registry_path, "r", encoding="utf-8") as f:
                registry = json.load(f)
        except (OSError, ValueError):
            registry = {}
        registry["latest_valid_receipt_digest"] = receipt["content_digest"]
        registry["latest_valid_receipt_path"] = os.path.relpath(
            os.path.join(args.run_dir, RECEIPT_NAME), repo).replace(os.sep, "/")
        registry["receipt_finalized_at"] = receipt["finalized_at"]
        atomic_write_json(registry_path, registry)
    emit(diags, computed, ["FINALIZE: PASS%s" % (" (FIXTURE-ONLY)" if fixture else ""),
                           "GATE RECEIPT: %s" % receipt["content_digest"],
                           "RECEIPT FILE: %s" % os.path.join(args.run_dir, RECEIPT_NAME)])
    if fixture:
        # exit 3 ≠ exit 0：合成 run 不许冒充交付通过（设一个 fixture_only 字段就跳过
        # git 校验并拿到 exit 0，此前是最省事的一条绕过路径）
        print("FIXTURE-ONLY：exit=%d，本 receipt 不可作为真实交付证据" % FIXTURE_EXIT)
        sys.exit(FIXTURE_EXIT)
    sys.exit(0)


def _parse_iso_ts(s):
    """容错解析账本时间戳（Z / +0800 / +08:00 都可能出现）；解析不动返回 None。"""
    if not s:
        return None
    s2 = str(s).replace("Z", "+00:00")
    m = re.match(r"^(.*[+-]\d{2})(\d{2})$", s2)
    if m:
        s2 = m.group(1) + ":" + m.group(2)
    try:
        from datetime import datetime as _dt
        return _dt.fromisoformat(s2).timestamp()
    except ValueError:
        return None


def _phase_cost_rows(ledger):
    """T6 遥测聚合：阶段 × 事件跨度 × timing 实测 × 子代理派发数 × 轮次数。

    数据全部来自账本已有事实：phase-start/end 配对给跨度，timing 的 phase 字段给实测耗时，
    phase-end 的 subagents/rounds 是自报遥测。只读聚合，不参与任何门判定。
    """
    spans, opens, order = {}, {}, []
    for e in ledger.get("events") or []:
        if e.get("type") != "phase":
            continue
        ph = e.get("phase") or "?"
        if ph not in spans:
            spans[ph] = {"span_ms": 0, "subagents": 0, "rounds": 0}
            order.append(ph)
        if e.get("action") == "start":
            opens[ph] = e.get("at")
        elif e.get("action") == "end":
            t0 = _parse_iso_ts(opens.pop(ph, None))
            t1 = _parse_iso_ts(e.get("at"))
            if t0 is not None and t1 is not None and t1 >= t0:
                spans[ph]["span_ms"] += int((t1 - t0) * 1000)
            spans[ph]["subagents"] += int(e.get("subagents") or 0)
            spans[ph]["rounds"] += int(e.get("rounds") or 0)
    timing = {}
    for t in ledger.get("timing") or []:
        if t.get("measured"):
            ph = t.get("phase") or "?"
            timing[ph] = timing.get(ph, 0) + int(t.get("elapsed_ms") or 0)
    return order, spans, timing


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
    banner = []
    if ledger.get("acknowledged"):
        banner += ["> ⚠ **本 run 已由用户确认放弃**：%s（批准消息 hash %s…，记于 %s）。"
                   "放弃只影响 hook/CI 是否阻断，**不改变下面任何一条结论**，本 run 也永远不会有 receipt。"
                   % (ledger.get("acknowledged_reason"),
                      str(ledger.get("acknowledged_approval"))[:12],
                      ledger.get("acknowledged_at")), ""]
    if ledger.get("retired"):
        banner += ["> ⚠ **本 run 已退役**：%s；继任 run = %s。"
                  "退役只影响 hook/CI 是否阻断，**不改变下面任何一条结论**。"
                  % (ledger.get("retired_reason"), ledger.get("superseded_by")), ""]
    lines = ["# plan-test gate report", ""] + banner + [
             "RUN: %s" % ledger.get("run_id"),
             "STATE: %s" % ("SHIPPABLE" if shippable else "BLOCKED"),
             "TESTED HEAD: %s" % ((ledger.get("runtime_attestation") or {}).get("head")
                                  or (ledger.get("baseline") or {}).get("head")),
             "GATE RECEIPT: %s" % (receipt.get("content_digest") if (receipt and shippable) else "无（不得宣布 SHIP）"),
             ""]
    lines += [
        "## 身份说明（tested vs delivery，读 receipt 前必看）",
        "- TESTED HEAD 是**测试时**的代码提交；把本 run-dir 的账本/截图/receipt 提交进仓库",
        "  的后续提交（evidence-only descendant）**不改变被测内容指纹**，receipt 依然有效。",
        "- 所以「receipt 的 head 早于仓库最终 HEAD」可以是完全合法的状态——判定依据是",
        "  内容指纹（排除下方声明范围），不是提交号。若 tested HEAD 之后还改了任何非 run-dir",
        "  文件，validator 会以 TESTED_RUNTIME_MISMATCH / RETEST_REQUIRED_AFTER_CHANGE 拦截。",
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
    approvals = ledger.get("approvals") or []
    if approvals:
        lines.append("## 用户批准记录")
        for a in approvals:
            lines.append("- %s｜%s｜消息 hash %s…｜%s" % (
                a.get("recorded_at"), a.get("kind"),
                str(a.get("message_sha256"))[:12], a.get("note") or ""))
        lines.append("")
    evidence_summary = summarize_evidence(ledger)
    lines.append("## Evidence 计数（引用不等于独立证明）")
    lines.append("- evidence records: %d" % evidence_summary["records"])
    lines.append("- distinct artifacts（按 sha256）: %d" %
                 evidence_summary["distinct_artifacts"])
    lines.append("- distinct root runs: %d" % evidence_summary["distinct_root_runs"])
    lines.append("- shared artifact hashes: %d" %
                 len(evidence_summary["shared_artifact_sha256"]))
    lines.append("")
    imported = [e for e in (ledger.get("evidence") or []) if e.get("imported")]
    if imported:
        lines.append("## 导入的历史证据（产生于开账之前，chain of custody 见来源）")
        for e in imported:
            lines.append("- %s（来源：%s；文件时间 %s）" % (
                e.get("path"), e.get("imported_from"), e.get("file_mtime")))
        lines.append("")
    auditor = ledger.get("auditor") or {}
    lines.append("## 审计与账本完整性")
    if auditor:
        lines.append("- 审计：verdict=%s engine=%s（产物 %s）" % (
            auditor.get("verdict"), auditor.get("engine"), auditor.get("output_path")))
    else:
        lines.append("- 审计：**未执行**")
    _chain_break = integrity_check(ledger)
    lines.append("- 账本链：%s（%d 条写入，链首 %s）" % (
        "自洽" if not _chain_break else "**异常：%s**" % _chain_break,
        len(((ledger.get("integrity") or {}).get("log")) or []),
        ((((ledger.get("integrity") or {}).get("log")) or [{}])[0]).get("op")))
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
    order, spans, timing_by_phase = _phase_cost_rows(ledger)
    if order:
        lines.append("")
        lines.append("## 本 run 开销表（阶段 × 耗时 × 子代理数）")
        lines.append("")
        lines.append("| 阶段 | 事件跨度(min) | timing 实测(min) | 子代理派发 | 轮次 |")
        lines.append("|---|---|---|---|---|")
        for ph in order:
            s = spans[ph]
            lines.append("| %s | %.1f | %.1f | %d | %d |" % (
                ph, s["span_ms"] / 60000.0, timing_by_phase.get(ph, 0) / 60000.0,
                s["subagents"], s["rounds"]))
        lines.append("")
        lines.append("> 遥测口径：跨度=配对 phase-start/end 时间差合计；实测=该阶段 measured "
                     "timing；子代理/轮次=phase-end --subagents/--rounds 自报（未报=0）。"
                     "供 LEAN 档压缩效果比对，不参与门判定。")
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
    if ok:
        # 同仓还不够：继任者必须真的"承接"了这次的工作，否则就是拿一张无关的 receipt 背书。
        # 独立审计实测：S-1 fail 的 run 被一个唯一场景是「Z-9 完全无关」的同仓 run 退役即通过。
        succ = load_ledger_quiet(args.superseded_by) or {}
        my_acc = (ledger_self.get("acceptance") or {}).get("sha256")
        su_acc = (succ.get("acceptance") or {}).get("sha256")
        if my_acc and su_acc and my_acc != su_acc:
            ok, detail = False, ("继任 run 的 acceptance 与本 run 不同（%s… vs %s…）——"
                                 "不是同一份验收标准，承接不成立"
                                 % (str(my_acc)[:8], str(su_acc)[:8]))
        else:
            mine = {sc["scenario_id"] for sc in (ledger_self.get("scenarios") or [])
                    if sc.get("required")}
            # 继任者那边必须是 **required 且重算为 PASS** 的场景。只比 scenario_id 字符串集合
            # 会被"多写一行 required:false 且一次都没跑"绕过（第九轮独立审计实测：绕过成本从
            # "另建一个 run"降到"多写一行"）。
            succ_status = validate(args.superseded_by, succ, mode="render",
                                   fixture=bool(succ.get("fixture_only")))[1]["scenario_statuses"]
            theirs = {sc["scenario_id"] for sc in (succ.get("scenarios") or [])
                      if sc.get("required")
                      and succ_status.get(sc["scenario_id"]) == "PASS"}
            missing = sorted(mine - theirs)
            if missing:
                ok, detail = False, ("继任 run 未覆盖本 run 的 required 场景：%s——"
                                     "退役是把举证责任转移过去，不是让它消失"
                                     % ", ".join(missing[:5]))
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
    if ok:
        succ_dir = ledger.get("superseded_by") or ""
        succ = load_ledger_quiet(succ_dir) or {}
        mine = {sc["scenario_id"] for sc in (ledger.get("scenarios") or []) if sc.get("required")}
        # 读侧与写侧同口径复算——r5 的"读/写侧不对称"教训不能在新字段上重演
        succ_status = validate(succ_dir, succ, mode="render",
                               fixture=bool(succ.get("fixture_only")))[1]["scenario_statuses"] if succ else {}
        theirs = {sc["scenario_id"] for sc in (succ.get("scenarios") or [])
                  if sc.get("required") and succ_status.get(sc["scenario_id"]) == "PASS"}
        my_acc = (ledger.get("acceptance") or {}).get("sha256")
        su_acc = (succ.get("acceptance") or {}).get("sha256")
        if my_acc and su_acc and my_acc != su_acc:
            print("INVALID: 继任 run 的 acceptance 与本 run 不同")
            sys.exit(1)
        if mine - theirs:
            ok, detail = False, "继任 run 未覆盖本 run 的 required 场景：%s" % ", ".join(sorted(mine - theirs)[:5])
    if not ok:
        print("INVALID: %s" % detail)
        sys.exit(1)
    print("VALID superseded_by=%s receipt=%s" % (ledger.get("superseded_by"), str(detail)[:16]))
    sys.exit(0)


def cmd_acknowledge(args):
    """用户显式确认**放弃**这一轮验证——退役之外的第二条出口，代价是本 run 作废。

    为什么需要它（simple_harness r3–r8 实测的死锁）：`retire` 要求继任 run 已经 SHIPPABLE，
    可"继任轮正在跑"恰恰是最需要安静的阶段——历史轮每回合都被完整刷一遍诊断，而它们唯一的
    出口要等新轮跑完；新轮跑完的成本又被这些噪音抬高。于是"历史轮越多，跑完新轮越贵"。

    守卫（否则它就是下一个 `fixture_only`：加个字段就让门消失）：
      - 必须绑定**用户批准消息原文的 SHA-256**，与 record-approval 同口径——放弃一轮验证是
        用户的决定，不是代理的自决。局限也与 record-approval 相同：hash 由代理计算，挡的是
        "顺手放弃"，不是存心伪造；真正的锚点在 CI（见 hooks/README.md）。
      - 写入走 integrity 链（op=acknowledge），手写 acknowledged:true 会被 ack-status 判无效。
      - 作废是真的作废：validate 从此对本 run 报 RUN_ABANDONED（error），它永远拿不到
        receipt，也就不可能被 successor_receipt_status 认成别人的继任 run。
      - 不可撤销：要继续这一轮请换 run-dir 重新 init 并说明来由。
    """
    if not re.match(r"^[0-9a-f]{64}$", args.approval_hash or ""):
        die("--approval-hash 须为用户批准消息原文的 SHA-256（64 位十六进制）——"
            "放弃一轮验证必须能回溯到用户说过的具体一句话")
    ledger_self = load_ledger(args.run_dir)
    if ledger_self.get("acknowledged"):
        die("本 run 已确认放弃（%s）；放弃不可撤销，继续验证请换 run-dir 重新 init"
            % ledger_self.get("acknowledged_reason"))
    if load_receipt(args.run_dir) and not ledger_self.get("retired"):
        die("本 run 已有 receipt：它是通过的交付证据，不该用「放弃」注销。"
            "要作废 receipt 用 invalidate，要交棒给新轮用 retire。")

    def mutate(ledger):
        ledger["acknowledged"] = True
        ledger["acknowledged_reason"] = args.reason
        ledger["acknowledged_approval"] = args.approval_hash
        ledger["acknowledged_at"] = now_iso()

    _append(args.run_dir, mutate, op="acknowledge")
    print("ACKNOWLEDGED（本 run 作废，不再阻断收尾）: %s\n  绑定批准消息 hash: %s…"
          % (args.reason, args.approval_hash[:12]))


def cmd_ack_status(args):
    """放弃是否成立——供 hook / CI 调用，避免它们各自解读账本字段。

    exit 0 = 成立且账本自洽；1 = 不成立（含未放弃、链断裂、字段手写）。
    """
    ledger = load_ledger(args.run_dir)
    if not ledger.get("acknowledged"):
        print("NOT_ACKNOWLEDGED")
        sys.exit(1)
    tamper = integrity_check(ledger)
    if tamper:
        print("INVALID: %s" % tamper)
        sys.exit(1)
    if not any(e.get("op") == "acknowledge"
               for e in (ledger.get("integrity", {}).get("log") or [])):
        print("INVALID: integrity 链里没有 acknowledge 操作——acknowledged 字段是手写的")
        sys.exit(1)
    if not re.match(r"^[0-9a-f]{64}$", str(ledger.get("acknowledged_approval") or "")):
        print("INVALID: 缺少用户批准消息 hash")
        sys.exit(1)
    print("VALID acknowledged reason=%s approval=%s…"
          % (ledger.get("acknowledged_reason"), str(ledger.get("acknowledged_approval"))[:12]))
    sys.exit(0)


def cmd_summary(args):
    """一行摘要——给 hook / CI 压缩输出用，退出码与 `finalize --check-only` 同口径。

    动机：hook 此前对**每个** run-dir 打印完整诊断，7 个历史轮 = 单次 Stop 300+ 行 / ~10k
    token，且内容与本回合做了什么完全无关。代理真正需要的只有"哪个 run-dir 还没闭环"。
    """
    ledger = load_ledger(args.run_dir)
    fixture = bool(ledger.get("fixture_only"))
    diags, computed = validate(args.run_dir, ledger, mode="check-only", fixture=fixture)
    blockers = blocking(diags)
    bad = [sid for sid, st in sorted((computed.get("scenario_statuses") or {}).items())
           if st != "PASS"]
    codes = []
    for d in blockers:
        if d.code not in codes:
            codes.append(d.code)
    parts = ["%s: %s" % (ledger.get("run_id") or os.path.basename(args.run_dir.rstrip("/")),
                         "READY_FOR_AUDIT" if not blockers else computed["state"])]
    if blockers:
        parts.append("阻塞 %d 条（%s%s）" % (
            len(blockers), ", ".join(codes[:3]), "…" if len(codes) > 3 else ""))
    if bad:
        parts.append("未闭环场景 %d 个：%s%s" % (
            len(bad), ",".join(bad[:6]), "…" if len(bad) > 6 else ""))
    if ledger.get("fixture_only"):
        parts.append("FIXTURE-ONLY")
    if ledger.get("retired"):
        parts.append("已退役→%s" % ledger.get("superseded_by"))
    if ledger.get("acknowledged"):
        parts.append("已确认放弃")
    print(" | ".join(parts))
    sys.exit(0 if not blockers else 1)


def _stats_scan_ledgers(root):
    """按内容形状全仓找账本（判据与 hooks/gate_scan.py 一致：四键 JSON）。

    stats 是只读报表，不需要 ACTIVE/HALVES 段，所以不依赖 hooks/ 目录——skill 目录
    被单独复制安装（无 hooks/）时 stats 也要能跑。
    """
    def git_lines(extra):
        try:
            out = subprocess.run(["git", "-C", root, "ls-files"] + extra,
                                 capture_output=True, text=True, timeout=30)
        except (OSError, subprocess.TimeoutExpired):
            return []
        return out.stdout.splitlines() if out.returncode == 0 else []

    cands = [p for p in git_lines(["-c", "-o", "--exclude-standard"]) if p.endswith(".json")]
    for p in git_lines(["-o", "-i", "--exclude-standard", "--", "plans/"]):
        if p.endswith(".json") and "/verification/" in p.replace(os.sep, "/"):
            cands.append(p)
    seen, found = set(), []
    for rel in cands:
        norm = rel.replace(os.sep, "/")
        if norm in seen or "/fixtures/" in norm or norm.startswith("fixtures/"):
            continue
        seen.add(norm)
        path = os.path.join(root, rel)
        try:
            if os.path.getsize(path) > 8 * 1024 * 1024:
                continue
            with open(path, "r", encoding="utf-8") as f:
                obj = json.load(f)
        except (OSError, ValueError):
            continue
        if isinstance(obj, dict) and all(
                k in obj for k in ("schema_version", "run_id", "scenarios", "integrity")):
            found.append((norm, obj))
    return found


def _stats_last_activity(root, rel, ledger):
    """run 的最后活动时间：integrity 链最后一条的 at，退回文件 mtime。"""
    chain = (ledger.get("integrity") or {}).get("chain") or []
    ats = [e.get("at") for e in chain if isinstance(e, dict) and e.get("at")]
    if ats:
        return max(ats)
    try:
        return time.strftime("%Y-%m-%dT%H:%M:%S%z",
                             time.localtime(os.path.getmtime(os.path.join(root, rel))))
    except OSError:
        return ""


def cmd_stats(args):
    """规则退休的数据来源（T4）：哪些门在实际 run 里做过工，哪些从没拦过任何东西。

    口径（如实声明）：诊断没有历史留痕，本表是对每个账本**当前状态**按
    `finalize --check-only` 同一路径重算——它回答"今天这些门各拦着谁"，不是
    "历史上每次 CLI 调用各触发过什么"。已闭环的 run 通常贡献为零（HEAD 前移会带出
    TESTED_RUNTIME_MISMATCH 一类噪音，属数据本身的形状，不在这里修饰）。
    退休候选只是候选：退掉一个门是设计决定，须对照它当初防的逃逸（config.md 纪律：
    新增任何门必须声明它防的诊断码和复审日期）。
    """
    rows = _stats_scan_ledgers(args.root)
    runs, skipped = [], []
    for rel, ledger in rows:
        run_dir = os.path.join(args.root, os.path.dirname(rel))
        try:
            diags, _ = validate(run_dir, ledger, mode="check-only",
                                fixture=bool(ledger.get("fixture_only")))
        except (Exception, SystemExit) as e:  # 老 schema 账本可能算不动：如实跳过，不装作零触发
            skipped.append((rel, "%s: %s" % (type(e).__name__, e)))
            continue
        runs.append({
            "rel": rel,
            "run_id": ledger.get("run_id") or os.path.dirname(rel),
            "at": _stats_last_activity(args.root, rel, ledger),
            "receipt": load_receipt(run_dir) is not None,
            "codes": sorted({d.code for d in diags}),
            "n_diags": len(diags),
        })
    runs.sort(key=lambda r: r["at"])

    window = max(args.window, 1)
    recent = runs[-window:]
    stats = {}
    for r in runs:
        for c in r["codes"]:
            s = stats.setdefault(c, {"runs": 0, "last_at": "", "last_run": ""})
            s["runs"] += 1
            if r["at"] >= s["last_at"]:
                s["last_at"], s["last_run"] = r["at"], r["run_id"]
    known = list(CANONICAL_ORDER)
    for c in stats:  # 目录之外新造的码也要进表，不静默丢
        if c not in known:
            known.append(c)
    recent_codes = {c for r in recent for c in r["codes"]}
    candidates = [c for c in known if c not in recent_codes] if len(runs) >= window else []

    if args.as_json:
        print(json.dumps({
            "runs_scanned": len(runs), "runs_skipped": len(skipped),
            "receipts": sum(1 for r in runs if r["receipt"]),
            "window": window, "per_code": stats,
            "retirement_candidates": candidates,
            "skipped": [{"path": p, "error": e} for p, e in skipped],
        }, ensure_ascii=False, indent=1))
        return

    print("plan-test gate stats：%d 个 run 账本（receipt %d 个%s），退休窗口=最近 %d 个 run"
          % (len(runs), sum(1 for r in runs if r["receipt"]),
             "，%d 个解析失败跳过" % len(skipped) if skipped else "", window))
    print("口径：各账本当前状态按 check-only 重算（诊断无历史留痕），不是逐次调用的流水。")
    if not runs:
        print("没有可统计的账本。")
        return
    print()
    print("%-38s %8s %10s  %s" % ("诊断码", "触发run数", "最后触发", "最后所在 run"))
    for c in sorted(stats, key=lambda c: (-stats[c]["runs"], c)):
        s = stats[c]
        print("%-38s %8d %10s  %s" % (c, s["runs"], (s["last_at"] or "-")[:10], s["last_run"]))
    zero = [c for c in known if c not in stats]
    if zero:
        print()
        print("全史零触发（%d）：%s" % (len(zero), ", ".join(zero)))
    print()
    if len(runs) < window:
        print("退休候选：样本不足（%d 个 run < 窗口 %d），不出结论。" % (len(runs), window))
    elif candidates:
        print("退休候选（最近 %d 个 run 零触发，共 %d 个）：" % (window, len(candidates)))
        for c in candidates:
            print("  · %s" % c)
        print("退休前须对照该门当初防的逃逸与复审日期（config.md 门禁登记纪律）。")
    else:
        print("退休候选：无——最近 %d 个 run 里每个已知诊断码都触发过。" % window)
    for p, e in skipped:
        print("跳过 %s（%s）" % (p, e), file=sys.stderr)


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


def cmd_check_release_unit(args):
    """P0-1: Phase 3 开工前的 Release Unit 硬门。

    检查：
    1. acceptance.md 的 MUST AC 数量 <= threshold
    2. implementation-tasks.md 行数 <= threshold
    3. 高风险子系统标记 <= threshold

    超限 → exit 1，输出 RELEASE_UNIT_TOO_LARGE + 拆分建议。
    """
    # 读取 acceptance
    if not os.path.isfile(args.acceptance):
        die("acceptance 文件不存在: %s" % args.acceptance)

    with open(args.acceptance, "r", encoding="utf-8") as f:
        acceptance_content = f.read()

    # 只统计 markdown 表格中首列为正式 AC-ID 的 MUST 行。叙述/汇总行即使同时含
    # `|` 和 `MUST` 也不是 acceptance case，不能把 release unit 误判超限。
    must_count = 0
    for line in acceptance_content.split("\n"):
        ac_row = re.match(
            r"^\s*\|\s*(?:\*\*)?AC[-_][A-Za-z0-9][A-Za-z0-9._-]*(?:\*\*)?\s*\|",
            line,
            re.IGNORECASE,
        )
        if ac_row and ("必须" in line or "MUST" in line.upper()):
            must_count += 1

    # 读取 plan/implementation-tasks
    plan_lines = 0
    if os.path.isfile(args.plan):
        with open(args.plan, "r", encoding="utf-8") as f:
            plan_lines = len(f.readlines())

    # 统计高风险子系统（查找 [HIGH_RISK: ...] 或 [高风险: ...] 标记）
    high_risk_count = 0
    high_risk_items = []
    if os.path.isfile(args.plan):
        with open(args.plan, "r", encoding="utf-8") as f:
            content = f.read()
            # 匹配 [HIGH_RISK: xxx] 或 [高风险: xxx]
            matches = re.findall(r'\[(HIGH[_\-]RISK|高风险):\s*([^\]]+)\]', content, re.IGNORECASE)
            high_risk_items = list(set(m[1].strip() for m in matches))
            high_risk_count = len(high_risk_items)

    # 获取阈值
    max_ac = args.max_must_ac or DEFAULT_THRESHOLDS["must_ac_count"]
    max_lines = args.max_plan_lines or DEFAULT_THRESHOLDS["plan_lines"]
    max_risk = args.max_high_risk or DEFAULT_THRESHOLDS["high_risk_subsystems"]

    # 检查
    violations = []
    if must_count > max_ac:
        violations.append("MUST AC 数量: %d (上限 %d)" % (must_count, max_ac))
    if plan_lines > max_lines:
        violations.append("Plan 行数: %d (上限 %d)" % (plan_lines, max_lines))
    if high_risk_count > max_risk:
        violations.append("高风险子系统: %d (上限 %d) - %s" %
                         (high_risk_count, max_risk, ", ".join(high_risk_items[:5])))

    if violations:
        print("RELEASE_UNIT_TOO_LARGE")
        print("\n超限项目:")
        for v in violations:
            print("  - %s" % v)
        print("\n拆分建议:")
        print("  1. 按功能模块拆分为独立 slice（每个 slice ≤ %d MUST AC）" % max_ac)
        print("  2. 将高风险子系统隔离到独立 slice")
        print("  3. 按层次（contracts → implementation → integration）拆分")
        print("  4. 每个 slice 应有独立的 acceptance.md 和 verification/")
        sys.exit(1)

    print("RELEASE_UNIT_CHECK_PASS")
    print("  - MUST AC: %d / %d" % (must_count, max_ac))
    print("  - Plan 行数: %d / %d" % (plan_lines, max_lines))
    print("  - 高风险子系统: %d / %d" % (high_risk_count, max_risk))
    sys.exit(0)


def cmd_validate_release_unit(args):
    """P0-2: 检查 ledger 的 release_unit 字段是否正确声明。

    必须包含:
    - slice_id
    - parent_program
    - scope_hash

    缺失任一字段 → exit 1, RELEASE_UNIT_UNDECLARED。
    """
    ledger = load_ledger(args.run_dir)
    ru = ledger.get("release_unit")

    if not ru or not isinstance(ru, dict):
        print("RELEASE_UNIT_UNDECLARED")
        print("ERROR: ledger 缺少 release_unit 声明")
        print("\nrelease_unit 必须包含:")
        print("  - slice_id: 本次 slice 标识符（如 'T4.1-A'）")
        print("  - parent_program: 所属 program（如 'SDK-extraction'）")
        print("  - scope_hash: acceptance + plan 的内容 hash")
        sys.exit(1)

    required = ["slice_id", "parent_program", "scope_hash"]
    missing = [f for f in required if not ru.get(f)]

    if missing:
        print("RELEASE_UNIT_UNDECLARED")
        print("ERROR: release_unit 缺少必填字段: %s" % ", ".join(missing))
        print("\n当前 release_unit: %s" % json.dumps(ru, indent=2, ensure_ascii=False))
        sys.exit(1)

    print("RELEASE_UNIT_VALID")
    print("  - slice_id: %s" % ru["slice_id"])
    print("  - parent_program: %s" % ru["parent_program"])
    print("  - scope_hash: %s..." % ru["scope_hash"][:16])
    sys.exit(0)


def cmd_check_wip_limit(args):
    """P0-5: 检查未提交 WIP 是否超过安全阈值。

    运行 git diff --stat，统计:
    - tracked modified 行数
    - tracked modified 文件数

    超限 → exit 1, WIP_ACCUMULATION_UNSAFE。
    """
    if not os.path.isdir(args.repo_dir):
        die("仓库目录不存在: %s" % args.repo_dir)

    # 获取 git diff --stat
    try:
        result = subprocess.run(
            ["git", "-C", args.repo_dir, "diff", "--stat"],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            die("git diff 失败: %s" % result.stderr)

        stat_output = result.stdout
    except Exception as e:
        die("运行 git diff 失败: %s" % str(e))

    # 解析统计（最后一行通常是 "X files changed, Y insertions(+), Z deletions(-)"）
    lines = stat_output.strip().split("\n")
    if not lines or not lines[-1]:
        # 没有改动
        print("WIP_CHECK_PASS: 工作树干净")
        sys.exit(0)

    summary_line = lines[-1]
    files_changed = 0
    insertions = 0
    deletions = 0

    # 解析 "3 files changed, 245 insertions(+), 12 deletions(-)"
    match = re.search(r'(\d+)\s+files?\s+changed', summary_line)
    if match:
        files_changed = int(match.group(1))
    match = re.search(r'(\d+)\s+insertions?\(\+\)', summary_line)
    if match:
        insertions = int(match.group(1))
    match = re.search(r'(\d+)\s+deletions?\(-\)', summary_line)
    if match:
        deletions = int(match.group(1))

    total_lines = insertions + deletions

    # 检查阈值
    max_lines = args.max_lines or DEFAULT_THRESHOLDS["max_wip_lines"]
    max_files = args.max_files or DEFAULT_THRESHOLDS["max_wip_files"]

    violations = []
    if total_lines > max_lines:
        violations.append("未提交行数: %d (上限 %d)" % (total_lines, max_lines))
    if files_changed > max_files:
        violations.append("未提交文件数: %d (上限 %d)" % (files_changed, max_files))

    if violations:
        print("WIP_ACCUMULATION_UNSAFE")
        print("\n超限项目:")
        for v in violations:
            print("  - %s" % v)
        print("\n必须先 checkpoint:")
        print("  1. 提交当前已完成的独立功能（有测试、可 revert）")
        print("  2. 或拆分当前任务为更小的 slice")
        print("  3. 禁止在超大 WIP 上继续叠加改动")
        sys.exit(1)

    print("WIP_CHECK_PASS")
    print("  - 未提交行数: %d / %d" % (total_lines, max_lines))
    print("  - 未提交文件数: %d / %d" % (files_changed, max_files))
    sys.exit(0)


def cmd_check_ledger_progress(args):
    """P1-1: 检查 ledger 是否长时间无进展（零增长警告）。

    读取账本最后一次 runs/evidence/timing 写入时间，
    若距离当前时间 > MIN_PROGRESS_INTERVAL → 警告 LEDGER_STALLED。
    """
    ledger = load_ledger(args.run_dir)

    # 查找最后一次写入时间
    last_run_time = None
    last_evidence_time = None
    last_timing_time = None

    runs = ledger.get("runs") or []
    if runs:
        # 假设 runs 按时间顺序，取最后一条
        last_run = runs[-1]
        last_run_time = last_run.get("recorded_at")

    evidence = ledger.get("evidence") or []
    if evidence:
        last_evidence = evidence[-1]
        last_evidence_time = last_evidence.get("attached_at")

    timing = ledger.get("timing") or []
    if timing:
        last_timing = timing[-1]
        last_timing_time = last_timing.get("recorded_at")

    # 找最近的时间戳
    timestamps = [t for t in [last_run_time, last_evidence_time, last_timing_time] if t]
    if not timestamps:
        print("LEDGER_STALLED")
        print("ERROR: 账本完全无进展（runs=0, evidence=0, timing=0）")
        print("可能正在绕过 gate 或陷入空转，建议暂停检查")
        sys.exit(1)

    # 解析最近时间戳（ISO 8601 格式）
    def parse_iso(s):
        # 简化版解析 YYYY-MM-DDTHH:MM:SS+ZZZZ
        try:
            import datetime
            # 移除时区后缀
            s_clean = re.sub(r'[+-]\d{4}$', '', s)
            return datetime.datetime.fromisoformat(s_clean)
        except:
            return None

    last_times = [parse_iso(t) for t in timestamps]
    last_times = [t for t in last_times if t is not None]

    if not last_times:
        print("WARNING: 无法解析时间戳，跳过进度检查")
        sys.exit(0)

    import datetime
    most_recent = max(last_times)
    now = datetime.datetime.now()
    elapsed_minutes = (now - most_recent).total_seconds() / 60

    min_interval = args.min_interval_minutes or MIN_PROGRESS_INTERVAL_MINUTES

    if elapsed_minutes > min_interval:
        print("LEDGER_STALLED")
        print("WARNING: 账本已 %.1f 分钟无进展（阈值 %d 分钟）" % (elapsed_minutes, min_interval))
        print("  - runs: %d" % len(runs))
        print("  - evidence: %d" % len(evidence))
        print("  - timing: %d" % len(timing))
        print("\n可能原因:")
        print("  1. 正在绕过机器门禁")
        print("  2. 陷入空转或无效循环")
        print("  3. 执行暂停但未明确标记")
        sys.exit(1)

    print("LEDGER_PROGRESS_OK")
    print("  - 最后进展: %.1f 分钟前" % elapsed_minutes)
    print("  - runs: %d, evidence: %d, timing: %d" % (len(runs), len(evidence), len(timing)))
    sys.exit(0)


def cmd_record_plan_defect(args):
    """P0-4: 记录 A2 plan defect 事件。

    在 Phase 3 执行期间发现 plan 有缺陷需要回炉时调用。
    写入 plan_defects[] 数组，生成唯一 event_id，记录到 integrity chain。
    """
    ledger = load_ledger(args.run_dir)

    # 生成 event_id
    existing_defects = ledger.get("plan_defects") or []
    event_id = "a2-%03d" % (len(existing_defects) + 1)

    # 当前时间戳（ISO 8601）
    import datetime
    now = datetime.datetime.now().astimezone()
    timestamp = now.isoformat()

    # 解析 affected_tasks
    affected_tasks = [t.strip() for t in args.affected_tasks.split(",") if t.strip()]

    defect_record = {
        "event_id": event_id,
        "occurred_at": timestamp,
        "affected_tasks": affected_tasks,
        "defect_type": args.defect_type,
        "description": args.description,
        "resolution": None,
        "resolved_at": None
    }

    def mutate(ledger):
        if "plan_defects" not in ledger:
            ledger["plan_defects"] = []
        ledger["plan_defects"].append(defect_record)

    _append(args.run_dir, mutate, op="record_plan_defect")

    # 重新加载以获取最新状态
    ledger = load_ledger(args.run_dir)

    print("PLAN_DEFECT_RECORDED")
    print("  - Event ID: %s" % event_id)
    print("  - 类型: %s" % args.defect_type)
    print("  - 影响任务: %s" % ", ".join(affected_tasks))
    print("  - 描述: %s" % args.description)
    print("\n累计未解决 A2 事件: %d / %d" % (
        len([d for d in ledger["plan_defects"] if not d.get("resolved_at")]),
        MAX_A2_EVENTS
    ))
    sys.exit(0)


def cmd_check_plan_stability(args):
    """P0-4: 检查 plan 稳定性（累计 A2 事件数）。

    统计未解决的 A2 事件数量。
    若 >= MAX_A2_EVENTS (3) → exit 1, PLAN_UNSTABLE。
    """
    ledger = load_ledger(args.run_dir)
    defects = ledger.get("plan_defects") or []

    # 统计未解决的
    unresolved = [d for d in defects if not d.get("resolved_at")]
    unresolved_count = len(unresolved)

    if unresolved_count >= MAX_A2_EVENTS:
        print("PLAN_UNSTABLE")
        print("\nPhase 2 未真正收敛，已累计 %d 次 plan defect（上限 %d）：\n" % (
            unresolved_count, MAX_A2_EVENTS
        ))

        for i, defect in enumerate(unresolved, 1):
            status = "已解决" if defect.get("resolved_at") else "未解决"
            print("%d. [%s] %s: %s" % (
                i, defect["event_id"], defect["defect_type"], defect["description"]
            ))
            print("   - 影响任务: %s" % ", ".join(defect["affected_tasks"]))
            print("   - 发生时间: %s" % defect["occurred_at"])
            print("   - 状态: %s" % status)
            if defect.get("resolution"):
                print("   - 解决方案: %s" % defect["resolution"])
            print()

        print("建议:")
        print("  - 禁止继续叠加 WIP")
        print("  - 提交或 stash 当前改动")
        print("  - 回退 phase-2 重新迭代 plan")
        print("  - 使用 reset-plan-defects 清空 A2 计数后才能恢复 phase-3")
        sys.exit(1)

    # 显示所有 defects（包括已解决的）
    print("PLAN_STABILITY_OK")
    print("  - 总计 A2 事件: %d" % len(defects))
    print("  - 未解决: %d / %d" % (unresolved_count, MAX_A2_EVENTS))
    if defects:
        print("\n历史记录:")
        for defect in defects:
            status = "✓ 已解决" if defect.get("resolved_at") else "✗ 未解决"
            print("  [%s] %s (%s)" % (defect["event_id"], defect["defect_type"], status))
    sys.exit(0)


def cmd_resolve_plan_defect(args):
    """P0-4: 标记某个 A2 事件已解决。"""
    ledger = load_ledger(args.run_dir)
    defects = ledger.get("plan_defects") or []

    # 查找目标 event
    target = None
    for d in defects:
        if d["event_id"] == args.event_id:
            target = d
            break

    if not target:
        die("找不到 event_id: %s" % args.event_id)

    if target.get("resolved_at"):
        die("事件 %s 已经标记为解决" % args.event_id)

    # 标记解决
    import datetime
    now = datetime.datetime.now().astimezone()

    def mutate(ledger):
        for d in ledger.get("plan_defects", []):
            if d["event_id"] == args.event_id:
                d["resolved_at"] = now.isoformat()
                d["resolution"] = args.resolution
                break

    _append(args.run_dir, mutate, op="resolve_plan_defect")

    print("PLAN_DEFECT_RESOLVED")
    print("  - Event ID: %s" % args.event_id)
    print("  - 解决方案: %s" % args.resolution)
    sys.exit(0)


def cmd_reset_plan_defects(args):
    """P0-4: 清空 A2 计数（需要用户批准）。"""
    ledger = load_ledger(args.run_dir)
    defects = ledger.get("plan_defects") or []

    if not defects:
        print("无需重置，当前没有 A2 事件记录")
        sys.exit(0)

    # 验证 approval hash 格式
    if not re.match(r'^[a-f0-9]{64}$', args.approval_hash):
        die("approval_hash 必须是 64 位十六进制 SHA-256")

    # 归档旧记录
    import datetime
    now = datetime.datetime.now().astimezone()
    archive_entry = {
        "archived_at": now.isoformat(),
        "reason": args.reason,
        "approval_hash": args.approval_hash,
        "defects": defects
    }

    def mutate(ledger):
        if "plan_defects_history" not in ledger:
            ledger["plan_defects_history"] = []
        ledger["plan_defects_history"].append(archive_entry)
        ledger["plan_defects"] = []

    _append(args.run_dir, mutate, op="reset_plan_defects")

    print("PLAN_DEFECTS_RESET")
    print("  - 已清空 %d 条 A2 事件" % len(defects))
    print("  - 理由: %s" % args.reason)
    print("  - 批准 hash: %s..." % args.approval_hash[:16])
    print("\n已归档到 plan_defects_history，可重新进入 phase-3")
    sys.exit(0)


def _challenge_loop(ledger, loop_id):
    for loop in ledger.get("challenge_loops") or []:
        if loop.get("loop_id") == loop_id:
            return loop
    return None


def _read_json_file(path, label):
    if not path or not os.path.isfile(path):
        die("%s 文件不存在: %s" % (label, path))
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError) as exc:
        die("无法解析 %s: %s" % (label, exc))


def _validate_assurance_contract(contract):
    errors = []
    if not isinstance(contract, dict):
        return ["contract 须为 object"]
    allowed = {
        "profile", "acceptance_ids", "protected_assets", "trusted_assumptions",
        "in_scope_failures", "in_scope_adversaries", "out_of_scope_conditions",
        "maximum_acceptable_impact",
    }
    extra = sorted(set(contract) - allowed)
    if extra:
        errors.append("未知字段: %s" % ", ".join(extra))
    profile = contract.get("profile")
    if profile not in ASSURANCE_PROFILES:
        errors.append("profile=%r 非法" % profile)
    acceptance_ids = contract.get("acceptance_ids")
    if (not isinstance(acceptance_ids, list) or not acceptance_ids
            or any(not isinstance(v, str) or not v.strip() for v in acceptance_ids)):
        errors.append("acceptance_ids 须为非空字符串数组")
    impact = contract.get("maximum_acceptable_impact")
    if not isinstance(impact, str) or not impact.strip():
        errors.append("maximum_acceptable_impact 须为非空字符串")
    seen = set()
    for key in ("protected_assets", "trusted_assumptions", "in_scope_failures",
                "in_scope_adversaries", "out_of_scope_conditions"):
        values = contract.get(key)
        if not isinstance(values, list):
            errors.append("%s 须为数组" % key)
            continue
        for i, item in enumerate(values):
            if not isinstance(item, dict) or set(item) != {"id", "description"}:
                errors.append("%s[%d] 须只含 id/description" % (key, i))
                continue
            iid = item.get("id")
            if not isinstance(iid, str) or not iid.strip():
                errors.append("%s[%d].id 须为非空字符串" % (key, i))
            elif iid in seen:
                errors.append("assurance id 重复: %s" % iid)
            else:
                seen.add(iid)
            if not isinstance(item.get("description"), str) or not item["description"].strip():
                errors.append("%s[%d].description 须为非空字符串" % (key, i))
    return errors


def _assurance_snapshot(path, contract, acceptance_sha256):
    scope_view = {
        "acceptance_ids": contract["acceptance_ids"],
        "protected_assets": contract["protected_assets"],
        "maximum_acceptable_impact": contract["maximum_acceptable_impact"],
    }
    risk_view = {
        "profile": contract["profile"],
        "trusted_assumptions": contract["trusted_assumptions"],
        "in_scope_failures": contract["in_scope_failures"],
        "in_scope_adversaries": contract["in_scope_adversaries"],
        "out_of_scope_conditions": contract["out_of_scope_conditions"],
    }
    return {
        "path": os.path.abspath(path),
        "sha256": sha256_file(path),
        "scope_hash": canonical_digest({
            "acceptance_sha256": acceptance_sha256,
            "contract_scope": scope_view,
        }),
        "threat_model_hash": canonical_digest(risk_view),
        "profile": contract["profile"],
        "acceptance_sha256": acceptance_sha256,
        "acceptance_ids": list(contract["acceptance_ids"]),
        "assurance_ids": sorted(
            item["id"] for key in ("protected_assets", "trusted_assumptions",
                                    "in_scope_failures", "in_scope_adversaries",
                                    "out_of_scope_conditions")
            for item in contract[key]),
        "recorded_at": now_iso(),
    }


def _active_contract_snapshot(loop):
    snapshots = loop.get("contract_snapshots") or []
    return snapshots[-1] if snapshots else None


def _active_acceptance_snapshot(loop):
    snapshots = loop.get("acceptance_snapshots") or []
    return snapshots[-1] if snapshots else None


def _validate_finding_payload(payload, round_no, loop):
    errors = []
    if not isinstance(payload, dict):
        return None, ["findings 根节点须为 object"]
    allowed_root = {"review_mode", "coverage", "findings"}
    extra = sorted(set(payload) - allowed_root)
    if extra:
        errors.append("findings 根节点未知字段: %s" % ", ".join(extra))
    mode = payload.get("review_mode")
    if mode not in CHALLENGE_REVIEW_MODES:
        errors.append("review_mode=%r 非法" % mode)
    if round_no == 1:
        if mode != "breadth":
            errors.append("BREADTH_REVIEW_INCOMPLETE: 第一轮 review_mode 必须为 breadth")
        coverage = payload.get("coverage")
        if (not isinstance(coverage, dict) or set(coverage) != BREADTH_COVERAGE_KEYS
                or not all(v is True for v in coverage.values())):
            errors.append("BREADTH_REVIEW_INCOMPLETE: coverage matrix 必须完整且全部 reviewed")
    elif mode == "breadth":
        errors.append("第二轮起不得重复 breadth；使用 diff，重大 reset 后使用 consolidated")
    elif round_no > 1:
        previous_round = round_no - 1
        major_change = any(
            e.get("action") in {"architecture-reset", "scope-change-approved"}
            and int(e.get("after_round") or 0) >= previous_round
            for e in loop.get("control_events") or [])
        if major_change and mode != "consolidated":
            errors.append("CONSOLIDATED_REVIEW_REQUIRED: architecture/scope change 后须完整复核")
        elif mode == "consolidated" and not major_change:
            errors.append("CONSOLIDATED_REVIEW_UNAUTHORIZED: 无 architecture/scope change 事件")
    if mode == "consolidated":
        coverage = payload.get("coverage")
        if (not isinstance(coverage, dict) or set(coverage) != BREADTH_COVERAGE_KEYS
                or not all(v is True for v in coverage.values())):
            errors.append("BREADTH_REVIEW_INCOMPLETE: consolidated review 必须重做 coverage matrix")
    findings = payload.get("findings")
    if not isinstance(findings, list):
        errors.append("findings 须为数组")
        return None, errors
    snap = _active_contract_snapshot(loop) or {}
    acceptance_ids = set(snap.get("acceptance_ids") or [])
    assurance_ids = set(snap.get("assurance_ids") or [])
    ids = set()
    normalized = []
    allowed_item = {
        "id", "severity", "scope_relation", "origin", "violated_acceptance_ids",
        "assurance_contract_ids", "evidence", "status", "root_cause",
        "why_not_found_in_round_one",
    }
    for i, item in enumerate(findings):
        where = "findings[%d]" % i
        if not isinstance(item, dict):
            errors.append("%s 须为 object" % where)
            continue
        unknown = sorted(set(item) - allowed_item)
        if unknown:
            errors.append("%s 未知字段: %s" % (where, ", ".join(unknown)))
        required = allowed_item - {"why_not_found_in_round_one"}
        missing = sorted(required - set(item))
        if missing:
            errors.append("%s 缺少字段: %s" % (where, ", ".join(missing)))
            continue
        fid = item.get("id")
        valid_fid = isinstance(fid, str) and bool(re.match(r"^[a-z][a-z0-9-]{2,63}$", fid))
        if not valid_fid:
            errors.append("%s.id 须匹配 ^[a-z][a-z0-9-]{2,63}$" % where)
        elif fid in ids:
            errors.append("%s.id 在本轮重复: %s" % (where, fid))
        if valid_fid:
            ids.add(fid)
        severity = item.get("severity")
        scope = item.get("scope_relation")
        origin = item.get("origin")
        status = item.get("status")
        if severity not in FINDING_SEVERITIES:
            errors.append("%s.severity=%r 非法" % (where, severity))
        if scope not in FINDING_SCOPE_RELATIONS:
            errors.append("%s.scope_relation=%r 非法" % (where, scope))
        if origin not in FINDING_ORIGINS:
            errors.append("%s.origin=%r 非法" % (where, origin))
        if status not in FINDING_STATUSES:
            errors.append("%s.status=%r 非法" % (where, status))
        if scope == "out-of-scope" and status != "advisory":
            errors.append("%s out-of-scope finding 必须是 advisory" % where)
        if scope != "out-of-scope" and status == "advisory":
            errors.append("%s in-scope/proposal finding 不能标 advisory" % where)
        acs = item.get("violated_acceptance_ids")
        aids = item.get("assurance_contract_ids")
        if not isinstance(acs, list) or any(not isinstance(v, str) for v in acs):
            errors.append("%s.violated_acceptance_ids 须为字符串数组" % where)
            acs = []
        if not isinstance(aids, list) or any(not isinstance(v, str) for v in aids):
            errors.append("%s.assurance_contract_ids 须为字符串数组" % where)
            aids = []
        if severity in ("P0", "P1") and scope in ("in-scope", "scope-change-proposal"):
            if not acs or not aids:
                errors.append("%s P0/P1 缺少 AC 或 assurance binding" % where)
        unknown_ac = sorted(set(acs) - acceptance_ids)
        unknown_assurance = sorted(set(aids) - assurance_ids)
        if unknown_ac:
            errors.append("%s 引用了未知 acceptance ID: %s" % (where, ", ".join(unknown_ac)))
        if unknown_assurance:
            errors.append("%s 引用了未知 assurance ID: %s" % (
                where, ", ".join(unknown_assurance)))
        for key in ("evidence", "root_cause"):
            if not isinstance(item.get(key), str) or not item[key].strip():
                errors.append("%s.%s 须为非空字符串" % (where, key))
        if (valid_fid and round_no > 1 and origin == "pre-existing" and fid not in {
                f.get("id") for r in loop.get("rounds") or [] for f in r.get("findings") or []}):
            why = item.get("why_not_found_in_round_one")
            if not isinstance(why, str) or not why.strip():
                errors.append("LATE_FINDING_UNEXPLAINED: %s 是第二轮后的 pre-existing 新 finding" % fid)
        normalized.append(item)
    return {"review_mode": mode, "coverage": payload.get("coverage"),
            "findings": normalized}, errors


def _latest_finding_states(loop):
    latest = {}
    for round_record in loop.get("rounds") or []:
        for finding in round_record.get("findings") or []:
            latest[finding["id"]] = (round_record["round"], finding)
    return latest


def _has_control(loop, action, minimum_round=0):
    return any(e.get("action") == action and int(e.get("after_round") or 0) >= minimum_round
               for e in loop.get("control_events") or [])


def _challenge_state(loop):
    rounds = loop.get("rounds") or []
    if not rounds:
        return "ACTIVE"
    if loop.get("orchestration") == "clustered":
        clusters = loop.get("challenge_clusters")
        if clusters is None:
            return "SPECIALIST_CHALLENGE_REQUIRED"
        specialist_by_cluster = {
            item.get("cluster_id"): item
            for item in (loop.get("specialist_challenges") or [])
        }
        incomplete = []
        for cluster in clusters:
            if not cluster.get("specialist_required", True):
                continue
            item = specialist_by_cluster.get(cluster.get("cluster_id"))
            if not item:
                incomplete.append(cluster.get("cluster_id"))
                continue
            if item.get("status") == "waived" and not item.get("waiver_reason"):
                incomplete.append(cluster.get("cluster_id"))
            elif item.get("status") not in {"completed", "waived"}:
                incomplete.append(cluster.get("cluster_id"))
        if incomplete:
            return "SPECIALIST_CHALLENGE_REQUIRED"
        if not loop.get("synthesis"):
            return "SYNTHESIS_REQUIRED"
        synthesis_round = int((loop.get("synthesis") or {}).get("after_round") or 0)
        if len(rounds) <= synthesis_round:
            return "CLOSURE_REVIEW_REQUIRED"
    controls = loop.get("control_events") or []
    for event in reversed(controls):
        if event.get("action") in {"scope-audit", "user-review"}:
            if event.get("outcome") == "scope-change" and not _has_control(
                    loop, "scope-change-approved", int(event.get("after_round") or 0)):
                return "USER_SCOPE_APPROVAL_REQUIRED"
            if event.get("outcome") == "architecture-reset" and not _has_control(
                    loop, "architecture-reset", int(event.get("after_round") or 0)):
                return "ARCHITECTURE_RESET_REQUIRED"
            break
    latest = _latest_finding_states(loop)
    open_blockers = [
        (round_no, f) for round_no, f in latest.values()
        if f.get("status") == "open" and f.get("scope_relation") == "in-scope"
        and f.get("severity") in ("P0", "P1")
    ]
    proposals = [
        (round_no, f) for round_no, f in latest.values()
        if f.get("status") == "open" and f.get("scope_relation") == "scope-change-proposal"
    ]
    if proposals:
        newest = max(r for r, _f in proposals)
        if not _has_control(loop, "scope-change-approved", newest):
            return "USER_SCOPE_APPROVAL_REQUIRED"
    if len(rounds) >= 2:
        last_two = rounds[-2:]
        if all(any(f.get("severity") == "P0" and f.get("origin") == "patch-induced"
                       and f.get("scope_relation") == "in-scope" and f.get("status") == "open"
                       for f in r.get("findings") or []) for r in last_two):
            if not _has_control(loop, "architecture-reset", rounds[-1]["round"]):
                return "ARCHITECTURE_RESET_REQUIRED"
    limits = loop.get("limits") or {}
    current = rounds[-1]
    if open_blockers and len(rounds) >= int(limits.get("hard", PLAN_CHALLENGE_HARD_LIMIT)):
        return "BLOCKED"
    if (current.get("new_critical_findings", 0) > 0
            and current["round"] >= int(limits.get("user_review", PLAN_CHALLENGE_USER_REVIEW_ROUND))
            and not _has_control(loop, "user-review")):
        return "USER_REVIEW_REQUIRED"
    if (current.get("new_critical_findings", 0) > 0
            and current["round"] >= int(limits.get("soft", PLAN_CHALLENGE_SOFT_LIMIT))
            and not (_has_control(loop, "scope-audit")
                     or _has_control(loop, "architecture-reset"))):
        return "SCOPE_AUDIT_REQUIRED"
    if open_blockers:
        return "CONTINUE"
    return "CONVERGED"


def cmd_start_challenge_loop(args):
    """冻结 assurance contract 并启动可审计的挑战循环。"""
    ledger = load_ledger(args.run_dir)
    if not os.path.isfile(args.target_file):
        die("目标文件不存在: %s" % args.target_file)
    acceptance = ledger.get("acceptance") or {}
    acceptance_path = acceptance.get("path")
    acceptance_hash = acceptance.get("sha256")
    if (not acceptance_path or not acceptance_hash
            or not os.path.isfile(acceptance_path)):
        die("ACCEPTANCE_REQUIRED: init manifest 必须冻结可读取的 acceptance_file")
    if sha256_file(acceptance_path) != acceptance_hash:
        die("ACCEPTANCE_CHANGED: acceptance hash 与 init 快照不一致")
    contract = _read_json_file(args.assurance_contract, "assurance contract")
    contract_errors = _validate_assurance_contract(contract)
    if contract_errors:
        die("SCHEMA_INVALID: assurance contract: %s" % "; ".join(contract_errors))
    baseline_hash = args.baseline_hash or sha256_file(args.target_file)
    if baseline_hash != sha256_file(args.target_file):
        die("BASELINE_HASH_MISMATCH: --baseline-hash 与目标文件不一致")
    loop_count = len(ledger.get("challenge_loops") or []) + 1
    loop_id = "%s-%03d" % (args.loop_type, loop_count)
    loop_record = {
        "loop_id": loop_id,
        "loop_type": args.loop_type,
        "target_file": os.path.abspath(args.target_file),
        "baseline_hash": baseline_hash,
        "started_at": now_iso(),
        "limits": {
            "soft": PLAN_CHALLENGE_SOFT_LIMIT,
            "user_review": PLAN_CHALLENGE_USER_REVIEW_ROUND,
            "hard": PLAN_CHALLENGE_HARD_LIMIT,
        },
        "acceptance_snapshots": [{
            "path": os.path.abspath(acceptance_path),
            "sha256": acceptance_hash,
            "recorded_at": now_iso(),
        }],
        "contract_snapshots": [
            _assurance_snapshot(args.assurance_contract, contract, acceptance_hash)
        ],
        "rounds": [],
        "control_events": [],
        "orchestration": args.orchestration,
        "specialist_challenges": [],
        "status": "ACTIVE",
    }

    def mutate(current):
        current.setdefault("challenge_loops", []).append(loop_record)

    _append(args.run_dir, mutate, op="start_challenge_loop")
    print(loop_id)
    sys.exit(0)


def cmd_check_loop_limit(args):
    ledger = load_ledger(args.run_dir)
    loop = _challenge_loop(ledger, args.loop_id)
    if not loop:
        die("找不到 loop_id: %s" % args.loop_id)
    state = _challenge_state(loop)
    rounds = len(loop.get("rounds") or [])
    hard = int((loop.get("limits") or {}).get("hard", PLAN_CHALLENGE_HARD_LIMIT))
    print("LOOP_STATE: %s" % state)
    print("  - 当前轮次: %d / %d" % (rounds, hard))
    if state in {"SPECIALIST_CHALLENGE_REQUIRED", "SYNTHESIS_REQUIRED",
                 "CLOSURE_REVIEW_REQUIRED", "SCOPE_AUDIT_REQUIRED", "ARCHITECTURE_RESET_REQUIRED",
                 "USER_REVIEW_REQUIRED", "USER_SCOPE_APPROVAL_REQUIRED", "BLOCKED"}:
        sys.exit(1)
    print("LOOP_LIMIT_OK")
    sys.exit(0)


def cmd_record_challenge_round(args):
    ledger = load_ledger(args.run_dir)
    loop = _challenge_loop(ledger, args.loop_id)
    if not loop:
        die("找不到 loop_id: %s" % args.loop_id)
    expected_round = len(loop.get("rounds") or []) + 1
    if args.round != expected_round:
        die("ROUND_SEQUENCE_INVALID: 期望 round=%d，收到 %d" % (expected_round, args.round))
    if (args.round > 1 and loop.get("orchestration") == "clustered"
            and not loop.get("synthesis")):
        die("CHALLENGE_SYNTHESIS_REQUIRED: clustered loop 必须先完成专项挑战与 synthesis，"
            "再记录 closure diff round")
    if not os.path.isfile(loop.get("target_file") or ""):
        die("目标文件不存在: %s" % loop.get("target_file"))
    actual_hash = sha256_file(loop["target_file"])
    if args.plan_hash != actual_hash:
        die("PLAN_HASH_MISMATCH: --plan-hash 与 target-file 当前内容不一致")
    if args.round > 1:
        prior_hash = loop["rounds"][-1]["plan_hash"]
        if args.based_on_plan_hash != prior_hash:
            die("PLAN_BASE_HASH_INVALID: based-on=%s 期望=%s" % (
                args.based_on_plan_hash, prior_hash))
    active_contract = _active_contract_snapshot(loop)
    active_acceptance = _active_acceptance_snapshot(loop)
    if (not active_acceptance or not os.path.isfile(active_acceptance.get("path") or "")
            or sha256_file(active_acceptance["path"]) != active_acceptance["sha256"]):
        die("ACCEPTANCE_CHANGED: acceptance hash 变化且没有用户批准事件")
    if (not active_contract or not os.path.isfile(active_contract.get("path") or "")
            or sha256_file(active_contract["path"]) != active_contract["sha256"]):
        die("ASSURANCE_CONTRACT_CHANGED: contract hash 变化且没有用户批准事件")
    payload = _read_json_file(args.findings, "findings")
    normalized, errors = _validate_finding_payload(payload, args.round, loop)
    if errors:
        die("SCHEMA_INVALID: %s" % "; ".join(errors))
    if args.round > 1 and loop.get("orchestration") == "clustered":
        synthesis_payload = (loop.get("synthesis") or {}).get("payload") or {}
        canonical_ids = {f.get("id") for f in synthesis_payload.get("canonical_findings", [])}
        closure_ids = {f.get("id") for f in normalized.get("findings") or []}
        if closure_ids != canonical_ids:
            die("CLOSURE_FINDING_COVERAGE_INVALID: closure 必须逐 ID 复核完整 canonical finding 集")
        if (any(d.get("action") == "plan-change"
                for d in synthesis_payload.get("decisions") or [] if isinstance(d, dict))
                and args.plan_hash == loop["rounds"][-1]["plan_hash"]):
            die("CLOSURE_PLAN_UNCHANGED: synthesis 声明 plan-change，但 target plan hash 未变化")
    historical_ids = {
        f.get("id") for r in loop.get("rounds") or [] for f in r.get("findings") or []
    }
    new_critical = sum(
        1 for f in normalized["findings"]
        if f["id"] not in historical_ids and f["severity"] in ("P0", "P1")
        and f["scope_relation"] == "in-scope" and f["status"] == "open")
    advisory = sum(1 for f in normalized["findings"]
                   if f["scope_relation"] == "out-of-scope")
    round_record = {
        "round": args.round,
        "review_mode": normalized["review_mode"],
        "coverage": normalized.get("coverage"),
        "plan_hash": args.plan_hash,
        "based_on_plan_hash": args.based_on_plan_hash,
        "scope_hash": active_contract["scope_hash"],
        "threat_model_hash": active_contract["threat_model_hash"],
        "findings": normalized["findings"],
        "new_critical_findings": new_critical,
        "reviewer_verdict": args.verdict,
        "timestamp": now_iso(),
    }
    prospective = json.loads(json.dumps(loop))
    prospective["rounds"].append(round_record)
    state = _challenge_state(prospective)

    def mutate(current):
        target = _challenge_loop(current, args.loop_id)
        if not target or len(target.get("rounds") or []) + 1 != args.round:
            die("ROUND_SEQUENCE_INVALID: 并发写入导致轮次已变化")
        target.setdefault("rounds", []).append(round_record)
        target["status"] = state

    _append(args.run_dir, mutate, op="record_challenge_round")
    print("CHALLENGE_ROUND_RECORDED")
    print("NEW_CRITICAL_FINDINGS: %d" % new_critical)
    print("ADVISORY_FINDINGS: %d" % advisory)
    print("LOOP_STATE: %s" % state)
    if args.verdict:
        print("REVIEWER_VERDICT_IGNORED: reviewer=%s; gate derives state from findings" % args.verdict)
    if state in {"SCOPE_AUDIT_REQUIRED", "ARCHITECTURE_RESET_REQUIRED",
                 "USER_REVIEW_REQUIRED", "USER_SCOPE_APPROVAL_REQUIRED", "BLOCKED"}:
        sys.exit(1)
    sys.exit(0)


def _validate_challenge_clusters(payload):
    if not isinstance(payload, dict):
        return None, ["cluster payload 须为 object"]
    allowed = {"primary_contradiction", "challenge_clusters"}
    extra = sorted(set(payload) - allowed)
    errors = ["cluster payload 未知字段: %s" % ", ".join(extra)] if extra else []
    contradiction = payload.get("primary_contradiction")
    if not isinstance(contradiction, dict):
        errors.append("primary_contradiction 须为 object")
    else:
        required_contradiction = {"id", "summary", "acceptance_ids"}
        missing = sorted(required_contradiction - set(contradiction))
        if missing:
            errors.append("primary_contradiction 缺少字段: %s" % ", ".join(missing))
        if not isinstance(contradiction.get("acceptance_ids"), list):
            errors.append("primary_contradiction.acceptance_ids 须为数组")
    clusters = payload.get("challenge_clusters")
    if not isinstance(clusters, list):
        errors.append("challenge_clusters 须为数组")
        return None, errors
    seen = set()
    normalized = []
    for i, item in enumerate(clusters):
        where = "challenge_clusters[%d]" % i
        if not isinstance(item, dict):
            errors.append("%s 须为 object" % where)
            continue
        allowed_item = {
            "cluster_id", "parent_finding_ids", "specialty", "question",
            "required_evidence", "specialist_required",
        }
        unknown = sorted(set(item) - allowed_item)
        if unknown:
            errors.append("%s 未知字段: %s" % (where, ", ".join(unknown)))
        cid = item.get("cluster_id")
        if not isinstance(cid, str) or not re.match(r"^[a-z][a-z0-9-]{2,63}$", cid):
            errors.append("%s.cluster_id 格式非法" % where)
        elif cid in seen:
            errors.append("cluster_id 重复: %s" % cid)
        else:
            seen.add(cid)
        parents = item.get("parent_finding_ids")
        if not isinstance(parents, list) or not parents or any(
                not isinstance(v, str) or not v for v in parents):
            errors.append("%s.parent_finding_ids 须为非空字符串数组" % where)
        if item.get("specialty") not in CHALLENGE_SPECIALTIES:
            errors.append("%s.specialty=%r 非法" % (where, item.get("specialty")))
        if not isinstance(item.get("question"), str) or not item["question"].strip():
            errors.append("%s.question 须为非空字符串" % where)
        required_evidence = item.get("required_evidence")
        if not isinstance(required_evidence, list) or any(
                not isinstance(v, str) or not v for v in required_evidence):
            errors.append("%s.required_evidence 须为字符串数组" % where)
        normalized.append(dict(item, specialist_required=bool(
            item.get("specialist_required", True))))
    return {"primary_contradiction": contradiction, "challenge_clusters": normalized}, errors


def cmd_record_challenge_clusters(args):
    ledger = load_ledger(args.run_dir)
    loop = _challenge_loop(ledger, args.loop_id)
    if not loop:
        die("找不到 loop_id: %s" % args.loop_id)
    if loop.get("orchestration") != "clustered":
        die("CLUSTER_ORCHESTRATION_DISABLED: start-challenge-loop 需使用 --orchestration clustered")
    if len(loop.get("rounds") or []) != 1:
        die("PRIMARY_CHALLENGE_REQUIRED: clusters 必须紧接第一轮 breadth challenge 记录")
    if loop.get("challenge_clusters") is not None:
        die("CHALLENGE_CLUSTERS_ALREADY_RECORDED")
    payload = _read_json_file(args.input, "challenge clusters")
    normalized, errors = _validate_challenge_clusters(payload)
    if errors:
        die("SCHEMA_INVALID: %s" % "; ".join(errors))
    contradiction = normalized["primary_contradiction"]
    if not re.match(r"^[a-z][a-z0-9-]{2,63}$", str(contradiction.get("id") or "")):
        die("SCHEMA_INVALID: primary_contradiction.id 格式非法")
    if not str(contradiction.get("summary") or "").strip():
        die("SCHEMA_INVALID: primary_contradiction.summary 须为非空字符串")
    known_ac = set((_active_contract_snapshot(loop) or {}).get("acceptance_ids") or [])
    contradiction_ac = set(contradiction.get("acceptance_ids") or [])
    if not contradiction_ac or not contradiction_ac.issubset(known_ac):
        die("SCHEMA_INVALID: primary_contradiction.acceptance_ids 缺失或引用未知 AC")
    primary_findings = {
        f.get("id") for f in (loop["rounds"][0].get("findings") or [])
    }
    unknown = sorted({fid for c in normalized["challenge_clusters"]
                      for fid in c.get("parent_finding_ids") or []} - primary_findings)
    if unknown:
        die("UNKNOWN_PARENT_FINDING: %s" % ", ".join(unknown))
    primary_blockers = {
        f.get("id") for f in (loop["rounds"][0].get("findings") or [])
        if f.get("severity") in {"P0", "P1"}
        and f.get("scope_relation") == "in-scope" and f.get("status") == "open"
    }
    clustered = {fid for c in normalized["challenge_clusters"]
                 for fid in c.get("parent_finding_ids") or []}
    missing = sorted(primary_blockers - clustered)
    if missing:
        die("PRIMARY_FINDING_UNCLUSTERED: %s" % ", ".join(missing))

    def mutate(current):
        target = _challenge_loop(current, args.loop_id)
        target["primary_contradiction"] = normalized["primary_contradiction"]
        target["challenge_clusters"] = normalized["challenge_clusters"]
        target["status"] = _challenge_state(target)

    _append(args.run_dir, mutate, op="record_challenge_clusters")
    print("CHALLENGE_CLUSTERS_RECORDED: %d" % len(normalized["challenge_clusters"]))


def _validate_cluster_finding_items(items, loop, required_ids=None):
    """Shared semantic checks for specialist and synthesis finding sets."""
    errors = []
    if not isinstance(items, list):
        return ["findings 须为数组"]
    required_fields = {
        "id", "severity", "scope_relation", "origin", "violated_acceptance_ids",
        "assurance_contract_ids", "evidence", "status", "root_cause",
    }
    snap = _active_contract_snapshot(loop) or {}
    known_ac = set(snap.get("acceptance_ids") or [])
    known_assurance = set(snap.get("assurance_ids") or [])
    seen = set()
    for index, item in enumerate(items):
        where = "findings[%d]" % index
        if not isinstance(item, dict):
            errors.append("%s 须为 object" % where)
            continue
        missing = sorted(required_fields - set(item))
        if missing:
            errors.append("%s 缺少字段: %s" % (where, ", ".join(missing)))
            continue
        fid = item.get("id")
        if not isinstance(fid, str) or not re.match(r"^[a-z][a-z0-9-]{2,63}$", fid):
            errors.append("%s.id 格式非法" % where)
        elif fid in seen:
            errors.append("%s.id 重复: %s" % (where, fid))
        seen.add(fid)
        if item.get("severity") not in FINDING_SEVERITIES:
            errors.append("%s.severity 非法" % where)
        if item.get("scope_relation") not in FINDING_SCOPE_RELATIONS:
            errors.append("%s.scope_relation 非法" % where)
        if item.get("origin") not in FINDING_ORIGINS:
            errors.append("%s.origin 非法" % where)
        if item.get("status") not in FINDING_STATUSES:
            errors.append("%s.status 非法" % where)
        if item.get("scope_relation") == "out-of-scope" and item.get("status") != "advisory":
            errors.append("%s out-of-scope finding 必须是 advisory" % where)
        if item.get("scope_relation") != "out-of-scope" and item.get("status") == "advisory":
            errors.append("%s in-scope/proposal finding 不能标 advisory" % where)
        acs = item.get("violated_acceptance_ids")
        aids = item.get("assurance_contract_ids")
        if not isinstance(acs, list) or not set(acs).issubset(known_ac):
            errors.append("%s acceptance binding 非法" % where)
            acs = []
        if not isinstance(aids, list) or not set(aids).issubset(known_assurance):
            errors.append("%s assurance binding 非法" % where)
            aids = []
        if (item.get("severity") in {"P0", "P1"}
                and item.get("scope_relation") in {"in-scope", "scope-change-proposal"}
                and (not acs or not aids)):
            errors.append("%s P0/P1 缺少 AC/assurance binding" % where)
        if not str(item.get("evidence") or "").strip() or not str(
                item.get("root_cause") or "").strip():
            errors.append("%s evidence/root_cause 须非空" % where)
    missing_required = set(required_ids or []) - seen
    if missing_required:
        errors.append("缺少 parent findings: %s" % ", ".join(sorted(missing_required)))
    return errors


def cmd_record_specialist_challenge(args):
    ledger = load_ledger(args.run_dir)
    loop = _challenge_loop(ledger, args.loop_id)
    if not loop:
        die("找不到 loop_id: %s" % args.loop_id)
    cluster = next((c for c in (loop.get("challenge_clusters") or [])
                    if c.get("cluster_id") == args.cluster_id), None)
    if not cluster:
        die("找不到 cluster_id: %s" % args.cluster_id)
    if any(i.get("cluster_id") == args.cluster_id
           for i in (loop.get("specialist_challenges") or [])):
        die("SPECIALIST_CHALLENGE_ALREADY_RECORDED: %s" % args.cluster_id)
    if args.status == "waived":
        if not args.waiver_reason or not args.waiver_reason.strip():
            die("WAIVER_REASON_REQUIRED")
        if not re.match(r"^[0-9a-f]{64}$", str(args.approval_hash or "")):
            die("USER_APPROVAL_REQUIRED: required specialist waiver 需要用户批准消息 SHA-256")
        output_path = None
        output_sha = None
    else:
        if not args.output or not os.path.isfile(args.output):
            die("SPECIALIST_OUTPUT_REQUIRED: %s" % args.output)
        payload = _read_json_file(args.output, "specialist output")
        if not isinstance(payload, dict) or not isinstance(payload.get("findings"), list):
            die("SCHEMA_INVALID: specialist output 须为含 findings 数组的 object")
        if payload.get("cluster_id") != args.cluster_id:
            die("SCHEMA_INVALID: specialist output.cluster_id 与目标 cluster 不一致")
        if payload.get("specialty") != cluster.get("specialty"):
            die("SCHEMA_INVALID: specialist output.specialty 与 cluster 不一致")
        if set(payload.get("parent_finding_ids") or []) != set(
                cluster.get("parent_finding_ids") or []):
            die("SCHEMA_INVALID: specialist output.parent_finding_ids 与 cluster 不一致")
        finding_errors = _validate_cluster_finding_items(
            payload.get("findings"), loop, required_ids=set(cluster.get("parent_finding_ids") or []))
        if finding_errors:
            die("SCHEMA_INVALID: specialist findings: %s" % "; ".join(finding_errors))
        if not isinstance(payload.get("cross_cluster_refs"), list):
            die("SCHEMA_INVALID: specialist output.cross_cluster_refs 须为数组")
        conclusion = payload.get("conclusion")
        if (not isinstance(conclusion, dict)
                or conclusion.get("status") not in {
                    "confirmed", "refined", "resolved", "needs-spike", "scope-change-proposal"
                } or not str(conclusion.get("summary") or "").strip()):
            die("SCHEMA_INVALID: specialist output.conclusion 缺少有效 status/summary")
        output_path = os.path.abspath(args.output)
        output_sha = sha256_file(args.output)
    record = {
        "cluster_id": args.cluster_id,
        "specialty": cluster.get("specialty"),
        "status": args.status,
        "output_path": output_path,
        "output_sha256": output_sha,
        "output": payload if args.status == "completed" else None,
        "waiver_reason": args.waiver_reason,
        "approval_hash": args.approval_hash,
        "recorded_at": now_iso(),
    }
    record = {k: v for k, v in record.items() if v is not None}

    def mutate(current):
        target = _challenge_loop(current, args.loop_id)
        target.setdefault("specialist_challenges", []).append(record)
        target["status"] = _challenge_state(target)

    _append(args.run_dir, mutate, op="record_specialist_challenge")
    print("SPECIALIST_CHALLENGE_RECORDED: %s status=%s" % (args.cluster_id, args.status))


def cmd_record_challenge_synthesis(args):
    ledger = load_ledger(args.run_dir)
    loop = _challenge_loop(ledger, args.loop_id)
    if not loop:
        die("找不到 loop_id: %s" % args.loop_id)
    if loop.get("synthesis"):
        die("CHALLENGE_SYNTHESIS_ALREADY_RECORDED")
    state = _challenge_state(loop)
    if state == "SPECIALIST_CHALLENGE_REQUIRED":
        die("SPECIALIST_CHALLENGE_REQUIRED: required cluster 尚未完成或有效豁免")
    payload = _read_json_file(args.input, "challenge synthesis")
    required = {"source_cluster_ids", "canonical_findings", "resolved_finding_ids",
                "open_finding_ids", "decisions", "conflicts", "required_spikes",
                "plan_actions"}
    if not isinstance(payload, dict) or not required.issubset(payload):
        die("SCHEMA_INVALID: synthesis 须包含 %s" % ", ".join(sorted(required)))
    for key in required:
        if not isinstance(payload.get(key), list):
            die("SCHEMA_INVALID: synthesis.%s 须为数组" % key)
    expected_clusters = {
        c.get("cluster_id") for c in (loop.get("challenge_clusters") or [])
        if c.get("specialist_required", True)
    }
    if set(payload.get("source_cluster_ids") or []) != expected_clusters:
        die("SYNTHESIS_CLUSTER_COVERAGE_INVALID: expected=%s actual=%s" % (
            ",".join(sorted(expected_clusters)),
            ",".join(sorted(set(payload.get("source_cluster_ids") or [])))))
    finding_errors = _validate_cluster_finding_items(payload.get("canonical_findings"), loop)
    if finding_errors:
        die("SCHEMA_INVALID: synthesis canonical_findings: %s" % "; ".join(finding_errors))
    canonical_ids = {f.get("id") for f in payload.get("canonical_findings") or []}
    specialist_ids = {
        f.get("id") for record in (loop.get("specialist_challenges") or [])
        for f in ((record.get("output") or {}).get("findings") or [])
    }
    if not specialist_ids.issubset(canonical_ids):
        die("SYNTHESIS_FINDING_COVERAGE_INVALID: missing=%s" %
            ",".join(sorted(specialist_ids - canonical_ids)))
    open_ids = set(payload.get("open_finding_ids") or [])
    resolved_ids = set(payload.get("resolved_finding_ids") or [])
    status_by_id = {f.get("id"): f.get("status") for f in payload.get("canonical_findings") or []}
    actionable_ids = {fid for fid, status in status_by_id.items() if status in {"open", "resolved"}}
    if open_ids & resolved_ids or open_ids | resolved_ids != actionable_ids:
        die("SYNTHESIS_FINDING_PARTITION_INVALID: open/resolved 必须无交集且覆盖全部 actionable canonical IDs")
    if any(status_by_id.get(fid) != "open" for fid in open_ids):
        die("SYNTHESIS_FINDING_STATUS_INVALID: open_finding_ids 与 canonical status 不一致")
    if any(status_by_id.get(fid) != "resolved" for fid in resolved_ids):
        die("SYNTHESIS_FINDING_STATUS_INVALID: resolved_finding_ids 与 canonical status 不一致")
    decision_ids = {d.get("canonical_finding_id") for d in payload.get("decisions") or []
                    if isinstance(d, dict)}
    if decision_ids != canonical_ids or len(payload.get("decisions") or []) != len(canonical_ids):
        die("SYNTHESIS_DECISION_COVERAGE_INVALID: 每个 canonical finding 必须有一个 decision")
    source_ids = specialist_ids | {
        f.get("id") for round_record in (loop.get("rounds") or [])
        for f in round_record.get("findings") or []
    }
    spike_ids = {item.get("id") for item in payload.get("required_spikes") or []
                 if isinstance(item, dict)}
    for decision in payload.get("decisions") or []:
        if not isinstance(decision, dict):
            die("SCHEMA_INVALID: synthesis decision 须为 object")
        action = decision.get("action")
        sources = decision.get("source_finding_ids")
        if (action not in {"plan-change", "evidence", "spike", "scope-change-proposal"}
                or not isinstance(sources, list) or not sources
                or not set(sources).issubset(source_ids)
                or not str(decision.get("rationale") or "").strip()):
            die("SCHEMA_INVALID: synthesis decision 的 action/source_finding_ids/rationale 非法")
        if action == "evidence" and not decision.get("evidence_refs"):
            die("SYNTHESIS_EVIDENCE_REQUIRED: evidence action 必须绑定 evidence_refs")
        if action == "spike":
            refs = set(decision.get("spike_ids") or [])
            if not refs or not refs.issubset(spike_ids):
                die("SYNTHESIS_SPIKE_REQUIRED: spike action 必须绑定 required_spikes ID")
        if action == "scope-change-proposal" and status_by_id.get(
                decision.get("canonical_finding_id")) != "open":
            die("SYNTHESIS_SCOPE_CHANGE_OPEN_REQUIRED: scope change finding 必须保持 open")
    for conflict in payload.get("conflicts") or []:
        if (not isinstance(conflict, dict)
                or conflict.get("canonical_finding_id") not in canonical_ids
                or not str(conflict.get("resolution") or "").strip()):
            die("SYNTHESIS_CONFLICT_UNRESOLVED: conflict 必须绑定 canonical finding 和 resolution")
    record = {
        "input_path": os.path.abspath(args.input),
        "input_sha256": sha256_file(args.input),
        "payload": payload,
        "after_round": len(loop.get("rounds") or []),
        "recorded_at": now_iso(),
    }

    def mutate(current):
        target = _challenge_loop(current, args.loop_id)
        target["synthesis"] = record
        target["status"] = _challenge_state(target)

    _append(args.run_dir, mutate, op="record_challenge_synthesis")
    print("CHALLENGE_SYNTHESIS_RECORDED")


def cmd_record_challenge_control(args):
    ledger = load_ledger(args.run_dir)
    loop = _challenge_loop(ledger, args.loop_id)
    if not loop:
        die("找不到 loop_id: %s" % args.loop_id)
    current_state = _challenge_state(loop)
    required_state = {
        "scope-audit": "SCOPE_AUDIT_REQUIRED",
        "architecture-reset": "ARCHITECTURE_RESET_REQUIRED",
        "user-review": "USER_REVIEW_REQUIRED",
        "scope-change-approved": "USER_SCOPE_APPROVAL_REQUIRED",
    }[args.action]
    if current_state != required_state:
        die("CONTROL_NOT_REQUIRED: action=%s 仅在 %s 可记录；当前=%s" % (
            args.action, required_state, current_state))
    if args.action not in CHALLENGE_CONTROL_ACTIONS:
        die("CONTROL_ACTION_INVALID: %s" % args.action)
    if not isinstance(args.evidence, str) or not args.evidence.strip():
        die("CONTROL_EVIDENCE_REQUIRED")
    if args.action in {"scope-audit", "user-review"} and args.outcome not in {
            "continue", "architecture-reset", "scope-change"}:
        die("CONTROL_OUTCOME_INVALID: %s 需要 continue|architecture-reset|scope-change" % args.action)
    if args.action == "scope-change-approved" and not re.match(
            r"^[0-9a-f]{64}$", str(args.approval_hash or "")):
        die("USER_APPROVAL_REQUIRED: scope change 需要 64 位消息 hash")
    after_round = len(loop.get("rounds") or [])
    event = {
        "action": args.action,
        "after_round": after_round,
        "outcome": args.outcome,
        "evidence": args.evidence,
        "approval_hash": args.approval_hash,
        "recorded_at": now_iso(),
    }
    if args.action == "architecture-reset":
        latest_plan_hash = (loop.get("rounds") or [{}])[-1].get("plan_hash")
        reset_plan_hash = sha256_file(loop["target_file"])
        if reset_plan_hash == latest_plan_hash:
            die("ARCHITECTURE_RESET_INCOMPLETE: plan 内容未变化")
        event["plan_hash"] = reset_plan_hash
    new_snapshot = None
    new_acceptance_snapshot = None
    if args.assurance_contract or args.acceptance:
        if args.action != "scope-change-approved":
            die("只有 scope-change-approved 可替换 acceptance/assurance contract")
        active_acceptance = _active_acceptance_snapshot(loop)
        acceptance_path = args.acceptance or (active_acceptance or {}).get("path")
        if not acceptance_path or not os.path.isfile(acceptance_path):
            die("ACCEPTANCE_REQUIRED: scope change 后须有可读取的 acceptance")
        acceptance_hash = sha256_file(acceptance_path)
        contract_path = args.assurance_contract or (_active_contract_snapshot(loop) or {}).get("path")
        contract = _read_json_file(contract_path, "assurance contract")
        errors = _validate_assurance_contract(contract)
        if errors:
            die("SCHEMA_INVALID: assurance contract: %s" % "; ".join(errors))
        new_acceptance_snapshot = {
            "path": os.path.abspath(acceptance_path),
            "sha256": acceptance_hash,
            "recorded_at": now_iso(),
        }
        new_snapshot = _assurance_snapshot(contract_path, contract, acceptance_hash)
        event["acceptance_sha256"] = acceptance_hash
        event["scope_hash"] = new_snapshot["scope_hash"]
        event["threat_model_hash"] = new_snapshot["threat_model_hash"]

    def mutate(current):
        target = _challenge_loop(current, args.loop_id)
        target.setdefault("control_events", []).append(event)
        if new_acceptance_snapshot:
            target.setdefault("acceptance_snapshots", []).append(new_acceptance_snapshot)
        if new_snapshot:
            target.setdefault("contract_snapshots", []).append(new_snapshot)
        target["status"] = _challenge_state(target)

    updated = _append(args.run_dir, mutate, op="record_challenge_control")
    state = _challenge_state(_challenge_loop(updated, args.loop_id))
    print("CHALLENGE_CONTROL_RECORDED: %s" % args.action)
    print("LOOP_STATE: %s" % state)
    sys.exit(0)


def _calculate_file_similarity(file1, file2):
    """计算两个文件的相似度（0-1）。

    使用简单的 difflib.SequenceMatcher。
    """
    try:
        with open(file1, 'r', encoding='utf-8', errors='ignore') as f:
            content1 = f.read()
        with open(file2, 'r', encoding='utf-8', errors='ignore') as f:
            content2 = f.read()

        import difflib
        matcher = difflib.SequenceMatcher(None, content1, content2)
        return matcher.ratio()
    except Exception:
        return 0.0


def cmd_detect_loop_reset(args):
    """P0-3: 检测循环重置绕过（防重置检测）。

    检查是否存在:
    - 账本被删除（challenge_loops 消失）
    - loop_id 改变但 target_file 相似度 > 80%
    - target_file 改名但内容相似
    """
    ledger = load_ledger(args.run_dir)
    loops = ledger.get("challenge_loops") or []

    if not loops:
        print("WARNING: 账本中无循环记录，可能已被删除或重置")
        if args.check_target_file and os.path.isfile(args.check_target_file):
            print("  - 检测到目标文件: %s" % args.check_target_file)
            print("  - 建议检查是否存在历史循环记录")
        sys.exit(0)

    # 如果提供了待检查的文件，计算相似度
    if args.check_target_file and os.path.isfile(args.check_target_file):
        for loop in loops:
            if str(loop.get("status") or "").lower() == "active" and loop["target_file"] != args.check_target_file:
                # 文件名不同，检查内容相似度
                if os.path.isfile(loop["target_file"]):
                    similarity = _calculate_file_similarity(
                        loop["target_file"],
                        args.check_target_file
                    )
                    if similarity > 0.8:
                        print("LOOP_RESET_EVASION")
                        print("\n检测到循环重置绕过:")
                        print("  - 原文件: %s" % loop["target_file"])
                        print("  - 新文件: %s" % args.check_target_file)
                        print("  - 相似度: %.1f%%" % (similarity * 100))
                        print("  - 原循环: %s（%d 轮）" % (
                            loop["loop_id"],
                            len(loop["rounds"])
                        ))
                        print("\n疑似通过改名绕过轮次限制")
                        sys.exit(1)

    print("LOOP_RESET_CHECK_PASS")
    print("  - 活跃循环: %d" % len([l for l in loops
                                     if str(l.get("status") or "").lower() == "active"]))
    print("  - 已收敛: %d" % len([l for l in loops
                                     if str(l.get("status") or "").lower() == "converged"]))
    sys.exit(0)


def cmd_check_plan_growth(args):
    """P1-2: 检查 plan 体量增长是否超过阈值。

    对比 baseline 和当前 plan，若增长 > MAX_PLAN_GROWTH_RATIO (1.5) → 主动报告。
    """
    if not os.path.isfile(args.baseline):
        die("baseline 文件不存在: %s" % args.baseline)

    if not os.path.isfile(args.current):
        die("current 文件不存在: %s" % args.current)

    # 计算行数
    with open(args.baseline, 'r', encoding='utf-8') as f:
        baseline_lines = len([l for l in f if l.strip()])

    with open(args.current, 'r', encoding='utf-8') as f:
        current_lines = len([l for l in f if l.strip()])

    growth_ratio = current_lines / baseline_lines if baseline_lines > 0 else float('inf')
    threshold = args.threshold or MAX_PLAN_GROWTH_RATIO

    if growth_ratio > threshold:
        print("PLAN_SCOPE_EXPANSION")
        print("\nPlan 体量显著增长:")
        print("  - Baseline: %d 行" % baseline_lines)
        print("  - Current: %d 行" % current_lines)
        print("  - 增长率: %.1f%% (阈值 %.0f%%)" % (
            (growth_ratio - 1) * 100,
            (threshold - 1) * 100
        ))
        print("\n可能原因:")
        print("  1. 需求理解偏差导致 scope 扩张")
        print("  2. 发现了未预料的复杂度")
        print("  3. 增加了原需求之外的功能")
        print("\n建议:")
        print("  - 与用户确认新增部分是否在原需求范围内")
        print("  - 考虑拆分成多个 release unit")
        print("  - 或更新 acceptance.md 反映实际范围")

        # advisory 级别，exit 0 但输出警告
        sys.exit(0)

    print("PLAN_GROWTH_OK")
    print("  - Baseline: %d 行" % baseline_lines)
    print("  - Current: %d 行" % current_lines)
    print("  - 增长率: %.1f%%" % ((growth_ratio - 1) * 100))
    sys.exit(0)


def cmd_show_loop_history(args):
    """P2-1: 显示循环历史和趋势。

    可视化展示每轮的 findings、hash、趋势。
    """
    ledger = load_ledger(args.run_dir)
    loops = ledger.get("challenge_loops") or []

    if not loops:
        print("无循环记录")
        sys.exit(0)

    # 如果指定了 loop_id，只显示该循环
    if args.loop_id:
        target_loop = None
        for loop in loops:
            if loop["loop_id"] == args.loop_id:
                target_loop = loop
                break

        if not target_loop:
            die("找不到 loop_id: %s" % args.loop_id)

        loops = [target_loop]

    print("=== 循环历史 ===\n")

    for loop in loops:
        print("Loop: %s" % loop["loop_id"])
        print("  类型: %s" % loop["loop_type"])
        print("  目标文件: %s" % loop["target_file"])
        print("  状态: %s" % loop["status"])
        print("  开始时间: %s" % loop["started_at"])
        print("  总轮次: %d\n" % len(loop["rounds"]))

        if not loop["rounds"]:
            print("  （无轮次记录）\n")
            continue

        # 表头
        print("  Round | Mode         | New P0/P1 | Open P0/P1 | Advisory | Plan Hash")
        print("  ------|--------------|-----------|------------|----------|----------")

        # 每轮数据
        for r in loop["rounds"]:
            findings = r.get("findings", [])
            if isinstance(findings, dict):
                # 1.3 legacy history
                new_count = findings.get("critical", 0) + findings.get("major", 0)
                open_count = new_count
                advisory_count = findings.get("minor", 0)
                mode = "legacy"
            else:
                new_count = int(r.get("new_critical_findings") or 0)
                open_count = sum(1 for f in findings if f.get("severity") in ("P0", "P1")
                                 and f.get("scope_relation") == "in-scope"
                                 and f.get("status") == "open")
                advisory_count = sum(1 for f in findings
                                     if f.get("scope_relation") == "out-of-scope")
                mode = r.get("review_mode") or "?"
            print("  %-5d | %-12s | %-9d | %-10d | %-8d | %s" % (
                r["round"], mode, new_count, open_count, advisory_count,
                r["plan_hash"][:8]))

        # 趋势分析
        if len(loop["rounds"]) >= 2:
            first = loop["rounds"][0]
            last = loop["rounds"][-1]

            def blocker_count(record):
                fs = record.get("findings", [])
                if isinstance(fs, dict):
                    return fs.get("critical", 0) + fs.get("major", 0)
                return sum(1 for f in fs if f.get("severity") in ("P0", "P1")
                           and f.get("scope_relation") == "in-scope"
                           and f.get("status") == "open")

            first_critical = blocker_count(first)
            last_critical = blocker_count(last)

            print("\n  趋势分析:")
            if last_critical < first_critical:
                print("    ✓ Critical findings 减少: %d → %d" % (first_critical, last_critical))
            elif last_critical > first_critical:
                print("    ✗ Critical findings 增加: %d → %d" % (first_critical, last_critical))
            else:
                print("    - Critical findings 持平: %d" % first_critical)

            # 检测回退
            hashes = [r["plan_hash"] for r in loop["rounds"]]
            if len(hashes) != len(set(hashes)):
                print("    ⚠️  检测到 plan hash 重复（可能回退）")

        print()

    sys.exit(0)


def cmd_record_phase_transition(args):
    """P2-2: 记录 phase 转移事件。

    记录从一个 phase 转移到另一个 phase，以及转移时的收敛证据。
    """
    ledger = load_ledger(args.run_dir)

    import datetime
    now = datetime.datetime.now().astimezone()

    transition_record = {
        "from_phase": args.from_phase,
        "to_phase": args.to_phase,
        "timestamp": now.isoformat(),
        "convergence_evidence": args.evidence or "N/A",
        "note": args.note
    }

    def mutate(ledger):
        if "phase_transitions" not in ledger:
            ledger["phase_transitions"] = []
        ledger["phase_transitions"].append(transition_record)

    _append(args.run_dir, mutate, op="record_phase_transition")

    print("PHASE_TRANSITION_RECORDED")
    print("  - From: %s" % args.from_phase)
    print("  - To: %s" % args.to_phase)
    print("  - 收敛证据: %s" % (args.evidence or "N/A"))
    if args.note:
        print("  - 备注: %s" % args.note)
    sys.exit(0)


# ---------------------------------------------------------------- main

def main(argv=None):
    ap = argparse.ArgumentParser(prog="plan_test_gate.py")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("compile-manifest",
                       help="从结构化 verification spec 编译并冻结 gate manifest")
    p.add_argument("--spec", required=True)
    p.add_argument("--output", required=True)
    p.set_defaults(fn=cmd_compile_manifest)

    p = sub.add_parser("init")
    p.add_argument("--run-dir", required=True)
    p.add_argument("--manifest", required=True)
    p.add_argument("--force", action="store_true")
    p.add_argument("--allow-external-run-dir", action="store_true",
                   help="允许把 run-dir 放到仓库之外（仓里不留痕迹，hook/CI 看不见）；选择会记入账本")
    p.set_defaults(fn=cmd_init)

    p = sub.add_parser("activate-run",
                       help="显式选择本仓库当前候选 run；并行 slice 不会被 init 自动抢占")
    p.add_argument("--run-dir", required=True)
    p.set_defaults(fn=cmd_activate_run)

    p = sub.add_parser("record-run")
    p.add_argument("--run-dir", required=True)
    p.add_argument("--scenario", required=True)
    p.add_argument("--kind", required=True, choices=sorted(KIND_VALUES))
    p.add_argument("--result", choices=sorted(RESULT_VALUES),
                   help="自报结果；与 --exec 互斥（--exec 时由 exit code 决定）")
    p.add_argument("--lane", default="fresh")
    p.add_argument("--driver", default="ai", choices=["ai", "human"])
    p.add_argument("--command")
    p.add_argument("--engine-terminal")
    p.add_argument("--business-terminal")
    p.add_argument("--session-id")
    p.add_argument("--run-id-under-test")
    # --exec -- <cmd...> 在 main() 里预切分（与 record-timing 同一约定）：
    # gate 亲自执行命令，exit code 决定 result，输出日志自动记为 primary 证据
    p.set_defaults(fn=cmd_record_run, exec_cmd=None)

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
    p.add_argument("--metadata", help="结构化 evidence metadata JSON（producer/artifact/identity/facts）")
    p.set_defaults(fn=cmd_attach_evidence, from_run=None)

    p = sub.add_parser("import-evidence",
                       help="显式导入**开账之前**产生的历史证据（保留 chain of custody）；"
                            "普通 attach 遇到早于开账的文件会被 EVIDENCE_PREDATES_LEDGER 拦截")
    p.add_argument("--run-dir", required=True)
    p.add_argument("--path", required=True, help="相对 run-dir 的证据路径")
    p.add_argument("--kind", required=True, choices=["primary", "derived"])
    p.add_argument("--from-run", required=True, dest="from_run",
                   help="来源说明：原始 run 目录/会话/采集时间——历史证据必须能说明出处")
    p.add_argument("--scenario")
    p.add_argument("--id")
    p.add_argument("--ui-action", action="store_true")
    p.add_argument("--negative-assertion", action="store_true")
    p.add_argument("--replace", action="store_true")
    p.add_argument("--depends-on", nargs="*")
    p.add_argument("--metadata", help="结构化 evidence metadata JSON（producer/artifact/identity/facts）")
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

    p = sub.add_parser("phase-start", help="进入一个阶段（finalize 要求与 phase-end 配对）")
    p.add_argument("--run-dir", required=True)
    p.add_argument("--phase", required=True)
    p.add_argument("--note")
    p.set_defaults(fn=lambda a: cmd_phase_event(a, "start"))

    p = sub.add_parser("phase-end", help="结束一个阶段")
    p.add_argument("--run-dir", required=True)
    p.add_argument("--phase", required=True)
    p.add_argument("--status", default="ok", choices=["ok", "blocked", "abandoned"])
    p.add_argument("--subagents", type=int,
                   help="遥测（自报）：本阶段派发的子代理数；render 开销表聚合，不参与门判定")
    p.add_argument("--rounds", type=int,
                   help="遥测（自报）：本阶段实际轮次数")
    p.add_argument("--note")
    p.set_defaults(fn=lambda a: cmd_phase_event(a, "end"))

    p = sub.add_parser("record-approval",
                       help="登记用户在 chat 中的显式批准（绑定批准消息的 SHA-256）")
    p.add_argument("--run-dir", required=True)
    p.add_argument("--kind", required=True, choices=["all-ai-driving", "scope-reduction"])
    p.add_argument("--message-hash", required=True,
                   help="用户批准消息原文的 SHA-256（64 位十六进制）")
    p.add_argument("--note")
    p.set_defaults(fn=cmd_record_approval)

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

    p = sub.add_parser("resolve-audit-finding",
                       help="用 resolution + evidence + 必要的 fresh retest 闭环结构化 auditor finding")
    p.add_argument("--run-dir", required=True)
    p.add_argument("--finding-id", required=True)
    p.add_argument("--resolution", required=True)
    p.add_argument("--evidence-ids", nargs="*")
    p.set_defaults(fn=cmd_resolve_audit_finding)

    p = sub.add_parser("list-audit-findings")
    p.add_argument("--run-dir", required=True)
    p.set_defaults(fn=cmd_list_audit_findings)

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

    p = sub.add_parser("acknowledge",
                       help="用户显式确认放弃这一轮验证：本 run 作废（永远不会有 receipt），"
                            "hook 不再拿它阻断收尾。与 retire 的区别：retire 是把举证责任"
                            "转移给已通过的继任轮，acknowledge 是用户认账放弃。")
    p.add_argument("--run-dir", required=True)
    p.add_argument("--reason", required=True, help="为什么放弃这一轮（会写进账本与报告横幅）")
    p.add_argument("--approval-hash", required=True, dest="approval_hash",
                   help="用户批准消息原文的 SHA-256（64 位十六进制）——放弃是用户的决定")
    p.set_defaults(fn=cmd_acknowledge)

    p = sub.add_parser("ack-status")
    p.add_argument("--run-dir", required=True)
    p.set_defaults(fn=cmd_ack_status)

    p = sub.add_parser("summary",
                       help="一行摘要（hook/CI 压缩输出用）；退出码同 finalize --check-only")
    p.add_argument("--run-dir", required=True)
    p.set_defaults(fn=cmd_summary)

    p = sub.add_parser("stats",
                       help="规则退休的数据来源：扫描全部 run 账本与 receipt，按诊断码统计"
                            "触发情况；连续 N 个 run 零触发的门列为退休候选（只报表，不改状态）")
    p.add_argument("--root", default=".", help="仓库根目录（缺省当前目录）")
    p.add_argument("--window", type=int, default=5,
                   help="退休候选窗口：最近 N 个 run 零触发（默认 5）")
    p.add_argument("--json", action="store_true", dest="as_json", help="机器可读输出")
    p.set_defaults(fn=cmd_stats)

    p = sub.add_parser("invalidate")
    p.add_argument("--run-dir", required=True)
    p.add_argument("--reason", required=True)
    p.set_defaults(fn=cmd_invalidate)

    p = sub.add_parser("check-release-unit",
                       help="P0-1: Phase 3 开工前检查 release unit 是否超限")
    p.add_argument("--acceptance", required=True, help="acceptance.md 路径")
    p.add_argument("--plan", required=True, help="plan.md 或 implementation-tasks.md 路径")
    p.add_argument("--max-must-ac", type=int, help="MUST AC 上限（默认 16）")
    p.add_argument("--max-plan-lines", type=int, help="Plan 行数上限（默认 2000）")
    p.add_argument("--max-high-risk", type=int, help="高风险子系统上限（默认 3）")
    p.set_defaults(fn=cmd_check_release_unit)

    p = sub.add_parser("validate-release-unit",
                       help="P0-2: 检查 ledger 的 release_unit 字段是否正确声明")
    p.add_argument("--run-dir", required=True)
    p.set_defaults(fn=cmd_validate_release_unit)

    p = sub.add_parser("check-wip-limit",
                       help="P0-5: 检查未提交 WIP 是否超过安全阈值")
    p.add_argument("--repo-dir", required=True, help="Git 仓库目录")
    p.add_argument("--max-lines", type=int, help="未提交行数上限（默认 5000）")
    p.add_argument("--max-files", type=int, help="未提交文件数上限（默认 20）")
    p.set_defaults(fn=cmd_check_wip_limit)

    p = sub.add_parser("check-ledger-progress",
                       help="P1-1: 检查 ledger 是否长时间无进展")
    p.add_argument("--run-dir", required=True)
    p.add_argument("--min-interval-minutes", type=int,
                   help="零增长警告阈值（分钟，默认 90）")
    p.set_defaults(fn=cmd_check_ledger_progress)

    p = sub.add_parser("record-plan-defect",
                       help="P0-4: 记录 A2 plan defect 事件")
    p.add_argument("--run-dir", required=True)
    p.add_argument("--affected-tasks", required=True,
                   help="受影响的任务 ID，逗号分隔（如 'T4.1,T4.2'）")
    p.add_argument("--defect-type", required=True,
                   help="缺陷类型（如 contract-conflict, scope-drift, assumption-failure）")
    p.add_argument("--description", required=True,
                   help="缺陷描述")
    p.set_defaults(fn=cmd_record_plan_defect)

    p = sub.add_parser("check-plan-stability",
                       help="P0-4: 检查 plan 稳定性（累计 A2 事件数）")
    p.add_argument("--run-dir", required=True)
    p.set_defaults(fn=cmd_check_plan_stability)

    p = sub.add_parser("resolve-plan-defect",
                       help="P0-4: 标记某个 A2 事件已解决")
    p.add_argument("--run-dir", required=True)
    p.add_argument("--event-id", required=True, help="事件 ID（如 a2-001）")
    p.add_argument("--resolution", required=True, help="解决方案描述")
    p.set_defaults(fn=cmd_resolve_plan_defect)

    p = sub.add_parser("reset-plan-defects",
                       help="P0-4: 清空 A2 计数（需要用户批准）")
    p.add_argument("--run-dir", required=True)
    p.add_argument("--approval-hash", required=True,
                   help="用户批准消息的 SHA-256（64 位十六进制）")
    p.add_argument("--reason", required=True,
                   help="重置理由（如 '已回退 phase-2 并重新收敛'）")
    p.set_defaults(fn=cmd_reset_plan_defects)

    p = sub.add_parser("start-challenge-loop",
                       help="P0-3: 启动一个挑战循环")
    p.add_argument("--run-dir", required=True)
    p.add_argument("--loop-type", required=True,
                   help="循环类型（如 plan-iteration, code-review）")
    p.add_argument("--target-file", required=True,
                   help="目标文件路径（如 plans/xxx/plan.md）")
    p.add_argument("--baseline-hash",
                   help="基线 hash（可选，不提供则自动计算）")
    p.add_argument("--assurance-contract", required=True,
                   help="结构化 assurance-contract.json；启动时冻结 scope/threat hashes")
    p.add_argument("--orchestration", choices=["legacy", "clustered"], default="legacy",
                   help="clustered=primary→专项 fan-out→synthesis→closure；legacy 仅用于旧调用兼容")
    p.set_defaults(fn=cmd_start_challenge_loop)

    p = sub.add_parser("check-loop-limit",
                       help="P0-3: 检查循环是否超过轮次上限")
    p.add_argument("--run-dir", required=True)
    p.add_argument("--loop-id", required=True, help="循环 ID（如 plan-iteration-001）")
    p.set_defaults(fn=cmd_check_loop_limit)

    p = sub.add_parser("record-challenge-round",
                       help="P0-3: 记录一轮挑战结果")
    p.add_argument("--run-dir", required=True)
    p.add_argument("--loop-id", required=True)
    p.add_argument("--round", type=int, required=True, help="轮次编号（从 1 开始）")
    p.add_argument("--plan-hash", required=True, help="当前 plan 文件的 SHA-256")
    p.add_argument("--based-on-plan-hash",
                   help="第二轮起必填：本轮修改所基于的上一轮 plan hash")
    p.add_argument("--findings", required=True,
                   help="结构化 review envelope JSON 文件")
    p.add_argument("--verdict", choices=["PASS", "FAIL"],
                   help="兼容旧 challenger 输出；只记为事实，不参与 gate 状态推导")
    p.set_defaults(fn=cmd_record_challenge_round)

    p = sub.add_parser("record-challenge-clusters",
                       help="记录 primary breadth 发现的主要矛盾与专项挑战 cluster")
    p.add_argument("--run-dir", required=True)
    p.add_argument("--loop-id", required=True)
    p.add_argument("--input", required=True, help="primary_contradiction/challenge_clusters JSON")
    p.set_defaults(fn=cmd_record_challenge_clusters)

    p = sub.add_parser("record-specialist-challenge",
                       help="记录一个 root-cause cluster 的专项挑战或显式豁免")
    p.add_argument("--run-dir", required=True)
    p.add_argument("--loop-id", required=True)
    p.add_argument("--cluster-id", required=True)
    p.add_argument("--status", required=True, choices=["completed", "waived"])
    p.add_argument("--output", help="completed 时必填：含 findings 数组的 JSON")
    p.add_argument("--waiver-reason", help="waived 时必填")
    p.add_argument("--approval-hash", help="waived 时必填：用户批准消息 SHA-256")
    p.set_defaults(fn=cmd_record_specialist_challenge)

    p = sub.add_parser("record-challenge-synthesis",
                       help="合并专项输出并冻结 closure review 的输入")
    p.add_argument("--run-dir", required=True)
    p.add_argument("--loop-id", required=True)
    p.add_argument("--input", required=True)
    p.set_defaults(fn=cmd_record_challenge_synthesis)

    p = sub.add_parser("record-challenge-control",
                       help="记录 scope audit、architecture reset、用户 review/scope 批准事件")
    p.add_argument("--run-dir", required=True)
    p.add_argument("--loop-id", required=True)
    p.add_argument("--action", required=True, choices=sorted(CHALLENGE_CONTROL_ACTIONS))
    p.add_argument("--outcome", choices=["continue", "architecture-reset", "scope-change"])
    p.add_argument("--evidence", required=True)
    p.add_argument("--approval-hash")
    p.add_argument("--assurance-contract",
                   help="scope-change-approved 时可提供经用户批准的新 contract")
    p.add_argument("--acceptance",
                   help="scope-change-approved 时可提供经用户批准的新 acceptance")
    p.set_defaults(fn=cmd_record_challenge_control)

    p = sub.add_parser("detect-loop-reset",
                       help="P0-3: 检测循环重置绕过（防重置检测）")
    p.add_argument("--run-dir", required=True)
    p.add_argument("--check-target-file",
                   help="待检查的目标文件（检测是否与历史循环相似）")
    p.set_defaults(fn=cmd_detect_loop_reset)

    p = sub.add_parser("check-plan-growth",
                       help="P1-2: 检查 plan 体量增长是否超过阈值")
    p.add_argument("--baseline", required=True, help="Baseline plan 文件路径")
    p.add_argument("--current", required=True, help="当前 plan 文件路径")
    p.add_argument("--threshold", type=float,
                   help="增长比例阈值（默认 1.5，即 50%% 增长）")
    p.set_defaults(fn=cmd_check_plan_growth)

    p = sub.add_parser("show-loop-history",
                       help="P2-1: 显示循环历史和趋势")
    p.add_argument("--run-dir", required=True)
    p.add_argument("--loop-id", help="指定循环 ID（可选，不指定则显示所有）")
    p.set_defaults(fn=cmd_show_loop_history)

    p = sub.add_parser("record-phase-transition",
                       help="P2-2: 记录 phase 转移事件")
    p.add_argument("--run-dir", required=True)
    p.add_argument("--from-phase", required=True, help="源 phase（如 phase-2）")
    p.add_argument("--to-phase", required=True, help="目标 phase（如 phase-3）")
    p.add_argument("--evidence", help="收敛证据描述")
    p.add_argument("--note", help="备注")
    p.set_defaults(fn=cmd_record_phase_transition)

    argv = list(sys.argv[1:] if argv is None else argv)
    exec_cmd = None
    if argv and argv[0] in ("record-timing", "record-run") and "--exec" in argv:
        i = argv.index("--exec")
        exec_cmd = argv[i + 1:]
        argv = argv[:i]
    args = ap.parse_args(argv)
    if exec_cmd is not None:
        args.exec_cmd = exec_cmd
    args.fn(args)


if __name__ == "__main__":
    main()
