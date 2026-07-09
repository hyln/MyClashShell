"""离线完整安装包构建：按架构复制仓库目录树并预置 cache/download/ 依赖。

构建产出::
  build/_cache/shared/        … 地理库（跨架构复用，已存在则跳过下载）
  build/_cache/{arch}/        … clash.gz、xray、xray.zip（已存在则跳过）
  build/amd64/mcs/            … 完整目录（与仓库同结构）
  build/armv7/mcs/
  build/arm64/mcs/
  dist/MCS-amd64-3.0.7.zip    … 解压后顶层目录为 mcs/
  dist/MCS-armv7-3.0.7.zip
  dist/MCS-arm64-3.0.7.zip
"""

from __future__ import annotations

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

ARCHES = ("amd64", "armv7", "arm64")
PACKAGE_NAME = "mcs"
RELEASE_ZIP_FMT = "MCS-{arch}-{version}.zip"
OFFLINE_MARKER = "install/offline-release.yaml"
CACHE_ASSETS = ("clash.gz", "xray", "Country.mmdb", "geoip.dat", "geosite.dat")
_REQUIRED_CACHE = ("clash.gz", "Country.mmdb")
_XRAY_BIN_NAMES = ("xray",)
_YAML_KERNEL_SECTION = "mihomo"
_PIP_PACKAGES = ("pyyaml", "ruamel.yaml", "colorlog", "requests", "textual", "flask")

_COPY_SKIP_DIRS = {
    ".git",
    ".cursor",
    ".agents",
    ".codex",
    "__pycache__",
    "venv",
    "mcs",
    "cache",
    "build",
    "dist",
    "back",
    "tmp",
    "typescript",
    "sub_configs",
    "config_urls",
}
# 仅跳过仓库根目录下的用户生成文件，不跳过 install/templates/user_config.yaml 等模板
_ROOT_SKIP_FILES = {
    "user_config.yaml",
    "config.yaml",
    "config_custom.yaml",
}


def machine_to_arch(machine: str | None = None) -> str:
    m = (machine if machine is not None else platform.machine()).lower()
    if m in ("x86_64", "amd64"):
        return "amd64"
    if m in ("aarch64", "arm64"):
        return "arm64"
    if m in ("armv7l", "armv7", "armhf", "armv7a"):
        return "armv7"
    raise ValueError(f"不支持的架构: {m!r}")


def yaml_section_for_url(section: str) -> str:
    s = section.strip().lower()
    if s in ("clash", "mihomo", "mihoyo"):
        return _YAML_KERNEL_SECTION
    return s


def load_download_doc(root: Path) -> dict:
    doc_path = root / "install" / "download.yaml"
    if not doc_path.is_file():
        raise FileNotFoundError(f"未找到 {doc_path}")
    with doc_path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError("download.yaml 格式错误")
    return data


def url_from_doc(data: dict, section: str, arch: str | None) -> str:
    if section == "mmdb":
        url = data.get("mmdb")
        if not isinstance(url, str) or not url.strip():
            raise ValueError("缺少 mmdb URL")
        return url.strip()
    if not arch:
        raise ValueError(f"{section} 须指定 arch")
    section = yaml_section_for_url(section)
    block = data.get(section)
    if not isinstance(block, dict):
        raise ValueError(f"缺少 {section} 段")
    u = block.get(arch)
    if not isinstance(u, str) or not u.strip():
        raise ValueError(f"{section}.{arch} 无有效 URL")
    return u.strip()


def geo_asset_url(data: dict, key: str) -> str | None:
    raw = data.get(key)
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return None


def read_version(root: Path) -> str:
    p = root / "install" / "version"
    if p.is_file():
        return p.read_text(encoding="utf-8").strip()
    return ""


def release_version_label(root: Path) -> str:
    """``install/version`` 去掉前缀 ``v``，用于 zip 文件名（如 ``3.0.7``）。"""
    v = read_version(root)
    return v.lstrip("vV") if v else "0"


def build_dir(root: Path) -> Path:
    d = root / "build"
    d.mkdir(parents=True, exist_ok=True)
    return d


def download_cache_dir(root: Path) -> Path:
    """构建时下载缓存（跨次 build 复用，避免重复拉取）。"""
    d = build_dir(root) / "_cache"
    d.mkdir(parents=True, exist_ok=True)
    return d


def shared_cache_dir(root: Path) -> Path:
    d = download_cache_dir(root) / "shared"
    d.mkdir(parents=True, exist_ok=True)
    return d


def arch_cache_dir(root: Path, arch: str) -> Path:
    d = download_cache_dir(root) / arch
    d.mkdir(parents=True, exist_ok=True)
    return d


def dist_dir(root: Path) -> Path:
    d = root / "dist"
    d.mkdir(parents=True, exist_ok=True)
    return d


def release_staging(root: Path, arch: str) -> Path:
    return build_dir(root) / arch / PACKAGE_NAME


def release_zip_path(root: Path, arch: str) -> Path:
    ver = release_version_label(root)
    return dist_dir(root) / RELEASE_ZIP_FMT.format(arch=arch, version=ver)


def _format_bytes(n: int) -> str:
    size = float(max(n, 0))
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


def _progress_hook(label: str):
    state = {"shown": False}

    def hook(block_count: int, block_size: int, total_size: int) -> None:
        downloaded = block_count * block_size
        state["shown"] = True
        if total_size and total_size > 0:
            downloaded = min(downloaded, total_size)
            ratio = downloaded / total_size
            bar_width = 28
            filled = min(bar_width, int(ratio * bar_width))
            bar = "#" * filled + "-" * (bar_width - filled)
            msg = (
                f"\r{label} [{bar}] "
                f"{ratio * 100:5.1f}% {_format_bytes(downloaded)}/{_format_bytes(total_size)}"
            )
        else:
            msg = f"\r{label} 已下载 {_format_bytes(downloaded)}"
        sys.stdout.write(msg)
        sys.stdout.flush()

    return hook, state


def download_file(url: str, dest: Path, label: str) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_file() and dest.stat().st_size > 0:
        print(f"已存在，跳过 {label}: {dest}")
        return
    tmp = Path(f"{dest}.tmp")
    if tmp.is_file():
        try:
            tmp.unlink()
        except OSError:
            pass
    print(f"下载 {label} -> {dest}")
    hook, state = _progress_hook(label)
    try:
        urlretrieve(url, str(tmp), reporthook=hook)
    except (OSError, URLError) as exc:
        if state["shown"]:
            print()
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise RuntimeError(f"下载失败 {label}: {exc}") from exc
    if state["shown"]:
        print()
    tmp.replace(dest)


def _find_xray_binary(unzip_dir: Path) -> Path | None:
    for name in _XRAY_BIN_NAMES:
        for p in unzip_dir.rglob(name):
            if p.is_file():
                return p
    return None


def _download_xray_binary(data: dict, arch: str, dest: Path, *, work_dir: Path) -> None:
    if dest.is_file() and dest.stat().st_size > 0:
        print(f"已存在，跳过 xray ({arch}): {dest}")
        dest.chmod(dest.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        return
    url = url_from_doc(data, "xray", arch)
    zip_cache = dest.parent / "xray.zip"
    download_file(url, zip_cache, f"xray zip ({arch})")
    with tempfile.TemporaryDirectory(prefix="xray_uz_", dir=str(work_dir)) as td:
        uz = Path(td) / "uz"
        uz.mkdir()
        with zipfile.ZipFile(zip_cache, "r") as zf:
            zf.extractall(uz)
        found = _find_xray_binary(uz)
        if found is None:
            raise RuntimeError(f"xray zip ({arch}) 中未找到 xray 可执行文件")
        shutil.copy2(found, dest)
    dest.chmod(dest.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def ensure_shared_assets(data: dict, cache_dir: Path) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    download_file(url_from_doc(data, "mmdb", None), cache_dir / "Country.mmdb", "Country.mmdb")
    gu = geo_asset_url(data, "geoip")
    if gu:
        download_file(gu, cache_dir / "geoip.dat", "geoip.dat")
    gs = geo_asset_url(data, "geosite")
    if gs:
        download_file(gs, cache_dir / "geosite.dat", "geosite.dat")


def ensure_arch_assets(data: dict, arch: str, cache_dir: Path, *, work_dir: Path) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    download_file(
        url_from_doc(data, _YAML_KERNEL_SECTION, arch),
        cache_dir / "clash.gz",
        f"mihomo→clash.gz ({arch})",
    )
    _download_xray_binary(data, arch, cache_dir / "xray", work_dir=work_dir)


def copy_assets_to_cache_download(src_arch: Path, src_shared: Path, cache_download: Path) -> None:
    cache_download.mkdir(parents=True, exist_ok=True)
    for name in ("clash.gz", "xray"):
        shutil.copy2(src_arch / name, cache_download / name)
        if name == "xray":
            (cache_download / name).chmod(
                (cache_download / name).stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
            )
    for name in ("Country.mmdb", "geoip.dat", "geosite.dat"):
        p = src_shared / name
        if p.is_file():
            shutil.copy2(p, cache_download / name)


def _make_copy_ignore(src_root: Path):
    root = src_root.resolve()

    def _copy_ignore(src: str, names: list[str]) -> set[str]:
        ignored: set[str] = set()
        for name in names:
            if name in _COPY_SKIP_DIRS:
                ignored.add(name)
                continue
            if name in _ROOT_SKIP_FILES and Path(src).resolve() == root:
                ignored.add(name)
                continue
            if name == "__pycache__" or name.endswith(".log"):
                ignored.add(name)
        if Path(src).name == "install" and "bundles" in names:
            ignored.add("bundles")
        return ignored

    return _copy_ignore


def copy_repo_tree(src_root: Path, dest_root: Path) -> None:
    if dest_root.exists():
        shutil.rmtree(dest_root)
    shutil.copytree(src_root, dest_root, ignore=_make_copy_ignore(src_root), dirs_exist_ok=False)


def write_offline_marker(package_root: Path, arch: str, version: str) -> None:
    doc = {"arch": arch, "version": version, "package": PACKAGE_NAME}
    p = package_root / OFFLINE_MARKER
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")


def zip_package_tree(package_root: Path, out_zip: Path) -> None:
    out_zip.parent.mkdir(parents=True, exist_ok=True)
    top = package_root.name
    with zipfile.ZipFile(out_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(package_root.rglob("*")):
            if not path.is_file():
                continue
            arcname = Path(top) / path.relative_to(package_root)
            zf.write(path, arcname.as_posix())
    print(f"已写入 dist 安装包: {out_zip}")


def build_release(root: Path, arch: str) -> tuple[Path, Path]:
    data = load_download_doc(root)
    version = read_version(root)
    work = build_dir(root) / "_work"
    work.mkdir(parents=True, exist_ok=True)
    shared = shared_cache_dir(root)
    arch_cache = arch_cache_dir(root, arch)
    ensure_shared_assets(data, shared)
    ensure_arch_assets(data, arch, arch_cache, work_dir=work)
    staging = release_staging(root, arch)
    print(f"=== 构建 {arch} -> {staging} ===")
    copy_repo_tree(root, staging)
    copy_assets_to_cache_download(arch_cache, shared, staging / "cache" / "download")
    write_offline_marker(staging, arch, version)
    out_zip = release_zip_path(root, arch)
    zip_package_tree(staging, out_zip)
    return staging, out_zip


def build_all_releases(root: Path) -> list[tuple[Path, Path]]:
    built: list[tuple[Path, Path]] = []
    for arch in ARCHES:
        built.append(build_release(root, arch))
    return built


def cache_download_ready(cache_download: Path) -> bool:
    return all((cache_download / name).is_file() for name in _REQUIRED_CACHE)


def is_offline_release(root: Path) -> bool:
    return (root / OFFLINE_MARKER).is_file()


def install_pip_deps(root: Path) -> None:
    venv_py = root / "venv" / "bin" / "python3"
    if not venv_py.is_file():
        raise FileNotFoundError("未找到 venv/bin/python3，请先 mkvenv")
    print(f"安装 pip 依赖 ({', '.join(_PIP_PACKAGES)}) …")
    r = subprocess.run(
        [str(venv_py), "-m", "pip", "install", *_PIP_PACKAGES],
        cwd=str(root),
    )
    if r.returncode != 0:
        raise RuntimeError("pip 安装失败")


def download_cache_for_dev(root: Path, cache_download: Path) -> None:
    """开发仓库（非离线包）缺依赖时从 download.yaml 在线拉取（写入 build/_cache/ 后复制）。"""
    data = load_download_doc(root)
    arch = machine_to_arch()
    work = build_dir(root) / "_work"
    work.mkdir(parents=True, exist_ok=True)
    shared = shared_cache_dir(root)
    arch_cache = arch_cache_dir(root, arch)
    print(f"开发模式：从网络下载依赖（arch={arch}）")
    ensure_shared_assets(data, shared)
    ensure_arch_assets(data, arch, arch_cache, work_dir=work)
    copy_assets_to_cache_download(arch_cache, shared, cache_download)


def ensure_cache_download(root: Path, cache_download: Path) -> None:
    cache_download.mkdir(parents=True, exist_ok=True)
    if cache_download_ready(cache_download):
        print("cache/download/ 已包含离线依赖，跳过下载")
        return
    if is_offline_release(root):
        missing = [n for n in _REQUIRED_CACHE if not (cache_download / n).is_file()]
        raise FileNotFoundError(
            f"离线安装包缺少 cache/download/ 文件: {', '.join(missing)}"
        )
    download_cache_for_dev(root, cache_download)
