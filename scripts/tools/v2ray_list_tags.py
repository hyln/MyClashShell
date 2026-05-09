#!/usr/bin/env python3
"""列出当前默认 v2ray 订阅合并进 mcs 后的 proxy outbound tag（供脚本或 ``myclash ui`` 参考）。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

_repo = Path(__file__).resolve().parents[2]
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))

from scripts.lib.paths import mcs_configs_dir, repo_root_from_env  # noqa: E402
from scripts.lib.subscribe import parse_subscribes, resolve_default_subscribe_name  # noqa: E402
from scripts.lib.v2ray_subscribe import _proxy_outbounds_from_saved_v2ray  # noqa: E402


def main() -> int:
    root = repo_root_from_env()
    if root is None:
        print("v2ray_list_tags: 请设置 MYCLASH_ROOT_PWD", file=sys.stderr)
        return 2

    uc = root / "user_config.yaml"
    if not uc.is_file():
        print(f"v2ray_list_tags: 未找到 {uc}", file=sys.stderr)
        return 2
    doc = yaml.safe_load(uc.read_text(encoding="utf-8"))
    if not isinstance(doc, dict):
        return 2
    sub_dict = doc.get("subscribes")
    if sub_dict is None:
        print("v2ray_list_tags: 无 subscribes", file=sys.stderr)
        return 2
    try:
        subs = parse_subscribes(sub_dict)
    except ValueError as e:
        print(f"v2ray_list_tags: {e}", file=sys.stderr)
        return 2
    eff = resolve_default_subscribe_name(subs, doc.get("default_subscribe"))
    if not eff or subs.get(eff, {}).get("backend") != "v2ray":
        print("v2ray_list_tags: 当前默认订阅不是 v2ray 后端", file=sys.stderr)
        return 2

    mcs_json = mcs_configs_dir(root) / "v2ray.json"
    if not mcs_json.is_file():
        print(f"v2ray_list_tags: 未找到 {mcs_json}", file=sys.stderr)
        return 1
    try:
        data = json.loads(mcs_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"v2ray_list_tags: {e}", file=sys.stderr)
        return 1
    obs = _proxy_outbounds_from_saved_v2ray(data)
    if not obs:
        print("v2ray_list_tags: 无 proxy outbound", file=sys.stderr)
        return 1
    cur = str(doc.get("v2ray_outbound_tag") or "").strip()
    if cur:
        print(f"# 当前固定: v2ray_outbound_tag={cur}")
    else:
        print("# 当前未固定（多节点时为随机 balancer）")
    for ob in obs:
        print(str(ob.get("tag") or "?"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
