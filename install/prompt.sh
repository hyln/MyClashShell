myclashinfo_welcome(){
    echo "欢迎使用 MyClashShell for ubuntu" 
    echo "开始前请确认"
    echo "1. 不是在docker的container中配置"
    echo "2. 不是在wsl2中配置"
    echo ""
    echo "目前每次运行都会删除之前的程序和数据"
    echo "是否确定开始 (按 Ctrl+c 退出)"
}



echo_guider_after_success(){
    echo_R "clash 安装完成，为了正常使用MyClashShell,还需要一些步骤"
    echo "---设置user_config.yaml---"
    echo "1.请根据你的实际情况修改MyClashShell目录下刚生成的user_config.yaml"
    echo "2.其中<your_proxy_name>和<you_proxy_url>分别指为代理设定的名字(任意) 以及 对应的订阅链接"
    echo "---source---"
    echo "3.为了在终端生效MyClash你需要 在此窗口运行 \"source /etc/bash.bashrc ;source ~/.bashrc\" 或者 你可以选择重新打开一个终端"
    echo "4.现在，你可以直接输入 myclash 或者 myclash help 学习如何使用了"
    echo "---更新订阅---"
    echo "5.config.yaml设置完成后,可以通过 myclash service update_subcribe 更新订阅"
    echo_R "注意:此安装完成后，MyClashShell文件夹不能删除"
}



