#!/bin/bash
# 普通用户执行：移除 ~/.config/systemd/user/myclash.service、~/.bashrc 中片段、本仓库下 mcs/（可选逻辑保留与旧版一致）
# 若曾安装系统级单元，请先: sudo ./install/uninstall_root.sh

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
MYCLASH_ROOT_PWD=$(realpath "${SCRIPT_DIR}/..")
SERVICE_MODE=""
if [ -f "${MYCLASH_ROOT_PWD}/cache/service_mode" ]; then
	SERVICE_MODE=$(tr -d ' \t\r\n' <"${MYCLASH_ROOT_PWD}/cache/service_mode")
fi

if [ "${EUID:-0}" -eq 0 ] && [ "$SERVICE_MODE" != "direct" ]; then
	echo "请勿以 root 执行 uninstall.sh。系统级清理请: sudo ./install/uninstall_root.sh；容器 direct 模式可直接执行。" >&2
	exit 1
fi

if [ -x "${MYCLASH_ROOT_PWD}/venv/bin/python3" ] && [ -f "${MYCLASH_ROOT_PWD}/scripts/myclash_cli.py" ]; then
	echo "停止 MyClash 服务（若正在运行）"
	MYCLASH_ROOT_PWD="${MYCLASH_ROOT_PWD}" "${MYCLASH_ROOT_PWD}/venv/bin/python3" "${MYCLASH_ROOT_PWD}/scripts/myclash_cli.py" service stop 2>/dev/null || true
fi

echo "停止/移除用户级 myclash.service"
systemctl --user stop myclash.service 2>/dev/null || true
systemctl --user disable myclash.service 2>/dev/null || true
rm -f "${HOME}/.config/systemd/user/myclash.service"
systemctl --user daemon-reload 2>/dev/null || true

echo "从 ~/.bashrc 移除 MyClash 片段（若存在）"
RC="${HOME}/.bashrc"
if [ -f "$RC" ]; then
	start_line=$(grep -nF 'clash_env_set_start' "$RC" 2>/dev/null | head -1 | cut -d: -f1 || true)
	end_line=$(grep -nF 'clash_env_set_end' "$RC" 2>/dev/null | head -1 | cut -d: -f1 || true)
	if [ -n "${start_line}" ] && [ -n "${end_line}" ]; then
		sed -i "${start_line},${end_line}d" "$RC"
	fi
fi

echo "删除 ${MYCLASH_ROOT_PWD}/mcs（若存在）"
rm -rf "${MYCLASH_ROOT_PWD}/mcs"

echo "删除旧版 ${MYCLASH_ROOT_PWD}/clash（若存在）"
rm -rf "${MYCLASH_ROOT_PWD}/clash"

echo "删除 ${MYCLASH_ROOT_PWD}/cache（若存在，下载与订阅缓存）"
rm -rf "${MYCLASH_ROOT_PWD}/cache"

echo "用户级卸载完成。若曾使用旧版系统服务，请执行: sudo ./install/uninstall_root.sh"
echo "最后可手动删除整个仓库目录: ${MYCLASH_ROOT_PWD}"
