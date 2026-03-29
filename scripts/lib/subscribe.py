"""Load/save user_config.yaml subscription fields (subscribes, default_subscribe).

Uses ruamel.yaml round-trip mode so comments and layout are preserved when possible.
"""

from __future__ import annotations

import os
import re
from collections.abc import MutableMapping
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap

_URL_RE = re.compile(r"^(https?|ftp)://[^\s/$.?#].[^\s]*$", re.IGNORECASE)


def is_valid_subscribe_url(url: str) -> bool:
    return bool(url and _URL_RE.match(url.strip()) is not None)


def user_config_path() -> Path | None:
    root = os.environ.get("MYCLASH_ROOT_PWD", "").strip()
    if not root:
        return None
    return Path(root) / "user_config.yaml"


def _yaml_roundtrip() -> YAML:
    y = YAML(typ="rt")
    y.preserve_quotes = True
    y.indent(mapping=2, sequence=4, offset=2)
    return y


def load_user_config_dict(path: Path) -> MutableMapping[str, Any]:
    """Load YAML preserving comments; returns a mutable mapping (usually CommentedMap)."""
    if not path.is_file():
        return CommentedMap()
    y = _yaml_roundtrip()
    with path.open(encoding="utf-8") as f:
        data = y.load(f)
    if data is None:
        return CommentedMap()
    if not isinstance(data, MutableMapping):
        return CommentedMap()
    return data


def normalize_subscribes(raw: Any) -> dict[str, str]:
    """Map name -> URL. Key order follows ``raw.items()`` (YAML / ruamel 中的书写顺序)。"""
    if not isinstance(raw, MutableMapping):
        return {}
    out: dict[str, str] = {}
    for k, v in raw.items():
        if v is None:
            continue
        out[str(k).strip()] = str(v).strip()
    return out


def set_document_subscribes(
    doc: MutableMapping[str, Any],
    subscribes: dict[str, str],
    key_order: list[str] | None = None,
) -> None:
    """Update subscribes in place when possible to keep comments/order outside that block.

    ``key_order`` controls YAML key order (must cover all keys in ``subscribes``; missing keys
    are appended at the end). If None, keys are sorted alphabetically (legacy).
    """
    raw = doc.get("subscribes")
    if key_order is None:
        keys = sorted(subscribes.keys())
    else:
        keys = [k for k in key_order if k in subscribes]
        for k in subscribes:
            if k not in keys:
                keys.append(k)
    ordered = {k: subscribes[k] for k in keys}
    if isinstance(raw, CommentedMap):
        raw.clear()
        for k, v in ordered.items():
            raw[k] = v
        return
    cm = CommentedMap()
    for k, v in ordered.items():
        cm[k] = v
    doc["subscribes"] = cm


def save_user_config_dict(path: Path, data: MutableMapping[str, Any]) -> None:
    y = _yaml_roundtrip()
    with path.open("w", encoding="utf-8") as f:
        y.dump(data, f)
