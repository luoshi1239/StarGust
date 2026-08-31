# -*- coding: utf-8 -*-
"""StarGust 残留检测：系统代理 / WinHTTP / 环境变量 / 进程 / 自启 / 配置目录"""
import csv
import io
import os
import subprocess
import winreg

from . import constants as C
from .backup import read_env_scope, read_run_entries

# 隐藏子进程控制台窗口（黑窗口闪过问题）
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def detect_system_proxy():
    """系统代理（WinINET）状态"""
    try:
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, C.INTERNET_SETTINGS, 0,
                           winreg.KEY_READ)
        proxy_enable = None
        try:
            proxy_enable, _ = winreg.QueryValueEx(k, "ProxyEnable")
        except OSError:
            pass
        proxy_server = None
        try:
            proxy_server, _ = winreg.QueryValueEx(k, "ProxyServer")
        except OSError:
            pass
        auto_config = None
        try:
            auto_config, _ = winreg.QueryValueEx(k, "AutoConfigURL")
        except OSError:
            pass
        winreg.CloseKey(k)
        active = bool(proxy_enable) or bool(auto_config)
        return {
            "active": active,
            "proxy_enable": proxy_enable,
            "proxy_server": proxy_server,
            "auto_config": auto_config,
        }
    except OSError:
        return None


def detect_winhttp():
    """WinHTTP 代理（netsh winhttp show proxy）"""
    try:
        r = subprocess.run(["netsh", "winhttp", "show", "proxy"],
                           capture_output=True, text=True, timeout=30,
                           errors="ignore",
                           creationflags=_NO_WINDOW)
        out = (r.stdout or "").strip()
        lower = out.lower()
        is_set = False
        if "direct access" in lower or "direct access (no proxy" in lower \
                or "无代理服务器" in lower or "直接访问" in lower:
            is_set = False
        elif "proxy server" in lower or "代理服务器" in lower:
            is_set = True
        return {"set": is_set, "detail": out}
    except Exception:
        return None


def detect_env_proxies():
    """扫描用户级与系统级环境变量中的代理配置"""
    items = []
    scopes = (
        ("用户", winreg.HKEY_CURRENT_USER, C.USER_ENV_KEY),
        ("系统", winreg.HKEY_LOCAL_MACHINE, C.MACHINE_ENV_KEY),
    )
    for scope, hive, key_path in scopes:
        data = read_env_scope(hive, key_path)
        for name in C.PROXY_ENV_VARS:
            if name in data:
                items.append({
                    "scope": scope, "name": name, "value": str(data[name]),
                })
    return items


def _tasklist_csv():
    try:
        r = subprocess.run(["tasklist", "/FO", "CSV", "/NH"],
                           capture_output=True, text=True, timeout=30,
                           errors="ignore",
                           creationflags=_NO_WINDOW)
        return r.stdout or ""
    except Exception:
        return ""


def detect_proxy_processes():
    """按白名单关键字匹配代理进程，返回 [{'name','pid'}]"""
    out = _tasklist_csv()
    found = []
    try:
        for row in csv.reader(io.StringIO(out)):
            if len(row) < 2:
                continue
            name = row[0]
            pid = row[1]
            lower = name.lower()
            # 命中排除名单（安全/系统软件）直接跳过
            if any(ek in lower for ek in C.EXCLUDE_PROCESS_KEYWORDS):
                continue
            for kw in C.PROXY_PROCESS_KEYWORDS:
                if kw in lower:
                    found.append({"name": name, "pid": pid})
                    break
    except Exception:
        pass
    return found


def detect_autostart():
    """扫描自启动项中命中代理关键字的条目"""
    items = []
    scopes = (
        ("用户", winreg.HKEY_CURRENT_USER, C.RUN_KEY_USER),
        ("系统", winreg.HKEY_LOCAL_MACHINE, C.RUN_KEY_MACHINE),
    )
    for scope, hive, key_path in scopes:
        data = read_run_entries(hive, key_path)
        for name, value in data.items():
            lower = "{} {}".format(name, value).lower()
            hit = [kw for kw in C.PROXY_PROCESS_KEYWORDS if kw in lower]
            if hit:
                items.append({
                    "scope": scope, "name": name, "value": value,
                    "keyword": hit[0],
                })
    return items


def detect_config_paths():
    """常见代理软件配置目录是否存在（仅报告）"""
    items = []
    for label, path in C.PROXY_CONFIG_PATHS:
        if path and os.path.isdir(path):
            items.append({"label": label, "path": path})
    return items


def detect_all():
    """汇总检测全部残留，返回统一结构"""
    result = {"system_proxy": None, "winhttp": None, "env": [],
              "process": [], "autostart": [], "config": []}

    sp = detect_system_proxy()
    if sp:
        result["system_proxy"] = sp

    result["winhttp"] = detect_winhttp()
    result["env"] = detect_env_proxies()
    result["process"] = detect_proxy_processes()
    result["autostart"] = detect_autostart()
    result["config"] = detect_config_paths()
    return result


def count_issues(result):
    """统计检测到的残留问题数（用于界面提示）"""
    n = 0
    sp = result.get("system_proxy")
    if sp and sp.get("active"):
        n += 1
    wh = result.get("winhttp")
    if wh and wh.get("set"):
        n += 1
    n += len(result.get("env", []))
    n += len(result.get("process", []))
    n += len(result.get("autostart", []))
    return n
