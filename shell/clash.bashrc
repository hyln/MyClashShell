#!/bin/bash
source ${MYCLASH_ROOT_PWD}/mcs_py/tools/common_func.sh

# 固定在仓库根执行 Python，避免其他工程 cwd 下的同名包抢先导入
_myclash_python() {
    local _py="${MYCLASH_ROOT_PWD}/venv/bin/python3"
    (
        cd "${MYCLASH_ROOT_PWD}" || exit 1
        PYTHONPATH="${MYCLASH_ROOT_PWD}" "$_py" "$@"
    )
}

# 与 user_config.yaml 中 port / socks-port 一致（缺省 7890 / 7891）
_myclash_read_config() {
    _myclash_python mcs_py/tools/read_config_value.py "$@" 2>/dev/null
}

_myclash_http_port() {
    local p=7890
    local _p
    _p=$(_myclash_read_config port)
    if [[ "$_p" =~ ^[0-9]+$ ]]; then
        p="$_p"
    fi
    echo "$p"
}

_myclash_socks_port() {
    local p=7891
    local _p
    _p=$(_myclash_read_config socks-port)
    if [[ "$_p" =~ ^[0-9]+$ ]]; then
        p="$_p"
    fi
    echo "$p"
}

_myclash_lan_host() {
    if [ -n "${MYCLASH_SHARE_HOST:-}" ]; then
        echo "${MYCLASH_SHARE_HOST}"
        return 0
    fi
    local ip=""
    ip=$(hostname -I 2>/dev/null | awk '{for (i=1; i<=NF; i++) { if ($i !~ /^127\./) { print $i; exit } }}')
    if [[ "$ip" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
        echo "$ip"
        return 0
    fi
    echo "127.0.0.1"
}

_myclash_run_cli() {
    _myclash_python mcs_py/myclash_cli.py "$@"
}

_myclash_with_shell_off() {
    myclash shell off
    _myclash_run_cli "$@"
    _rc=$?
    myclash shell on
    return "${_rc}"
}

myclash()
{
    case $1 in
    'service')
        if [ "$2" = "update_subscribe" ]; then
            _use=$(_myclash_read_config update_sub_use_proxy)
            if [ "$_use" = "true" ]; then
                _myclash_run_cli "$@"
            else
                _myclash_with_shell_off "$@"
            fi
            return "$?"
        fi
        _myclash_run_cli "$@"
        ;;
    'window')
        if [ "${2:-}" = "on" ]; then
            # Anaconda /bin 也有叫做 gsettings 的程序,所以给了绝对路径
            # 以下设置也适用于 unity 桌面
            _hp="$(_myclash_http_port)"
            _sp="$(_myclash_socks_port)"
            /usr/bin/gsettings set org.gnome.system.proxy.http host 127.0.0.1
            /usr/bin/gsettings set org.gnome.system.proxy.http port "$_hp"
            /usr/bin/gsettings set org.gnome.system.proxy.https host 127.0.0.1
            /usr/bin/gsettings set org.gnome.system.proxy.https port "$_hp"
            # /usr/bin/gsettings set org.gnome.system.proxy.socks host 127.0.0.1
            # /usr/bin/gsettings set org.gnome.system.proxy.socks port "$_sp"
            # /usr/bin/gsettings set org.gnome.system.proxy.ftp host 127.0.0.1
            # /usr/bin/gsettings set org.gnome.system.proxy.ftp port "$_hp"
            /usr/bin/gsettings set org.gnome.system.proxy mode manual
            echo "start proxy in Gnome Desktop"
        elif [ "${2:-}" = "off" ]; then
            /usr/bin/gsettings set org.gnome.system.proxy mode none
            echo "close proxy in Gnome Desktop"
        else
            echo command $1 $2 not exist
        fi
        ;;
    'shell')
        if [ "${2:-}" = "on" ]; then
            _hp="$(_myclash_http_port)"
            _sp="$(_myclash_socks_port)"
            export http_proxy=http://127.0.0.1:${_hp}
            export https_proxy=http://127.0.0.1:${_hp}
            export ftp_proxy=http://127.0.0.1:${_hp}
            # export all_proxy=socks5h://127.0.0.1:${_sp}
            export no_proxy=127.0.0.1,localhost
            export HTTP_PROXY=http://127.0.0.1:${_hp}
            export HTTPS_PROXY=http://127.0.0.1:${_hp}
            export FTP_PROXY=http://127.0.0.1:${_hp}
            # export ALL_PROXY=socks5h://127.0.0.1:${_sp}
            export NO_PROXY=127.0.0.1,localhost

            echo "start proxy in Terminal"
        elif [ "${2:-}" = "off" ]; then
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
        _myclash_run_cli "$@"
        ;;
    'change_subscribe')
        _myclash_with_shell_off "$@"
        return "$?"
        ;;
    'ui')
        # 按 default_subscribe 的 backend（优先 mcs GET /kernel/status）自动打开 Clash TUI 或 v2ray TUI
        _be=$(_myclash_python mcs_py/tools/myclash_ui_backend.py 2>/dev/null | tr -d '\r\n')
        _be="${_be:-clash}"
        case "${_be}" in
        v2ray)
            _myclash_python -m mcs_py.tui_v2ray
            ;;
        *)
            _myclash_python -m mcs_py.tui ${2:+$2}
            ;;
        esac
        ;;
    'share')
        _myclash_run_cli "$@"
        ;;
    'docker-proxy')
        _myclash_run_cli "$@"
        ;;
    'config')
        _myclash_run_cli "$@"
        ;;
    'help'|'--help'|'-h')
        _myclash_run_cli help
        ;;
    *)
        _myclash_run_cli
    esac
    
}
_myclash()
{
    local cur=${COMP_WORDS[COMP_CWORD]};
    local cmd=${COMP_WORDS[COMP_CWORD-1]};

    case $cmd in
    'myclash')
        COMPREPLY=( $(compgen -W 'service window shell log help change_subscribe ui share docker-proxy config' -- $cur) )
        ;;
    'docker-proxy')
        COMPREPLY=( $(compgen -W 'update' -- $cur) )
        ;;
    'config')
        COMPREPLY=( $(compgen -W 'edit show' -- $cur) )
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

docker_with_proxy()
{
    if [ "$#" -eq 0 ]; then
        echo "用法: docker_with_proxy [build] <docker build 参数...>"
        echo "示例: docker_with_proxy . -t your/image:tag"
        return 2
    fi
    if [ "${1:-}" = "build" ]; then
        shift
    fi

    local _hp="$(_myclash_http_port)"
    local _host="$(_myclash_lan_host)"
    local _proxy="http://${_host}:${_hp}/"
    local _no_proxy="${MYCLASH_DOCKER_NO_PROXY:-localhost,127.0.0.1,::1}"

    echo "docker_with_proxy: ${_proxy}"
    docker build \
        --build-arg "HTTP_PROXY=${_proxy}" \
        --build-arg "HTTPS_PROXY=${_proxy}" \
        --build-arg "NO_PROXY=${_no_proxy}" \
        --build-arg "http_proxy=${_proxy}" \
        --build-arg "https_proxy=${_proxy}" \
        --build-arg "no_proxy=${_no_proxy}" \
        "$@"
}

# Auto start Proxy in Terminal
if [ "$(_myclash_read_config shell_use_proxy)" = "true" ]; then
    _hp="$(_myclash_http_port)"
    export http_proxy=http://127.0.0.1:${_hp}
    export https_proxy=http://127.0.0.1:${_hp}
    echo "start proxy in Terminal (http ${_hp})"
else
    unset http_proxy;unset https_proxy
    echo "close proxy in Terminal"
fi
