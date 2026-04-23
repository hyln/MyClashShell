#!/usr/bin/python
"""``myclash service update_subcribe`` 调用的订阅更新逻辑。

阶段 1 — 更新 **全部** ``subscribes`` 到 cache（与 ``default_subscribe`` 无关）：

- ``backend: clash``：下载到 ``cache/<订阅名>.yaml``；
- ``backend: v2ray``：下载解析后写入 ``cache/<订阅名>.json``。

阶段 2 — **仅**根据 ``default_subscribe`` 解析出的默认项，载入 **mcs** 磁盘配置：

- 默认项为 ``clash``：合并该条（或回退）到 ``mcs/configs/config.yaml``；
- 默认项为 ``v2ray``：将 ``cache/<默认订阅名>.json`` **复制**到 ``mcs/configs/v2ray.json``（阶段 1 已为每条 v2ray 写好各自 cache）。

阶段 2 结束后调用 ``POST /kernel/sync_meta`` 与 ``POST /kernel/reload``，由 mcs 重启子进程加载上述文件（不再使用 Clash 9090 REST 热替换）。

由 ``mcs_manager`` 读 ``user_config`` 默认项的 ``backend`` 决定实际拉起 Clash 还是 v2ray；本脚本阶段 2 负责与之一致的 mcs 主配置。
"""
import shutil
import subprocess, sys
from pathlib import Path

import os
import warnings 
import traceback
import yaml
import util
import merge_proxy
import logging
import colorlog

_repo = Path(__file__).resolve().parents[2]
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))
from scripts.lib.paths import clash_config_yaml, download_cache_dir, mcs_configs_dir  # noqa: E402
from scripts.lib.subscribe import (  # noqa: E402
    parse_subscribes,
    resolve_default_subscribe_name,
)
from scripts.lib.mcs_api_client import request_kernel_reload, request_sync_meta  # noqa: E402
from scripts.lib.v2ray_subscribe import (  # noqa: E402
    download_v2ray_subscription_outbounds,
    refresh_v2ray_json_listen_from_user_config,
    write_v2ray_json_from_outbounds,
)

def download_profile(profile_name:str,url:str):
    '''
    下载profile
    '''
    full_url = f"{url}&flag=clash"

    logger.info(f'{profile_name} : "{full_url}"')

    cache_cfg_path = raw_configs_dir + f"/{profile_name}.yaml"
    download_configs_cmd= f'unset http_proxy https_proxy;curl -o {cache_cfg_path} -k -L --max-time 20 -H "User-Agent: ClashForWindows/0.20.5" "{full_url}"'
    # -k 取消校验
    # --max-time 10 设置超时
    print(download_configs_cmd)
    result = subprocess.run(download_configs_cmd, shell=True, capture_output=True, text=True)
    # print(result.returncode)
    if result.returncode != 0:
        logger.debug(result.stdout.strip())
        logger.error(f"Download {profile_name} failed")
        print(result.stdout.strip())
        return False
    # 检查yaml文件是否合法且包含关键字
    try:
        with open(cache_cfg_path, "r") as f:
            cfg_data = yaml.safe_load(f)
        # 检查是否包含关键字（如 'proxies', 'proxy-groups', 'rules'）
        required_keys = ['proxies', 'proxy-groups', 'rules']
        if not any(key in cfg_data for key in required_keys):
            logger.error(f"{profile_name} 配置文件缺少关键字段，你的订阅可能已过期或不支持 Clash,也请检查网络连接是否正常")
            return False
    except Exception as e:
        logger.error(f"{profile_name} 配置文件解析失败: {e}")
        return False

    #  asset config is already download
    result = subprocess.run("find "+cache_cfg_path, shell=True, capture_output=True, text=True)
    if result.returncode == 0:
        # print(result.stdout.strip())
        logger.info(f"Download {profile_name} success")
        return True
        # Get the size of the file in bytes
        # file_size = os.path.getsize(cache_cfg_path)
        # print(f"The size of the file is: {file_size} bytes")
    else:
        logger.error(f"Download {profile_name} failed")
        return False

    
if __name__=="__main__":

    # find path
    myclash_root_pwd = os.getenv('MYCLASH_ROOT_PWD') # None
    if myclash_root_pwd is None:
        raise TypeError("[ERROR] 找不到 MYCLASH_ROOT_PWD;请尝试 source ~/.bashrc 后重新运行")
    raw_configs_dir = str(download_cache_dir(Path(myclash_root_pwd)))
    Path(raw_configs_dir).mkdir(parents=True, exist_ok=True)
    gen_rule_cfg_pwd = str(clash_config_yaml(Path(myclash_root_pwd)))
    user_config_path = myclash_root_pwd+'/user_config.yaml'

    # 创建日志记录器
    logger = logging.getLogger("MCS:Update Profile")
    logger.setLevel(logging.INFO)
    # 创建一个控制台输出处理器，并且配置颜色
    console_handler = logging.StreamHandler()

    # 配置日志格式和颜色
    formatter = colorlog.ColoredFormatter(
        '%(log_color)s%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        log_colors={
            'DEBUG': 'blue',
            'INFO': 'green',
            'WARNING': 'yellow',
            'ERROR': 'red',
            'CRITICAL': 'bold_red',
        }
    )

    console_handler.setFormatter(formatter)

    # 创建文件处理器
    file_handler = logging.FileHandler(myclash_root_pwd+'/app.log')
    file_handler.setFormatter(formatter)

    # 将处理器添加到记录器
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)


    # logger.info("1. Delete Download Configs")
    # subprocess.run("rm -rf {}".format(raw_configs_dir), shell = True, executable="/bin/bash")
    # subprocess.run("mkdir {}".format(raw_configs_dir), shell = True, executable="/bin/bash")
    # print(subprocess.run("rm -rf {}".format(raw_configs_dir), shell = True, executable="/bin/bash").returncode)
    # print(subprocess.run("mkdir {}".format(raw_configs_dir), shell = True, executable="/bin/bash").returncode)
    # print("download new raw_config")

    # 读取 user_config
    download_configs: list[str] = []
    default_subscribe = None
    rules_template_resolved = None
    slim_pg = False
    subs: dict[str, dict[str, str]] = {}
    with open(user_config_path, "r") as stream:
        dictionary = yaml.safe_load(stream)
        rules_template_resolved = merge_proxy.resolve_rules_template_path(
            myclash_root_pwd,
            dictionary.get("rules_template") if dictionary else None,
        )
        slim_pg = merge_proxy.slim_proxy_groups_enabled(dictionary)
        default_subscribe = dictionary.get("default_subscribe")
        sub_dict = dictionary.get("subscribes")
        if sub_dict is None:
            raise TypeError("[ERROR] 没有找到订阅信息")
        try:
            subs = parse_subscribes(sub_dict)
        except ValueError as e:
            logger.error(str(e))
            sys.exit(1)
        if not subs:
            raise TypeError("[ERROR] subscribes 为空或无效")

    effective = resolve_default_subscribe_name(subs, default_subscribe)
    eff_backend = subs.get(effective, {}).get("backend") if effective else ""

    root = Path(myclash_root_pwd)

    # --- 阶段 1：全部 subscribes → cache ---
    logger.info("==== 阶段 1：更新全部 subscribes 到 cache（与 default_subscribe 无关）====")
    for key, entry in subs.items():
        if entry.get("backend") != "clash":
            continue
        url = entry.get("url") or ""
        if util.is_valid_url(url):
            ret = download_profile(key, url)
            if ret:
                download_configs.append(key)
        else:
            logger.error(f"invalid clash subscribe url {key}: {url!r}")

    for key, entry in subs.items():
        if entry.get("backend") != "v2ray":
            continue
        v2_url = (entry.get("url") or "").strip()
        if not v2_url:
            logger.info('v2ray 订阅 "%s" 未填写 url，跳过', key)
            continue
        obs = download_v2ray_subscription_outbounds(
            myclash_root=root,
            profile_name=key,
            url=v2_url,
            logger=logger,
        )
        if not obs:
            if key == effective and eff_backend == "v2ray":
                sys.exit(1)
            logger.warning('v2ray 订阅 "%s" 下载或解析失败，跳过', key)
            continue
        write_v2ray_json_from_outbounds(
            myclash_root=root,
            profile_name=key,
            outbounds=obs,
            logger=logger,
            write_mcs=False,
            include_mcs=key == effective and eff_backend == "v2ray",
        )

    for key, entry in subs.items():
        if entry.get("backend") != "v2ray":
            continue
        refresh_v2ray_json_listen_from_user_config(
            myclash_root=root,
            profile_name=key,
            logger=logger,
            write_mcs=False,
            include_mcs=key == effective and eff_backend == "v2ray",
        )

    # --- 阶段 2：仅默认项 → mcs ---
    logger.info(
        "==== 阶段 2：按 default_subscribe 载入 mcs（默认=%s backend=%s）====",
        effective or "?",
        eff_backend or "?",
    )
    if eff_backend == "v2ray":
        logger.info("默认后端为 v2ray：不写 config.yaml")
        eff_v2_url = (subs.get(effective, {}).get("url") or "").strip()
        if eff_v2_url:
            cache_json = download_cache_dir(root) / f"{effective}.json"
            if not cache_json.is_file():
                logger.error(
                    "默认 v2ray 订阅应有 cache 文件 %s（阶段 1 应已生成），中止",
                    cache_json,
                )
                sys.exit(1)
            mcs_json = mcs_configs_dir(root) / "v2ray.json"
            mcs_json.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(cache_json, mcs_json)
            logger.info("已从 %s 载入 mcs/configs/v2ray.json", cache_json)
        else:
            logger.info("默认 v2ray 订阅未填写 url，跳过载入 mcs/configs/v2ray.json（其它 v2ray 项仍可能已更新 cache）")
    elif eff_backend == "clash" and download_configs:
        logger.info("==== Gen Clash Config（仅默认 clash 合并入 mcs）====")
        merge_key = effective if effective in download_configs else download_configs[0]
        if merge_key != effective:
            logger.warning(
                "默认订阅 %s 的 Clash 配置未下载成功，改用 %s",
                effective,
                merge_key,
            )
        logger.info("merge {} configs".format(merge_key))
        merge_proxy.merge_cfg(
            raw_rule_path=f"{raw_configs_dir}/{merge_key}.yaml",
            gen_cfg_path=gen_rule_cfg_pwd,
            user_config_doc=dictionary,
            rules_template_path=rules_template_resolved,
            slim_proxy_groups=slim_pg,
        )
        logger.info("代理更新完成: 使用: {}".format(merge_key))
    else:
        logger.error("没有找到任何可用的 Clash 订阅下载（当前默认订阅为 clash 后端时需成功下载）")
        sys.exit(1)
    if not request_sync_meta(logger=logger):
        logger.warning(
            "未能通过 mcs_manager POST /kernel/sync_meta 更新 cache/current_sub.txt（服务未启动时可忽略）"
        )
    if not request_kernel_reload(logger=logger, root=root):
        logger.warning(
            "未能通过 mcs_manager POST /kernel/reload 重载内核（服务未启动时可忽略；已启动时请执行 myclash service restart）"
        )
