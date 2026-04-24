"""v2ray 固定出站：读写 ``user_config.yaml``、重写 ``mcs/configs/v2ray.json``、请求内核重载。"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import yaml

from scripts.lib.mcs_api_client import request_kernel_reload, wait_kernel_ready
from scripts.lib.paths import download_cache_dir, mcs_configs_dir
from scripts.lib.subscribe import parse_subscribes, resolve_default_subscribe_name
from scripts.lib.v2ray_subscribe import (
    _proxy_outbounds_from_saved_v2ray,
    write_v2ray_json_from_outbounds,
)


def load_user_config_dict(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError(f"未找到 {path}")
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(doc, dict):
        raise ValueError("user_config.yaml 顶层不是映射")
    return doc


def save_user_config_dict(path: Path, doc: dict[str, Any]) -> None:
    path.write_text(
        yaml.safe_dump(doc, allow_unicode=True, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )


def resolve_v2ray_default_profile(root: Path) -> tuple[str, dict[str, Any], Path]:
    """当前默认订阅为 v2ray 时返回 ``(订阅名, user_config 字典, user_config 路径)``。"""
    uc_path = root / "user_config.yaml"
    doc = load_user_config_dict(uc_path)
    sub_dict = doc.get("subscribes")
    if sub_dict is None:
        raise ValueError("user_config 无 subscribes")
    try:
        subs = parse_subscribes(sub_dict)
    except ValueError as e:
        raise ValueError(str(e)) from e
    eff = resolve_default_subscribe_name(subs, doc.get("default_subscribe"))
    if not eff:
        raise ValueError("无法解析 default_subscribe")
    if subs.get(eff, {}).get("backend") != "v2ray":
        raise ValueError(f"当前默认订阅 {eff!r} 不是 v2ray 后端（需 backend: v2ray）")
    return eff, doc, uc_path


def load_proxy_outbounds_from_cache(root: Path, profile_name: str) -> list[dict[str, Any]]:
    cache_json = download_cache_dir(root) / f"{profile_name}.json"
    if not cache_json.is_file():
        raise ValueError(f"未找到 {cache_json}，请先执行 myclash service update_subscribe")
    try:
        data = json.loads(cache_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise ValueError(f"读取 cache 失败: {e}") from e
    obs = _proxy_outbounds_from_saved_v2ray(data)
    if not obs:
        raise ValueError("cache 中无可用 proxy outbound")
    return obs


def current_fixed_tag(doc: dict[str, Any]) -> str | None:
    v = doc.get("v2ray_outbound_tag")
    if isinstance(v, str) and v.strip():
        return v.strip()
    return None


def fixed_routing_outbound_tag_from_mcs(root: Path) -> str | None:
    """从 ``mcs/configs/v2ray.json`` 解析主路由里固定的 ``outboundTag``；若为 balancer 等多出口则返回 ``None``。"""
    p = mcs_configs_dir(root) / "v2ray.json"
    if not p.is_file():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    routing = data.get("routing")
    if not isinstance(routing, dict):
        return None
    for rule in routing.get("rules") or []:
        if not isinstance(rule, dict):
            continue
        ot = rule.get("outboundTag")
        if isinstance(ot, str) and ot.strip():
            return ot.strip()
    return None


def apply_v2ray_outbound_selection(
    root: Path,
    *,
    tag: str | None,
    clear: bool,
    logger: logging.Logger | None = None,
) -> tuple[bool, str, bool]:
    """更新 ``v2ray_outbound_tag``、重写 mcs 配置并 ``POST /kernel/reload``，并等待子进程恢复。

    返回 ``(是否视为成功, 提示文案, 是否确认热重载已生效)``。
    """
    log = logger or logging.getLogger(__name__)
    eff, doc, uc_path = resolve_v2ray_default_profile(root)
    if clear:
        doc.pop("v2ray_outbound_tag", None)
        msg = "已清除固定节点（多订阅节点时将使用随机 balancer）"
    else:
        if not tag or not str(tag).strip():
            return False, "未指定节点 tag", False
        doc["v2ray_outbound_tag"] = str(tag).strip()
        msg = f"已固定节点: {str(tag).strip()!r}"
    save_user_config_dict(uc_path, doc)
    obs = load_proxy_outbounds_from_cache(root, eff)
    write_v2ray_json_from_outbounds(
        myclash_root=root,
        profile_name=eff,
        outbounds=obs,
        logger=log,
        write_mcs=True,
        include_mcs=True,
    )
    if not request_kernel_reload(logger=log, root=root):
        return True, msg + "；未能连接 mcs 热重载 API（请检查 mcs_api 地址/令牌或执行: myclash service restart）", False
    ready, werr = wait_kernel_ready(want_backend="v2ray", root=root, timeout=20.0)
    if ready:
        return True, msg + "；已热重载，v2ray 子进程已恢复（无需再手动 restart）。", True
    return (
        True,
        msg + f"；已发送重载但未在超时内确认进程（{werr or 'unknown'}），可稍候或: myclash service restart",
        False,
    )

