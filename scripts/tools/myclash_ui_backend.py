#!/usr/bin/env python3
"""供 shell 使用：根据 user_config / mcs API 打印当前默认订阅后端 ``clash`` 或 ``v2ray``（单行，无多余空白）。"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_repo = Path(__file__).resolve().parents[2]
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))


def _backend_from_user_config(root: Path) -> str:
    import yaml

    from scripts.lib.subscribe import parse_subscribes, resolve_default_subscribe_name

    uc = root / "user_config.yaml"
    if not uc.is_file():
        return "clash"
    try:
        doc = yaml.safe_load(uc.read_text(encoding="utf-8"))
    except Exception:
        return "clash"
    if not isinstance(doc, dict):
        return "clash"
    sub_dict = doc.get("subscribes")
    if sub_dict is None:
        return "clash"
    try:
        subs = parse_subscribes(sub_dict)
    except ValueError:
        return "clash"
    eff = resolve_default_subscribe_name(subs, doc.get("default_subscribe"))
    if not eff:
        return "clash"
    be = str(subs.get(eff, {}).get("backend") or "clash").strip().lower()
    return be if be in ("clash", "v2ray") else "clash"


def main() -> int:
    raw = os.environ.get("MYCLASH_ROOT_PWD", "").strip()
    if not raw:
        print("clash", end="")
        return 0
    root = Path(raw).resolve()

    try:
        from scripts.lib.mcs_api_client import get_kernel_status

        st, _ = get_kernel_status(timeout=3.0, root=root)
        if isinstance(st, dict):
            b = str(st.get("backend_from_config") or "").strip().lower()
            if b in ("clash", "v2ray"):
                print(b, end="")
                return 0
    except Exception:
        pass

    print(_backend_from_user_config(root), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
