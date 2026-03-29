myclashinfo_welcome(){
    echo "Welcome to MyClashShell for Ubuntu"
    echo "Before you start, please make sure:"
    echo "1. You are not configuring it inside a Docker container"
    echo "2. You are not configuring it inside WSL2"
    echo ""
    echo "Currently, each run will delete the previous program and data"
    echo "Are you sure you want to start? (Press Ctrl+c to exit)"
}



echo_guider_after_success(){
    echo_R "Clash installation is complete. To use MyClashShell properly, there are a few more steps"
    echo "---Set up config.yaml---"
    echo "1. Please modify the user_config.yaml generated in the MyClashShell directory according to your actual situation"
    echo "2. In the file, <your_proxy_name> and <your_proxy_url> represent the name (any name) and subscription URL for the proxy you set"
    echo "---Source---"
    echo "3. To make MyClash effective in the terminal, run \"source /etc/bash.bashrc; source ~/.bashrc\" in this window, or you can open a new terminal"
    echo "4. Now, you can directly type myclash or myclash help to learn how to use it"
    echo "---Update Subscription---"
    echo "5. After setting up config.yaml, you can update the subscription using myclash service update_subscribe"
    echo_R "Note: After the installation is complete, the MyClashShell folder cannot be deleted"
}
