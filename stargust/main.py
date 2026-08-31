# -*- coding: utf-8 -*-
"""StarGust（星息）程序入口：管理员权限检查与提权"""
import ctypes
import sys


def is_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def elevate():
    """以管理员权限重新启动自身，返回 True 表示已请求提权（本进程应退出）"""
    if "--elevated" in sys.argv:
        return False
    try:
        args = [a for a in sys.argv[1:] if a != "--elevated"]
        params = " ".join('"{}"'.format(a) for a in args)
        ret = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.argv[0], "--elevated {}".format(params),
            None, 1)
        return ret > 32
    except Exception:
        return False


def main():
    if not is_admin():
        if elevate():
            sys.exit(0)
        ctypes.windll.user32.MessageBoxW(
            0, "StarGust 需要管理员权限运行。\n请右键「以管理员身份运行」。",
            "StarGust 星息", 0x10)
        sys.exit(1)

    from stargust.ui import StarGustApp
    import tkinter as tk
    root = tk.Tk()
    app = StarGustApp(root)
    app.run()


if __name__ == "__main__":
    main()
