#!/bin/bash
source ${MYCLASH_ROOT_PWD}/scripts/tools/common_func.sh

# 与 user_config.yaml 中 port / socks-port 一致（缺省 7890 / 7891）
_myclash_http_port() {
    local p=7890
    local _p
    _p=$(PYTHONPATH="${MYCLASH_ROOT_PWD}" ${MYCLASH_ROOT_PWD}/venv/bin/python3 -m scripts.tools.read_config_value port 2>/dev/null)
    if [[ "$_p" =~ ^[0-9]+$ ]]; then
        p="$_p"
    fi
    echo "$p"
}

_myclash_socks_port() {
    local p=7891
    local _p
    _p=$(PYTHONPATH="${MYCLASH_ROOT_PWD}" ${MYCLASH_ROOT_PWD}/venv/bin/python3 -m scripts.tools.read_config_value socks-port 2>/dev/null)
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

_myclash_run_cli() {
    PYTHONPATH="${MYCLASH_ROOT_PWD}" \
        "${MYCLASH_ROOT_PWD}/venv/bin/python3" -m scripts.myclash_cli "$@"
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
            _myclash_with_shell_off "$@"
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
            /usr/bin/gsettings set org.gnome.system.proxy.socks host 127.0.0.1
            /usr/bin/gsettings set org.gnome.system.proxy.socks port "$_sp"
            /usr/bin/gsettings set org.gnome.system.proxy.ftp host 127.0.0.1
            /usr/bin/gsettings set org.gnome.system.proxy.ftp port "$_hp"
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
            export all_proxy=socks5h://127.0.0.1:${_sp}
            export no_proxy=127.0.0.1,localhost
            export HTTP_PROXY=http://127.0.0.1:${_hp}
            export HTTPS_PROXY=http://127.0.0.1:${_hp}
            export FTP_PROXY=http://127.0.0.1:${_hp}
            export ALL_PROXY=socks5h://127.0.0.1:${_sp}
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
shell_proxy_default=$(PYTHONPATH="${MYCLASH_ROOT_PWD}" ${MYCLASH_ROOT_PWD}/venv/bin/python3 -m scripts.tools.read_config_value shell_proxy_default)
if [ "${shell_proxy_default}" = "ON" ]; then
    _hp="$(_myclash_http_port)"
    export http_proxy=http://127.0.0.1:${_hp}
    export https_proxy=http://127.0.0.1:${_hp}
    echo "start proxy in Terminal (http ${_hp})"
else
    unset http_proxy;unset https_proxy
    echo "close proxy in Terminal"
fi
