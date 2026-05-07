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

_myclash_share_host() {
    if [ -n "${MYCLASH_SHARE_HOST:-}" ]; then
        echo "${MYCLASH_SHARE_HOST}"
        return 0
    fi
    local ip=""
    ip=$(hostname -I 2>/dev/null | awk '{print $1}')
    if [[ "$ip" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
        echo "$ip"
        return 0
    fi
    echo "127.0.0.1"
}

_myclash_fmt_dim() { printf '\033[2m%s\033[0m' "$1"; }
_myclash_fmt_bold() { printf '\033[1m%s\033[0m' "$1"; }

# $1…$6: version, 当前订阅名, HTTP 口, SOCKS 口, allow-lan 文案, 连通性(0=正常 非0=异常)
_myclash_print_status() {
    local _ver="$1" _sub="$2" _http="$3" _socks="$4" _lan="$5" _px="$6"
    local _edge="  ╭──────────────────────────────────────────────────╮"
    local _mid="  ├──────────────────────────────────────────────────┤"
    local _bot="  ╰──────────────────────────────────────────────────╯"
    echo ""
    echo "$_edge"
    printf "  │ %b  %b\n" "$(_myclash_fmt_bold "MyClash")" "$(_myclash_fmt_dim "${_ver}")"
    echo "$_mid"
    printf "  │ %b  %s\n" "$(_myclash_fmt_dim "当前订阅")    " "${_sub}"
    printf "  │ %b  %s\n" "$(_myclash_fmt_dim "HTTP 端口")    " "${_http}"
    printf "  │ %b  %s\n" "$(_myclash_fmt_dim "SOCKS 端口")   " "${_socks}"
    printf "  │ %b  %s\n" "$(_myclash_fmt_dim "允许局域网")    " "${_lan}"
    printf '  │ %b  ' "$(_myclash_fmt_dim "连通性")"
    if [ "${_px}" = 0 ]; then
        printf "%b\n" "$colors_On_Green 正常 $colors_Normal"
    else
        printf "%b\n" "$colors_On_Red 异常 $colors_Normal"
    fi
    echo "$_bot"
    echo ""
    printf "  %b  myclash help   %b\n" "$(_myclash_fmt_dim "→")" "$(_myclash_fmt_dim "命令列表（与 --help 相同）")"
    printf "  %b  myclash ui    %b\n" "$(_myclash_fmt_dim "→")" "$(_myclash_fmt_dim "终端节点面板")"
    echo ""
}

_myclash_print_help() {
    cat <<'EOF'
  ╭──────────────────────────────────────────────────╮
  │ MyClash · 命令参考                                │
  ╰──────────────────────────────────────────────────╯

  myclash <命令> [参数 …]

  服务与日志
    service <子命令>  start | stop | restart | status | get_logs
                      | update_subscribe | reload_kernel
    log [journalctl…] 跟踪 myclash.service（mcs + 内核）

  节点界面
    ui                   clash → mihomo TUI；v2ray → 选节点（视默认订阅）
    v2ray ui | v2ray log 选节点 / 同 get_logs（journalctl）

  代理
    shell on|off         当前 shell（默认见 user_config.shell_proxy_default）
    window on|off        GNOME 等：系统 HTTP/SOCKS

  其它
    change_subscribe <名>
    share [env|export]   输出可 eval 的 export（局域网 Master IP；默认 hostname -I 首个 IPv4）
    docker-proxy update

  提示
    · update_subscribe / change_subscribe：会先 shell off，避免经代理拉配置失败；结束后再 shell on
    · reload_kernel：只重启 clash/v2ray 子进程
    · API 端口见 cache/current_mcs_port.txt；池见 user_config.mcs_api_port_range
    · get_logs / log：journalctl --user；无登录会话：loginctl enable-linger <用户>
    · 无子命令或非常规参数：打印运行状态摘要；等价于单独执行 myclash（无参数）
EOF
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
        elif [ $2 = "update_subscribe" ]; then
            myclash shell off
            ${MYCLASH_ROOT_PWD}/venv/bin/python3 ${MYCLASH_ROOT_PWD}/scripts/runtime/update_proxy_config.py "${@:3}"
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
            _sp="$(_myclash_socks_port)"
            export http_proxy=http://127.0.0.1:${_hp}
            export https_proxy=http://127.0.0.1:${_hp}
            export ftp_proxy=http://127.0.0.1:${_hp}
            export all_proxy=socks5h://127.0.0.1:${_sp}
            export no_proxy=127.0.0.1,localhost
            export HTTP_PROXY=http://127.0.0.1:${_hp}
            export HTTPS_PROXY=http://127.0.0.1:${_hp}
            export FTP_PROXY=http://127.0.0.1:${_hp}
            export ALL_PROXY=socks5h://127.0.0.1:${_sp}
            export NO_PROXY=127.0.0.1,localhost

            echo "start proxy in Terminal"
        elif [ $2 = "off" ]; then
            unset http_proxy;
            unset https_proxy;
            unset ftp_proxy;
            unset all_proxy;
            unset no_proxy;
            unset HTTP_PROXY;
            unset HTTPS_PROXY;
            unset FTP_PROXY;
            unset ALL_PROXY;
            unset NO_PROXY;
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
    'change_subscribe')
        local _cs_rc=0
        myclash shell off
        ${MYCLASH_ROOT_PWD}/venv/bin/python3 ${MYCLASH_ROOT_PWD}/scripts/runtime/change_sub.py "${@:2}" || _cs_rc=$?
        myclash shell on
        return "${_cs_rc}"
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
        ''|'env'|'export')
            _hp="$(_myclash_http_port)"
            _sp="$(_myclash_socks_port)"
            _host="$(_myclash_share_host)"
            echo "export http_proxy=http://${_host}:${_hp}"
            echo "export https_proxy=http://${_host}:${_hp}"
            echo "export ftp_proxy=http://${_host}:${_hp}"
            echo "export all_proxy=socks5h://${_host}:${_sp}"
            echo "export no_proxy=127.0.0.1,localhost"
            echo "export HTTP_PROXY=http://${_host}:${_hp}"
            echo "export HTTPS_PROXY=http://${_host}:${_hp}"
            echo "export FTP_PROXY=http://${_host}:${_hp}"
            echo "export ALL_PROXY=socks5h://${_host}:${_sp}"
            echo "export NO_PROXY=127.0.0.1,localhost"
            ;;
        *)
            echo "用法: myclash share [env|export]"
            echo "不带参数或与 env/export：输出可 eval 的 export（MYCLASH_SHARE_HOST 可覆盖主机 IP）"
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
    'help'|'--help'|'-h')
        _myclash_print_help
        ;;
    *)
        HTTP_PORT="$(_myclash_http_port)"
        export MYCLASH_HTTP_PORT="${HTTP_PORT}"
        SOCKS_PORT="$(_myclash_socks_port)"
        _al=$("${MYCLASH_ROOT_PWD}/venv/bin/python3" "${MYCLASH_ROOT_PWD}/scripts/tools/read_yaml.py" allow-lan 2>/dev/null)
        case "$_al" in
            [Tt]rue|1|[Yy]es|[Oo]n) LAN_TXT="已开启" ;;
            [Ff]alse|0|[Nn]o|[Oo]ff) LAN_TXT="已关闭" ;;
            *) LAN_TXT="未知" ;;
        esac
        _ver=$(cat "${MYCLASH_ROOT_PWD}/install/version" 2>/dev/null || echo "?")
        current_config_name=$(cat "${MYCLASH_ROOT_PWD}/cache/current_sub.txt" 2>/dev/null || cat "${MYCLASH_ROOT_PWD}/cache/subscribe/current_sub.txt" 2>/dev/null || echo "—")

        bash "${MYCLASH_ROOT_PWD}/scripts/tools/test_proxy_status.sh" >/dev/null 2>&1
        _proxy_ok=$?

        _myclash_print_status "${_ver}" "${current_config_name}" "${HTTP_PORT}" "${SOCKS_PORT}" "${LAN_TXT}" "${_proxy_ok}"
    esac
    
}
_myclash()
{
    local cur=${COMP_WORDS[COMP_CWORD]};
    local cmd=${COMP_WORDS[COMP_CWORD-1]};

    case $cmd in
    'myclash')
        COMPREPLY=( $(compgen -W 'service window shell log help change_subscribe ui share docker-proxy v2ray' -- $cur) )
        ;;
    'v2ray')
        COMPREPLY=( $(compgen -W 'ui log' -- $cur) )
        ;;
    'share')
        COMPREPLY=( $(compgen -W 'env export' -- $cur) )
        ;;
    'docker-proxy')
        COMPREPLY=( $(compgen -W 'update' -- $cur) )
        ;;
    'service')
        COMPREPLY=( $(compgen -W 'start stop restart status get_logs update_subscribe reload_kernel' -- $cur) ) 
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
