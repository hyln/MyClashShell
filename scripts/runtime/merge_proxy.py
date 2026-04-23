#!/usr/bin/env python3
from __future__ import annotations

import sys
import yaml
import getpass
import os
import logging

logger = logging.getLogger(__name__)


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
    raw_rule_path,
    custum_rule_path,
    gen_cfg_path,
    rules_template_path: str | None = None,
    slim_proxy_groups: bool = False,
):
    '''
    通过下载的profile和自定义的规则生成最终使用的规则

    参数:
    raw_rule_path: 下载的规则路径 .yaml 结尾
    custum_rule_path: 自定义规则路径 .yaml 结尾
    gen_rule_path: 生成的新profile路径 .yaml 结尾
    rules_template_path: 可选，整段替换 rules
    slim_proxy_groups: 为 True 时用 Via-Proxy（全部节点+DIRECT）替换订阅 proxy-groups
    '''
    check_yaml_path(raw_rule_path)
    check_yaml_path(custum_rule_path)
    # check_yaml_path(gen_cfg_path)

    # 读取raw_cfg
    raw_configs_stream = open(raw_rule_path, "r",encoding='utf-8')
    raw_configs = yaml.safe_load(raw_configs_stream)

    if(raw_configs is None):
        print(f"cann't read rule from  {raw_rule_path}")
        return False
    # 如果 custom_rule 文件不存在，直接复制raw，然后退出
    if(os.path.exists(custum_rule_path) is False):
        _finalize_config(raw_configs, rules_template_path, slim_proxy_groups)
        with open(gen_cfg_path,'w') as yamlfile:
            yaml.safe_dump(raw_configs, yamlfile,allow_unicode=True)
        return True
    # 读取 custom_rule
    custom_configs_stream = open(custum_rule_path, "r",encoding='utf-8')
    custom_configs = yaml.safe_load(custom_configs_stream)
    # 如果custom_rule是空的，直接复制raw，然后退出
    if(custom_configs is None):
        _finalize_config(raw_configs, rules_template_path, slim_proxy_groups)
        with open(gen_cfg_path,'w') as yamlfile:
            yaml.safe_dump(raw_configs, yamlfile,allow_unicode=True)
        return True
    
    # merge 分为两个部分
    # 1. cover
    # 2. append

    cover_configs = ["port" , "socks-port", "mode", "allow-lan", "log-level", "external-controller"]
    # port: 7890
    # socks-port: 7891
    # allow-lan: true
    # mode: Rule
    # log-level: info
    # external-controller: :9090

    for key, value in custom_configs.items():
        if key in cover_configs:
            raw_configs[key] = custom_configs[key]

    #  
    add_configs = ["proxies" , "proxy-groups", "rules"]
    for key, value in custom_configs.items():
        if key in add_configs:
            # print(type(custom_configs[key]))
            if type(custom_configs[key]) is list: 
                for i in custom_configs[key]:
                    raw_configs[key].insert(0, i)

    _finalize_config(raw_configs, rules_template_path, slim_proxy_groups)

    with open(gen_cfg_path,'w') as yamlfile:
        yaml.safe_dump(raw_configs, yamlfile,allow_unicode=True)
    return True