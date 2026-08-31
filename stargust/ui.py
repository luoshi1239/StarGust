# -*- coding: utf-8 -*-
"""StarGust（星息）tkinter 图形界面

交互原则：
  - 通知类信息一律进日志 + 状态栏，不弹窗打扰（静默）
  - 仅保留必要的安全确认弹窗（清理 / 还原 / 清缓存 / 强制恢复）
  - 长任务（全扫 / 清理 / 还原 / 强制恢复）运行时显示进度条
  - 任务结束在状态栏给出成功 / 失败着色提示
"""
import os
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageTk

from . import constants as C
from . import backup, cleaner, detector, netcheck, scanner


def _resource_path(rel):
    """兼容源码运行与 PyInstaller 打包后的资源路径定位"""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return os.path.join(base, rel)
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), rel)


class StarGustApp:
    def __init__(self, root):
        self.root = root
        self.fail_count = 0
        self.detect_result = None
        self._busy = False
        self._progress_job = None

        root.title("{} {} —— {}".format(C.APP_NAME, C.APP_NAME_CN, C.MOTTO))
        root.geometry("980x660")
        root.minsize(860, 580)

        self._setup_style()
        self._build_ui()
        self._on_startup()

    # ------------------------------------------------------------------ UI
    def _setup_style(self):
        """现代化简约主题：浅灰底 + 白色卡片 + 品牌紫主色"""
        self.style = ttk.Style(self.root)
        try:
            self.style.theme_use("clam")
        except tk.TclError:
            pass

        FONT = "Microsoft YaHei UI"
        BG = "#f5f6fa"        # 全局背景
        CARD = "#ffffff"      # 卡片白
        INK = "#2d3436"       # 主文字
        MUT = "#8a94a6"       # 次要文字
        LINE = "#e5e8ee"      # 分隔线
        ACC = "#6C5CE7"       # 品牌紫
        ACC_H = "#5A4BD1"     # 紫 hover
        # 供其他方法复用
        self.C_INK = INK

        # 全局
        self.style.configure(".", font=(FONT, 10), background=BG, foreground=INK)
        self.style.configure("TFrame", background=BG)
        self.style.configure("Card.TFrame", background=CARD)
        self.style.configure("TLabel", background=CARD, foreground=INK)

        # Header 横幅
        self.style.configure("Header.TFrame", background=ACC)
        self.style.configure("HeaderLogo.TLabel", background=ACC)
        self.style.configure("HeaderTitle.TLabel", background=ACC,
                             foreground="#ffffff", font=(FONT, 16, "bold"))
        self.style.configure("HeaderMotto.TLabel", background=ACC,
                             foreground="#dcd6ff", font=(FONT, 10))

        # 按钮：扁平卡片风格
        self.style.configure("TButton", background=CARD, foreground=INK,
                             borderwidth=1, relief="flat", bordercolor=LINE,
                             padding=(16, 8), font=(FONT, 10))
        self.style.map("TButton",
                       background=[("active", "#eef0f5"), ("pressed", "#e2e6ee")],
                       bordercolor=[("active", "#cfd6e4")],
                       foreground=[("disabled", "#b7bfcc")])
        # 主操作按钮（紫色）
        self.style.configure("Accent.TButton", background=ACC, foreground="#ffffff",
                             borderwidth=0, padding=(18, 9), font=(FONT, 10, "bold"))
        self.style.map("Accent.TButton",
                       background=[("active", ACC_H), ("pressed", ACC_H)],
                       foreground=[("disabled", "#b9b2f0")])
        # 危险按钮
        self.style.configure("Danger.TButton", background="#e05a4e",
                             foreground="#ffffff", borderwidth=0,
                             padding=(14, 8), font=(FONT, 10))
        self.style.map("Danger.TButton",
                       background=[("active", "#c8483d"), ("pressed", "#c8483d")])

        # Notebook：扁平 tab
        self.style.configure("TNotebook", background=BG, borderwidth=0)
        self.style.configure("TNotebook.Tab",
                             background="#e9ebf2", foreground=MUT,
                             borderwidth=0, padding=(24, 9), font=(FONT, 10))
        self.style.map("TNotebook.Tab",
                       background=[("selected", CARD)],
                       foreground=[("selected", ACC)])
        self.style.configure("TNotebook.TFrame", background=CARD)

        # Treeview 表格
        self.style.configure("Treeview", background=CARD, fieldbackground=CARD,
                             foreground=INK, rowheight=30, borderwidth=0)
        self.style.configure("Treeview.Heading", background="#f0f2f7",
                             foreground="#5b6472", font=(FONT, 10, "bold"),
                             relief="flat", padding=(8, 7))
        self.style.map("Treeview",
                       background=[("selected", "#e9e7fb")],
                       foreground=[("selected", INK)])
        self.style.map("Treeview.Heading",
                       background=[("active", "#e6e9f1")])

        # 进度条
        self.style.configure("Horizontal.TProgressbar", background=ACC,
                             troughcolor="#e5e8ee", borderwidth=0,
                             lightcolor=ACC, darkcolor=ACC)

        # 状态栏
        self.style.configure("Status.TLabel", background="#eef0f5",
                             foreground=INK, padding=(12, 6), font=(FONT, 9))

        # 日志卡片
        self.style.configure("TLabelframe", background=CARD, bordercolor=LINE,
                             relief="flat")
        self.style.configure("TLabelframe.Label", background=CARD,
                             foreground=MUT, font=(FONT, 9))

        # 复选框
        self.style.configure("TCheckbutton", background=CARD, foreground=INK,
                             font=(FONT, 9))
        self.style.map("TCheckbutton", background=[("active", CARD)])

    def _load_logo(self):
        """加载品牌 logo（打包后从 _MEIPASS 定位资源）"""
        try:
            path = _resource_path(os.path.join("stargust", "assets", "logo.png"))
            img = Image.open(path)
            img = img.resize((44, 44), Image.LANCZOS)
            return ImageTk.PhotoImage(img)
        except Exception:
            return None

    def _build_ui(self):
        # 顶部品牌横幅：logo + 标题 + 口号
        header = ttk.Frame(self.root, style="Header.TFrame", padding=(18, 12))
        header.pack(fill=tk.X)
        self._header_logo = self._load_logo()
        if self._header_logo is not None:
            ttk.Label(header, image=self._header_logo,
                      style="HeaderLogo.TLabel").pack(side=tk.LEFT, padx=(0, 14))
        title_box = ttk.Frame(header, style="Header.TFrame")
        title_box.pack(side=tk.LEFT)
        ttk.Label(title_box, text="{} {}".format(C.APP_NAME, C.APP_NAME_CN),
                  style="HeaderTitle.TLabel").pack(anchor=tk.W)
        ttk.Label(title_box, text=C.MOTTO,
                  style="HeaderMotto.TLabel").pack(anchor=tk.W, pady=(2, 0))

        # 主体卡片容器
        body = ttk.Frame(self.root, style="TFrame", padding=12)
        body.pack(fill=tk.BOTH, expand=True)
        card = ttk.Frame(body, style="Card.TFrame", padding=12)
        card.pack(fill=tk.BOTH, expand=True)

        # 操作按钮行
        bar = ttk.Frame(card, style="Card.TFrame")
        bar.pack(fill=tk.X, pady=(0, 10))
        self.btn_detect = ttk.Button(bar, text="检测残留", command=self.on_detect)
        self.btn_detect.pack(side=tk.LEFT, padx=(0, 6))
        self.btn_quick = ttk.Button(bar, text="快速端口扫描", command=self.on_quick_scan)
        self.btn_quick.pack(side=tk.LEFT, padx=6)
        self.btn_full = ttk.Button(bar, text="全端口扫描", command=self.on_full_scan)
        self.btn_full.pack(side=tk.LEFT, padx=6)
        ttk.Separator(bar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=12)
        self.btn_clean = ttk.Button(bar, text="一键清理", style="Accent.TButton",
                                    command=self.on_clean)
        self.btn_clean.pack(side=tk.LEFT, padx=6)
        self.btn_restore = ttk.Button(bar, text="一键还原", command=self.on_restore)
        self.btn_restore.pack(side=tk.LEFT, padx=6)
        self.btn_cache = ttk.Button(bar, text="清缓存", command=self.on_clear_cache)
        self.btn_cache.pack(side=tk.LEFT, padx=6)

        # 强制按钮：初始隐藏，普通清理连续失败 3 次后出现
        self.btn_force = ttk.Button(bar, text="⚠ 强制恢复网络",
                                    style="Danger.TButton", command=self.on_force)
        self.btn_force.pack(side=tk.LEFT, padx=6)
        self.btn_force.pack_forget()

        # 进度条
        self.progress = ttk.Progressbar(card, mode="determinate", maximum=100)
        self.progress.pack(fill=tk.X, pady=(0, 10))

        self.notebook = ttk.Notebook(card)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        # --- Tab1 残留检测 ---
        tab_detect = ttk.Frame(self.notebook, style="TNotebook.TFrame")
        self.notebook.add(tab_detect, text="残留检测")
        cols = ("category", "item", "detail", "action")
        self.tree = ttk.Treeview(tab_detect, columns=cols, show="headings")
        for cid, text, width in (
            ("category", "类别", 90),
            ("item", "项目", 200),
            ("detail", "值 / 详情", 430),
            ("action", "处置方式", 150),
        ):
            self.tree.heading(cid, text=text)
            self.tree.column(cid, width=width, anchor=tk.W)
        self.tree.pack(fill=tk.BOTH, expand=True, side=tk.TOP)

        # 自启动项勾选区
        self.auto_frame = ttk.LabelFrame(tab_detect,
                                         text="自启动项（代理相关，勾选后随清理删除）",
                                         padding=8)
        self.auto_frame.pack(fill=tk.X, side=tk.BOTTOM, pady=(8, 0))
        self.auto_vars = []

        # --- Tab2 端口占用 ---
        tab_port = ttk.Frame(self.notebook, style="TNotebook.TFrame")
        self.notebook.add(tab_port, text="端口占用")
        pcols = ("port", "pid", "process", "known")
        self.ptree = ttk.Treeview(tab_port, columns=pcols, show="headings")
        for cid, text, width in (
            ("port", "端口", 90),
            ("pid", "PID", 90),
            ("process", "占用进程", 300),
            ("known", "代理常用端口", 120),
        ):
            self.ptree.heading(cid, text=text)
            self.ptree.column(cid, width=width, anchor=tk.W)
        self.ptree.pack(fill=tk.BOTH, expand=True)

        # --- Tab3 网络连通 ---
        tab_net = ttk.Frame(self.notebook, style="TNotebook.TFrame")
        self.notebook.add(tab_net, text="网络连通")
        net_bar = ttk.Frame(tab_net, style="TNotebook.TFrame")
        net_bar.pack(fill=tk.X, pady=(0, 8))
        self.btn_net = ttk.Button(net_bar, text="检测内外网连通性",
                                  style="Accent.TButton", command=self.on_net_check)
        self.btn_net.pack(side=tk.LEFT)
        self.net_summary = ttk.Label(net_bar, text="未检测", style="TNotebook.TFrame",
                                     foreground="#8a94a6")
        self.net_summary.pack(side=tk.LEFT, padx=(14, 0))

        ncols = ("zone", "target", "ip", "port", "latency", "status")
        self.ntree = ttk.Treeview(tab_net, columns=ncols, show="headings")
        for cid, text, width in (
            ("zone", "区域", 70),
            ("target", "目标", 240),
            ("ip", "解析 IP", 130),
            ("port", "端口", 60),
            ("latency", "延迟", 90),
            ("status", "状态", 170),
        ):
            self.ntree.heading(cid, text=text)
            self.ntree.column(cid, width=width, anchor=tk.W)
        self.ntree.tag_configure("ok", foreground="#1b5e20")
        self.ntree.tag_configure("fail", foreground="#b71c1c")
        self.ntree.pack(fill=tk.BOTH, expand=True)

        # --- 日志区 ---
        log_frame = ttk.LabelFrame(body, text="日志", padding=6)
        log_frame.pack(fill=tk.X, pady=(10, 0))
        self.log_text = tk.Text(log_frame, height=8, state=tk.DISABLED,
                                font=("Consolas", 9), bg="#ffffff", fg=self.C_INK,
                                relief="flat", bd=0, padx=4, pady=4)
        self.log_text.pack(fill=tk.X)

        # 状态栏
        self.status = ttk.Label(self.root, text="就绪", anchor=tk.W,
                                style="Status.TLabel")
        self.status.pack(fill=tk.X, side=tk.BOTTOM)

    # ------------------------------------------------------------ 状态与进度
    def log(self, msg):
        stamp = time.strftime("%H:%M:%S")
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, "[{}] {}\n".format(stamp, msg))
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def _set_status(self, msg, kind="info"):
        """状态栏着色提示：info=灰蓝 / ok=绿 / error=红 / busy=蓝"""
        colors = {"info": "#455a64", "ok": "#1b5e20",
                  "error": "#b71c1c", "busy": "#1565c0"}
        self.status.configure(text=msg, foreground=colors.get(kind, "#455a64"))

    def _start_progress(self):
        self.progress.configure(value=0)

        def tick():
            v = self.progress["value"]
            self.progress.configure(value=5 if v >= 95 else v + 4)
            self._progress_job = self.root.after(150, tick)

        tick()

    def _stop_progress(self):
        if self._progress_job:
            try:
                self.root.after_cancel(self._progress_job)
            except Exception:
                pass
            self._progress_job = None
        self.progress.configure(value=100)
        self.root.after(500, lambda: self.progress.configure(value=0))

    def set_busy(self, flag):
        self._busy = flag
        state = tk.DISABLED if flag else tk.NORMAL
        for b in (self.btn_detect, self.btn_quick, self.btn_full,
                  self.btn_clean, self.btn_restore, self.btn_cache, self.btn_net):
            try:
                b.configure(state=state)
            except Exception:
                pass

    def _run_async(self, fn, done=None):
        if self._busy:
            self.log("有任务执行中，请稍候……")
            return
        self.set_busy(True)
        self._start_progress()

        def worker():
            try:
                result = fn()
            except Exception as e:  # noqa: BLE001
                result = ("__ERROR__", str(e))
            self.root.after(0, lambda: self._finish(result, done))

        threading.Thread(target=worker, daemon=True).start()

    def _finish(self, result, done):
        self.set_busy(False)
        self._stop_progress()
        if isinstance(result, tuple) and result and result[0] == "__ERROR__":
            self.log("执行出错: {}".format(result[1]))
            self._set_status("执行出错：{}".format(result[1]), "error")
            return
        if done:
            done(result)

    # ------------------------------------------------------------ 启动逻辑
    def _on_startup(self):
        created, ok = backup.ensure_startup_snapshot()
        if created and ok:
            self.log("已首次强制保存「启动前快照」，清理出错可随时一键还原")
        elif ok:
            self.log("检测到已有「启动前快照」，一键还原可用")
        else:
            self.log("警告：启动前快照创建失败，请确认以管理员权限运行")
        self._refresh_status()
        self.on_detect()

    def _refresh_status(self):
        s = backup.snapshot_summary()
        txt = "快照 | 启动前: {} | 在用: {} | 历史增量: {} 份".format(
            s["startup"] or "无", s["current"] or "无", s["history_count"])
        self._set_status(txt, "info")

    # ------------------------------------------------------------ 检测
    def on_detect(self):
        self.log("开始检测代理残留……")
        self._set_status("正在检测残留……", "busy")
        self._run_async(detector.detect_all, self._render_detect)

    def _render_detect(self, result):
        self.detect_result = result
        for i in self.tree.get_children():
            self.tree.delete(i)
        issues = 0

        sp = result.get("system_proxy")
        if sp:
            if sp.get("active"):
                issues += 1
                self.tree.insert("", tk.END, values=(
                    "系统代理", "ProxyEnable/Server",
                    "{} / {}".format(sp.get("proxy_enable"),
                                     sp.get("proxy_server") or "(空)"),
                    "一键清理自动重置"))
                self.log("  系统代理: 已开启, ProxyEnable={}, Server={}".format(
                    sp.get("proxy_enable"), sp.get("proxy_server") or "(空)"))
                if sp.get("auto_config"):
                    self.log("  AutoConfigURL={}".format(sp.get("auto_config")))
            else:
                self.tree.insert("", tk.END, values=(
                    "系统代理", "ProxyEnable/Server", "直连（未启用）", "无需处理"))
                self.log("  系统代理: 直连（未启用）")

        wh = result.get("winhttp")
        if wh:
            if wh.get("set"):
                issues += 1
                self.tree.insert("", tk.END, values=(
                    "WinHTTP", "代理设置", "已配置", "一键清理自动重置"))
                self.log("  WinHTTP: 已配置代理")
            else:
                self.tree.insert("", tk.END, values=(
                    "WinHTTP", "代理设置", "直连（无代理）", "无需处理"))
                self.log("  WinHTTP: 直连（无代理）")

        for it in result.get("env", []):
            issues += 1
            self.tree.insert("", tk.END, values=(
                "环境变量", "[{}] {}".format(it["scope"], it["name"]),
                it["value"], "一键清理自动删除"))
            self.log("  环境变量[{}] {}={}".format(
                it["scope"], it["name"], it["value"]))

        for it in result.get("process", []):
            issues += 1
            self.tree.insert("", tk.END, values=(
                "代理进程", it["name"], "PID {}".format(it["pid"]),
                "一键清理强制结束"))
            self.log("  代理进程: {} (PID {})".format(it["name"], it["pid"]))

        for it in result.get("autostart", []):
            issues += 1
            self.tree.insert("", tk.END, values=(
                "自启动", "[{}] {}".format(it["scope"], it["name"]),
                it["value"], "下方勾选后删除"))
            self.log("  自启动[{}] {} -> {}".format(
                it["scope"], it["name"], it["value"]))

        for it in result.get("config", []):
            self.tree.insert("", tk.END, values=(
                "软件配置", it["label"], it["path"], "仅报告，不自动清理"))
            self.log("  软件配置: {} 存在 -> {}".format(it["label"], it["path"]))

        self._render_autostart_checks(result.get("autostart", []))
        if issues == 0:
            self.log("检测完成：未发现代理残留，网络处于干净状态")
            self._set_status("检测完成：未发现代理残留", "ok")
        else:
            self.log("检测完成：共发现 {} 处待处理项，详见列表与日志".format(issues))
            self._set_status("检测完成：发现 {} 处待处理项".format(issues), "error")

    def _render_autostart_checks(self, items):
        for w in self.auto_frame.winfo_children():
            w.destroy()
        self.auto_vars = []
        if not items:
            ttk.Label(self.auto_frame, text="未发现代理相关自启动项",
                      foreground="gray").pack(anchor=tk.W)
            return
        for it in items:
            var = tk.BooleanVar(value=True)
            self.auto_vars.append((var, it))
            cb = ttk.Checkbutton(
                self.auto_frame,
                text="[{}] {}  ->  {}".format(it["scope"], it["name"],
                                             it["value"][:60]),
                variable=var)
            cb.pack(anchor=tk.W)

    # ------------------------------------------------------------ 端口扫描
    def on_quick_scan(self):
        self.log("快速端口扫描（已知代理端口）……")
        self._set_status("快速端口扫描中……", "busy")
        self._run_async(scanner.quick_scan, lambda rows: self._render_ports(rows, "快速"))

    def on_full_scan(self):
        self.log("全端口扫描（全部监听 TCP 端口，可能需要数秒）……")
        self._set_status("全端口扫描中……", "busy")
        self._run_async(scanner.full_scan, lambda rows: self._render_ports(rows, "全量"))

    def _render_ports(self, rows, label):
        for i in self.ptree.get_children():
            self.ptree.delete(i)
        for r in rows:
            known = "是" if r["known"] else "否"
            self.ptree.insert("", tk.END, values=(
                r["port"], r["pid"], r["process"], known))
        known_cnt = sum(1 for r in rows if r["known"])
        self.log("  {}端口扫描: 共 {} 个监听端口, 其中代理常用端口 {} 个".format(
            label, len(rows), known_cnt))
        for r in rows:
            if r["known"]:
                self.log("    [代理端口] {}  <- {} (PID {})".format(
                    r["port"], r["process"], r["pid"]))
        self._set_status("{}扫描完成：{} 个监听端口 / {} 个代理常用端口".format(
            label, len(rows), known_cnt), "ok")

    # ------------------------------------------------------------ 网络连通
    def on_net_check(self):
        self.log("开始检测内外网连通性（多线程并发 TCP 探测）……")
        self._set_status("正在检测网络连通性……", "busy")
        self.net_summary.configure(text="检测中……", foreground="#1565c0")
        self._run_async(netcheck.run_all, self._render_net)

    def _render_net(self, rows):
        for i in self.ntree.get_children():
            self.ntree.delete(i)
        lan_ok = wan_ok = 0
        lan_n = wan_n = 0
        for r in rows:
            if r["zone"] == "内网":
                lan_n += 1
                if r["ok"]:
                    lan_ok += 1
            else:
                wan_n += 1
                if r["ok"]:
                    wan_ok += 1
            if r["ok"]:
                status = "正常 · {} ms".format(r["latency"])
                tag = "ok"
                lat = "{} ms".format(r["latency"])
            else:
                status = "失败 · {}".format(r["err"] or "无响应")
                tag = "fail"
                lat = "超时" if r["latency"] >= 3000 else "-"
            self.ntree.insert("", tk.END, tags=(tag,), values=(
                r["zone"], "{} :{}".format(r["note"], r["port"]),
                r["ip"] or "-", r["port"], lat, status))
        summary = "内网 {}/{} · 外网 {}/{} 可达".format(lan_ok, lan_n, wan_ok, wan_n)
        color = "#1b5e20" if (lan_ok == lan_n and wan_ok == wan_n) else "#b71c1c"
        self.net_summary.configure(text=summary, foreground=color)
        self.log("  网络检测：{}".format(summary))
        for r in rows:
            if not r["ok"]:
                self.log("    [不可达] {} ({}:{}) -> {}".format(
                    r["note"], r["host"], r["port"], r["err"] or "无响应"))
        self._set_status("网络检测完成：{}".format(summary), "ok")

    # ------------------------------------------------------------ 一键清理
    def on_clean(self):
        if self.detect_result is None:
            self.log("请先执行「检测残留」")
            self._set_status("请先执行「检测残留」", "error")
            return
        if not messagebox.askyesno(
                "StarGust", "即将清理以下内容：\n"
                "  · 关闭系统代理并清空 ProxyServer\n"
                "  · 重置 WinHTTP 代理\n"
                "  · 删除代理相关环境变量\n"
                "  · 强制结束代理进程\n"
                "  · 删除勾选的自启动项\n\n"
                "清理前会自动保存快照，可一键还原。\n确认执行？"):
            return
        self.log("开始一键清理……")
        self._set_status("正在清理……", "busy")
        self._run_async(self._do_clean, self._after_clean)

    def _do_clean(self):
        logs = []
        backup.save_history_snapshot()
        backup.save_current_snapshot()
        logs.append("已保存清理前快照（历史 + 在用）")

        # 1 进程
        pids = []
        for it in self.detect_result.get("process", []):
            if it.get("pid", "").isdigit():
                pids.append(int(it["pid"]))
        if pids:
            kills = cleaner.kill_processes(pids)
            ok_n = sum(1 for k in kills if k["ok"])
            logs.append("进程处理 {} 个 / 成功 {} 个".format(len(kills), ok_n))
            for k in kills:
                logs.append("  PID {} -> {}".format(
                    k["pid"], "成功" if k["ok"] else ("失败: " + (k["msg"] or ""))))
        else:
            logs.append("无代理进程需处理")

        # 2 系统代理
        ok, msg = cleaner.clean_system_proxy()
        logs.append("系统代理: {} -> {}".format(
            "成功" if ok else "失败", msg))

        # 3 WinHTTP
        ok, msg = cleaner.reset_winhttp()
        logs.append("WinHTTP: {} -> {}".format(
            "成功" if ok else "失败", msg))

        # 4 环境变量
        ok, changed = cleaner.clean_env_proxies()
        logs.append("环境变量: 删除 {} 项{}".format(
            changed, "" if ok else "（部分失败，需管理员权限）"))

        # 5 自启动（勾选）
        checked = [it for var, it in self.auto_vars if var.get()]
        if checked:
            removed = cleaner.remove_autostart(checked)
            logs.append("自启动: 删除 {} 项 -> {}".format(
                len(removed), ", ".join(removed) if removed else "无"))
        else:
            logs.append("自启动: 未勾选，跳过")

        # 6 复查
        logs.append("清理完成，正在复查……")
        re = detector.detect_all()
        remaining = detector.count_issues(re)
        logs.append("复查：剩余 {} 处待处理项".format(remaining))
        return {"logs": logs, "re": re, "remaining": remaining}

    def _after_clean(self, data):
        for l in data["logs"]:
            self.log(l)
        self._render_detect(data["re"])
        self._refresh_status()
        if data["remaining"] > 0:
            self.fail_count += 1
            self.log("清理未完全生效（第 {} 次未达标）。".format(self.fail_count))
            self._set_status("清理未完全生效：剩余 {} 处待处理".format(
                data["remaining"]), "error")
            if self.fail_count >= 3:
                self._show_force_button()
                self.log("普通清理已连续 3 次未完全生效，已解锁「强制恢复网络」。")
        else:
            self.fail_count = 0
            self.log("清理完成，系统网络已恢复直连。")
            self._set_status("清理完成，系统网络已恢复直连", "ok")

    # ------------------------------------------------------------ 强制恢复
    def _show_force_button(self):
        self.btn_force.pack(side=tk.LEFT, padx=8)

    def on_force(self):
        if not messagebox.askyesno(
                "高危操作警告",
                "「强制恢复网络」将执行以下高风险操作：\n\n"
                "  · 直接删除所有代理相关环境变量（http_proxy 等）\n"
                "  · 强制关闭系统代理\n"
                "  · 重置 WinHTTP 代理\n\n"
                "目的：梯子意外中断后一键恢复系统网络。\n"
                "此操作不修改 PATH 等其它系统变量，但仍建议确认。\n\n"
                "确认继续？", icon="warning"):
            return
        self.log("执行强制恢复网络……")
        self._set_status("强制恢复网络中……", "busy")
        self._run_async(self._do_force, self._after_force)

    def _do_force(self):
        logs = []
        backup.save_history_snapshot()
        backup.save_current_snapshot()
        logs.append("已保存清理前快照（历史 + 在用）")
        ok, changed = cleaner.clean_env_proxies()
        logs.append("删除代理环境变量 {} 项{}".format(
            changed, "" if ok else "（部分失败，请检查管理员权限）"))
        ok, msg = cleaner.clean_system_proxy()
        logs.append("系统代理: {} -> {}".format(
            "成功" if ok else "失败", msg))
        ok, msg = cleaner.reset_winhttp()
        logs.append("WinHTTP: {} -> {}".format(
            "成功" if ok else "失败", msg))
        re = detector.detect_all()
        remaining = detector.count_issues(re)
        logs.append("复查：剩余 {} 处待处理项".format(remaining))
        return {"logs": logs, "re": re, "remaining": remaining}

    def _after_force(self, data):
        for l in data["logs"]:
            self.log(l)
        self._render_detect(data["re"])
        self._refresh_status()
        if data["remaining"] > 0:
            self._set_status("强制恢复后仍有残留，请检查代理软件或重启系统", "error")
            self.log("强制恢复后仍有残留，建议手动检查代理软件或重启系统。")
        else:
            self._set_status("强制恢复完成，系统网络已恢复直连", "ok")
            self.log("强制恢复完成，系统网络已恢复直连。")

    # ------------------------------------------------------------ 还原 / 缓存
    def on_restore(self):
        s = backup.snapshot_summary()
        if not s["startup"] and not s["current"]:
            self.log("未找到任何可用快照，无法还原")
            self._set_status("未找到可用快照，无法还原", "error")
            return
        if not messagebox.askyesno(
                "StarGust",
                "将从快照还原系统代理与代理相关环境变量。\n"
                "启动前快照: {} / 在用快照: {}\n\n"
                "（优先使用启动前快照）\n确认还原？".format(
                    s["startup"] or "无", s["current"] or "无")):
            return
        self.log("开始一键还原……")
        self._set_status("还原中……", "busy")
        self._run_async(lambda: backup.restore_startup(), self._after_restore)

    def _after_restore(self, result):
        if result is None:
            self.log("还原失败：未找到可用快照")
            self._set_status("还原失败", "error")
            return
        self.log("还原完成：注册表 {}，环境变量恢复 {} 项，自启动补回 {} 项".format(
            "成功" if result["reg"] else "失败", result["env"], result["run"]))
        self.log("建议重启系统使环境变量完全生效。")
        self._render_detect(detector.detect_all())
        self._refresh_status()
        self._set_status("还原完成，建议重启系统完全生效", "ok")

    def on_clear_cache(self):
        if not messagebox.askyesno(
                "StarGust",
                "将清除历史增量快照（中间产物），\n"
                "保留「启动前快照」与「在用快照」以便还原。\n确认清除？"):
            return
        n = backup.clear_cache()
        self.log("缓存清理完成：删除 {} 份历史快照".format(n))
        self._refresh_status()
        self._set_status("缓存清理完成：删除 {} 份历史快照".format(n), "ok")

    def run(self):
        self.root.mainloop()
