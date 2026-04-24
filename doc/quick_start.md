# MyClashShell Quickstart

myclashshell 仅提供对Ubuntu平台的支持

- [x] amd64
- [x] armv8  (aarch64)
- [x] armv7a
## 安装

```bash
git clone https://github.com/hyaline-wang/MyClashShell.git
cd MyClashShell
# 1) 系统级准备（需 root）：apt 依赖、sudoers 代理保留、清理旧版系统 systemd 与 /etc/bash.bashrc 片段
sudo ./install/install_root.sh
# 不写入 sudoers 里代理 env_keep 时（少见）: sudo ./install/install_root.sh --deactivate-for-sudo
# 2) 用户级安装：venv、下载内核、systemd --user、写入当前用户的 ~/.bashrc（推荐不用 sudo；root 执行时脚本会提示预期路径）
./install/install.sh
##########
source ~/.bashrc
```

**`install_root.sh`**：需要 root。**`install.sh`**：推荐在将使用 MyClash 的登录用户下执行；若以 **root** 执行亦可，脚本会打印 systemd 与 `~/.bashrc` 的预期路径，请自行判断是否合适。`install.sh` 开头用 **`ps -p 1 -o comm=`** 是否为 **`systemd`** 判断本机是否 systemd init；非 root 时还会检查 **`/run/user/$UID`** 与 **`systemctl --user`**。无用户会话时可 **`sudo loginctl enable-linger <用户名>`** 后再装。`apt` 包列表见 **`install/apt-packages.txt`**。

**卸载**：普通用户 `./install/uninstall.sh`（用户 systemd、`~/.bashrc`、本仓库下 `mcs/`）；若曾装过旧版系统服务，再执行 **`sudo ./install/uninstall_root.sh`**。最后可手动删除整个仓库目录。

安装完成后
1. 使用 `myclash` 命令查看软件信息
3. 通过`myclash help` 查看帮助

> 首次使用更新完代理后执行 `myclash service restart`（systemd **用户**服务，无需 sudo）

## 快速开始

### 设置订阅
修改 MyClashShell 目录下生成的 user_config.yaml
```yaml
shell_proxy_default: 'ON'  #  ON / OFF
subscribes:
  <your_proxy_name>:
    url: "<you_proxy_url>"
    backend: clash   # clash：订阅合并 / TUI / 9090 API；v2ray：见下文
default_subscribe: "DEFAULT"
```
 - shell_proxy_default: 选择是否自动在命令行开启代理，保存即生效
 - 每条订阅须为 **`url` + `backend`**（`clash` 或 `v2ray`），不再支持旧版「键名直接对应 URL 字符串」。
 - `<your_proxy_name>` 与 `<you_proxy_url>` 分别为订阅显示名与订阅链接；修改后运行
    ```bash
      # 更新订阅
      myclash service update_subcribe 
    ```
 - Clash 订阅下载的原始 YAML 与 **`cache/current_sub.txt`**（当前订阅名）均在仓库 **`cache/`**；`tmp/` 仅保留安装过程生成物等，与下载缓存分开。
 - **default_subscribe**：当前默认使用的订阅名，可填 `subscribes` 下任意键；**`DEFAULT`** 表示使用 YAML 中**第一个**订阅。`mcs_manager` 会根据该订阅的 **`backend`** 决定拉起 **Clash** 还是 **v2ray**；切换默认订阅后执行 **`myclash service restart`** 使内核与配置一致。

### Clash 与 v2ray 后端（按订阅）

- **`backend: clash`**：参与订阅下载与合并、`myclash service update_subcribe`、TUI、`127.0.0.1:9090` API。
- **`backend: v2ray`**：由 `mcs_manager` 执行 `mcs/bin/v2ray run -config mcs/configs/v2ray.json`；**与 Clash 的 `config.yaml` 无关**，需自行编辑 **`mcs/configs/v2ray.json`**（安装时会从 `install/templates/v2ray-default.json` 拷贝占位，默认 SOCKS `127.0.0.1:7890` 直连出站）。`update_subcribe` 对 v2ray 条目不下载 Clash 配置，仅更新当前订阅名等元数据。
- v2ray 与其它安装包 URL 统一写在 **`install/download.yaml`**（按架构 `amd64` / `armv7` / `arm64`），在 **`install.sh`** 阶段下载到 **`cache/`** 再安装到 **`mcs/bin/v2ray`**。

## 配置

### 设置多个订阅

针对有多个代理的情况,MyClashShell允许同时添加多个代理
```yaml
shell_proxy_default: 'ON'  ##  ON  / OFF
subscribes:
  <your_proxy_name_1>:
    url: "<you_proxy_url_1>"
    backend: clash
  <your_proxy_name_2>:
    url: "<you_proxy_url_2>"
    backend: clash
  <your_proxy_name_3>:
    url: ""
    backend: v2ray
default_subscribe: "DEFAULT"
```

### 更改clash参数

```yaml
# clash 默认端口为 7890,你也可以改成其他值
port: 7890
#
socks-port: 7891
# 允许局域网中的其他设备使用这个代理 true/false
allow-lan: true
# Rule/Direct/Global
mode: Rule
# info / debug / 
log-level: info
# rest api 端口，默认为 9090
external-controller: :9090
```
更改后运行 `myclash service restart` 使内核与配置一致。



## 常见问题

### ssh github 走代理

一个常用的配置是 以7890端口为例
```bash
Host github.com
    User git
    Port 443
    HostName ssh.github.com
    IdentityFile ~/.ssh/id_rsa
    ProxyCommand nc -v -x 127.0.0.1:7890 %h %p
```
### 在 docker pull 时走代理

[Docker的三种网络代理配置 &middot; 零壹軒·笔记](https://note.qidong.name/2020/05/docker-proxy/)

`docker pull` 由守护进程 `dockerd` 执行，代理需写在 **dockerd 的 systemd 环境**里。一条命令按 `user_config.yaml` 里的 **HTTP 端口**（默认 7890）写入 drop-in 并 `daemon-reload` + 重启 Docker：

```bash
myclash docker-proxy update
```

- **rootful**：写入 `/etc/systemd/system/docker.service.d/`，会提示 **sudo**。
- **rootless**：写入 `~/.config/systemd/user/docker.service.d/`，使用 **`systemctl --user`**，无需 sudo。

若当前连不上 daemon、又同时装了两种 Docker，脚本可能默认系统级；可强制：`export MYCLASH_DOCKER_PROXY_TARGET=user` 或 `=system` 后再执行。可选 `MYCLASH_DOCKER_NO_PROXY` 覆盖默认的 `NO_PROXY`。

### 在 docker 容器中使用 clash

| docker的机制里不支持systemctl 所以docker 想使用 clash ，只能通过与主机共享来实现

docker依赖于宿主机上的clash,可以使用以下方法配置

```bash
# 查看宿主机 Docker 虚拟网卡地址（本例为 172.17.0.1）
ifconfig

# 进入容器，配置代理环境变量
export http_proxy="http://172.17.0.1:7890"
```

<!-- 
### Nvidia Omniverse

**Isaac Sim** 中一些 assets 可能需要访问 aws 下载，但是在使用代理时可能遇到一些资产无法下载的问题。

> 1. 添加一个规则直连aws (未测试)
> 2. 将 `shell_proxy_default` 改为 `OFF` (已测试) -->

### 自定义规则

请直接在`user_config.yaml` 的 `rules_template` 所指文件（默认 `install/templates/rules.yaml`）里，为 其他需要的域名追加规则，策略名用你合并后的组名（启用 `slim_proxy_groups` 时一般为 `Via-Proxy`）。保存后执行 `myclash service update_subcribe` 下载并合并订阅。需要可在 `myclash log`（或 `myclash service get_logs`）里看 **systemd 用户服务日志**（mcs + 内核子进程输出）核对是否走代理。
