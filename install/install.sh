#!/bin/bash
# 在仓库根目录执行: ./install/install.sh（推荐普通用户；root 亦可，见下方说明）
# 系统级准备（apt、sudoers、清理旧系统服务与 /etc/bash.bashrc）请先:
#   sudo ./install/install_root.sh

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
export MYCLASH_ROOT_PWD=$(realpath "${SCRIPT_DIR}/..")

source "${MYCLASH_ROOT_PWD}/scripts/tools/common_func.sh"
source "${MYCLASH_ROOT_PWD}/install/prompt.sh"

mcs_print_root_install_notice() {
	if [ "${EUID:-0}" -ne 0 ]; then
		return 0
	fi
	echo ""
	echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	echo "  当前以 root 执行 install.sh（有效用户: $(id -un)）"
	echo "  预期写入位置如下，请自行判断是否合适："
	echo "    • systemd --user: \${HOME}/.config/systemd/user/myclash.service"
	echo "      （当前 HOME=${HOME:-未设置}）"
	echo "    • shell 片段: \${HOME}/.bashrc"
	echo "    • 仓库内: ${MYCLASH_ROOT_PWD}/venv 、 mcs/ 、 cache/（下载缓存）、tmp/（生成物）等"
	echo "  桌面日常使用建议在普通用户下安装；root/容器等场景可忽略本提示。"
	echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	echo ""
}

if ! command -v python3 >/dev/null 2>&1; then
	failed_and_exit "未找到 python3。请先执行: sudo ./install/install_root.sh"
fi

# 是否 systemd 系统：以 PID 1 的 comm 为准（与 ps -p 1 -o comm= 一致）。
# 非 root：另需 logind 的 systemd --user（/run/user/$UID）。
# root（sudo）：/run/user/0 常不存在，仅提示，不因此退出。
mcs_require_pid1_systemd() {
	local p1
	p1=$(ps -p 1 -o comm= 2>/dev/null | tr -d ' \t\r\n')
	if [ "$p1" != "systemd" ]; then
		failed_and_exit "未检测到 systemd 作为 PID 1（ps -p 1 -o comm= 得到: ${p1:-空}）。本安装需要 systemd 作为 init。"
	fi
}

mcs_require_systemd_user_env() {
	if [ "${EUID:-0}" -eq 0 ]; then
		rd="/run/user/0"

		if [ ! -d "$rd" ]; then
			echo "root user systemd runtime not found. Try: sudo loginctl enable-linger root" >&2
			return 1
		fi

		export XDG_RUNTIME_DIR="$rd"
		export DBUS_SESSION_BUS_ADDRESS="unix:path=${rd}/bus"

		if ! systemctl --user is-system-running >/dev/null 2>&1; then
			echo "root systemd --user not running. Try: sudo loginctl enable-linger root" >&2
			return 1
		fi

		return 0
	fi
}

mcs_require_systemd_user_env

mkvenv() {
	local ENV_NAME=${1:-venv}
	local BASE_DIR="${MYCLASH_ROOT_PWD:-$(pwd)}"
	local ENV_DIR="${BASE_DIR%/}/${ENV_NAME}"

	if ! command -v python3 >/dev/null 2>&1; then
		echo "❌ python3 未安装"
		return 1
	fi

	if ! python3 -m venv --help >/dev/null 2>&1; then
		echo "❌ python3 未提供 venv 模块。请先执行: sudo ./install/install_root.sh（安装 python3-venv）"
		return 1
	fi

	echo "📦 在 ${BASE_DIR} 创建虚拟环境: $ENV_NAME"
	python3 -m venv "$ENV_DIR" || return 1

	echo "🚀 激活虚拟环境: $ENV_DIR"
	# shellcheck source=/dev/null
	source "${ENV_DIR}/bin/activate"

	"${MYCLASH_ROOT_PWD}/venv/bin/pip" install --upgrade pip >/dev/null 2>&1

	"${MYCLASH_ROOT_PWD}/venv/bin/pip" install pyyaml requests


	echo "✅ 完成！当前环境: $ENV_DIR"
}

download_clash() {
	echo "===下载内核 mihomo（install/resolve_download.py install-cache，安装为 mcs/bin/clash）==="
	"${MYCLASH_ROOT_PWD}/venv/bin/python3" "${MYCLASH_ROOT_PWD}/install/resolve_download.py" install-cache
	print_err_and_exit_if_failed "install-cache 失败（见上）"
}

install_mcs() {
	echo "===安装 mcs/（bin：内核；configs：配置）==="
	mkdir -p "${MYCLASH_ROOT_PWD}/mcs/bin"
	mkdir -p "${MYCLASH_ROOT_PWD}/mcs/configs"
	chmod -R u+rwX "${MYCLASH_ROOT_PWD}/mcs/"

	# mihomo 压缩包解压为 mcs/bin/clash，与 user_config 中 backend: clash 及 paths.clash_executable 一致
	gunzip -c "${MYCLASH_ROOT_PWD}/cache/clash.gz" >"${MYCLASH_ROOT_PWD}/mcs/bin/clash"
	chmod +x "${MYCLASH_ROOT_PWD}/mcs/bin/clash"

	if [ -f "${MYCLASH_ROOT_PWD}/cache/v2ray" ]; then
		cp -f "${MYCLASH_ROOT_PWD}/cache/v2ray" "${MYCLASH_ROOT_PWD}/mcs/bin/v2ray"
		chmod +x "${MYCLASH_ROOT_PWD}/mcs/bin/v2ray"
		echo "已从 cache/v2ray 复制 v2ray 到 mcs/bin/"
	fi

	cp "${MYCLASH_ROOT_PWD}/cache/Country.mmdb" "${MYCLASH_ROOT_PWD}/mcs/configs/Country.mmdb"

	version=""
	if [ -f "${MYCLASH_ROOT_PWD}/install/version" ]; then
		version=$(cat "${MYCLASH_ROOT_PWD}/install/version")
		echo "当前版本: $version"
	else
		echo "未找到版本文件: ${MYCLASH_ROOT_PWD}/install/version"
	fi
	if [ ! -f "${MYCLASH_ROOT_PWD}/user_config.yaml" ]; then
		echo "未找到 user_config.yaml，将重新生成。"
		"${MYCLASH_ROOT_PWD}/venv/bin/python3" "${MYCLASH_ROOT_PWD}/scripts/runtime/gen_placehold_fill_file.py" \
			"${MYCLASH_ROOT_PWD}/install/templates/user_config.yaml" \
			"${MYCLASH_ROOT_PWD}/user_config.yaml" \
			"${version}"
		chmod u+rw "${MYCLASH_ROOT_PWD}/user_config.yaml"
		"${MYCLASH_ROOT_PWD}/venv/bin/python3" "${MYCLASH_ROOT_PWD}/scripts/runtime/init_user_config_ports.py" \
			"${MYCLASH_ROOT_PWD}/user_config.yaml"
	else
		config_version=""
		if grep -q '^version:' "${MYCLASH_ROOT_PWD}/user_config.yaml"; then
			config_version=$(grep '^version:' "${MYCLASH_ROOT_PWD}/user_config.yaml" | awk '{print $2}')
		fi
		if [ "$version" != "" ] && [ "$version" != "$config_version" ]; then
			echo "user_config.yaml 版本($config_version)与当前版本($version)不一致，将重新生成。"
			rm -f "${MYCLASH_ROOT_PWD}/user_config.yaml"
			"${MYCLASH_ROOT_PWD}/venv/bin/python3" "${MYCLASH_ROOT_PWD}/scripts/runtime/gen_placehold_fill_file.py" \
				"${MYCLASH_ROOT_PWD}/install/templates/user_config.yaml" \
				"${MYCLASH_ROOT_PWD}/user_config.yaml" \
				"${version}"
			chmod u+rw "${MYCLASH_ROOT_PWD}/user_config.yaml"
			"${MYCLASH_ROOT_PWD}/venv/bin/python3" "${MYCLASH_ROOT_PWD}/scripts/runtime/init_user_config_ports.py" \
				"${MYCLASH_ROOT_PWD}/user_config.yaml"
		fi
	fi

	cp "${MYCLASH_ROOT_PWD}/install/templates/empty.yaml" "${MYCLASH_ROOT_PWD}/mcs/configs/config.yaml"
	chmod u+rw "${MYCLASH_ROOT_PWD}/mcs/configs/config.yaml"
	if [ ! -f "${MYCLASH_ROOT_PWD}/mcs/configs/v2ray.json" ]; then
		cp "${MYCLASH_ROOT_PWD}/install/templates/v2ray-default.json" "${MYCLASH_ROOT_PWD}/mcs/configs/v2ray.json"
		chmod u+rw "${MYCLASH_ROOT_PWD}/mcs/configs/v2ray.json"
	fi

	echo "设置 systemd 用户服务（systemctl --user）"
	USER_UNIT_DIR="${HOME}/.config/systemd/user"
	mkdir -p "${USER_UNIT_DIR}"
	systemctl --user stop myclash.service 2>/dev/null || true
	systemctl --user disable myclash.service 2>/dev/null || true

	"${MYCLASH_ROOT_PWD}/venv/bin/python3" "${MYCLASH_ROOT_PWD}/scripts/runtime/gen_placehold_fill_file.py" \
		"${MYCLASH_ROOT_PWD}/install/templates/myclash.service" \
		"${MYCLASH_ROOT_PWD}/tmp/myclash.service" \
		"${MYCLASH_ROOT_PWD}" "${MYCLASH_ROOT_PWD}" "${MYCLASH_ROOT_PWD}" "${MYCLASH_ROOT_PWD}"
	cp "${MYCLASH_ROOT_PWD}/tmp/myclash.service" "${USER_UNIT_DIR}/myclash.service"
	chmod 0644 "${USER_UNIT_DIR}/myclash.service"
	rm -f "${MYCLASH_ROOT_PWD}/tmp/myclash.service"

	systemctl --user daemon-reload
	print_err_and_exit_if_failed "systemctl --user daemon-reload 失败"
	if ! systemctl --user enable --now myclash.service; then
		echo "提示: systemctl --user enable --now 失败时，请重新登录或 SSH 后再执行 myclash service start；无会话机器可: sudo loginctl enable-linger $(id -un)" >&2
	fi
}

#############################################






cat "${MYCLASH_ROOT_PWD}/scripts/tools/logo.txt"
mcs_print_root_install_notice
myclashinfo_welcome
read -n 1 -s -r -p "Press any key to continue..." key
echo
mkvenv || failed_and_exit "虚拟环境创建失败"
download_clash

rm -rf "${MYCLASH_ROOT_PWD}/mcs"
install_mcs

echo "设置 shell 环境变量（写入 ~/.bashrc）"
"${MYCLASH_ROOT_PWD}/venv/bin/python3" "${MYCLASH_ROOT_PWD}/scripts/runtime/gen_placehold_fill_file.py" \
	"${MYCLASH_ROOT_PWD}/install/templates/env_prefix.txt" \
	"${MYCLASH_ROOT_PWD}/tmp/env_prefix.txt" \
	"${MYCLASH_ROOT_PWD}"

RC="${HOME}/.bashrc"
touch "$RC"
start_line=$(grep -nF 'clash_env_set_start' "$RC" 2>/dev/null | head -1 | cut -d: -f1 || true)
end_line=$(grep -nF 'clash_env_set_end' "$RC" 2>/dev/null | head -1 | cut -d: -f1 || true)
if [ -n "${start_line}" ] && [ -n "${end_line}" ]; then
	sed -i "${start_line},${end_line}d" "$RC"
fi
cat "${MYCLASH_ROOT_PWD}/tmp/env_prefix.txt" >>"$RC"

echo_guider_after_success
