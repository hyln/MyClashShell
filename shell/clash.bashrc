#!/bin/bash
source ${MYCLASH_ROOT_PWD}/scripts/tools/common_func.sh

# 与 user_config.yaml 中 port / socks-port 一致（缺省 7890 / 7891）
_myclash_http_port() {
    local p=7890
    local _p
    _p=$("${MYCLASH_ROOT_PWD}/venv/bin/python3" "${MYCLASH_ROOT_PWD}/scripts/tools/read_yaml.py" port 2>/dev/null)
    if [[ "$_p" =~ ^[0-9]+$ ]]; then
        p="$_p"
    fi
    echo "$p"
}

_myclash_socks_port() {
    local p=7891
    local _p
    _p=$("${MYCLASH_ROOT_PWD}/venv/bin/python3" "${MYCLASH_ROOT_PWD}/scripts/tools/read_yaml.py" socks-port 2>/dev/null)
    if [[ "$_p" =~ ^[0-9]+$ ]]; then
        p="$_p"
    fi
    echo "$p"
}

myclash()
{
    case $1 in
    'service')
        if [ $2 = "start" ]; then
            systemctl --user start myclash.service

        elif [ $2 = "stop" ]; then
            systemctl --user stop myclash.service

        elif [ $2 = "restart" ]; then
            systemctl --user restart myclash.service
        elif [ $2 = "status" ]; then
            systemctl --user status myclash.service
        elif [ $2 = "get_logs" ]; then
            # 与内核子进程（mihomo / v2ray）一致：看 systemd 用户单元日志，不再走 Clash /logs HTTP
            if ! command -v journalctl >/dev/null 2>&1; then
                echo "myclash service get_logs: 未找到 journalctl（需 systemd）" >&2
                return 1
            fi
            journalctl --user -u myclash.service -n 200 -f "${@:3}"
        elif [ $2 = "update_subcribe" ]; then
            myclash shell off
            ${MYCLASH_ROOT_PWD}/venv/bin/python3 ${MYCLASH_ROOT_PWD}/scripts/runtime/update_proxy_config.py
            myclash shell on
        elif [ $2 = "reload_kernel" ]; then
            PYTHONPATH="${MYCLASH_ROOT_PWD}" \
                "${MYCLASH_ROOT_PWD}/venv/bin/python3" -m scripts.lib.mcs_api_client
        else
            echo command $1 $2 not exist
        fi
        ;;
    'window')
        if [ $2 = "on" ]; then
            # Anaconda /bin 也有叫做 gsettings 的程序,所以给了绝对路径
            # 以下设置也适用于 unity 桌面
            _hp="$(_myclash_http_port)"
            _sp="$(_myclash_socks_port)"
            /usr/bin/gsettings set org.gnome.system.proxy.http host 127.0.0.1
            /usr/bin/gsettings set org.gnome.system.proxy.http port "$_hp"
            /usr/bin/gsettings set org.gnome.system.proxy.https host 127.0.0.1
            /usr/bin/gsettings set org.gnome.system.proxy.https port "$_hp"
            /usr/bin/gsettings set org.gnome.system.proxy.socks host 127.0.0.1
            /usr/bin/gsettings set org.gnome.system.proxy.socks port "$_sp"
            /usr/bin/gsettings set org.gnome.system.proxy.ftp host 127.0.0.1
            /usr/bin/gsettings set org.gnome.system.proxy.ftp port "$_hp"
            /usr/bin/gsettings set org.gnome.system.proxy mode manual
            echo "start proxy in Gnome Desktop"
        elif [ $2 = "off" ]; then
            /usr/bin/gsettings set org.gnome.system.proxy mode none
            echo "close proxy in Gnome Desktop"
        else
            echo command $1 $2 not exist
        fi
        ;;
    'shell')
        if [ $2 = "on" ]; then
            _hp="$(_myclash_http_port)"
            export http_proxy=http://127.0.0.1:${_hp}
            export https_proxy=http://127.0.0.1:${_hp}
            export ftp_proxy=http://127.0.0.1:${_hp}
            export all_proxy=
            export no_proxy=127.0.0.1,localhost

            echo "start proxy in Terminal"
        elif [ $2 = "off" ]; then
            unset http_proxy;unset https_proxy;
            unset ftp_proxy;unset all_proxy;unset no_proxy;
            echo "close proxy in Terminal"
        else
            echo command $1 $2 not exist
        fi
        ;;
    'log')
        if ! command -v journalctl >/dev/null 2>&1; then
            echo "myclash log: 未找到 journalctl（需 systemd）" >&2
            return 1
        fi
        journalctl --user -u myclash.service -n 200 -f "${@:2}"
        ;;
    'cfg')
        ${MYCLASH_ROOT_PWD}/venv/bin/python3 ${MYCLASH_ROOT_PWD}/scripts/runtime/myclash.py $1 $2
        ;;
    'change_subscribe')
        ${MYCLASH_ROOT_PWD}/venv/bin/python3 ${MYCLASH_ROOT_PWD}/scripts/runtime/change_sub.py $2
        ;;
    'ui')
        # 按 default_subscribe 的 backend（优先 mcs GET /kernel/status）自动打开 Clash TUI 或 v2ray TUI
        _be=$(PYTHONPATH="${MYCLASH_ROOT_PWD}" "${MYCLASH_ROOT_PWD}/venv/bin/python3" \
            "${MYCLASH_ROOT_PWD}/scripts/tools/myclash_ui_backend.py" 2>/dev/null | tr -d '\r\n')
        _be="${_be:-clash}"
        case "${_be}" in
        v2ray)
            PYTHONPATH="${MYCLASH_ROOT_PWD}" \
                "${MYCLASH_ROOT_PWD}/venv/bin/python3" -m scripts.tui_v2ray
            ;;
        *)
            PYTHONPATH="${MYCLASH_ROOT_PWD}" \
                "${MYCLASH_ROOT_PWD}/venv/bin/python3" -m scripts.tui ${2:+$2}
            ;;
        esac
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
    'docker-proxy')
        case $2 in
        'update')
            bash "${MYCLASH_ROOT_PWD}/scripts/tools/myclash_docker_proxy_update.sh"
            ;;
        *)
            echo "用法: myclash docker-proxy update"
            echo "  按 user_config 的 HTTP 端口写入 dockerd 的 systemd drop-in，并 reload + restart。"
            echo "  自动识别 rootless（用户单元）与 rootful（需 sudo）。"
            echo "  强制目标: MYCLASH_DOCKER_PROXY_TARGET=user|system"
            ;;
        esac
        ;;
    'v2ray')
        case $2 in
        'ui')
            PYTHONPATH="${MYCLASH_ROOT_PWD}" \
                "${MYCLASH_ROOT_PWD}/venv/bin/python3" -m scripts.tui_v2ray "${@:3}"
            ;;
        'log')
            if ! command -v journalctl >/dev/null 2>&1; then
                echo "myclash v2ray log: 未找到 journalctl（需 systemd）" >&2
                return 1
            fi
            # v2ray 子进程与 mcs_manager 的 stdout/stderr 由 systemd --user 写入 journal
            journalctl --user -u myclash.service -n 200 -f "${@:4}"
            ;;
        *)
            echo "用法:"
            echo "  myclash v2ray ui   — 节点选择与测速（Textual）"
            echo "  myclash v2ray log  — 同 myclash log / service get_logs（journalctl myclash.service）"
            echo "  追加参数会原样传给 journalctl，例如: myclash v2ray log --since today"
            ;;
        esac
        ;;
    'help')
        echo "myclash [command*] [option*]"
        echo "Command:"
        echo "      log [journalctl参数…]  — 跟踪 myclash.service（mcs + mihomo/v2ray 子进程）"
        echo "      service [ start/stop/restart/status/get_logs/update_subcribe/reload_kernel ]"
        echo "      window [ on/off ]"
        echo "      shell [ on/off ]"
        echo "      cfg"
        echo "      ui [proxy_group(optional)]  — 按后端自动打开 Clash TUI 或 v2ray 选节点界面"
        echo "      tui [proxy_group(optional)]  — 仅 Clash（mihomo）TUI，与 ui 在 clash 后端时等价"
        echo "      v2ray ui | v2ray log  — v2ray 选节点；log 与 service get_logs 相同（journalctl）"
        echo "      share serve [端口] | share stop | share status"
        echo "          本机 HTTP 提供 slave_bootstrap.sh（局域网 curl 安装 Slave）"
        echo "      docker-proxy update  — docker pull 走本机 Clash HTTP 代理（systemd drop-in）"
        echo "======================"
        echo "Remark"
        echo "[command] service 负责管理 MCS 内核（systemd --user，无需 sudo）"
        echo "[option] 安装后对用户会话 enable，可手动 start/stop/restart；无登录会话的机器见 loginctl enable-linger"
        echo "[option] update_subcribe 选项可以更新代理"
        echo "[option] reload_kernel 通知 mcs_manager 重拉 Clash/v2ray 子进程（端口见 cache/current_mcs_port.txt；池为 mcs_api_start_port–mcs_api_end_port）"
        echo "[option] get_logs / myclash log  — journalctl 用户服务日志（含 mihomo/v2ray 标准输出）"
        echo "[command] window  命令管理在图形化应用(如 chrome )[on/off]代理"
        echo "[command] shell   命令管理在当前终端窗口[on/off]代理,默认值为config.yaml中的shell_proxy_default参数"
        echo "[command] cfg "
        echo "[command] ui     终端节点面板（clash / v2ray 自动切换）"
        echo "[command] tui    同 ui 之 Clash 专用入口"
        ;;
    *)
        # ${MYCLASH_ROOT_PWD}/venv/bin/python3 ${MYCLASH_ROOT_PWD}/tools/gui/gui.py
        echo Myclash $(cat ${MYCLASH_ROOT_PWD}/install/version)
        # 从 user_config.yaml 读取常用项（与 TUI / 脚本约定一致）
        HTTP_PORT="$(_myclash_http_port)"
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
        echo "---- Summary ----"
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
        current_config_name=$(cat ${MYCLASH_ROOT_PWD}/cache/current_sub.txt)

        echo "当前使用配置: $current_config_name"
        echo "你可以通过 myclash help 查看帮助"
        echo "==================================="
        echo "终端控制面板: myclash ui（或 myclash tui）"
    esac
    
}
_myclash()
{
    local cur=${COMP_WORDS[COMP_CWORD]};
    local cmd=${COMP_WORDS[COMP_CWORD-1]};

    case $cmd in
    'myclash')
        COMPREPLY=( $(compgen -W 'service window shell log help cfg change_subscribe ui tui share docker-proxy v2ray' -- $cur) )
        ;;
    'v2ray')
        COMPREPLY=( $(compgen -W 'ui log' -- $cur) )
        ;;
    'share')
        COMPREPLY=( $(compgen -W 'serve stop status' -- $cur) )
        ;;
    'docker-proxy')
        COMPREPLY=( $(compgen -W 'update' -- $cur) )
        ;;
    'service')
        COMPREPLY=( $(compgen -W 'start stop restart status get_logs update_subcribe reload_kernel' -- $cur) ) 
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
    _hp="$(_myclash_http_port)"
    export http_proxy=http://127.0.0.1:${_hp}
    export https_proxy=http://127.0.0.1:${_hp}
    echo "start proxy in Terminal (http ${_hp})"
else
    unset http_proxy;unset https_proxy
    echo "close proxy in Terminal"
fi
