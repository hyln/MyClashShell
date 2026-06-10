# Docker Proxy

[Docker的三种网络代理配置 &middot; 零壹軒·笔记](https://note.qidong.name/2020/05/docker-proxy/)

使用docker时3个部分需要使用代理

- Pull Image
- Build Image
- Use Container

## myclash 下的使用

### pull image

在 myclash 中集成了 `myclash docker-proxy update` 功能，可以自动设置。

### build image

使用 `docker_with_proxy`，会自动按当前 `user_config.yaml` 的 HTTP 端口和宿主机局域网 IP 注入 build proxy 参数：

```bash
docker_with_proxy . -t your/image:tag
```

也兼容保留 `build` 子命令的写法：

```bash
docker_with_proxy build . -t your/image:tag
```

等价于执行：

```bash
docker build . \
    --build-arg HTTP_PROXY=http://<host-ip>:<http-port>/ \
    --build-arg HTTPS_PROXY=http://<host-ip>:<http-port>/ \
    --build-arg NO_PROXY=localhost,127.0.0.1,::1 \
    -t your/image:tag
```

如需覆盖宿主机 IP 或 NO_PROXY：

```bash
MYCLASH_SHARE_HOST=10.42.30.34 docker_with_proxy . -t your/image:tag
MYCLASH_DOCKER_NO_PROXY=localhost,127.0.0.1,::1,.example.com docker_with_proxy . -t your/image:tag
```

### Use Container

在主机上使用 `myclash share`, 输出可直接复制到容器或 `eval`。

```bash
myclash share
```


## 原理

## pull image 走代理

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

`docker_with_proxy` 只在 build 阶段传入 `--build-arg`，通常不会作为容器运行时环境变量留在最终镜像中。

不要在 Dockerfile 中把代理写入 `ENV` 或持久配置文件，例如：

```dockerfile
ENV HTTP_PROXY=$HTTP_PROXY
RUN npm config set proxy "$HTTP_PROXY"
```

这类写法会把代理信息留在镜像层或配置文件里。

## 在 docker 容器中使用 clash

| docker的机制里不支持systemctl 所以docker 想使用 clash ，只能通过与主机共享来实现

docker依赖于宿主机上的clash,可以使用以下方法配置

```bash
# 查看宿主机 Docker 虚拟网卡地址（本例为 172.17.0.1）
ifconfig

# 进入容器，配置代理环境变量
export http_proxy="http://172.17.0.1:7890"
```
