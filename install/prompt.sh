myclashinfo_welcome(){
    echo "欢迎使用 MyClashShell for ubuntu"
    echo "是否确定开始 (按 Ctrl+c 退出)"
}



echo_guider_after_success(){
    echo_R "mcs 内核与配置目录安装完成，为了正常使用 MyClashShell，还需要一些步骤"
    echo "---设置user_config.yaml---"
    echo "1.请根据你的实际情况修改MyClashShell目录下刚生成的user_config.yaml"
    echo "2.其中<your_proxy_name>和<you_proxy_url>分别指为代理设定的名字(任意) 以及 对应的订阅链接"
    echo "---systemd 用户服务---"
    echo "3.Clash 已注册为当前用户的 systemd --user 服务（~/.config/systemd/user/）"
    echo "   若开机后未自动拉起，可执行: sudo loginctl enable-linger $(whoami)"
    echo "---source---"
    echo "4.在本终端执行 source ~/.bashrc，或重新打开终端，使 MYCLASH_ROOT_PWD 与 myclash 命令生效"
    echo "5.现在，你可以直接输入 myclash 或者 myclash help 学习如何使用了"
    echo "---更新订阅---"
    echo "6.config.yaml设置完成后,可以通过 myclash service update_subscribe 更新订阅"
    echo_R "注意:此安装完成后，MyClashShell文件夹不能删除"
}



