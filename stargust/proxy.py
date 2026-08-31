# -*- coding: utf-8 -*-
"""StarGust 代理增强：一键设置/取消系统代理 + 代理地址连通性测试

实现说明（零第三方依赖）：
  - 设置系统代理：写注册表 ProxyEnable=1 / ProxyServer=host:port，
    并广播 WM_SETTINGCHANGE(InternetSettings) 立即生效
  - 取消系统代理：ProxyEnable=0 并删除 ProxyServer / AutoConfigURL
  - 连通性 / 延迟：socket TCP 探测
"""
import ctypes
import socket
import time
import winreg

from . import constants as C


def _broadcast_settings():
    """广播 WM_SETTINGCHANGE，让系统代理设置立即生效"""
    HWND_BROADCAST = 0xFFFF
    WM_SETTINGCHANGE = 0x001A
    SMTO_ABORTIFHUNG = 0x0002
    try:
        ctypes.windll.user32.SendMessageTimeoutW(
            HWND_BROADCAST, WM_SETTINGCHANGE, 0, "InternetSettings",
            SMTO_ABORTIFHUNG, 5000, None)
        return True
    except Exception:
        return False


def _open_internet_settings(write=True):
    access = (winreg.KEY_SET_VALUE | winreg.KEY_READ) if write else winreg.KEY_READ
    return winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                          C.INTERNET_SETTINGS, 0, access)


def current_proxy():
    """读取当前系统代理设置，返回 dict 或 None"""
    try:
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, C.INTERNET_SETTINGS, 0,
                           winreg.KEY_READ)
        enable = None
        try:
            enable, _ = winreg.QueryValueEx(k, "ProxyEnable")
        except OSError:
            pass
        server = None
        try:
            server, _ = winreg.QueryValueEx(k, "ProxyServer")
        except OSError:
            pass
        winreg.CloseKey(k)
        return {"enable": bool(enable), "server": server}
    except OSError:
        return None


def set_system_proxy(host, port):
    """设置系统代理 host:port，返回 (ok, msg)"""
    port = int(port)
    server = "{}:{}".format(host, port)
    try:
        k = _open_internet_settings()
        winreg.SetValueEx(k, "ProxyEnable", 0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(k, "ProxyServer", 0, winreg.REG_SZ, server)
        # 清除自动配置脚本，避免与手动代理冲突
        try:
            winreg.DeleteValue(k, "AutoConfigURL")
        except OSError:
            pass
        winreg.CloseKey(k)
        _broadcast_settings()
        return True, "系统代理已设置为 {}".format(server)
    except OSError as e:
        return False, "设置失败: {}".format(e)


def cancel_system_proxy():
    """一键取消系统代理，返回 (ok, msg)"""
    try:
        k = _open_internet_settings()
        winreg.SetValueEx(k, "ProxyEnable", 0, winreg.REG_DWORD, 0)
        for name in ("ProxyServer", "AutoConfigURL"):
            try:
                winreg.DeleteValue(k, name)
            except OSError:
                pass
        winreg.CloseKey(k)
        _broadcast_settings()
        return True, "系统代理已取消（恢复直连）"
    except OSError as e:
        return False, "取消失败: {}".format(e)


def test_proxy(host, port, timeout=3.0):
    """TCP 探测代理地址连通性 / 延迟，返回 (ok, latency_ms, err)"""
    t0 = time.perf_counter()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True, int((time.perf_counter() - t0) * 1000), ""
    except socket.timeout:
        return False, int((time.perf_counter() - t0) * 1000), "连接超时"
    except OSError as e:
        return False, int((time.perf_counter() - t0) * 1000), str(e)[:50]
