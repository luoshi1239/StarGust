# -*- coding: utf-8 -*-
"""StarGust 端口连通测试：主动 TCP 连接探测指定「目标 IP:端口」是否开放

实现说明：
  零第三方依赖，直接用 socket 发起 TCP 连接（无需系统命令）；
  内置常用端口清单（80/443/22/3389/7890 等）供下拉选择，支持自定义端口；
  批量测试使用线程池并发，避免逐个串行等待。
"""
import socket
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

# 常用端口清单：(说明, 端口号)
COMMON_PORTS = [
    ("HTTP", 80), ("HTTPS", 443), ("SSH", 22), ("FTP", 21),
    ("Telnet", 23), ("SMTP", 25), ("POP3", 110), ("IMAP", 143),
    ("RDP 远程桌面", 3389), ("MySQL", 3306), ("PostgreSQL", 5432),
    ("MSSQL", 1433), ("Redis", 6379), ("MongoDB", 27017),
    ("Elasticsearch", 9200), ("SMB", 445), ("DNS", 53),
    ("Clash 混合代理", 7890), ("Clash 代理", 7891),
    ("V2Ray 默认", 10808), ("V2Ray 代理", 10809), ("SOCKS5", 1080),
    ("Shadowsocks", 8388), ("HTTP 代理", 8080),
]


def tcp_probe(host, port, timeout=3.0):
    """TCP 连接测试单个端口，返回 (ok, latency_ms, err)"""
    t0 = time.perf_counter()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            lat = int((time.perf_counter() - t0) * 1000)
            return True, lat, ""
    except socket.timeout:
        return False, int((time.perf_counter() - t0) * 1000), "连接超时"
    except OSError as e:
        return False, int((time.perf_counter() - t0) * 1000), str(e)[:50]


def test_one(host, port, timeout=3.0):
    """测试单个端口，返回 dict"""
    ok, lat, err = tcp_probe(host, port, timeout)
    return {"host": host, "port": int(port), "ok": ok,
            "latency": lat, "err": err}


def test_many(host, ports, timeout=3.0):
    """并发测试多个端口，返回结果列表（保持传入顺序）"""
    ports = [int(p) for p in ports if str(p).isdigit()]
    ports = list(dict.fromkeys(ports))
    if not ports:
        return []
    results = {}
    with ThreadPoolExecutor(max_workers=min(20, max(1, len(ports)))) as ex:
        futs = {ex.submit(tcp_probe, host, p, timeout): p for p in ports}
        for f in as_completed(futs):
            results[futs[f]] = f.result()
    rows = []
    for p in ports:
        ok, lat, err = results[p]
        rows.append({"host": host, "port": p, "ok": ok,
                     "latency": lat, "err": err})
    return rows
