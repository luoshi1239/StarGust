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

# PIL 仅用于品牌 logo 缩放显示；缺失时程序照常运行（仅不显示 logo）
try:
    from PIL import Image, ImageTk
except ImportError:
    Image = ImageTk = None

from . import constants as C
from . import (backup, cleaner, detector, monitor, netcheck,
               netdiag, porttest, proxy, scanner)


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
        """加载品牌 logo（打包后从 _MEIPASS 定位资源）
        优先 PIL 缩放 44x44；PIL 缺失时回退 tk.PhotoImage 原尺寸加载。
        """
        try:
            path = _resource_path(os.path.join("stargust", "assets", "logo.png"))
            if Image is not None:
                img = Image.open(path)
                img = img.resize((44, 44), Image.LANCZOS)
                return ImageTk.PhotoImage(img)
            return tk.PhotoImage(file=path)
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

        # 代理增强区：一键设置 / 取消系统代理 + 连通性测试
        self.proxy_frame = ttk.LabelFrame(tab_detect,
                                          text="代理增强：一键设置 / 取消系统代理 · 连通性测试",
                                          padding=8)
        self.proxy_frame.pack(fill=tk.X, side=tk.BOTTOM, pady=(8, 0))
        pf = ttk.Frame(self.proxy_frame, style="Card.TFrame")
        pf.pack(fill=tk.X)
        ttk.Label(pf, text="Host:", style="Card.TFrame").pack(side=tk.LEFT)
        self.proxy_host_var = tk.StringVar(value="127.0.0.1")
        ttk.Entry(pf, textvariable=self.proxy_host_var, width=16).pack(
            side=tk.LEFT, padx=(4, 10))
        ttk.Label(pf, text="Port:", style="Card.TFrame").pack(side=tk.LEFT)
        self.proxy_port_var = tk.StringVar(value="7890")
        ttk.Entry(pf, textvariable=self.proxy_port_var, width=8).pack(
            side=tk.LEFT, padx=(4, 10))
        self.btn_set_proxy = ttk.Button(pf, text="设置系统代理",
                                        style="Accent.TButton",
                                        command=self.on_set_proxy)
        self.btn_set_proxy.pack(side=tk.LEFT, padx=4)
        self.btn_cancel_proxy = ttk.Button(pf, text="取消系统代理",
                                           command=self.on_cancel_proxy)
        self.btn_cancel_proxy.pack(side=tk.LEFT, padx=4)
        self.btn_test_proxy = ttk.Button(pf, text="测试代理连通性",
                                         command=self.on_test_proxy)
        self.btn_test_proxy.pack(side=tk.LEFT, padx=4)
        self.proxy_status = ttk.Label(self.proxy_frame, text="",
                                      style="Card.TFrame",
                                      foreground="#8a94a6")
        self.proxy_status.pack(anchor=tk.W, pady=(6, 0))

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

        # 端口连通测试子区：主动 TCP 连接探测指定 目标IP:端口
        self.pt_frame = ttk.LabelFrame(tab_port,
                                       text="端口连通测试（主动 TCP 连接探测）",
                                       padding=8)
        self.pt_frame.pack(fill=tk.X, side=tk.BOTTOM, pady=(8, 0))
        ptb = ttk.Frame(self.pt_frame, style="Card.TFrame")
        ptb.pack(fill=tk.X)
        ttk.Label(ptb, text="目标 IP:", style="Card.TFrame").pack(side=tk.LEFT)
        self.pt_host_var = tk.StringVar(value="127.0.0.1")
        ttk.Entry(ptb, textvariable=self.pt_host_var, width=16).pack(
            side=tk.LEFT, padx=(4, 10))
        ttk.Label(ptb, text="端口:", style="Card.TFrame").pack(side=tk.LEFT)
        self.pt_port_var = tk.StringVar(value="7890")
        self.pt_port_cb = ttk.Combobox(
            ptb, textvariable=self.pt_port_var, width=10,
            values=[str(p) for _, p in porttest.COMMON_PORTS],
            state="normal")
        self.pt_port_cb.pack(side=tk.LEFT, padx=(4, 10))
        self.btn_ptest = ttk.Button(ptb, text="测试该端口",
                                    style="Accent.TButton",
                                    command=self.on_port_test)
        self.btn_ptest.pack(side=tk.LEFT, padx=4)
        self.btn_ptest_many = ttk.Button(ptb, text="测试全部常用端口",
                                         command=self.on_port_test_many)
        self.btn_ptest_many.pack(side=tk.LEFT, padx=4)
        self.pt_summary = ttk.Label(self.pt_frame, text="",
                                    style="Card.TFrame",
                                    foreground="#8a94a6")
        self.pt_summary.pack(anchor=tk.W, pady=(4, 0))

        ptcols = ("p_host", "p_port", "p_status", "p_latency")
        self.ptree_test = ttk.Treeview(self.pt_frame, columns=ptcols,
                                       show="headings", height=4)
        for cid, text, width in (
            ("p_host", "目标", 150),
            ("p_port", "端口", 70),
            ("p_status", "状态", 180),
            ("p_latency", "延迟", 90),
        ):
            self.ptree_test.heading(cid, text=text)
            self.ptree_test.column(cid, width=width, anchor=tk.W)
        self.ptree_test.tag_configure("ok", foreground="#1b5e20")
        self.ptree_test.tag_configure("fail", foreground="#b71c1c")
        self.ptree_test.pack(fill=tk.X, pady=(6, 0))

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

        # --- Tab4 网络诊断 ---
        tab_diag = ttk.Frame(self.notebook, style="TNotebook.TFrame")
        self.notebook.add(tab_diag, text="网络诊断")

        diag_bar = ttk.Frame(tab_diag, style="TNotebook.TFrame")
        diag_bar.pack(fill=tk.X, pady=(0, 6))

        # 行1：Ping | Tracert
        row1 = ttk.Frame(diag_bar, style="TNotebook.TFrame")
        row1.pack(fill=tk.X, pady=(0, 6))
        ping_box = ttk.LabelFrame(row1, text="Ping 目标", padding=6)
        ping_box.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
        ttk.Label(ping_box, text="目标:", style="Card.TFrame").pack(side=tk.LEFT)
        self.ping_host_var = tk.StringVar(value="www.baidu.com")
        ttk.Entry(ping_box, textvariable=self.ping_host_var,
                  width=18).pack(side=tk.LEFT, padx=(4, 8))
        ttk.Label(ping_box, text="次数:", style="Card.TFrame").pack(side=tk.LEFT)
        self.ping_count_var = tk.StringVar(value="4")
        ttk.Spinbox(ping_box, from_=1, to=20, width=4,
                    textvariable=self.ping_count_var).pack(side=tk.LEFT, padx=(4, 8))
        ttk.Label(ping_box, text="超时(ms):", style="Card.TFrame").pack(side=tk.LEFT)
        self.ping_timeout_var = tk.StringVar(value="1000")
        ttk.Spinbox(ping_box, from_=100, to=5000, increment=100, width=6,
                    textvariable=self.ping_timeout_var).pack(side=tk.LEFT, padx=(4, 8))
        self.btn_ping = ttk.Button(ping_box, text="Ping",
                                   style="Accent.TButton", command=self.on_ping)
        self.btn_ping.pack(side=tk.LEFT, padx=4)

        tr_box = ttk.LabelFrame(row1, text="Traceroute 路由追踪", padding=6)
        tr_box.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Label(tr_box, text="目标:", style="Card.TFrame").pack(side=tk.LEFT)
        self.tr_host_var = tk.StringVar(value="www.baidu.com")
        ttk.Entry(tr_box, textvariable=self.tr_host_var,
                  width=18).pack(side=tk.LEFT, padx=(4, 8))
        self.btn_traceroute = ttk.Button(tr_box, text="路由追踪",
                                         command=self.on_traceroute)
        self.btn_traceroute.pack(side=tk.LEFT, padx=4)

        # 行2：DNS | 公网IP / 网卡
        row2 = ttk.Frame(diag_bar, style="TNotebook.TFrame")
        row2.pack(fill=tk.X, pady=(0, 6))
        dns_box = ttk.LabelFrame(row2, text="DNS 多源对比解析", padding=6)
        dns_box.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
        ttk.Label(dns_box, text="域名:", style="Card.TFrame").pack(side=tk.LEFT)
        self.dns_host_var = tk.StringVar(value="www.baidu.com")
        ttk.Entry(dns_box, textvariable=self.dns_host_var,
                  width=18).pack(side=tk.LEFT, padx=(4, 8))
        self.btn_dns = ttk.Button(dns_box, text="多源解析", command=self.on_dns)
        self.btn_dns.pack(side=tk.LEFT, padx=4)

        info_box = ttk.LabelFrame(row2, text="公网 / 本机", padding=6)
        info_box.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.btn_pubip = ttk.Button(info_box, text="公网 IP + 归属地",
                                    command=self.on_public_ip)
        self.btn_pubip.pack(side=tk.LEFT, padx=4)
        self.btn_adapters = ttk.Button(info_box, text="本机网卡信息",
                                       command=self.on_adapters)
        self.btn_adapters.pack(side=tk.LEFT, padx=4)
        self.diag_summary = ttk.Label(info_box, text="", style="Card.TFrame",
                                      foreground="#8a94a6")
        self.diag_summary.pack(side=tk.LEFT, padx=(10, 0))

        # 诊断结果表格
        dcols = ("diag_item", "diag_value", "diag_note")
        self.diag_tree = ttk.Treeview(tab_diag, columns=dcols, show="headings")
        for cid, text, width in (
            ("diag_item", "项目 / 跳数", 220),
            ("diag_value", "结果", 380),
            ("diag_note", "备注", 220),
        ):
            self.diag_tree.heading(cid, text=text)
            self.diag_tree.column(cid, width=width, anchor=tk.W)
        self.diag_tree.tag_configure("ok", foreground="#1b5e20")
        self.diag_tree.tag_configure("fail", foreground="#b71c1c")
        self.diag_tree.pack(fill=tk.BOTH, expand=True)

        # --- Tab5 实时监控 ---
        tab_mon = ttk.Frame(self.notebook, style="TNotebook.TFrame")
        self.notebook.add(tab_mon, text="实时监控")

        mon_bar = ttk.Frame(tab_mon, style="TNotebook.TFrame")
        mon_bar.pack(fill=tk.X, pady=(0, 6))
        self.mon_auto_var = tk.BooleanVar(value=False)
        self.chk_mon_auto = ttk.Checkbutton(mon_bar, text="自动刷新（每秒）",
                                            variable=self.mon_auto_var,
                                            command=self.on_monitor_auto)
        self.chk_mon_auto.pack(side=tk.LEFT)
        self.btn_mon_refresh = ttk.Button(mon_bar, text="立即刷新",
                                          style="Accent.TButton",
                                          command=self.on_monitor_refresh)
        self.btn_mon_refresh.pack(side=tk.LEFT, padx=8)
        self.mon_bw = ttk.Label(mon_bar, text="↓ --  ↑ --",
                                style="TNotebook.TFrame",
                                foreground="#6C5CE7",
                                font=("Microsoft YaHei UI", 13, "bold"))
        self.mon_bw.pack(side=tk.LEFT, padx=(12, 0))
        self.mon_stat = ttk.Label(mon_bar, text="TCP 连接: --",
                                  style="TNotebook.TFrame",
                                  foreground="#455a64")
        self.mon_stat.pack(side=tk.LEFT, padx=(12, 0))

        mcols = ("m_proc", "m_pid", "m_local", "m_remote", "m_state")
        self.mtree = ttk.Treeview(tab_mon, columns=mcols, show="headings")
        for cid, text, width in (
            ("m_proc", "进程", 170),
            ("m_pid", "PID", 70),
            ("m_local", "本地地址", 190),
            ("m_remote", "远端地址", 200),
            ("m_state", "状态", 100),
        ):
            self.mtree.heading(cid, text=text)
            self.mtree.column(cid, width=width, anchor=tk.W)
        self.mtree.tag_configure("established", foreground="#1b5e20")
        self.mtree.tag_configure("listening", foreground="#1565c0")
        self.mtree.pack(fill=tk.BOTH, expand=True)
        self._mon_job = None
        self._mon_running = False

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
                  self.btn_clean, self.btn_restore, self.btn_cache,
                  self.btn_net, self.btn_set_proxy, self.btn_cancel_proxy,
                  self.btn_test_proxy, self.btn_ptest, self.btn_ptest_many,
                  self.btn_ping, self.btn_traceroute, self.btn_dns,
                  self.btn_pubip, self.btn_adapters):
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

    # ------------------------------------------------------------ 网络诊断
    def _diag_clear(self):
        for i in self.diag_tree.get_children():
            self.diag_tree.delete(i)

    def on_ping(self):
        host = self.ping_host_var.get().strip()
        if not host:
            self._set_status("请输入 Ping 目标", "error")
            return
        try:
            count = int(self.ping_count_var.get())
            timeout = int(self.ping_timeout_var.get())
        except ValueError:
            self._set_status("次数 / 超时须为数字", "error")
            return
        self.log("Ping {}（{} 次，超时 {}ms）……".format(host, count, timeout))
        self._set_status("Ping 执行中……", "busy")
        self._run_async(lambda: netdiag.ping(host, count, timeout),
                        self._render_ping)

    def _render_ping(self, d):
        self._diag_clear()
        ok = d["received"] > 0
        self.diag_tree.insert("", tk.END, tags=("ok" if ok else "fail",), values=(
            "Ping 目标", d["target"],
            "发送 {} / 接收 {}".format(d["sent"], d["received"])))
        self.diag_tree.insert("", tk.END, values=(
            "丢包率",
            "{}%".format(d["loss_pct"] if d["loss_pct"] is not None else "-"),
            ""))
        if d["avg_ms"] is not None:
            self.diag_tree.insert("", tk.END, values=(
                "平均延迟", "{} ms".format(d["avg_ms"]), ""))
            self.diag_tree.insert("", tk.END, values=(
                "延迟范围", "{} ~ {} ms".format(d["min_ms"], d["max_ms"]), ""))
        if not ok:
            self.diag_tree.insert("", tk.END, tags=("fail",), values=(
                "结果", "目标不可达或全部超时", ""))
        msg = "Ping {}：丢包 {}%，平均 {}ms".format(
            d["target"],
            d["loss_pct"] if d["loss_pct"] is not None else "-",
            "{} ms".format(d["avg_ms"]) if d["avg_ms"] is not None else "-")
        self.log("  " + msg)
        self._set_status(msg, "ok" if ok else "error")

    def on_traceroute(self):
        host = self.tr_host_var.get().strip()
        if not host:
            self._set_status("请输入路由追踪目标", "error")
            return
        self.log("路由追踪 {}……".format(host))
        self._set_status("路由追踪执行中（可能需要数十秒）……", "busy")
        self._run_async(lambda: netdiag.traceroute(host), self._render_traceroute)

    def _render_traceroute(self, data):
        hops, _raw = data
        self._diag_clear()
        if not hops:
            self.diag_tree.insert("", tk.END, tags=("fail",), values=(
                "路由追踪", "无结果", "目标不可达或全部超时"))
            self._set_status("路由追踪无结果", "error")
            return
        for h in hops:
            times = " / ".join("{}ms".format(t) for t in h["times"]) or "*"
            self.diag_tree.insert("", tk.END, values=(
                "跳 {}".format(h["hop"]), h["ip"] or "请求超时", times))
        self._set_status("路由追踪完成：共 {} 跳".format(len(hops)), "ok")
        self.log("  路由追踪完成：共 {} 跳".format(len(hops)))

    def on_dns(self):
        domain = self.dns_host_var.get().strip()
        if not domain:
            self._set_status("请输入域名", "error")
            return
        self.log("DNS 多源对比解析 {}……".format(domain))
        self._set_status("DNS 解析中……", "busy")
        self._run_async(lambda: netdiag.dns_query(domain), self._render_dns)

    def _render_dns(self, results):
        self._diag_clear()
        ok_n = 0
        for r in results:
            ok = bool(r["addrs"])
            if ok:
                ok_n += 1
            self.diag_tree.insert(
                "", tk.END, tags=("ok" if ok else "fail",), values=(
                    "{} ({})".format(r["label"], r["dns"]),
                    "  ".join(r["addrs"]) if r["addrs"] else "无解析结果",
                    "解析成功" if ok else "无记录 / 解析失败"))
        self._set_status("DNS 解析完成：{}/{} 命中".format(ok_n, len(results)),
                         "ok" if ok_n else "error")
        self.log("  DNS 多源对比：{}/{} 个 DNS 命中".format(ok_n, len(results)))

    def on_public_ip(self):
        self.log("查询公网 IP 与归属地……")
        self._set_status("查询公网 IP 中……", "busy")
        self._run_async(netdiag.public_ip, self._render_public_ip)

    def _render_public_ip(self, info):
        self._diag_clear()
        if info.get("ip"):
            self.diag_tree.insert("", tk.END, tags=("ok",), values=(
                "公网 IP", info["ip"], ""))
            loc = "{} {} {}".format(info.get("country", ""),
                                    info.get("region", ""),
                                    info.get("city", "")).strip()
            if loc:
                self.diag_tree.insert("", tk.END, values=("归属地", loc, ""))
            if info.get("isp"):
                self.diag_tree.insert("", tk.END, values=("运营商", info["isp"], ""))
            if info.get("org"):
                self.diag_tree.insert("", tk.END, values=("组织", info["org"], ""))
            self._set_status("公网 IP：{}".format(info["ip"]), "ok")
            self.log("  公网 IP：{}".format(info["ip"]))
            if info.get("error"):
                self.diag_tree.insert("", tk.END, tags=("fail",), values=(
                    "归属地", "查询失败", info["error"]))
                self.log("  " + info["error"])
        else:
            self.diag_tree.insert("", tk.END, tags=("fail",), values=(
                "公网 IP", "查询失败", info.get("error", "无法获取外网 IP")))
            self._set_status("公网 IP 查询失败", "error")

    def on_adapters(self):
        self.log("读取本机网卡信息……")
        self._set_status("读取网卡信息中……", "busy")
        self._run_async(netdiag.local_adapters, self._render_adapters)

    def _render_adapters(self, adapters):
        self._diag_clear()
        if not adapters:
            self.diag_tree.insert("", tk.END, tags=("fail",), values=(
                "网卡信息", "未获取到", "ipconfig 无输出或权限不足"))
            self._set_status("网卡信息读取失败", "error")
            return
        for a in adapters:
            self.diag_tree.insert("", tk.END, values=(
                "网卡", a["name"], "MAC {}".format(a["mac"] or "-")))
            self.diag_tree.insert("", tk.END, values=(
                "  IPv4", a["ip"] or "-", "掩码 {}".format(a["mask"] or "-")))
            self.diag_tree.insert("", tk.END, values=(
                "  网关", a["gateway"] or "-",
                "DNS {}".format(" ".join(a["dns"]) if a["dns"] else "-")))
        self._set_status("已读取 {} 张网卡".format(len(adapters)), "ok")
        self.log("  共读取 {} 张网卡".format(len(adapters)))

    # ------------------------------------------------------------ 端口连通测试
    def on_port_test(self):
        host = self.pt_host_var.get().strip()
        port = self.pt_port_var.get().strip()
        if not host:
            self._set_status("请输入目标 IP", "error")
            return
        if not port.isdigit() or not (1 <= int(port) <= 65535):
            self._set_status("端口须为 1-65535 的数字", "error")
            return
        self.log("端口连通测试 {}:{}……".format(host, port))
        self._set_status("测试端口 {}:{}……".format(host, port), "busy")
        self._run_async(lambda: porttest.test_one(host, int(port)),
                        self._render_port_test)

    def on_port_test_many(self):
        host = self.pt_host_var.get().strip()
        if not host:
            self._set_status("请输入目标 IP", "error")
            return
        ports = [str(p) for _, p in porttest.COMMON_PORTS]
        self.log("并发测试 {} 的全部常用端口……".format(host))
        self._set_status("测试全部常用端口中……", "busy")
        self._run_async(lambda: porttest.test_many(host, ports),
                        self._render_port_test_many)

    def _render_port_test(self, r):
        for i in self.ptree_test.get_children():
            self.ptree_test.delete(i)
        tag = "ok" if r["ok"] else "fail"
        status = ("开放 · {} ms".format(r["latency"]) if r["ok"]
                  else "关闭/拒绝 · {}".format(r["err"] or "无响应"))
        self.ptree_test.insert("", tk.END, tags=(tag,), values=(
            "{}:{}".format(r["host"], r["port"]), r["port"], status,
            "{} ms".format(r["latency"]) if r["ok"] else "-"))
        self.pt_summary.configure(
            text="{}:{} {}".format(r["host"], r["port"],
                                   "可连通" if r["ok"] else "不可连通"),
            foreground="#1b5e20" if r["ok"] else "#b71c1c")
        self.log("  端口 {}:{} -> {}".format(
            r["host"], r["port"], "开放" if r["ok"] else "关闭/拒绝"))
        self._set_status("端口测试完成：{}:{} {}".format(
            r["host"], r["port"], "开放" if r["ok"] else "不可连通"),
            "ok" if r["ok"] else "error")

    def _render_port_test_many(self, rows):
        for i in self.ptree_test.get_children():
            self.ptree_test.delete(i)
        open_n = 0
        for r in rows:
            if r["ok"]:
                open_n += 1
                tag = "ok"
                status = "开放 · {} ms".format(r["latency"])
                lat = "{} ms".format(r["latency"])
            else:
                tag = "fail"
                status = "关闭/拒绝 · {}".format(r["err"] or "无响应")
                lat = "-"
            self.ptree_test.insert("", tk.END, tags=(tag,), values=(
                "{}:{}".format(r["host"], r["port"]), r["port"], status, lat))
        self.pt_summary.configure(
            text="{} 个常用端口，开放 {} 个".format(len(rows), open_n),
            foreground="#1b5e20" if open_n else "#b71c1c")
        self.log("  常用端口测试：{} 个开放 / 共 {}".format(open_n, len(rows)))
        self._set_status("常用端口测试完成：开放 {} / 共 {}".format(
            open_n, len(rows)), "ok" if open_n else "error")

    # ------------------------------------------------------------ 实时监控
    @staticmethod
    def _fmt_bw(bps):
        if bps is None:
            return "--"
        if bps >= 1024 * 1024:
            return "{:.2f} MB/s".format(bps / 1024 / 1024)
        if bps >= 1024:
            return "{:.1f} KB/s".format(bps / 1024)
        return "{} B/s".format(bps)

    def _monitor_collect(self):
        """后台采集监控数据，返回 (bw, rows, stats)"""
        try:
            bw = monitor.get_bandwidth()
            rows, stats = monitor.get_connections()
            return bw, rows, stats
        except Exception as e:
            self.log("监控采集出错: {}".format(e))
            return None, [], {}

    def _apply_monitor(self, data):
        bw, rows, stats = data
        if bw is not None:
            self.mon_bw.configure(text="↓ {}  ↑ {}".format(
                self._fmt_bw(bw[0]), self._fmt_bw(bw[1])))
        else:
            self.mon_bw.configure(text="↓ --  ↑ --")
        self.mon_stat.configure(text="TCP 连接 {} | 已建立 {} | 监听 {}".format(
            stats.get("total", 0), stats.get("established", 0),
            stats.get("listening", 0)))
        for i in self.mtree.get_children():
            self.mtree.delete(i)
        for r in rows:
            st = r["state"].lower()
            tag = "established" if st == "established" else (
                "listening" if st == "listening" else "")
            self.mtree.insert("", tk.END,
                              tags=(tag,) if tag else (), values=(
                                  r["process"], r["pid"], r["local"],
                                  r["remote"], r["state"]))

    def _mon_worker(self):
        data = self._monitor_collect()
        try:
            self.root.after(0, lambda: self._apply_monitor(data))
        except Exception:
            pass

    def on_monitor_refresh(self):
        if self._busy:
            self.log("有任务执行中，请稍候……")
            return
        if getattr(self, "_mon_busy", False):
            return
        self._mon_busy = True
        self.log("手动刷新网络实时监控……")
        self._set_status("刷新网络状态中……", "busy")

        def worker():
            data = self._monitor_collect()
            self._mon_busy = False
            try:
                self.root.after(0, lambda: self._apply_monitor(data))
                self.root.after(0, lambda: self._set_status("网络状态已刷新", "ok"))
            except Exception:
                pass

        threading.Thread(target=worker, daemon=True).start()

    def on_monitor_auto(self):
        if self.mon_auto_var.get():
            self._start_monitor_loop()
        else:
            self._stop_monitor_loop()

    def _start_monitor_loop(self):
        self._stop_monitor_loop()
        self._mon_running = True
        self._mon_tick()

    def _mon_tick(self):
        if not getattr(self, "_mon_running", False):
            return
        try:
            if not self._busy:
                threading.Thread(target=self._mon_worker, daemon=True).start()
            self._mon_job = self.root.after(1000, self._mon_tick)
        except Exception:
            pass

    def _stop_monitor_loop(self):
        self._mon_running = False
        if getattr(self, "_mon_job", None):
            try:
                self.root.after_cancel(self._mon_job)
            except Exception:
                pass
            self._mon_job = None

    # ------------------------------------------------------------ 代理增强
    def _refresh_detect_light(self):
        """静默刷新残留检测视图（代理变更后后台重检，不阻塞界面）"""

        def worker():
            try:
                re = detector.detect_all()
                self.root.after(0, lambda: self._render_detect(re))
            except Exception:
                pass

        threading.Thread(target=worker, daemon=True).start()

    def on_set_proxy(self):
        host = self.proxy_host_var.get().strip()
        port = self.proxy_port_var.get().strip()
        if not host or not port.isdigit():
            self._set_status("请输入有效的 Host 与端口", "error")
            return
        self.log("设置系统代理 {}:{}……".format(host, port))
        self._set_status("设置系统代理中……", "busy")
        self._run_async(lambda: proxy.set_system_proxy(host, int(port)),
                        self._after_proxy_op)

    def on_cancel_proxy(self):
        self.log("取消系统代理……")
        self._set_status("取消系统代理中……", "busy")
        self._run_async(proxy.cancel_system_proxy, self._after_proxy_op)

    def on_test_proxy(self):
        host = self.proxy_host_var.get().strip()
        port = self.proxy_port_var.get().strip()
        if not host or not port.isdigit():
            self._set_status("请输入有效的 Host 与端口", "error")
            return
        self.log("TCP 探测代理 {}:{}……".format(host, port))
        self._set_status("测试代理连通性中……", "busy")
        self._run_async(lambda: proxy.test_proxy(host, int(port)),
                        self._after_proxy_test)

    def _after_proxy_op(self, res):
        ok, msg = res
        self.proxy_status.configure(
            text=msg, foreground=("#1b5e20" if ok else "#b71c1c"))
        self.log("  " + msg)
        self._set_status(msg, "ok" if ok else "error")
        # 代理变更后刷新残留检测视图
        self._refresh_detect_light()

    def _after_proxy_test(self, res):
        ok, lat, err = res
        host = self.proxy_host_var.get().strip()
        port = self.proxy_port_var.get().strip()
        if ok:
            msg = "{}:{} 代理可连通，延迟 {} ms".format(host, port, lat)
            self.proxy_status.configure(text=msg, foreground="#1b5e20")
            self._set_status(msg, "ok")
        else:
            msg = "{}:{} 代理不可连通：{}".format(host, port, err or "无响应")
            self.proxy_status.configure(text=msg, foreground="#b71c1c")
            self._set_status(msg, "error")
        self.log("  " + msg)

    def run(self):
        self.root.mainloop()
