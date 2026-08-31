# -*- coding: utf-8 -*-
"""StarGust 网络实时监控：实时上下行带宽 / TCP 连接统计 / 连接按进程分组

实现说明（零第三方依赖，全部基于系统自带命令）：
  - 带宽   : typeperf 网络接口计数器（Bytes Received/Sent per sec）
  - 连接   : netstat -ano -p tcp + tasklist 做 PID -> 进程名映射
"""
import csv
import io
import subprocess

from .scanner import get_pid_names

# 隐藏子进程控制台窗口（黑窗口闪过问题）
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _run(cmd, timeout=30):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           timeout=timeout, errors="ignore",
                           creationflags=_NO_WINDOW)
        return r.stdout or ""
    except Exception:
        return ""


def get_bandwidth():
    """实时上下行带宽 (Bytes/s)。typeperf 采样 2 次间隔 1 秒，取最新。
    返回 (recv_bps, sent_bps)；typeperf 不可用时返回 None。
    """
    cmd = ["typeperf",
           r"\Network Interface(*)\Bytes Received/sec",
           r"\Network Interface(*)\Bytes Sent/sec",
           "-sc", "2", "-si", "1"]
    out = _run(cmd, timeout=20)
    try:
        rows = list(csv.reader(io.StringIO(out)))
    except Exception:
        return None
    if len(rows) < 3:
        return None
    header = rows[1] if len(rows) > 1 else []
    recv_idx = [i for i, h in enumerate(header) if "Bytes Received" in h]
    sent_idx = [i for i, h in enumerate(header) if "Bytes Sent" in h]
    data_rows = rows[2:]
    if not data_rows:
        return None
    last = data_rows[-1]

    def _sum(idx_list):
        total = 0.0
        for i in idx_list:
            if i < len(last):
                v = last[i].strip()
                if v and v != "A":  # A = 实例无效/不存在
                    try:
                        total += float(v)
                    except ValueError:
                        pass
        return int(total)

    return _sum(recv_idx), _sum(sent_idx)


def get_connections():
    """TCP 连接统计。返回 (rows, stats)。
    rows = [{pid, process, local, remote, state}]
    stats = {total, established, listening, time_wait, syn_sent, close_wait, other}
    """
    out = _run(["netstat", "-ano", "-p", "tcp"], timeout=15)
    pid_names = get_pid_names()
    rows = []
    stats = {"total": 0, "established": 0, "listening": 0, "time_wait": 0,
             "syn_sent": 0, "close_wait": 0, "other": 0}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) < 4 or parts[0].upper() != "TCP":
            continue
        local = parts[1]
        remote = parts[2]
        state = parts[3]
        pid = parts[-1] if parts[-1].isdigit() else ""
        rows.append({
            "pid": pid,
            "process": pid_names.get(int(pid)) if pid else "系统",
            "local": local, "remote": remote, "state": state,
        })
        stats["total"] += 1
        key = state.lower()
        if key in ("established", "listening", "time_wait", "syn_sent", "close_wait"):
            stats[key] += 1
        else:
            stats["other"] += 1
    return rows, stats
