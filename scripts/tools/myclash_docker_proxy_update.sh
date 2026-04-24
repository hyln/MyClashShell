#!/usr/bin/env bash
# 为 dockerd 写入 systemd drop-in（HTTP/HTTPS 指向本机 Clash HTTP 端口），并 reload + restart。
# 自动区分 rootless（systemctl --user）与 rootful（sudo systemctl）。
set -euo pipefail

: "${MYCLASH_ROOT_PWD:?MYCLASH_ROOT_PWD 未设置}"

PY="${MYCLASH_ROOT_PWD}/venv/bin/python3"
READ_YAML="${MYCLASH_ROOT_PWD}/scripts/tools/read_yaml.py"

if ! command -v docker >/dev/null 2>&1; then
	echo "myclash docker-proxy update: 未找到 docker 命令" >&2
	exit 1
fi
if ! command -v systemctl >/dev/null 2>&1; then
	echo "myclash docker-proxy update: 未找到 systemctl（需 systemd）" >&2
	exit 1
fi

_http_port() {
	local p=7890
	local _p
	_p=$("$PY" "$READ_YAML" port 2>/dev/null || true)
	if [[ "$_p" =~ ^[0-9]+$ ]]; then
		p="$_p"
	fi
	echo "$p"
}

HP=$(_http_port)
PROXY_URL="http://127.0.0.1:${HP}/"
NO_PROXY_VAL="${MYCLASH_DOCKER_NO_PROXY:-localhost,127.0.0.1,::1}"

write_dropin_body() {
	cat <<EOF
[Service]
Environment="HTTP_PROXY=${PROXY_URL}"
Environment="HTTPS_PROXY=${PROXY_URL}"
Environment="NO_PROXY=${NO_PROXY_VAL}"
EOF
}

user_unit_loaded() {
	local s
	s=$(systemctl --user show docker.service -p LoadState --value 2>/dev/null || echo "")
	[[ "$s" == "loaded" ]]
}

system_unit_loaded() {
	local s
	s=$(systemctl show docker.service -p LoadState --value 2>/dev/null || echo "")
	[[ "$s" == "loaded" ]]
}

docker_info_rootless() {
	local line
	line=$(docker info 2>/dev/null | grep -i '^[[:space:]]*rootless:' | head -n1 || true)
	[[ "$line" =~ [Tt]rue ]]
}

docker_host_suggests_rootless() {
	case "${DOCKER_HOST:-}" in
	*"/run/user/"*) return 0 ;;
	esac
	local rt="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
	[[ -n "${DOCKER_HOST:-}" ]] && [[ "$DOCKER_HOST" == *"$rt"* ]] && return 0
	return 1
}

pick_target() {
	case "${MYCLASH_DOCKER_PROXY_TARGET:-}" in
	user | rootless)
		echo user
		return
		;;
	system | rootful)
		echo system
		return
		;;
	esac

	if docker info >/dev/null 2>&1; then
		if docker_info_rootless; then
			echo user
			return
		fi
		echo system
		return
	fi

	if docker_host_suggests_rootless; then
		echo user
		return
	fi

	if user_unit_loaded && ! system_unit_loaded; then
		echo user
		return
	fi
	if system_unit_loaded && ! user_unit_loaded; then
		echo system
		return
	fi
	if user_unit_loaded && system_unit_loaded; then
		echo >&2 "提示: 无法连接 docker daemon，且检测到用户级与系统级 docker.service 均存在。"
		echo >&2 "      默认写入系统级（需 sudo）。若实际为 rootless，请设置:"
		echo >&2 "      export MYCLASH_DOCKER_PROXY_TARGET=user"
	fi
	echo system
}

TARGET=$(pick_target)
DROPIN_NAME="myclash-proxy.conf"

if [[ "$TARGET" == "user" ]]; then
	DROP_DIR="${HOME}/.config/systemd/user/docker.service.d"
	mkdir -p "$DROP_DIR"
	write_dropin_body >"${DROP_DIR}/${DROPIN_NAME}"
	echo "已写入 ${DROP_DIR}/${DROPIN_NAME}（HTTP/HTTPS → ${PROXY_URL}）"
	systemctl --user daemon-reload
	if systemctl --user restart docker 2>/dev/null; then
		echo "已执行: systemctl --user daemon-reload && systemctl --user restart docker"
	else
		echo "已 daemon-reload；若 docker 用户服务未运行，请稍后执行: systemctl --user restart docker" >&2
	fi
else
	SYS_DIR="/etc/systemd/system/docker.service.d"
	echo "将使用 sudo 写入 ${SYS_DIR}/${DROPIN_NAME}（目标: 系统 dockerd）"
	sudo mkdir -p "$SYS_DIR"
	write_dropin_body | sudo tee "${SYS_DIR}/${DROPIN_NAME}" >/dev/null
	sudo systemctl daemon-reload
	sudo systemctl restart docker
	echo "已执行: sudo systemctl daemon-reload && sudo systemctl restart docker"
fi
