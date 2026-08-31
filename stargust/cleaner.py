# -*- coding: utf-8 -*-
"""StarGust 清理动作：系统代理 / WinHTTP / 环境变量 / 进程 / 自启 / 强制恢复"""
import subprocess
import winreg

from . import constants as C
from .backup import _broadcast_env

# 隐藏子进程控制台窗口（黑窗口闪过问题）
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


# ---------------------------------------------------------------------------
# 系统代理
# ---------------------------------------------------------------------------
def clean_system_proxy():
    """关闭系统代理并清空 ProxyServer / AutoConfigURL，返回 (ok, msg)"""
    try:
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, C.INTERNET_SETTINGS, 0,
                           winreg.KEY_SET_VALUE | winreg.KEY_READ)
        winreg.SetValueEx(k, "ProxyEnable", 0, winreg.REG_DWORD, 0)
        for name in ("ProxyServer", "AutoConfigURL"):
            try:
                winreg.DeleteValue(k, name)
            except OSError:
                pass
        winreg.CloseKey(k)
        return True, "系统代理已重置为直连"
    except OSError as e:
        return False, "系统代理重置失败: {}".format(e)


# ---------------------------------------------------------------------------
# WinHTTP
# ---------------------------------------------------------------------------
def reset_winhttp():
    """netsh winhttp reset proxy，返回 (ok, msg)"""
    try:
        r = subprocess.run(["netsh", "winhttp", "reset", "proxy"],
                           capture_output=True, text=True, timeout=60,
                           errors="ignore",
                           creationflags=_NO_WINDOW)
        msg = (r.stdout or r.stderr or "").strip()
        return r.returncode == 0, (msg or "WinHTTP 已重置")
    except Exception as e:
        return False, str(e)


# ---------------------------------------------------------------------------
# 环境变量（代理相关）
# ---------------------------------------------------------------------------
def clean_env_proxies():
    """删除用户级与系统级所有代理环境变量，返回 (ok, changed)"""
    ok = True
    changed = 0
    for hive, key_path in (
        (winreg.HKEY_CURRENT_USER, C.USER_ENV_KEY),
        (winreg.HKEY_LOCAL_MACHINE, C.MACHINE_ENV_KEY),
    ):
        try:
            k = winreg.OpenKey(hive, key_path, 0,
                               winreg.KEY_SET_VALUE | winreg.KEY_READ)
        except OSError:
            ok = False
            continue
        for name in C.PROXY_ENV_VARS:
            try:
                winreg.QueryValueEx(k, name)
            except OSError:
                continue
            try:
                winreg.DeleteValue(k, name)
                changed += 1
            except OSError:
                ok = False
        winreg.CloseKey(k)
    if changed:
        _broadcast_env()
    return ok, changed


# ---------------------------------------------------------------------------
# 进程（强制结束，taskkill 系统默认接口）
# ---------------------------------------------------------------------------
def kill_processes(pids):
    """强制结束进程及其子进程树，返回结果列表"""
    results = []
    for pid in pids:
        try:
            r = subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                capture_output=True, text=True, timeout=30,
                errors="ignore",
                creationflags=_NO_WINDOW,
            )
            results.append({
                "pid": pid,
                "ok": r.returncode == 0,
                "msg": (r.stdout or r.stderr or "").strip(),
            })
        except Exception as e:
            results.append({"pid": pid, "ok": False, "msg": str(e)})
    return results


# ---------------------------------------------------------------------------
# 自启动项
# ---------------------------------------------------------------------------
def remove_autostart(items):
    """按用户勾选删除自启动项，返回已删除的项名列表"""
    removed = []
    for it in items:
        is_user = it.get("scope") == "用户"
        hive = winreg.HKEY_CURRENT_USER if is_user else winreg.HKEY_LOCAL_MACHINE
        key_path = C.RUN_KEY_USER if is_user else C.RUN_KEY_MACHINE
        try:
            k = winreg.OpenKey(hive, key_path, 0,
                               winreg.KEY_SET_VALUE | winreg.KEY_READ)
            try:
                winreg.DeleteValue(k, it["name"])
                removed.append("{}[{}]".format(it["name"], it.get("scope", "")))
            except OSError:
                pass
            winreg.CloseKey(k)
        except OSError:
            pass
    return removed
