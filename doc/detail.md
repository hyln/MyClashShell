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
