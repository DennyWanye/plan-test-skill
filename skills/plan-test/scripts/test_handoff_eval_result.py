#!/usr/bin/env python3
"""评估员输出处置的决定性测试：每条钉住一种会让"没有 block"被误读成 PASS 的变异。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from handoff_eval_result import judge

OK = ('{"verdict":"FAIL","findings":[{"id":"F1","severity":"block","fix_class":"硬伤"}]}')


class TestJudge(unittest.TestCase):
    def test_clean_pass_can_send(self):
        self.assertEqual(judge('{"verdict":"PASS","findings":[]}')[0], "send")

    def test_truncated_json_is_not_pass(self):
        self.assertEqual(judge('{"verdict":"FAIL","findings":[{"id":"F1"')[0], "retry-then-blocked")

    def test_missing_required_field(self):
        self.assertEqual(judge('{"findings":[]}')[0], "retry-then-blocked")

    def test_prose_wrapped_json_is_extracted(self):
        text = "先说结论：不能发。\n" + '{"verdict":"FAIL","findings":[{"id":"F1","severity":"block","fix_class":"文字"}]}' + "\n另外还有个建议。"
        action, _, findings = judge(text)
        self.assertEqual(action, "fix-and-send")
        self.assertEqual(len(findings), 1)

    def test_two_json_objects_are_ambiguous(self):
        self.assertEqual(judge(OK + "\n" + OK)[0], "retry-then-blocked")

    def test_duplicate_id_takes_strictest(self):
        text = ('{"verdict":"FAIL","findings":['
                '{"id":"F1","severity":"note"},'
                '{"id":"F1","severity":"block","fix_class":"硬伤"}]}')
        action, _, findings = judge(text)
        self.assertEqual(action, "fix-and-reeval")
        self.assertEqual(len(findings), 1)

    def test_refusal_and_empty(self):
        self.assertEqual(judge("抱歉，我无法完成这次评估。")[0], "retry-then-blocked")
        self.assertEqual(judge("")[0], "retry-then-blocked")

    def test_block_without_fix_class_is_not_sendable(self):
        self.assertEqual(judge('{"verdict":"FAIL","findings":[{"id":"F1","severity":"block"}]}')[0],
                         "retry-then-blocked")

    def test_text_only_blocks_send_after_fix(self):
        text = '{"verdict":"FAIL","findings":[{"id":"F1","severity":"block","fix_class":"文字"}]}'
        self.assertEqual(judge(text)[0], "fix-and-send")


if __name__ == "__main__":
    unittest.main(verbosity=2)
