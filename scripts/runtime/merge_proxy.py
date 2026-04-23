#!/usr/bin/env python3
from __future__ import annotations

import sys
import yaml
import getpass
import os
import logging

logger = logging.getLogger(__name__)

# 合并订阅 raw 时，允许从 user_config.yaml 顶层读取的 Clash / mihomo 字段（其余键为 MCS 元数据，不参与合并）
_CLASH_COVER_KEYS: frozenset[str] = frozenset(
    {
        "port",
        "socks-port",
        "mixed-port",
        "mode",
        "allow-lan",
        "log-level",
        "external-controller",
    }
)
_CLASH_ADD_KEYS: frozenset[str] = frozenset({"proxies", "proxy-groups", "rules"})


def clash_overlay_from_user_config(doc: dict | None) -> dict[str, object]:
    """从完整 user_config 文档中抽出参与合并的 Clash 顶层键。"""
    if not isinstance(doc, dict):
        return {}
    allow = _CLASH_COVER_KEYS | _CLASH_ADD_KEYS
    return {k: v for k, v in doc.items() if k in allow}


def slim_proxy_groups_enabled(user_cfg: dict | None) -> bool:
    """user_config.yaml 中 slim_proxy_groups 开启时，合并后仅保留 Via-Proxy 策略组。"""
    if not user_cfg:
        return False
    return bool(user_cfg.get("slim_proxy_groups"))


def resolve_rules_template_path(
    myclash_root_pwd: str,
    rules_template_from_user_config: object,
) -> str | None:
    """将 user_config 中的 rules_template 解析为绝对路径；未配置或空串则返回 None。"""
    if rules_template_from_user_config is None:
        return None
    if isinstance(rules_template_from_user_config, str):
        rt = rules_template_from_user_config.strip()
    else:
        return None
    if not rt:
        return None
    return rt if os.path.isabs(rt) else os.path.join(myclash_root_pwd, rt)


class InvalidPathError(Exception):
    """自定义异常，用于处理无效的文件路径"""
    pass

def check_yaml_path(path):
    if not path.endswith('.yaml'):
        raise InvalidPathError(f"路径 {path} 不是以 .yaml 结尾的文件路径！")
    return True


def _apply_rules_template(raw_configs: dict, rules_template_path: str | None) -> None:
    """若指定了 rules 模板文件，则用其中整段 rules 替换当前配置（覆盖订阅自带规则）。"""
    if not rules_template_path:
        return
    if not os.path.isfile(rules_template_path):
        logger.warning("rules_template 文件不存在，跳过替换: %s", rules_template_path)
        return
    with open(rules_template_path, "r", encoding="utf-8") as stream:
        tpl = yaml.safe_load(stream)
    if tpl is None or not isinstance(tpl.get("rules"), list):
        logger.warning("rules_template 无有效 rules 列表: %s", rules_template_path)
        return
    raw_configs["rules"] = tpl["rules"]
    logger.info("已用 %s 中的 rules 替换订阅规则", rules_template_path)


def _apply_via_proxy_only_groups(raw_configs: dict) -> None:
    """用单一 Via-Proxy（select）替换订阅自带 proxy-groups；成员为全部叶子代理名 + DIRECT。"""
    proxies = raw_configs.get("proxies")
    if not isinstance(proxies, list):
        logger.warning("无 proxies 列表，跳过 Via-Proxy 策略组替换")
        return
    names: list[str] = []
    seen: set[str] = set()
    for p in proxies:
        if not isinstance(p, dict):
            continue
        n = p.get("name")
        if not n or not isinstance(n, str):
            continue
        if n in seen:
            continue
        seen.add(n)
        names.append(n)
    if not names:
        logger.warning("proxies 中无有效 name，跳过 Via-Proxy 策略组替换")
        return
    raw_configs["proxy-groups"] = [
        {
            "name": "Via-Proxy",
            "type": "select",
            "proxies": names + ["DIRECT"],
        }
    ]
    logger.info(
        "已用 Via-Proxy 替换 proxy-groups（%d 个节点 + DIRECT）",
        len(names),
    )


def _finalize_config(
    raw_configs: dict,
    rules_template_path: str | None,
    slim_proxy_groups: bool,
) -> None:
    _apply_rules_template(raw_configs, rules_template_path)
    if slim_proxy_groups:
        _apply_via_proxy_only_groups(raw_configs)


def merge_cfg(
    raw_rule_path: str,
    gen_cfg_path: str,
    *,
    user_config_doc: dict | None = None,
    rules_template_path: str | None = None,
    slim_proxy_groups: bool = False,
) -> bool:
    """将订阅 raw 与 ``user_config.yaml`` 中允许的 Clash 顶层键合并，写入 ``gen_cfg_path``。

    不再读取 ``custom_configs/<订阅名>.yaml``；监听端口、模式等一律写在 ``user_config.yaml`` 顶层。
    """
    check_yaml_path(raw_rule_path)

    with open(raw_rule_path, "r", encoding="utf-8") as raw_configs_stream:
        raw_configs = yaml.safe_load(raw_configs_stream)

    if raw_configs is None:
        print(f"cann't read rule from  {raw_rule_path}")
        return False

    custom_configs = clash_overlay_from_user_config(user_config_doc)
    if not custom_configs:
        _finalize_config(raw_configs, rules_template_path, slim_proxy_groups)
        with open(gen_cfg_path, "w", encoding="utf-8") as yamlfile:
            yaml.safe_dump(raw_configs, yamlfile, allow_unicode=True)
        return True

    for key, value in custom_configs.items():
        if key in _CLASH_COVER_KEYS:
            raw_configs[key] = value

    for key, value in custom_configs.items():
        if key not in _CLASH_ADD_KEYS:
            continue
        if not isinstance(value, list):
            continue
        bucket = raw_configs.get(key)
        if bucket is None:
            raw_configs[key] = list(value)
            continue
        if not isinstance(bucket, list):
            logger.warning("合并跳过 %s：订阅中该字段不是列表", key)
            continue
        for i in value:
            bucket.insert(0, i)

    _finalize_config(raw_configs, rules_template_path, slim_proxy_groups)

    with open(gen_cfg_path, "w", encoding="utf-8") as yamlfile:
        yaml.safe_dump(raw_configs, yamlfile, allow_unicode=True)
    return True