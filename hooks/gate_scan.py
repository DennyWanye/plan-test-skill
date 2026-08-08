#!/usr/bin/env python3
"""扫描工作区里的 gate 记账物——**按内容形状识别，不靠文件名，也不靠目录名**。

为什么不靠名字（两轮独立审计各打穿一次）：
  - 第八轮：hook 只扫 `*/verification/*`，把 run-dir 放到 `plans/run-x/` 就整体绕过唯一强制点；
  - 第九轮：改成按文件名 `plan-test-run.json` 找，把账本改名为 `ledger.archived.json` 又绕过
    ——本仓当时的"归档"方案自己就是这条逃逸的一个实例。

名字由被测者定，任何基于名字的识别都会输。账本的**形状**是它无法在保持可用的前提下改变的：
同时含 schema_version / run_id / scenarios / integrity 四个键的 JSON 就是账本。

枚举分两趟：
  1) `git ls-files -c -o --exclude-standard`：尊重 .gitignore（否则 .venv 里几百个
     manifest.json 会把每次 Stop 拖到 7 秒以上，还会误报），未跟踪但未忽略的新文件同样在列。
  2) 补充趟 `git ls-files -o -i --exclude-standard -- plans/`，只取路径含 `/verification/`
     的被 ignore 的 .json。动机：有的仓库（如 simple_harness）**有意** gitignore 机器账本
     （账本证明当前 HEAD，提交即过期），第 1 趟对它们永远失明 → LEDGERS 恒空：失败账本
     躲过 check-only，同 plan 的 manifest 还被误判"半截 init"。
     这一趟的目录范围只限定**补充可见性**的枚举成本（不进 .venv / node_modules），不参与
     识别（识别仍按形状），也不缩小第 1 趟的可见范围——改名/挪目录不会让任何原本可见的
     账本消失，所以不复活第八轮那条逃逸。残余：在 plans/**/verification/ 之外 gitignore
     一份失败账本仍不可见——该逃逸在本改动前是**全量**存在的（ignore 任意位置即整体隐身），
     本改动只收窄不放大；进一步收窄需要全仓枚举 ignored 文件，会退回 .venv 的性能/误报坑。
     补充趟的文件**只作为账本候选，不作为 manifest/HALVES 候选**：老 schema（1.1.0，缺
     integrity 键）的历史账本不满足四键账本形状、却满足 manifest 形状，若收进 HALVES 会
     变成既未 tracked（committed-clean 豁免救不了）又无法补账的死锁误报（simple_harness
     实测）。不收不引入新逃逸：这些文件在本改动前对扫描器完全不可见，HALVES 对它们的
     覆盖本来就是零；而真正的新 init 写出的是当前 schema 账本，四键形状照常收进 LEDGERS。

manifest 的"半截 init"豁免（HALVES 过滤）：
  - 原规则保留：同目录存在账本 = 正常 run；
  - 放宽新增：manifest 目录**子树**内存在账本，且 manifest 若声明 run_id 则须与账本
    run_id 一致（simple_harness 布局：manifest 在 plan 根、账本在 verification/<run>/）。
    run_id 一致性保证"manifest 已指向 r6 但 r6 账本没写出来"仍判半截；被豁免时对应的
    子树账本本身仍在 LEDGERS 里被 check-only 审到——豁免不减少任何审计，只消除重复告警。

活动轮（ACTIVE 段，2026-08-09 加）：
  hook 此前对**每一个** run-dir 打印完整诊断——7 个历史轮 = 单次 Stop 300+ 行 / ~10k token，
  而且这些内容与本回合做了什么无关（改了一个证据文件、甚至没碰账本，照样全刷一遍）。
  ACTIVE 让 hook 知道"哪一个是本会话正在跑的轮"，只详报它，其余压成一行。
  判定：run_id 与某个 gate manifest 的 run_id 相同的账本；同时命中多个（每个 run-dir 各带
  一份 manifest 的布局）或一个都没命中时，退回"最近修改的那个账本"——活动轮每条 CLI 写入
  都会重写账本，mtime 是最可靠的活动信号。**ACTIVE 只影响输出详略，不影响谁被审计**：
  LEDGERS 一个不少，每个都照跑退出码判定。

输出：三段，`LEDGERS`、`HALVES`、`ACTIVE`，各自每行一个相对路径。
"""

import json
import os
import subprocess
import sys

MAX_BYTES = 8 * 1024 * 1024
LEDGER_KEYS = ("schema_version", "run_id", "scenarios", "integrity")
MANIFEST_MARKERS = ("applicability", "source_request_text", "source_request_file", "run_id")


def _git_lines(args):
    try:
        out = subprocess.run(["git", "ls-files"] + args,
                             capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return []
    if out.returncode != 0:
        return []
    return out.stdout.splitlines()


def candidate_files():
    """返回 [(相对路径, 是否来自补充趟)]。补充趟文件只可作账本候选（见模块 docstring）。"""
    files = [(p, False) for p in _git_lines(["-c", "-o", "--exclude-standard"])
             if p.endswith(".json")]
    # 补充趟：被 .gitignore 的账本（见模块 docstring）。范围只限枚举成本，识别仍按形状。
    for p in _git_lines(["-o", "-i", "--exclude-standard", "--", "plans/"]):
        if p.endswith(".json") and "/verification/" in p.replace(os.sep, "/"):
            files.append((p, True))
    seen = set()
    return [(p, ig) for p, ig in files if not (p in seen or seen.add(p))]


def load(rel):
    try:
        if os.path.getsize(rel) > MAX_BYTES:
            return None
        with open(rel, "r", encoding="utf-8") as f:
            obj = json.load(f)
    except (OSError, ValueError):
        return None
    return obj if isinstance(obj, dict) else None


def is_gate_manifest(obj):
    """gate manifest 的形状：scenarios 是带 scenario_id 的对象数组 + 一个 gate 专属键。

    按形状而非键名区分，BDD/测试清单那种字符串数组不会误报（第八轮审计实测过误报）。
    """
    sc = obj.get("scenarios")
    shaped = isinstance(sc, list) and len(sc) > 0 and all(
        isinstance(x, dict) and "scenario_id" in x for x in sc)
    return shaped and any(k in obj for k in MANIFEST_MARKERS)


def covered_by_ledger(mf_path, mf_run_id, ledgers):
    """manifest 是否有账本兜底：同目录（原规则）或子树内 run_id 匹配（放宽，见 docstring）。"""
    d = os.path.dirname(mf_path)
    prefix = d + "/" if d else ""
    for led_path, led_run_id in ledgers:
        if os.path.dirname(led_path) == d:
            return True
        if led_path.startswith(prefix) and (mf_run_id is None or led_run_id == mf_run_id):
            return True
    return False


def _mtime(path):
    try:
        return os.path.getmtime(path)
    except OSError:
        return 0.0


def pick_active(ledgers, manifest_run_ids):
    """选出唯一的活动轮账本路径（见模块 docstring）；没有账本时返回 None。"""
    if not ledgers:
        return None
    matched = [p for p, rid in ledgers if rid and rid in manifest_run_ids]
    pool = matched or [p for p, _ in ledgers]
    return max(pool, key=lambda p: (_mtime(p), p))


def main():
    ledgers, halves, manifest_run_ids = [], [], set()
    for rel, from_ignored in candidate_files():
        norm = rel.replace(os.sep, "/")
        if "/fixtures/" in norm or norm.startswith("fixtures/"):
            continue
        obj = load(rel)
        if obj is None:
            continue
        if all(k in obj for k in LEDGER_KEYS):
            ledgers.append((norm, obj.get("run_id")))
        elif is_gate_manifest(obj) and not from_ignored:
            halves.append((norm, obj.get("run_id")))
            if obj.get("run_id"):
                # 被账本覆盖（不进 HALVES）的 manifest 同样是活动轮的指针，照收
                manifest_run_ids.add(obj["run_id"])
    print("LEDGERS")
    for x, _ in sorted(ledgers):
        print(x)
    print("HALVES")
    for mf, mf_run_id in sorted(halves):
        if not covered_by_ledger(mf, mf_run_id, ledgers):
            print(mf)
    print("ACTIVE")
    active = pick_active(ledgers, manifest_run_ids)
    if active:
        print(active)


if __name__ == "__main__":
    main()
