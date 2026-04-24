# Docker Proxy

[Docker的三种网络代理配置 &middot; 零壹軒·笔记](https://note.qidong.name/2020/05/docker-proxy/)

使用docker时3个部分需要使用代理

- pull image时
- build 时
- 使用时

## pull image 走代理

> 在 myclash 中集成了 `myclash docker-proxy update` 功能，可以自动设置。

`docker pull` 由守护进程 `dockerd` 执行，代理需写在 **dockerd 的 systemd 环境**里。一条命令按 `user_config.yaml` 里的 **HTTP 端口**（默认 7890）写入 drop-in 并 `daemon-reload` + 重启 Docker:

```bash
sudo mkdir -p /etc/systemd/system/docker.service.d
sudo touch /etc/systemd/system/docker.service.d/proxy.conf
```
在这个proxy.conf文件（可以是任意*.conf的形式）中，添加以下内容：

```bash
[Service]
Environment="HTTP_PROXY=http://proxy.example.com:8080/"
Environment="HTTPS_PROXY=http://proxy.example.com:8080/"
Environment="NO_PROXY=localhost,127.0.0.1,.example.com"
```

## Dockerfile build


TODO

## 在 docker 容器中使用 clash

| docker的机制里不支持systemctl 所以docker 想使用 clash ，只能通过与主机共享来实现

docker依赖于宿主机上的clash,可以使用以下方法配置

```bash
# 查看宿主机 Docker 虚拟网卡地址（本例为 172.17.0.1）
ifconfig

# 进入容器，配置代理环境变量
export http_proxy="http://172.17.0.1:7890"
```