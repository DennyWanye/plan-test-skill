#!/usr/bin/env python3
"""handoff_evidence 的决定性测试：每条都钉住一个曾经出过的判错。"""
import io
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import handoff_evidence as HE


def rec(**kw):
    kw.setdefault("uuid", os.urandom(6).hex())
    return json.dumps(kw, ensure_ascii=False)


def tool_use(ts, name, inp, tid):
    return rec(type="assistant", timestamp=ts,
               message={"content": [{"type": "tool_use", "id": tid, "name": name, "input": inp}]})


def tool_result(ts, tid, text="ok", is_error=False):
    return rec(type="user", timestamp=ts,
               message={"content": [{"type": "tool_result", "tool_use_id": tid,
                                     "content": text, "is_error": is_error}]})


def text_msg(ts, text):
    return rec(type="assistant", timestamp=ts, message={"content": [{"type": "text", "text": text}]})


class Base(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.sid = "11111111-2222-3333-4444-555555555555"
        self.proj = os.path.join(self.root, "-Users-x-proj")
        os.makedirs(self.proj)
        self.path = os.path.join(self.proj, self.sid + ".jsonl")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def write(self, lines, path=None):
        with io.open(path or self.path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")

    def collect(self, **kw):
        kw.setdefault("since", None)
        kw.setdefault("until", None)
        return HE.collect(self.sid, self.root, kw["since"], kw["until"])


class TestClassification(Base):
    def test_real_click_ok_error_and_unexecuted(self):
        """真实点击要分成功/报错/没执行三种——早期原型把后两种也算成真点。"""
        self.write([
            tool_use("2026-09-10T01:00:00Z", "mcp__Claude_Browser__computer",
                     {"action": "left_click", "coordinate": [10, 20]}, "t1"),
            tool_result("2026-09-10T01:00:01Z", "t1"),
            tool_use("2026-09-10T01:01:00Z", "mcp__Claude_Browser__computer",
                     {"action": "left_click"}, "t2"),
            tool_result("2026-09-10T01:01:01Z", "t2", "boom", is_error=True),
            tool_use("2026-09-10T01:02:00Z", "mcp__Claude_Browser__computer",
                     {"action": "left_click"}, "t3"),  # 无 tool_result
        ])
        steps, _, _ = self.collect()
        got = [(s["cls"], s["status"]) for s in steps]
        self.assertEqual(got.count(("真实交互", "ok")), 1)
        self.assertEqual(got.count(("真实交互", "error")), 1)
        self.assertEqual(got.count(("真实交互", "未执行")), 1)

    def test_js_drive_is_never_real_click(self):
        """e2 的形态：JS .click()/$wire.set 不算真实点击。"""
        self.write([
            tool_use("2026-09-10T01:00:00Z", "mcp__Claude_Browser__javascript_tool",
                     {"text": "document.querySelector('button').click()"}, "t1"),
            tool_result("2026-09-10T01:00:01Z", "t1"),
            tool_use("2026-09-10T01:00:02Z", "mcp__Claude_Browser__javascript_tool",
                     {"text": "c.$wire.set('data.name','KILZ')"}, "t2"),
            tool_result("2026-09-10T01:00:03Z", "t2"),
            tool_use("2026-09-10T01:00:04Z", "mcp__Claude_Browser__javascript_tool",
                     {"text": "location.pathname"}, "t3"),
            tool_result("2026-09-10T01:00:05Z", "t3"),
        ])
        steps, _, _ = self.collect()
        cls = [s["cls"] for s in steps]
        self.assertEqual(cls.count("JS驱动"), 2)
        self.assertEqual(cls.count("JS读取"), 1)
        self.assertNotIn("真实交互", cls)

    def test_batch_expansion_both_shapes(self):
        """browser_batch 带 name；computer-use 批量只有 action，两种都要展开。"""
        self.write([
            tool_use("2026-09-10T01:00:00Z", "mcp__Claude_Browser__browser_batch",
                     {"actions": [{"name": "computer", "input": {"action": "left_click"}},
                                  {"name": "computer", "input": {"action": "screenshot"}}]}, "t1"),
            tool_result("2026-09-10T01:00:01Z", "t1"),
            tool_use("2026-09-10T01:00:02Z", "mcp__computer-use__app_batch",
                     {"actions": [{"action": "click", "x": 1, "y": 2}]}, "t2"),
            tool_result("2026-09-10T01:00:03Z", "t2"),
        ])
        steps, _, _ = self.collect()
        self.assertEqual(len([s for s in steps if s["cls"] == "真实交互"]), 2)
        self.assertEqual(len([s for s in steps if s["cls"] == "观察"]), 1)

    def test_form_input_and_code_edit_steps(self):
        """表单直填不算点击；代码改动要单列，供判断真点是否晚于最后一次改动。"""
        self.write([
            tool_use("2026-09-10T01:00:00Z", "mcp__Claude_Browser__form_input",
                     {"value": "abc", "ref": "ref_1"}, "t1"),
            tool_result("2026-09-10T01:00:01Z", "t1"),
            tool_use("2026-09-10T01:05:00Z", "Edit", {"file_path": "/a/b/Page.php"}, "t2"),
            tool_result("2026-09-10T01:05:01Z", "t2"),
        ])
        steps, _, _ = self.collect()
        kinds = {s["cls"] for s in steps}
        self.assertIn("表单直填", kinds)
        self.assertIn("代码改动", kinds)
        self.assertNotIn("真实交互", kinds)


class TestSourceLookups(Base):
    def test_read_and_grep_are_kept_as_source_clues(self):
        """留出集 2 核查实测：读代码的命令被整条丢弃后，
        评估员把"读过代码才写下的结论"误判成"断言无来源"。"""
        self.write([
            rec(type="user", timestamp="2026-09-10T00:59:00Z", message={"content": "x"}),
            tool_use("2026-09-10T01:00:00Z", "Bash",
                     {"command": "grep -n twiceDailyAt routes/console.php"}, "t1"),
            tool_result("2026-09-10T01:00:01Z", "t1", "23:  ->twiceDailyAt(11, 23, 35)"),
            tool_use("2026-09-10T01:00:02Z", "Read", {"file_path": "/a/routes/console.php"}, "t2"),
            tool_result("2026-09-10T01:00:03Z", "t2"),
        ])
        steps, _, _ = self.collect()
        clues = [s for s in steps if s["cls"] == "来源线索"]
        self.assertEqual(len(clues), 2)
        self.assertTrue(all(s["status"] == "ok" for s in clues))

    def test_source_clue_is_not_a_real_click(self):
        self.write([
            rec(type="user", timestamp="2026-09-10T00:59:00Z", message={"content": "x"}),
            tool_use("2026-09-10T01:00:00Z", "Bash", {"command": "git log --oneline -3"}, "t1"),
            tool_result("2026-09-10T01:00:01Z", "t1"),
        ])
        steps, _, _ = self.collect()
        self.assertNotIn("真实交互", [s["cls"] for s in steps])


class TestWindowAndFiles(Base):
    def test_queue_record_is_not_session_start(self):
        """v6 假告警的根因：文件首条是队列记录，不能当会话起点。"""
        self.write([
            rec(type="queue-operation", timestamp="2026-09-09T00:00:00Z"),
            rec(type="user", timestamp="2026-09-10T01:00:00Z", message={"content": "开始"}),
            tool_use("2026-09-10T01:00:10Z", "mcp__Claude_Browser__computer",
                     {"action": "left_click"}, "t1"),
            tool_result("2026-09-10T01:00:11Z", "t1"),
        ])
        _, warn_in, _ = HE.collect(self.sid, self.root, "2026-09-10T01:00:00Z", None)
        self.assertEqual(warn_in, [], "窗口起点等于首条 user 记录时不应告警")
        _, warn_before, _ = HE.collect(self.sid, self.root, "2026-09-09T12:00:00Z", None)
        self.assertEqual(len(warn_before), 1, "窗口真的早于首条 user 记录时才告警")

    def test_start_gap_within_tolerance_is_not_warned(self):
        """窗口起点只早几秒是调用方取整，告警会被评估员误读成证据缺失。"""
        self.write([
            rec(type="user", timestamp="2026-09-10T01:00:08Z", message={"content": "开始"}),
            tool_use("2026-09-10T01:00:10Z", "mcp__Claude_Browser__computer",
                     {"action": "left_click"}, "t1"),
            tool_result("2026-09-10T01:00:11Z", "t1"),
        ])
        _, near, _ = HE.collect(self.sid, self.root, "2026-09-10T01:00:00Z", None)
        self.assertEqual(near, [], "相差 8 秒不应告警")
        _, far, _ = HE.collect(self.sid, self.root, "2026-09-10T00:30:00Z", None)
        self.assertEqual(len(far), 1, "相差 30 分钟必须告警")

    def test_window_filters_and_dedupes_across_files(self):
        """续接会话会把同一条记录复制到新文件，按 uuid 去重，否则步骤翻倍。"""
        shared = tool_use("2026-09-10T01:00:00Z", "mcp__Claude_Browser__computer",
                          {"action": "left_click"}, "t1")
        res = tool_result("2026-09-10T01:00:01Z", "t1")
        self.write([rec(type="user", timestamp="2026-09-10T00:59:00Z",
                        message={"content": "x"}), shared, res])
        sub = os.path.join(self.proj, self.sid, "subagents")
        os.makedirs(sub)
        self.write([shared, res], os.path.join(sub, "agent-a1.jsonl"))
        steps, _, files = self.collect()
        self.assertEqual(len([s for s in steps if s["cls"] == "真实交互"]), 1)
        self.assertEqual(len(files), 2)
        late, _, _ = HE.collect(self.sid, self.root, "2026-09-10T02:00:00Z", None)
        self.assertEqual(late, [], "窗口之外的步骤不得出现")

    def test_unparsable_file_exits_2(self):
        self.write(["{ not json"] * 60)
        self.assertEqual(HE.main(["--session-id", self.sid, "--root", self.root]), 2)


class TestAudit(Base):
    def test_handoff_line_without_evaluator_is_reported(self):
        """不装 hook 时，这是唯一能查出'交接了但没派评估员'的地方。"""
        self.write([
            rec(type="user", timestamp="2026-09-10T00:59:00Z", message={"content": "x"}),
            text_msg("2026-09-10T01:00:00Z", "都做完了\n交接评估：PASS（eval-1.json）"),
        ])
        steps, _, _ = self.collect()
        self.assertEqual(len(HE.audit(steps)), 1)

    def test_evaluator_then_handoff_line_is_clean(self):
        self.write([
            rec(type="user", timestamp="2026-09-10T00:59:00Z", message={"content": "x"}),
            tool_use("2026-09-10T00:59:30Z", "Agent",
                     {"prompt": "读 prompts/test-result-evaluator.md 评估"}, "t1"),
            tool_result("2026-09-10T00:59:40Z", "t1"),
            text_msg("2026-09-10T01:00:00Z", "都做完了\n交接评估：PASS（eval-1.json）"),
        ])
        steps, _, _ = self.collect()
        self.assertEqual(HE.audit(steps), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
