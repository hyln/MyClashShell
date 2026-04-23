#!/bin/bash
source ${MYCLASH_ROOT_PWD}/scripts/tools/common_func.sh
# 端口由调用方传入（与 user_config.yaml 中 port 一致）；默认 7890
_HTTP_PORT="${MYCLASH_HTTP_PORT:-7890}"
export http_proxy="http://127.0.0.1:${_HTTP_PORT}"
export https_proxy="http://127.0.0.1:${_HTTP_PORT}"
# 与 scripts/tui/state.py 中 MYCLASH_TUI_TEST_URL 默认一致，便于「myclash」与 TUI 测速同源
TEST_URL="${MYCLASH_TUI_TEST_URL:-https://www.gstatic.com/generate_204}"
echo "测试连接 (${TEST_URL})"
curl -fsSL --max-time 4 "${TEST_URL}" > /dev/null 2>/dev/null
if [ $? = 0 ] 
then
    # echo_G "连接正常"
    exit 0
else
    # echo_R "连接失败"
    exit 1
fi