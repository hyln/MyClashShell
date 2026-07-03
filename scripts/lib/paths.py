"""Resolve repository paths from MYCLASH_ROOT_PWD or package layout."""

from __future__ import annotations

import os
import shutil
from pathlib import Path


def repo_root_from_env() -> Path | None:
    raw = os.environ.get("MYCLASH_ROOT_PWD", "").strip()
    return Path(raw).resolve() if raw else None


def repo_root() -> Path:
    """Prefer MYCLASH_ROOT_PWD; else infer from scripts/lib/paths.py location (dev)."""
    p = repo_root_from_env()
    if p is not None:
        return p
    return Path(__file__).resolve().parents[2]


def scripts_runtime_dir(root: Path | None = None) -> Path:
    base = root if root is not None else repo_root()
    return base / "scripts" / "runtime"


def scripts_tools_dir(root: Path | None = None) -> Path:
    base = root if root is not None else repo_root()
    return base / "scripts" / "tools"


def update_proxy_config_script(root: Path | None = None) -> Path:
    return scripts_runtime_dir(root) / "update_proxy_config.py"


def repo_cache_dir(root: Path | None = None) -> Path:
    """仓库根下 ``cache/``（例如 ``env_prefix.txt``、``current_sub.txt``、``current_mcs_port.txt``）。"""
    base = root if root is not None else repo_root()
    return base / "cache"


def env_prefix_txt_path(root: Path | None = None) -> Path:
    """安装写入 ``~/.bashrc`` 的片段生成目标：``cache/env_prefix.txt``。"""
    return repo_cache_dir(root) / "env_prefix.txt"


def current_sub_txt_path(root: Path | None = None) -> Path:
    """当前默认订阅名：``cache/current_sub.txt``。"""
    return repo_cache_dir(root) / "current_sub.txt"


def cache_download_dir(root: Path | None = None) -> Path:
    """安装阶段下载的内核与地理库：``cache/download/``。"""
    return repo_cache_dir(root) / "download"


def subscribe_cache_dir(root: Path | None = None) -> Path:
    """订阅原始 clash yaml / v2ray json：``cache/subscribe/``。"""
    return repo_cache_dir(root) / "subscribe"


def _prune_legacy_repo_tmp(base: Path) -> None:
    """删除仓库根下旧版 ``tmp/`` 中的已知遗留文件；若目录为空则移除，避免长期保留空 ``tmp``。"""
    td = base / "tmp"
    if not td.is_dir():
        return
    for name in (
        "myclash.service",
        "env_prefix.txt",
        "slave_http_server.pid",
        "slave_http_server.log",
    ):
        p = td / name
        if p.is_file():
            try:
                p.unlink()
            except OSError:
                pass
    try:
        next(td.iterdir())
    except StopIteration:
        try:
            td.rmdir()
        except OSError:
            pass
    except OSError:
        pass


def migrate_legacy_cache_layout(root: Path | None = None) -> None:
    """若仍为旧版扁平 ``cache/*.yaml`` / ``cache/clash.gz`` 等，迁移至 ``subscribe`` / ``download``。"""
    base = repo_root() if root is None else Path(root).resolve()
    tmp_ep = base / "tmp" / "env_prefix.txt"
    cache_ep = env_prefix_txt_path(base)
    if tmp_ep.is_file():
        cache_ep.parent.mkdir(parents=True, exist_ok=True)
        if not cache_ep.is_file():
            shutil.move(str(tmp_ep), str(cache_ep))
        else:
            try:
                tmp_ep.unlink()
            except OSError:
                pass
    cr = base / "cache"
    if cr.is_dir():
        dl = cache_download_dir(base)
        sb = subscribe_cache_dir(base)
        dl.mkdir(parents=True, exist_ok=True)
        sb.mkdir(parents=True, exist_ok=True)
        for name in ("clash.gz", "Country.mmdb", "geoip.dat", "geosite.dat", "xray.zip", "xray"):
            src = cr / name
            dst = dl / name
            if src.is_file() and not dst.is_file():
                shutil.move(str(src), str(dst))
        for old, new in (("v2ray.zip", "xray.zip"), ("v2ray", "xray")):
            src = cr / old
            dst = dl / new
            if src.is_file() and not dst.is_file():
                shutil.move(str(src), str(dst))
        legacy_cs = sb / "current_sub.txt"
        target_cs = current_sub_txt_path(base)
        if legacy_cs.is_file():
            if not target_cs.is_file():
                shutil.move(str(legacy_cs), str(target_cs))
            else:
                try:
                    legacy_cs.unlink()
                except OSError:
                    pass
        for src in list(cr.glob("*.yaml")) + list(cr.glob("*.json")):
            if not src.is_file():
                continue
            dst = sb / src.name
            if not dst.is_file():
                shutil.move(str(src), str(dst))
    _prune_legacy_repo_tmp(base)


def mcs_dir(root: Path | None = None) -> Path:
    base = root if root is not None else repo_root()
    return base / "mcs"


def mcs_bin_dir(root: Path | None = None) -> Path:
    return mcs_dir(root) / "bin"


def mcs_configs_dir(root: Path | None = None) -> Path:
    return mcs_dir(root) / "configs"


def clash_executable(root: Path | None = None) -> Path:
    """Clash 兼容代理内核可执行文件路径（实际为 mihomo，固定安装名 mcs/bin/clash）。"""
    return mcs_bin_dir(root) / "clash"


def xray_executable(root: Path | None = None) -> Path:
    return mcs_bin_dir(root) / "xray"


def clash_config_yaml(root: Path | None = None) -> Path:
    """合并后的 Clash 主配置（mcs/configs/config.yaml）。"""
    return mcs_configs_dir(root) / "config.yaml"


def download_cache_dir(root: Path | None = None) -> Path:
    """兼容旧名：等同于 :func:`subscribe_cache_dir`。"""
    return subscribe_cache_dir(root)


def v2ray_geo_asset_dir(root: Path | None = None) -> Path | None:
    """若存在 ``geoip.dat`` 与 ``geosite.dat``，返回其所在目录。"""
    base = root if root is not None else repo_root()
    for d in (mcs_configs_dir(base), cache_download_dir(base), repo_cache_dir(base)):
        if (d / "geoip.dat").is_file() and (d / "geosite.dat").is_file():
            return d
    return None

