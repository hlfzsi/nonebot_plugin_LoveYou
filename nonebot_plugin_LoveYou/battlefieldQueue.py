import sqlite3
from .connection_pool import SQLitePool
import os
from datetime import datetime
import httpx
import re
import Levenshtein
from . import DATA_DIR


class NFManager:
    def __init__(self, db_path=os.path.join(DATA_DIR, 'DataBase', 'bf1', 'battlefield.db3')):
        db_dir = os.path.dirname(db_path)
        if not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
        self.BF_POOL = SQLitePool(db_path)
        self.db_path = db_path
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA journal_mode")
            current_journal_mode = cursor.fetchone()[0]
            if current_journal_mode != 'wal':
                cursor.execute("PRAGMA journal_mode=WAL")
            conn.execute('''
                CREATE TABLE IF NOT EXISTS server (
                    name TEXT PRIMARY KEY,
                    qq TEXT NOT NULL,
                    time INTEGER NOT NULL,
                    type INTEGER NOT NULL
                )
            ''')
            conn.commit()
        self.client = httpx.AsyncClient()

    async def check_server_exists(self, name):
        url = f"https://api.gametools.network/bf1/servers?name={name}"
        response = await self.client.get(url)
        if response.status_code == 200:
            data = response.json()
            if data and 'servers' in data and data['servers']:
                return True
        return False

    async def add_nf(self, name, qq, type):
        if type not in [0, 1]:
            raise ValueError("Type must be 0 or 1")

        time = datetime.now().timestamp()

        async with self.BF_POOL.connection() as conn:
            await conn.execute('''
                INSERT INTO server (name, qq, time, type) VALUES (?, ?, ?, ?)
            ''', (name, qq, time, type))
            await conn.commit()

    async def cancel_nf(self, name):
        async with self.BF_POOL.connection() as conn:
            await conn.execute('''
                DELETE FROM server WHERE name = ?
            ''', (name,))
            await conn.commit()

    async def show_nf(self, type):
        now = datetime.now().timestamp()
        one_hour_ago = now - 3600  # 一小时前的时间戳
        result = []

        async with self.BF_POOL.connection() as conn:
            # 删除一小时前的记录
            await conn.execute('''
                DELETE FROM server WHERE time < ?
            ''', (one_hour_ago,))
            await conn.commit()

            # 获取最新的5条记录，只取指定类型的记录
            cursor = await conn.execute('''
                SELECT name, time FROM server WHERE type = ? ORDER BY time ASC LIMIT 5
            ''', (type,))
            rows = await cursor.fetchall()
            for row in rows:
                name, timestamp = row
                dt = datetime.fromtimestamp(timestamp)
                formatted_time = dt.strftime('%H 时-%M 分完成添加')  # 格式化时间为 小时-分钟
                result.append({'name': name, 'time': formatted_time})

        # 获取排位第一的记录
        top_record = None
        if result:
            top_name = result[0]['name']
            top_server_info = await self.get_server_info(top_name)
            if top_server_info:
                top_record = top_server_info
                top_server_info['name'] = top_name
                result.pop(0)

        return {'top_record': top_record, 'records': result}

    async def get_server_info(self, name):
        url = f"https://api.gametools.network/bf1/servers?name={name}"
        response = await self.client.get(url)
        if response.status_code == 200:
            data = response.json()
            if data and 'servers' in data and data['servers']:
                # 初始化最小编辑距离和对应的服务器
                min_distance = float('inf')
                best_match = None
                best_match_with_tag = None

                # 提取 name 中的 #3 类似的内容
                name_tag_match = re.search(r'#\d+', name)
                name_tag = name_tag_match.group(0) if name_tag_match else None

                for server in data['servers']:
                    prefix = server.get('prefix', '')
                    # 提取 prefix 中 [] 包裹的内容
                    match = re.search(r'\[(.*?)\]', prefix)
                    if match:
                        prefix_content = match.group(1).lower()  # 转换为小写
                        # 计算编辑距离（忽略大小写）
                        distance = Levenshtein.distance(name.lower(), prefix_content)
                        if distance < min_distance:
                            min_distance = distance
                            best_match = server
                            if name_tag and name_tag in prefix:
                                best_match_with_tag = server
                        elif distance == min_distance:
                            if name_tag and name_tag in prefix:
                                best_match_with_tag = server

                # 如果有基于标签的最佳匹配，则返回该匹配
                if best_match_with_tag:
                    return best_match_with_tag
                # 否则返回基于编辑距离的最佳匹配
                return best_match
