# 导入 requests 包
import requests


base_url = "http://127.0.0.1:9090"
get_dict = {
    "logs": "/logs",
    "traffic": "/traffic", # kpbs
    "memory" : "/memory", # kb error
    "version" : "/version",
    "configs" : "/configs",
    "proxies" : "/proxies",
}
put_dict = {

}
patch_dict = {

}
post_dict = {
    "restart":"/restart",

}


# 发送请求
x = requests.get(base_url+get_dict["traffic"])

# 返回网页内容
print(x.text)
# https://wiki.metacubex.one/api/#configs