#!/usr/bin/env python3
"""tier_check.py 的测试：真 git 仓库、真 diff、真子进程退出码——不 mock git。"""

import refusal_guard  # noqa: F401  测试隔离：把 refusal 写入引到 tmpdir（s1a AC-7，见该模块 docstring）
import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TIER_CHECK = os.path.join(HERE, "tier_check.py")

LEDGER = {
    "schema_version": "2.0.0",
    "run_id": "r-test",
    "scenarios": [],
    "integrity": {"chain": []},
}


def run_git(repo, *args):
    subprocess.run(["git", "-C", repo] + list(args), check=True,
                   capture_output=True, text=True)


def commit_all(repo, msg):
    run_git(repo, "add", "-A")
    subprocess.run(["git", "-C", repo, "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-q", "--allow-empty", "-m", msg],
                   check=True, capture_output=True, text=True)


def write(repo, rel, content):
    path = os.path.join(repo, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def tier_check(repo, base="base", extra=None):
    cmd = [sys.executable, TIER_CHECK, "--base", base, "--repo", repo] + (extra or [])
    return subprocess.run(cmd, capture_output=True, text=True, timeout=60)


class TierCheckTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = self._tmp.name
        run_git(self.repo, "init", "-q")
        write(self.repo, "readme.md", "hi\n")
        commit_all(self.repo, "init")
        run_git(self.repo, "tag", "base")

    def tearDown(self):
        self._tmp.cleanup()

    def with_globs(self, *lines):
        write(self.repo, ".claude/plan-test-risk.globs", "\n".join(lines) + "\n")
        commit_all(self.repo, "globs")
        run_git(self.repo, "tag", "-f", "base")

    def test_no_globs_file_passes(self):
        write(self.repo, "database/migrations/x.php", "<?php\n")
        commit_all(self.repo, "mig")
        r = tier_check(self.repo)
        self.assertEqual(r.returncode, 0)
        self.assertIn("未声明", r.stdout)

    def test_comment_only_globs_passes(self):
        self.with_globs("# 只有注释", "", "   ")
        write(self.repo, "database/migrations/x.php", "<?php\n")
        commit_all(self.repo, "mig")
        r = tier_check(self.repo)
        self.assertEqual(r.returncode, 0)

    def test_non_matching_change_passes(self):
        self.with_globs("database/migrations/**")
        write(self.repo, "docs/note.md", "x\n")
        commit_all(self.repo, "docs")
        r = tier_check(self.repo)
        self.assertEqual(r.returncode, 0)
        self.assertIn("未命中", r.stdout)

    def test_risk_hit_without_ledger_fails(self):
        self.with_globs("database/migrations/**", "routes/**")
        write(self.repo, "database/migrations/2026_x.php", "<?php\n")
        commit_all(self.repo, "mig")
        r = tier_check(self.repo)
        self.assertEqual(r.returncode, 1)
        self.assertIn("database/migrations/2026_x.php", r.stderr)
        self.assertIn("database/migrations/**", r.stderr)

    def test_risk_hit_with_ledger_passes(self):
        self.with_globs("database/migrations/**")
        write(self.repo, "database/migrations/2026_x.php", "<?php\n")
        write(self.repo, "plans/p/verification/r1/plan-test-run.json",
              json.dumps(LEDGER))
        commit_all(self.repo, "mig+ledger")
        r = tier_check(self.repo)
        self.assertEqual(r.returncode, 0)
        self.assertIn("账本", r.stdout)

    def test_shape_not_name_decides_ledger(self):
        # 叫 plan-test-run.json 但缺 integrity 键：不是账本，照样 FAIL
        self.with_globs("routes/**")
        write(self.repo, "routes/web.php", "<?php\n")
        fake = {k: LEDGER[k] for k in ("schema_version", "run_id", "scenarios")}
        write(self.repo, "plans/p/verification/r1/plan-test-run.json",
              json.dumps(fake))
        commit_all(self.repo, "fake ledger")
        self.assertEqual(tier_check(self.repo).returncode, 1)
        # 反向：名字随意但形状是账本 → 放行
        write(self.repo, "plans/p/verification/r1/whatever.json", json.dumps(LEDGER))
        commit_all(self.repo, "shaped ledger")
        self.assertEqual(tier_check(self.repo).returncode, 0)

    def test_updated_ledger_counts(self):
        # 账本早已存在，本次 diff 只更新它：算账本活动
        self.with_globs("config/**")
        write(self.repo, "plans/p/verification/r1/plan-test-run.json",
              json.dumps(LEDGER))
        commit_all(self.repo, "ledger")
        run_git(self.repo, "tag", "-f", "base")
        write(self.repo, "config/app.php", "<?php\n")
        updated = dict(LEDGER, run_id="r-test-2")
        write(self.repo, "plans/p/verification/r1/plan-test-run.json",
              json.dumps(updated))
        commit_all(self.repo, "config+ledger update")
        self.assertEqual(tier_check(self.repo).returncode, 0)

    def test_glob_star_does_not_cross_slash(self):
        self.with_globs("app/Providers/*.php")
        write(self.repo, "app/Providers/Sub/Deep.php", "<?php\n")
        commit_all(self.repo, "deep")
        self.assertEqual(tier_check(self.repo).returncode, 0)
        write(self.repo, "app/Providers/AppServiceProvider.php", "<?php\n")
        commit_all(self.repo, "direct")
        self.assertEqual(tier_check(self.repo).returncode, 1)

    def test_doublestar_prefix_and_middle(self):
        self.with_globs("**/secrets/**")
        write(self.repo, "app/stores/secrets/key.txt", "x\n")
        commit_all(self.repo, "secret")
        self.assertEqual(tier_check(self.repo).returncode, 1)

    def test_bad_base_ref_is_usage_error(self):
        self.with_globs("routes/**")
        r = tier_check(self.repo, base="no-such-ref")
        self.assertEqual(r.returncode, 2)
        self.assertIn("git diff 失败", r.stderr)

    def test_merge_base_semantics(self):
        # base 分支在 HEAD 之后又前进了：triple-dot 只看本分支自 merge-base 的改动
        self.with_globs("routes/**")
        main = subprocess.run(["git", "-C", self.repo, "symbolic-ref", "--short", "HEAD"],
                              capture_output=True, text=True, check=True).stdout.strip()
        run_git(self.repo, "checkout", "-q", "-b", "feature")
        write(self.repo, "docs/a.md", "x\n")
        commit_all(self.repo, "docs only")
        run_git(self.repo, "checkout", "-q", main)
        write(self.repo, "routes/web.php", "<?php\n")
        commit_all(self.repo, "main moved")
        run_git(self.repo, "checkout", "-q", "feature")
        r = tier_check(self.repo, base=main)
        self.assertEqual(r.returncode, 0, r.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=1)
