import sqlite3
from typing import List,Union,Any,Optional
from .command_signer import BasicHandler
import sqlite3
from connection_pool import SQLitePool
from nonebot.exception import StopPropagation
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, PrivateMessageEvent
from typing import List, Set, Dict
import asyncio
from collections import Counter

SHARED_MEMORY_DB_NAME = "file:shared_memory_db?mode=memory&cache=shared"
MEMORY_DB_CONN = sqlite3.connect(SHARED_MEMORY_DB_NAME, uri=True)
COMMAND_POOL = SQLitePool(shared_uri=SHARED_MEMORY_DB_NAME)


def create_memory_table():
    cursor = MEMORY_DB_CONN.cursor()

    # 创建 commands 表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS commands (
            command TEXT PRIMARY KEY,
            description TEXT,
            owner TEXT,
            full_match INTEGER,
            handler_list TEXT  -- 使用逗号分隔的字符串来存储多个 Handler 的 ID
        )
    ''')

    # 创建 command_prefixes 表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS command_prefixes (
            command TEXT,
            prefix TEXT,
            PRIMARY KEY (command, prefix)
        )
    ''')

    # 创建索引以提高查询性能
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_commands ON commands(command)
    ''')
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_command_prefixes ON command_prefixes(prefix)
    ''')

    MEMORY_DB_CONN.commit()


create_memory_table()


class Command:
    def __init__(self, commands: List[str], description: str, handler_list: List[BasicHandler], owner: str, full_match: bool = False):
        self.command: Set[str] = {command.strip() for command in commands}
        self.description: str = description
        self.full_match: bool = full_match
        self.__owner: str = owner
        self.handler_list: List[str] = [
            str(handler.get_self_id()) for handler in handler_list]
        self.sign()
        
    @property
    def owner(self) -> str:
        return self.__owner

    def sign(self) -> None:
        """将命令及其相关信息保存到内存中的 SQLite 数据库中（仅用于初始化）"""
        cursor = MEMORY_DB_CONN.cursor()
        handler_ids = ','.join(self.handler_list)
        for command in self.command:
            cursor.execute('''
                INSERT INTO commands (command, description,owner, full_match, handler_list)
                VALUES (?, ?, ?, ?,?)
            ''', (command, self.description, self.owner, self.full_match, handler_ids))
        MEMORY_DB_CONN.commit()

    async def resign(self, new_commands: List[str] = None) -> None:
        """将命令及其相关信息保存到 SQLite 数据库中（使用连接池）"""
        if new_commands is not None:
            await self.remove()
            self.command = {command.strip() for command in new_commands}

        handler_ids = ','.join(self.handler_list)
        async with COMMAND_POOL.connection() as conn:
            cursor = await conn.cursor()
            for command in self.command:
                await cursor.execute('''
                    INSERT OR REPLACE INTO commands (command, description,owner, full_match, handler_list)
                    VALUES (?, ?, ?, ?, ?)
                ''', (command, self.description, self.owner, self.full_match, handler_ids))
            await conn.commit()

    async def change_handler(self, handler_list: List[BasicHandler]) -> None:
        """更改处理程序列表并重新保存命令信息"""
        self.handler_list = [str(handler.get_self_id())
                             for handler in handler_list]
        await self.resign()

    async def remove(self) -> None:
        """从数据库中删除该命令的记录（使用连接池）"""
        async with COMMAND_POOL.connection() as conn:
            cursor = await conn.cursor()
            for command in self.command:
                await cursor.execute('DELETE FROM commands WHERE command = ?', (command,))
            await conn.commit()


def ngrams(text, n=2):
    return [text[i:i+n] for i in range(len(text)-n+1)]


def ngrams_similarity(s1, s2, n=2):
    ngrams1 = ngrams(s1, n)
    ngrams2 = ngrams(s2, n)
    counter1 = Counter(ngrams1)
    counter2 = Counter(ngrams2)
    intersection = sum((counter1 & counter2).values())
    total = sum(counter1.values()) + sum(counter2.values())
    return 2 * intersection / total


async def find_closest_matches(user_input, conn):
    cursor = await conn.cursor()

    # 查询包含该前缀的命令
    await cursor.execute("SELECT command FROM command_prefixes WHERE prefix LIKE ?", (user_input + '%',))
    candidates = [row[0] for row in await cursor.fetchall()]

    best_match = None
    best_similarity = 0.0

    for candidate in candidates:
        similarity = ngrams_similarity(user_input, candidate)
        if similarity == 1.0:
            best_match = candidate
            break
        if similarity > best_similarity:
            best_similarity = similarity
            best_match = candidate

    return best_match


    
#To do
async def dispatch(message: str, bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent], image: Optional[str], private_vars: Optional[Dict[str, Any]] = None) -> None:
    """消息派发, 执行对应逻辑

    Args:
        message (str): 消息(纯文本)
        bot (Bot): Bot对象
        event (Union[GroupMessageEvent, PrivateMessageEvent]): 消息事件. 私信消息groupid按照-1处理
        image (Optional[str]): 图片url. 仅支持单张图片
        private_vars (Optional[Dict[str, Any]], optional): 可选的附加参数, 需与匹配类适配

    Raises:
        StopPropagation: 阻断事件传播
    """
    try:
        groupid = str(event.group_id)
    except AttributeError:
        groupid = '-1'

    async with COMMAND_POOL.connection() as conn:
        cursor = await conn.cursor()

        # 检查字符串是否等于某个特定值（完全匹配）
        await cursor.execute('''
            SELECT handler_list FROM commands
            WHERE full_match = 1 AND command = ?
        ''', (message,))
        for row in await cursor.fetchall():
            handlers = [BasicHandler.get_handler_by_id(handler_id)
                        for handler_id in row[0].split(',')]
            for handler in handlers:
                asyncio.create_task(handler.handle(msg=message, image=image, qq=str(event.user_id), groupid=groupid,
                                                   bot=bot, event=event, **(private_vars or {})))
                if handler.block:
                    raise StopPropagation

        # 检查字符串是否以某个前缀开始，并结合自动纠错
        best_match = await find_closest_matches(message, conn)
        if best_match:
            await cursor.execute('''
                SELECT handler_list FROM commands
                WHERE full_match = 0 AND command = ?
            ''', (best_match,))
            for row in await cursor.fetchall():
                handlers = [BasicHandler.get_handler_by_id(handler_id)
                            for handler_id in row[0].split(',')]
                for handler in handlers:
                    asyncio.create_task(handler.handle(msg=message, image=image, qq=str(event.user_id), groupid=groupid,
                                                       bot=bot, event=event, **(private_vars or {})))
                    if handler.block:
                        raise StopPropagation

        # 关闭游标
        await cursor.close()

if __name__ == '__main__':
    import asyncio
    async def main():

        class HandlerA(BasicHandler):
            async def handle(self, bot=None, event=None, msg: str = None, qq: str = None, groupid: str = None, image=None, ** kwargs) -> None:
                print(f'{self.handler_id} and Handler is running')
        handlers = [HandlerA(), HandlerA()]
        cmd = Command(commands=["  cmd1 ", "cmd2", "  cmd1  ", "cmd3"],
                    description="Sample command", handler_list=handlers, owner='test')

        print(cmd.command)  # 输出应该是 {'cmd1', 'cmd2', 'cmd3'}
        await HandlerA(True).handle()

        # 更新命令
        await cmd.resign(new_commands=["  cmd4 ", "cmd5"])
        print(cmd.command)  # 输出应该是 {'cmd4', 'cmd5'}

        # 更改处理程序
        new_handlers = [HandlerA()]
        await cmd.change_handler(new_handlers)

        # 删除记录
        await cmd.remove()

        await COMMAND_POOL.close()  # 关闭连接池
    asyncio.run(main())
