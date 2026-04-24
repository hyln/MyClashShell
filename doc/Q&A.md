# Q&A

## 安装问题
```
(base) se@se-ThinkPad-T14p-Gen-3:~/MyClashShell/install$ systemctl --user daemon-reload Failed to connect to bus: Connection refused
```
重启一下好了


## ssh github 走代理

一个常用的配置是 以7890端口为例
```bash
Host github.com
    User git
    Port 443
    HostName ssh.github.com
    IdentityFile ~/.ssh/id_rsa
    ProxyCommand nc -v -x 127.0.0.1:7890 %h %p
```