from . import DATA_DIR
from .love_manager import qq_pool
import aiosqlite
import time
import os


class GroupMembers:
    def __init__(self, db_file=os.path.join(DATA_DIR, 'DataBase', 'users', 'qq.db3'), pool=qq_pool):
        self.db_file = db_file
        self.pool = pool

    async def check_and_create_table(self, conn: aiosqlite.Connection, groupid):
        """ 检查是否存在给定groupid的表，不存在则创建 """
        table_name = f"qq_{groupid}"
        async with conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,)
        ) as cursor:
            if not (await cursor.fetchone()):
                # 创建表
                await conn.execute(
                    f"CREATE TABLE {
                        table_name} (QQ TEXT PRIMARY KEY, last_updated INTEGER)"
                )
                await conn.execute(f"CREATE INDEX IF NOT EXISTS idx_qq_{groupid}_qq ON {table_name}(QQ)")
                await conn.commit()
            else:
                # 检查是否存在 last_updated 列
                async with conn.execute(
                    f"PRAGMA table_info({table_name})"
                ) as cursor:
                    columns = [row[1] for row in await cursor.fetchall()]
                    if 'last_updated' not in columns:
                        # 添加 last_updated 列
                        await conn.execute(
                            f"ALTER TABLE {
                                table_name} ADD COLUMN last_updated INTEGER"
                        )
                        await conn.commit()

    async def insert_or_ignore(self, conn: aiosqlite.Connection, table_name, userid):
        """ 插入或忽略userid的记录，并设置last_updated时间戳 """
        current_time = int(time.time())
        await conn.execute(
            f"""
        INSERT INTO {table_name} (QQ, last_updated)
        VALUES (?, ?)
        ON CONFLICT(QQ) DO UPDATE SET last_updated=excluded.last_updated
        """,
            (userid, current_time)
        )
        await conn.commit()

    async def create_and_insert_if_not_exists(self, groupid, userid):
        """ 根据groupid创建表，并插入userid记录 """
        conn = await self.pool.acquire()
        try:
            await self.check_and_create_table(conn, groupid)
            table_name = f"qq_{groupid}"
            await self.insert_or_ignore(conn, table_name, userid)
        finally:
            await self.pool.release(conn)

    async def get_top_users_by_love_from_total_table(self, conn: aiosqlite.Connection, groupid):
        """ 根据groupid从总表中获取前十个用户ID，这些用户ID也必须在对应groupid表中存在，并且是7天内的记录 """
        table_name = f"qq_{groupid}"
        seven_days_ago = int(time.time()) - 7 * 24 * 60 * 60  # 7天前的时间戳

        # 获取前10名有效用户
        async with conn.execute(
            f"""
            WITH ranked_users AS (
                SELECT t1.QQ, t2.last_updated,
                    ROW_NUMBER() OVER (ORDER BY t1.love DESC) AS rank
                FROM qq_love AS t1
                INNER JOIN {table_name} AS t2 ON t1.QQ = t2.QQ
                WHERE t2.last_updated >= ?
            )
            SELECT QQ
            FROM ranked_users
            WHERE rank <= 10
            """,
            (seven_days_ago,)
        ) as cursor:
            valid_users = [row[0] async for row in cursor]

        # 删除过期记录
        await conn.execute(
            f"DELETE FROM {table_name} WHERE last_updated < ?",
            (seven_days_ago,)
        )
        await conn.commit()

        return valid_users

    async def get_top_users_by_groupid(self, groupid):
        """ 根据groupid获取前十个用户ID """
        conn = await self.pool.acquire()
        try:
            return await self.get_top_users_by_love_from_total_table(conn, groupid)
        finally:
            await self.pool.release(conn)

    async def close(self):
        """ 关闭所有数据库连接并清空连接池 """
        await self.pool.close()
