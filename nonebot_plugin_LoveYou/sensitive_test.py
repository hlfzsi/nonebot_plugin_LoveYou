import os
from pygtrie import Trie
from nonebot import logger
from opencc import OpenCC
import jieba
from .config import result
from . import DATA_DIR
(
    bot_name, baseline, rate, master,
    search_love_reply, botreact, model, role,
    API_Key, Secret_Key, tank_enable, Ca, Cb,
    lv_enable, La, Lb, Lc, Ld,
    Le, Lf, Lg, Lh, Li, Lj,
    lv1_reply, lv2_reply, lv3_reply, lv4_reply, lv5_reply, memory
) = result
path = os.path.join(DATA_DIR, "forbidden/")


def load_sensitive_words(directory=path):
    """从目录下的所有.txt文件加载敏感词，并构建Trie树"""
    trie = Trie()
    for filename in os.listdir(directory):
        if filename.endswith('.txt'):
            filepath = os.path.join(directory, filename)
            with open(filepath, 'r', encoding='utf-8') as file:
                words = [line.strip() for line in file]
                for word in words:
                    # 存储敏感词及其来源文件名
                    trie[word] = filename
    return trie


sensitive_trie = load_sensitive_words()
logger.info('违禁词汇构建完成')
text_cc = OpenCC('t2s')


def sensitive_word(text: str) -> str:
    """在分词后的文本中查找第一个敏感词及其来源文件名"""
    text = text.replace(' ', '')
    text = text_cc.convert(text)
    trie = sensitive_trie
    for word in jieba.cut(text):
        if word in trie:
            # 返回第一个找到的敏感词及其来源文件名
            return trie[word]
    # 如果没有找到任何敏感词，返回None
    return None
