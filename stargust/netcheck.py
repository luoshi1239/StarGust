# -*- coding: utf-8 -*-
"""StarGust 网络连通性检测：多线程并发 TCP 探测内网 / 外网常见站点

说明：
  - 用 socket 建立 TCP 连接测延迟（比 ICMP ping 更可靠，多数站点屏蔽 ICMP 但放行 443）
  - 对域名先做 DNS 解析，解析失败直接判失败，并记录错误
  - 内网站点动态获取默认网关 + 固定常见内网地址；外网站点用常见 CDN / DNS
"""
import socket
import threading
import time
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed

# ---- 外网常见探测目标（host, 端口, 说明）----
WAN_TARGETS = [
    ("www.baidu.com", 443, "百度"),
    ("www.qq.com", 443, "腾讯"),
    ("www.taobao.com", 443, "阿里"),
    ("www.aliyun.com", 443, "阿里云"),
    ("www.google.com", 443, "Google"),
    ("www.youtube.com", 443, "YouTube"),
    ("github.com", 443, "GitHub"),
    ("www.cloudflare.com", 443, "Cloudflare"),
    ("223.5.5.5", 53, "阿里 DNS"),
    ("8.8.8.8", 53, "谷歌 DNS"),
    ("114.114.114.114", 53, "114 DNS"),
]

# ---- 内网固定探测目标 ----
LAN_TARGETS = [
    ("100.64.0.1", 443, "Tailscale 网关"),
    ("192.168.1.1", 80, "常见路由器 192.168.1.1"),
    ("127.0.0.1", 5666, "本机 fnOS 5666"),
]


def get_default_gateway():
    """通过 route print 解析默认网关（0.0.0.0 行）"""
    try:
        out = subprocess.run(
            ["route", "print", "0.0.0.0"],
            capture_output=True, text=True, timeout=8,
            creationflags=0x08000000, errors="ignore",
        ).stdout or ""
        for line in out.splitlines():
            parts = line.split()
            if len(parts) >= 5 and parts[0] == "0.0.0.0" and parts[1] == "0.0.0.0":
                return parts[2]
    except Exception:
        pass
    return None


def build_targets():
    """构建完整探测目标列表：内网(动态网关+固定) + 外网，返回 (host, port, note, zone)"""
    targets = []
    gw = get_default_gateway()
    if gw:
        targets.append((gw, 443, "默认网关 {}".format(gw), "内网"))
    for host, port, note in LAN_TARGETS:
        targets.append((host, port, note, "内网"))
    for host, port, note in WAN_TARGETS:
        targets.append((host, port, note, "外网"))
    return targets


def probe_one(host, port, timeout=3.0):
    """探测单个目标，返回 (ok, latency_ms, ip, err)"""
    # DNS 解析
    try:
        ip = socket.gethostbyname(host)
    except socket.gaierror:
        return False, 0, "", "DNS 解析失败"
    t0 = time.perf_counter()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            latency = int((time.perf_counter() - t0) * 1000)
            return True, latency, ip, ""
    except socket.timeout:
        return False, int((time.perf_counter() - t0) * 1000), ip, "连接超时"
    except OSError as e:
        return False, int((time.perf_counter() - t0) * 1000), ip, str(e)[:40]


def run_all(timeout=3.0):
    """并发探测所有目标，返回结果列表（保持顺序）"""
    targets = build_targets()
    results = {}
    with ThreadPoolExecutor(max_workers=10) as ex:
        futures = {
            ex.submit(probe_one, host, port, timeout): (host, port, note, zone)
            for host, port, note, zone in targets
        }
        for fut in as_completed(futures):
            key = futures[fut]
            results[key] = fut.result()

    rows = []
    for host, port, note, zone in targets:
        ok, latency, ip, err = results[(host, port, note, zone)]
        rows.append({
            "host": host,
            "port": port,
            "note": note,
            "zone": zone,
            "ok": ok,
            "latency": latency,
            "ip": ip,
            "err": err,
        })
    return rows
