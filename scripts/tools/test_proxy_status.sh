#!/bin/bash
source ${MYCLASH_ROOT_PWD}/scripts/tools/common_func.sh
export http_proxy=http://127.0.0.1:7890
export https_proxy=http://127.0.0.1:7890
echo "测试Google连接"
timeout 3 curl https://www.google.com > /dev/null 2>/dev/null
if [ $? = 0 ] 
then
    # echo_G "连接正常"
    exit 0
else
    # echo_R "连接失败"
    exit 1
fi