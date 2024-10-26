import asyncio
import json
import aiofiles
import aiosqlite
import os
from . import DATA_DIR
from nonebot import logger
from contextlib import contextmanager
from pathlib import Path
from datetime import datetime
from typing import Optional, List

from .others import get_file_lock
from .config import result
(
    bot_name, baseline, rate, master,
    search_love_reply, botreact, model, role,
    API_Key, Secret_Key, tank_enable,  Ca, Cb,
    lv_enable, La, Lb, Lc, Ld,
    Le, Lf, Lg, Lh, Li, Lj,
    lv1_reply, lv2_reply, lv3_reply, lv4_reply, lv5_reply, memory
) = result

db_path = os.path.join(DATA_DIR, 'DataBase', 'users', 'qq.db3')


class AdminManager:
    '''词库和漂流瓶管理'''

    def __init__(self, filename=os.path.join(DATA_DIR, 'admin.json')):
        self.filename = filename
        self.lock = asyncio.Lock()
        self.admin_data = self.load_admin()

    def load_admin(self):
        """加载管理员数据"""
        try:
            with open(self.filename, 'r') as file:
                return json.load(file, strict=False)
        except FileNotFoundError:
            return {}

    async def save_admin(self):
        """异步保存管理员数据到文件"""
        async with self.lock:  # 加锁
            try:
                async with aiofiles.open(self.filename, mode='w') as file:
                    await file.write(json.dumps(self.admin_data, indent=4))
            except Exception as e:
                logger.error(f"Error saving admin data: {e}")

    async def write_admin(self, groupid, type_, qq, db_path=None):
        """向指定组ID添加管理员"""
        if type_ not in ['high', 'common']:
            raise ValueError("Invalid type. It should be 'high' or 'common'.")

        if groupid not in self.admin_data:
            self.admin_data[groupid] = {'high': [], 'common': []}

        if self.check_admin(groupid, qq) != False:
            logger.debug(f'{qq}已经是{groupid}的管理员')
            return
        if db_path:
            async with aiosqlite.connect(db_path) as conn:
                cursor = await conn.cursor()

                # 查询qq是否存在于qq_love表中
                await cursor.execute("SELECT * FROM qq_love WHERE QQ=?", (qq,))
                result = await cursor.fetchone()

                if not result:
                    logger.debug(f'不存在{qq}用户,无法添加管理')
                    return

        self.admin_data[groupid][type_].append(qq)
        await self.save_admin()

    async def del_admin(self, groupid, qq):
        """从普通管理员列表中移除管理员"""
        await self._del_from_list(groupid, 'common', qq)

    async def del_admin_high(self, groupid, qq):
        """从高级管理员列表中移除管理员"""
        await self._del_from_list(groupid, 'high', qq)

    async def _del_from_list(self, groupid, list_type, qq):
        """通用的删除方法"""
        if groupid in self.admin_data and list_type in self.admin_data[groupid]:
            if qq in self.admin_data[groupid][list_type]:
                self.admin_data[groupid][list_type].remove(qq)
                await self.save_admin()

    def check_admin(self, groupid, qq):
        """检查给定QQ是否是管理员及其类型"""
        if groupid in self.admin_data:
            if qq in self.admin_data[groupid]['high']:
                return 'high'
            elif qq in self.admin_data[groupid]['common']:
                return 'common'
        return False


class MsgManager:
    """
    异步实现超管信息向用户/群聊 定向/不定向 传递
    """

    def __init__(self, filename: str = os.path.join(DATA_DIR, 'Msg_Transmitter.json')):
        self.filename = filename
        self.data = {}
        self.lock = asyncio.Lock()
        asyncio.create_task(self.load_data())

    async def load_data(self):
        try:
            if os.path.exists(self.filename):
                async with aiofiles.open(self.filename, mode='r', encoding='utf-8') as file:
                    self.data = json.loads(await file.read())
        except Exception as e:
            logger.warning(f"Error loading data from {self.filename}: {e}")

    async def save_data(self):
        try:
            async with aiofiles.open(self.filename, mode='w', encoding='utf-8') as file:
                await file.write(json.dumps(self.data, ensure_ascii=False, indent=4))
        except Exception as e:
            logger.warning(f"Error saving data to {self.filename}: {e}")

    @contextmanager
    def auto_save(self):
        try:
            yield
            asyncio.create_task(self.save_data())
        except Exception as e:
            logger.warning(f"Error during auto save: {e}")

    async def get_Msg(self, qq=None, groupid=None) -> str:
        '''异步尝试根据QQ和groupid获得消息'''
        async with self.lock:
            key = self._get_key(qq, groupid)
            keys_priority = [key, f"{qq}:*", f"*:{groupid}", 'WILDCARD']
            for k in keys_priority:
                if k in self.data:
                    value = self.data.pop(k)
                    with self.auto_save():
                        pass  # 触发数据保存
                    return str(value)
        return None
    
    async def get_and_send_Msg(self,bot,event,qq=None, groupid=None):
        reply = await self.get_Msg(qq, groupid)
        if reply:
            await bot.send(event, f'\n主人有话给您:\n{reply}')

    async def set_Msg(self, qq=None, value=None, groupid=None):
        '''异步设置消息'''
        async with self.lock:
            key = self._get_key(qq, groupid)
            if self.data.get(key) != value:
                self.data[key] = value
                with self.auto_save():
                    pass  # 触发数据保存

    def _get_key(self, qq=None, groupid=None):
        # 键生成逻辑，包含通配符
        if qq is None and groupid is None:
            return 'WILDCARD'
        elif groupid is None:
            return f"{qq}:*"
        elif qq is None:
            return f"*:{groupid}"
        else:
            return f"{qq}:{groupid}"


async def super_admin_record(a: str) -> None:
    """
    获取当前时间，并格式化为字符串（精确到秒），然后异步地将包含当前时间和传入字符串a的消息追加到文件中。
    """
    # 获取当前时间，并格式化为字符串（精确到秒）
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # 构建要写入文件的字符串，包括时间和传入的字符串a
    message = f"{current_time} - {a}\n"

    # 获取文件路径
    file_path = os.path.join(
        DATA_DIR, "super_admins_actions.txt")

    # 获取文件锁
    file_lock = await get_file_lock(file_path)

    # 异步地获取锁
    async with file_lock:
        # 异步地打开文件以追加模式（'a'），将内容追加到文件末尾
        async with aiofiles.open(file_path, mode='a', encoding='utf-8') as file:
            # 异步地写入消息
            await file.write(message)


class BlackWhiteList:
    """黑白名单类"""

    def __init__(self, black_white_list_file: Path = os.path.join(DATA_DIR, "black_white_list.json")):
        """
        初始化黑白名单类实例。

        :param black_white_list_file: 黑白名单JSON文件路径
        """
        self.black_white_list_file = black_white_list_file
        self.lock = asyncio.Lock()  # 创建一个锁用于并发控制
        self.black_list = {'groupid': set(), 'userid': set()}  # 黑名单字典
        self.white_list = {'groupid': set(), 'userid': set()}  # 白名单字典
        asyncio.create_task(self._load_lists())  # 异步加载黑白名单数据

    async def _load_lists(self):
        """
        从JSON文件异步加载黑白名单数据。
        """
        try:
            async with aiofiles.open(self.black_white_list_file, mode='r', encoding='utf-8') as file:
                data = json.loads(await file.read())
                self.black_list['groupid'] = set(
                    data.get('black_list', {}).get('groupid', []))
                self.black_list['userid'] = set(
                    data.get('black_list', {}).get('userid', []))
                self.white_list['groupid'] = set(
                    data.get('white_list', {}).get('groupid', []))
                self.white_list['userid'] = set(
                    data.get('white_list', {}).get('userid', []))
        except FileNotFoundError:
            pass  # 如果文件不存在，则初始化为空

    async def _save_lists(self):
        """
        异步保存黑白名单数据到JSON文件。
        """
        async with self.lock:  # 获取锁以防止并发修改
            async with aiofiles.open(self.black_white_list_file, mode='w', encoding='utf-8') as file:
                # 将set转换为list
                data = {
                    'black_list': {
                        'groupid': list(self.black_list['groupid']),
                        'userid': list(self.black_list['userid'])
                    },
                    'white_list': {
                        'groupid': list(self.white_list['groupid']),
                        'userid': list(self.white_list['userid'])
                    }
                }
                # 序列化为JSON字符串并写入文件
                await file.write(json.dumps(data, indent=4, ensure_ascii=False))

    async def _check_in_table(self, id: str, db_path: str = db_path) -> bool:
        """
        异步检查给定的ID是否存在于指定的数据库表中。

        :param id_type: ID类型（groupid 或 userid）
        :param id: 要检查的ID
        :return: 如果存在则返回True，否则返回False
        """
        async with aiosqlite.connect(db_path) as conn:
            cursor = await conn.cursor()
            await cursor.execute(f"SELECT * FROM qq_love WHERE ID=?", (id,))
            return bool(await cursor.fetchone())

    async def add_to_blacklist(self, id_type: str, id: str) -> List[str]:
        """
        异步向黑名单中添加指定类型的ID。

        :param id_type: ID类型（groupid 或 userid）
        :param id: 要添加的ID
        :return: 返回一个消息列表，表示成功或失败
        """
        if id_type not in ['groupid', 'userid']:
            raise ValueError("Invalid id_type, must be 'groupid' or 'userid'.")

        # 检查是否已经在黑名单或白名单中
        if id in self.black_list[id_type] or id in self.white_list[id_type]:
            if id in self.black_list[id_type]:
                return [f"{id} 已经作为 {id_type} 添加为黑名单"]
            else:
                await self.remove_from_whitelist(id_type,id)

        if id_type == 'userid':
            if await self._check_in_table(id):
                self.black_list[id_type].add(id)
                await self._save_lists()
                return [f"{id} 作为 {id_type} 添加入黑名单"]
        elif id_type == 'groupid':
            self.black_list[id_type].add(id)
            await self._save_lists()
            return [f"{id} 作为 {id_type} 添加入黑名单"]

        return []

    async def add_to_whitelist(self, id_type: str, id: str) -> List[str]:
        """
        异步向白名单中添加指定类型的ID。

        :param id_type: ID类型（groupid 或 userid）
        :param id: 要添加的ID
        :return: 返回一个消息列表，表示成功或失败
        """
        if id_type not in ['groupid', 'userid']:
            raise ValueError("Invalid id_type, must be 'groupid' or 'userid'.")

        # 检查是否已经在黑名单或白名单中
        if id in self.black_list[id_type] or id in self.white_list[id_type]:
            if id in self.black_list[id_type]:
                return [f"{id} 已经作为 {id_type} 添加为黑名单"]
            else:
                return [f"{id} 已经作为 {id_type} 添加为白名单"]

        if id_type == 'userid':
            if await self._check_in_table(id):
                self.white_list[id_type].add(id)
                await self._save_lists()
                return [f"{id} 作为 {id_type} 添加入白名单"]
        elif id_type == 'groupid':
            self.white_list[id_type].add(id)
            await self._save_lists()
            return [f"{id} 作为 {id_type} 添加入白名单"]

        return []

    async def remove_from_blacklist(self, id_type: str, id: str) -> List[str]:
        """
        异步从黑名单中移除指定类型的ID。

        :param id_type: ID类型（groupid 或 userid）
        :param id: 要移除的ID
        :return: 返回一个消息列表，表示成功或失败
        """
        if id in self.black_list[id_type]:
            self.black_list[id_type].remove(id)
            await self._save_lists()
            return [f"{id} 作为 {id_type} 从黑名单中移除"]

        return [f'{id} 作为 {id_type} 不是黑名单']

    async def remove_from_whitelist(self, id_type: str, id: str) -> List[str]:
        """
        异步从白名单中移除指定类型的ID。

        :param id_type: ID类型（groupid 或 userid）
        :param id: 要移除的ID
        :return: 返回一个消息列表，表示成功或失败
        """
        if id in self.white_list[id_type]:
            self.white_list[id_type].remove(id)
            await self._save_lists()
            return [f"{id} 作为 {id_type} 从白名单中移除"]

        return [f'{id} 作为 {id_type} 不是白名单']

    async def check_in_list(self, id_type: str, id: str) -> Optional[str]:
        """
        异步检查指定类型的ID是否在黑名单或白名单中。

        :param id_type: ID类型（groupid 或 userid）
        :param id: 要检查的ID
        :return: 如果在黑名单中返回 'blacklist'，如果在白名单中返回 'whitelist'，否则返回 None
        """
        if id in self.black_list[id_type]:
            return 'blacklist'
        elif id in self.white_list[id_type]:
            return 'whitelist'
        else:
            return None


async def super_admin_action(qq_number: str, action: str, ADMIN_FILE: Path = os.path.join(DATA_DIR, "super_admins.json")) -> List[str]:
    """
    根据action参数添加、删除或获取管理员QQ号码列表
    action: get / add / remove
    """
    admins = []

    try:
        # 异步连接到SQLite数据库
        async with aiosqlite.connect(db_path) as conn:
            cursor = await conn.cursor()

            # 查询qq_number是否存在于qq_love表中
            await cursor.execute("SELECT * FROM qq_love WHERE QQ=?", (qq_number,))
            result = await cursor.fetchone()

            # 根据不同的action执行对应的操作
            if action == 'get' or result is None:
                logger.info('完成超管数据读取')
                try:
                    async with aiofiles.open(ADMIN_FILE, mode='r', encoding='utf-8') as file:
                        admins = json.loads(await file.read())
                except FileNotFoundError:
                    pass  # 文件不存在则返回空列表
            else:
                # 从JSON文件中读取数据
                file_lock = await get_file_lock(ADMIN_FILE)
                async with file_lock:
                    try:
                        async with aiofiles.open(ADMIN_FILE, mode='r', encoding='utf-8') as file:
                            admins = json.loads(await file.read())
                    except FileNotFoundError:
                        admins = []

                    # 执行添加或删除操作
                    if action == 'add':
                        if qq_number not in admins:
                            logger.debug(f'添加{qq_number}作为超管')
                            admins.append(qq_number)
                    elif action == 'remove':
                        if qq_number in admins:
                            logger.debug(f'移除{qq_number}作为超管')
                            admins.remove(qq_number)

                    # 将数据写回JSON文件
                    async with aiofiles.open(ADMIN_FILE, mode='w', encoding='utf-8') as file:
                        await file.write(json.dumps(admins, indent=4, ensure_ascii=False))

        return set(admins)
    except Exception as e:
        logger.warning(f"发生错误: {e}")
        return ()
