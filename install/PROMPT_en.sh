myclashinfo_welcome(){
    echo "Welcome to MyClashShell for Ubuntu"
    echo "Are you sure you want to start? (Press Ctrl+c to exit)"
}



echo_guider_after_success(){
    echo_R "Clash installation is complete. To use MyClashShell properly, there are a few more steps"
    echo "---Set up config.yaml---"
    echo "1. Please modify the user_config.yaml generated in the MyClashShell directory according to your actual situation"
    echo "2. In the file, <your_proxy_name> and <your_proxy_url> represent the name (any name) and subscription URL for the proxy you set"
    echo "---systemd user service---"
    echo "3. Clash is registered as a systemd --user unit under ~/.config/systemd/user/"
    echo "   If it does not start at boot, run: sudo loginctl enable-linger $(whoami)"
    echo "---Source---"
    echo "4. Run source ~/.bashrc in this terminal (or open a new terminal) so MYCLASH_ROOT_PWD and myclash are available"
    echo "5. Now you can type myclash or myclash help"
    echo "---Update Subscription---"
    echo "6. After config.yaml is ready, update the subscription with: myclash service update_subscribe"
    echo_R "Note: After the installation is complete, the MyClashShell folder cannot be deleted"
}
