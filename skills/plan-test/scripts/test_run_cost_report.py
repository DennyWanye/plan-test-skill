#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""run_cost_report.py 的决定性测试：合成会话记录，每条钉住一个口径（与 ~/.plan-test 冻结基线 adhoc_stats r5 同源）。"""
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import run_cost_report as rcr

SKILL = "/Users/x/.claude/plugins/plan-test-skill/skills/plan-test/"


def _asst(mid, tools, ctx=1000, out=10, ts="2026-09-24T01:00:00Z"):
    content = [{"type": "tool_use", "id": "t%d" % i, "name": n, "input": inp} for i, (n, inp) in enumerate(tools)]
    return {"type": "assistant", "timestamp": ts, "cwd": "/tmp/nowhere",
            "message": {"id": mid, "usage": {"cache_read_input_tokens": ctx, "input_tokens": 0,
                                                "cache_creation_input_tokens": 0, "output_tokens": out},
                        "content": content}}


def _result(text, ts="2026-09-24T01:00:01Z"):
    return {"type": "user", "timestamp": ts, "message": {"content": [{"type": "tool_result", "content": text}]}}


def _text(t):
    return {"type": "assistant", "message": {"usage": {"output_tokens": 5}, "content": [{"type": "text", "text": t}]}}


class Fixture(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.sid = "abcdef12-0000-0000-0000-000000000000"
        proj = os.path.join(self.root, "-Users-x-proj")
        os.makedirs(os.path.join(proj, self.sid, "subagents"))
        self.main = os.path.join(proj, self.sid + ".jsonl")
        self.subdir = os.path.join(proj, self.sid, "subagents")

    def tearDown(self):
        shutil.rmtree(self.root)

    def write_main(self, rows):
        with open(self.main, "w") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    def write_sub(self, name, first_user, assistant_texts):
        rows = [{"type": "user", "timestamp": "2026-09-24T01:00:00Z", "message": {"content": [{"type": "text", "text": first_user}]}}]
        rows += [_text(t) for t in assistant_texts]
        with open(os.path.join(self.subdir, "agent-%s.jsonl" % name), "w") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    def report(self):
        return rcr.compute(self.sid[:8], self.root)


class TestMainSessionMetrics(Fixture):
    def test_turns_context_and_lone_bash(self):
        self.write_main([
            _asst("m1", [("Bash", {"command": "ls"})], ctx=100),
            _asst("m2", [("Bash", {"command": "ls"}), ("Read", {"file_path": "/a"})], ctx=300),
            _asst("m3", [("Read", {"file_path": "/a"})], ctx=200),
            _asst("m4", [], ctx=400),
        ])
        R = self.report()
        self.assertEqual(R["轮次"], 4)
        self.assertEqual(R["每轮上下文中位"], 300)   # 排序后 [100,200,300,400] 取 idx 2
        self.assertEqual(R["带工具调用消息"], 3)
        self.assertEqual(R["单Bash独占"], 1)
        self.assertEqual(R["单Bash独占比例%"], 33)

    def test_doc_reads_repeats_and_prompts(self):
        rules = SKILL + "RULES.md"
        self.write_main([
            _asst("m1", [("Read", {"file_path": rules})]),
            _asst("m2", [("Read", {"file_path": rules})]),
            _asst("m3", [("Bash", {"command": "cat " + SKILL + "prompts/test-result-evaluator.md"})]),
            _asst("m4", [("Read", {"file_path": SKILL + "phase-1-plan.md"})]),
        ])
        R = self.report()
        self.assertEqual(R["skill文档读取"], 4)
        self.assertEqual(R["重复读取"], 1)
        self.assertEqual(R["非压缩重复读取"], 1)
        self.assertEqual(R["prompts读取"], 1)
        self.assertTrue(R["读过phase文档"])
        self.assertEqual(R["skill文档读取按文件"]["plan-test/RULES.md"], 2)

    def test_reread_of_rules_right_after_compact_is_not_counted_as_repeat(self):
        rules = SKILL + "RULES.md"
        self.write_main([
            _asst("m1", [("Read", {"file_path": rules})]),
            {"type": "user", "isCompactSummary": True, "message": {"content": "summary"}},
            _asst("m2", [("Read", {"file_path": rules})]),
        ])
        R = self.report()
        self.assertEqual(R["压缩事件"], 1)
        self.assertEqual(R["重复读取"], 1)
        self.assertEqual(R["压缩后规则重读"], 1)
        self.assertEqual(R["非压缩重复读取"], 0)

    def test_big_outputs_and_bash_segments(self):
        self.write_main([
            _asst("m1", [("Bash", {"command": "a && b; c\nd"})]),
            _result("x" * 8001),
            _asst("m2", [("Bash", {"command": "cat <<'EOF'\na && b\nEOF"})]),
            _result("short"),
        ])
        R = self.report()
        self.assertEqual(R["大输出次数"], 1)
        self.assertEqual(R["大输出字符"], 8001)
        self.assertEqual(R["Bash段数中位"], 4)   # [1,4] 取 idx 1

    def test_edits_to_skill_dir_and_prompts(self):
        self.write_main([
            _asst("m1", [("Edit", {"file_path": SKILL + "prompts/x.md"})]),
            _asst("m2", [("Bash", {"command": "sed -i '' s/a/b/ " + SKILL + "RULES.md"})]),
            _asst("m3", [("Read", {"file_path": SKILL + "RULES.md"})]),
        ])
        R = self.report()
        self.assertEqual(R["编辑过prompts"], 1)
        self.assertEqual(R["编辑过skill目录"], 2)


class TestSubagentsAndEvalRows(Fixture):
    def test_roles_and_eval_rows_from_text(self):
        self.write_main([_asst("m1", [])])
        self.write_sub("11111111", "你是交接评估员 ROUND: 2", [
            "先说结论。", '{"verdict":"FAIL","findings":[{"id":"F1","fix_class":"硬伤"},{"id":"F2","fix_class":"文字"}]}'])
        self.write_sub("22222222", "你是 challenger，挑战这份 plan", ["ok"])
        self.write_sub("33333333", "你是交接评估员", ["没有 JSON 只有散文"])
        R = self.report()
        self.assertEqual(R["子代理"]["评估"]["个数"], 2)
        self.assertEqual(R["子代理"]["挑战"]["个数"], 1)
        rows = {e["子代理"]: e for e in R["评估行"]}
        self.assertEqual(rows["11111111"]["ROUND"], 2)
        self.assertEqual(rows["11111111"]["verdict"], "FAIL")
        self.assertEqual(rows["11111111"]["硬伤数"], 1)
        self.assertEqual(rows["33333333"]["verdict"], "unparsed")
        self.assertEqual(R["有效评估行"], 1)
        self.assertEqual(R["硬伤合计"], 1)
        self.assertEqual(R["unparsed"], 1)

    def test_eval_row_falls_back_to_file_in_cwd_plans(self):
        cwd = os.path.join(self.root, "repo")
        os.makedirs(os.path.join(cwd, "plans", "f", "handoff"))
        with open(os.path.join(cwd, "plans", "f", "handoff", "eval-1.json"), "w") as f:
            json.dump({"verdict": "PASS", "findings": []}, f)
        now = os.path.getmtime(os.path.join(cwd, "plans", "f", "handoff", "eval-1.json"))
        import datetime
        ts = datetime.datetime.fromtimestamp(now, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        row = _asst("m1", []); row["cwd"] = cwd; row["timestamp"] = ts
        self.write_main([row])
        rows = [{"type": "user", "timestamp": ts, "message": {"content": [{"type": "text", "text": "交接评估员"}]}}, _text("散文")]
        with open(os.path.join(self.subdir, "agent-44444444.jsonl"), "w") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        R = self.report()
        self.assertEqual(R["评估行"][0]["verdict"], "PASS")
        self.assertEqual(R["评估行"][0]["来源"], "file")
        self.assertEqual(R["有效评估行"], 1)


class TestCli(Fixture):
    def test_missing_session_is_a_clear_error(self):
        with self.assertRaises(SystemExit) as cm:
            rcr.compute("nope", self.root)
        self.assertIn("找不到会话记录", str(cm.exception))

    def test_render_and_json_carry_every_headline(self):
        self.write_main([_asst("m1", [("Bash", {"command": "ls"})])])
        R = self.report()
        txt = rcr.render(R)
        for key in ("轮次", "单 Bash 独占", "skill 文档读取", ">8K 输出", "子代理", "评估行"):
            self.assertIn(key, txt)
        json.dumps(R, ensure_ascii=False)  # 必须可序列化

    def test_list_filters_by_skill_call_and_since(self):
        row = _asst("m1", [("Read", {"file_path": SKILL + "phase-1-plan.md"})], ts="2026-09-24T02:00:00Z")
        self.write_main([row, {"type": "user", "timestamp": "2026-09-24T02:00:01Z", "message": {"content": '"skill":"plan-test"'}}])
        self.assertEqual(rcr.list_sessions(self.root, "2026-09-25T00:00:00Z"), [])
        rows = rcr.list_sessions(self.root, "2026-09-24T00:00:00Z")
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]["读过phase文档"])


if __name__ == "__main__":
    unittest.main()
