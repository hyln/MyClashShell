"""LAN Master–Master discovery (UDP multicast) and config HTTP — no Zenoh."""

from __future__ import annotations

import os

LAN_PROTO_VERSION = 1

# Link-local multicast (same destination as mDNS); use a dedicated UDP port — not 5353.
LAN_MULTICAST_ADDR = "224.0.0.251"


def lan_udp_port() -> int:
    try:
        return int(os.environ.get("MYCLASH_LAN_UDP_PORT", "53287"))
    except ValueError:
        return 53287


def lan_config_http_port() -> int:
    try:
        return int(os.environ.get("MYCLASH_LAN_CONFIG_PORT", "53288"))
    except ValueError:
        return 53288


# GET with query pin= & proto=
LAN_CONFIG_HTTP_PATH = "/myclash/v1/config"
