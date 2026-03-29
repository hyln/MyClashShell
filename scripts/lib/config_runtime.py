"""Clash runtime /configs PATCH payload construction (no Textual)."""

from __future__ import annotations

from typing import Any


def runtime_config_patch_payload(
    *,
    port: int,
    socks_port: int,
    mixed_port: int,
    redir_port: int,
    tproxy_port: int,
    mode: str,
    log_level: str,
    allow_lan: bool,
    ipv6: bool,
) -> dict[str, Any]:
    return {
        "port": port,
        "socks-port": socks_port,
        "mixed-port": mixed_port,
        "redir-port": redir_port,
        "tproxy-port": tproxy_port,
        "mode": mode,
        "log-level": log_level,
        "allow-lan": allow_lan,
        "ipv6": ipv6,
    }
