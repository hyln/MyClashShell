#!/usr/bin/env bash
# 移除旧版 / 当前 MyClashShell 在本机留下的「安装痕迹」（用户级 systemd、shell 片段、
# 仓库下的 clash|mcs|cache、旧 tmp/ 与 cache 内生成物、根目录 app.log）。
#
# 默认保留：venv/、user_config.yaml、整个仓库目录。
# 系统级（/etc/systemd、/etc/bash.bashrc）请另行执行: sudo ./install/uninstall_root.sh
#
# 用法（在仓库内）:
#   ./install/remove_legacy_myclash.sh           # 实际删除
#   ./install/remove_legacy_myclash.sh --dry-run # 仅打印将执行的操作
#   ./install/remove_legacy_myclash.sh --with-venv  # 同时删除仓库内 venv/
#
# 环境变量 MYCLASH_ROOT_PWD 可显式指定仓库根（未设置时按本脚本位置推断）。

set -u

DRY_RUN=0
WITH_VENV=0
for a in "$@"; do
	case "$a" in
	--dry-run) DRY_RUN=1 ;;
	--with-venv) WITH_VENV=1 ;;
	-h|--help)
		sed -n '1,20p' "$0"
		exit 0
		;;
	*)
		echo "未知参数: $a（支持 --dry-run --with-venv）" >&2
		exit 2
		;;
	esac
done

rm_rf() {
	local p=$1
	if [ ! -e "$p" ]; then
		return 0
	fi
	if [ "$DRY_RUN" -eq 1 ]; then
		echo "[dry-run] rm -rf $p"
	else
		rm -rf "$p"
		echo "已删除: $p"
	fi
}

rm_f() {
	local p=$1
	if [ ! -f "$p" ] && [ ! -L "$p" ]; then
		return 0
	fi
	if [ "$DRY_RUN" -eq 1 ]; then
		echo "[dry-run] rm -f $p"
	else
		rm -f "$p"
		echo "已删除: $p"
	fi
}

strip_clash_env_block() {
	local file=$1
	[ -f "$file" ] || return 0
	local start_line end_line
	start_line=$(grep -nF 'clash_env_set_start' "$file" 2>/dev/null | head -1 | cut -d: -f1 || true)
	end_line=$(grep -nF 'clash_env_set_end' "$file" 2>/dev/null | head -1 | cut -d: -f1 || true)
	if [ -n "${start_line}" ] && [ -n "${end_line}" ]; then
		if [ "$DRY_RUN" -eq 1 ]; then
			echo "[dry-run] sed -i '${start_line},${end_line}d' $file  # clash_env 块"
		else
			sed -i "${start_line},${end_line}d" "$file"
			echo "已从 $file 移除 clash_env_set_start … clash_env_set_end 块"
		fi
	else
		echo "（无 clash_env 标记块）$file"
	fi
}

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
if [ -n "${MYCLASH_ROOT_PWD:-}" ]; then
	MYCLASH_ROOT_PWD=$(realpath "${MYCLASH_ROOT_PWD}")
else
	MYCLASH_ROOT_PWD=$(realpath "${SCRIPT_DIR}/..")
fi
export MYCLASH_ROOT_PWD

echo "仓库根: ${MYCLASH_ROOT_PWD}"
if [ "$DRY_RUN" -eq 1 ]; then
	echo "模式: --dry-run（不写入）"
fi

echo "=== 用户级 systemd：停止并移除 myclash.service ==="
if [ "$DRY_RUN" -eq 1 ]; then
	echo "[dry-run] systemctl --user stop/disable myclash.service; rm ~/.config/systemd/user/myclash.service"
else
	systemctl --user stop myclash.service 2>/dev/null || true
	systemctl --user disable myclash.service 2>/dev/null || true
	rm -f "${HOME}/.config/systemd/user/myclash.service"
	systemctl --user daemon-reload 2>/dev/null || true
	echo "用户级 myclash.service 已处理"
fi

echo "=== ~/.bashrc：移除 MyClash 环境片段 ==="
strip_clash_env_block "${HOME}/.bashrc"

echo "=== 仓库内运行时目录与旧版 clash/ ==="
rm_rf "${MYCLASH_ROOT_PWD}/clash"
rm_rf "${MYCLASH_ROOT_PWD}/mcs"
rm_rf "${MYCLASH_ROOT_PWD}/cache"
rm_f "${MYCLASH_ROOT_PWD}/tmp/myclash.service"
rm_f "${MYCLASH_ROOT_PWD}/cache/myclash.service.gen"
rm_f "${MYCLASH_ROOT_PWD}/tmp/env_prefix.txt"
rm_f "${MYCLASH_ROOT_PWD}/cache/env_prefix.txt"
rm_f "${MYCLASH_ROOT_PWD}/tmp/slave_http_server.pid"
rm_f "${MYCLASH_ROOT_PWD}/tmp/slave_http_server.log"
rm_f "${MYCLASH_ROOT_PWD}/app.log"

if [ "$WITH_VENV" -eq 1 ]; then
	echo "=== 按请求删除 venv/ ==="
	rm_rf "${MYCLASH_ROOT_PWD}/venv"
else
	echo "（保留 venv/；若需一并删除请加 --with-venv）"
fi

echo ""
echo "完成。若曾安装系统级单元或写入 /etc/bash.bashrc，请执行:"
echo "  sudo ${MYCLASH_ROOT_PWD}/install/uninstall_root.sh"
echo "删除整个仓库请自行: rm -rf ${MYCLASH_ROOT_PWD}"
echo "新开 shell 或: source ~/.bashrc"
