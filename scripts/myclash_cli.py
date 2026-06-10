#!/usr/bin/env python3
"""Unified CLI entry for myclash.

Shell wrappers should delegate service/log/share/change_subscribe/docker-proxy/status
to this entry, while keeping only ui/window/shell in bash for interactive state.
"""

from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
from pathlib import Path
from textwrap import dedent

import requests
import yaml

_repo = Path(__file__).resolve().parents[1]
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))

from scripts.lib.mcs_api_client import (  # noqa: E402
    get_kernel_status,
    mcs_control_base_url,
    request_kernel_reload,
    request_sync_meta,
)
from scripts.lib.paths import current_sub_txt_path, repo_root_from_env  # noqa: E402


def _root() -> Path:
    root = repo_root_from_env()
    if root is not None:
        return root
    return _repo


def _python(root: Path) -> Path:
    return root / "venv" / "bin" / "python3"


def _load_user_config(root: Path) -> dict:
    uc = root / "user_config.yaml"
    if not uc.is_file():
        return {}
    try:
        doc = yaml.safe_load(uc.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}
    return doc if isinstance(doc, dict) else {}


def _read_version(root: Path) -> str:
    p = root / "install" / "version"
    try:
        return p.read_text(encoding="utf-8").strip() or "?"
    except OSError:
        return "?"


def _read_current_sub(root: Path) -> str:
    p = current_sub_txt_path(root)
    try:
        return p.read_text(encoding="utf-8").strip() or "—"
    except OSError:
        return "—"


def _proxy_test(root: Path, port: int) -> bool:
    test_url = os.environ.get("MYCLASH_TUI_TEST_URL", "https://www.gstatic.com/generate_204")
    proxies = {
        "http": f"http://127.0.0.1:{port}",
        "https": f"http://127.0.0.1:{port}",
    }
    try:
        r = requests.get(test_url, proxies=proxies, timeout=4)
        return r.status_code < 400
    except Exception:  # noqa: BLE001
        return False


def _allow_lan_text(doc: dict) -> str:
    v = doc.get("allow-lan")
    if isinstance(v, bool):
        return "已开启" if v else "已关闭"
    if isinstance(v, (int, float)):
        return "已开启" if bool(v) else "已关闭"
    if isinstance(v, str):
        s = v.strip().lower()
        if s in ("true", "1", "yes", "on"):
            return "已开启"
        if s in ("false", "0", "no", "off"):
            return "已关闭"
    return "未知"


def _ansi(text: str, code: str) -> str:
    return f"\033[{code}m{text}\033[0m"


def _green(text: str) -> str:
    return _ansi(text, "0;32")


def _red(text: str) -> str:
    return _ansi(text, "0;31")


def _dim(text: str) -> str:
    return _ansi(text, "2")


def _config_value(doc: dict, key: str, default: str = "") -> str:
    v = doc.get(key, default)
    if isinstance(v, bool):
        return "ON" if v else "OFF"
    if v is None:
        return default
    return str(v)


def _config_port(doc: dict, key: str, default: int) -> int:
    v = doc.get(key, default)
    if isinstance(v, int) and 1 <= v <= 65535:
        return v
    if isinstance(v, str):
        s = v.strip()
        if s.isdigit():
            p = int(s)
            if 1 <= p <= 65535:
                return p
    return default


def print_status() -> int:
    root = _root()
    doc = _load_user_config(root)
    port = 7890
    socks = 7891
    if isinstance(doc.get("port"), int):
        port = doc["port"]
    if isinstance(doc.get("socks-port"), int):
        socks = doc["socks-port"]

    status, _err = get_kernel_status(timeout=3.0, root=root)
    alive = bool(isinstance(status, dict) and status.get("alive"))
    pid = status.get("pid") if isinstance(status, dict) else None
    backend_running = status.get("backend_running") if isinstance(status, dict) else None
    backend_from_config = status.get("backend_from_config") if isinstance(status, dict) else None
    current_sub = _read_current_sub(root)
    version = _read_version(root)
    lan = _allow_lan_text(doc)
    proxy_ok = _proxy_test(root, port)
    api = mcs_control_base_url(root)

    edge = "  ╭──────────────────────────────────────────────────╮"
    mid = "  ├──────────────────────────────────────────────────┤"
    bot = "  ╰──────────────────────────────────────────────────╯"
    running_txt = _green("正常") if alive else _red("停止")
    conn_txt = _green("正常") if proxy_ok else _red("异常")
    lan_txt = _green(lan) if lan == "已开启" else _red(lan) if lan == "已关闭" else lan
    backend_line = f"{backend_from_config or '—'}  pid {pid or '—'}"
    print()
    print(edge)
    print(f"  │ MyClash  {_dim(version)}")
    print(mid)
    print(f"  │ 当前订阅        {current_sub}")
    print(f"  │ HTTP 端口       {port}")
    print(f"  │ SOCKS 端口      {socks}")
    print(f"  │ 允许局域网      {lan_txt}")
    print(f"  │ API             {api}")
    print(f"  │ 后端/PID        {backend_line}")
    print(f"  │ 运行中          {running_txt}")
    print(f"  │ 连通性          {conn_txt}")
    print(bot)
    print()
    return 0


def _run(cmd: list[str], *, env: dict[str, str] | None = None) -> int:
    proc = subprocess.run(cmd, env=env)
    return proc.returncode


def _systemctl_user(*args: str) -> int:
    return _run(["systemctl", "--user", *args])


def _journalctl_user(*args: str) -> int:
    return _run(["journalctl", "--user", *args])


def _shell_script(root: Path, rel: str, *args: str) -> int:
    return _run(["bash", str(root / rel), *args], env={**os.environ, "MYCLASH_ROOT_PWD": str(root)})


def _python_script(root: Path, rel: str, *args: str) -> int:
    py = _python(root)
    return _run([str(py), str(root / rel), *args], env={**os.environ, "MYCLASH_ROOT_PWD": str(root)})


def _cmd_service(root: Path, args: list[str]) -> int:
    if not args:
        return print_status()
    sub = args[0]
    rest = args[1:]
    if sub == "start":
        return _systemctl_user("start", "myclash.service")
    if sub == "stop":
        return _systemctl_user("stop", "myclash.service")
    if sub == "restart":
        return _systemctl_user("restart", "myclash.service")
    if sub == "status":
        return _systemctl_user("status", "myclash.service")
    if sub == "get_logs":
        return _journalctl_user("-u", "myclash.service", "-n", "200", "-f", *rest)
    if sub == "update_subscribe":
        return _python_script(root, "scripts/runtime/update_proxy_config.py", *rest)
    if sub == "reload_kernel":
        logging.basicConfig(level=logging.INFO, format="%(message)s")
        ok = request_kernel_reload(logger=logging.getLogger("myclash_cli"), root=root)
        return 0 if ok else 1
    print(f"unknown service subcommand: {sub}", file=sys.stderr)
    return 2


def _cmd_log(root: Path, args: list[str]) -> int:
    return _journalctl_user("-u", "myclash.service", "-n", "200", "-f", *args)


def _cmd_share(root: Path, args: list[str]) -> int:
    if args and args[0] not in ("env", "export"):
        print("用法: myclash share [env|export]", file=sys.stderr)
        return 2
    doc = _load_user_config(root)
    http = int(doc.get("port") or 7890)
    socks = int(doc.get("socks-port") or 7891)
    host = os.environ.get("MYCLASH_SHARE_HOST", "").strip() or "127.0.0.1"
    print("# 直接复制到当前 shell，或手动按需修改后再执行")
    print(f"export http_proxy=http://{host}:{http} https_proxy=http://{host}:{http} ftp_proxy=http://{host}:{http}")
    print(f"export all_proxy=socks5h://{host}:{socks}")
    print("export no_proxy=127.0.0.1,localhost")
    print(f"export HTTP_PROXY=http://{host}:{http} HTTPS_PROXY=http://{host}:{http} FTP_PROXY=http://{host}:{http}")
    print(f"export ALL_PROXY=socks5h://{host}:{socks}")
    print("export NO_PROXY=127.0.0.1,localhost")
    return 0


def _cmd_change_subscribe(root: Path, args: list[str]) -> int:
    return _python_script(root, "scripts/runtime/change_sub.py", *args)


def _cmd_docker_proxy(root: Path, args: list[str]) -> int:
    if len(args) == 1 and args[0] == "update":
        return _shell_script(root, "scripts/tools/myclash_docker_proxy_update.sh")
    print("用法: myclash docker-proxy update", file=sys.stderr)
    return 2


def _cmd_config(root: Path, args: list[str]) -> int:
    def print_config_help() -> None:
        print(
            dedent(
                """
                myclash config <命令>

                  edit    打开 user_config.yaml 编辑器
                  show    显示当前 user_config.yaml
                """
            ).strip()
        )

    if not args:
        print_config_help()
        return 2

    sub = args[0]
    rest = args[1:]
    if sub in ("-h", "--help", "help"):
        if rest:
            print("用法: myclash config help", file=sys.stderr)
            return 2
        print_config_help()
        return 0

    if sub == "edit":
        if rest:
            print("用法: myclash config edit", file=sys.stderr)
            return 2
        env = {**os.environ, "MYCLASH_ROOT_PWD": str(root)}
        return _run([str(_python(root)), "-m", "scripts.tui.app_text"], env=env)

    if sub == "show":
        if rest:
            print("用法: myclash config show", file=sys.stderr)
            return 2
        config_path = root / "user_config.yaml"
        try:
            sys.stdout.write(config_path.read_text(encoding="utf-8"))
        except OSError as exc:
            print(f"myclash config show: 无法读取 {config_path}: {exc}", file=sys.stderr)
            return 1
        return 0

    print(f"未知 config 子命令: {sub}", file=sys.stderr)
    print("用法: myclash config <edit|show>", file=sys.stderr)
    return 2


def _cmd_help() -> int:
    print(
        dedent(
            """
            myclash <命令> [参数 …]

            服务与日志
              service <子命令>  start | stop | restart | status | get_logs
                                | update_subscribe | reload_kernel
              log [journalctl…] 跟踪 myclash.service（mcs + 内核）

            代理
              shell on|off         当前 shell（默认见 user_config.shell_proxy_default）
              window on|off        GNOME 等：系统 HTTP/SOCKS

            其它
              change_subscribe <名>
              share [env|export]   输出可 eval 的 export（局域网 Master IP；默认 hostname -I 首个 IPv4）
              docker-proxy update
              config <子命令>      edit | show

            提示
              · update_subscribe / change_subscribe：会先 shell off，避免经代理拉配置失败；结束后再 shell on
              · reload_kernel：只重启 clash/v2ray 子进程
              · API 端口见 cache/current_mcs_port.txt；池见 user_config.mcs_api_port_range
              · get_logs / log：journalctl --user；无登录会话：loginctl enable-linger <用户>
              · 无子命令：打印状态卡片
            """
        ).strip()
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("cmd", nargs="?")
    parser.add_argument("args", nargs=argparse.REMAINDER)
    ns = parser.parse_args(argv)

    root = _root()
    cmd = ns.cmd
    args = ns.args
    if args and args[0] == "--":
        args = args[1:]

    if cmd is None:
        return print_status()
    if cmd in ("-h", "--help", "help"):
        return _cmd_help()
    if cmd == "service":
        return _cmd_service(root, args)
    if cmd == "log":
        return _cmd_log(root, args)
    if cmd == "share":
        return _cmd_share(root, args)
    if cmd == "change_subscribe":
        return _cmd_change_subscribe(root, args)
    if cmd == "docker-proxy":
        return _cmd_docker_proxy(root, args)
    if cmd == "config":
        return _cmd_config(root, args)
    print(f"unknown command: {cmd}", file=sys.stderr)
    print("use: myclash help", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
