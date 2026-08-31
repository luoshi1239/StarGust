# -*- coding: utf-8 -*-
"""StarGust 本机概览：系统资源实时采集（零第三方依赖）

提供 CPU / 内存 / 磁盘 / 进程资源占用榜 / 结束进程 能力，全部基于
系统自带命令（typeperf / taskkill / PowerShell）与标准库实现：
  - CPU 整体使用率：typeperf 计数器（wmic 在新系统已被移除，不可依赖）
  - 内存：ctypes GlobalMemoryStatusEx
  - 磁盘：shutil.disk_usage
  - 进程占用榜：PowerShell Get-Process 取内存 + 累计 CPU 秒数，
    与上一次快照差分换算当前 CPU 占用核数
  - 结束进程：taskkill /F /PID
"""
import ctypes
import shutil
import subprocess
import time

CREATE_NO_WINDOW = 0x08000000


def _run(cmd, timeout=20):
    """运行命令并静默返回 stdout（GUI 下禁止弹出黑色控制台窗口）"""
    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            errors="ignore", creationflags=CREATE_NO_WINDOW)
        return (r.stdout or "") or (r.stderr or "")
    except Exception:
        return ""


# ---------------------------------------------------------------- CPU
def get_cpu_percent():
    """整体 CPU 使用率（%），失败返回 None。typeperf 需两次采样求瞬时值。"""
    out = _run(["typeperf", r"\Processor(_Total)\% Processor Time",
                "-sc", "2", "-si", "1"], timeout=12)
    # 输出：表头 + 若干行 "时间","数值"；取最后一行的数值
    val = None
    for line in out.splitlines():
        line = line.strip()
        if not line.startswith('"'):
            continue
        parts = line.split(",")
        if len(parts) >= 2:
            try:
                val = float(parts[-1].strip().strip('"'))
            except ValueError:
                continue
    if val is None:
        return None
    return max(0.0, min(100.0, val))


# ---------------------------------------------------------------- 内存
class _MEMORYSTATUSEX(ctypes.Structure):
    _fields_ = [
        ("dwLength", ctypes.c_ulong),
        ("dwMemoryLoad", ctypes.c_ulong),
        ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong),
        ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong),
        ("ullAvailVirtual", ctypes.c_ulonglong),
        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


def get_memory():
    """内存信息 {total_gb, used_gb, pct}，失败返回 None"""
    try:
        m = _MEMORYSTATUSEX()
        m.dwLength = ctypes.sizeof(_MEMORYSTATUSEX)
        ok = ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
        if not ok:
            return None
        total = m.ullTotalPhys / (1024 ** 3)
        avail = m.ullAvailPhys / (1024 ** 3)
        return {
            "total_gb": total,
            "used_gb": total - avail,
            "pct": float(m.dwMemoryLoad),
        }
    except Exception:
        return None


# ---------------------------------------------------------------- 磁盘
def get_disks():
    """本机逻辑磁盘使用情况列表（跳过光驱等无容量盘）"""
    disks = []
    for letter in "CDEFGH":
        path = letter + ":\\"
        try:
            u = shutil.disk_usage(path)
            total = u.total / (1024 ** 3)
            used = u.used / (1024 ** 3)
            if total <= 0:
                continue
            disks.append({
                "drive": letter + ":",
                "total_gb": total,
                "used_gb": used,
                "pct": used / total * 100.0,
            })
        except OSError:
            continue
    return disks


# ---------------------------------------------------------------- 进程
def get_processes(prev=None):
    """进程资源占用榜

    prev: 上次快照 {pid: (name, cpu_sec, ts)}
    返回 (rows, snapshot)：
      rows 按内存降序，每项 {pid, name, mem_mb, cpu_cores}
      cpu_cores: 当前占用核数（无快照时 None，表示需要下次刷新才有值）
    """
    script = (
        "Get-Process | Where-Object { $_.Id -gt 0 } | "
        "Select-Object Id,ProcessName,WorkingSet64,CPU | "
        "ConvertTo-Csv -NoTypeInformation"
    )
    out = _run(["powershell", "-NoProfile", "-NonInteractive",
                "-Command", script], timeout=15)
    now = time.time()
    rows = []
    snapshot = {}
    for line in out.splitlines():
        line = line.strip()
        if not line.startswith('"'):
            continue
        # CSV: "Id","ProcessName","WorkingSet64","CPU"
        cells = []
        buf = ""
        in_q = False
        for ch in line:
            if ch == '"':
                in_q = not in_q
            elif ch == "," and not in_q:
                cells.append(buf)
                buf = ""
            else:
                buf += ch
        if buf or in_q is False:
            cells.append(buf)
        if len(cells) < 4:
            continue
        try:
            pid = int(cells[0])
            name = cells[1] or "?"
            mem = float(cells[2])
            cpu = float(cells[3]) if cells[3] else 0.0
        except (ValueError, TypeError):
            continue
        snapshot[pid] = (name, cpu, now)
        cpu_cores = None
        if prev and pid in prev:
            _, p_cpu, p_ts = prev[pid]
            dt = now - p_ts
            if dt > 0.5:
                cpu_cores = max(0.0, (cpu - p_cpu) / dt)
        rows.append({
            "pid": pid, "name": name,
            "mem_mb": mem / (1024 * 1024), "cpu_cores": cpu_cores,
        })
    rows.sort(key=lambda r: r["mem_mb"], reverse=True)
    return rows, snapshot


def get_top_processes(prev=None, top=12):
    """进程占用 Top 榜（含 CPU 核数与内存）"""
    rows, snapshot = get_processes(prev)
    return rows[:top], snapshot


# ---------------------------------------------------------------- 结束进程
def kill_process(pid):
    """结束指定进程，返回 (ok, msg)。调用方必须先经用户确认。"""
    out = _run(["taskkill", "/F", "/PID", str(pid)], timeout=10)
    ok = ("成功" in out) or ("SUCCESS" in out.upper())
    return ok, out.strip()


if __name__ == "__main__":
    print("CPU:", get_cpu_percent())
    print("MEM:", get_memory())
    print("DISK:", get_disks())
    r1, s1 = get_processes()
    print("PROC first pass rows:", len(r1))
    time.sleep(1.2)
    r2, _ = get_processes(s1)
    for p in r2[:8]:
        print("  {} (PID {}) mem={:.0f}MB cpu_cores={}".format(
            p["name"], p["pid"], p["mem_mb"], p["cpu_cores"]))
