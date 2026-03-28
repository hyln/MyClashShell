#!/bin/bash
if (( $EUID != 0 )); then
    echo "Please run as root"
    exit
fi

rm -rf clash
systemctl stop myclash.service 2>/dev/null || true
systemctl stop clash.service 2>/dev/null || true
systemctl stop clash_dashboard.service 2>/dev/null || true
systemctl disable myclash.service 2>/dev/null || true
systemctl disable clash.service 2>/dev/null || true
systemctl disable clash_dashboard.service 2>/dev/null || true

echo remove systemd units
rm -f /etc/systemd/system/myclash.service >> /dev/null
rm -f /etc/systemd/system/clash.service >> /dev/null
rm -f /etc/systemd/system/clash_dashboard.service >> /dev/null

systemctl daemon-reload >> /dev/null

echo "remove config in /etc/bash.bashrc"
start_line=$(cat /etc/bash.bashrc|grep clash_env_set_start -n|head -n 1|cut -d: -f1)
end_line=$(cat /etc/bash.bashrc|grep clash_env_set_end -n|head -n 1|cut -d: -f1)
# echo "delete ${start_line}~${end_line}"
sed -i "${start_line},${end_line}d" /etc/bash.bashrc




echo "卸载完成，最后请将 MyClashShell 文件夹 整体删除完成最终卸载"
