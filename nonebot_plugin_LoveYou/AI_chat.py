from . import DATA_DIR
import qianfan
import json
import urllib
import requests
import os
import asyncio
from concurrent.futures import ThreadPoolExecutor
import aiofiles
from nonebot import logger
from datetime import datetime, timedelta
from .config import result
from .love_manager import replace_qq
import snownlp
import random
import math
import jieba
from collections import defaultdict

(
    bot_name, baseline, rate, master,
    search_love_reply, botreact, model, role,
    API_Key, Secret_Key, tank_enable,  Ca, Cb,
    lv_enable, La, Lb, Lc, Ld,
    Le, Lf, Lg, Lh, Li, Lj,
    lv1_reply, lv2_reply, lv3_reply, lv4_reply, lv5_reply, memory
) = result


MAX_AGE = timedelta(minutes=60)  # 消息的有效时间为60分钟
previous_msgs = defaultdict(datetime)
qianfan.disable_log()
executor = ThreadPoolExecutor(max_workers=4)


async def qingyunke(msg: str):
    url = 'http://api.qingyunke.com/api.php?key=free&appid=0&msg={}'.format(
        urllib.parse.quote(msg))

    loop = asyncio.get_running_loop()
    response = await loop.run_in_executor(executor, requests.get, url)

    return response.json()["content"]


async def baidu_ai(msg: str, qq: str, intlove, name: str, lv='Unknown') -> str:
    '''
    通过百度模型获得ai回复
    '''
    intlove = str(intlove)
    name = await replace_qq(qq)
    time = datetime.now()
    time = time.strftime("%Y-%m-%d.%H:%M")
    local_role = role
    local_role = local_role.replace(
        '[intlove]', intlove).replace('[sender]', name).replace('[time]', time)
    if lv != 'Unknown':
        local_role = local_role.replace('[lv]', str(lv))
    if memory:
        send_msg = await chat_memory(qq, msg, '')
        while len(send_msg) + len(local_role) >= 20000:
            await reduce_memory(qq)
            send_msg = await chat_memory(qq, msg, '')
        loop = asyncio.get_running_loop()
        resp = await loop.run_in_executor(executor, lambda: qianfan.ChatCompletion().do(
            model=model,
            messages=send_msg,
            temperature=0.95,
            top_p=0.7,
            penalty_score=1,
            system=local_role,
            show_total_latency=True
        ))
        try:
            if msg != '你有什么想对我说的话':
                await chat_memory(qq, msg, resp['result'])
            if resp['need_clear_history']:
                await clear_memory(qq)
                logger.debug('清理用户记忆')
        except:
            pass

    else:
        loop = asyncio.get_running_loop()
        resp = await loop.run_in_executor(executor, lambda: qianfan.ChatCompletion().do(
            model=model,
            messages=send_msg,
            temperature=0.95,
            top_p=0.7,
            penalty_score=1,
            system=local_role,
            show_total_latency=True
        ))
    return resp['result']


async def clear_memory(qq: str):
    file_path = os.path.join(DATA_DIR, "memory", f'{qq}.json')
    try:
        os.remove(file_path)
    except FileNotFoundError:
        pass


async def reduce_memory(qq: str):
    file_path = os.path.join(DATA_DIR, "memory", f'{qq}.json')
    try:
        async with aiofiles.open(file_path, 'r', encoding='utf-8') as file:
            data = json.loads(await file.read())

        del data[:2]

        async with aiofiles.open(file_path, 'w', encoding='utf-8') as file:
            await file.write(json.dumps(data, ensure_ascii=False, indent=4))
    except FileNotFoundError:
        pass


async def chat_memory(qq: str, question: str, answer: str):
    """处理用户对话

    如果answer为空,则只添加question并返回字符串.文件不保留.

    如果answer非空,无return,保留修改

    Args:
        qq (str): 用户
        question (str): 用户消息
        answer (str): 回复消息
    """
    # 构造文件路径
    file_path = os.path.join(DATA_DIR, "memory", f'{qq}.json')

    # 确保目录存在
    os.makedirs(os.path.dirname(file_path), exist_ok=True)

    # 初始化聊天记录列表，如果文件不存在则为空列表
    try:
        async with aiofiles.open(file_path, 'r', encoding='utf-8') as file:
            records = json.loads(await file.read())
    except FileNotFoundError:
        records = []

    # 如果answer不是空字符串，则添加新的聊天记录
    if answer:  # 检查answer是否为非空字符串
        records.append({"role": "user", "content": question})
        records.append({"role": "assistant", "content": answer})
        async with aiofiles.open(file_path, 'w', encoding='utf-8') as file:
            await file.write(json.dumps(records, ensure_ascii=False, indent=4))
        return None
    else:
        records.append({"role": "user", "content": question})
        return records


def map_sentiment_to_range(sentiment_score, target_min=-10, target_max=10):
    # 线性映射函数，但调整斜率使得中间区域变化小，极端值变化大
    if sentiment_score >= 0.54:
        # 正面情感，使用较缓的斜率
        mapped_score = (sentiment_score - 0.5) * 2 * (target_max -
                                                      target_min) + target_min + (target_max - target_min) / 2.41
    elif sentiment_score <= 0.46:
        mapped_score = (sentiment_score - 0.6) * 2 * (target_max -
                                                      target_min) + target_min + (target_max - target_min) / 2.41
    else:
        mapped_score = (sentiment_score - 0.5) * 2 * (target_max -
                                                      target_min) + target_min + (target_max - target_min) / 2.41

    # 确保值在目标范围内
    mapped_score = max(min(mapped_score, target_max), target_min)
    return mapped_score


def add_random_fluctuation(score, target_min, target_max):
    # 添加一个固定的随机波动在[-1, 1]范围内
    fluctuation = random.uniform(-1, 1)
    fluctuated_score = max(
        min(score + fluctuation, target_max), target_min)  # 确保值在目标范围内
    return fluctuated_score


def adjust_score_if_high(score, threshold, deduction_range):
    # 如果得分大于等于阈值，则随机减去一个整数
    if score >= threshold:
        deduction = random.randint(deduction_range[0], deduction_range[1])
        score -= deduction
        score = math.floor(score)
    return score


def adjust_score_if_low(score, threshold, deduction_range):
    # 如果得分小于等于阈值，则随机加上一个整数
    if score <= threshold:
        deduction = random.randint(deduction_range[0], deduction_range[1])
        score += deduction
        score = math.floor(score)
    return score


def love_score(text: str, target_min=-10, target_max=10):
    # 使用 SnowNLP 分析文本情感倾向
    s = snownlp.SnowNLP(text)
    sentiment_score = s.sentiments

    # 映射情感倾向
    mapped_score = map_sentiment_to_range(
        sentiment_score, target_min, target_max)

    # 添加随机波动
    fluctuated_score = add_random_fluctuation(
        mapped_score, target_min, target_max)
    fluctuated_score = adjust_score_if_high(fluctuated_score, 7, [0, 7])
    final_score = adjust_score_if_low(fluctuated_score, -7, [0, 7])
    final_score = int(final_score)

    # 返回结果
    return final_score


def tokenize(text):
    return list(jieba.cut(text, cut_all=False))


def new_msg_judge(msg, jaccard_threshold=0.6):
    # 使用结巴库进行分词
    tokens = tokenize(msg)

    # 清理过期的消息
    current_time = datetime.now()
    for prev_msg, timestamp in list(previous_msgs.items()):
        if (current_time - timestamp) >= MAX_AGE:
            del previous_msgs[prev_msg]

    # 检查当前消息是否与先前的消息高度相似
    for prev_msg, timestamp in previous_msgs.items():
        prev_tokens = tokenize(prev_msg)
        jaccard_sim = jaccard_similarity(tokens, prev_tokens)
        if jaccard_sim >= jaccard_threshold:
            return False  # 如果找到高度相似的msg且在MAX_AGE内，返回False

    # 如果没有找到高度相似的msg，将其添加到previous_msgs字典中
    previous_msgs[msg] = datetime.now()
    return True


def jaccard_similarity(list1, list2):
    intersection = len(set(list1).intersection(set(list2)))
    union = len(set(list1)) + len(set(list2)) - intersection
    return intersection / union if union else 0
