"""Zenoh LAN sharing key layout and protocol version."""

from __future__ import annotations

LAN_PROTO_VERSION = 1
ANNOUNCE_GLOB = "myclash/lan/**/announce"


def announce_key(node_id: str) -> str:
    return f"myclash/lan/{node_id}/announce"


def config_query_key(node_id: str) -> str:
    return f"myclash/lan/{node_id}/config"
