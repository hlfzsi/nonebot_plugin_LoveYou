from .config import result
from . import DATA_DIR

from nonebot import logger
import sqlite3
import aiosqlite
import httpx
import os
import io
from PIL import Image
import base64
import string
import random
from typing import List, Optional, Dict, Tuple
(
    bot_name, baseline, rate, master,
    search_love_reply, botreact, model, role,
    API_Key, Secret_Key, tank_enable, Ca, Cb,
    lv_enable, La, Lb, Lc, Ld,
    Le, Lf, Lg, Lh, Li, Lj,
    lv1_reply, lv2_reply, lv3_reply, lv4_reply, lv5_reply, memory
) = result
db_path = os.path.join(DATA_DIR, 'qq.db3')


def start_db():
    logger.info('检查数据库...')

    try:
        # 尝试连接数据库，如果文件不存在则会自动创建
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            # 定义表名和列信息
            tables = [
                {
                    'name': 'qq_love',
                    'columns': [
                        ('QQ', 'TEXT', 'PRIMARY KEY UNIQUE'),
                        ('love', 'INTEGER', 'DEFAULT 0'),
                        ('alias', 'TEXT', 'DEFAULT ""'),
                        ('extra', 'TEXT', 'DEFAULT ""'),
                        ('pic', 'BLOB'),
                        ('real_id', 'TEXT', 'UNIQUE'),
                        ('state', 'INTEGER', 'DEFAULT 0')
                    ],
                    'indexes': [
                        ('idx_real_id', 'real_id'),
                        ('idx_alias', 'alias'),
                        ('idx_love', 'love'),
                        ('idx_qq', 'QQ')
                    ]
                },
                {
                    'name': 'code',
                    'columns': [
                        ('code', 'TEXT', 'PRIMARY KEY UNIQUE'),
                        ('userid', 'TEXT', 'DEFAULT ""'),
                        ('count', 'INTEGER', 'DEFAULT 5'),
                        ('type', 'TEXT', 'DEFAULT alias')
                    ],
                    'indexes': [
                        ('idx_code_code', 'code'),
                        ('idx_code_userid', 'userid'),
                        ('idx_code_type', 'type')
                    ]
                }
            ]

            # 遍历表格定义，创建或更新表
            for table_def in tables:
                # 检查表是否存在
                cursor.execute('''
                    SELECT name
                    FROM sqlite_master
                    WHERE type='table' AND name=:name;
                ''', {'name': table_def['name']})
                table_exists = cursor.fetchone() is not None

                # 如果表不存在，则创建新表
                if not table_exists:
                    create_table_sql = f'''
                        CREATE TABLE {table_def['name']} (
                            {', '.join([f"{col[0]} {col[1]}" + (f" {col[2]}" if len(col)
                                                                > 2 else '') for col in table_def['columns']])}
                        );
                    '''
                    cursor.execute(create_table_sql)
                else:
                    # 如果表存在，检查并添加缺失的列
                    cursor.execute(f"PRAGMA table_info({table_def['name']})")
                    existing_columns = [col[1] for col in cursor.fetchall()]

                    for col in table_def['columns']:
                        if col[0] not in existing_columns:
                            alter_table_sql = f"ALTER TABLE {table_def['name']} ADD COLUMN {col[0]} {col[1]}" + (
                                f" {col[2]}" if len(col) > 2 else '')
                            cursor.execute(alter_table_sql)

                    # 确保索引存在
                if 'indexes' in table_def:
                    for index_name, index_column in table_def['indexes']:
                        cursor.execute(
                            f"SELECT name FROM sqlite_master WHERE type='index' AND name='{index_name}'")
                        index_exists = cursor.fetchone() is not None
                        if not index_exists:
                            create_index_sql = f"CREATE INDEX {index_name} ON {
                                table_def['name']}({index_column})"
                            cursor.execute(create_index_sql)

            conn.commit()

    except sqlite3.Error as e:
        logger.error(f"An error occurred: {e}")

    finally:
        # 关闭数据库连接
        if conn:
            conn.close()

    logger.info('数据库检查完成')


def get_range(value: int) -> Optional[int]:
    """获取好感等级"""
    # 定义范围和对应的级别
    ranges = {
        (La, Lb): 1,
        (Lc, Ld): 2,
        (Le, Lf): 3,
        (Lg, Lh): 4,
        (Li, Lj): 5,
    }

    # 查找符合条件的第一个范围
    for lower_bound, upper_bound in ranges:
        if lower_bound <= value < upper_bound:
            level = ranges[(lower_bound, upper_bound)]
            logger.debug(f'获得lv{level}')
            return level

    # 如果没有找到匹配的范围
    logger.debug('未获得lv')
    return None


async def replace_qq(qq: str) -> str:
    """
    使用别名替代QQ
    """
    alias = await read_alias(qq)
    if alias != '':
        return alias
    else:
        return qq


async def del_qq_record(qq: str, columns_to_reset: List[str]) -> bool:
    try:
        async with aiosqlite.connect(db_path) as conn:
            cursor = await conn.cursor()

            # 首先检查qq是否存在于数据库中
            await cursor.execute('SELECT QQ FROM qq_love WHERE QQ = ?', (qq,))
            if await cursor.fetchone() is None:
                # 如果找不到对应的QQ，直接返回
                return False

            if columns_to_reset == ['']:
                await cursor.execute('DELETE FROM qq_love WHERE QQ = ?', (qq,))
            else:
                set_clauses = []
                for col in columns_to_reset:
                    if col == 'pic':
                        set_clauses.append(f"{col} = NULL")
                    elif col in ['alias', 'extra']:
                        set_clauses.append(f"{col} = ''")
                    elif col == 'love':
                        set_clauses.append(f"{col} = 0")

                set_clause = ', '.join(set_clauses)
                query = f'''
                    UPDATE qq_love
                    SET {set_clause}
                    WHERE QQ = ?
                '''
                if set_clause:
                    await cursor.execute(query, (qq,))

            await conn.commit()
            return True
    except Exception as e:
        logger.error(f"An error occurred while deleting the record: {e}")
        return False


async def read_extra(qq: str) -> str:
    """
    读取QQ的好感后缀
    """
    try:
        async with aiosqlite.connect(db_path) as conn:
            cursor = await conn.cursor()

            # 尝试从qq_love表中读取extra
            await cursor.execute('''
                SELECT extra FROM qq_love WHERE QQ = ?;
            ''', (qq,))
            result = await cursor.fetchone()

            if result is None:
                # 如果没有找到，插入新记录
                await cursor.execute('''
                    INSERT INTO qq_love (QQ, love, alias, extra, pic) VALUES (?, 0, '', '', zeroblob(0));
                ''', (qq,))
                await conn.commit()
                return ''
            else:
                # 如果找到了，返回extra
                return result[0] or ''
    except Exception as e:
        # 记录错误信息
        logger.warning(f"An error occurred while reading extra: {e}")
        return ''


async def get_real_id(qq: str) -> Optional[str]:
    """
    获取指定QQ在qq_love表中的real_id值。

    如果找不到对应记录，则返回None。
    """
    try:
        async with aiosqlite.connect(db_path) as conn:
            cursor = await conn.cursor()

            # 查询数据
            await cursor.execute('SELECT real_id FROM qq_love WHERE QQ = ?', (qq,))
            result = await cursor.fetchone()

            # 返回结果
            return result[0] if result else None
    except Exception as e:
        # 记录错误信息
        logger.warning(f"An error occurred while fetching real_id: {e}")
        return None


async def get_qq_by_real_id(real_id: str) -> str:
    """
    根据real_id查询qq_love表中的QQ。

    如果找不到对应的记录，则返回real_id。
    """
    try:
        async with aiosqlite.connect(db_path) as conn:
            cursor = await conn.cursor()

            # 查询数据
            await cursor.execute('SELECT QQ FROM qq_love WHERE real_id = ?', (real_id,))
            result = await cursor.fetchone()

            # 返回结果
            return result[0] if result else real_id
    except:
        return real_id


async def update_real_id(qq: str, real_id: str) -> None:
    """
    更新指定QQ在qq_love表中的real_id值。如果real_id已存在，则抛出异常。
    """
    try:
        async with aiosqlite.connect(db_path) as conn:
            cursor = await conn.cursor()

            # 首先检查real_id是否已存在
            await cursor.execute('SELECT 1 FROM qq_love WHERE real_id = ?', (real_id,))
            if await cursor.fetchone():
                raise ValueError("The real_id already exists in the database.")

            # 更新数据
            await cursor.execute('UPDATE qq_love SET real_id = ? WHERE QQ = ?', (real_id, qq))

            # 检查是否更新成功
            if cursor.rowcount == 0:
                # 如果没有更新任何行，那么尝试插入新记录
                await cursor.execute('INSERT INTO qq_love (QQ, real_id) VALUES (?, ?)', (qq, real_id))

            # 提交事务
            await conn.commit()
    except Exception as e:
        # 记录错误信息
        logger.warning(f"An error occurred while updating real_id: {e}")
        raise


async def write_str_love(qq: str, str_value: str) -> None:
    """
    更新或插入QQ的好感后缀。
    """
    try:
        async with aiosqlite.connect(db_path) as conn:
            cursor = await conn.cursor()

            # 更新或插入数据
            await cursor.execute('''
                INSERT INTO qq_love (QQ, extra) VALUES (?, ?)
                ON CONFLICT(QQ) DO UPDATE SET extra=excluded.extra;
            ''', (qq, str_value))

            # 提交事务
            await conn.commit()
    except Exception as e:
        # 记录错误信息
        logger.warning(f"An error occurred while writing extra: {e}")


async def write_pic(qq: str, pic_url: str) -> None:
    """
    下载图片并将其保存到数据库。
    """
    try:
        # 下载图片
        async with httpx.AsyncClient() as client:
            response = await client.get(pic_url)
            response.raise_for_status()  # 抛出HTTP错误
            response_content = response.read()

        # 使用PIL将图片数据转换为Image对象
        image = Image.open(io.BytesIO(response_content))

        # 将图片转换为JPEG格式
        output = io.BytesIO()
        image.convert("RGB").save(output, format="JPEG")
        jpeg_data = output.getvalue()

        # 连接到数据库
        async with aiosqlite.connect(db_path) as conn:
            cursor = await conn.cursor()

            # 检查qq_love表中是否已有该QQ的记录
            await cursor.execute('SELECT pic FROM qq_love WHERE QQ = ?', (qq,))
            result = await cursor.fetchone()

            if result is None:
                # 如果没有找到，插入新记录
                await cursor.execute('''
                    INSERT INTO qq_love (QQ, love, alias, extra, pic) VALUES (?, 0, '', '', ?);
                ''', (qq, jpeg_data))
            else:
                # 如果找到了，更新pic字段
                await cursor.execute(
                    'UPDATE qq_love SET pic = ?, state = 0 WHERE QQ = ?', (
                        jpeg_data, qq)
                )

            # 提交事务
            await conn.commit()
    except Exception as e:
        # 记录错误信息
        logger.warning(f"An error occurred while writing the picture: {e}")


async def decrement_count(code_to_decrement: str, code_type: str) -> int:
    """
    将指定类型的code的count字段减1，并在减至小于等于0时删除该code记录。

    参数:
    code_to_decrement (str): 要减1的code。
    code_type (str): 指定的code类型，可以是'alias', 'love', 'pic'。

    返回:
    int: 减1后的count值。
    """
    async with aiosqlite.connect(db_path) as db:
        # 查询code是否存在及其count值
        cursor = await db.execute('SELECT code, count FROM code WHERE code = ? AND type = ?', (code_to_decrement, code_type))
        result = await cursor.fetchone()
        await cursor.close()  # 关闭游标

        if result is None:
            # 如果code不存在
            return -1  # 表示code不存在

        _, count = result

        if count > 0:
            new_count = count - 1
            if new_count <= 0:
                # 如果减1后count小于等于0，则删除记录
                await db.execute('DELETE FROM code WHERE code = ? AND type = ?', (code_to_decrement, code_type))
                await db.commit()
                return -1
            else:
                # 如果减1后count大于0，则更新count
                await db.execute('UPDATE code SET count = ? WHERE code = ? AND type = ?', (new_count, code_to_decrement, code_type))
                await db.commit()
                return new_count
        else:
            # 如果count已经是0或负数，则不做任何操作
            return -1


async def read_five_codes(code_type: str) -> list:
    """
    从数据库中读取指定类型的前五个userid为空的code记录。

    参数:
    code_type (str): 指定的code类型。

    返回:
    list: 包含前五个userid为空的code记录的列表。
    """

    try:
        async with aiosqlite.connect(db_path) as db:
            # 查询userid为空的前五个指定类型的code
            cursor = await db.execute(
                'SELECT code FROM code WHERE type = ? AND userid = "" LIMIT 5;', (
                    code_type,)
            )
            codes = await cursor.fetchall()
            # 关闭游标
            await cursor.close()

        # 将结果转换成只包含code的列表
        codes_only = [row[0] for row in codes]

        return codes_only

    except Exception as e:
        logger.warning(f"读取数据库时发生错误: {e}")
        return []


async def find_qq_by_alias(alias: str, additional_filters: Dict[str, str] = None) -> List[str]:
    """
    根据别名和附加过滤条件查找QQ号码。

    参数:
    alias (str): 别名。
    additional_filters (dict): 额外的过滤条件，如 {'love': '1', 'extra': 'some_value'}。

    返回:
    List[str]: 匹配的QQ号码列表。
    """
    try:
        # 异步连接到SQLite数据库
        async with aiosqlite.connect(db_path) as conn:
            cursor = await conn.cursor()

            # 构建WHERE子句
            where_clause_parts = ['alias = ?']
            where_params = [alias]

            if additional_filters:
                for column, value in additional_filters.items():
                    if column == 'love':
                        try:
                            value = int(value)
                        except ValueError:
                            continue  # 忽略这个键值对

                    if column in ['love', 'extra']:
                        where_clause_parts.append(f"{column} = ?")
                        where_params.append(value)

            # 组装完整的查询语句
            query = f"""
                SELECT QQ
                FROM qq_love
                WHERE {' AND '.join(where_clause_parts)}
            """

            # 执行查询
            await cursor.execute(query, tuple(where_params))

            # 获取所有结果
            results = await cursor.fetchall()

            if not results:
                return ['没有匹配结果']

            # 提取QQ号码
            qqs = [row[0] for row in results]

            return qqs

    except aiosqlite.DatabaseError as e:
        logger.warning(f"数据库错误: {e}")
        return []


async def info_qq(qq: str) -> Optional[Dict[str, str]]:
    """
    根据QQ号码获取用户信息。

    参数:
    qq (str): QQ号码。

    返回:
    Optional[Dict[str, str]]: 包含用户信息的字典，如果没有匹配结果，则返回None。
    """
    try:
        # 异步连接到SQLite数据库
        async with aiosqlite.connect(db_path) as conn:
            cursor = await conn.cursor()

            # 执行查询
            query = """
                SELECT alias, extra, love, pic
                FROM qq_love
                WHERE QQ = ?
            """
            await cursor.execute(query, (qq,))

            # 获取第一条结果
            result = await cursor.fetchone()

            if result is not None:
                # 解码pic列（如果存在）
                alias, extra, love, pic = result
                if pic:
                    pic_base64 = base64.b64encode(pic).decode('utf-8')
                else:
                    pic_base64 = None

                # 返回所有信息
                return {
                    'QQ': qq,
                    'alias': alias,
                    'extra': extra,
                    'love': love,
                    'pic': pic_base64
                }
            else:
                return None

    except aiosqlite.DatabaseError as e:
        logger.warning(f"数据库错误: {e}")
        return None


async def update_alias(qq: str, str_value: str) -> Optional[bool]:
    """
    更新或插入指定QQ号码的别名。

    参数:
    qq (str): QQ号码。
    str_value (str): 新的别名值。

    返回:
    Optional[bool]: 如果成功更新或插入则返回True，否则返回False。
    """

    try:
        # 异步连接到SQLite数据库
        async with aiosqlite.connect(db_path) as conn:
            cursor = await conn.cursor()

            # 更新或插入数据
            await cursor.execute('''
                INSERT INTO qq_love (QQ, alias) VALUES (?, ?)
                ON CONFLICT(QQ) DO UPDATE SET alias=excluded.alias;
            ''', (qq, str_value))

            # 提交事务
            await conn.commit()

            return True

    except aiosqlite.DatabaseError as e:
        logger.warning(f"数据库错误: {e}")
        return False


async def read_alias(qq: str) -> Optional[str]:
    """
    获得指定QQ号码的别名。

    参数:
    qq (str): QQ号码。

    返回:
    Optional[str]: 如果找到别名则返回别名，否则返回空字符串。
    """

    try:
        # 异步连接到SQLite数据库
        async with aiosqlite.connect(db_path) as conn:
            cursor = await conn.cursor()

            # 尝试从qq_love表中读取alias
            await cursor.execute('''
                SELECT alias FROM qq_love WHERE QQ = ?;
            ''', (qq,))
            result = await cursor.fetchone()

            if result is None:
                # 如果没有找到，插入新记录
                await cursor.execute('''
                    INSERT INTO qq_love (QQ, love, alias, extra, pic) VALUES (?, 0, '', '', zeroblob(0));
                ''', (qq,))
                await conn.commit()
                return ''
            else:
                # 如果找到了，返回alias
                return result[0]

    except aiosqlite.DatabaseError as e:
        logger.warning(f"数据库错误: {e}")
        return ''


def replace_qq_sq(qq: str) -> str:
    """
    使用别名替代QQ。

    参数:
    qq (str): QQ号码。

    返回:
    str: 如果找到别名则返回别名，否则返回原QQ号码。
    """

    try:
        # 同步连接到SQLite数据库
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()

            # 尝试从qq_love表中读取alias
            cursor.execute('''
                SELECT alias FROM qq_love WHERE QQ = ?;
            ''', (qq,))
            result = cursor.fetchone()

            if result is None:
                # 如果没有找到，插入新记录
                cursor.execute('''
                    INSERT INTO qq_love (QQ, love, alias, extra, pic) VALUES (?, 0, '', '', zeroblob(0));
                ''', (qq,))
                conn.commit()
                return qq
            else:
                # 如果找到了，返回alias
                alias = result[0]
                return alias if alias != '' else qq

    except sqlite3.DatabaseError as e:
        logger.warning(f"数据库错误: {e}")
        return qq


async def check_code(code_to_check: str, code_type: str, qq: str) -> bool:
    """
    检查指定类型的code是否存在，并根据userid的状态进行相应的操作。

    参数:
    code_to_check (str): 要检查的code。
    code_type (str): 指定的code类型，可以是'alias', 'love', 'pic'。
    qq (str): 传入的qq号。

    返回:
    bool: 如果code存在并且userid状态符合要求，则返回True；否则返回False。
    """
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute('SELECT code, userid FROM code WHERE code = ? AND type = ?', (code_to_check, code_type))
        result = await cursor.fetchone()
        await cursor.close()

    if result is None:
        # 如果code不存在
        return False

    _, userid = result

    if userid == '':
        # 如果userid为空，则更新userid为qq
        async with aiosqlite.connect(db_path) as db:
            await db.execute('UPDATE code SET userid = ? WHERE code = ? AND type = ?', (qq, code_to_check, code_type))
            await db.commit()
        return True
    elif userid == qq:
        # 如果userid与传入的qq相同
        return True
    else:
        # 如果userid与传入的qq不同
        return False


async def update_love(qq: str, love: int) -> Optional[bool]:
    """
    更新用户的好感度。

    参数:
    qq (str): QQ号码。
    love (int): 好感变化量。

    返回:
    Optional[bool]: 如果成功更新或插入则返回True，否则返回False。
    """

    try:
        # 异步连接到SQLite数据库
        async with aiosqlite.connect(db_path) as conn:
            cursor = await conn.cursor()

            # 构造一个SQL语句，用于查找并更新
            update_sql = "UPDATE qq_love SET love = love + ? WHERE QQ = ?"

            # 尝试执行更新操作
            await cursor.execute(update_sql, (love, qq))

            # 检查是否有行被更新
            if cursor.rowcount == 0:
                # 如果没有匹配的行被更新（即没有找到匹配的QQ），则插入新记录
                insert_sql = "INSERT INTO qq_love (QQ, love) VALUES (?, ?)"
                await cursor.execute(insert_sql, (qq, love))

            # 提交事务
            await conn.commit()

            return True

    except aiosqlite.DatabaseError as e:
        logger.warning(f"数据库错误: {e}")
        return False


def update_love_sq(qq: str, love: int) -> Optional[bool]:
    """
    更新用户的好感度。

    参数:
    qq (str): QQ号码。
    love (int): 好感变化量。

    返回:
    Optional[bool]: 如果成功更新或插入则返回True，否则返回False。
    """

    try:
        # 同步连接到SQLite数据库
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()

            # 构造一个SQL语句，用于查找并更新
            update_sql = "UPDATE qq_love SET love = love + ? WHERE QQ = ?"

            # 尝试执行更新操作
            cursor.execute(update_sql, (love, qq))

            # 检查是否有行被更新
            if cursor.rowcount == 0:
                # 如果没有匹配的行被更新（即没有找到匹配的QQ），则插入新记录
                insert_sql = "INSERT INTO qq_love (QQ, love) VALUES (?, ?)"
                cursor.execute(insert_sql, (qq, love))

            # 提交事务
            conn.commit()

        return True

    except sqlite3.DatabaseError as e:
        logger.warning(f"数据库错误: {e}")
        return False


async def read_love(qq: str) -> Optional[int]:
    """
    读取用户的当前好感度。

    参数:
    qq (str): QQ号码。

    返回:
    Optional[int]: 如果记录存在，则返回好感度值；如果记录不存在，则插入新记录并返回0。
    """

    try:
        # 异步连接到SQLite数据库
        async with aiosqlite.connect(db_path) as conn:
            cursor = await conn.cursor()

            # 尝试查询记录
            await cursor.execute("SELECT love FROM qq_love WHERE QQ=?", (qq,))
            result = await cursor.fetchone()

            # 如果记录存在，返回love的值
            if result:
                return result[0]
            else:
                # 如果记录不存在，插入新记录
                await cursor.execute(
                    "INSERT INTO qq_love (QQ, love, alias, extra, pic) VALUES (?, 0, '', '', zeroblob(0))",
                    (qq,)
                )
                # 提交事务
                await conn.commit()
                # 新增后默认返回0
                return 0

    except aiosqlite.DatabaseError as e:
        logger.warning(f"数据库错误: {e}")
        return 0


def read_love_sq(qq: str) -> Optional[int]:
    """
    读取用户的当前好感度。

    参数:
    qq (str): QQ号码。

    返回:
    Optional[int]: 如果记录存在，则返回好感度值；如果记录不存在，则插入新记录并返回0。
    """

    try:
        # 同步连接到SQLite数据库
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()

            # 尝试查询记录
            cursor.execute("SELECT love FROM qq_love WHERE QQ=?", (qq,))
            result = cursor.fetchone()

            # 如果记录存在，返回love的值
            if result:
                return result[0]
            else:
                # 如果记录不存在，插入新记录
                cursor.execute(
                    "INSERT INTO qq_love (QQ, love, alias, extra, pic) VALUES (?, 0, '', '', zeroblob(0))",
                    (qq,)
                )
                # 提交事务
                conn.commit()
                # 新增后默认返回0
                return 0

    except sqlite3.DatabaseError as e:
        logger.warning(f"数据库错误: {e}")
        return 0


async def get_loverank(qq: str) -> Tuple[str, str]:
    """
    返回用户的好感排名以及整张表的记录数。

    参数:
    qq (str): QQ号码。

    返回:
    Tuple[str, str]: 用户的好感排名和整张表的记录数。
    """

    try:
        # 异步连接到SQLite数据库
        async with aiosqlite.connect(db_path) as conn:
            cursor = await conn.cursor()

            # 获取总记录数
            await cursor.execute("SELECT COUNT(*) FROM qq_love")
            total_records = (await cursor.fetchone())[0]

            # 使用窗口函数来获取排名
            await cursor.execute("""
                WITH RankedUsers AS (
                    SELECT QQ, love, 
                           RANK() OVER (ORDER BY love DESC) AS rank
                    FROM qq_love
                )
                SELECT rank
                FROM RankedUsers
                WHERE QQ = ?
            """, (qq,))

            rank_result = await cursor.fetchone()

            if rank_result:
                rank = rank_result[0]
                return str(rank), str(total_records)
            else:
                return 'Unfound', str(total_records)

    except aiosqlite.DatabaseError as e:
        logger.warning(f"数据库错误: {e}")
        return 'Error', 'Error'


async def read_love_only(qq: str) -> Optional[int]:
    """
    读取用户的当前好感度。

    参数:
    qq (str): QQ号码。

    返回:
    Optional[int]: 如果记录存在，则返回好感度值；如果记录不存在，则返回None。
    """

    try:
        # 异步连接到SQLite数据库
        async with aiosqlite.connect(db_path) as conn:
            cursor = await conn.cursor()

            # 尝试查询记录
            await cursor.execute("SELECT love FROM qq_love WHERE QQ=?", (qq,))
            result = await cursor.fetchone()

            # 如果记录存在，返回love的值
            if result:
                return result[0]
            else:
                return None

    except aiosqlite.DatabaseError as e:
        logger.warning(f"数据库错误: {e}")
        return None


async def get_both_love_only(qq):
    """
    与get_both_love函数的唯一区别在于这个函数是只读的,不会插入记录
    """
    # 初始化返回值
    love = await read_love_only(qq)
    if love != None:
        int_love = love
        str_love = ''

        # 检查qq
        extra = await read_extra(qq)
        if extra != '':
            extra = f' {extra}'
        str_love = f'{int_love}{extra}'

        # 返回两个值
        return int_love, str_love

    else:
        return None, None


async def get_both_love(qq: str) -> Tuple[int, str]:
    """获得好感度,如果qq不存在则插入记录

    Args:
        qq (str):用户qq号

    Returns:
        数值好感(int),文本好感(str)
    """
    # 初始化返回值
    int_love = await read_love(qq)
    str_love = ''

    # 检查qq
    extra = await read_extra(qq)
    if extra != '':
        extra = f' {extra}'
    str_love = f'{int_love}{extra}'

    # 返回两个值
    return int_love, str_love


async def read_pic(qq: str, readonly: bool = False) -> str:
    """
    获得QQ的好感回复图片
    return : base64 encoded string or ''
    """
    try:
        async with aiosqlite.connect(db_path) as conn:
            cursor = await conn.cursor()

            # 尝试从qq_love表中读取pic
            await cursor.execute('''
                SELECT pic,state FROM qq_love WHERE QQ = ?;
            ''', (qq,))
            result = await cursor.fetchone()

            if result is None or result[1] == 0:
                if readonly or result[1] == 0:
                    return ''
                else:
                    # 如果结果为空（即没有找到QQ），则插入新记录
                    await cursor.execute('''
                        INSERT INTO qq_love (QQ, love, alias, extra, pic) VALUES (?, 0, '', '', zeroblob(0));
                    ''', (qq,))
                    await conn.commit()
                    return ''
            else:
                pic = result[0]
                # 如果pic为None（即数据库中为NULL），返回空字符串
                return base64.b64encode(pic).decode('utf-8') if pic is not None else ''
    except Exception as e:
        # 记录错误信息
        logger.warning(f"An error occurred while reading the picture: {e}")
        return ''


async def del_qq_record(qq: str, columns_to_reset: List[str]) -> bool:
    try:
        async with aiosqlite.connect(db_path) as conn:
            cursor = await conn.cursor()

            # 首先检查qq是否存在于数据库中
            await cursor.execute('SELECT QQ FROM qq_love WHERE QQ = ?', (qq,))
            if await cursor.fetchone() is None:
                # 如果找不到对应的QQ，直接返回
                return False

            if columns_to_reset == ['']:
                await cursor.execute('DELETE FROM qq_love WHERE QQ = ?', (qq,))
            else:
                set_clauses = []
                for col in columns_to_reset:
                    if col == 'pic':
                        set_clauses.append(f"{col} = NULL")
                    elif col in ['alias', 'extra', 'real_id']:
                        set_clauses.append(f"{col} = ''")
                    elif col == 'love':
                        set_clauses.append(f"{col} = 0")

                set_clause = ', '.join(set_clauses)
                query = f'''
                    UPDATE qq_love
                    SET {set_clause}
                    WHERE QQ = ?
                '''
                if set_clause:
                    await cursor.execute(query, (qq,))

            await conn.commit()
            return True
    except Exception as e:
        logger.error(f"An error occurred while deleting the record: {e}")
        return False


async def info_qq(qq: str) -> Optional[Dict[str, str]]:
    """
    根据QQ号码获取用户信息。

    参数:
    qq (str): QQ号码。

    返回:
    Optional[Dict[str, str]]: 包含用户信息的字典，如果没有匹配结果，则返回None。
    """
    try:
        # 异步连接到SQLite数据库
        async with aiosqlite.connect(db_path) as conn:
            cursor = await conn.cursor()

            # 执行查询
            query = """
                SELECT alias, extra, love, pic
                FROM qq_love
                WHERE QQ = ?
            """
            await cursor.execute(query, (qq,))

            # 获取第一条结果
            result = await cursor.fetchone()

            if result is not None:
                # 解码pic列（如果存在）
                alias, extra, love, pic = result
                if pic:
                    pic_base64 = base64.b64encode(pic).decode('utf-8')
                else:
                    pic_base64 = None

                # 返回所有信息
                return {
                    'QQ': qq,
                    'alias': alias,
                    'extra': extra,
                    'love': love,
                    'pic': pic_base64
                }
            else:
                return None

    except aiosqlite.DatabaseError as e:
        logger.warning(f"数据库错误: {e}")
        return None


async def generate_codes(a, b):
    '''
    a为数目,b为类型
    '''
    a = int(a)
    b = int(b)
    characters = string.ascii_letters + string.digits
    type_map = {0: 'alias', 1: 'love', 2: 'pic'}
    code_type = type_map.get(b, 'alias')

    async with aiosqlite.connect(db_path) as db:
        # 确保我们有足够的唯一code
        generated_count = 0
        while generated_count < a:
            # 一次性生成多个code以提高效率
            new_codes = {''.join(random.choices(characters, k=8))
                         for _ in range(a - generated_count)}

            # 尝试插入新的code
            try:
                await db.executemany('INSERT INTO code (code, type) VALUES (?, ?)', [(code, code_type) for code in new_codes])
                await db.commit()
                generated_count += len(new_codes)
            except aiosqlite.IntegrityError:
                # 如果有code冲突，则忽略错误并再次尝试生成新的code
                pass


async def get_low_ten_qqs() -> List[str]:
    """
    查询并返回好感度最低的前10名用户的QQ号。

    返回:
    List[str]: 包含好感度最低的前10名用户的QQ号列表。
    """

    try:
        # 异步连接到SQLite数据库
        async with aiosqlite.connect(db_path) as conn:
            cursor = await conn.cursor()

            # 执行 SQL 查询语句
            query = "SELECT QQ FROM qq_love ORDER BY love ASC LIMIT 10"
            await cursor.execute(query)

            # 获取查询结果，并转换为列表
            results = await cursor.fetchall()
            low_ten_qqs = [row[0] for row in results]

            # 返回结果列表
            return low_ten_qqs

    except aiosqlite.DatabaseError as e:
        # 如果出现错误，打印错误信息并返回空列表
        logger.warning(f"数据库错误: {e}")
        return []


async def global_compare() -> List[str]:
    """
    查询并返回好感度最高的前10名用户的QQ号。

    返回:
    List[str]: 包含好感度最高的前10名用户的QQ号列表。
    """

    try:
        # 异步连接到SQLite数据库
        async with aiosqlite.connect(db_path) as conn:
            cursor = await conn.cursor()

            # 编写SQL查询语句
            sql = "SELECT QQ FROM qq_love ORDER BY love DESC LIMIT 10"

            # 执行SQL查询
            await cursor.execute(sql)

            # 获取查询结果
            results = await cursor.fetchall()

            # 处理查询结果
            qq_list = [row[0] for row in results]

            # 返回结果列表
            return qq_list

    except aiosqlite.DatabaseError as e:
        # 如果出现错误，打印错误信息并返回空列表
        logger.warning(f"数据库错误: {e}")
        return []


async def get_low_ten_qqs() -> List[str]:
    """
    查询并返回好感度最低的前10名用户的QQ号。

    返回:
    List[str]: 包含好感度最低的前10名用户的QQ号列表。
    """

    try:
        # 异步连接到SQLite数据库
        async with aiosqlite.connect(db_path) as conn:
            cursor = await conn.cursor()

            # 执行 SQL 查询语句
            query = "SELECT QQ FROM qq_love ORDER BY love ASC LIMIT 10"
            await cursor.execute(query)

            # 获取查询结果，并转换为列表
            results = await cursor.fetchall()
            low_ten_qqs = [row[0] for row in results]

            # 返回结果列表
            return low_ten_qqs

    except aiosqlite.DatabaseError as e:
        # 如果出现错误，打印错误信息并返回空列表
        logger.warning(f"数据库错误: {e}")
        return []
