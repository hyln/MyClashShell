#!/usr/bin/env python3
"""写入 ``user_config.yaml`` 的 ``v2ray_outbound_tag``，并重写 ``mcs/configs/v2ray.json`` + 请求内核重载。

命令行用法（一般不手写；选节点请用 ``myclash ui``）::

    PYTHONPATH=<repo> python3 scripts/tools/v2ray_use.py <outbound-tag>
    PYTHONPATH=<repo> python3 scripts/tools/v2ray_use.py --clear
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

_repo = Path(__file__).resolve().parents[2]
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))

from scripts.lib.paths import repo_root_from_env  # noqa: E402
from scripts.lib.v2ray_persist import apply_v2ray_outbound_selection  # noqa: E402


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    log = logging.getLogger("v2ray_use")

    ap = argparse.ArgumentParser(description="固定 v2ray 出站节点（user_config: v2ray_outbound_tag）")
    ap.add_argument("--clear", action="store_true", help="清除固定 tag，多节点时恢复随机 balancer")
    ap.add_argument("tag", nargs="?", default=None, help="proxy outbound 的 tag")
    args = ap.parse_args()

    root = repo_root_from_env()
    if root is None:
        print("v2ray_use: 请设置 MYCLASH_ROOT_PWD", file=sys.stderr)
        return 2

    if args.clear and args.tag:
        print("v2ray_use: 不要同时使用 --clear 与 tag", file=sys.stderr)
        return 2
    if not args.clear and not (args.tag and args.tag.strip()):
        ap.print_help()
        return 2

    try:
        ok, msg, _reload_ok = apply_v2ray_outbound_selection(
            root,
            tag=args.tag,
            clear=bool(args.clear),
            logger=log,
        )
    except ValueError as e:
        print(f"v2ray_use: {e}", file=sys.stderr)
        return 2

    print(msg)
    if not ok:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
