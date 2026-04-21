#!/usr/bin/env python3
"""Which clash core to run (clash vs mihomo) and optional clash.meta subscription URLs."""
from __future__ import annotations

import os
import re
import yaml


def load_user_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data if isinstance(data, dict) else {}


def subscribed_names_using_mihomo(cfg: dict) -> set:
    v = cfg.get("mihomo_subscribes")
    if v is None:
        return set()
    if isinstance(v, str):
        return {v.strip()} if v.strip() else set()
    if isinstance(v, (list, tuple)):
        return {str(x).strip() for x in v if str(x).strip()}
    return set()


def prepare_download_url(url: str, profile_name: str, cfg: dict) -> tuple[str, str]:
    """
    Returns (url_for_download, flag_value for subconverter).
    For Mihomo-listed profiles, optionally switch target=clash -> clash.meta and use flag=clash.meta.
    """
    if profile_name not in subscribed_names_using_mihomo(cfg):
        return url, "clash"
    u = url
    if cfg.get("mihomo_clash_meta_convert", True):
        if re.search(r"target=clash\.meta", u) is None:
            u = re.sub(r"(target=)clash(&|$)", r"\1clash.meta\2", u, count=1)
    return u, "clash.meta"


def write_current_core(myclash_root: str, subscribe_name: str) -> None:
    cfg_path = os.path.join(myclash_root, "user_config.yaml")
    if not os.path.isfile(cfg_path):
        core = "clash"
    else:
        cfg = load_user_config(cfg_path)
        core = "mihomo" if subscribe_name in subscribed_names_using_mihomo(cfg) else "clash"
    tmp_dir = os.path.join(myclash_root, "tmp")
    os.makedirs(tmp_dir, exist_ok=True)
    with open(os.path.join(tmp_dir, "current_core.txt"), "w", encoding="ascii") as f:
        f.write(core)
