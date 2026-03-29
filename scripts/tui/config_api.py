"""Normalize GET /configs payloads across Clash variants."""

from __future__ import annotations

from typing import Any


def _cfg_int(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, bool):
        return int(value)
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def normalize_runtime_config(raw: Any) -> dict[str, Any]:
    """统一不同内核/版本的 GET /configs 结构（扁平或包在 config 里）。"""
    if not isinstance(raw, dict):
        return {}
    data = raw
    for wrap in ("config", "Config", "data", "Data"):
        inner = data.get(wrap)
        if isinstance(inner, dict) and any(
            k in inner for k in ("port", "mixed-port", "mode", "log-level", "allow-lan")
        ):
            data = dict(inner)
            break
    return data
