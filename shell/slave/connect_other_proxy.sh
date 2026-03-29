#!/bin/bash
if [ $# -eq 0 ]
then
    echo "请输入要连接设备的ip"
    echo "使用示例:./connect_other_proxy.sh 10.42.0.1 7890"
    echo "default port:7890"
    echo "使用示例:./connect_other_proxy.sh 10.42.0.1"
elif [ $# -eq 1 ]
then
    echo "设定ip:$1"
    echo "使用默认端口:7890"
    export http_proxy=http://$1:7890;export https_proxy=http://$1:7890 

elif [ $# -eq 2 ]
then
    echo "设定ip:$1"
    echo "设定端口:$2"
fi

