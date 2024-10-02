import asyncio
import os
import io
import json
import base64
import hashlib
import aiofiles
import httpx
import glob
from httpx import AsyncClient
from pathlib import Path
from datetime import date, datetime
from PIL import Image
from imagehash import phash
from functools import wraps
from contextlib import contextmanager
from typing import Any, Optional
from . import DATA_DIR
from nonebot import logger
from .love_manager import replace_qq
from .config import result
(
    bot_name, baseline, rate, master,
    search_love_reply, botreact, model, role,
    API_Key, Secret_Key, tank_enable, Ca, Cb,
    lv_enable, La, Lb, Lc, Ld,
    Le, Lf, Lg, Lh, Li, Lj,
    lv1_reply, lv2_reply, lv3_reply, lv4_reply, lv5_reply, memory
) = result

file_locks = {}


async def get_file_lock(file_path: Path) -> asyncio.Lock:
    """
    返回给定路径的文件锁，如果不存在则创建。
    """
    if file_path not in file_locks:
        file_locks[file_path] = asyncio.Lock()
    return file_locks[file_path]


class DailyCacheDecorator:
    """
    同步装饰器类，使函数在相同输入的情况下每天只执行一次，并且使用上下文管理器自动保存缓存。
    只支持同步函数。
    """

    def __init__(self, cache_file: str = os.path.join(DATA_DIR, 'daily_cache.json')):
        self.cache_file: str = cache_file
        self.memory_cache: dict = {}
        self.last_update_date: date = None
        self.load_cache()

    def load_cache(self) -> None:
        """
        同步加载缓存文件到内存，并清除过期的缓存。
        """
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'r') as f:
                    content = f.read()
                    self.memory_cache = json.loads(content)

                    # 清理旧的缓存记录
                    current_date_str = date.today().isoformat()
                    self.memory_cache = {
                        k: v for k, v in self.memory_cache.items() if v.get('date', '') == current_date_str
                    }
            except (json.JSONDecodeError, FileNotFoundError) as e:
                logger.warning(
                    f"Error loading cache from {self.cache_file}: {e}")
                self.memory_cache = {}

        self.last_update_date = date.today()

    def save_cache(self) -> None:
        """同步将内存中的缓存保存到文件。"""
        try:
            with open(self.cache_file, 'w') as f:
                json.dump(self.memory_cache, f, indent=4)
        except IOError as e:
            logger.warning(f"Error saving cache to {self.cache_file}: {e}")

    @contextmanager
    def auto_save(self):
        """上下文管理器用于确保退出上下文时保存缓存。"""
        try:
            yield
        except Exception as e:
            logger.warning(f"Error during auto save: {e}")
        else:
            # 如果没有异常发生，则保存缓存
            self.save_cache()

    def decorator(self, func: callable) -> callable:
        '''真正需要调用的装饰器'''

        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Optional[Any]:
            current_date = date.today()
            if current_date > (self.last_update_date or current_date):
                self.memory_cache.clear()
                self.load_cache()
                self.last_update_date = current_date

            hasher = hashlib.sha256()
            hasher.update((func.__name__ + str(args) +
                          str(kwargs)).encode('utf-8'))
            key = hasher.hexdigest()

            if key not in self.memory_cache or self.memory_cache[key].get('date', '') != current_date.isoformat():
                result = func(*args, **kwargs)
                self.memory_cache[key] = {
                    'date': current_date.isoformat(),
                    'result': result
                }

                # 使用上下文管理器确保缓存被保存
                with self.auto_save():
                    pass

                return result
            else:
                return None

        return wrapper


async def tell_record(a: str, qq: str, groupid: str) -> None:
    """
    获取当前时间，并格式化为字符串（精确到秒），然后异步地将包含当前时间、群组ID、QQ号和传入字符串a的消息追加到文件中。
    """
    # 替换QQ号
    alias = await replace_qq(qq)
    if alias != qq:
        qq = f'{qq}:{alias}'

    # 获取当前时间，并格式化为字符串（精确到秒）
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M')

    # 构建要写入文件的字符串，包括时间和传入的字符串a
    message = f"{current_time}|G{groupid}|{qq}|{a}\n"

    # 获取文件路径
    file_path = os.path.join(DATA_DIR, "tell.txt")

    # 获取文件锁
    file_lock = await get_file_lock(file_path)

    # 异步地获取锁
    async with file_lock:
        # 异步地打开文件以追加模式（'a'），将内容追加到文件末尾
        async with aiofiles.open(file_path, mode='a', encoding='utf-8') as file:
            # 异步地写入消息
            await file.write(message)


async def read_five_tells(filepath: str = os.path.join(DATA_DIR, "tell.txt")) -> list:
    """
    读取文件的前五行，从原文件中删除它们，并返回被删除的行。

    参数:
    filepath (str): 要读取和修改的文件的路径。

    返回:
    list: 包含被删除的前五行的列表（如果文件行数少于五行，则返回所有行）。
    """
    # 获取文件路径
    file_path = Path(filepath)

    try:
        # 异步地打开文件以读取模式（'r'）
        async with aiofiles.open(file_path, mode='r', encoding='utf-8') as file:
            # 异步地读取所有行
            lines = await file.readlines()

        # 如果文件行数少于五行，则直接返回所有行
        if len(lines) < 5:
            return lines

        # 提取前五行
        first_five_lines = lines[:5]

        # 移除前五行
        remaining_lines = lines[5:]

        # 获取文件锁
        file_lock = await get_file_lock(file_path)

        # 异步地获取锁
        async with file_lock:
            # 将剩余内容写回文件
            async with aiofiles.open(file_path, mode='w', encoding='utf-8') as file:
                await file.writelines(remaining_lines)

        # 去除每行末尾的换行符（可选，取决于你的需求）
        first_five_lines_stripped = [line.strip() for line in first_five_lines]

        return first_five_lines_stripped

    except FileNotFoundError:
        logger.warning(f"文件 {filepath} 未找到。")
        return []


async def code_record(a: str) -> None:
    """
    获取当前时间，并格式化为字符串（精确到秒），然后异步地将包含当前时间和传入字符串a的消息追加到文件中。
    """
    # 获取当前时间，并格式化为字符串（精确到秒）
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # 构建要写入文件的字符串，包括时间和传入的字符串a
    message = f"{current_time} - {a}\n"

    # 获取文件路径
    file_path = os.path.join(DATA_DIR, 'code_users.txt')

    # 获取文件锁
    file_lock = await get_file_lock(file_path)

    # 异步地获取锁
    async with file_lock:
        # 异步地打开文件以追加模式（'a'），将内容追加到文件末尾
        async with aiofiles.open(file_path, mode='a', encoding='utf-8') as file:
            # 异步地写入消息
            await file.write(message)


async def download(url: str, filename: Path):
    """
    异步下载单个图片到指定的文件路径.

    :param url: 图片的URL地址.
    :param filename: Path实例，指向要存储下载图片的文件路径.
    """
    # 确保目录存在
    filename = Path(filename)
    filename.parent.mkdir(parents=True, exist_ok=True)

    async with httpx.AsyncClient() as client:
        async with client.stream('GET', url) as response:
            if response.status_code != 200:
                raise Exception(f"Failed to download file: status code {
                                response.status_code}")

            async with aiofiles.open(filename, 'wb') as f:
                async for chunk in response.aiter_bytes():
                    await f.write(chunk)


async def check_images_similarity(image_urls: list):
    """
    异步检查一组图片是否外观相同。

    参数:
    image_urls (list): 包含图片URL的列表。

    返回:
    bool: 如果所有图片外观相同返回True，否则返回False。
    """

    async def download_image(session: AsyncClient, url):
        """异步下载图片并计算其感知哈希值."""
        async with session.stream('GET', url) as response:
            if response.status_code != 200:
                raise Exception(f"Failed to download file: status code {
                                response.status_code}")

            image_data = io.BytesIO()
            async for chunk in response.aiter_bytes():
                image_data.write(chunk)
            image_data.seek(0)  # 重置文件指针

            image = Image.open(image_data)
            image_hash = phash(image)
            # 释放内存中的图片数据
            del image
            return image_hash

    async with httpx.AsyncClient() as session:
        # 使用并发任务下载所有图片并计算哈希值
        tasks = [download_image(session, url) for url in image_urls]
        image_hashes = await asyncio.gather(*tasks)

        # 检查所有图片的哈希值是否相同
        first_hash = image_hashes[0]
        all_same = all(hash_value == first_hash for hash_value in image_hashes)

        return all_same


def check_group_folder(groupid: str) -> str:
    '''返回群组文件夹路径'''
    folder_path = os.path.join(DATA_DIR, 'pic', groupid)
    if not os.path.exists(folder_path):
        os.makedirs(folder_path)
    return f'{folder_path}\\'


def image_to_base64(image_path):
    """
    将指定路径的图片读取并转换成 base64 格式。

    如果图片不是 JPEG 格式，则转换为 JPEG 格式。

    :param image_path: 图片的文件路径
    :return: 图片的 base64 字符串
    """
    try:
        # 打开图片文件
        with Image.open(image_path) as img:
            # 检查图片格式
            if img.format not in ['JPEG', 'JPG']:
                # 如果不是 JPEG 或 JPG，则转换为 JPEG 格式
                img = img.convert('RGB')

            # 创建一个BytesIO对象用于保存图片数据
            byte_arr = io.BytesIO()
            img.save(byte_arr, format='JPEG')
            encoded_img = base64.b64encode(byte_arr.getvalue()).decode('ascii')
        return encoded_img
    except IOError:
        logger.warning("无法打开图片，请检查路径是否正确以及是否有足够的权限。")
        return None
    except Exception as e:
        logger.warning(f"发生错误: {e}")
        return None


def find_images(path, filename):
    image_formats = ['*.jpeg', '*.jpg', '*.png']
    for format_ in image_formats:
            files = glob.glob(os.path.join(path, filename + format_))
            if files:
                return os.path.basename(files[0])
    return None
