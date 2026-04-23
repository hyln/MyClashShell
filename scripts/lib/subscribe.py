"""Load/save user_config.yaml 中的 subscribes / default_subscribe。

subscribes 每项必须为映射 ``{ url, backend }``，``backend`` 为 ``clash`` 或 ``v2ray``（不再支持旧版「值直接为 URL 字符串」）。
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


def parse_subscribes(raw: Any) -> dict[str, dict[str, str]]:
    """解析 subscribes：name -> { url, backend }。顺序与 YAML 中键顺序一致（Python 3.7+ dict 保序）。"""
    if not isinstance(raw, MutableMapping):
        return {}
    out: dict[str, dict[str, str]] = {}
    for k, v in raw.items():
        name = str(k).strip()
        if not name:
            continue
        if not isinstance(v, dict):
            raise ValueError(
                f'subscribes["{name}"] 须为 {{ url, backend }} 映射（clash|v2ray），不再支持旧版「值为 URL 字符串」'
            )
        url_s = str(v.get("url") or "").strip()
        be = str(v.get("backend") or "").strip().lower()
        if be not in ("clash", "v2ray"):
            raise ValueError(f'subscribes["{name}"].backend 须为 clash 或 v2ray，当前: {v.get("backend")!r}')
        if be == "clash" and not is_valid_subscribe_url(url_s):
            raise ValueError(f'subscribes["{name}"].url 对 clash 后端须为有效订阅 URL')
        if be == "v2ray" and url_s and not is_valid_subscribe_url(url_s):
            raise ValueError(f'subscribes["{name}"].url 若填写则须为有效 URL')
        out[name] = {"url": url_s, "backend": be}
    return out


def resolve_default_subscribe_name(
    subs: dict[str, dict[str, str]],
    default_sub: Any,
) -> str:
    """与 update_proxy_config 一致：DEFAULT 或缺省/无效名 -> 第一个订阅名。"""
    names = list(subs.keys())
    if not names:
        return ""
    d = str(default_sub if default_sub is not None else "DEFAULT").strip()
    if d == "DEFAULT" or d not in subs:
        return names[0]
    return d


def set_document_subscribes(
    doc: MutableMapping[str, Any],
    subscribes: dict[str, dict[str, str]],
    key_order: list[str] | None = None,
) -> None:
    """将 subscribes 写回文档（值为含 url、backend 的映射）。"""
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
            raw[k] = dict(v)
        return
    cm = CommentedMap()
    for k, v in ordered.items():
        cm[k] = dict(v)
    doc["subscribes"] = cm


def save_user_config_dict(path: Path, data: MutableMapping[str, Any]) -> None:
    y = _yaml_roundtrip()
    with path.open("w", encoding="utf-8") as f:
        y.dump(data, f)


def persist_default_subscribe(path: Path, subscribe_name: str) -> None:
    """将 ``default_subscribe`` 设为 ``subscribe_name``（保留 YAML 注释与格式）。"""
    doc = load_user_config_dict(path)
    doc["default_subscribe"] = str(subscribe_name).strip()
    save_user_config_dict(path, doc)
