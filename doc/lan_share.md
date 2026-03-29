# 局域网共享（TUI「共享」页）

需要 **Python venv 已安装 `eclipse-zenoh`**（完整安装见 `install/install.sh` 中的 pip 列表）。仅使用概览/代理/配置页时可以不装 Zenoh。

## 两种模式

1. **配置 Master–Master**  
   - 打开「局域网发现」后，本机会在局域网内广播极简节点信息（不含 PIN）。  
   - **本机 PIN** 显示在页面上；他机在下拉框选中你后，输入 **你屏幕上** 的 3 位 PIN，即可 **拉取你的 `clash/configs/config.yaml`** 到其本机（会先备份再覆盖）。  
   - 拉取成功后需 **`sudo systemctl restart myclash`**。  
   - 关闭「提供配置拉取」后，本机不再响应配置查询，但仍可发广播（若仍开启发现）。

2. **代理 Master–Slave**  
   - 在 **不安装 MyClashShell** 的 Slave 上使用：按页面中的命令执行 `shell/slave/slave_bootstrap.sh`（或 `curl` 远程脚本），会写入 sudoers 的 `env_keep`、安装 `/etc/myclash-slave/slave.bashrc`，并在 `/etc/bash.bashrc` 增加与 MCS 类似的 source 块。  
   - 新 shell 中执行 `myslave shell on` 即可走 Master 的 HTTP 代理。  
   - **本机 HTTP 镜像（免 scp / 免 Git）**：在 Master 上执行 `myclash share serve [端口]`（默认 **8765**，绑定 `0.0.0.0`），会只读提供 `slave_bootstrap.sh` 与 `connect_other_proxy.sh`（无目录列表）。Slave 上示例：  
     `curl -fsSL http://<MASTER_IP>:<SERVE_PORT>/slave_bootstrap.sh | sudo bash -s -- <MASTER_IP> <CLASH_HTTP_PORT>`  
   - 停止服务：`myclash share stop`；查看是否在跑：`myclash share status`。环境变量：`MYCLASH_SLAVE_SERVE_PORT`、`MYCLASH_SLAVE_SERVE_BIND`。  
   - 需在防火墙中放行 **SERVE_PORT**（脚本下载）以及 **Clash HTTP 代理端口**（Slave 实际走代理）。

## 安全说明

- 仅在 **可信局域网** 使用；HTTP 代理与 Zenoh 默认均无强加密。  
- **`myclash share serve` 暴露的 HTTP** 仅两个固定路径的只读脚本，无鉴权；任何人能连上该端口即可下载脚本，请勿在公网或未信任网络监听 `0.0.0.0`。  
- **3 位 PIN** 只降低误操作风险，不能替代身份认证。  
- Master 需对 Slave 开放 HTTP 代理端口；若仅代理网页流量，请确保 Clash 已按你的期望监听在局域网可达地址（常见为 `allow-lan` 与端口配置）。

## 环境变量

- **`MYCLASH_ROOT_PWD`**：必须指向仓库根目录，用于定位 `clash/configs/config.yaml` 与 `shell/slave/slave_bootstrap.sh`。
