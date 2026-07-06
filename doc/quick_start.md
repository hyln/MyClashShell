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

### Docker / K8s（无 systemd）

容器里通常没有 systemd，可使用 direct 模式安装与运行。direct 模式不会注册 `systemd --user`，而是由 `myclash service start|stop|restart` 直接管理 `scripts/runtime/mcs_manager.py`。PID 与日志默认位于 `/tmp/myclash-runtime/`，可用 `MYCLASH_RUNTIME_DIR` 覆盖。

```bash
MYCLASH_SERVICE_MODE=direct MYCLASH_ASSUME_YES=1 ./install/install.sh
source ~/.bashrc
myclash service status
myclash log
```

也可以不显式设置 `MYCLASH_SERVICE_MODE`：安装脚本会在检测不到 systemd 用户服务时自动切到 direct。`MYCLASH_ASSUME_YES=1` 用于跳过安装前的按键确认，适合 Dockerfile、CI、K8s initContainer。

如需把运行态放到其它目录（例如 K8s `emptyDir` 挂载），可设置：

```bash
export MYCLASH_RUNTIME_DIR=/tmp/myclash-runtime
```

K8s/容器入口可直接使用：

```bash
myclash service run
```

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
