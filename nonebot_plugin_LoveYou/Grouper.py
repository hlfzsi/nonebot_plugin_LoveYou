import aiosqlite
from . import DATA_DIR
import os


class GroupMembers:
    def __init__(self, db_file=os.path.join(DATA_DIR, 'qq.db3')):
        self.db_file = db_file
        self.conn = None

    async def create_connection(self):
        """ 创建一个到SQLite数据库的异步连接 """
        if not self.conn:
            self.conn = await aiosqlite.connect(self.db_file)
        return self.conn

    async def check_and_create_table(self, conn, groupid):
        """ 检查是否存在给定groupid的表，不存在则创建 """
        table_name = f"qq_{groupid}"
        # 使用参数化查询来避免 SQL 注入和语法错误
        async with conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,)
        ) as cursor:
            if not (await cursor.fetchone()):
                # 创建表
                await conn.execute(
                    f"CREATE TABLE {table_name} (QQ TEXT PRIMARY KEY)"
                )
                await conn.execute(f"CREATE INDEX IF NOT EXISTS idx_qq_{groupid}_qq ON {table_name}(QQ)")
                await conn.commit()

    async def insert_or_ignore(self, conn, table_name, userid):
        """ 插入或忽略userid的记录 """
        async with conn.execute(
            f"INSERT OR IGNORE INTO {table_name} (QQ) VALUES (?)", (userid,)
        ) as cursor:
            await conn.commit()

    async def create_and_insert_if_not_exists(self, groupid, userid):
        """ 根据groupid创建表，并插入userid记录 """
        conn = await self.create_connection()
        try:
            await self.check_and_create_table(conn, groupid)
            table_name = f"qq_{groupid}"
            await self.insert_or_ignore(conn, table_name, userid)
        finally:
            # 确保连接关闭
            await conn.close()
            self.conn = None

    async def get_top_users_by_love_from_total_table(self, conn, groupid):
        """ 根据groupid从总表中获取前十个用户ID，这些用户ID也必须在对应groupid表中存在 """
        table_name = f"qq_{groupid}"
        async with conn.execute(
            f"""
            SELECT t1.QQ
            FROM qq_love AS t1
            INNER JOIN {table_name} AS t2 ON t1.QQ = t2.QQ
            ORDER BY t1.love DESC
            LIMIT 10
            """
        ) as cursor:
            return [row[0] async for row in cursor]

    async def get_top_users_by_groupid(self, groupid):
        """ 根据groupid获取前十个用户ID """
        conn = await self.create_connection()
        try:
            return await self.get_top_users_by_love_from_total_table(conn, groupid)
        finally:
            # 确保连接关闭
            await conn.close()
            self.conn = None

    async def close(self):
        """ 关闭数据库连接 """
        if self.conn:
            await self.conn.close()
            self.conn = None