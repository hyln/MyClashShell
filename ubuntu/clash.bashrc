#!/bin/bash
source ${MYCLASH_ROOT_PWD}/tools/common_func.sh
myclash()
{
    case $1 in
    'service')
        if [ $2 = "start" ]; then
            sudo systemctl start clash
            sudo systemctl start clash_dashboard

        elif [ $2 = "stop" ]; then
            sudo systemctl stop clash
            sudo systemctl stop clash_dashboard

        elif [ $2 = "restart" ]; then
            sudo systemctl restart clash
            sudo systemctl restart clash_dashboard
        elif [ $2 = "status" ]; then
            sudo systemctl status clash
        elif [ $2 = "get_logs" ]; then
            echo RUNNING
            curl --location 'http://127.0.0.1:9090/logs'
        elif [ $2 = "update_subcribe" ]; then
            myclash shell off
            ${MYCLASH_ROOT_PWD}/venv/bin/python3 ${MYCLASH_ROOT_PWD}/ubuntu/scripts/update_proxy_config.py
            sudo systemctl restart clash
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
        ${MYCLASH_ROOT_PWD}/venv/bin/python3 ${MYCLASH_ROOT_PWD}/ubuntu/scripts/myclash.py $1 $2
        ;;
    'change_subscribe')
        ${MYCLASH_ROOT_PWD}/venv/bin/python3 ${MYCLASH_ROOT_PWD}/ubuntu/scripts/change_sub.py $2
        sudo systemctl restart clash
        ;;        
    'help')
        echo "myclash [command*] [option*]"
        echo "Command:"
        echo "      service [ start/stop/restart/status/get_logs/update_subcribe ]"
        echo "      window [ on/off ]"
        echo "      shell [ on/off ]"
        echo "      cfg"
        echo "======================"
        echo "Remark"
        echo "[command] service 负责管理clash服务"
        echo "[option] clash的服务设置为在安装完成后开机自启,你可以手动开启，关闭或重启服务[start/stop/restart]"
        echo "[option] update_subcribe 选项可以更新代理"
        echo "[option] get_logs 可以监看日志"
        echo "[command] window  命令管理在图形化应用(如 chrome )[on/off]代理"
        echo "[command] shell   命令管理在当前终端窗口[on/off]代理,默认值为config.yaml中的shell_proxy_default参数"
        echo "[command] cfg "
        ;;
    *)
        # ${MYCLASH_ROOT_PWD}/venv/bin/python3 ${MYCLASH_ROOT_PWD}/tools/gui/gui.py
        echo Myclash $(cat ${MYCLASH_ROOT_PWD}/ubuntu/version)
        bash ${MYCLASH_ROOT_PWD}/tools/test_proxy_status.sh > /dev/null
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
        current_core=$(cat ${MYCLASH_ROOT_PWD}/tmp/current_core.txt 2>/dev/null || echo clash)

        echo "当前使用配置: $current_config_name"
        echo "当前代理内核: $current_core (clash=原版, mihomo=Meta/AnyTLS 等)"
        echo "你可以通过 myclash help 查看帮助"
        echo "==================================="
        echo "若需要使用程序控制面板，请打开网页"
        echo "http://127.0.0.1:34507"
    esac
    
}
_myclash()
{
    local cur=${COMP_WORDS[COMP_CWORD]};
    local cmd=${COMP_WORDS[COMP_CWORD-1]};

    case $cmd in
    'myclash')
        COMPREPLY=( $(compgen -W 'service window shell help cfg change_subscribe' -- $cur) ) 
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
shell_proxy_default=$(${MYCLASH_ROOT_PWD}/venv/bin/python3 ${MYCLASH_ROOT_PWD}/tools/read_yaml.py shell_proxy_default)
if [ $shell_proxy_default = "ON" ]; then
    export http_proxy=http://127.0.0.1:7890
    export https_proxy=http://127.0.0.1:7890
    echo "start proxy in Terminal"
else
    unset http_proxy;unset https_proxy
    echo "close proxy in Terminal"
fi
