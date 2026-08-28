"""套件级终态断言：整套测试跑完，真实 refusal 账本必须原封未动。

文件名以 zz 开头是刻意的：unittest discover 按字母序加载模块，本模块最后运行，
因此它看得见此前**所有**模块、所有 harness、所有子进程的泄漏。
详见 refusal_guard.py 的模块 docstring 与 s1a acceptance AC-7。
"""
import os
import unittest

import refusal_guard


class RealRefusalLedgerUntouchedTestCase(unittest.TestCase):
    def test_env_isolation_is_active(self):
        """隔离生效：环境变量已指向 tmpdir，而非真实 ~/.plan-test。"""
        home = os.environ.get("PLAN_TEST_REFUSAL_HOME")
        self.assertTrue(home, "PLAN_TEST_REFUSAL_HOME 未设置——refusal_guard 没有被最先 import")
        self.assertNotEqual(
            os.path.realpath(home),
            os.path.realpath(os.path.dirname(refusal_guard.REAL_FILE)),
            "隔离目录竟指向真实 ~/.plan-test")

    def test_real_ledger_matches_baseline(self):
        """真实账本与套件开跑前的基线逐字节一致。

        本断言红 = 套件中某处绕过了隔离直写真实账本。排查线索：新增的 gate
        调用方式没有继承测试进程环境（如显式 env= 覆盖、或经 shell 重置环境）。
        """
        self.assertEqual(
            refusal_guard.BASELINE, refusal_guard.current(),
            "真实 %s 在测试期间被改动（基线 vs 终态不符）" % refusal_guard.REAL_FILE)


if __name__ == "__main__":
    unittest.main()
