#!/usr/bin/env python3
import sys
import yaml
import getpass
import os

############
# arg 1 input config index
config_index = sys.argv[1]

############
# print ("Number of arguments:", len(sys.argv), "arguments")
# print ("Argument List:", str(sys.argv))
EXEC_DIR = os.getenv('MYCLASH_ROOT_PWD')
# print(EXEC_DIR)
raw_configs_stream = open(EXEC_DIR+'/clash/configs/raw_config_{}.yaml'.format(config_index), "r",encoding='utf-8')
# raw_configs_stream = open(EXEC_DIR+'/clash/configs/config.yaml', "r",encoding='utf-8')

raw_configs = yaml.safe_load(raw_configs_stream)

custom_configs_stream = open(EXEC_DIR+'/config_custom.yaml', "r",encoding='utf-8')
# custom_configs_stream = open(EXEC_DIR+'/config.yaml', "r",encoding='utf-8')

custom_configs = yaml.safe_load(custom_configs_stream)

# cover
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
        # print(key ,raw_configs[key])


# add
add_configs = ["proxies" , "proxy-groups", "rules"]

for key, value in custom_configs.items():
    if key in add_configs:
        # print(type(custom_configs[key]))
        if type(custom_configs[key]) is list: 
            for i in custom_configs[key]:
                raw_configs[key].insert(0, i)
                # if(i):

                # else:
                #     raw_configs[key].append(i)

with open(EXEC_DIR+'/clash/configs/config.yaml','w') as yamlfile:
    yaml.safe_dump(raw_configs, yamlfile,allow_unicode=True)
