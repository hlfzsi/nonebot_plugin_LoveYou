from . import DATA_DIR
from .others import get_file_lock
from .config import result
from nonebot import logger
import os
from typing import Dict, Tuple
import pandas as pd
import asyncio
import aiofiles
import re
import numpy as np
import random
(
    bot_name, baseline, rate, master,
    search_love_reply, botreact, model, role,
    API_Key, Secret_Key, tank_enable, Ca, Cb,
    lv_enable, La, Lb, Lc, Ld,
    Le, Lf, Lg, Lh, Li, Lj,
    lv1_reply, lv2_reply, lv3_reply, lv4_reply, lv5_reply, memory
) = result

pd.StringDtype('pyarrow')
groups_df: Dict[str, pd.DataFrame] = {}
groups_df_lock = asyncio.Lock()
basePath = os.path.join(DATA_DIR, 'group')
WEIGHTED_CHOICE_PATTERN = re.compile(
    r'%(?P<name>[^%!]+)%'
    r'(?:(?P<R>R:(\d*\.?\d*))?'
    r'(?:(?P<sep1>,)?(?P<L>L:(\d+)))?)?'
    r'!'
)


async def group_del(groupid: str, question: str):
    '''
    删除指定群组的特定触发词记录。

    参数:
    groupid (str): 群号
    question (str): 触发词
    '''
    file_path = os.path.join(basePath, f"{groupid}.csv")

    if groupid in groups_df:
        df = groups_df[groupid]

        # 找到与question完全匹配且Status不为locked的行
        mask = (df['Question'] == question) & (df['Status'] != 'locked')
        rows_to_delete = df[mask].index.tolist()

        # 记录需要删除的图片路径
        pictures_to_delete = []

        for index in sorted(rows_to_delete, reverse=True):
            row = df.iloc[index]
            if '[pic=' in row['Answer']:
                _, path = pic_support(row['Answer'])
                pictures_to_delete.append(path)

            # 删除DataFrame中的行
            df.drop(index, inplace=True)

        # 定义一个异步函数来执行所有 I/O 操作
        async def perform_io_operations(df: pd.DataFrame, pictures_to_delete, file_path):
            # 删除图片
            for path in pictures_to_delete:
                try:
                    os.remove(f'./data/pic/group/{groupid}/{path}')
                except FileNotFoundError:
                    logger.warning(f"文件 {path} 未找到，无法删除。")

            # 将修改后的DataFrame写回CSV文件
            async with aiofiles.open(file_path, 'w', encoding='utf-8') as file:
                await file.write(df.to_csv(index=False, encoding='utf-8'))

            # 更新全局变量groups_df
            async with groups_df_lock:
                groups_df[groupid] = df

        # 获取该文件的锁
        async with await get_file_lock(file_path):
            await perform_io_operations(df, pictures_to_delete, file_path)

        logger.debug('删除成功')
    else:
        logger.warning(f"{file_path} 不存在")


def pic_support(text: str) -> Tuple[str, str]:
    '''返回图片名称'''
    # 正则表达式匹配 [pic=任意图片名.(png|jpg|jpeg)]
    pattern = r'\[pic=(.*?\.(png|jpg|jpeg))\]'

    # 查找所有匹配项
    matches = re.findall(pattern, text)

    # 如果没有找到匹配项，则直接返回原字符串和 None
    if not matches:
        return text, None

    # 只关心第一个匹配项
    path = matches[0][0]

    # 使用 re.sub() 替换掉第一个匹配项
    new_text = re.sub(pattern, '', text, count=1)

    return new_text, path


async def group_write(groupid: str, question: str, answer: str, type: str):
    '''
    在非阻塞的方式下写入群组数据到CSV文件并更新df。

    参数:
    groupid (str): 群号
    question (str): 触发词
    answer (str): 回复
    type (str): 类型。1为精准匹配,2为模糊匹配
    '''
    file_path = os.path.join(basePath, f"{groupid}.csv")

    # 确保目录存在
    os.makedirs(os.path.dirname(file_path), exist_ok=True)

    # 定义一个异步函数来执行所有 I/O 操作
    async def perform_io_operations(file_path):
        global groups_df

        if not os.path.exists(file_path):
            df = pd.DataFrame(
                columns=['Question', 'Answer', 'Love', 'Range', 'Type', 'Status'])
        else:
            df = groups_df.get(groupid, pd.DataFrame())

        # 将新的数据添加到DataFrame中
        new_row = pd.DataFrame([[question, answer, '', '', type, '']],
                               columns=['Question', 'Answer', 'Love', 'Range', 'Type', 'Status'])
        df = pd.concat([df, new_row], ignore_index=True)

        # 将DataFrame写入CSV文件
        async with aiofiles.open(file_path, 'w', encoding='utf-8') as file:
            await file.write(df.to_csv(index=False, encoding='utf-8'))

        # 更新全局变量groups_df
        async with groups_df_lock:
            groups_df[groupid] = df

    # 获取该文件的锁
    async with await get_file_lock(file_path):
        await perform_io_operations(file_path)

    logger.debug('写入成功')


def find_row(groupid: str, question: str) -> list:
    # 从字典中获取DataFrame
    if groupid in groups_df:
        df = groups_df[groupid]
        # 使用列名Question来找到所有匹配的行
        matches = df[df['Question'] == question]
        # 如果找到了匹配的行，返回行号和Answer列的字符串列表
        if not matches.empty:
            # 使用matches.index来获取原始行号，并与Answer值一起构造列表
            logger.debug(f'完成在{groupid}的查找')
            return [f"{idx} : {matches.loc[idx, 'Answer']}" for idx in matches.index]
        else:
            logger.debug(f'完成在{groupid}的查找,但为空')
            return []  # 如果没有找到匹配的行，返回一个空列表
    else:
        logger.warning(f'{groupid}不在词库中')
        return ['当前词库不存在']


async def del_row(groupid: str, row_indices: list):
    if groupid in groups_df:
        # 构造文件路径
        file_path = os.path.join(basePath, f"{groupid}.csv")

        df = groups_df[groupid]

        status_column = df['Status']
        column_with_images = df['Answer']

        # 过滤出row_indices中对应的且不是'locked'的行索引
        rows_to_update = [
            idx for idx in row_indices if idx in df.index and not status_column.iloc[idx] == 'locked']

        # 定义一个异步函数来执行所有 I/O 操作
        async def perform_io_operations(df: pd.DataFrame, rows_to_update, file_path):
            for idx in rows_to_update:
                if idx in df.index:
                    status = status_column.iloc[idx]
                    if not status == 'locked':
                        # 检查图片链接列是否包含'[pic='
                        if '[pic=' in str(column_with_images.iloc[idx]):
                            _, path = pic_support(
                                str(column_with_images.iloc[idx]))
                            os.remove(f'./data/pic/group/{groupid}/{path}')

            # 设置这些行为NaN
            df.loc[rows_to_update] = np.nan

            # 删除所有列都为NaN的行
            df.dropna(how='all', inplace=True)

            # 将修改后的DataFrame保存回文件
            async with aiofiles.open(file_path, 'w', encoding='utf-8') as file:
                await file.write(df.to_csv(index=False, encoding='utf-8'))

            # 更新全局变量groups_df
            async with groups_df_lock:
                groups_df[groupid] = df

            logger.debug(f'完成在{groupid}的行删除')
            return len(rows_to_update), len(row_indices) - len(rows_to_update)

        # 获取该文件的锁
        async with await get_file_lock(file_path):
            result = await perform_io_operations(df, rows_to_update, file_path)

        return result
    else:
        logger.warning(f'{groupid}不在词库中')
        return 0, 0


async def lock_row(groupid: str, rows: list[str], type: int) -> None:
    if groupid in groups_df:
        df = groups_df[groupid]

        # 遍历字符串列表并尝试锁定相应的行
        for row_str in rows:
            # 尝试将字符串转换为整数
            row_int = int(row_str)
            # 检查行号是否有效
            if 0 <= row_int < len(df):
                # 锁定指定行的第六列（使用iloc和整数索引）
                if type == 0:
                    df.iloc[row_int, 5] = 'locked'
                elif type == 1:
                    df.iloc[row_int, 5] = 'unlocked'
            else:
                raise Exception("Row index out of bounds.")

        # 构造文件路径
        file_path = os.path.join(basePath, f"{groupid}.csv")

        # 定义一个异步函数来执行所有 I/O 操作
        async def perform_io_operations(df: pd.DataFrame, file_path):
            # 将修改后的DataFrame保存回文件
            async with aiofiles.open(file_path, 'w', encoding='utf-8') as file:
                await file.write(df.to_csv(index=False, encoding='utf-8'))

            # 更新全局变量groups_df
            async with groups_df_lock:
                groups_df[groupid] = df

            logger.debug(f'完成在{groupid}的锁定修改')

        # 获取该文件的锁
        async with await get_file_lock(file_path):
            await perform_io_operations(df, file_path)

    else:
        logger.warning(f'{groupid}不在词库中')
        raise Exception(f'{groupid}不在词库中')


def load_info(groupid: str, row: int) -> list:
    """获得指定行的详细信息

    Args:
        groupid (str): 群号
        row (int): 行数

    Returns:
        list|None: 正常情况下返回按列排序的list
    """
    if groupid in groups_df:
        df = groups_df[groupid]
        if 0 <= row < len(df):  # 确保行号在DataFrame的行数范围内
            # 读取指定行的所有列内容
            row_data = df.iloc[row].fillna('None').tolist()    # 使用iloc通过整数位置索引
            logger.debug(f'完成在{groupid}的行查找')
            return row_data
        else:
            return None
    else:
        logger.warning(f'{groupid}不在词库中')
        return None


def RL_support(s: str) -> Tuple[str, int]:
    items = []
    total_weight = 0.0

    # 解析字符串并构建items列表
    for match in WEIGHTED_CHOICE_PATTERN.finditer(s):
        item = {
            'name': match.group('name'),
            # R值，默认1.0
            'R': float(match.group('R')[2:] if match.group('R') else '1.0'),
            # L值，默认0
            'L': int(match.group('L')[2:] if match.group('L') else '0')
        }
        total_weight += item['R']
        items.append(item)

    # 如果没有有效的items，返回默认值
    if not items:
        return '', 0

    # 按照权重随机选择
    r = random.random() * total_weight
    for item in items:
        r -= item['R']
        if r <= 0:
            return item['name'], item['L']
    logger.warning('RL出现异常')
    return None, 0


def get_global_reply(search_term: str, m: int) -> Tuple[str, int]:
    """检查词库获得回复

    Args:
        search_term (str): 需要匹配的内容
        m (int): 用户的数值好感度
    Returns:
        Tuple[str,int]: 回复,好感变化值
    """
    # 筛选匹配第一列的行
    matches = df[(df.iloc[:, 4] == '1') & (df.iloc[:, 0] == search_term)]
    if matches.empty:         # 如果没有找到匹配的行，进行模糊匹配
        if len(search_term) <= 90:
            # 使用列表推导式来检查search_term是否包含第一列中的任何字符串
            condition = [str(x) in search_term for x in df.iloc[:, 0]]
            condition = pd.Series(condition, index=df.index)
            matches = df[(df.iloc[:, 4] == '2') &
                         condition]

        else:
            return None, None
    # 模糊匹配无法高效率实现，因此在全局词库中考虑抛弃该功能

    # 过滤掉第四列(c, d)范围不包含m的行，并处理空值
    def is_m_in_range(row):
        cd_str = str(row.iloc[3])
        if cd_str.strip() == "nan" or cd_str.strip() == "":  # 如果为空值或空字符串，则认为m符合范围
            return True
        try:
            c, d = map(int, cd_str.strip('()').split(','))
            return c <= m <= d  # 检查 m 是否在 (c, d) 范围内
        except ValueError:  # 如果无法转换为整数
            return True

    valid_matches = matches.apply(is_m_in_range, axis=1)
    valid_matches = matches[valid_matches]

    # 如果没有找到匹配的行
    if valid_matches.empty:
        return None, None

    # 从有效匹配中随机选择一行
    chosen_row = valid_matches.sample(n=1).iloc[0]

    # 读取第二列作为reply，如果为空则跳过
    reply = chosen_row.iloc[1] if pd.notnull(chosen_row.iloc[1]) else None

    # 读取第三列(a, b)范围，并在范围内随机选择一个整数作为love，处理空值
    ab_str = str(chosen_row.iloc[2])
    if ab_str.strip() == "":  # 如果为空字符串
        love = 0
    else:
        try:
            a, b = map(int, ab_str.strip('()').split(','))
            love = random.randint(a, b)
        except ValueError:
            love = 0
    logger.debug('完成回复配对')
    return reply, love


def groups_reply(groupid, search_term, m):
    """检查词库获得回复

    Args:
        groupid(str):用户对应的群号,用于选择词库
        search_term (str): 需要匹配的内容
        m (int): 用户的数值好感度

    Returns:
        Tuple[str,int]: 回复,好感变化值
    """
    if groupid in groups_df:
        df = groups_df[groupid]
        # 筛选匹配第一列的行
        matches = df[(df.iloc[:, 4] == '1') & (df.iloc[:, 0] == search_term)]
        if matches.empty:         # 如果没有找到匹配的行，进行模糊匹配
            if len(search_term) <= 90:
                # 使用列表推导式来检查search_term是否包含第一列中的任何字符串
                condition = [str(x) in search_term for x in df['Question']]
                condition = pd.Series(condition, index=df.index)
                matches = df[(df['Type'] == '2') &
                             condition]

            else:
                return None, 0

        # 过滤掉第四列(c, d)范围不包含m的行，并处理空值
        def is_m_in_range(row):
            cd_str = str(row.iloc[3])
            if cd_str.strip() == "nan" or cd_str.strip() == "":  # 如果为空值或空字符串，则认为m符合范围
                return True
            try:
                c, d = map(int, cd_str.strip('()').split(','))
                return c <= m <= d  # 检查 m 是否在 (c, d) 范围内
            except ValueError:  # 如果无法转换为整数
                return True

        # 假设 matches 是一个pandas DataFrame，且第四列是字符串形式的范围，如"(1, 5)"
        # 或者第四列可能包含空值或无法转换为整数的字符串
        valid_matches = matches.apply(is_m_in_range, axis=1)
        valid_matches = matches[valid_matches]
        if valid_matches.empty:
            return None, None

        if valid_matches.empty:
            return None, None

        # 从有效匹配中随机选择一行
        chosen_row = valid_matches.sample(n=1).iloc[0]

        # 读取第二列作为reply，如果为空则跳过
        reply = chosen_row.iloc[1] if pd.notnull(chosen_row.iloc[1]) else None

        # 读取第三列(a, b)范围，并在范围内随机选择一个整数作为love，处理空值
        ab_str = str(chosen_row.iloc[2])
        if ab_str.strip() == "":  # 如果为空字符串
            love = 0
        else:
            try:
                a, b = map(int, ab_str.strip('()').split(','))
                love = random.randint(a, b)
            except ValueError:  # 如果无法转换为整数
                love = 0
        return reply, love
    else:
        return None, 0


def read_csv_files_to_global_dict(directory=os.path.join(DATA_DIR, 'group')):
    # 遍历目录中的所有文件
    for filename in os.listdir(directory):
        # 检查文件是否为CSV文件
        if filename.endswith('.csv'):
            # 去除后缀以获取groupid
            groupid = os.path.splitext(filename)[0]
            # 构造文件路径
            file_path = os.path.join(directory, filename)
            # 读取CSV文件到DataFrame
            df = pd.read_csv(file_path, dtype=str,
                             usecols=range(6), encoding='utf-8')
            df.iloc[:, 4] = df.iloc[:, 4].fillna('1')
            # 将DataFrame添加到全局字典中，以groupid为键
            groups_df[groupid] = df


def init_wordbank():
    """初始化词库功能"""
    logger.info('正在初始化词库...')
    global df
    df = pd.read_csv(os.path.join(DATA_DIR, 'reply.csv'), header=None, dtype=str,
                     usecols=range(5), encoding='utf-8')
    df.iloc[:, 4] = df.iloc[:, 4].fillna('1')
    df.iloc[:, 2] = df.iloc[:, 2].fillna(f'({Ca},{Cb})')
    read_csv_files_to_global_dict()
    logger.info('词库初始化完成')
