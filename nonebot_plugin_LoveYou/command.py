import sqlite3
from .command_signer import BasicHandler
from nonebot import logger
import pandas as pd
from connection_pool import SQLitePool
from nonebot.exception import StopPropagation
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, PrivateMessageEvent
from typing import List, Union, Any, Optional, Dict
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

    # 创建索引以提高查询性能
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_commands ON commands(command)
    ''')

    MEMORY_DB_CONN.commit()


create_memory_table()


class CommandData:
    """数据模型类，用于存储命令的属性。"""

    def __init__(self, command: List[str], description: str, owner: str, full_match: bool, handler_list: List[str]):
        self.command = command
        self.description = description
        self.owner = owner
        self.full_match = full_match
        self.handler_list = handler_list


class CommandDatabase:
    """数据库操作类，用于命令的增删改查。"""

    def __init__(self, db_connection: sqlite3.Connection = None):
        self.conn = db_connection

    def insert_commands(self, command_data: CommandData):
        """插入命令到数据库。"""
        cursor = self.conn.cursor()
        cursor.executemany('''
            INSERT INTO commands (command, description, owner, full_match, handler_list)
            VALUES (?, ?, ?, ?, ?)
        ''', [(cmd, command_data.description, command_data.owner, command_data.full_match, ','.join(command_data.handler_list)) for cmd in command_data.command])
        self.conn.commit()

    async def update_commands(self, command_data: CommandData):
        """更新命令到数据库。"""
        async with COMMAND_POOL.connection() as conn:
            try:
                conn.isolation_level = 'EXCLUSIVE'
                cursor = await conn.cursor()
                await cursor.execute('BEGIN EXCLUSIVE')
                await cursor.executemany('''
                    INSERT OR REPLACE INTO commands (command, description, owner, full_match, handler_list)
                    VALUES (?, ?, ?, ?, ?)
                ''', [(cmd, command_data.description, command_data.owner, command_data.full_match, ','.join(command_data.handler_list)) for cmd in command_data.command])
                await conn.commit()
            except Exception as e:
                await conn.rollback()
                raise e

    async def remove_commands(self, commands: List[str]):
        """删除命令记录。"""
        async with COMMAND_POOL.connection() as conn:
            cursor = await conn.cursor()
            await cursor.executemany('DELETE FROM commands WHERE command = ?', [(cmd,) for cmd in commands])
            await conn.commit()

    async def get_commands(self, command: str):
        """获取命令记录。"""
        async with COMMAND_POOL.connection() as conn:
            cursor = await conn.cursor()
            await cursor.execute('SELECT * FROM commands WHERE command = ?', (command,))
            return await cursor.fetchone()


class Command:
    """命令类。"""

    def __init__(self, commands: List[str], description: str, owner: str, full_match: bool, handler_list: List[Union[str, BasicHandler]]):  # type: ignore
        self.data = CommandData(
            command=list(dict.fromkeys([command.strip()
                         for command in commands])),
            description=description,
            owner=owner,
            full_match=full_match,
            handler_list=[str(handler.handler_id) if isinstance(
                handler, BasicHandler) else handler for handler in handler_list]
        )

        # 在初始化时进行验证和保存
        if self.validate():
            self.save()

    def validate(self) -> bool:
        """验证命令数据的合法性。"""
        for command in self.data.command:
            if not command or not isinstance(command, str):
                return False
        return True

    def save(self):
        """保存命令数据到数据库。"""
        if not self.validate():
            raise ValueError("Invalid command data.")

        db = CommandDatabase(MEMORY_DB_CONN)
        db.insert_commands(self.data)

    async def update(self, new_commands: List[str] = None, new_hander_list: List[Union[str, BasicHandler]] = None):
        db = CommandDatabase()
        if new_commands is not None:
            await db.remove_commands(self.data.command)
            self.data.command = list(dict.fromkeys(
                [command.strip() for command in new_commands]))
        if new_hander_list is not None:
            self.data.handler_list = [str(handler.handler_id) if isinstance(
                handler, BasicHandler) else handler for handler in new_hander_list]
        """更新命令数据到数据库。"""
        if not self.validate():
            raise ValueError("Invalid command data.")

        await db.update_commands(self.data)

    async def delete(self):
        """删除该命令。"""
        db = CommandDatabase()
        await db.remove_commands(self.data.command)


class CommandFactory:
    @staticmethod
    def create_command(commands: List[str], description: str, owner: str, full_match: bool, handler_list: List[str]) -> Command:
        return Command(commands, description, owner, full_match, handler_list)


def _ngram_similarity(s1: str, s2: str, n: int = 2) -> float:
    """计算两个字符串之间的n-gram相似度。"""
    grams1 = Counter(_ngrams(s1.lower(), n))
    grams2 = Counter(_ngrams(s2.lower(), n))
    intersection = grams1 & grams2
    union = grams1 | grams2
    return sum(intersection.values()) / sum(union.values()) if union else 0.0


def _ngrams(text: str, n: int = 2) -> List[str]:
    """从给定文本生成n-gram计数。"""
    return [text[i:i+n] for i in range(len(text)-n+1)]


async def dispatch(
    message: str,
    bot: Bot,
    event: Union[GroupMessageEvent, PrivateMessageEvent],
    image: Optional[str] = None,
    private_vars: Optional[Dict[str, Any]] = None
) -> None:
    """消息派发，执行对应逻辑"""

    groupid: str = str(getattr(event, 'group_id', -1))
    message = message.strip()
    if not message:
        return

    async with COMMAND_POOL.connection() as conn:
        cursor = await conn.cursor()
        try:
            if len(message) < 2:
                await cursor.execute('SELECT command, handler_list FROM commands WHERE command = ?', (message,))
            else:
                prefix = message[:2]
                await cursor.execute('SELECT command, handler_list, full_match FROM commands WHERE command = ? OR command LIKE ?', (message, f'{prefix}%'))
            commands = await cursor.fetchall()
        except Exception as e:
            # 记录错误信息
            logger.error(f"数据库操作失败: {e}")
            raise
        finally:
            await cursor.close()

    if not commands:
        return

    df_commands = pd.DataFrame(
        commands, columns=['command', 'handler_list', 'full_match'])
    best_match, best_match_handlers, exact_match, highest_similarity = None, [], False, 0.0

    # 检查精确匹配
    exact_matches = df_commands[df_commands['command'] == message]
    if not exact_matches.empty:
        best_match = exact_matches.iloc[0]['command']
        best_match_handlers = exact_matches.iloc[0]['handler_list'].split(',')
        exact_match = True
    else:
        # 计算命令的空格数量
        df_commands['command_spaces'] = df_commands['command'].str.count(' ')
        # 获取消息的前N个单词
        message_split = message.split(' ')
        df_commands['message_n_plus_1_space_content'] = df_commands['command_spaces'].apply(
            lambda spaces: ' '.join(
                message_split[:spaces + 1]) if spaces + 1 <= len(message_split) else ''
        )

        # 查找非完全匹配命令
        matches = df_commands[(~df_commands['full_match']) & (
            df_commands['command'] == df_commands['message_n_plus_1_space_content'])]
        if not matches.empty:
            best_match = matches.iloc[0]['command']
            best_match_handlers = matches.iloc[0]['handler_list'].split(',')
            exact_match = True

        # 计算相似度
        if not df_commands.empty:
            df_commands['similarity'] = df_commands.apply(
                lambda row: _ngram_similarity(
                    row['message_n_plus_1_space_content'], row['command'])
                if row['command_spaces'] + 1 <= len(message_split) else 0.0, axis=1
            )
            # 找到相似度最高的行
            max_similarity = df_commands['similarity'].max()
            best_match_rows = df_commands[df_commands['similarity']
                                          == max_similarity]
            print(max_similarity)
            if len(best_match_rows) == 1 and max_similarity >= 0.4:
                logger.debug(f"相似度最高的命令是：{best_match_rows.iloc[0]['command']},相似度为：{
                             max_similarity}")
                best_match_row = best_match_rows.iloc[0]
                best_match = best_match_row['command']
                best_match_handlers = best_match_row['handler_list'].split(',')
                highest_similarity = best_match_row['similarity']
            else:
                return

    # 确保字符数差异符合要求
    if best_match:
        command_full_match = df_commands[df_commands['command']
                                         == best_match]['full_match'].iloc[0]
        if command_full_match and abs(len(message) - len(best_match)) >= 1:
            return

        # 替换消息内容
        if not exact_match:
            message_parts = message.split(' ')
            command_spaces = best_match.count(' ')
            if command_spaces + 1 <= len(message_parts):
                message_parts[:command_spaces + 1] = best_match.split(' ')
                message = ' '.join(message_parts)

    # 继续执行处理程序
    if best_match:
        for handler_id in best_match_handlers:
            handler = BasicHandler.get_handler_by_id(int(handler_id))
            if handler:
                if await handler.should_handle(msg=message, image=image, qq=str(event.user_id), groupid=groupid, bot=bot, event=event, highest_similarity=highest_similarity, best_match_handlers=best_match_handlers):
                    asyncio.create_task(handler.handle(msg=message, image=image, qq=str(
                        event.user_id), groupid=groupid, bot=bot, event=event, best_match_handlers=best_match_handlers, **(private_vars or {})))
                    if await handler.should_block(msg=message, image=image, qq=str(event.user_id), groupid=groupid, bot=bot, event=event, highest_similarity=highest_similarity, best_match_handlers=best_match_handlers):
                        raise StopPropagation

if __name__ == '__main__':
    class HandlerA(BasicHandler):
        async def handle(self, bot: Bot, event: GroupMessageEvent | PrivateMessageEvent, msg: str, qq: str, groupid: str, image: str | None, **kwargs: Any) -> None:
            print(f'{self.handler_id} and Handler is running')
    CommandFactory.create_command(
        ['/ChangeGtype', '/ChangeCtype'], 'test command', 'test', False, [HandlerA()])

    async def test():
        await dispatch('/Changetype 1', None, None)
    asyncio.run(test())
