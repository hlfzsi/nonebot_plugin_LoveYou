import asyncio
import aiosqlite
from nonebot import logger
from contextlib import asynccontextmanager


class SQLitePool:
    def __init__(self, db_file=None, max_size=5, ** kwargs):
        self.db_file = db_file
        self.max_size = max_size
        self.shared_uri = kwargs.get('shared_uri', None)
        self.pool = asyncio.Queue(maxsize=max_size)
        self.lock = asyncio.Lock()
        self._initialized = False
        self._closed = False
        if not self.db_file and not self.shared_uri:
            raise ValueError('没有指定的数据库')

    async def _initialize_pool(self):
        """ 初始化连接池 """
        if not self._initialized:
            async with self.lock:
                if not self._initialized:
                    for _ in range(self.max_size):
                        try:
                            if self.shared_uri:
                                # 使用共享内存数据库
                                conn = await aiosqlite.connect(self.shared_uri, uri=True)
                            else:
                                # 使用常规的磁盘上的数据库文件
                                conn = await aiosqlite.connect(self.db_file)
                            await self.pool.put(conn)
                        except Exception as e:
                            self.max_size -= 1
                            logger.error(f"Failed to create connection: {e}")
                    self._initialized = True

    async def acquire(self, timeout=None) -> aiosqlite.Connection:
        """ 获取一个数据库连接，可设置获取连接的超时时间 """
        if not self._initialized:
            await self._initialize_pool()

        try:
            conn = await asyncio.wait_for(self.pool.get(), timeout)
            return conn
        except asyncio.TimeoutError:
            raise TimeoutError("Timed out waiting for a database connection")
        except Exception as e:
            raise RuntimeError(f"Failed to acquire connection: {e}")

    async def release(self, conn: aiosqlite.Connection):
        """ 释放一个数据库连接回连接池 """
        if conn is not None:
            await self.pool.put(conn)

    async def close(self):
        """ 关闭所有连接并清空连接池 """
        if not self._closed:
            async with self.lock:
                if not self._closed:
                    while not self.pool.empty():
                        conn = await self.pool.get()
                        await conn.close()
                    self._closed = True

    @asynccontextmanager
    async def connection(self, timeout=None):
        """ 异步上下文管理器，用于自动管理连接的获取和释放，并处理连接相关错误 """
        conn = await self.acquire(timeout)
        try:
            yield conn
        except (aiosqlite.OperationalError, aiosqlite.DatabaseError):
            # 检查连接是否仍然有效，如果无效则关闭并重新创建连接
            await self.check_connection_health(conn)
            raise
        finally:
            await self.release(conn)

    async def check_connection_health(self, conn: aiosqlite.Connection):
        """ 检查连接是否仍然有效，如果无效则关闭并重新创建连接，并将其放回连接池 """
        try:
            await conn.execute('SELECT 1')
        except (aiosqlite.OperationalError, aiosqlite.DatabaseError):
            await conn.close()
            new_conn = await aiosqlite.connect(self.db_file)
            await self.pool.put(new_conn)
