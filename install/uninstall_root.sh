#!/bin/bash
# 需 root：移除旧版系统级 systemd 单元、/etc/bash.bashrc 中的 MyClash 片段。
# 用户级数据请再以普通用户执行: ./install/uninstall.sh

if [ "${EUID:-}" -ne 0 ]; then
	echo "请使用: sudo ./install/uninstall_root.sh" >&2
	exit 1
fi

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
MYCLASH_ROOT_PWD=$(realpath "${SCRIPT_DIR}/..")

echo "停止/移除系统级旧单元（若存在）"
systemctl stop myclash.service 2>/dev/null || true
systemctl stop clash.service 2>/dev/null || true
systemctl stop clash_dashboard.service 2>/dev/null || true
systemctl disable myclash.service 2>/dev/null || true
systemctl disable clash.service 2>/dev/null || true
systemctl disable clash_dashboard.service 2>/dev/null || true
rm -f /etc/systemd/system/myclash.service
rm -f /etc/systemd/system/clash.service
rm -f /etc/systemd/system/clash_dashboard.service
systemctl daemon-reload 2>/dev/null || true

echo "从 /etc/bash.bashrc 移除 MyClash 片段（若存在）"
if [ -f /etc/bash.bashrc ]; then
	start_line=$(grep -nF 'clash_env_set_start' /etc/bash.bashrc 2>/dev/null | head -1 | cut -d: -f1 || true)
	end_line=$(grep -nF 'clash_env_set_end' /etc/bash.bashrc 2>/dev/null | head -1 | cut -d: -f1 || true)
	if [ -n "${start_line}" ] && [ -n "${end_line}" ]; then
		sed -i "${start_line},${end_line}d" /etc/bash.bashrc
	fi
fi

echo "系统级卸载步骤完成。如需删除本用户 systemd 单元与 ~/.bashrc 片段，请在该用户下执行: ./install/uninstall.sh"
echo "最后可手动删除目录: ${MYCLASH_ROOT_PWD}"
