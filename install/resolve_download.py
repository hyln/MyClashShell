#!/usr/bin/env python3
"""install/download.yaml：解析 URL + 将安装所需二进制下载到 cache/。

子命令:
  install-cache   创建 cache/tmp、安装 pip 依赖、下载 mihomo → cache/clash.gz、Country.mmdb、
                  geoip.dat / geosite.dat（install/download.yaml 中 ``geoip`` / ``geosite``）、
                  可选下载并解压 v2ray 到 cache/v2ray（供 install.sh 再 cp 到 mcs/bin/）
  url SECTION [ARCH]  仅打印一条 URL（SECTION 为 mmdb / geoip / geosite 时不带 ARCH；clash/mihomo/mihoyo 均指向 mihomo 段）

环境变量 MYCLASH_ROOT_PWD 须指向仓库根。
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlretrieve

import yaml

_V2RAY_NAMES = ("v2ray", "xray")

# download.yaml 中内核段键名；url 子命令中 clash / mihoyo 视为别名（配置侧仍用 backend: clash）
_YAML_KERNEL_SECTION = "mihomo"


def _yaml_section_for_url(section: str) -> str:
    s = section.strip().lower()
    if s in ("clash", "mihomo", "mihoyo"):
        return _YAML_KERNEL_SECTION
    return s


def _root() -> Path:
    raw = os.environ.get("MYCLASH_ROOT_PWD", "").strip()
    if not raw:
        print("resolve_download: 缺少 MYCLASH_ROOT_PWD", file=sys.stderr)
        sys.exit(2)
    return Path(raw).resolve()


def _load_doc(root: Path) -> dict:
    doc_path = root / "install" / "download.yaml"
    if not doc_path.is_file():
        print(f"resolve_download: 未找到 {doc_path}", file=sys.stderr)
        sys.exit(2)
    with doc_path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        print("resolve_download: download.yaml 格式错误", file=sys.stderr)
        sys.exit(2)
    return data


def _url_from_doc(data: dict, section: str, arch: str | None) -> str:
    if section == "mmdb":
        url = data.get("mmdb")
        if not isinstance(url, str) or not url.strip():
            raise ValueError("缺少 mmdb URL")
        return url.strip()
    if not arch:
        raise ValueError("clash/mihomo/v2ray 须指定 arch")
    section = _yaml_section_for_url(section)
    block = data.get(section)
    if not isinstance(block, dict):
        raise ValueError(f"缺少 {section} 段")
    u = block.get(arch)
    if not isinstance(u, str) or not u.strip():
        raise ValueError(f"{section}.{arch} 无有效 URL")
    return u.strip()


def _geo_asset_url(data: dict, key: str) -> str | None:
    raw = data.get(key)
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return None


def _optional_v2ray_url(data: dict, arch: str) -> str | None:
    try:
        return _url_from_doc(data, "v2ray", arch)
    except ValueError:
        return None


def _machine_to_dl_arch() -> str:
    m = platform.machine().lower()
    if m in ("x86_64", "amd64"):
        return "amd64"
    if m in ("aarch64", "arm64"):
        return "arm64"
    if m in ("armv7l", "armv7", "armhf", "armv7a"):
        return "armv7"
    print(f"resolve_download: 不支持的架构 {m!r}", file=sys.stderr)
    sys.exit(2)


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


def _download_file(url: str, dest: Path, label: str) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"resolve_download: 下载 {label} -> {dest}")
    try:
        urlretrieve(url, str(dest))
    except (OSError, URLError) as exc:
        print(f"resolve_download: 下载失败 {label}: {exc}", file=sys.stderr)
        sys.exit(1)


def _download_file_optional(url: str, dest: Path, label: str) -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"resolve_download: 下载 {label} -> {dest}")
    try:
        urlretrieve(url, str(dest))
    except (OSError, URLError) as exc:
        print(f"resolve_download: {label} 下载失败，跳过: {exc}", file=sys.stderr)
        return False
    return True


def _find_v2ray_binary(unzip_dir: Path) -> Path | None:
    for name in _V2RAY_NAMES:
        for p in unzip_dir.rglob(name):
            if p.is_file():
                return p
    return None


def cmd_install_cache() -> None:
    root = _root()
    cache = root / "cache"
    tmp = root / "tmp"
    cache.mkdir(parents=True, exist_ok=True)
    tmp.mkdir(parents=True, exist_ok=True)
    _chmod_tree_rw(cache)
    _chmod_tree_rw(tmp)

    venv_py = root / "venv" / "bin" / "python3"
    if not venv_py.is_file():
        print("resolve_download: 未找到 venv/bin/python3，请先 mkvenv", file=sys.stderr)
        sys.exit(2)
    print("resolve_download: 安装 pip 依赖 (pyyaml ruamel.yaml colorlog requests textual flask) …")
    r = subprocess.run(
        [
            str(venv_py),
            "-m",
            "pip",
            "install",
            "pyyaml",
            "ruamel.yaml",
            "colorlog",
            "requests",
            "textual",
            "flask",
        ],
        cwd=str(root),
    )
    if r.returncode != 0:
        print("resolve_download: pip 安装失败", file=sys.stderr)
        sys.exit(r.returncode)

    data = _load_doc(root)
    arch = _machine_to_dl_arch()
    print(f"resolve_download: 使用 install/download.yaml 架构={arch}")

    clash_gz = cache / "clash.gz"
    if clash_gz.is_file():
        print("resolve_download: cache/clash.gz 已存在，跳过")
    else:
        _download_file(_url_from_doc(data, _YAML_KERNEL_SECTION, arch), clash_gz, "mihomo→clash.gz")

    mmdb = cache / "Country.mmdb"
    if mmdb.is_file():
        print("resolve_download: cache/Country.mmdb 已存在，跳过")
    else:
        _download_file(_url_from_doc(data, "mmdb", None), mmdb, "Country.mmdb")

    geoip_path = cache / "geoip.dat"
    if geoip_path.is_file():
        print("resolve_download: cache/geoip.dat 已存在，跳过")
    else:
        gu = _geo_asset_url(data, "geoip")
        if gu:
            _download_file(gu, geoip_path, "geoip.dat")
        else:
            print(
                "resolve_download: download.yaml 未配置 geoip，跳过 geoip.dat",
                file=sys.stderr,
            )

    geosite_path = cache / "geosite.dat"
    if geosite_path.is_file():
        print("resolve_download: cache/geosite.dat 已存在，跳过")
    else:
        gs = _geo_asset_url(data, "geosite")
        if gs:
            _download_file(gs, geosite_path, "geosite.dat")
        else:
            print(
                "resolve_download: download.yaml 未配置 geosite，跳过 geosite.dat",
                file=sys.stderr,
            )

    v2_url = _optional_v2ray_url(data, arch)
    if not v2_url:
        print("resolve_download: 无 v2ray URL，跳过 v2ray 二进制", file=sys.stderr)
        return

    shutil.rmtree(cache / "v2ray_unzip", ignore_errors=True)
    zip_path = cache / "v2ray.zip"
    v2_bin = cache / "v2ray"
    if zip_path.is_file():
        print("resolve_download: cache/v2ray.zip 已存在，跳过下载")
    elif not _download_file_optional(v2_url, zip_path, "v2ray zip"):
        return

    with tempfile.TemporaryDirectory(prefix="v2ray_uz_", dir=str(cache)) as udz:
        uz_path = Path(udz)
        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(uz_path)
        except zipfile.BadZipFile as exc:
            print(f"resolve_download: v2ray zip 损坏，跳过: {exc}", file=sys.stderr)
            return
        found = _find_v2ray_binary(uz_path)
        if found is None:
            print("resolve_download: zip 中未找到 v2ray/xray，跳过", file=sys.stderr)
            return
        shutil.copy2(found, v2_bin)
    v2_bin.chmod(v2_bin.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    print(f"resolve_download: 已写入 {v2_bin}")


def cmd_url(section: str, arch: str | None) -> None:
    try:
        data = _load_doc(_root())
        if section == "mmdb":
            print(_url_from_doc(data, "mmdb", None))
            return
        if section == "geoip":
            gu = _geo_asset_url(data, "geoip")
            if not gu:
                raise ValueError("缺少 geoip URL")
            print(gu)
            return
        if section == "geosite":
            gs = _geo_asset_url(data, "geosite")
            if not gs:
                raise ValueError("缺少 geosite URL")
            print(gs)
            return
        print(_url_from_doc(data, section, arch))
    except ValueError as exc:
        print(f"resolve_download: {exc}", file=sys.stderr)
        sys.exit(2)


def main() -> None:
    ap = argparse.ArgumentParser(description="install/download.yaml 解析与 cache 下载")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser(
        "install-cache",
        help="下载 mihomo（cache/clash.gz）/ mmdb / geoip.dat / geosite.dat / v2ray 到 cache/",
    )

    p_url = sub.add_parser("url", help="打印单条 URL")
    p_url.add_argument(
        "section",
        choices=("clash", "mihomo", "mihoyo", "v2ray", "mmdb", "geoip", "geosite"),
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
            print("resolve_download: clash/mihomo/mihoyo/v2ray 须指定 arch", file=sys.stderr)
            sys.exit(2)
        cmd_url(args.section, arch)
    else:
        ap.print_help()
        sys.exit(2)


if __name__ == "__main__":
    main()
