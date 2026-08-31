---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: d0cbf299c1fe88dadee21ddd749378e3_9140a470a55c11f1b8ae525400287e28
    ReservedCode1: 9uSZdoetVb3t2//4aqaQOeSP32J6ZOUdCxJboBmbQBKnQAVccX8WTgMCUudcQtQ51RQPjvgyK0ufwb5hQLxfetfa18bwqYJUKrWoShjJFbiWFi1eupGFsMnGoMmDFBahjGPZhA9IbOsfr/D+727/Dh+JYeuDfqaIEISexf6Vf5HaHOO12FFc8qLj7lM=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: d0cbf299c1fe88dadee21ddd749378e3_9140a470a55c11f1b8ae525400287e28
    ReservedCode2: 9uSZdoetVb3t2//4aqaQOeSP32J6ZOUdCxJboBmbQBKnQAVccX8WTgMCUudcQtQ51RQPjvgyK0ufwb5hQLxfetfa18bwqYJUKrWoShjJFbiWFi1eupGFsMnGoMmDFBahjGPZhA9IbOsfr/D+727/Dh+JYeuDfqaIEISexf6Vf5HaHOO12FFc8qLj7lM=
---



# StarGust（星息）—— 网络代理残留一键清理工具

> 风过尘尽，一切如新

## 简介

StarGust 是一款 Windows 图形化工具，用于一键检测并清理网络代理残留，解决「代理软件退出后网络仍然异常」的问题。面向 FlClash、Clash Verge/Rev、Clash for Windows、v2rayN、sing-box、Shadowsocks 等常见代理软件场景。

## 使用方式

- 双击 `StarGust.exe` 运行，首次启动会弹出 UAC 提权请求（必须允许，否则无法读写注册表）。
- 若未提权，程序会自动重新请求管理员权限。

## 功能说明

| 按钮 | 功能 |
|---|---|
| 检测残留 | 扫描系统代理 / WinHTTP / 环境变量 / 代理进程 / 自启动项 / 软件配置目录 |
| 网络连通 | TCP 并发探测内网（默认网关、常见路由器、本机服务）与外网（百度 / 腾讯 / GitHub / 公共 DNS 等）站点，显示连通状态与延迟，排查代理清理后网络是否恢复 |
| 快速端口扫描 | 仅检查已知代理端口（7890/7897/10808/10809/57321 等约 50 个） |
| 全端口扫描 | 列出全部处于监听状态的 TCP 端口及占用进程 |
| 一键清理 | 关闭系统代理、重置 WinHTTP、删除代理环境变量、强制结束代理进程、删除勾选的自启动项 |
| 一键还原 | 从「启动前快照」恢复系统代理与代理环境变量（优先），无启动前快照则用最近一次在用快照 |
| 清缓存 | 删除历史增量快照（中间产物），保留「启动前快照」与「在用快照」 |

## 安全设计

- **启动前快照**：首次运行强制保存，清理出错可一键还原，避免修改损坏配置。
- **每次清理前自动备份**：生成带时间戳的历史增量快照，可被「清缓存」清除，不影响还原能力。
- **强制恢复网络**（隐藏按钮）：普通清理连续 3 次未完全生效后解锁，点击有高危警告。仅删除代理相关环境变量（http_proxy/https_proxy/all_proxy 等）并重置系统代理，**不修改 PATH 等其它系统变量**。
- **进程清理**：仅结束命中代理白名单的进程（FlClash、Clash 系列、mihomo、v2ray 等），并内置排除名单（安全软件进程如 HipsDaemon、360、Windows Defender 不会误杀）。
- **自启动项**：只检测 + 界面勾选确认，不自动删除。
- **软件配置目录**：仅报告不清理，避免误删用户数据。

## 快照存储位置

`%LOCALAPPDATA%\StarGust\backup\`

## 技术信息

- 开发语言：Python 3.11（标准库 + tkinter，无第三方依赖）
- 打包：PyInstaller 6.22，单文件，UAC 提权（requireAdministrator）
- 核心机制：注册表（WinINET 系统代理、环境变量、Run 自启）、`netsh winhttp`、`netstat` / `tasklist` / `taskkill` 系统默认接口
- 运行环境：Windows 10 / 11（x64），需管理员权限

## 注意事项

- 修改系统代理、环境变量、自启动项属系统级变更，请确认了解后再操作。
- 还原环境变量后建议重启系统完全生效。
- 清理后若发现软件路径异常，请使用「一键还原」恢复启动前状态。
*（内容由AI生成，仅供参考）*
*（内容由AI生成，仅供参考）*
