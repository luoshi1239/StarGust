# -*- coding: utf-8 -*-
"""StarGust 网络诊断工具箱：Ping / Traceroute / DNS 多源解析 / 公网IP / 本机网卡

实现说明（零第三方依赖，全部基于系统自带命令）：
  - ping      : ping -n 次数 -w 超时 目标
  - traceroute: tracert -d -w 500 -h 跳数 目标
  - DNS       : nslookup 域名 DNS服务器（多公共 DNS 对比）
  - 公网IP    : curl -s api.ipify.org / ip-api.com（Windows 10/11 自带 curl）
  - 网卡      : ipconfig /all
"""
import json
import re
import subprocess

# 隐藏子进程控制台窗口（黑窗口闪过问题）
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# 公共 DNS 服务器（多源对比）
PUBLIC_DNS = [
    ("阿里 DNS", "223.5.5.5"),
    ("腾讯 DNSPod", "119.29.29.29"),
    ("114 DNS", "114.114.114.114"),
    ("Google DNS", "8.8.8.8"),
    ("Cloudflare", "1.1.1.1"),
]


def _run(cmd, timeout=30):
    """统一执行系统命令：防黑窗口 + 防 GBK 解码崩溃"""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           timeout=timeout, errors="ignore",
                           creationflags=_NO_WINDOW)
        out = (r.stdout or "") + "\n" + (r.stderr or "")
        return r.returncode, out
    except Exception as e:
        return -1, str(e)


# ---------------------------------------------------------------------------
# Ping
# ---------------------------------------------------------------------------
def ping(target, count=4, timeout=1000):
    """Ping 指定目标，统计延迟与丢包率。
    返回 dict：sent/received/lost/loss_pct/min_ms/max_ms/avg_ms/raw
    """
    cmd = ["ping", "-n", str(count), "-w", str(timeout), target]
    rc, out = _run(cmd, timeout=max(15, int(count * timeout / 1000) + 15))
    data = {
        "target": target, "rc": rc, "raw": out,
        "sent": 0, "received": 0, "lost": 0,
        "loss_pct": None, "min_ms": None, "max_ms": None, "avg_ms": None,
    }

    # 发送 / 接收（中英文兼容）
    m = re.search(r"已发送\s*=\s*(\d+)[^\d]*已接收\s*=\s*(\d+)", out) \
        or re.search(r"Sent\s*=\s*(\d+)[^\d]*Received\s*=\s*(\d+)", out)
    if m:
        data["sent"] = int(m.group(1))
        data["received"] = int(m.group(2))
        data["lost"] = data["sent"] - data["received"]

    # 丢包率（中英文兼容）
    m = re.search(r"\((\d+)%\s*(?:丢失|loss)\)", out)
    if m:
        data["loss_pct"] = int(m.group(1))

    # 延迟：最短 / 最长 / 平均（中英文兼容）
    m = re.search(
        r"(?:最短|Minimum)\s*=\s*(\d+)\s*ms\D+"
        r"(?:最长|Maximum)\s*=\s*(\d+)\s*ms\D+"
        r"(?:平均|Average)\s*=\s*(\d+)\s*ms", out)
    if m:
        data["min_ms"] = int(m.group(1))
        data["max_ms"] = int(m.group(2))
        data["avg_ms"] = int(m.group(3))
    return data


# ---------------------------------------------------------------------------
# Traceroute
# ---------------------------------------------------------------------------
def traceroute(target, max_hops=30):
    """路由追踪，返回 (hops, raw)。
    hops = [{hop, ip, times:[ms...], raw}]
    """
    cmd = ["tracert", "-d", "-w", "500", "-h", str(max_hops), target]
    rc, out = _run(cmd, timeout=180)
    hops = []
    for line in out.splitlines():
        stripped = line.strip()
        m = re.match(r"^(\d+)\s+(.*)$", stripped)
        if not m:
            continue
        hop = int(m.group(1))
        rest = m.group(2)
        times = [int(t) for t in re.findall(
            r"<?\s*(\d+)\s*(?:ms|毫秒)", rest)]
        ipm = re.search(r"\d{1,3}(?:\.\d{1,3}){3}", rest)
        ip = ipm.group(0) if ipm else ""
        hops.append({"hop": hop, "ip": ip, "times": times, "raw": stripped})
    return hops, out


# ---------------------------------------------------------------------------
# DNS 多源对比解析
# ---------------------------------------------------------------------------
def _parse_nslookup(out):
    """从 nslookup 输出提取查询结果地址（最后一个 名称/Name 块之后）"""
    lines = out.splitlines()
    last_name = -1
    for i, ln in enumerate(lines):
        if ln.strip().startswith(("名称", "Name")):
            last_name = i
    addrs = []
    if last_name < 0:
        return addrs
    for ln in lines[last_name + 1:]:
        ln = ln.strip()
        if ln.startswith(("Address:", "Addresses:")):
            rest = ln.split(":", 1)[1].strip()
            for tok in re.split(r"[\s,]+", rest):
                tok = tok.strip()
                if tok and tok not in addrs:
                    addrs.append(tok)
    return addrs


def dns_query(domain, servers=None):
    """用多个公共 DNS 解析指定域名。
    返回 [{label, dns, addrs, rc, raw}]
    """
    servers = servers or PUBLIC_DNS
    results = []
    for label, dns in servers:
        rc, out = _run(["nslookup", domain, dns], timeout=15)
        results.append({
            "label": label, "dns": dns,
            "addrs": _parse_nslookup(out),
            "rc": rc, "raw": out,
        })
    return results


# ---------------------------------------------------------------------------
# 公网 IP + 归属地
# ---------------------------------------------------------------------------
def public_ip():
    """查询公网 IP 与归属地（依赖系统 curl 与外网连通），返回 dict"""
    info = {"ip": "", "error": "", "country": "", "region": "",
            "city": "", "isp": "", "org": "", "as": ""}
    rc, out = _run(["curl", "-s", "--max-time", "10",
                    "https://api.ipify.org"], timeout=15)
    ip = (out or "").strip()
    if not re.match(r"^\d{1,3}(?:\.\d{1,3}){3}$", ip):
        info["error"] = "公网 IP 查询失败（需可访问外网，依赖系统 curl）"
        return info
    info["ip"] = ip

    rc2, out2 = _run(
        ["curl", "-s", "--max-time", "10",
         "https://ip-api.com/json/{}?lang=zh-CN"
         "&fields=status,country,regionName,city,isp,org,as,query".format(ip)],
        timeout=15)
    try:
        j = json.loads(out2 or "{}")
        if j.get("status") == "success":
            info.update({
                "country": j.get("country", ""),
                "region": j.get("regionName", ""),
                "city": j.get("city", ""),
                "isp": j.get("isp", ""),
                "org": j.get("org", ""),
                "as": j.get("as", ""),
            })
        else:
            info["error"] = "归属地查询失败: {}".format(
                j.get("message", "接口返回非 success"))
    except Exception:
        info["error"] = "归属地查询失败（接口无响应）"
    return info


# ---------------------------------------------------------------------------
# 本机网卡信息
# ---------------------------------------------------------------------------
def _clean_val(val):
    """清洗 ipconfig 值：去掉 (首选) 等括号后缀"""
    val = val.strip()
    idx = val.find("(")
    if idx > 0:
        val = val[:idx].strip()
    return val


def local_adapters():
    """读取本机全部网卡信息，返回
    [{name, ip, mask, gateway, dns:[...], mac}]
    """
    rc, out = _run(["ipconfig", "/all"], timeout=30)
    adapters = []
    cur = None
    in_dns = False
    for line in out.splitlines():
        stripped = line.strip()
        # 适配器块头（中文 / 英文，均以冒号结尾且含"适配器/adapter"）
        if ("适配器" in stripped or "adapter" in stripped.lower()) \
                and stripped.endswith(":"):
            if cur:
                adapters.append(cur)
            cur = {"name": stripped[:-1].strip(), "ip": "", "mask": "",
                   "gateway": "", "dns": [], "mac": ""}
            in_dns = False
            continue
        if cur is None:
            continue
        # 字段行： `字段名 . . . . : 值`（中英文点号）
        m = re.match(r"^(.+?)\s*(?:[.．·]\s*)+\s*:\s*(.*)$", stripped)
        if not m:
            # DNS 服务器续行（纯地址行）
            if in_dns:
                tok = stripped.split()[0] if stripped.split() else ""
                if re.match(r"^[0-9a-fA-F:.]+$", tok):
                    cur["dns"].append(tok)
            continue
        key = m.group(1).strip()
        val = m.group(2).strip()
        in_dns = False
        if "IPv4 地址" in key or "IPv4 Address" in key:
            if not cur["ip"]:
                cur["ip"] = _clean_val(val)
        elif "子网掩码" in key or "Subnet Mask" in key:
            if not cur["mask"]:
                cur["mask"] = _clean_val(val)
        elif "默认网关" in key or "Default Gateway" in key:
            if not cur["gateway"]:
                cur["gateway"] = _clean_val(val)
        elif "DNS 服务器" in key or "DNS Servers" in key:
            if val:
                cur["dns"].append(_clean_val(val))
            in_dns = True
        elif "物理地址" in key or "Physical Address" in key:
            if val and not cur["mac"]:
                cur["mac"] = _clean_val(val)
    if cur:
        adapters.append(cur)
    return adapters
