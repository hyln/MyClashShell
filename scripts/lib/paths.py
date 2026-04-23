"""Resolve repository paths from MYCLASH_ROOT_PWD or package layout."""

from __future__ import annotations

import os
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


def shell_slave_dir(root: Path | None = None) -> Path:
    base = root if root is not None else repo_root()
    return base / "shell" / "slave"


def update_proxy_config_script(root: Path | None = None) -> Path:
    return scripts_runtime_dir(root) / "update_proxy_config.py"


def slave_bootstrap_script(root: Path | None = None) -> Path:
    return shell_slave_dir(root) / "slave_bootstrap.sh"


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


def v2ray_executable(root: Path | None = None) -> Path:
    return mcs_bin_dir(root) / "v2ray"


def clash_config_yaml(root: Path | None = None) -> Path:
    """合并后的 Clash 主配置（mcs/configs/config.yaml）。"""
    return mcs_configs_dir(root) / "config.yaml"


def download_cache_dir(root: Path | None = None) -> Path:
    """订阅原始 YAML、current_sub.txt 及安装阶段二进制缓存等。"""
    base = root if root is not None else repo_root()
    return base / "cache"


# Relative to repo root, for HTTP static file mapping (slave_http_server)
SLAVE_SCRIPT_RELPATHS: tuple[str, ...] = (
    "shell/slave/slave_bootstrap.sh",
    "shell/slave/connect_other_proxy.sh",
)

GITHUB_RAW_SLAVE_BOOTSTRAP_MAIN = (
    "https://raw.githubusercontent.com/<user>/MyClashShell/main/shell/slave/slave_bootstrap.sh"
)
