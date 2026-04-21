#!/bin/bash
set -euo pipefail
ROOT="${MYCLASH_ROOT_PWD:?MYCLASH_ROOT_PWD is not set}"
CFG_DIR="${ROOT}/clash/configs"
CORE="clash"
if [[ -f "${ROOT}/tmp/current_core.txt" ]]; then
  read -r c < "${ROOT}/tmp/current_core.txt" || true
  if [[ "$c" == "mihomo" ]]; then
    CORE="mihomo"
  fi
fi
if [[ "$CORE" == "mihomo" && -x "${ROOT}/clash/mihomo" ]]; then
  exec "${ROOT}/clash/mihomo" -d "${CFG_DIR}"
fi
exec "${ROOT}/clash/clash" -d "${CFG_DIR}"
