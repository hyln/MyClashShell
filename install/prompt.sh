myclashinfo_welcome(){
    echo "欢迎使用 MyClashShell for ubuntu"
    echo "是否确定开始 (按 Ctrl+c 退出)"
}



echo_guider_after_success(){
    echo_G "mcs 内核与配置目录安装完成，为了正常使用 MyClashShell，还需要一些步骤"
    echo "---设置user_config.yaml---"
    echo "1. source ~/.bashrc 或打开新终端"
    echo "2.修改MyClashShell目录下刚生成的user_config.yaml, 主要是subscribes部分"
    echo "3.config.yaml设置完成后,可以通过 myclash service update_subscribe 更新订阅"
    echo "--------------------------------"
    echo "你可以直接输入 myclash 或者 myclash help 学习如何使用了"

    echo_R "注意:此安装完成后，MyClashShell文件夹不能删除"
}



