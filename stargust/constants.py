# -*- coding: utf-8 -*-
"""StarGust（星息）全局常量与白名单配置"""
import os

APP_NAME = "StarGust"
APP_NAME_CN = "星息"
MOTTO = "风过尘尽，一切如新"

# 备份根目录（默认放 %LOCALAPPDATA%\StarGust\backup）
_LOCALAPPDATA = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
BACKUP_ROOT = os.path.join(_LOCALAPPDATA, APP_NAME, "backup")
# 启动前快照：首次运行强制保存，一键还原的唯一真源
SNAPSHOT_STARTUP = os.path.join(BACKUP_ROOT, "startup")
# 在用快照：最近一次清理前的最新状态
SNAPSHOT_CURRENT = os.path.join(BACKUP_ROOT, "current")
# 历史增量快照：可被「清缓存」清除
SNAPSHOT_HISTORY = os.path.join(BACKUP_ROOT, "history")

# ---- 系统代理注册表 ----
INTERNET_SETTINGS = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
INTERNET_SETTINGS_FULL = r"HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Internet Settings"

# ---- 环境变量（代理相关）----
PROXY_ENV_VARS = [
    "http_proxy", "https_proxy", "all_proxy", "no_proxy",
    "ftp_proxy", "socks_proxy",
    "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY",
    "FTP_PROXY", "SOCKS_PROXY",
]
USER_ENV_KEY = r"Environment"
MACHINE_ENV_KEY = r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"

# ---- 自启动项 ----
RUN_KEY_USER = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_KEY_MACHINE = r"Software\Microsoft\Windows\CurrentVersion\Run"

# ---- 代理进程白名单关键字（子串匹配，覆盖常见代理软件）----
PROXY_PROCESS_KEYWORDS = [
    "flclash", "clash", "mihomo", "verge", "v2ray", "xray",
    "sing-box", "singbox", "shadowsocks", "ssr", "qv2ray", "netch",
    "hysteria", "trojan", "gost", "sstap", "tun2socks", "surge",
    "outline", "lantern", "nekoray", "nekobox", "stash", "chisel",
    "shadowrocket", "karing", "hiddify",
]

# 排除名单：命中这些关键字的进程绝不视为代理进程（避免误杀安全/系统软件）
EXCLUDE_PROCESS_KEYWORDS = [
    "hipsdaemon", "hips", "huorong", "sysdiag", "wsctrl",
    "windowsdefender", "msmpeng", "winsd", "360safe", "360tray",
]

# ---- 已知代理端口（快速扫描清单）----
KNOWN_PROXY_PORTS = [
    7890, 7891, 7892, 7893, 7894, 7895, 7896, 7897, 7898, 7899,
    1080, 1081, 10808, 10809, 10810, 10811, 1080,
    8118, 8888, 8889, 9050, 9051, 9150, 9090,
    7078, 2080, 2081, 10800, 10801, 12333,
    57321, 57322, 57323, 57324, 25500, 25501,
    30000, 30001, 30002, 30003, 30005,
]
KNOWN_PROXY_PORTS = sorted(set(KNOWN_PROXY_PORTS))

# ---- 代理软件配置目录（仅检测报告，不自动清理）----
def _join(base, *paths):
    if not base:
        return ""
    return os.path.join(base, *paths)

_APPDATA = os.environ.get("APPDATA", "")
_USERPROFILE = os.environ.get("USERPROFILE", "")
PROXY_CONFIG_PATHS = [
    ("FlClash", _join(_APPDATA, "FlClash")),
    ("Clash Verge / Rev", _join(_APPDATA, "io.github.clash-verge-rev.clash-verge-rev")),
    ("Clash for Windows", _join(_USERPROFILE, ".config", "clash")),
    ("mihomo", _join(_USERPROFILE, ".config", "mihomo")),
    ("v2rayN", _join(_USERPROFILE, "v2rayN")),
    ("sing-box", _join(_USERPROFILE, ".config", "sing-box")),
    ("Nekoray", _join(_USERPROFILE, "nekoray")),
    ("Hiddify", _join(_APPDATA, "hiddify")),
    ("Qv2ray", _join(_APPDATA, "qv2ray")),
    ("Shadowsocks-Windows", _join(_APPDATA, "Shadowsocks")),
]
