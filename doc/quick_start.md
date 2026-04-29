# MyClashShell Quickstart

myclashshell 仅提供对Ubuntu平台的支持

- [x] amd64
- [x] armv8  (aarch64)
- [x] armv7a

支持后端 

- v2ray
- mihomo

## 快速开始

### 准备
```bash
git clone https://github.com/hyaline-wang/MyClashShell.git
cd MyClashShell
# 1) 系统级准备（需 root）：apt 依赖、sudoers 代理保留、清理旧版系统 systemd 与 /etc/bash.bashrc 片段
sudo ./install/install_root.sh
sudo loginctl enable-linger $(whoami)

```


### 安装

```bash
# 2) 用户级安装：venv、下载内核、systemd --user、写入当前用户的 ~/.bashrc（推荐不用 sudo；root 执行时脚本会提示预期路径）
./install/install.sh
##########
source ~/.bashrc
```

安装完成后
1. 使用 `myclash` 命令查看软件信息
3. 通过`myclash help` 查看帮助

> 你需要知道mcs仅仅是小工具，你需要填写正确的代理链接才能正常使用。
> 
> 填写完成后请输入 `myclash service update_subscribe` 下载并载入订阅。
<!-- > 设置完代理后执行 `myclash service restart`（systemd **用户**服务，无需 sudo） -->

## 卸载

**卸载**：普通用户 `./install/uninstall.sh`（用户 systemd、`~/.bashrc`、本仓库下 `mcs/`）；若曾装过旧版系统服务，再执行 **`sudo ./install/uninstall_root.sh`**。最后可手动删除整个仓库目录。

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
 - 每条订阅须为 **`url` + `backend`**（`clash` 或 `v2ray`）
 - `<your_proxy_name>` 与 `<you_proxy_url>` 分别为订阅显示名与订阅链接；修改后运行
    ```bash
      # 更新订阅
      myclash service update_subscribe 
    ```
 <!-- - Clash 订阅原始 YAML 在 **`cache/subscribe/`**；**`cache/current_sub.txt`**、**`cache/env_prefix.txt`**（写入 ~/.bashrc 的片段）；内核与地理库在 **`cache/download/`**；安装生成的 systemd 单元草稿等在 **`cache/`**。
 - **default_subscribe**：当前默认使用的订阅名，可填 `subscribes` 下任意键；**`DEFAULT`** 表示使用 YAML 中**第一个**订阅。`mcs_manager` 会根据该订阅的 **`backend`** 决定拉起 **Clash** 还是 **v2ray**；切换默认订阅后执行 **`myclash service restart`** 使内核与配置一致。 -->


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
# rest api 仅本机监听（示例）
external-controller: 127.0.0.1:9090
```
更改后运行 `myclash service restart` 使内核与配置一致。

### clash自定义规则

为了简化使用，对于clash订阅，无论下载的定义文件有多少个 proxy-group，均合并成仅有一种，即`A-Via-Proxy`


请直接在`user_config.yaml` 的 `rules_template` 所指文件（默认 `install/templates/rules.yaml`）里，为 其他需要的域名追加规则。你可以选择 `A-Via-Proxy` 或者 `DIRECT`。


保存后，当执行 `myclash service update_subscribe` 或 
 `myclash change_subscribe`
时会自动更新

可在 `myclash log`（或 `myclash service get_logs`）里看 **systemd 用户服务日志** 核对是否正确走代理。

### v2ray 与国内分流

`install-cache` 会按 `install/download.yaml` 下载 `geoip.dat`、`geosite.dat`，`install.sh` 将其复制到 `mcs/configs/`。更新订阅并重写配置后，`v2ray` 路由会对私有网段与国内域名/IP 走直连，其余再走节点。若要暂时关闭分流（全部走代理），在 `user_config.yaml` 中设置 `v2ray_geo_split: false`。
