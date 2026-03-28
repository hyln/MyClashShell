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

> 首次使用更新完代理后需要使用 `sudo systemctl restart myclash`（或 `myclash service restart`）

## 快速开始

### 设置订阅
修改 MyClashShell 目录下生成的 user_config.yaml
```yaml
shell_proxy_default: 'ON'  #  ON / OFF
subscribes:
    <your_proxy_name>: "<you_proxy_url>"
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
