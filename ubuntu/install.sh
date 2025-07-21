#!/bin/bash

download_dashboard(){
    mkdir -p "${MYCLASH_ROOT_PWD}/tmp"
    chmod -R 777 "${MYCLASH_ROOT_PWD}/tmp"
    
    echo "===下载网页界面==="
    # 检查是否已经下载过
    if [ -f "${MYCLASH_ROOT_PWD}/tmp/Razord-meta-gh-pages.zip" ] && [ -f "${MYCLASH_ROOT_PWD}/tmp/yacd-gh-pages.zip" ]; then
        echo "网页界面已存在，跳过下载"
        return
    fi
    # 下载webpage
    base_url=https://gitee.com/wangdaochuan/resource_backup/releases/download/webpage
    download_dep $base_url/Razord-meta-gh-pages.zip ${MYCLASH_ROOT_PWD}/tmp/Razord-meta-gh-pages.zip
    download_dep $base_url/yacd-gh-pages.zip ${MYCLASH_ROOT_PWD}/tmp/yacd-gh-pages.zip
}
install_dashboard() {
    mkdir -p "${MYCLASH_ROOT_PWD}/clash/page"
    chmod -R 777 "${MYCLASH_ROOT_PWD}/clash/"

    unzip -o ${MYCLASH_ROOT_PWD}/tmp/Razord-meta-gh-pages.zip -d ${MYCLASH_ROOT_PWD}/clash/page/
    unzip -o ${MYCLASH_ROOT_PWD}/tmp/yacd-gh-pages.zip -d ${MYCLASH_ROOT_PWD}/clash/page/

    # 设置systemd
    # 生成clash_dashboard.service
    ${MYCLASH_ROOT_PWD}/ubuntu/scripts/gen_placehold_fill_file.py  \
    ${MYCLASH_ROOT_PWD}/ubuntu/template/clash_dashboard.service \
    ${MYCLASH_ROOT_PWD}/tmp/clash_dashboard.service \
    ${MYCLASH_ROOT_PWD}
    # 移动clash_dashboard.service
    mv ${MYCLASH_ROOT_PWD}/tmp/clash_dashboard.service /etc/systemd/system/clash_dashboard.service
    # 启动clash_dashboard.service
    systemctl daemon-reload
    systemctl enable clash_dashboard.service
    systemctl start clash_dashboard.service
}
download_clash(){
    mkdir -p "${MYCLASH_ROOT_PWD}/tmp"
    chmod -R 777 "${MYCLASH_ROOT_PWD}/tmp"
    echo "===安装依赖==="
    sudo apt install -y curl vim wget python3 python3-pip
    print_err_and_exit_if_failed "apt 安装失败,请检查网络连接"

    /usr/bin/python3 -m pip install pyyaml colorlog
    print_err_and_exit_if_failed "pyyaml | colorlog 安装失败,请检查网络连接"

    echo "===下载程序==="
    if [ -f "${MYCLASH_ROOT_PWD}/tmp/clash.gz" ]; then
        echo "clash.gz 已存在，跳过下载"

        print_err_and_exit_if_failed "Clash Core 下载失败"
    else
        echo "clash.gz 不存在，准备下载"
        arch=$(uname -m)
        if [ $arch = x86_64 ]; then
            clash_arch=clash-linux-amd64-v3-v1.11.4.gz
        elif [ $arch = aarch64 ]; then
            clash_arch=clash-linux-armv8-v1.11.8.gz
        # elif [ $arch = armv7a ]; then
        #     clash_arch=clash-linux-armv7-v1.12.0.gz
        else
            failed_and_exit "Arch $arch is not supported"
        fi

        wget ${dependenciesUrl}/$clash_arch -O ${MYCLASH_ROOT_PWD}/tmp/clash.gz
    fi
    
    echo "=======下载Country.mmdb======"
    if [ -f "${MYCLASH_ROOT_PWD}/tmp/Country.mmdb" ]; then
        echo "Country.mmdb 已存在，跳过下载"

    else
        echo "Country.mmdb 不存在，准备下载"
        wget ${dependenciesUrl}/Country.mmdb -O ${MYCLASH_ROOT_PWD}/tmp/Country.mmdb 
        print_err_and_exit_if_failed "Country.mmdb 下载失败"
    fi


}
install_clash(){
    echo "===安装==="
    mkdir -p ${MYCLASH_ROOT_PWD}/clash
    mkdir -p ${MYCLASH_ROOT_PWD}/clash/configs
    chmod -R 777 "${MYCLASH_ROOT_PWD}/clash/"

    cd ${MYCLASH_ROOT_PWD}/clash
    # install_dashboard
    # 解压 clash
    # gunzip -o ${MYCLASH_ROOT_PWD}/tmp/clash.gz -d ${MYCLASH_ROOT_PWD}/clash/
    gunzip -c ${MYCLASH_ROOT_PWD}/tmp/clash.gz > ${MYCLASH_ROOT_PWD}/clash/clash

    chmod +x ${MYCLASH_ROOT_PWD}/clash/clash

    cp ${MYCLASH_ROOT_PWD}/tmp/Country.mmdb {MYCLASH_ROOT_PWD}/clash/configs/Country.mmdb 

    # 读取version文件
    if [ -f "${MYCLASH_ROOT_PWD}/ubuntu/version" ]; then
        version=$(cat "${MYCLASH_ROOT_PWD}/ubuntu/version")
        echo "当前版本: $version"
    else
        echo "未找到版本文件: ${MYCLASH_ROOT_PWD}/ubuntu/version"
    fi
    # 检查 user_config.yaml 是否存在
    if [ ! -f "${MYCLASH_ROOT_PWD}/user_config.yaml" ]; then
        echo "未找到 user_config.yaml，将重新生成。"
        # 生成 user_config
        ${MYCLASH_ROOT_PWD}/ubuntu/scripts/gen_placehold_fill_file.py  \
        ${MYCLASH_ROOT_PWD}/ubuntu/template/user_config.yaml \
        ${MYCLASH_ROOT_PWD}/user_config.yaml \
        ${version}
        chmod 666 ${MYCLASH_ROOT_PWD}/user_config.yaml
    else
        # 检查 user_config.yaml 版本是否与当前版本一致
        config_version=""
        if grep -q '^version:' "${MYCLASH_ROOT_PWD}/user_config.yaml"; then
            config_version=$(grep '^version:' "${MYCLASH_ROOT_PWD}/user_config.yaml" | awk '{print $2}')
        fi
        if [ "$version" != "" ] && [ "$version" != "$config_version" ]; then
            echo "user_config.yaml 版本($config_version)与当前版本($version)不一致，将重新生成。"
            rm -f "${MYCLASH_ROOT_PWD}/user_config.yaml"
            # 生成 user_config
            ${MYCLASH_ROOT_PWD}/ubuntu/scripts/gen_placehold_fill_file.py  \
            ${MYCLASH_ROOT_PWD}/ubuntu/template/user_config.yaml \
            ${MYCLASH_ROOT_PWD}/user_config.yaml \
            ${version}
            chmod 666 ${MYCLASH_ROOT_PWD}/user_config.yaml
        fi
    fi

    # create empty 
    cp ${MYCLASH_ROOT_PWD}/ubuntu/template/empty.yaml ${MYCLASH_ROOT_PWD}/clash/configs/config.yaml 
    chmod 666  ${MYCLASH_ROOT_PWD}/clash/configs/config.yaml 



    echo "设置systemd 服务"

    # remove clash from bashrc
    echo "remove clash config in /etc/bash.bashrc"
    start_line=$(cat /etc/bash.bashrc|grep clash_env_set_start -n|head -n 1|cut -d: -f1)
    end_line=$(cat /etc/bash.bashrc|grep clash_env_set_end -n|head -n 1|cut -d: -f1)
    # echo "delete ${start_line}~${end_line}"
    sed -i "${start_line},${end_line}d" /etc/bash.bashrc


    echo remove old clash.service
    # remove /etc/systemd/system/clash.service
    rm -f /etc/systemd/system/clash.service >> /dev/null


    # 设置clash.service
    clash_exec="${MYCLASH_ROOT_PWD}/clash/clash"
    clash_config="${MYCLASH_ROOT_PWD}/clash/configs"
    # 生成clash.service
    ${MYCLASH_ROOT_PWD}/ubuntu/scripts/gen_placehold_fill_file.py  \
    ${MYCLASH_ROOT_PWD}/ubuntu/template/clash.service \
    ${MYCLASH_ROOT_PWD}/tmp/clash.service \
    ${MYCLASH_ROOT_PWD} ${MYCLASH_ROOT_PWD}
    mv ${MYCLASH_ROOT_PWD}/tmp/clash.service /etc/systemd/system/clash.service
    # 启动clash.service
    systemctl daemon-reload
    systemctl enable clash.service
    systemctl start clash.service

}

env_sudoers_add(){
    # 记得开始前备份
    # 确认是否是 root 用户
    if [ $EUID -ne 0 ]; then
        echo "请使用 root 用户执行此函数。"
    else
        # 备份原始的 sudoers 文件
        cp /etc/sudoers /etc/sudoers.bak    
        # 检查是否已经存在对应的设置
        if grep -q 'Defaults env_keep += "http_proxy https_proxy ftp_proxy no_proxy"' /etc/sudoers; then
            echo "环境变量代理设置已存在于 /etc/sudoers 中，无需重复添加。"
        else
            # 使用 echo 和 tee 安全地追加到 sudoers 文件
            echo 'Defaults env_keep += "http_proxy https_proxy ftp_proxy no_proxy"' | tee -a /etc/sudoers > /dev/null
            if [ $? -eq 0 ]; then
                echo "成功添加环境变量代理设置到 /etc/sudoers。"
            else
                echo "添加失败，请检查脚本权限或 /etc/sudoers 文件格式。"
            fi
        fi
    fi
}
##################################################

argNums=$#
dependenciesUrl=https://gitee.com/wangdaochuan/resource_backup/releases/download/cat_dependencies
bashrcPath=$(echo $(pwd)/$0 | awk '{split($0,a,"install.sh"); print a[1]}')

export MYCLASH_ROOT_PWD=$(realpath ${bashrcPath}/..)
source ${MYCLASH_ROOT_PWD}/tools/common_func.sh # 常用函数
source ${MYCLASH_ROOT_PWD}/ubuntu/PROMPT.sh # 提示语
# echo ${MYCLASH_ROOT_PWD}

# root user check
if (( $EUID != 0 )); then
    failed_and_exit "Please run as root"
fi

# get arguments
use_cache=$1

#############################################

cat ${MYCLASH_ROOT_PWD}/tools/logo.txt
# 使用须知
myclashinfo_welcome
read -n 1 -s -r -p "Press any key to continue..." key
echo "\n\n"

download_clash
download_dashboard
if [[ "$use_cache" != "--deactivate-for-sudo" ]]; then
    env_sudoers_add
fi


rm -rf ${MYCLASH_ROOT_PWD}/clash
install_clash
install_dashboard

echo "设置环境变量"
# 生成env_prefix.sh
${MYCLASH_ROOT_PWD}/ubuntu/scripts/gen_placehold_fill_file.py  \
${MYCLASH_ROOT_PWD}/ubuntu/template/env_prefix.txt \
${MYCLASH_ROOT_PWD}/tmp/env_prefix.txt \
${MYCLASH_ROOT_PWD} 

cat ${MYCLASH_ROOT_PWD}/tmp/env_prefix.txt >> /etc/bash.bashrc



echo_guider_after_success
