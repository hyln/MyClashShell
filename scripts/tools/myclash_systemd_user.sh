#!/usr/bin/env bash
# 解析「安装 systemd --user 单元」的目标登录用户（供 install / uninstall 共用）。
# 优先 MYCLASH_INSTALL_USER，其次 sudo 的 SUDO_USER，再 logname；均不可用则为 root。

mcs_resolve_install_user() {
	# 非 root 时为当前用户；root 时为 root（与以 root 执行 install.sh 时一致）
	if [ "$(id -u)" -ne 0 ]; then
		id -un
		return
	fi
	local u="${MYCLASH_INSTALL_USER:-${SUDO_USER:-}}"
	if [ -z "$u" ] || [ "$u" = "root" ]; then
		u=$(logname 2>/dev/null || true)
	fi
	if [ -z "$u" ]; then
		u="root"
	fi
	printf '%s\n' "$u"
}

mcs_user_systemctl() {
	# 用法: mcs_user_systemctl <login> <systemctl 子命令...>
	# 例: mcs_user_systemctl alice --user daemon-reload
	local login="$1"
	shift
	local uid rd
	uid=$(id -u "$login" 2>/dev/null) || return 1
	rd="/run/user/${uid}"
	if [ "$(id -un)" = "$login" ]; then
		env XDG_RUNTIME_DIR="$rd" systemctl "$@"
	else
		sudo -u "$login" env XDG_RUNTIME_DIR="$rd" systemctl "$@"
	fi
}
