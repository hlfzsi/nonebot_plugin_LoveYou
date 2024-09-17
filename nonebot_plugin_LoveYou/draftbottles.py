from typing import List, Dict, Optional, Tuple
import httpx
import time
import sqlite3
import io
import random
import base64
import re
import os
from PIL import Image
from datetime import datetime
from aiohttp import web
import aiosqlite
import string


from nonebot import logger
from .love_manager import update_love_sq, read_love_sq, replace_qq_sq
from . import DATA_DIR


def generate_random_string(length=10):
    # 定义可选字符集，包含所有大小写字母及数字
    characters = string.ascii_letters + string.digits

    # 使用random.choices()从字符集中随机选择指定长度的字符
    random_string = ''.join(random.choices(characters, k=length))

    return random_string


class DriftBottle:
    """
    漂流瓶类。
    """

    def __init__(self, DB_PATH: str = os.path.join(DATA_DIR, 'DriftBottles.db3')):
        self.DB_PATH = DB_PATH
        self.conn: sqlite3.Connection = None
        self._connect()

    def initialize(self) -> None:
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS Bottles (
                id TEXT PRIMARY KEY UNIQUE,
                userid TEXT,
                message TEXT,
                timestamp INTEGER,
                image BLOB,
                type TEXT,
                likes INTEGER DEFAULT 0,
                dislikes INTEGER DEFAULT 0,
                blocked BOOLEAN DEFAULT 0,
                draw_count INTEGER DEFAULT 0,
                last_drawn INTEGER,
                groupid TEXT,
                state INTEGER DEFAULT 0
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS Types (
                groupid TEXT PRIMARY KEY,
                types TEXT,
                real_id TEXT UNIQUE
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS Likes (
                userid TEXT,
                bottle_id TEXT,
                timestamp INTEGER,
                PRIMARY KEY (userid, bottle_id)
            )
        """)
        # 添加索引
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_bottle_type ON Bottles(type)")
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_bottle_userid ON Bottles(userid)")
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_likes_userid ON Likes(userid)")
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_likes_bottle_id ON Likes(bottle_id)")

        self.conn.commit()

    def _connect(self):
        """内部使用，用于建立数据库连接。"""
        self.conn = sqlite3.connect(self.DB_PATH, check_same_thread=False)
        self.initialize()

    def close(self) -> None:
        """关闭数据库连接。"""
        if self.conn:
            self.conn.close()
            self.conn = None

    def get_bottle_ids_by_userid(self, userid: str) -> List[str]:
        """
        返回与给定userid相关的所有漂流瓶记录的id。
        """
        cursor = self.conn.execute(
            "SELECT id FROM Bottles WHERE userid=?", (userid,))
        bottle_ids = [row[0] for row in cursor]
        cursor.close()
        return bottle_ids

    def insert_bottle(self, userid: str, message: str, groupid: str, image_url: str = None):
        """
        将用户ID和消息插入数据库，并记录时间戳。如有图片，记录图片数据。
        """
        timestamp = int(time.time())
        bottle_id = f'{timestamp}{userid}{groupid}'
        str_list = list(bottle_id)
        random.shuffle(str_list)
        bottle_id = ''.join(str_list)[:12]

        # 同步获取groupid对应的types
        types = self.get_types_for_groupid(groupid)
        if not types:
            self.modify_type(groupid, ['Default'])
            types = self.get_types_for_groupid(groupid)

        types = random.choice(types)

        image_data = None
        if image_url:
            try:
                # 使用httpx发送GET请求
                response = httpx.get(image_url)

                if response.status_code == 200:
                    original_image_data = response.content
                    image = Image.open(io.BytesIO(original_image_data))

                    # 确保图像转换为RGB模式
                    image = image.convert('RGB')

                    output = io.BytesIO()
                    image.save(output, format="JPEG", quality=75)

                    # 将处理后的图像数据存入image_data
                    image_data = output.getvalue()

                    output.close()

                    if len(original_image_data) > 400 * 1024:
                        raise ValueError("图片过大")
                else:
                    raise ValueError("图片获取失败")

            except Exception as e:
                logger.warning(f"Error fetching image: {e}")
        # 同步执行插入操作
        self.conn.execute(
            """
            INSERT INTO Bottles (id, userid, message, timestamp, image, type,groupid)
            VALUES (?, ?, ?, ?, ?, ?,?)
            """, (bottle_id, userid, message, timestamp, image_data, types, groupid)
        )
        self.conn.commit()
        return bottle_id

    def get_types_for_groupid(self, groupid: str) -> List[str]:
        """
        同步获取指定groupid对应的类型列表。
        """
        cursor = self.conn.cursor()
        cursor.execute("SELECT types FROM Types WHERE groupid=?", (groupid,))
        result = cursor.fetchone()
        cursor.close()
        if result is not None:
            return result[0].split(',')
        return []

    def get_real_id_for_groupid(self, groupid: str) -> str:
        """
        同步获取指定groupid对应的真实ID。
        """
        cursor = self.conn.cursor()
        cursor.execute("SELECT real_id FROM Types WHERE groupid=?", (groupid,))
        result = cursor.fetchone()
        cursor.close()
        if result is not None:
            return result[0]
        return None

    def get_bottle(self, groupid: str) -> Optional[Dict[str, str]]:
        """
        随机加权取出漂流瓶，根据groupid的类型。每个漂流瓶被取出的次数越多，
        下次被抽取的概率越小。返回漂流瓶ID、消息内容、点赞数、点踩数。
        如果有图片，返回图片的base64编码。
        """
        with self.conn:
            cursor = self.conn.cursor()

            # 获取groupid对应的类型列表
            cursor.execute(
                "SELECT types FROM Types WHERE groupid=?", (groupid,)
            )
            types_row = cursor.fetchone()
            if types_row is None:
                # 如果找不到groupid，则使用默认类型列表
                types = ['Default']
            else:
                types = [t.strip() for t in types_row[0].split(',')]

            # 构建SQL IN子句
            type_in_clause = '(' + ', '.join(['?'] * len(types)) + ')'

            # 查询所有符合条件的漂流瓶
            cursor.execute(f"""
                SELECT id, userid, message, image, likes, dislikes, draw_count ,groupid ,state
                FROM Bottles
                WHERE type IN {type_in_clause} AND blocked=0
            """, tuple(types))

            matching_bottles = cursor.fetchall()

            if not matching_bottles:
                # 没有找到匹配的漂流瓶
                return None

            # 计算权重
            weights = []
            total_draws = sum(max(b[6], 1) for b in matching_bottles)

            for b in matching_bottles:
                weight = total_draws / max(b[6], 1)
                # 如果state为0，则将权重减少到原来的25%
                if b[8] == 0:
                    weight *= 0.25
                weights.append(max(weight, 1))

            # 随机选择一个“瓶子”
            selected_bottle = random.choices(
                matching_bottles, weights=weights)[0]

            bottle_id, _, message, image, likes, dislikes, _, from_groupid, state = selected_bottle
            groupid = self.get_real_id_for_groupid(from_groupid)

            if image and state == 200:
                image_base64 = base64.b64encode(image).decode('utf-8')
            else:
                image_base64 = None

            if state == 0 and image:
                image_base64 = None
                message = f'{message}\n[未经过审核，图片暂不展示]'

            # 更新抽取次数和最后被抽取的时间
            current_time = int(datetime.now().timestamp())
            cursor.execute(
                "UPDATE Bottles SET draw_count=draw_count+1, last_drawn=? WHERE id=?", (
                    current_time, bottle_id)
            )

        return {
            'id': bottle_id,
            'message': message,
            'likes': likes,
            'dislikes': dislikes,
            'image_base64': image_base64,
            'groupid': groupid
        }

    def set_real_group(self, groupid: str, real_id: str):
        """通过groupid设置真实id。"""
        with self.conn:
            cursor = self.conn.cursor()

            # 检查groupid是否已存在于Types表中
            cursor.execute(
                "SELECT real_id FROM Types WHERE groupid=?", (groupid,))
            existing_row = cursor.fetchone()

            if existing_row is not None:
                # 如果groupid已存在
                if existing_row[0] is not None:
                    return existing_row[0]

                # 如果groupid已存在，但是real_id为null，则更新real_id
                cursor.execute(
                    "UPDATE Types SET real_id=? WHERE groupid=?", (real_id, groupid))
            else:
                # 如果groupid不存在，则插入新的记录
                cursor.execute(
                    "INSERT INTO Types (groupid, types, real_id) VALUES (?, ?, ?)", (groupid, 'Default', real_id))

    def like_bottle(self, userid: str, bottle_id: str) -> bool:
        """
        为对应漂流瓶增加点赞数。只允许在漂流瓶被抽取后30秒内点赞，
        相同userid只能为同一漂流瓶点赞一次。
        """
        current_time = int(datetime.now().timestamp())

        with self.conn:
            # 检查是否已经点过赞
            cursor = self.conn.execute(
                "SELECT timestamp FROM Likes WHERE userid=? AND bottle_id=?", (
                    userid, bottle_id)
            )
            if cursor.fetchone():
                cursor.close()
                return False

            # 获取漂流瓶最后一次被抽取的时间戳
            cursor = self.conn.execute(
                "SELECT last_drawn FROM Bottles WHERE id=?", (bottle_id,)
            )
            last_drawn_row = cursor.fetchone()
            cursor.close()
            if last_drawn_row is None or current_time - last_drawn_row[0] > 30:
                return False

            # 增加点赞数并记录点赞
            self.conn.execute(
                "UPDATE Bottles SET likes=likes+1 WHERE id=?", (bottle_id,)
            )
            self.conn.execute(
                "INSERT INTO Likes (userid, bottle_id, timestamp) VALUES (?, ?, ?)", (
                    userid, bottle_id, current_time)
            )
            self.conn.commit()

        return True

    def dislike_bottle(self, userid: str, bottle_id: str) -> bool:
        """
        为对应漂流瓶增加点踩数。具体要求同点赞。
        """
        current_time = int(datetime.now().timestamp())

        with self.conn:
            # 检查是否已经点过踩
            cursor = self.conn.execute(
                "SELECT timestamp FROM Likes WHERE userid=? AND bottle_id=?", (
                    userid, bottle_id)
            )
            if cursor.fetchone():
                cursor.close()
                return False

            # 获取漂流瓶最后一次被抽取的时间戳
            cursor = self.conn.execute(
                "SELECT last_drawn FROM Bottles WHERE id=?", (bottle_id,)
            )
            last_drawn_row = cursor.fetchone()
            cursor.close()
            if last_drawn_row is None or current_time - last_drawn_row[0] > 30:
                return False

            # 增加点踩数并记录点踩
            self.conn.execute(
                "UPDATE Bottles SET dislikes=dislikes+1 WHERE id=?", (bottle_id,)
            )
            self.conn.execute(
                "INSERT INTO Likes (userid, bottle_id, timestamp) VALUES (?, ?, ?)", (
                    userid, bottle_id, current_time)
            )
            self.conn.commit()

        return True

    def clean_old_bottles(self) -> None:
        """
        同步清理所有存在时间超过7天的漂流瓶记录，并计算love值。
        """
        threshold_time = int(time.time()) - 7 * 24 * 3600

        with self.conn:
            cursor = self.conn.cursor()

            # 获取所有过期的漂流瓶ID
            cursor.execute(
                "SELECT id, likes, dislikes, draw_count, userid, blocked FROM Bottles WHERE timestamp<?", (threshold_time,))
            bottles_to_clean = cursor.fetchall()

            for bottle_id, likes, dislikes, draw_count, userid, blocked in bottles_to_clean:
                love = int(15 * (1.5 * likes - dislikes) /
                           (draw_count + likes + dislikes + 1))
                if blocked:
                    love = -abs(love)
                update_love_sq(userid, love)

            # 清理与这些漂流瓶相关的点赞记录
            for bottle_id, _, _, _, _ in bottles_to_clean:
                cursor.execute(
                    "DELETE FROM Likes WHERE bottle_id=?", (bottle_id,))

            # 删除漂流瓶
            cursor.execute("DELETE FROM Bottles WHERE timestamp<?",
                           (threshold_time,))
            self.conn.commit()

    def block_bottle(self, bottle_id: str) -> None:
        """
        同步屏蔽指定漂流瓶，使其无法被抽取。
        """
        with self.conn:
            self.conn.execute(
                "UPDATE Bottles SET blocked=1 WHERE id=?", (bottle_id,))
            self.conn.commit()

    def unblock_bottle(self, bottle_id: str) -> None:
        """
        同步解除屏蔽指定漂流瓶。
        """
        with self.conn:
            self.conn.execute(
                "UPDATE Bottles SET blocked=0 WHERE id=?", (bottle_id,))
            self.conn.commit()

    def get_bottle_by_id(self, bottle_id: str) -> Optional[dict]:
        """
        同步返回指定ID的漂流瓶信息。
        """
        with self.conn:
            cursor = self.conn.execute(
                "SELECT id, userid, message, timestamp, image, likes, dislikes, blocked, draw_count, last_drawn, groupid "
                "FROM Bottles WHERE id=?", (bottle_id,)
            )
        bottle = cursor.fetchone()

        if bottle:
            (bottle_id, userid, message, b_timestamp, image, likes,
             dislikes, blocked, draw_count, last_drawn, groupid) = bottle

            # 处理时间戳
            if last_drawn:
                last_drawn = datetime.fromtimestamp(last_drawn)
                last_drawn = last_drawn.strftime('%Y-%m-%d %H:%M:%S')

            b_timestamp = datetime.fromtimestamp(b_timestamp)
            b_timestamp = b_timestamp.strftime('%Y-%m-%d %H:%M:%S')

            # 将图片数据转换为Base64编码字符串
            if image:
                image_base64 = base64.b64encode(image).decode('utf-8')
            else:
                image_base64 = None

            real_groupid = self.get_real_id_for_groupid(groupid) or groupid

            return {
                'id': bottle_id,
                'userid': userid,
                'message': message,
                'timestamp': b_timestamp,
                'image_base64': image_base64,
                'likes': likes,
                'dislikes': dislikes,
                'blocked': blocked,
                'draw_count': draw_count,
                'last_drawn': last_drawn,
                'groupid': real_groupid
            }

        return None

    def list_types(self) -> List[Tuple[str, str]]:
        """
        同步列出所有可用的类型。
        """
        with self.conn:  # 假设self.conn是sqlite3.Connection的一个实例
            cursor = self.conn.execute("SELECT groupid, types FROM Types")
            types = cursor.fetchall()
        return types

    def modify_type(self, groupid: str, new_types: List[str]):
        """
        同步修改groupid对应的适用类型。
        """
        with self.conn:  # 使用上下文管理器自动处理事务
            # 首先检查groupid是否存在
            cursor = self.conn.execute(
                "SELECT COUNT(*) FROM Types WHERE groupid=?", (groupid,)
            )
            count = cursor.fetchone()[0]

            if count == 0:
                # 如果groupid不存在，则插入新记录
                # 将new_types列表转换为字符串
                types_str = ', '.join(new_types)
                self.conn.execute(
                    "INSERT INTO Types (groupid, types) VALUES (?, ?)", (
                        groupid, types_str)
                )
            else:
                # 如果groupid存在，则更新类型
                # 将new_types列表转换为字符串
                types_str = ', '.join(new_types)
                self.conn.execute(
                    "UPDATE Types SET types=? WHERE groupid=?", (
                        types_str, groupid)
                )

    def is_formated(self, input_text: str) -> bool:
        """
        检查所有 [] 是否符合规范。
        如果每个 [] 内容都能被正则匹配，则返回 True；否则返回 False。
        如果 arg == 'love'，检查 targets 是否含有两个可被 int 的元素（将 * 视为可被 int 的元素），且第一个元素小于等于第二个元素。
        """
        input_text = input_text.replace('，', ',').replace('：', ':')
        # 定义正则表达式
        pattern_with_else = r'\[(.*?)=(.*?):(.*?)\s*else\s*(.*?)\]'
        pattern_without_else = r'\[(.*?)=(.*?):(.*?)\]'

        # 查找所有符合模式的 []
        matches = re.findall(r'\[.*?\]', input_text)

        for match in matches:
            # 检查是否有else的情况
            match_with_else = re.match(pattern_with_else, match)
            if match_with_else:
                arg = match_with_else.group(1)
                targets = [t.strip()
                           for t in match_with_else.group(2).split(',')]
            else:
                # 检查没有else的情况
                match_without_else = re.match(pattern_without_else, match)
                if match_without_else:
                    arg = match_without_else.group(1)
                    targets = [t.strip()
                               for t in match_without_else.group(2).split(',')]
                else:
                    # 如果不符合任何模式，直接返回 False
                    logger.debug('无效的漂流瓶条件语句')
                    return False

            # 特殊检查：arg == 'love'
            if arg == 'love':
                # 检查 targets 中是否有两个可以被 int 的元素
                if len(targets) != 2:
                    logger.debug(f'无效的漂流瓶love条件语句,非标准目标,targets={targets}')
                    return False

                # 检查 targets 是否包含两个可被 int 的元素，并且第一个元素小于等于第二个元素
                try:
                    first_target = int(
                        targets[0]) if targets[0] != '*' else -float('inf')
                    second_target = int(
                        targets[1]) if targets[1] != '*' else float('inf')

                    if first_target > second_target:
                        logger.debug('无效的漂流瓶love条件语句,大小错误')
                        return False
                except ValueError:
                    # 如果转换失败，说明 targets 不是有效的数字或 '*'
                    logger.debug('无效的漂流瓶love条件语句,非数字')
                    return False

            elif arg not in ['userid', 'groupid', 'Gtype', 'alias', 'time']:
                logger.debug('不受支持的漂流瓶条件语句')
                return False

        # 如果所有 [] 都符合规范，则返回 True
        return True

    def msg_process(self, input_text: str, qq: str, groupid: str) -> str:
        """处理漂流瓶自定义内容

        Args:
            input_text (str): 漂流瓶原始消息
            qq (str): 触发漂流瓶的QQ
            groupid (str): 触发漂流瓶的群号

        Returns:
            str: 处理后的漂流瓶消息
        """
        input_text = input_text.replace('，', ',').replace('：', ':')

        while True:
            # 匹配有else的情况
            pattern_with_else = r'\[(.*?)=(.*?):(.*?)\s*else\s*(.*?)\]'
            match = re.search(pattern_with_else, input_text)

            # 如果没有匹配到带else的情况，尝试匹配不带else的情况
            if not match:
                pattern_without_else = r'\[(.*?)=(.*?):(.*?)\]'
                match = re.search(pattern_without_else, input_text)

            if not match:
                break

            arg = match.group(1)
            targets = [t.strip() for t in match.group(2).split(',')]
            optmsg = match.group(3).strip()
            elsemsg = match.group(4).strip() if len(
                match.groups()) == 4 else ''

            # 逻辑处理
            if arg == 'love':
                love = read_love_sq(qq)
                if targets[0] == '*' and targets[1] == '*':
                    replacement = optmsg
                elif targets[0] == '*' and love <= int(targets[1]):
                    replacement = optmsg
                elif targets[1] == '*' and love >= int(targets[0]):
                    replacement = optmsg
                elif love >= int(targets[0]) and love <= int(targets[1]):
                    replacement = optmsg
                else:
                    replacement = elsemsg
            elif arg == 'userid':
                if qq in targets:
                    replacement = optmsg
                else:
                    replacement = elsemsg
            elif arg == 'groupid':
                if groupid in targets:
                    replacement = optmsg
                else:
                    replacement = elsemsg
            elif arg == 'alias':
                alias = replace_qq_sq(qq)
                if alias in targets:
                    replacement = optmsg
                else:
                    replacement = elsemsg
            elif arg == 'Gtype':
                Gtype = self.get_types_for_groupid(groupid)
                if not Gtype:
                    Gtype = ['Default']
                for i in Gtype:
                    if i in targets:
                        replacement = optmsg
                        break
                if not replacement:
                    replacement = elsemsg
            elif arg == 'time':
                now = datetime.now()
                formatted_date = now.strftime("%m-%d %H:%M")
                replacement = formatted_date
            else:
                replacement = ''

            if replacement:
                # 替换匹配的内容
                start, end = match.span()
                input_text = input_text[:start] + \
                    str(replacement) + input_text[end:]
            else:
                start, end = match.span()
                input_text = input_text[:start] + input_text[end:]

        return input_text


PASSWORD_EXPIRATION = 30  # 密码有效时间（秒）


class ReviewApp:
    def __init__(self, db_path=os.path.join(DATA_DIR, 'DriftBottles.db3')):
        self.app = web.Application()
        self.db_path = db_path
        self.passwords = {}  # 存储密码及其生成时间

    async def get_db_connection(self):
        """ 获取或创建数据库连接 """
        return await aiosqlite.connect(self.db_path)

    def generate_webcode(self):
        """ 生成一个唯一的Web代码 """
        webcode = generate_random_string()
        self.passwords[webcode] = time.time()
        logger.info(f'{webcode}')
        return webcode

    async def authenticate(self, request):
        """ 认证请求中的密码是否有效 """
        data = await request.json()
        password = data.get('password')
        current_time = time.time()
        if password in self.passwords and current_time - self.passwords[password] <= PASSWORD_EXPIRATION:
            del self.passwords[password]
            return web.Response(text='Authenticated successfully\n认证成功!\nGo Work!(笑)')
        else:
            return web.Response(status=401, text='Authentication failed\n你谁啊,我不认识你')

    async def handle_index(self, request):
        """ 返回主页文件 """
        return web.FileResponse(os.path.join(DATA_DIR, 'index.html'))

    async def get_info(self, row):
        """ 从数据库行中提取并格式化信息 """
        # 获取列名列表
        columns = [col[0]
                   for col in row.keys()] if hasattr(row, 'keys') else None

        if row['last_drawn'] is not None:
            last_drawn = datetime.fromtimestamp(
                row['last_drawn']).strftime('%Y-%m-%d %H:%M:%S')
        else:
            last_drawn = None

        b_timestamp = datetime.fromtimestamp(
            row['timestamp']).strftime('%Y-%m-%d %H:%M:%S')

        if row['image'] is not None:
            image_base64 = base64.b64encode(row['image']).decode('utf-8')
        else:
            image_base64 = None

        # 获取groupid字段，并尝试从Types表中获取对应的real_id
        groupid = row.get('groupid')
        real_groupid = await self.get_real_id_for_groupid(groupid)
        if real_groupid:
            real_groupid = f'{real_groupid} | {groupid}'
        else:
            real_groupid = groupid

        return {
            'id': row['id'],
            'userid': row['userid'],
            'message': row['message'],
            'timestamp': b_timestamp,
            'image_base64': image_base64,
            'likes': row['likes'],
            'dislikes': row['dislikes'],
            'blocked': row['blocked'],
            'draw_count': row['draw_count'],
            'last_drawn': last_drawn,
            'groupid': real_groupid
        }

    async def handle_review(self, request):
        """ 获取一个待审核的漂流瓶信息 """
        async with aiosqlite.connect(self.db_path) as conn:
            cursor = await conn.execute("SELECT * FROM Bottles WHERE state = 0 LIMIT 1")
            # 获取列名列表
            columns = [col[0] for col in cursor.description]
            row = await cursor.fetchone()
            # 将查询结果转换为字典
            if row:
                row = dict(zip(columns, row))
            await cursor.close()

        if row:
            info = await self.get_info(row)
            return web.json_response(info)
        else:
            return web.Response(status=204)

    async def get_real_id_for_groupid(self, groupid):
        """ 从Types表中根据groupid获取real_id """
        if not groupid:
            return None

        async with aiosqlite.connect(self.db_path) as conn:
            cursor = await conn.execute("SELECT real_id FROM Types WHERE groupid=?", (groupid,))
            result = await cursor.fetchone()
            await cursor.close()

        return result[0] if result and result[0] else None

    async def handle_review_action(self, request):
        """ 执行审核动作 """
        data = await request.json()
        action = data.get('action')
        id = data.get('id')

        if action not in ('approve', 'reject'):
            return web.Response(status=400, text='Invalid action')

        async with aiosqlite.connect(self.db_path) as conn:
            try:
                if action == 'approve':
                    await conn.execute("UPDATE Bottles SET state = 200 WHERE id = ?", (id,))
                else:
                    await conn.execute("DELETE FROM Bottles WHERE id = ?", (id,))
                await conn.commit()
            except Exception as e:
                print(f"Error updating database: {e}")
                await conn.rollback()
                return web.Response(status=500, text='Failed to update record')

        return web.Response(text='Record updated')

    async def get_bottle_by_id_app(self, bottle_id: str) -> dict:
        """ 获取指定ID的漂流瓶信息 """
        async with aiosqlite.connect(self.db_path) as conn:
            cursor = await conn.execute(
                "SELECT id, userid, message, timestamp, image, likes, dislikes, blocked, draw_count, last_drawn , groupid"
                "FROM Bottles WHERE id=?", (bottle_id,)
            )
            # 获取列名列表
            columns = [col[0] for col in cursor.description]
            bottle = await cursor.fetchone()
            # 将查询结果转换为字典
            if bottle:
                bottle = dict(zip(columns, bottle))
            await cursor.close()

        if bottle:
            return await self.get_info(bottle)


app = None


def init_app(db_path=os.path.join(DATA_DIR, 'DriftBottles.db3')):
    global app
    if app is None:
        app = ReviewApp(db_path)
    app.app.add_routes([
        web.get('/', app.handle_index),
        web.post('/authenticate', app.authenticate),
        web.get('/review', app.handle_review),
        web.post('/review', app.handle_review_action),
    ])


def start_server(port=9999):
    global app
    if app is not None:
        web.run_app(app.app, port=port)
