import colorlog
import os
import sys
import yaml
import logging
import argparse
from pathlib import Path
import merge_proxy

_repo = Path(__file__).resolve().parents[2]
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))
from scripts.lib.subscribe import parse_subscribes, persist_default_subscribe  # noqa: E402
from scripts.lib.paths import clash_config_yaml, migrate_legacy_cache_layout, subscribe_cache_dir  # noqa: E402
from scripts.lib.mcs_api_client import request_kernel_reload, request_sync_meta  # noqa: E402
from scripts.lib.v2ray_subscribe import download_and_write_v2ray_config  # noqa: E402

if __name__=="__main__":
    parser = argparse.ArgumentParser(
        description="切换到已配置的订阅名：更新 default_subscribe；cache/current_sub.txt 由 mcs API 同步；Clash 合并写盘；v2ray 下载并写配置；mcs POST /kernel/reload 让子进程加载新配置"
    )
    parser.add_argument("new_subscribe", type=str, help="订阅名（subscribes 下的键）")
    args = parser.parse_args()
    new_subscribe = args.new_subscribe
    # find path
    myclash_root_pwd = os.getenv('MYCLASH_ROOT_PWD') # None
    if myclash_root_pwd is None:
        raise TypeError("[ERROR] 找不到 MYCLASH_ROOT_PWD;请尝试 source ~/.bashrc 后重新运行")
    migrate_legacy_cache_layout(Path(myclash_root_pwd))
    raw_configs_dir = str(subscribe_cache_dir(Path(myclash_root_pwd)))
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


    with open(user_config_path, "r") as stream:
        dictionary = yaml.safe_load(stream)
    if not isinstance(dictionary, dict):
        dictionary = {}
    sub_dict = dictionary.get("subscribes")
    if sub_dict is None:
        raise TypeError("[ERROR] 没有找到订阅信息")
    try:
        subs = parse_subscribes(sub_dict)
    except ValueError as e:
        logger.error(str(e))
        raise SystemExit(1) from e
    if new_subscribe not in subs:
        raise TypeError("[ERROR] 不存在此订阅")
    entry = subs[new_subscribe]
    rules_template_resolved = merge_proxy.resolve_rules_template_path(
        myclash_root_pwd,
        dictionary.get("rules_template") if dictionary else None,
    )
    slim_pg = merge_proxy.slim_proxy_groups_enabled(dictionary)
    if entry.get("backend") == "v2ray":
        logger.info("目标订阅为 v2ray 后端，跳过 Clash 合并")
        v2_url = (entry.get("url") or "").strip()
        if v2_url:
            ok = download_and_write_v2ray_config(
                myclash_root=Path(myclash_root_pwd),
                profile_name=new_subscribe,
                url=v2_url,
                logger=logger,
            )
            if not ok:
                raise SystemExit(1)
        else:
            logger.info("该 v2ray 订阅未填写 url，不修改 mcs/configs/v2ray.json")
    else:
        logger.info("merge {} configs".format(new_subscribe))
        merge_proxy.merge_cfg(
            raw_rule_path=f"{raw_configs_dir}/{new_subscribe}.yaml",
            gen_cfg_path=gen_rule_cfg_pwd,
            user_config_doc=dictionary,
            rules_template_path=rules_template_resolved,
            slim_proxy_groups=slim_pg,
        )
        logger.info("代理更新完成: 使用: {}".format(new_subscribe))
    persist_default_subscribe(Path(user_config_path), new_subscribe)
    if not request_sync_meta(logger=logger):
            logger.warning("未能通过 mcs_manager 同步 cache/current_sub.txt（请确认服务已启动）")
    if request_kernel_reload(logger=logger, root=Path(myclash_root_pwd)):
        logger.info("default_subscribe 已设为 %s，内核已由 mcs_manager API 重载", new_subscribe)
    else:
        logger.info(
            "已将 default_subscribe 设为 %s；热重载不可用时请执行: myclash service restart",
            new_subscribe,
        )