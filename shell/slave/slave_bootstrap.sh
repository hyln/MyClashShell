#!/usr/bin/env bash
# Install slave proxy helpers (no Clash / no myclash.service). Run as root.
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "Please run as root: sudo bash $0 <MASTER_IP> [HTTP_PORT]"
  exit 1
fi

MASTER_IP="${1:-}"
HTTP_PORT="${2:-7890}"
if [[ -z "$MASTER_IP" ]]; then
  echo "Usage: sudo bash $0 <MASTER_IP> [HTTP_PORT]"
  exit 1
fi

if ! grep -q 'Defaults env_keep += "http_proxy https_proxy ftp_proxy no_proxy"' /etc/sudoers 2>/dev/null; then
  cp /etc/sudoers /etc/sudoers.bak.myclash_slave.$(date +%s)
  echo 'Defaults env_keep += "http_proxy https_proxy ftp_proxy no_proxy"' >> /etc/sudoers
  echo "Appended proxy env_keep to /etc/sudoers (backup created)."
else
  echo "sudoers env_keep already present, skip."
fi

install -d /etc/myclash-slave
cat > /etc/myclash-slave/slave.bashrc << EOF
export MYCLASH_SLAVE_PROXY_HOST="${MASTER_IP}"
export MYCLASH_SLAVE_PROXY_PORT="${HTTP_PORT}"

myslave() {
  case "\${1:-}" in
  shell)
    case "\${2:-}" in
    on)
      export http_proxy="http://\${MYCLASH_SLAVE_PROXY_HOST}:\${MYCLASH_SLAVE_PROXY_PORT}"
      export https_proxy="http://\${MYCLASH_SLAVE_PROXY_HOST}:\${MYCLASH_SLAVE_PROXY_PORT}"
      echo "myslave: proxy on -> \${http_proxy}"
      ;;
    off)
      unset http_proxy https_proxy
      echo "myslave: proxy off"
      ;;
    *)
      echo "Usage: myslave shell on|off"
      ;;
    esac
    ;;
  help|"")
    echo "myslave shell on|off  — use Master's HTTP proxy (\${MYCLASH_SLAVE_PROXY_HOST}:\${MYCLASH_SLAVE_PROXY_PORT})"
    ;;
  *)
    echo "Unknown command; try: myslave help"
    ;;
  esac
}
EOF
chmod 644 /etc/myclash-slave/slave.bashrc

MARK_START="# myclash_slave_env_set_start"
MARK_END="# myclash_slave_env_set_end"
if grep -qF "$MARK_START" /etc/bash.bashrc 2>/dev/null; then
  echo "/etc/bash.bashrc already sources myclash-slave, skip."
else
  {
    echo ""
    echo "$MARK_START"
    echo "if [ -f /etc/myclash-slave/slave.bashrc ]; then"
    echo "  source /etc/myclash-slave/slave.bashrc"
    echo "fi"
    echo "$MARK_END"
  } >> /etc/bash.bashrc
  echo "Appended myclash-slave block to /etc/bash.bashrc"
fi

echo "Done. Open a new shell or: source /etc/myclash-slave/slave.bashrc"
echo "Then: myslave shell on"
