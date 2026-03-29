#!/usr/bin/env python3
import sys
import yaml
import getpass
import os

class InvalidPathError(Exception):
    """自定义异常，用于处理无效的文件路径"""
    pass

def check_yaml_path(path):
    if not path.endswith('.yaml'):
        raise InvalidPathError(f"路径 {path} 不是以 .yaml 结尾的文件路径！")
    return True
def merge_cfg(raw_rule_path,custum_rule_path,gen_cfg_path):
    '''
    通过下载的profile和自定义的规则生成最终使用的规则

    参数:
    raw_rule_path: 下载的规则路径 .yaml 结尾
    custum_rule_path: 自定义规则路径 .yaml 结尾
    gen_rule_path: 生成的新profile路径 .yaml 结尾
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
        with open(gen_cfg_path,'w') as yamlfile:
            yaml.safe_dump(raw_configs, yamlfile,allow_unicode=True)
        return True
    # 读取 custom_rule
    custom_configs_stream = open(custum_rule_path, "r",encoding='utf-8')
    custom_configs = yaml.safe_load(custom_configs_stream)
    # 如果custom_rule是空的，直接复制raw，然后退出
    if(custom_configs is None):
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

    with open(gen_cfg_path,'w') as yamlfile:
        yaml.safe_dump(raw_configs, yamlfile,allow_unicode=True)
    return True