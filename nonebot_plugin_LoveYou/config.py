from . import DATA_DIR
from nonebot import logger
import toml
import os
import time


def loadconfig():
    config_path = os.path.join(DATA_DIR, "LoveYou_config.toml")
    try:
        with open(config_path, "r", encoding='utf-8') as config_file:
            config = toml.load(config_file)
            logger.info('正在加载config.toml')
    except FileNotFoundError:
        logger.error(f'无法加载{config_path}，请检查文件是否存在或格式是否正确')
        import sys
        time.sleep(5)
        sys.exit(1)

    # 读取 random_CG 配置
    baseline: int = config['random_CG']['baseline']
    rate: float = config['random_CG']['rate']

    # 读取 others 配置
    bot_name: str = config['others']['bot_name']
    master: int = config['others']['master']
    search_love_reply: bool = config['others']['search_love_reply']
    tank_enable: bool = config['others']['tank_enable']

    # 读取 csv 配置
    common_love: str = config['csv']['common_love']
    Ca, Cb = (value.strip() for value in common_love.split(','))

    # 读取 ai 配置
    botreact: bool = config['ai']['enable']
    model: str = config['ai']['model']
    role: str = config['ai']['role']
    API_Key: str = config['ai']['API_Key']
    Secret_Key: str = config['ai']['Secret_Key']
    memory: bool = config['ai']['memory']

    # 读取 lv 配置
    lv_enable: bool = config['lv']['enable']
    lv1: str = config['lv']['lv1']
    lv2: str = config['lv']['lv2']
    lv3: str = config['lv']['lv3']
    lv4: str = config['lv']['lv4']
    lv5: str = config['lv']['lv5']

    lv1_reply: str = config['lv']['lv1_reply'].replace('\\n', '\n')
    lv2_reply: str = config['lv']['lv2_reply'].replace('\\n', '\n')
    lv3_reply: str = config['lv']['lv3_reply'].replace('\\n', '\n')
    lv4_reply: str = config['lv']['lv4_reply'].replace('\\n', '\n')
    lv5_reply: str = config['lv']['lv5_reply'].replace('\\n', '\n')

    a, b = (int(value.strip()) for value in lv1.split(','))
    c, d = (int(value.strip()) for value in lv2.split(','))
    e, f = (int(value.strip()) for value in lv3.split(','))
    g, h = (int(value.strip()) for value in lv4.split(','))
    i, j = (int(value.strip()) for value in lv5.split(','))

    logger.info('config.toml已成功加载')

    return (
        bot_name, baseline, rate, master,
        search_love_reply, botreact, model, role,
        API_Key, Secret_Key, tank_enable, Ca, Cb,
        lv_enable, int(a), int(b), int(c), int(d),
        int(e), int(f), int(g), int(h), int(i), int(j),
        lv1_reply, lv2_reply, lv3_reply, lv4_reply, lv5_reply, memory
    )


result = loadconfig()
