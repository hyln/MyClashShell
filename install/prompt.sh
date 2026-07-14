myclashinfo_welcome(){
    echo "欢迎使用 MyClashShell for ubuntu"
    echo "是否确定开始 (按 Ctrl+c 退出)"
}



echo_guider_after_success(){
    echo_G "MyClashShell 安装完成"
    echo ""
    echo "接下来请按以下步骤配置并启用代理："
    echo "  1. source ~/.bashrc"
    echo "  2. myclash config edit"
    echo "     在 user_config.yaml 的 subscribes 中填写订阅名称、url 和 backend，"
    echo "     并确认 default_subscribe 指向要使用的订阅。"
    echo "  3. myclash service update_subscribe"
    echo "     下载订阅、生成配置并重载内核。"
    echo "  4. myclash service status"
    echo "     确认服务和代理连通性。"
    echo ""
    echo "常用命令："
    echo "  myclash ui          选择节点、测速（clash/v2ray 均支持）"
    echo "  myclash shell on    为当前终端开启代理"
    echo "  myclash shell off   为当前终端关闭代理"
    echo "  myclash help        查看完整帮助"
    if [ "${SERVICE_MODE:-}" = "direct" ]; then
        echo ""
        echo "当前使用 direct 服务模式；可用 myclash service start|stop|restart 管理进程。"
    fi
    echo ""
    echo_R "请保留 MyClashShell 目录；命令、配置和内核均依赖此目录。"
}


