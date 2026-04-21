# MyClashShell Quickstart

myclashshell 仅提供对Ubuntu平台的支持

- [x] amd64
- [x] armv8  (aarch64)
- [x] armv7a
## 安装

```bash
git clone https://github.com/hyaline-wang/MyClashShell.git
cd MyClashShell
sudo ./ubuntu/install.sh
# sudo ./ubuntu/install.sh --use-cache # 如果已经安装过一遍了，正在重新装，可以不重复下载
########## 
source /etc/bash.bashrc ;source ~/.bashrc
```
安装完成后
1. 使用 `myclash` 命令查看软件信息
3. 通过`myclash help` 查看帮助

> 首次使用更新完代理后需要使用 systemctl restart clash

## 快速开始

### 设置订阅
修改 MyClashShell 目录下生成的 user_config.yaml
```yaml
shell_proxy_default: 'ON'  #  ON / OFF
subscribes:
    <your_proxy_name>: "<you_proxy_url>"
# 若某订阅需 Mihomo（如 AnyTLS），见下文「Mihomo 与原版 Clash 并存」
# mihomo_subscribes:
#   - <your_proxy_name>
default_subscribe: "DEFAULT"
```
 - shell_proxy_default: 选择是否自动在命令行开启代理，保存即生效
 - <your_proxy_name>和<you_proxy_url>分别指 自己为这个代理设定的名字 以及 订阅链接，修改后运行
    ```bash
      # 更新订阅
      myclash service update_subcribe 
    ```
 - default_subscribe： 这是默认使用的代理，你可以填subscribe_urls中的任意名字,DEFAULT 是指使用 subscribe_urls 中的第一个

## 配置

### 设置多个订阅

针对有多个代理的情况,MyClashShell允许同时添加多个代理
```yaml
shell_proxy_default: 'ON'  ##  ON  / OFF
subscribes:
    <your_proxy_name_1>: "<you_proxy_url_1>"
    <your_proxy_name_2>: "<you_proxy_url_2>"
    <your_proxy_name_3>: "<you_proxy_url_3>"
default_subscribe: "DEFAULT"
```

### Mihomo 与原版 Clash 并存（AnyTLS 等）

部分机场节点使用 **AnyTLS** 等仅 **Clash Meta（Mihomo）** 支持的协议。本仓库在安装时会同时放置：

| 文件 | 说明 |
|------|------|
| `clash/clash` | 原有内核，兼容常见 Clash 订阅 |
| `clash/mihomo` | Meta 内核，用于 AnyTLS 等 |
| `clash/launch-core.sh` | 根据当前订阅名选择上述之一启动 |

在 `user_config.yaml` 中，用 **`mihomo_subscribes`** 列出要走 Mihomo 的订阅**键名**（必须与 `subscribes` 下的 key 一致）；**未**出现在列表中的订阅仍使用原版 `clash`。

```yaml
subscribes:
  sub: "https://example.com/subscribe/xxx/clash/"
  other: "https://converter.example/sub?target=clash&url=..."
# 与 subscribes 的键名一致；仅这些订阅用 Mihomo
mihomo_subscribes:
  - sub
# 可选。对「带 subconverter、且 URL 中含 target=clash」的链接，自动改为 target=clash.meta 并使用 flag=clash.meta；若转换器不兼容可设为 false
mihomo_clash_meta_convert: true
default_subscribe: "sub"
```

说明：

- 执行 **`myclash service update_subcribe`** 或 **`myclash change_subscribe <名>`** 后，会写入 `tmp/current_core.txt` 并 **重启 `clash` 服务**，以切换到对应内核。
- 无参执行 **`myclash`** 时，会显示当前订阅名与当前内核（`clash` / `mihomo`）。
- 若机器上仍是旧安装、缺少 `mihomo` 或 `launch-core.sh`，可在仓库根目录执行（将路径换成你的安装根目录，通常即克隆目录）：
  ```bash
  sudo MYCLASH_ROOT_PWD=/path/to/MyClashShell bash ubuntu/apply_mihomo_sidecar.sh
  ```
- 机场若提供 **直连 Clash 订阅** 且内容已是 Meta 格式（含 `type: anytls` 等），可不套 subconverter；否则按机场说明使用转换链接，并视情况开启 `mihomo_clash_meta_convert`。

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
更改后运行 `myclash cfg update`完成更改

### 添加自定义规则

我们一般不会手动新增节点，代理组变化的可能性也非常小，但是可能需要自定义部分**规则**



更改后运行 `myclash cfg update`完成更改


## 常见问题
### ssh github 走代理

一个常用的配置是
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

在执行`docker pull`时，是由守护进程`dockerd`来执行。 因此，代理需要配在`dockerd`的环境中。 而这个环境，则是受`systemd`所管控，因此实际是`systemd`的配置。

```bash
sudo mkdir -p /etc/systemd/system/docker.service.d
sudo vim /etc/systemd/system/docker.service.d/proxy.conf
```

在这个`proxy.conf`文件（可以是任意`*.conf`的形式）中，添加以下内容：

```
[Service]
Environment="HTTP_PROXY=http://127.0.0.1:7890/"
Environment="HTTPS_PROXY=http://127.0.0.1:7890/"
```

```bash
# 最后重启 Docker 服务
systemctl daemon-reload
systemctl restart docker
```

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

### chatgpt

1. 添加一下字段 其中 `<your_sub_name>` 是你设置的订阅名,`<proxy-group>` 一个能正常访问google的代理组

    ```yaml
    custom-rule-<your_sub_name>:
    use_node: "<proxy-group>"
    domain:
      - DOMAIN-SUFFIX,openai.com,GPT
      - DOMAIN-SUFFIX,auth0.com,GPT
      - DOMAIN-SUFFIX,bing.com,GPT
      - DOMAIN-SUFFIX,live.com,GPT
    ```
2. 使用 `myclash config update` 完成更新 
3. 现在应该可以正常使用 chatgpt 了，你也可在尝试时通过 `myclash service get-logs` 监控openai的网站是否使用了设置的规则
