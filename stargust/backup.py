# -*- coding: utf-8 -*-
"""StarGust 备份 / 还原 / 缓存清理

快照体系：
  - startup  首次运行强制保存的「启动前配置」，一键还原的唯一真源
  - current  最近一次清理前的最新在用状态
  - history  每次清理前生成的增量快照，可被「清缓存」清除（保留 startup 与 current）
"""
import ctypes
import json
import os
import shutil
import subprocess
import time
import winreg

from . import constants as C

# 隐藏子进程控制台窗口（黑窗口闪过问题）
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


# ---------------------------------------------------------------------------
# 基础读取
# ---------------------------------------------------------------------------
def read_env_scope(hive, key_path):
    """读取某作用域的全部环境变量 {name: value}"""
    data = {}
    try:
        k = winreg.OpenKey(hive, key_path, 0, winreg.KEY_READ)
        i = 0
        while True:
            try:
                name, value, _ = winreg.EnumValue(k, i)
                data[name] = value
                i += 1
            except OSError:
                break
        winreg.CloseKey(k)
    except OSError:
        pass
    return data


def read_run_entries(hive, key_path):
    """读取自启动注册表项 {name: value}"""
    return read_env_scope(hive, key_path)


def export_reg(full_key_path, file_path):
    """reg export 导出整个键（含子键）到 .reg 文件"""
    try:
        r = subprocess.run(
            ["reg", "export", full_key_path, file_path, "/y"],
            capture_output=True, text=True, timeout=60,
            errors="ignore",
            creationflags=_NO_WINDOW,
        )
        return r.returncode == 0
    except Exception:
        return False


def _broadcast_env():
    """广播 WM_SETTINGCHANGE，让系统环境变量变更立即生效"""
    HWND_BROADCAST = 0xFFFF
    WM_SETTINGCHANGE = 0x001A
    SMTO_ABORTIFHUNG = 0x0002
    try:
        ctypes.windll.user32.SendMessageTimeoutW(
            HWND_BROADCAST, WM_SETTINGCHANGE, 0, "Environment",
            SMTO_ABORTIFHUNG, 5000, None,
        )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# 快照生成
# ---------------------------------------------------------------------------
def _make_snapshot(folder):
    """把当前系统状态写为一份完整快照，返回 (reg_ok: bool)"""
    os.makedirs(folder, exist_ok=True)
    meta = {"created": time.strftime("%Y-%m-%d %H:%M:%S")}
    with open(os.path.join(folder, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    reg_ok = export_reg(C.INTERNET_SETTINGS_FULL,
                        os.path.join(folder, "internet_settings.reg"))

    user_env = read_env_scope(winreg.HKEY_CURRENT_USER, C.USER_ENV_KEY)
    mach_env = read_env_scope(winreg.HKEY_LOCAL_MACHINE, C.MACHINE_ENV_KEY)
    user_run = read_run_entries(winreg.HKEY_CURRENT_USER, C.RUN_KEY_USER)
    mach_run = read_run_entries(winreg.HKEY_LOCAL_MACHINE, C.RUN_KEY_MACHINE)

    for fname, data in (
        ("env_user.json", user_env),
        ("env_machine.json", mach_env),
        ("run_user.json", user_run),
        ("run_machine.json", mach_run),
    ):
        with open(os.path.join(folder, fname), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    return reg_ok


def ensure_startup_snapshot():
    """首次运行强制保存「启动前快照」。
    返回 (created_now: bool, ok: bool)
    """
    if os.path.isdir(C.SNAPSHOT_STARTUP) and \
            os.path.exists(os.path.join(C.SNAPSHOT_STARTUP, "meta.json")):
        return False, True
    ok = _make_snapshot(C.SNAPSHOT_STARTUP)
    return True, ok


def save_history_snapshot():
    """清理前生成一份带时间戳的历史增量快照"""
    folder = os.path.join(C.SNAPSHOT_HISTORY,
                          time.strftime("%Y%m%d_%H%M%S"))
    return _make_snapshot(folder)


def save_current_snapshot():
    """覆盖式保存「在用」快照（最新一次清理前状态）"""
    if os.path.isdir(C.SNAPSHOT_CURRENT):
        shutil.rmtree(C.SNAPSHOT_CURRENT, ignore_errors=True)
    return _make_snapshot(C.SNAPSHOT_CURRENT)


# ---------------------------------------------------------------------------
# 还原
# ---------------------------------------------------------------------------
def _restore_reg(folder):
    reg_file = os.path.join(folder, "internet_settings.reg")
    if not os.path.exists(reg_file):
        return False
    try:
        r = subprocess.run(["reg", "import", reg_file],
                           capture_output=True, text=True, timeout=60,
                           errors="ignore",
                           creationflags=_NO_WINDOW)
        return r.returncode == 0
    except Exception:
        return False


def _restore_env_scope(hive, key_path, snapshot):
    """仅恢复「代理相关」环境变量：快照有值写回、无值删除。
    非代理变量一律不动，避免破坏 PATH 等全局配置。
    返回变更数。
    """
    changed = 0
    try:
        k = winreg.OpenKey(hive, key_path, 0,
                           winreg.KEY_SET_VALUE | winreg.KEY_READ)
    except OSError:
        return 0
    for name in C.PROXY_ENV_VARS:
        cur = None
        try:
            cur, _ = winreg.QueryValueEx(k, name)
        except OSError:
            pass
        snap = snapshot.get(name)
        if cur == snap:
            continue
        if snap is None:
            try:
                winreg.DeleteValue(k, name)
                changed += 1
            except OSError:
                pass
        else:
            try:
                winreg.SetValueEx(k, name, 0, winreg.REG_SZ, str(snap))
                changed += 1
            except OSError:
                pass
    winreg.CloseKey(k)
    return changed


def _restore_run_scope(hive, key_path, snapshot):
    """补回快照中存在、当前已缺失的自启动项"""
    changed = 0
    try:
        k = winreg.OpenKey(hive, key_path, 0,
                           winreg.KEY_SET_VALUE | winreg.KEY_READ)
    except OSError:
        return 0
    for name, value in snapshot.items():
        try:
            winreg.QueryValueEx(k, name)
            continue  # 已存在则跳过
        except OSError:
            pass
        try:
            winreg.SetValueEx(k, name, 0, winreg.REG_SZ, str(value))
            changed += 1
        except OSError:
            pass
    winreg.CloseKey(k)
    return changed


def restore_from(folder):
    """从指定快照还原，返回统计 dict"""
    result = {"reg": False, "env": 0, "run": 0, "folder": folder}
    result["reg"] = _restore_reg(folder)

    env_user = {}
    env_mach = {}
    run_user = {}
    run_mach = {}
    for fname, holder in (
        ("env_user.json", env_user), ("env_machine.json", env_mach),
        ("run_user.json", run_user), ("run_machine.json", run_mach),
    ):
        p = os.path.join(folder, fname)
        if os.path.exists(p):
            try:
                with open(p, encoding="utf-8") as f:
                    holder.update(json.load(f))
            except Exception:
                pass

    result["env"] += _restore_env_scope(winreg.HKEY_CURRENT_USER,
                                        C.USER_ENV_KEY, env_user)
    result["env"] += _restore_env_scope(winreg.HKEY_LOCAL_MACHINE,
                                        C.MACHINE_ENV_KEY, env_mach)
    result["run"] += _restore_run_scope(winreg.HKEY_CURRENT_USER,
                                        C.RUN_KEY_USER, run_user)
    result["run"] += _restore_run_scope(winreg.HKEY_LOCAL_MACHINE,
                                        C.RUN_KEY_MACHINE, run_mach)
    if result["env"] or result["run"]:
        _broadcast_env()
    return result


def restore_startup():
    """一键还原：优先启动前快照，其次最近一次在用快照"""
    if os.path.isdir(C.SNAPSHOT_STARTUP):
        return restore_from(C.SNAPSHOT_STARTUP)
    if os.path.isdir(C.SNAPSHOT_CURRENT):
        return restore_from(C.SNAPSHOT_CURRENT)
    return None


# ---------------------------------------------------------------------------
# 缓存清理
# ---------------------------------------------------------------------------
def clear_cache():
    """清除历史增量快照（保留 startup 与 current），返回删除条目数"""
    removed = 0
    if os.path.isdir(C.SNAPSHOT_HISTORY):
        for name in os.listdir(C.SNAPSHOT_HISTORY):
            p = os.path.join(C.SNAPSHOT_HISTORY, name)
            try:
                if os.path.isdir(p):
                    shutil.rmtree(p, ignore_errors=True)
                else:
                    os.remove(p)
                removed += 1
            except OSError:
                pass
    return removed


def snapshot_summary():
    """返回快照体系现状摘要，供界面展示"""
    def _exists(p):
        return os.path.isdir(p) and os.path.exists(os.path.join(p, "meta.json"))
    def _time(p):
        try:
            with open(os.path.join(p, "meta.json"), encoding="utf-8") as f:
                return json.load(f).get("created", "?")
        except Exception:
            return "?"
    hist = []
    if os.path.isdir(C.SNAPSHOT_HISTORY):
        hist = sorted(os.listdir(C.SNAPSHOT_HISTORY))
    return {
        "startup": _time(C.SNAPSHOT_STARTUP) if _exists(C.SNAPSHOT_STARTUP) else None,
        "current": _time(C.SNAPSHOT_CURRENT) if _exists(C.SNAPSHOT_CURRENT) else None,
        "history_count": len(hist),
    }
