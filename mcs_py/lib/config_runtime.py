"""Clash runtime /configs PATCH payload construction (no Textual).

端口由磁盘配置决定，不在 TUI 中 PATCH；此处仅包含可安全在运行时切换的项。
"""

from __future__ import annotations

from typing import Any


def runtime_config_patch_payload(
    *,
    mode: str,
    log_level: str,
    allow_lan: bool,
    ipv6: bool,
) -> dict[str, Any]:
    return {
        "mode": mode,
        "log-level": log_level,
        "allow-lan": allow_lan,
        "ipv6": ipv6,
    }
