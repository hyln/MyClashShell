#!/bin/bash
if (( EUID != 0 )); then
    echo "Please run as root"
    exit 1
fi
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
ROOT=$(cd "${SCRIPT_DIR}/.." && pwd)
cd "${ROOT}" || exit 1
echo "卸载目录: ${ROOT}"
rm -rf "${ROOT}/clash"
systemctl disable clash
echo remove old clash.service
rm -f /etc/systemd/system/clash.service >> /dev/null
rm -f /etc/systemd/system/clash_dashboard.service >> /dev/null

systemctl stop clash.service
systemctl stop clash_dashboard.service
systemctl daemon-reload >> /dev/null

echo "remove config in /etc/bash.bashrc"
start_line=$(cat /etc/bash.bashrc|grep clash_env_set_start -n|head -n 1|cut -d: -f1)
end_line=$(cat /etc/bash.bashrc|grep clash_env_set_end -n|head -n 1|cut -d: -f1)
# echo "delete ${start_line}~${end_line}"
sed -i "${start_line},${end_line}d" /etc/bash.bashrc




echo "卸载完成，最后请将 MyClashShell 文件夹 整体删除完成最终卸载"
