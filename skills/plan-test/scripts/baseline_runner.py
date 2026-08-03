#!/usr/bin/env python3
"""大型仓库绿色基线执行器（phase-2 B）。

DeskPet 2026-08-03 复盘（baseline.md 原始记录）：全量 pytest 单命令跑 15 分钟无终态被迫
按时间边界掐掉、一个目录 5 分钟静默超时、手工找 PID 27432/20928 精确终止，之后才摸索出
按文件名 modulo 8 分片。这些教训固化成本工具：

  - 分片清单由仓库维护（baseline-shards.json），不再临场发明；
  - 每片实时心跳：已运行时间 + 最近一行输出，不再有"静默 15 分钟"；
  - 既有失败按签名区分（shard id + exit code 记入 known-failures 文件），
    新增失败立即阻断——基线红不红要"如实告知"，不能把老红当新绿、也不能让新红混进老红；
  - 单片超时只终止**本片的精确进程树**（POSIX 进程组 / Windows taskkill /T），
    已绿分片结果落盘，--resume 跳过不重跑。

清单格式（仓库根 baseline-shards.json）：

  {
    "shards": [
      {"id": "backend-mod8-0",
       "command": ["python", "-m", "pytest", "--import-mode=importlib", "-q",
                    "tests/shard0"],
       "timeout_seconds": 300,
       "cwd": "backend"}
    ]
  }

用法：

  python baseline_runner.py --manifest baseline-shards.json \
      [--state .baseline-state.json] [--known-failures baseline-known-failures.json] \
      [--resume] [--accept-current-failures] [--heartbeat 30]

exit code：0 = 全部分片达到基线（绿，或红但与 known-failures 签名一致）；
1 = 出现**新增**失败或超时；2 = 用法/清单错误。
结果 JSON 写入 --state 文件，可直接作为 phase-2 baseline.md 的证据附件，
也可整体用 `plan_test_gate.py record-timing --exec --` 包裹本命令让耗时自动入账。
仅 stdlib。
"""

import argparse
import json
import os
import signal
import subprocess
import sys
import threading
import time


def load_json(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")


def kill_tree(proc):
    """只终止本片的精确进程树，不误伤同机其他测试进程。"""
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                       capture_output=True)
    else:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            proc.kill()


def run_shard(shard, heartbeat_seconds):
    """跑一个分片：实时心跳 + 超时精确终止。返回结果 dict。"""
    sid = shard["id"]
    timeout = int(shard.get("timeout_seconds") or 300)
    cwd = shard.get("cwd") or None
    start = time.monotonic()
    popen_kw = {"stdout": subprocess.PIPE, "stderr": subprocess.STDOUT,
                "text": True, "cwd": cwd, "encoding": "utf-8", "errors": "replace"}
    if os.name != "nt":
        popen_kw["preexec_fn"] = os.setsid  # 独立进程组 → 可整树终止
    try:
        proc = subprocess.Popen(shard["command"], **popen_kw)
    except OSError as e:
        return {"id": sid, "status": "error", "detail": str(e), "elapsed_s": 0}

    last_line = [""]
    lines_seen = [0]

    def pump():
        for line in proc.stdout:
            last_line[0] = line.rstrip()[-160:]
            lines_seen[0] += 1

    t = threading.Thread(target=pump, daemon=True)
    t.start()
    next_beat = start + heartbeat_seconds
    while True:
        rc = proc.poll()
        now = time.monotonic()
        if rc is not None:
            t.join(timeout=5)
            elapsed = round(now - start, 1)
            status = "pass" if rc == 0 else "fail"
            print("[%s] %s exit=%d elapsed=%.0fs lines=%d" % (
                sid, status.upper(), rc, elapsed, lines_seen[0]), flush=True)
            return {"id": sid, "status": status, "exit_code": rc,
                    "elapsed_s": elapsed, "output_lines": lines_seen[0],
                    "last_line": last_line[0]}
        if now - start > timeout:
            kill_tree(proc)
            elapsed = round(now - start, 1)
            print("[%s] TIMEOUT elapsed=%.0fs（进程树已精确终止）——把本片拆细后重跑，"
                  "已绿分片用 --resume 跳过" % (sid, elapsed), flush=True)
            return {"id": sid, "status": "timeout", "elapsed_s": elapsed,
                    "output_lines": lines_seen[0], "last_line": last_line[0]}
        if now >= next_beat:
            print("[%s] …%.0fs lines=%d｜%s" % (
                sid, now - start, lines_seen[0], last_line[0]), flush=True)
            next_beat = now + heartbeat_seconds
        time.sleep(0.5)


def failure_signature(result):
    """既有失败的稳定签名：分片 id + exit code。同签名 = 同一个老红。"""
    return "%s:exit=%s" % (result["id"], result.get("exit_code", "timeout"))


def main(argv=None):
    ap = argparse.ArgumentParser(prog="baseline_runner.py")
    ap.add_argument("--manifest", required=True, help="分片清单 JSON（仓库维护）")
    ap.add_argument("--state", default=".baseline-state.json",
                    help="结果落盘文件；--resume 据此跳过已绿分片")
    ap.add_argument("--known-failures", default="baseline-known-failures.json",
                    help="既有失败签名文件；命中签名的红不阻断（如实标注为老红）")
    ap.add_argument("--resume", action="store_true", help="跳过 state 里已 pass 的分片")
    ap.add_argument("--accept-current-failures", action="store_true",
                    help="把本轮全部失败签名写入 known-failures（仅在如实告知用户后使用）")
    ap.add_argument("--heartbeat", type=int, default=30, help="心跳间隔秒数")
    args = ap.parse_args(argv)

    manifest = load_json(args.manifest)
    if not manifest or not manifest.get("shards"):
        print("ERROR: 清单缺 shards: %s" % args.manifest, file=sys.stderr)
        return 2
    ids = [s.get("id") for s in manifest["shards"]]
    if len(set(ids)) != len(ids) or not all(ids):
        print("ERROR: 分片 id 缺失或重复", file=sys.stderr)
        return 2

    known = set((load_json(args.known_failures, {}) or {}).get("signatures", []))
    state = load_json(args.state, {}) or {}
    results = state.get("results", {}) if args.resume else {}

    new_failures = []
    for shard in manifest["shards"]:
        sid = shard["id"]
        prev = results.get(sid)
        if args.resume and prev and prev.get("status") == "pass":
            print("[%s] SKIP（--resume：上轮已绿）" % sid, flush=True)
            continue
        res = run_shard(shard, args.heartbeat)
        results[sid] = res
        state["results"] = results
        state["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        save_json(args.state, state)  # 每片落盘：中断后 --resume 不丢进度
        if res["status"] != "pass":
            sig = failure_signature(res)
            if sig in known:
                print("[%s] 既有失败（签名命中 %s）——不阻断，基线保持如实的红" % (sid, sig),
                      flush=True)
            else:
                new_failures.append(res)
                print("[%s] **新增失败**（签名 %s 不在 known-failures）——立即阻断"
                      % (sid, sig), flush=True)
                break  # 新红即停：别在坏基线上继续烧时间

    total = len(manifest["shards"])
    passed = sum(1 for r in results.values() if r.get("status") == "pass")
    known_red = sum(1 for r in results.values()
                    if r.get("status") != "pass" and failure_signature(r) in known)
    print("BASELINE SUMMARY: %d/%d pass, %d known-red, %d new-fail"
          % (passed, total, known_red, len(new_failures)), flush=True)

    if args.accept_current_failures:
        sigs = sorted(known | {failure_signature(r) for r in results.values()
                               if r.get("status") != "pass"})
        save_json(args.known_failures, {"signatures": sigs,
                                        "accepted_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")})
        print("KNOWN-FAILURES UPDATED: %d 个签名（须在 baseline.md 里如实告知用户）"
              % len(sigs), flush=True)

    return 1 if new_failures else 0


if __name__ == "__main__":
    sys.exit(main())
