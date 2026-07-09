#!/usr/bin/env python3
"""构建 mcs 完整离线安装包（apt / pip 除外）。

目录布局::

    build/amd64/mcs/            # 与仓库相同的完整目录 + 预置 cache/download/
    build/armv7/mcs/
    build/arm64/mcs/
    dist/MCS-amd64-3.0.7.zip    # 解压后顶层目录为 mcs/（版本取自 install/version）
    dist/MCS-armv7-3.0.7.zip
    dist/MCS-arm64-3.0.7.zip

用法（维护者，需联网；MYCLASH_ROOT_PWD 指向仓库根）::

    python3 install/build_release.py all
    python3 install/build_release.py amd64
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_repo = Path(__file__).resolve().parents[1]
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))

from install.release import ARCHES, build_all_releases, build_release, machine_to_arch  # noqa: E402


def _root() -> Path:
    raw = os.environ.get("MYCLASH_ROOT_PWD", "").strip()
    if not raw:
        print("build_release: 缺少 MYCLASH_ROOT_PWD", file=sys.stderr)
        sys.exit(2)
    return Path(raw).resolve()


def main() -> None:
    ap = argparse.ArgumentParser(description="构建 mcs 完整离线安装 zip（每架构一包）")
    ap.add_argument(
        "arch",
        nargs="?",
        choices=(*ARCHES, "all", "current"),
        default="all",
        help="目标架构；all=三种架构；current=本机",
    )
    args = ap.parse_args()
    root = _root()
    target = args.arch
    if target == "current":
        arch = machine_to_arch()
        results = [build_release(root, arch)]
    elif target == "all":
        results = build_all_releases(root)
    else:
        results = [build_release(root, target)]
    print("构建完成:")
    for staging, zipp in results:
        print(f"  目录: {staging}")
        print(f"  zip:  {zipp}")


if __name__ == "__main__":
    main()
