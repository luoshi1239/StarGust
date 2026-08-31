# -*- coding: utf-8 -*-
"""StarGust 端口扫描：快扫（已知代理端口）+ 全扫（全部监听端口）

实现说明：
  基于 `netstat -ano -p tcp` 一次性获取全部 LISTENING 端口，
  再与 `tasklist` 进程表做 PID -> 进程名映射，区分端口占用程序。
  快扫 = 只看已知代理端口；全扫 = 列出所有监听中的 TCP 端口。
"""
import csv
import io
import subprocess

from . import constants as C

# 隐藏子进程控制台窗口（黑窗口闪过问题）
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _run(cmd):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60,
                           errors="ignore",
                           creationflags=_NO_WINDOW)
        return r.stdout or ""
    except Exception:
        return ""


def get_listeners():
    """返回 {port: set(pid)}：当前处于 LISTENING 的 TCP 端口及占用 PID"""
    out = _run(["netstat", "-ano", "-p", "tcp"])
    listeners = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) < 5:
            continue
        state = parts[-2]
        if state.upper() != "LISTENING":
            continue
        try:
            port = int(parts[1].rsplit(":", 1)[-1])
            pid = int(parts[-1])
        except (ValueError, IndexError):
            continue
        listeners.setdefault(port, set()).add(pid)
    return listeners


def get_pid_names():
    """返回 {pid: process_name}"""
    out = _run(["tasklist", "/FO", "CSV", "/NH"])
    mapping = {}
    try:
        for row in csv.reader(io.StringIO(out)):
            if len(row) >= 2:
                try:
                    mapping[int(row[1])] = row[0]
                except ValueError:
                    pass
    except Exception:
        pass
    return mapping


def _to_rows(listeners, pid_names, known_ports, known_only):
    rows = []
    for port in sorted(listeners):
        is_known = port in known_ports
        if known_only and not is_known:
            continue
        for pid in sorted(listeners[port]):
            rows.append({
                "port": port,
                "pid": pid,
                "process": pid_names.get(pid, "未知/无权限读取"),
                "known": is_known,
            })
    return rows


def quick_scan():
    """快速扫描：仅展示已知代理端口中的占用情况"""
    listeners = get_listeners()
    pid_names = get_pid_names()
    known = set(C.KNOWN_PROXY_PORTS)
    return _to_rows(listeners, pid_names, known, known_only=True)


def full_scan():
    """全量扫描：展示全部监听中的 TCP 端口及占用程序"""
    listeners = get_listeners()
    pid_names = get_pid_names()
    known = set(C.KNOWN_PROXY_PORTS)
    return _to_rows(listeners, pid_names, known, known_only=False)
