#!/bin/bash
# 需 root：apt 依赖、sudoers 代理保留、清理旧版系统级 systemd 与 /etc/bash.bashrc 中的 MyClash 片段。
# 完成后请执行: ./install/install.sh（推荐普通用户；root 亦可，脚本会提示预期路径）

if [ "${EUID:-}" -ne 0 ]; then
	echo "请使用: sudo ./install/install_root.sh" >&2
	exit 1
fi

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
export MYCLASH_ROOT_PWD=$(realpath "${SCRIPT_DIR}/..")
# shellcheck source=/dev/null
source "${MYCLASH_ROOT_PWD}/scripts/tools/common_func.sh"

mcs_install_apt_packages() {
	local list_file="${MYCLASH_ROOT_PWD}/install/apt-packages.txt"
	if [ ! -f "${list_file}" ]; then
		failed_and_exit "缺少 ${list_file}"
	fi
	local pkgs=()
	while IFS= read -r line || [ -n "${line}" ]; do
		line=$(printf '%s\n' "${line}" | sed -e 's/#.*//' -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')
		[ -z "${line}" ] && continue
		pkgs+=("${line}")
	done < "${list_file}"
	if [ "${#pkgs[@]}" -eq 0 ]; then
		echo "警告: ${list_file} 中无有效包名，跳过 apt 安装" >&2
		return 0
	fi
	echo "=== apt 安装依赖（${#pkgs[@]} 个，列表见 install/apt-packages.txt）==="
	apt-get update -qq
	apt-get install -y "${pkgs[@]}"
	print_err_and_exit_if_failed "apt 安装失败,请检查网络连接"
}

env_sudoers_add() {
	if [ "${EUID:-}" -ne 0 ]; then
		echo "请使用 root 用户执行此函数。"
		return 1
	fi
	cp /etc/sudoers /etc/sudoers.bak
	if grep -q 'Defaults env_keep += "http_proxy https_proxy ftp_proxy no_proxy"' /etc/sudoers; then
		echo "环境变量代理设置已存在于 /etc/sudoers 中，无需重复添加。"
	else
		echo 'Defaults env_keep += "http_proxy https_proxy ftp_proxy no_proxy"' | tee -a /etc/sudoers >/dev/null
		if [ $? -eq 0 ]; then
			echo "成功添加环境变量代理设置到 /etc/sudoers。"
		else
			echo "添加失败，请检查脚本权限或 /etc/sudoers 文件格式。"
		fi
	fi
}

use_cache="${1:-}"

mcs_install_apt_packages

if [[ "${use_cache}" != "--deactivate-for-sudo" ]]; then
	env_sudoers_add
fi

echo "=== 清理旧版系统级 systemd 单元（若存在）==="
systemctl stop myclash.service 2>/dev/null || true
systemctl stop clash.service 2>/dev/null || true
systemctl stop clash_dashboard.service 2>/dev/null || true
systemctl disable myclash.service 2>/dev/null || true
systemctl disable clash.service 2>/dev/null || true
systemctl disable clash_dashboard.service 2>/dev/null || true
rm -f /etc/systemd/system/clash.service
rm -f /etc/systemd/system/clash_dashboard.service
rm -f /etc/systemd/system/myclash.service
systemctl daemon-reload 2>/dev/null || true

echo "=== 从 /etc/bash.bashrc 移除旧版 MyClash 片段（若存在）==="
if [ -f /etc/bash.bashrc ]; then
	start_line=$(grep -nF 'clash_env_set_start' /etc/bash.bashrc 2>/dev/null | head -1 | cut -d: -f1 || true)
	end_line=$(grep -nF 'clash_env_set_end' /etc/bash.bashrc 2>/dev/null | head -1 | cut -d: -f1 || true)
	if [ -n "${start_line}" ] && [ -n "${end_line}" ]; then
		sed -i "${start_line},${end_line}d" /etc/bash.bashrc
		echo "已删除 /etc/bash.bashrc 中 clash_env 标记块。"
	fi
fi

echo ""
echo "系统级准备已完成。在项目根目录执行用户级安装:"
echo "  ./install/install.sh"
echo "（推荐登录用户执行；若以 root 执行 install.sh，服务与 ~/.bashrc 将落在 root 的 HOME 下。）"
