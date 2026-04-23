#!/bin/bash
source ${MYCLASH_ROOT_PWD}/scripts/tools/common_func.sh
myclash()
{
    case $1 in
    'service')
        if [ $2 = "start" ]; then
            sudo systemctl start myclash

        elif [ $2 = "stop" ]; then
            sudo systemctl stop myclash

        elif [ $2 = "restart" ]; then
            sudo systemctl restart myclash
        elif [ $2 = "status" ]; then
            sudo systemctl status myclash
        elif [ $2 = "get_logs" ]; then
            echo RUNNING
            curl --location 'http://127.0.0.1:9090/logs'
        elif [ $2 = "update_subcribe" ]; then
            myclash shell off
            ${MYCLASH_ROOT_PWD}/venv/bin/python3 ${MYCLASH_ROOT_PWD}/scripts/runtime/update_proxy_config.py
            myclash shell on
        else
            echo command $1 $2 not exist
        fi
        ;;
    'window')
        if [ $2 = "on" ]; then
            # Anaconda /bin 也有叫做 gsettings 的程序,所以给了绝对路径
            # 以下设置也适用于 unity 桌面
            /usr/bin/gsettings set org.gnome.system.proxy.http host 127.0.0.1
            /usr/bin/gsettings set org.gnome.system.proxy.http port 7890
            /usr/bin/gsettings set org.gnome.system.proxy.https host 127.0.0.1
            /usr/bin/gsettings set org.gnome.system.proxy.https port 7890
            /usr/bin/gsettings set org.gnome.system.proxy mode manual
            echo "start proxy in Gnome Desktop"
        elif [ $2 = "off" ]; then
            gsettings set org.gnome.system.proxy mode none
            echo "close proxy in Gnome Desktop"
        else
            echo command $1 $2 not exist
        fi
        ;;
    'shell')
        if [ $2 = "on" ]; then
            export http_proxy=http://127.0.0.1:7890
            export https_proxy=http://127.0.0.1:7890
            echo "start proxy in Terminal"
        elif [ $2 = "off" ]; then
            unset http_proxy;unset https_proxy
            echo "close proxy in Terminal"
        else
            echo command $1 $2 not exist
        fi
        ;;
    'cfg')
        ${MYCLASH_ROOT_PWD}/venv/bin/python3 ${MYCLASH_ROOT_PWD}/scripts/runtime/myclash.py $1 $2
        ;;
    'change_subscribe')
        ${MYCLASH_ROOT_PWD}/venv/bin/python3 ${MYCLASH_ROOT_PWD}/scripts/runtime/change_sub.py $2
        ;;
    'tui')
        PYTHONPATH="${MYCLASH_ROOT_PWD}" \
            ${MYCLASH_ROOT_PWD}/venv/bin/python3 -m scripts.tui ${2:+$2}
        ;;
    'share')
        case $2 in
        'serve')
            PORT="${3:-${MYCLASH_SLAVE_SERVE_PORT:-8765}}"
            PIDF="${MYCLASH_ROOT_PWD}/tmp/slave_http_server.pid"
            LOGF="${MYCLASH_ROOT_PWD}/tmp/slave_http_server.log"
            mkdir -p "${MYCLASH_ROOT_PWD}/tmp"
            if [ -f "$PIDF" ]; then
                OLD=$(cat "$PIDF")
                if kill -0 "$OLD" 2>/dev/null; then
                    echo "slave 脚本 HTTP 已在运行 (pid=$OLD)。先执行: myclash share stop"
                    return 1
                fi
                rm -f "$PIDF"
            fi
            nohup env MYCLASH_ROOT_PWD="${MYCLASH_ROOT_PWD}" \
                ${MYCLASH_ROOT_PWD}/venv/bin/python3 \
                "${MYCLASH_ROOT_PWD}/scripts/runtime/slave_http_server.py" \
                --bind "${MYCLASH_SLAVE_SERVE_BIND:-0.0.0.0}" --port "$PORT" \
                >>"$LOGF" 2>&1 &
            echo $! >"$PIDF"
            echo "slave 脚本 HTTP 已后台启动 pid=$(cat "$PIDF") 端口=$PORT"
            echo "Slave 示例: curl -fsSL http://<本机局域网IP>:${PORT}/slave_bootstrap.sh | sudo bash -s -- <本机IP> <Clash HTTP 代理端口>"
            echo "日志: $LOGF"
            ;;
        'stop')
            PIDF="${MYCLASH_ROOT_PWD}/tmp/slave_http_server.pid"
            if [ ! -f "$PIDF" ]; then
                echo "无 pid 文件，可能未启动"
                return 1
            fi
            PID=$(cat "$PIDF")
            if kill -0 "$PID" 2>/dev/null; then
                kill "$PID" && echo "已停止 pid=$PID"
            else
                echo "进程已不存在，清理 pid 文件"
            fi
            rm -f "$PIDF"
            ;;
        'status')
            PIDF="${MYCLASH_ROOT_PWD}/tmp/slave_http_server.pid"
            if [ -f "$PIDF" ] && kill -0 "$(cat "$PIDF")" 2>/dev/null; then
                echo "运行中 pid=$(cat "$PIDF")"
            else
                echo "未运行"
            fi
            ;;
        *)
            echo "用法: myclash share serve [端口] | myclash share stop | myclash share status"
            echo "默认端口 8765；可用环境变量 MYCLASH_SLAVE_SERVE_PORT / MYCLASH_SLAVE_SERVE_BIND"
            ;;
        esac
        ;;
    'help')
        echo "myclash [command*] [option*]"
        echo "Command:"
        echo "      service [ start/stop/restart/status/get_logs/update_subcribe ]"
        echo "      window [ on/off ]"
        echo "      shell [ on/off ]"
        echo "      cfg"
        echo "      tui [proxy_group(optional)]"
        echo "      share serve [端口] | share stop | share status"
        echo "          本机 HTTP 提供 slave_bootstrap.sh（局域网 curl 安装 Slave）"
        echo "======================"
        echo "Remark"
        echo "[command] service 负责管理clash服务"
        echo "[option] clash的服务设置为在安装完成后开机自启,你可以手动开启，关闭或重启服务[start/stop/restart]"
        echo "[option] update_subcribe 选项可以更新代理"
        echo "[option] get_logs 可以监看日志"
        echo "[command] window  命令管理在图形化应用(如 chrome )[on/off]代理"
        echo "[command] shell   命令管理在当前终端窗口[on/off]代理,默认值为config.yaml中的shell_proxy_default参数"
        echo "[command] cfg "
        echo "[command] tui    终端节点面板（方向键选择，回车切换）"
        ;;
    *)
        # ${MYCLASH_ROOT_PWD}/venv/bin/python3 ${MYCLASH_ROOT_PWD}/tools/gui/gui.py
        echo Myclash $(cat ${MYCLASH_ROOT_PWD}/install/version)
        # 从 user_config.yaml 读取常用项（与 TUI / 脚本约定一致）
        HTTP_PORT=7890
        _p=$("${MYCLASH_ROOT_PWD}/venv/bin/python3" "${MYCLASH_ROOT_PWD}/scripts/tools/read_yaml.py" port 2>/dev/null)
        if [[ "$_p" =~ ^[0-9]+$ ]]; then
            HTTP_PORT="$_p"
        fi
        export MYCLASH_HTTP_PORT="${HTTP_PORT}"
        _al=$("${MYCLASH_ROOT_PWD}/venv/bin/python3" "${MYCLASH_ROOT_PWD}/scripts/tools/read_yaml.py" allow-lan 2>/dev/null)
        case "$_al" in
            [Tt]rue|1|[Yy]es|[Oo]n) LAN_TXT="已开启" ;;
            [Ff]alse|0|[Nn]o|[Oo]ff) LAN_TXT="已关闭" ;;
            *) LAN_TXT="未知" ;;
        esac
        API_BASE="http://127.0.0.1:9090"
        _ec=$("${MYCLASH_ROOT_PWD}/venv/bin/python3" "${MYCLASH_ROOT_PWD}/scripts/tools/read_yaml.py" external-controller 2>/dev/null)
        if [[ -n "$_ec" ]]; then
            if [[ "$_ec" == http://* || "$_ec" == https://* ]]; then
                API_BASE="$_ec"
            elif [[ "$_ec" == :* ]]; then
                API_BASE="http://127.0.0.1${_ec}"
            elif [[ "$_ec" == 0.0.0.0:* ]]; then
                API_BASE="http://127.0.0.1:${_ec#0.0.0.0:}"
            elif [[ "$_ec" == *:* ]]; then
                API_BASE="http://${_ec}"
            fi
        fi
        echo "---- Clash Core Summary ----"
        echo "HTTP 代理端口: ${HTTP_PORT}  (socks 见 user_config 中 socks-port)"
        echo "允许局域网 (allow-lan): ${LAN_TXT}"
        bash ${MYCLASH_ROOT_PWD}/scripts/tools/test_proxy_status.sh > /dev/null
        if [ $? = 0 ] 
        then
            echo -n "当前状态："
            echo_G "连接正常"
        else
            echo -n "当前状态："
            echo_R "连接失败"
        fi
        # current_config_name=$(${MYCLASH_ROOT_PWD}/venv/bin/python3 ${MYCLASH_ROOT_PWD}/tools/read_yaml.py default_subscribe)
        current_config_name=$(cat ${MYCLASH_ROOT_PWD}/tmp/current_sub.txt)

        echo "当前使用配置: $current_config_name"
        echo "你可以通过 myclash help 查看帮助"
        echo "==================================="
        echo "终端控制面板: myclash tui"
    esac
    
}
_myclash()
{
    local cur=${COMP_WORDS[COMP_CWORD]};
    local cmd=${COMP_WORDS[COMP_CWORD-1]};

    case $cmd in
    'myclash')
        COMPREPLY=( $(compgen -W 'service window shell help cfg change_subscribe tui share' -- $cur) )
        ;;
    'share')
        COMPREPLY=( $(compgen -W 'serve stop status' -- $cur) )
        ;;
    'service')
        COMPREPLY=( $(compgen -W 'start stop restart status get_logs update_subcribe' -- $cur) ) 
        ;;
    'window')
        COMPREPLY=( $(compgen -W 'on off' -- $cur) ) 
        ;;
    'shell')
        COMPREPLY=( $(compgen -W 'on off' -- $cur) ) 
        ;;
    '*')
        ;;
    esac
}
complete -F _myclash myclash

# Auto start Proxy in Terminal
shell_proxy_default=$(${MYCLASH_ROOT_PWD}/venv/bin/python3 ${MYCLASH_ROOT_PWD}/scripts/tools/read_yaml.py shell_proxy_default)
if [ $shell_proxy_default = "ON" ]; then
    export http_proxy=http://127.0.0.1:7890
    export https_proxy=http://127.0.0.1:7890
    echo "start proxy in Terminal"
else
    unset http_proxy;unset https_proxy
    echo "close proxy in Terminal"
fi
