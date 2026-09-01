"""测试隔离守卫：把 refusal 写入引到 tmpdir，并为「真实账本未被碰过」留基线。

s1a AC-7（plans/2026-08-28-gate-authority/slices/s1a-refusal-log/acceptance.md）：
测试以子进程调 gate，且大量调用不传 cwd（实测 143 处 run_gate 仅 24 处传 cwd），
若不隔离，跑一次套件会向真实 ~/.plan-test/refusals.jsonl 追加上百条合成拒绝，
污染 stats 唯一的数据源，并提前触发 512 KB trim 淘汰真实记录。

机制：本模块在 **import 时**（即任何用例运行、任何子进程派生之前）：
  1. 若 PLAN_TEST_REFUSAL_HOME 未设，指向本测试进程专属的 tmpdir——
     环境变量被所有子进程（乃至孙进程，如 gate_usage_report 再调 gate）继承，
     因此**一次设置覆盖全部 harness**，无须逐类改 setUp；
  2. 记录真实 ~/.plan-test/refusals.jsonl 的基线快照。

断言在 test_zz_refusal_guard.py（unittest discover 按字母序加载，zz 保证最后运行）：
套件里任何时刻、任何 harness 的泄漏都会让终态与基线不符——这才是能判红的
套件级 oracle。断言写在单个已隔离用例内是「按构造无法失败」（它看不见其他
harness 在别的时刻的写入），该缺陷在本 plan 的三轮挑战中三次出现，此为设防。

每个 test_*.py 顶部 import 本模块；import 幂等。
"""
import atexit
import hashlib
import os
import shutil
import tempfile

_REAL_FILE = os.path.join(os.path.expanduser("~"), ".plan-test", "refusals.jsonl")


def _archives(path):
    """同目录 trim 归档（refusals-*.jsonl.gz）的 (名字, 大小) 元组集。
    2026-09-01 v0.7.1 起 trim 会产出归档文件——只盯主文件的基线看不见
    归档污染（review F14），归档集必须一并入指纹。"""
    d = os.path.dirname(path)
    try:
        return tuple(sorted(
            (a, os.path.getsize(os.path.join(d, a)))
            for a in os.listdir(d)
            if a.startswith("refusals-") and a.endswith(".jsonl.gz")))
    except OSError:
        return ()


def _snapshot(path):
    """真实账本的状态指纹：(存在?, 大小, sha256, 归档集)。不存在记 (False, 0, None, 归档集)。"""
    if not os.path.isfile(path):
        return (False, 0, None, _archives(path))
    with open(path, "rb") as f:
        data = f.read()
    return (True, len(data), hashlib.sha256(data).hexdigest(), _archives(path))


# ---- import 副作用：先隔离，再记基线（顺序无所谓——隔离改的是 env，不碰真实文件）----
if not os.environ.get("PLAN_TEST_REFUSAL_HOME"):
    _tmp = tempfile.mkdtemp(prefix="refusal-guard-")
    os.environ["PLAN_TEST_REFUSAL_HOME"] = _tmp
    atexit.register(shutil.rmtree, _tmp, ignore_errors=True)

#: 真实账本在套件开跑前的状态；test_zz_refusal_guard 与之对账。
BASELINE = _snapshot(_REAL_FILE)
REAL_FILE = _REAL_FILE


def current():
    """真实账本此刻的状态，供终态断言。"""
    return _snapshot(_REAL_FILE)
