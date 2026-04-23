# 局域网共享（TUI「共享」页）

Master–Master **不再依赖** `eclipse-zenoh` 或任何额外 pip 包：发现使用 **UDP 组播 `224.0.0.251` + 自建业务端口**（与系统 mDNS 同组播地址，**不是** UDP 5353），并在开启「提供配置拉取」时在本机起 **小型 HTTP 服务**（gzip 返回 `config.yaml`）。多网卡时会尽量在每张网卡上 join 组播并分别宣告。

## 两种模式

1. **配置 Master–Master**  
   - 打开「局域网发现」后，本机周期性在组播地址上发送 JSON 宣告（含 `node_id`、各网卡 IP、Clash HTTP 端口、`config_port` 等，**不含 PIN**）。  
   - **本机 PIN** 显示在页面上；他机在列表中选中你后，输入 **你屏幕上** 的 3 位 PIN，即可 **拉取你的 `mcs/configs/config.yaml`**（会先备份再覆盖）。  
   - **手动拉取**：若自动发现不可用（例如部分手机热点 AP 隔离），可在「对方 IP / config 端口」中填写对端信息，使用同一 PIN 拉取。  
   - 拉取成功后执行 **`myclash service restart`**（或 `systemctl --user restart myclash.service`）。  
   - 关闭「提供配置拉取」后，本机不再提供配置 HTTP，但仍可发组播宣告（若仍开启发现）。

2. **代理 Master–Slave**  
   - 在 **不安装 MyClashShell** 的 Slave 上使用：按页面中的命令执行 `shell/slave/slave_bootstrap.sh`（或 `curl` 远程脚本），会写入 sudoers 的 `env_keep`、安装 `/etc/myclash-slave/slave.bashrc`，并在 `/etc/bash.bashrc` 增加与 MCS 类似的 source 块。  
   - 新 shell 中执行 `myslave shell on` 即可走 Master 的 HTTP 代理。  
   - **本机 HTTP 镜像（免 scp / 免 Git）**：在 Master 上执行 `myclash share serve [端口]`（默认 **8765**，绑定 `0.0.0.0`），会只读提供 `slave_bootstrap.sh` 与 `connect_other_proxy.sh`（无目录列表）。Slave 上示例：  
     `curl -fsSL http://<MASTER_IP>:<SERVE_PORT>/slave_bootstrap.sh | sudo bash -s -- <MASTER_IP> <CLASH_HTTP_PORT>`  
   - 停止服务：`myclash share stop`；查看是否在跑：`myclash share status`。环境变量：`MYCLASH_SLAVE_SERVE_PORT`、`MYCLASH_SLAVE_SERVE_BIND`。  
   - 需在防火墙中放行 **SERVE_PORT**（脚本下载）以及 **Clash HTTP 代理端口**（Slave 实际走代理）。

## 端口与环境变量

| 变量 | 默认 | 说明 |
|------|------|------|
| `MYCLASH_LAN_UDP_PORT` | 53287 | 组播/广播业务 UDP 端口 |
| `MYCLASH_LAN_CONFIG_PORT` | 53288 | 配置拉取 HTTP（`GET /myclash/v1/config?pin=…&proto=…`） |
| `MYCLASH_LAN_ADDRS` | （自动） | 逗号分隔 IPv4，可选 `/前缀`，强制参与宣告/收听的地址 |

自动枚举在 Linux 上优先使用 `ip -j addr`；失败时退化为单地址（与 `pick_lan_host()` 类似）。

**防火墙**：同网段内需放行 **UDP `MYCLASH_LAN_UDP_PORT`**（入站用于收组播）以及 **TCP `MYCLASH_LAN_CONFIG_PORT`**（当本机「提供配置拉取」开启时）。

**与 `myclash share serve` 的区别**：后者是 **8765** 上只读提供 **Slave 安装脚本**；Master–Master 配置同步使用 **53288**（默认）上的 **config HTTP**，二者独立。

## 安全说明

- 仅在 **可信局域网** 使用；组播与配置 HTTP 均无强加密。  
- **`myclash share serve` 暴露的 HTTP** 仅两个固定路径的只读脚本，无鉴权；任何人能连上该端口即可下载脚本，请勿在公网或未信任网络监听 `0.0.0.0`。  
- **3 位 PIN** 只降低误操作风险，不能替代身份认证。  
- Master 需对 Slave 开放 HTTP 代理端口；若仅代理网页流量，请确保 Clash 已按你的期望监听在局域网可达地址（常见为 `allow-lan` 与端口配置）。

## 其它

- **`MYCLASH_ROOT_PWD`**：必须指向仓库根目录，用于定位 `mcs/configs/config.yaml` 与 `shell/slave/slave_bootstrap.sh`。  
- 与 **旧版使用 Zenoh 的 MCS** 在 Master–Master 上 **协议不兼容**；需双方均为本实现。
