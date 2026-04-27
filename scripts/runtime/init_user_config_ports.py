#!/usr/bin/env python3
"""Initialize random available ports in user_config.yaml."""

from __future__ import annotations

import random
import socket
import sys
from pathlib import Path

import yaml


def _normalize_range(value: object, default: tuple[int, int]) -> tuple[int, int]:
    if isinstance(value, (list, tuple)) and len(value) == 2:
        try:
            lo = int(value[0])
            hi = int(value[1])
        except (TypeError, ValueError):
            lo, hi = default
    else:
        lo, hi = default
    lo = max(1, min(65535, lo))
    hi = max(1, min(65535, hi))
    if lo > hi:
        lo, hi = hi, lo
    return lo, hi


def _can_bind(host: str, port: int) -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((host, port))
            return True
    except OSError:
        return False


def _pick_random_available(
    lo: int,
    hi: int,
    *,
    host: str,
    exclude: set[int] | None = None,
) -> int:
    pool = list(range(lo, hi + 1))
    random.shuffle(pool)
    banned = exclude or set()
    for p in pool:
        if p in banned:
            continue
        if _can_bind(host, p):
            return p
    raise RuntimeError(f"no available port in range {lo}-{hi}")


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: init_user_config_ports.py <user_config.yaml>", file=sys.stderr)
        return 2

    cfg_path = Path(sys.argv[1]).resolve()
    if not cfg_path.is_file():
        print(f"config not found: {cfg_path}", file=sys.stderr)
        return 1

    doc = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    if not isinstance(doc, dict):
        print("invalid yaml root, expected mapping", file=sys.stderr)
        return 1

    proxy_lo, proxy_hi = _normalize_range(doc.get("proxy_port_range"), (37890, 37990))
    ext_lo, ext_hi = _normalize_range(doc.get("clash_external_port_range"), (39090, 39190))

    http_port = _pick_random_available(proxy_lo, proxy_hi, host="0.0.0.0")
    socks_port = _pick_random_available(
        proxy_lo,
        proxy_hi,
        host="0.0.0.0",
        exclude={http_port},
    )
    ext_port = _pick_random_available(ext_lo, ext_hi, host="127.0.0.1")

    doc["port"] = int(http_port)
    doc["socks-port"] = int(socks_port)
    doc["external-controller"] = f"127.0.0.1:{int(ext_port)}"

    cfg_path.write_text(
        yaml.safe_dump(doc, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

