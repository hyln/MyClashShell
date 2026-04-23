"""Run: PYTHONPATH=<repo_root> python -m scripts.tui [optional_proxy_group]"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _require_clash_backend_for_tui() -> None:
    """TUI 依赖 Clash 兼容 REST（mihomo）；通过 mcs_manager ``GET /kernel/status`` 确认 backend 为 clash 且进程存活。"""
    if not os.environ.get("MYCLASH_ROOT_PWD", "").strip():
        print("TUI: 未设置 MYCLASH_ROOT_PWD", file=sys.stderr)
        sys.exit(1)
    _repo = Path(__file__).resolve().parents[2]
    if str(_repo) not in sys.path:
        sys.path.insert(0, str(_repo))
    from scripts.lib.mcs_api_client import get_kernel_status, mcs_control_base_url

    st, mcs_err = get_kernel_status()
    if not st:
        print(
            "TUI: 无法从 mcs_manager 读取状态（GET /kernel/status）。"
            "请确认: systemctl --user status myclash.service 为 active；"
            f"地址为 {mcs_control_base_url()}。",
            file=sys.stderr,
        )
        if mcs_err:
            print(f"  详情: {mcs_err}", file=sys.stderr)
        print(
            "  若已设置 MYCLASH_MCS_API_TOKEN，须在环境中 export 同名 Bearer；"
            "若终端开了代理仍失败，可试: myclash shell off",
            file=sys.stderr,
        )
        sys.exit(1)
    want = str(st.get("backend_from_config") or "").strip().lower()
    if want != "clash":
        print(
            f"TUI 仅支持 backend: clash（mihomo 内核）；当前 user_config 默认订阅为 {want!r}（来自 mcs API）。",
            file=sys.stderr,
        )
        sys.exit(2)
    alive = bool(st.get("alive"))
    run = str(st.get("backend_running") or "").strip().lower()
    if not alive or run != "clash":
        print(
            "TUI: clash 槽位（mihomo）未在运行或未就绪（mcs API）。请执行: myclash service start 或 myclash service reload_kernel",
            file=sys.stderr,
        )
        sys.exit(2)


def main() -> None:
    try:
        from textual.app import App  # noqa: F401
    except ImportError:
        print(
            "Textual is required. Install with:\n"
            "  ${MYCLASH_ROOT_PWD}/venv/bin/pip install textual",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        from ruamel.yaml import YAML  # noqa: F401
    except ImportError:
        print(
            "ruamel.yaml is required. Install with:\n"
            "  ${MYCLASH_ROOT_PWD}/venv/bin/pip install ruamel.yaml",
            file=sys.stderr,
        )
        sys.exit(1)

    _require_clash_backend_for_tui()

    from .app import main as run_app

    run_app()


if __name__ == "__main__":
    main()
