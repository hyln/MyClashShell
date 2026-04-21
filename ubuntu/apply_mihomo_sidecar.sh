#!/bin/bash
# 已有安装目录时：下载 Mihomo、安装 launch-core、刷新 clash.service（不删除 clash 配置）
# 用法: sudo MYCLASH_ROOT_PWD=/path/to/MyClashShell bash ubuntu/apply_mihomo_sidecar.sh
# 未设置 MYCLASH_ROOT_PWD 时，默认使用「本脚本所在仓库」的根目录。
set -euo pipefail
if (( EUID != 0 )); then
  echo "请使用 root 执行，例如: sudo MYCLASH_ROOT_PWD=/opt/MyClashShell bash ubuntu/apply_mihomo_sidecar.sh"
  exit 1
fi
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "${SCRIPT_DIR}/.." && pwd)
ROOT="${MYCLASH_ROOT_PWD:-$REPO_ROOT}"
export MYCLASH_ROOT_PWD="$ROOT"
mkdir -p "${ROOT}/tmp" "${ROOT}/clash/configs"
MIHOMO_TAG="v1.19.24"
arch=$(uname -m)
if [ "$arch" = x86_64 ]; then
  mihomo_asset="mihomo-linux-amd64-compatible-${MIHOMO_TAG}.gz"
elif [ "$arch" = aarch64 ]; then
  mihomo_asset="mihomo-linux-arm64-${MIHOMO_TAG}.gz"
else
  echo "未支持的架构: $arch"
  exit 1
fi
mihomo_url="https://github.com/MetaCubeX/mihomo/releases/download/${MIHOMO_TAG}/${mihomo_asset}"
echo "下载 Mihomo -> ${ROOT}/tmp/mihomo.gz"
wget "${mihomo_url}" -O "${ROOT}/tmp/mihomo.gz"
gunzip -c "${ROOT}/tmp/mihomo.gz" > "${ROOT}/clash/mihomo"
chmod +x "${ROOT}/clash/mihomo"
cp "${REPO_ROOT}/ubuntu/template/launch-core.sh" "${ROOT}/clash/launch-core.sh"
chmod +x "${ROOT}/clash/launch-core.sh"
"${REPO_ROOT}/ubuntu/scripts/gen_placehold_fill_file.py" \
  "${REPO_ROOT}/ubuntu/template/clash.service" \
  "${ROOT}/tmp/clash.service.new" \
  "${ROOT}" "${ROOT}" "${ROOT}"
mv "${ROOT}/tmp/clash.service.new" /etc/systemd/system/clash.service
systemctl daemon-reload
echo "完成。请在 user_config.yaml 中配置 mihomo_subscribes 后执行: systemctl restart clash"
