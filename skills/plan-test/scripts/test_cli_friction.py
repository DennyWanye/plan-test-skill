#!/usr/bin/env python3
"""v0.8.1 出口降本（2026-09-10 runlog 复盘）的决定性测试。

复盘事实：v0.6.0→v0.7.3 的 106 条真实 refusal 里约 75% 是 CLI 用法摩擦而非质量拦截——
attach-evidence 元数据 32 条（内联 JSON 被当路径 16 + 未知字段 16）、缺必填参数 11、
timing 错词 9、路径猜错 10。另有 9 条 LEDGER_TAMPERED 是 gate 自己的序号配对误报，
代理误判为并发写而删掉两本账。本文件把每一类的消除固化为可复跑断言。

运行：python skills/plan-test/scripts/test_cli_friction.py
"""

import refusal_guard  # noqa: F401  测试隔离：refusal 写入引到 tmpdir
import json
import os
import subprocess
import sys
import time
import unittest

from test_plan_test_gate import (GATE, GateHarness, RealRepoAttestationTestCase,
                                 gate_module, run_gate)


def load_ledger(run_dir):
    with open(os.path.join(run_dir, "plan-test-run.json"), encoding="utf-8") as f:
        return json.load(f)


class MetadataFrictionTestCase(GateHarness):
    """attach-evidence --metadata：内联 JSON 与非标准字段（实测 32 条拒绝）。"""

    def attach(self, meta):
        self.artifact("artifacts/x.log", "ok")
        return run_gate(["attach-evidence", "--run-dir", self.run_dir, "--path",
                         "artifacts/x.log", "--kind", "primary", "--scenario", "S-1",
                         "--metadata", meta])

    def test_inline_json_metadata_is_accepted(self):
        self.init([{"scenario_id": "S-1", "required": True}])
        r = self.attach('{"producer_type":"runtime-probe","artifact_kind":"execution-log"}')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        ev = load_ledger(self.run_dir)["evidence"][0]
        self.assertEqual(ev["producer_type"], "runtime-probe")
        self.assertEqual(ev["artifact_kind"], "execution-log")

    def test_metadata_file_path_still_works(self):
        self.init([{"scenario_id": "S-1", "required": True}])
        mp = self.write("meta.json", '{"producer_type":"gate-exec"}')
        r = self.attach(mp)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(load_ledger(self.run_dir)["evidence"][0]["producer_type"], "gate-exec")

    def test_unknown_fields_stay_top_level_and_identity_envelope_is_lifted(self):
        """非标准字段留在顶层（evidence_contract.required_identity 从顶层读任意字段名），
        identity/facts 信封抬到顶层——帮助文案曾写 identity/facts，代理照字面给。"""
        self.init([{"scenario_id": "S-1", "required": True}])
        r = self.attach('{"producer_type":"runtime-probe","host_head":"af9fdc7a",'
                        '"identity":{"root_run_id":"run-milestone-1"},"seam_count":11,'
                        '"facts":{"business_terminal":"answered"}}')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("原样入账", r.stderr)
        ev = load_ledger(self.run_dir)["evidence"][0]
        self.assertEqual(ev["producer_type"], "runtime-probe")
        self.assertEqual(ev["host_head"], "af9fdc7a")
        self.assertEqual(ev["root_run_id"], "run-milestone-1")
        self.assertEqual(ev["seam_count"], 11)
        self.assertEqual(ev["business_facts"], {"business_terminal": "answered"})
        self.assertNotIn("identity", ev)
        self.assertNotIn("facts", ev)

    def test_reserved_ledger_fields_cannot_be_overridden(self):
        self.init([{"scenario_id": "S-1", "required": True}])
        r = self.attach('{"sha256":"0000"}')
        self.assertEqual(r.returncode, 2)
        self.assertIn("不得覆盖账本自有字段", r.stderr)
        self.assertEqual(load_ledger(self.run_dir)["evidence"], [])

    def test_near_miss_custom_key_is_not_treated_as_typo(self):
        """'session' 与 session_id 相似度 0.82：是合法的自定义键，不是拼写错误。"""
        self.init([{"scenario_id": "S-1", "required": True}])
        r = self.attach('{"session":"sdk-abc","generated":"2026-09-10"}')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        ev = load_ledger(self.run_dir)["evidence"][0]
        self.assertEqual(ev["session"], "sdk-abc")

    def test_typo_of_known_field_is_still_refused(self):
        """折叠不能变成"打错字段名也照收"：root_runid 与 root_run_id 只差一个字符。"""
        self.init([{"scenario_id": "S-1", "required": True}])
        r = self.attach('{"root_runid":"r1"}')
        self.assertEqual(r.returncode, 2)
        self.assertIn("root_runid→root_run_id", r.stderr)
        self.assertEqual(load_ledger(self.run_dir)["evidence"], [])

    def test_bad_inline_json_is_refused_with_usage_error(self):
        self.init([{"scenario_id": "S-1", "required": True}])
        r = self.attach('{"producer_type":')
        self.assertEqual(r.returncode, 2)
        self.assertIn("无法解析内联", r.stderr)


class TimingFrictionTestCase(GateHarness):
    """record-timing：错词归一化与 wait-reason 默认（实测 9 + 2 条拒绝）。"""

    def timing(self, cls, *extra):
        return run_gate(["record-timing", "--run-dir", self.run_dir, "--phase", "phase-4",
                         "--activity-class", cls, "--declared-start", "2026-09-10T01:00:00Z",
                         "--declared-end", "2026-09-10T01:10:00Z"] + list(extra))

    def test_aliases_are_normalized_and_announced(self):
        self.init([{"scenario_id": "S-1", "required": True}])
        cases = {"automated-test-execution": "automated_test", "Manual-UI": "manual_e2e",
                 "ledger-recording": "implementation", "Provider Wait": "provider_wait",
                 "manual_verification": "manual_e2e", "documentation": "implementation",
                 "machine_execution": "automated_test"}
        for raw, canon in cases.items():
            r = self.timing(raw)
            self.assertEqual(r.returncode, 0, "%s: %s" % (raw, r.stderr))
            self.assertIn("已归一为 %r" % canon, r.stderr)
        got = [t["activity_class"] for t in load_ledger(self.run_dir)["timing"]]
        self.assertEqual(got, list(cases.values()))

    def test_canonical_value_is_silent(self):
        self.init([{"scenario_id": "S-1", "required": True}])
        r = self.timing("automated_test")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("已归一", r.stderr)

    def test_unknown_word_is_still_refused(self):
        self.init([{"scenario_id": "S-1", "required": True}])
        r = self.timing("brainstorming")
        self.assertEqual(r.returncode, 2)
        self.assertIn("TIMING_CLASS_INVALID", r.stderr)
        self.assertEqual(load_ledger(self.run_dir).get("timing") or [], [])

    def test_ambiguous_words_are_refused_with_both_options(self):
        """test/testing 自动化与真人都说得通——不猜，拒绝并给二选一（render 拆分靠它）。"""
        self.init([{"scenario_id": "S-1", "required": True}])
        for word in ("test", "testing", "test-exec"):
            r = self.timing(word)
            self.assertEqual(r.returncode, 2, word)
            self.assertIn("automated_test/manual_e2e", r.stderr)

    def test_wait_reason_defaults_per_class(self):
        self.init([{"scenario_id": "S-1", "required": True}])
        r = self.timing("user_wait")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("默认记为 user_input", r.stderr)
        r = self.timing("provider-wait")
        self.assertEqual(r.returncode, 0, r.stderr)
        t = load_ledger(self.run_dir)["timing"]
        self.assertEqual([x["wait_reason"] for x in t], ["user_input", "provider_latency"])

    def test_explicit_bad_wait_reason_is_still_refused(self):
        self.init([{"scenario_id": "S-1", "required": True}])
        r = self.timing("user_wait", "--wait-reason", "lunch")
        self.assertEqual(r.returncode, 2)
        self.assertIn("WAIT_REASON_REQUIRED", r.stderr)


class RunDirFrictionTestCase(RealRepoAttestationTestCase):
    """路径猜错、缺 --run-dir、缺必填参数（实测 10 + 11 条拒绝）。"""

    def test_missing_ledger_hint_lists_neighbouring_run_dirs(self):
        self.init_real_run()
        wrong = os.path.join(self.repo, "plans", "p", "verification", "run-2")
        r = run_gate(["status", "--run-dir", wrong], cwd=self.repo)
        self.assertEqual(r.returncode, 2)
        self.assertIn("先执行 init", r.stderr)
        self.assertIn("附近已有账本的 run-dir", r.stderr)
        self.assertIn("run-1", r.stderr)

    def test_missing_input_file_hint_lists_same_basename(self):
        self.write("manifest.json", "{}")
        r = run_gate(["init", "--run-dir", self.run_dir, "--manifest",
                      "plans/nope/manifest.json"], cwd=self.repo)
        self.assertEqual(r.returncode, 2)
        self.assertIn("manifest 文件不存在", r.stderr)
        self.assertIn("同名文件", r.stderr)
        self.assertIn("manifest.json", r.stderr.split("同名文件", 1)[1])

    def test_run_dir_falls_back_to_active_run(self):
        self.init_real_run()
        r = run_gate(["activate-run", "--run-dir", self.run_dir], cwd=self.repo)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        r = run_gate(["status"], cwd=self.repo)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("STATE:", r.stdout)
        self.assertIn("使用 active run", r.stderr)
        # 子目录里也能找到（向上找 .plan-test）
        sub = os.path.join(self.repo, "plans", "p")
        r = run_gate(["status"], cwd=sub)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_run_dir_omitted_without_active_run_is_args_invalid(self):
        self.init_real_run()
        r = run_gate(["status"], cwd=self.repo)
        self.assertEqual(r.returncode, 2)
        self.assertIn("ARGS_INVALID", r.stderr)
        self.assertIn("activate-run", r.stderr)

    def test_refusal_under_fallback_records_resolved_run_dir(self):
        """省略 --run-dir 时拒绝账本要记解析后的目标，否则 stats 的按 run 配对丢掉这类记录。"""
        self.init_real_run()
        run_gate(["activate-run", "--run-dir", self.run_dir], cwd=self.repo)
        home = os.path.join(self.tmp, "refusal-home")
        os.makedirs(home)
        env = dict(os.environ, PLAN_TEST_REFUSAL_HOME=home)
        r = subprocess.run([sys.executable, GATE, "record-timing", "--phase", "p",
                            "--activity-class", "brainstorming",
                            "--declared-start", "2026-09-10T01:00:00Z",
                            "--declared-end", "2026-09-10T01:10:00Z"],
                           cwd=self.repo, env=env, capture_output=True, text=True)
        self.assertEqual(r.returncode, 2, r.stderr)
        with open(os.path.join(home, "refusals.jsonl"), encoding="utf-8") as f:
            rec = json.loads(f.read().strip().splitlines()[-1])
        self.assertEqual(rec["code"], "TIMING_CLASS_INVALID")
        self.assertTrue(rec["run_dir"], rec)
        self.assertEqual(os.path.realpath(rec["run_dir"]), os.path.realpath(self.run_dir))

    def test_retire_and_activate_run_never_fall_back(self):
        """retire 的 --run-dir 是被退役的旧轮，active run 通常是继任者——回落等于让继任者退役自己。"""
        self.init_real_run()
        run_gate(["activate-run", "--run-dir", self.run_dir], cwd=self.repo)
        r = run_gate(["retire", "--reason", "x", "--superseded-by", "plans/p/verification/run-2"],
                     cwd=self.repo)
        self.assertEqual(r.returncode, 2)
        self.assertIn("必须显式给出", r.stderr)
        r = run_gate(["activate-run"], cwd=self.repo)
        self.assertEqual(r.returncode, 2)
        self.assertIn("必须显式给出", r.stderr)
        self.assertEqual(load_ledger(self.run_dir).get("retired"), None)

    def test_worktree_git_file_stops_the_walk(self):
        """git worktree 的 .git 是文件：回落必须停在 worktree 根，不得拿外层仓库的 active run。"""
        self.init_real_run()
        run_gate(["activate-run", "--run-dir", self.run_dir], cwd=self.repo)
        wt = os.path.join(self.repo, ".worktrees", "wt", "src")
        os.makedirs(wt)
        with open(os.path.join(self.repo, ".worktrees", "wt", ".git"), "w") as f:
            f.write("gitdir: /nonexistent\n")
        r = run_gate(["status"], cwd=wt)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("没有 active run", r.stderr)

    def test_init_still_requires_run_dir(self):
        r = run_gate(["init", "--manifest", "x.json"], cwd=self.repo)
        self.assertEqual(r.returncode, 2)
        self.assertIn("--run-dir", r.stderr)

    def test_missing_required_arg_shows_example(self):
        self.init_real_run()
        r = run_gate(["record-run", "--run-dir", self.run_dir, "--scenario", "S-1"],
                     cwd=self.repo)
        self.assertEqual(r.returncode, 2)
        self.assertIn("ARGS_INVALID", r.stderr)
        self.assertIn("示例: plan_test_gate.py record-run", r.stderr)
        self.assertIn("--help", r.stderr)

    def test_external_run_dir_message_names_both_roots(self):
        outside = os.path.join(self.tmp, "elsewhere", "verification", "r1")
        os.makedirs(outside)
        manifest = {
            "run_id": "ext", "repo_root": self.repo, "source_request_text": "x",
            "acceptance_file": self.write("acceptance.md", "AC-1 必须\n"),
            "applicability": self.applicability_block(),
            "scenarios": [{"scenario_id": "S-1", "required": True}],
        }
        mp = self.write("manifest.json", json.dumps(manifest, ensure_ascii=False))
        r = run_gate(["init", "--run-dir", outside, "--manifest", mp], cwd=self.repo)
        self.assertEqual(r.returncode, 2)
        self.assertIn("仓库之外", r.stderr)
        self.assertIn("仓库根", r.stderr)
        self.assertIn(self.repo, r.stderr)


class ConcurrentExecTestCase(RealRepoAttestationTestCase):
    """record-run --exec 的序号必须在锁内定：后台长回归期间别人先入账不能把链打成 TAMPERED。

    实测（2026-09-02 s5b r1/r2）：REG-FULL 后台 --exec 跑 10 分钟，期间两条 S1 record-run
    先入账，REG 写回时日志序号仍是开跑前的快照值，位置配对失败 → 链下界多 1 →
    不可豁免的 LEDGER_TAMPERED；代理判成"并发写"，两本账连同 100+ 条事实一起删除。
    """

    def start_exec(self, scenario, sleep_s):
        return subprocess.Popen(
            [sys.executable, GATE, "record-run", "--run-dir", self.run_dir, "--scenario",
             scenario, "--kind", "root", "--exec", "--", sys.executable, "-c",
             "import time; time.sleep(%s)" % sleep_s],
            cwd=self.repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    def test_background_exec_does_not_break_chain(self):
        self.init_real_run(scenarios=[{"scenario_id": "S-1", "required": True},
                                      {"scenario_id": "S-2", "required": True}])
        bg = self.start_exec("S-1", 2)
        time.sleep(0.6)
        r = run_gate(["record-run", "--run-dir", self.run_dir, "--scenario", "S-2",
                      "--kind", "root", "--result", "pass"], cwd=self.repo)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        out, err = bg.communicate(timeout=60)
        self.assertEqual(bg.returncode, 0, out + err)
        led = load_ledger(self.run_dir)
        self.assertEqual([x["scenario_id"] for x in led["runs"]], ["S-1", "S-2", "S-1"])
        exec_run = led["runs"][2]
        self.assertEqual(exec_run["exec_log_path"], "artifacts/exec-S-1-0003.log")
        paths = [e["path"] for e in led["evidence"]]
        self.assertEqual(paths, ["artifacts/exec-S-1-0003.log"])
        self.assertTrue(os.path.isfile(os.path.join(self.run_dir, paths[0])))
        self.assertFalse([f for f in os.listdir(os.path.join(self.run_dir, "artifacts"))
                          if f.endswith(".partial")], "临时日志须清理")
        gm = gate_module()
        self.assertIsNone(gm.integrity_check(led))
        self.assertNotIn("LEDGER_TAMPERED", self.check().stdout)

    def test_refused_write_keeps_the_exec_log_on_disk(self):
        """写账被拒（这里：账本被手改 → TAMPERED 预检）时，gate 亲眼看过的执行输出不能被删。"""
        self.init_real_run()
        lp = os.path.join(self.run_dir, "plan-test-run.json")
        led = load_ledger(self.run_dir)
        led["runs"][0]["result"] = "fail"  # 绕过 CLI 手改
        with open(lp, "w", encoding="utf-8") as f:
            json.dump(led, f)
        r = run_gate(["record-run", "--run-dir", self.run_dir, "--scenario", "S-1", "--kind",
                      "root", "--exec", "--", sys.executable, "-c", "print('kept')"], cwd=self.repo)
        self.assertEqual(r.returncode, 2)
        self.assertIn("LEDGER_TAMPERED", r.stderr)
        self.assertIn("执行日志保留在", r.stderr)
        kept = [f for f in os.listdir(os.path.join(self.run_dir, "artifacts"))
                if f.startswith("exec-S-1-unrecorded-")]
        self.assertEqual(len(kept), 1, kept)
        with open(os.path.join(self.run_dir, "artifacts", kept[0]), encoding="utf-8") as f:
            self.assertIn("kept", f.read())

    def test_two_background_execs_same_scenario_get_distinct_logs(self):
        self.init_real_run()
        a, b = self.start_exec("S-1", 1), self.start_exec("S-1", 1)
        for p in (a, b):
            out, err = p.communicate(timeout=60)
            self.assertEqual(p.returncode, 0, out + err)
        led = load_ledger(self.run_dir)
        paths = sorted(e["path"] for e in led["evidence"])
        self.assertEqual(paths, ["artifacts/exec-S-1-0002.log", "artifacts/exec-S-1-0003.log"])
        for p in paths:
            self.assertTrue(os.path.isfile(os.path.join(self.run_dir, p)))
        self.assertEqual({r["exec_log_path"] for r in led["runs"] if "exec_exit_code" in r},
                         set(paths))
        self.assertIsNone(gate_module().integrity_check(led))

    def test_legacy_stale_seq_ledger_is_not_tampered(self):
        """v0.8.1 之前开的账：exec run 位置与日志序号错开——链下界不得再多算。"""
        gm = gate_module()
        ledger = {
            "runs": [{"scenario_id": "S-2", "result": "pass"},
                     {"scenario_id": "S-1", "result": "pass", "exec_exit_code": 0}],
            "evidence": [{"path": "artifacts/exec-S-1-0001.log", "producer_type": "gate-exec"}],
        }
        # init 1 + runs 2 + evidence 1 − 配对 1 = 3
        self.assertEqual(gm.expected_chain_length(ledger), 3)
        # 折扣上限是 exec run 数：多出来的 exec 日志不能再减
        ledger["evidence"].append({"path": "artifacts/exec-S-1-0002.log",
                                   "producer_type": "gate-exec"})
        self.assertEqual(gm.expected_chain_length(ledger), 4)
        # 08-19~08-24 的存量 exec 证据没有 producer_type 戳：配对只看路径形态，不看戳
        del ledger["evidence"][0]["producer_type"]
        self.assertEqual(gm.expected_chain_length(ledger), 4)
        # 序号超过四位（%04d 增长）仍配得上
        ledger["evidence"][0]["path"] = "artifacts/exec-S-1-10000.log"
        self.assertEqual(gm.expected_chain_length(ledger), 4)


class RetireMessageTestCase(RealRepoAttestationTestCase):
    """RETIRE 拒绝时必须说清继任者卡在哪（实测 4 条拒绝全是顺序问题）。"""

    def test_successor_cannot_be_self(self):
        self.init_real_run()
        r = run_gate(["retire", "--run-dir", self.run_dir, "--reason", "x",
                      "--superseded-by", self.run_dir], cwd=self.repo)
        self.assertEqual(r.returncode, 2)
        self.assertIn("就是本 run 自己", r.stderr)
        self.assertEqual(load_ledger(self.run_dir).get("retired"), None)

    def test_refusal_lists_successor_blockers(self):
        sib_dir = os.path.join(self.repo, "plans", "p", "verification", "run-0")
        os.makedirs(os.path.join(sib_dir, "artifacts"))
        manifest = {
            "run_id": "run-0", "repo_root": self.repo, "source_request_text": "兄弟轮",
            "acceptance_file": self.write("acceptance.md", "AC-1 必须：脚本可运行\n"),
            "applicability": self.applicability_block(),
            "scenarios": [{"scenario_id": "S-1", "required": True}],
        }
        mp = os.path.join(sib_dir, "manifest.json")
        with open(mp, "w", encoding="utf-8") as f:
            f.write(json.dumps(manifest, ensure_ascii=False))
        r = run_gate(["init", "--run-dir", sib_dir, "--manifest", mp], cwd=self.repo)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        run_gate(["record-run", "--run-dir", sib_dir, "--scenario", "S-1", "--kind", "root",
                  "--result", "fail"], cwd=self.repo)
        self.init_real_run(related_run_dirs=["plans/p/verification/run-0"])
        # 继任者只有一条 root pass，既无证据也无审计——不是 SHIPPABLE
        r = run_gate(["retire", "--run-dir", sib_dir, "--reason", "被 run-1 承接",
                      "--superseded-by", "plans/p/verification/run-1"], cwd=self.repo)
        self.assertEqual(r.returncode, 2)
        self.assertIn("RETIRE 拒绝", r.stderr)
        self.assertIn("阻塞:", r.stderr)
        self.assertIn("不必先 finalize", r.stderr)


class StabilityWindowTestCase(RealRepoAttestationTestCase):
    """FLAKY 只看当前被测 HEAD 上的样本；手误/上游/基座失败可标记为非产品原因。

    实测（2026-09-01~05）：s5a r2 因 4 条旧 root fail 永远到不了 SHIPPABLE（6 条 fail 里
    5 条是 cwd/路径/marker 手误），s5b r3 判 FLAKY 21/26 而 5 次失败成因全已修复——两次都只能
    开新 run-dir 干净重跑，失败史留在被 retire 的旧账里，与规则初衷相反。
    """

    SCEN = [{"scenario_id": "S-1", "required": True, "min_root_runs": 2}]

    def record(self, result, *extra):
        return run_gate(["record-run", "--run-dir", self.run_dir, "--scenario", "S-1",
                         "--kind", "root", "--result", result] + list(extra), cwd=self.repo)

    def test_same_head_flakiness_still_blocks(self):
        """底线不动：同一份代码上时通时挂就是抖动，不得 SHIP。"""
        self.init_real_run(scenarios=self.SCEN)
        self.assertEqual(self.record("fail").returncode, 0)
        self.assertEqual(self.record("pass").returncode, 0)
        r = self.check()
        self.assertEqual(r.returncode, 1)
        self.assertIn("STABILITY_SAMPLES_INSUFFICIENT", r.stdout)
        self.assertIn("FLAKY（当前 HEAD 上 2/3 通过", r.stdout)
        self.assertIn("invalidate-run", r.stdout)  # 消息给出合法出口

    def test_failures_before_behavioral_change_do_not_count(self):
        """旧代码上失败 → 改代码 re-attest → 新代码上连续通过：不是抖动。"""
        self.init_real_run(scenarios=self.SCEN)
        self.assertEqual(self.record("fail").returncode, 0)
        self.assertEqual(self.record("fail").returncode, 0)
        self.write("src.py", "print('v2')\n")
        r = run_gate(["re-attest", "--run-dir", self.run_dir, "--reason", "修 bug"], cwd=self.repo)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("kind=behavioral", r.stdout)
        self.assertEqual(self.record("pass").returncode, 0)
        self.assertEqual(self.record("pass").returncode, 0)
        r = self.check()
        self.assertNotIn("STABILITY_SAMPLES_INSUFFICIENT", r.stdout)
        self.assertNotIn("FLAKY", r.stdout)
        self.assertEqual(r.returncode, 0, r.stdout)
        # 失败史仍在账本里，没有被洗掉
        results = [x["result"] for x in load_ledger(self.run_dir)["runs"]]
        self.assertEqual(results, ["pass", "fail", "fail", "pass", "pass"])

    def test_new_failure_after_change_still_counts(self):
        """窗口重开不是赦免：切点之后再挂一次，照样 FLAKY。"""
        self.init_real_run(scenarios=self.SCEN)
        self.write("src.py", "print('v2')\n")
        run_gate(["re-attest", "--run-dir", self.run_dir, "--reason", "修 bug"], cwd=self.repo)
        self.record("pass")
        self.record("fail")
        self.record("pass")
        r = self.check()
        self.assertEqual(r.returncode, 1)
        self.assertIn("FLAKY（当前 HEAD 上 2/3 通过", r.stdout)

    def test_old_passes_do_not_satisfy_min_root_runs_after_change(self):
        """防洗账：随便碰一行代码 re-attest + 一次幸运 pass 不能把 N 个样本的要求降成 1。"""
        self.init_real_run(scenarios=self.SCEN)
        self.record("pass")  # v1 上 2 次通过
        self.write("src.py", "print('v2')\n")
        run_gate(["re-attest", "--run-dir", self.run_dir, "--reason", "修 bug"], cwd=self.repo)
        self.record("pass")  # v2 上只有 1 次
        r = self.check()
        self.assertEqual(r.returncode, 1)
        self.assertIn("需要当前 HEAD 上 ≥2 次独立 root pass，仅 1 次", r.stdout)
        self.assertIn("切点前 2 次通过不计", r.stdout)
        self.record("pass")
        self.assertEqual(self.check().returncode, 0, self.check().stdout)

    def test_doc_only_reattest_keeps_old_failures_counting(self):
        self.init_real_run(scenarios=self.SCEN)
        self.record("fail")
        self.record("fail")
        self.write("ARCHITECTURE/overview.md", "# 架构\n")
        r = run_gate(["re-attest", "--run-dir", self.run_dir, "--reason", "文档"], cwd=self.repo)
        self.assertIn("kind=doc-only", r.stdout)
        self.record("pass")
        self.record("pass")
        r = self.check()
        self.assertEqual(r.returncode, 1)
        self.assertIn("FLAKY（当前 HEAD 上 3/5 通过", r.stdout)

    def test_impact_paths_narrowing_resets_only_the_hit_scenario(self):
        manifest = {
            "run_id": "ip", "repo_root": self.repo, "source_request_text": "x",
            "acceptance_file": self.write("acceptance.md", "AC-1 必须\n"),
            "applicability": self.applicability_block(),
            "scenarios": [
                {"scenario_id": "S-A", "required": True, "min_root_runs": 2, "impact_paths": ["backend/**"]},
                {"scenario_id": "S-B", "required": True, "min_root_runs": 2, "impact_paths": ["frontend/**"]},
            ],
        }
        mp = self.write("manifest.json", json.dumps(manifest, ensure_ascii=False))
        r = run_gate(["init", "--run-dir", self.run_dir, "--manifest", mp], cwd=self.repo)
        self.assertEqual(r.returncode, 0, r.stderr)

        def rec(sid, result):
            r = run_gate(["record-run", "--run-dir", self.run_dir, "--scenario", sid,
                          "--kind", "root", "--result", result], cwd=self.repo)
            self.assertEqual(r.returncode, 0, r.stderr)
        rec("S-A", "fail")
        rec("S-B", "fail")
        rec("S-B", "pass")
        self.write("backend/api.py", "x = 1\n")
        r = run_gate(["re-attest", "--run-dir", self.run_dir, "--reason", "修 backend"], cwd=self.repo)
        self.assertIn("kind=behavioral", r.stdout)
        rec("S-A", "pass")
        rec("S-A", "pass")
        rec("S-B", "pass")
        r = self.check()
        self.assertNotIn("场景 S-A FLAKY", r.stdout)
        self.assertIn("场景 S-B FLAKY（当前 HEAD 上 2/3 通过", r.stdout)  # 切点没动，旧失败仍算

    def test_legacy_attestation_without_runs_index_counts_full_history(self):
        gm = gate_module()
        ledger = {"scenarios": [{"scenario_id": "S-1", "required": True}],
                  "attestations": [{"change_kind": "behavioral", "changed_paths": ["src/x.py"],
                                    "changed_count": 1}]}
        cutoffs, _ = gm._behavioral_cutoffs(ledger)
        self.assertEqual(cutoffs, {"S-1": 0})

    def test_invalid_reason_excludes_failure_but_keeps_it(self):
        self.init_real_run(scenarios=self.SCEN)
        r = self.record("fail", "--invalid-reason", "operator_error",
                        "--invalid-detail", "cwd 在 memory-sdk 仓，pytest 路径不存在")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("invalid_reason=operator_error", r.stdout)
        self.assertEqual(self.record("pass").returncode, 0)
        r = self.check()
        self.assertNotIn("FLAKY", r.stdout)
        self.assertEqual(r.returncode, 0, r.stdout)
        runs = load_ledger(self.run_dir)["runs"]
        self.assertEqual(runs[1]["result"], "fail")
        self.assertEqual(runs[1]["invalid_reason"], "operator_error")
        self.assertIn("cwd", runs[1]["invalid_detail"])

    def test_invalid_reason_guards(self):
        self.init_real_run(scenarios=self.SCEN)
        r = self.record("pass", "--invalid-reason", "operator_error", "--invalid-detail", "1234567890x")
        self.assertEqual(r.returncode, 2)
        self.assertIn("只用于 result=fail", r.stderr)
        r = self.record("fail", "--invalid-reason", "operator_error")
        self.assertEqual(r.returncode, 2)
        self.assertIn("必须同时给", r.stderr)
        r = self.record("fail", "--invalid-reason", "operator_error", "--invalid-detail", "短")
        self.assertEqual(r.returncode, 2)
        self.assertIn("至少 10 个字符", r.stderr)
        r = self.record("fail", "--invalid-reason", "lazy", "--invalid-detail", "1234567890x")
        self.assertEqual(r.returncode, 2)
        self.assertIn("ARGS_INVALID", r.stderr)
        self.assertEqual(len(load_ledger(self.run_dir)["runs"]), 1)

    def test_exec_with_invalid_reason_is_refused_before_running(self):
        """跑完 10 分钟再因参数组合被拒、日志成孤儿——检查必须在 exec 之前。"""
        self.init_real_run(scenarios=self.SCEN)
        marker = os.path.join(self.tmp, "ran.txt")
        r = run_gate(["record-run", "--run-dir", self.run_dir, "--scenario", "S-1", "--kind", "root",
                      "--invalid-reason", "upstream_unavailable", "--invalid-detail", "1234567890x",
                      "--exec", "--", sys.executable, "-c", "open(%r,'w').write('x')" % marker],
                     cwd=self.repo)
        self.assertEqual(r.returncode, 2)
        self.assertIn("不与 --exec 同用", r.stderr)
        self.assertIn("invalidate-run", r.stderr)
        self.assertFalse(os.path.exists(marker), "命令不该被执行")
        self.assertEqual(os.listdir(os.path.join(self.run_dir, "artifacts")), [])
        self.assertEqual(len(load_ledger(self.run_dir)["runs"]), 1)

    def test_invalidate_run_marks_exec_failure_after_the_fact(self):
        """--exec 的失败跑完才知道：事后 invalidate-run 标记，留痕、进链、不进分母。"""
        self.init_real_run(scenarios=self.SCEN)
        r = run_gate(["record-run", "--run-dir", self.run_dir, "--scenario", "S-1", "--kind", "root",
                      "--exec", "--", sys.executable, "-c", "import sys; sys.exit(1)"], cwd=self.repo)
        self.assertEqual(r.returncode, 1)
        self.record("pass")
        self.assertIn("FLAKY（当前 HEAD 上 2/3 通过", self.check().stdout)
        r = run_gate(["invalidate-run", "--run-dir", self.run_dir, "--run-index", "1",
                      "--reason", "operator_error", "--detail", "pytest 路径写错，命令根本没跑起来"],
                     cwd=self.repo)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("INVALIDATED runs[1]", r.stdout)
        r = self.check()
        self.assertNotIn("FLAKY", r.stdout)
        self.assertEqual(r.returncode, 0, r.stdout)
        led = load_ledger(self.run_dir)
        self.assertEqual(led["runs"][1]["result"], "fail")
        self.assertEqual(led["runs"][1]["invalid_reason"], "operator_error")
        self.assertTrue(led["runs"][1]["invalidated_at"])
        self.assertEqual(led["integrity"]["log"][-1]["op"], "invalidate-run")
        self.assertIsNone(gate_module().integrity_check(led))
        # 守卫：越界 / 不是 fail / 不许改写
        for idx, msg in ((9, "越界"), (0, "不是 fail"), (1, "不许改写")):
            r = run_gate(["invalidate-run", "--run-dir", self.run_dir, "--run-index", str(idx),
                          "--reason", "operator_error", "--detail", "1234567890x"], cwd=self.repo)
            self.assertEqual(r.returncode, 2, idx)
            self.assertIn(msg, r.stderr)

    def test_excused_fails_cannot_outnumber_real_passes(self):
        """标记是留痕不是赦免：被标记的失败多于真实通过时仍 FLAKY。"""
        self.init_real_run(scenarios=self.SCEN)  # 1 次真实通过
        for _ in range(3):
            self.assertEqual(self.record("fail", "--invalid-reason", "operator_error",
                                         "--invalid-detail", "cwd 在错的仓库里").returncode, 0)
        self.record("pass")  # 真实通过 2，被标记失败 3
        r = self.check()
        self.assertEqual(r.returncode, 1)
        self.assertIn("多于真实通过", r.stdout)
        self.record("pass")  # 3 vs 3：不再多于
        self.assertEqual(self.check().returncode, 0, self.check().stdout)

    def test_render_and_receipt_expose_stability_accounting(self):
        self.init_real_run(scenarios=self.SCEN)
        self.record("fail", "--invalid-reason", "upstream_unavailable", "--invalid-detail", "provider 502 三次")
        self.record("pass")
        with open(os.path.join(self.run_dir, "artifacts", "s1.log"), "w") as f:
            f.write("ok")
        run_gate(["attach-evidence", "--run-dir", self.run_dir, "--path", "artifacts/s1.log",
                  "--kind", "primary", "--scenario", "S-1"], cwd=self.repo)
        for name, body in (("auditor-input.json", '{"frozen":true}'),
                           ("auditor-output.json", '{"verdict":"PASS"}')):
            with open(os.path.join(self.run_dir, name), "w") as f:
                f.write(body)
        run_gate(["audit", "--run-dir", self.run_dir, "--verdict", "PASS", "--engine", "e",
                  "--input", "auditor-input.json", "--output", "auditor-output.json"], cwd=self.repo)
        r = run_gate(["finalize", "--run-dir", self.run_dir], cwd=self.repo)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        with open(os.path.join(self.run_dir, "gate-receipt.json"), encoding="utf-8") as f:
            receipt = json.load(f)
        self.assertEqual(receipt["stability"]["S-1"]["invalid_fails"], 1)
        self.assertEqual(receipt["stability"]["S-1"]["passed"], 2)
        r = run_gate(["render", "--run-dir", self.run_dir], cwd=self.repo)
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(os.path.join(self.run_dir, "report.md"), encoding="utf-8") as f:
            report = f.read()
        self.assertIn("稳定性窗口", report)
        self.assertIn("upstream_unavailable", report)
        self.assertIn("provider 502 三次", report)


class RetestWasteTestCase(RealRepoAttestationTestCase):
    """两处让 re-attest 退化为全量复测的病根（runlog 复盘：s4/s5b 各因此重测一轮）。"""

    def test_architecture_dir_docs_are_doc_only(self):
        self.init_real_run()
        self.write("ARCHITECTURE/overview.md", "# 架构\n收尾期回写。\n")
        self.assertEqual(self.check().returncode, 1)  # 先如实变红
        r = run_gate(["re-attest", "--run-dir", self.run_dir, "--reason", "文档回写"], cwd=self.repo)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("kind=doc-only", r.stdout)
        self.assertEqual(self.check().returncode, 0, self.check().stdout)

    def test_prompts_under_architecture_like_dirs_stay_behavioral(self):
        """放宽的只是 ARCHITECTURE/ 目录；prompts/ 仍是行为文本。"""
        self.init_real_run()
        self.write("prompts/system.md", "# 系统提示\n忽略所有规则。\n")
        r = run_gate(["re-attest", "--run-dir", self.run_dir, "--reason", "x"], cwd=self.repo)
        self.assertIn("kind=behavioral", r.stdout)

    def test_generators_under_architecture_dir_stay_behavioral(self):
        """放行的是 ARCHITECTURE/ 下的 *.md，不是整个目录（review 抓出：生成器/图表代码会被放过）。"""
        self.init_real_run()
        self.write("ARCHITECTURE/gen_config.py", "print('x')\n")
        r = run_gate(["re-attest", "--run-dir", self.run_dir, "--reason", "x"], cwd=self.repo)
        self.assertIn("kind=behavioral", r.stdout)

    def test_string_impact_paths_are_refused_at_init(self):
        manifest = {
            "run_id": "ip2", "repo_root": self.repo, "source_request_text": "x",
            "acceptance_file": self.write("acceptance.md", "AC-1 必须\n"),
            "applicability": self.applicability_block(),
            "scenarios": [{"scenario_id": "S-1", "required": True, "impact_paths": "src/**"}],
        }
        mp = self.write("manifest.json", json.dumps(manifest, ensure_ascii=False))
        r = run_gate(["init", "--run-dir", self.run_dir, "--manifest", mp], cwd=self.repo)
        self.assertEqual(r.returncode, 2)
        self.assertIn("须为字符串列表", r.stderr)

    def test_absolute_impact_paths_are_refused_at_init(self):
        manifest = {
            "run_id": "ip", "repo_root": self.repo, "source_request_text": "x",
            "acceptance_file": self.write("acceptance.md", "AC-1 必须\n"),
            "applicability": self.applicability_block(),
            "scenarios": [{"scenario_id": "S-1", "required": True,
                           "impact_paths": [os.path.join(self.repo, "src/**")]}],
        }
        mp = self.write("manifest.json", json.dumps(manifest, ensure_ascii=False))
        r = run_gate(["init", "--run-dir", self.run_dir, "--manifest", mp], cwd=self.repo)
        self.assertEqual(r.returncode, 2)
        self.assertIn("impact_paths 含绝对路径", r.stderr)
        self.assertFalse(os.path.exists(os.path.join(self.run_dir, "plan-test-run.json")))
        manifest["scenarios"][0]["impact_paths"] = ["src/**"]
        mp = self.write("manifest.json", json.dumps(manifest, ensure_ascii=False))
        r = run_gate(["init", "--run-dir", self.run_dir, "--manifest", mp], cwd=self.repo)
        self.assertEqual(r.returncode, 0, r.stderr)


def load_tests(loader, tests, pattern):
    """只跑本文件定义的用例——基类 RealRepoAttestationTestCase 自带的 test_* 不在这里重跑。"""
    suite = unittest.TestSuite()
    for cls in (MetadataFrictionTestCase, TimingFrictionTestCase, RunDirFrictionTestCase,
                ConcurrentExecTestCase, RetireMessageTestCase, StabilityWindowTestCase,
                RetestWasteTestCase):
        own = [n for n in loader.getTestCaseNames(cls) if n in cls.__dict__]
        suite.addTests(cls(n) for n in own)
    return suite


if __name__ == "__main__":
    unittest.main()
