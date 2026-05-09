#!/usr/bin/env python3
"""Read a handful of `user_config.yaml` values for shell/runtime helpers.

This is intentionally not exposed as a public myclash subcommand.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

from scripts.lib.paths import repo_root_from_env


def _root() -> Path:
    root = repo_root_from_env()
    if root is not None:
        return root
    return Path(__file__).resolve().parents[2]


def _read_doc(root: Path) -> dict:
    p = root / "user_config.yaml"
    try:
        doc = yaml.safe_load(p.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return doc if isinstance(doc, dict) else {}


def _port(v: object, default: int) -> int:
    if isinstance(v, int) and 1 <= v <= 65535:
        return v
    if isinstance(v, str) and v.strip().isdigit():
        p = int(v.strip())
        if 1 <= p <= 65535:
            return p
    return default


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print("use: read_config_value.py <key>", file=sys.stderr)
        return 2
    key = args[0]
    doc = _read_doc(_root())
    if key == "port":
        print(_port(doc.get("port"), 7890))
        return 0
    if key == "socks-port":
        print(_port(doc.get("socks-port"), 7891))
        return 0
    if key == "shell_proxy_default":
        v = str(doc.get("shell_proxy_default") or "OFF").strip().upper()
        print(v if v in ("ON", "OFF") else "OFF")
        return 0
    print(f"unknown key: {key}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
