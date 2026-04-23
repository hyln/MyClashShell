#!/usr/bin/env python3
"""v2ray 模式延迟测试：临时起 Xray/v2ray 子进程 + 本机 SOCKS，用 curl 测 RTT（无 core 官方 API）。

用法（需已安装 curl，且仓库根下有可用的 v2ray/Xray 二进制）::

    PYTHONPATH=<repo> python3 scripts/tools/v2ray_ping.py
    PYTHONPATH=<repo> python3 scripts/tools/v2ray_ping.py [--tag …] [--url …]

环境变量（可选）::

    MYCLASH_TUI_TEST_URL   默认 https://www.gstatic.com/generate_204
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_repo = Path(__file__).resolve().parents[2]
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))

from scripts.lib.paths import repo_root_from_env, v2ray_executable  # noqa: E402
from scripts.lib.v2ray_delay_test import (  # noqa: E402
    default_v2ray_config_path,
    list_proxy_outbounds_from_file,
    measure_proxy_delay_ms,
)


def main() -> int:
    ap = argparse.ArgumentParser(description="v2ray/Xray：按节点起临时 SOCKS 进程并用 curl 测延迟")
    ap.add_argument(
        "--config",
        type=Path,
        default=None,
        help="完整 v2ray.json（默认 <MYCLASH_ROOT>/mcs/configs/v2ray.json）",
    )
    ap.add_argument("--tag", type=str, default="", help="只测该 outbound tag；缺省测全部")
    ap.add_argument(
        "--url",
        type=str,
        default=os.environ.get("MYCLASH_TUI_TEST_URL", "https://www.gstatic.com/generate_204"),
        help="经 SOCKS 访问的 URL",
    )
    ap.add_argument("--curl-timeout", type=float, default=4.0, help="单次 curl --max-time（秒）")
    ap.add_argument("--listen-wait", type=float, default=8.0, help="等待 SOCKS 监听就绪（秒）")
    args = ap.parse_args()

    root = repo_root_from_env()
    if root is None:
        print("v2ray_ping: 请设置 MYCLASH_ROOT_PWD 或从仓库根运行", file=sys.stderr)
        return 2
    cfg_path = args.config if args.config is not None else default_v2ray_config_path(root)
    exe = v2ray_executable(root)
    if not exe.is_file():
        print(f"v2ray_ping: 未找到内核可执行文件: {exe}", file=sys.stderr)
        return 2
    obs = list_proxy_outbounds_from_file(cfg_path)
    if not obs:
        print(f"v2ray_ping: 未从 {cfg_path} 解析到任何代理 outbound", file=sys.stderr)
        return 1
    want = (args.tag or "").strip()
    if want:
        obs = [x for x in obs if str(x.get("tag") or "") == want]
        if not obs:
            print(f"v2ray_ping: 无 tag={want!r}", file=sys.stderr)
            return 1

    print(f"# config={cfg_path}\n# url={args.url}\n# kernel={exe}\n")
    for ob in obs:
        tag = str(ob.get("tag") or "?")
        ms = measure_proxy_delay_ms(
            v2ray_exe=exe,
            proxy_ob=ob,
            test_url=args.url,
            curl_timeout=args.curl_timeout,
            listen_ready_timeout=args.listen_wait,
        )
        if ms is None:
            print(f"{tag}\tfail")
        else:
            print(f"{tag}\t{ms}ms")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
