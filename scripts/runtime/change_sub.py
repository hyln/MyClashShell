import colorlog
import os
import yaml
import logging
import argparse
import util
import merge_proxy

if __name__=="__main__":
    parser = argparse.ArgumentParser(description="Change subscription URL")
    parser.add_argument("new_subscribe", type=str, help="New subscription URL")
    args = parser.parse_args()
    new_subscribe = args.new_subscribe
    # find path
    myclash_root_pwd = os.getenv('MYCLASH_ROOT_PWD') # None
    if myclash_root_pwd is None:
        raise TypeError("[ERROR] 找不到 MYCLASH_ROOT_PWD;请尝试 source /etc/bash.bashrc ;source ~/.bashrc 然后重新运行")
    raw_configs_dir = "{}/tmp".format(myclash_root_pwd)
    custom_cfgs_dir = "{}/custom_configs".format(myclash_root_pwd)
    gen_rule_cfg_pwd = "{}/clash/configs/config.yaml".format(myclash_root_pwd)
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



    download_configs = []
    default_subcribe = None
    with open(user_config_path, "r") as stream:
        try:
            dictionary = yaml.safe_load(stream)
            sub_dict = dictionary.get("subscribes")
            if(sub_dict is None):
                raise TypeError("[ERROR] 没有找到订阅信息")
            if(new_subscribe not in sub_dict):
                raise TypeError("[ERROR] 不存在此订阅")
            custum_proxy_path = myclash_root_pwd + "/custom_configs"
            logger.info("merge {} configs".format(new_subscribe))
            merge_proxy.merge_cfg(
                raw_rule_path=f"{raw_configs_dir}/{new_subscribe}.yaml",
                custum_rule_path=f"{custum_proxy_path}/{new_subscribe}.yaml",
                gen_cfg_path=gen_rule_cfg_pwd
            )
            logger.info("代理更新完成: 使用: {}".format(new_subscribe))
            util.update_config_by_api(gen_rule_cfg_pwd)
            with open(f"{raw_configs_dir}/current_sub.txt", "w") as file:
                file.write(new_subscribe)
            
        except SystemExit:
            print("更新失败，请检查配置文件")
            pass