import logging
import colorlog
import os
import subprocess

if __name__=="__main__":



    # find path
    myclash_root_pwd = os.getenv('MYCLASH_ROOT_PWD') # None
    if myclash_root_pwd is None:
        raise TypeError("[ERROR] 找不到 MYCLASH_ROOT_PWD;请尝试 source /etc/bash.bashrc ;source ~/.bashrc 然后重新运行")
    raw_configs_pwd = "{}/clash/raw_configs".format(myclash_root_pwd)
    final_configs_pwd = "{}/clash/final_configs".format(myclash_root_pwd)
    user_config_path = myclash_root_pwd+'/config.yaml'

    # 创建日志记录器
    logger = logging.getLogger("MCS:Change Profile")
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

    # read yaml and find avilable cfg
    download_configs = []
    default_subcribe = None


    profile_names = []
    for filename in os.listdir(raw_configs_pwd):
        file_path = os.path.join(raw_configs_pwd, filename)
        
        # 检查是否是文件（而不是目录）
        if os.path.isfile(file_path):
            profile_names.append(os.path.splitext(os.path.basename(file_path))[0])
    logger.info(f"Available profiles: {profile_names}")