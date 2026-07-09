#!/usr/bin/env python3
"""安装阶段依赖准备：pip + 使用预置或在线补齐 cache/download/。

子命令:
  install-cache   安装 pip 依赖；离线安装包直接使用 cache/download/；
                  开发仓库缺文件时从 download.yaml 在线下载
  url SECTION [ARCH]  打印 download.yaml 中的 URL（供 build_release 使用）

环境变量 MYCLASH_ROOT_PWD 须指向仓库根。
"""

from __future__ import annotations

import argparse
import os
import stat
import sys
from pathlib import Path

_repo_root = Path(__file__).resolve().parents[1]
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))
from install.release import (  # noqa: E402
    ensure_cache_download,
    geo_asset_url,
    install_pip_deps,
    load_download_doc,
    machine_to_arch,
    url_from_doc,
)
from scripts.lib.paths import (  # noqa: E402
    cache_download_dir,
    migrate_legacy_cache_layout,
    repo_cache_dir,
)


def _root() -> Path:
    raw = os.environ.get("MYCLASH_ROOT_PWD", "").strip()
    if not raw:
        print("resolve_download: 缺少 MYCLASH_ROOT_PWD", file=sys.stderr)
        sys.exit(2)
    return Path(raw).resolve()


def _chmod_tree_rw(path: Path) -> None:
    for p in path.rglob("*"):
        try:
            p.chmod(p.stat().st_mode | stat.S_IWRITE | stat.S_IREAD | stat.S_IXUSR)
        except OSError:
            pass
    try:
        path.chmod(path.stat().st_mode | stat.S_IWRITE | stat.S_IREAD | stat.S_IXUSR)
    except OSError:
        pass


def cmd_install_cache() -> None:
    root = _root()
    migrate_legacy_cache_layout(root)
    dload = cache_download_dir(root)
    dload.mkdir(parents=True, exist_ok=True)
    repo_cache = repo_cache_dir(root)
    repo_cache.mkdir(parents=True, exist_ok=True)
    _chmod_tree_rw(repo_cache)
    _chmod_tree_rw(dload)

    try:
        install_pip_deps(root)
    except (FileNotFoundError, RuntimeError) as exc:
        print(f"resolve_download: {exc}", file=sys.stderr)
        sys.exit(2)

    arch = machine_to_arch()
    print(f"resolve_download: 本机架构={arch}")
    try:
        ensure_cache_download(root, dload)
    except (FileNotFoundError, RuntimeError) as exc:
        print(f"resolve_download: {exc}", file=sys.stderr)
        sys.exit(1)
    print("resolve_download: cache/download/ 已就绪")


def cmd_url(section: str, arch: str | None) -> None:
    try:
        data = load_download_doc(_root())
        if section == "mmdb":
            print(url_from_doc(data, "mmdb", None))
            return
        if section == "geoip":
            gu = geo_asset_url(data, "geoip")
            if not gu:
                raise ValueError("缺少 geoip URL")
            print(gu)
            return
        if section == "geosite":
            gs = geo_asset_url(data, "geosite")
            if not gs:
                raise ValueError("缺少 geosite URL")
            print(gs)
            return
        print(url_from_doc(data, section, arch))
    except (ValueError, FileNotFoundError) as exc:
        print(f"resolve_download: {exc}", file=sys.stderr)
        sys.exit(2)


def main() -> None:
    ap = argparse.ArgumentParser(description="安装依赖准备与 download.yaml URL 查询")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser(
        "install-cache",
        help="pip 依赖 + 使用 cache/download/（离线包预置或开发模式在线下载）",
    )

    p_url = sub.add_parser("url", help="打印单条 URL（构建安装包用）")
    p_url.add_argument(
        "section",
        choices=("clash", "mihomo", "mihoyo", "xray", "mmdb", "geoip", "geosite"),
    )
    p_url.add_argument(
        "arch",
        nargs="?",
        choices=("amd64", "armv7", "arm64"),
    )

    args = ap.parse_args()
    if args.cmd == "install-cache":
        cmd_install_cache()
    elif args.cmd == "url":
        no_arch = args.section in ("mmdb", "geoip", "geosite")
        arch = None if no_arch else args.arch
        if not no_arch and not arch:
            print("resolve_download: clash/mihomo/mihoyo/xray 须指定 arch", file=sys.stderr)
            sys.exit(2)
        cmd_url(args.section, arch)
    else:
        ap.print_help()
        sys.exit(2)


if __name__ == "__main__":
    main()
