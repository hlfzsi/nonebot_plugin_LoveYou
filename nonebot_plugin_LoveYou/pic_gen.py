from PIL import Image, ImageDraw, ImageFont
import re
import os
import cv2
import numpy as np
import random
import io
import asyncio
import time
from . import DATA_DIR
import base64
import httpx
from typing import List, Dict, Tuple
from functools import lru_cache
from PIL import ImageDraw, ImageFont, Image
from nonebot import logger
from .love_manager import get_both_love, get_range, replace_qq
from .config import result
from .AI_chat import qingyunke, baidu_ai
(
    bot_name, baseline, rate, master,
    search_love_reply, botreact, model_chat, role,
    API_Key, Secret_Key, tank_enable, Ca, Cb,
    lv_enable, La, Lb, Lc, Ld,
    Le, Lf, Lg, Lh, Li, Lj,
    lv1_reply, lv2_reply, lv3_reply, lv4_reply, lv5_reply, memory
) = result


@lru_cache(maxsize=1)
def load_model_image(path):
    if not os.path.exists(path):
        logger.error("模型图片不存在")
        return None
    return cv2.imread(path, cv2.IMREAD_UNCHANGED)


async def pic_reply(qq, pre_pic, name, avatarurl):
    start_time = time.time()
    int_love, str_love = await get_both_love(qq)
    lv = get_range(int_love)
    if lv is None and int_love > 0:
        lv = 5
        lv_r = 'Nan'
    elif lv is None and int_love <= 0:
        lv = 1
        lv_r = 'Nan'
    else:
        lv_r = str(lv)
    if model_chat != 'qingyunke':
        comment = asyncio.create_task(
            baidu_ai(f'你有什么想对我说的话', qq, int_love, name, str(lv)))
    else:
        comment = asyncio.create_task(qingyunke(f'我在{bot_name}心中的印象是什么'))

    def glass_effect(img, regions, blur_radius=3):
        for x, y, w, h in regions:
            region = img[y:y+h, x:x+w]
            blurred_region = cv2.GaussianBlur(
                region, (blur_radius*2+1, blur_radius*2+1), 0)
            img[y:y+h, x:x+w] = blurred_region
        return img

    def truncate_text(text: str):
        # 如果文本长度小于等于49，直接返回
        if len(text) <= 49:
            return text

        # 定义中英文标点符号
        punctuation = r'[。！？”’》〉」』】〕、·…—～﹏`\'\"!@#$%^&*()-_=+]}|;:.>/?]\(（'

        # 在第29个字符后查找第一个标点符号，直到第90个字符
        match = re.search(punctuation, text[49:90])
        if match:
            # 标点符号的位置，加上之前的49个字符的长度
            punctuation_pos = match.start() + 49

            # 如果标点符号位置在90个字符以内
            if punctuation_pos < 90:
                return text[:punctuation_pos + 1]  # 包括标点符号

        # 如果在49到90个字符之间没有找到标点符号，检查0到49个字符内是否有标点符号
        early_match = re.search(punctuation, text[:49])
        if early_match:
            # 标点符号的位置
            punctuation_pos = early_match.start()

            # 如果在前49个字符内找到标点符号
            return text[:punctuation_pos + 1]  # 包括标点符号

        # 如果在0到49个字符内没有找到标点符号，尝试在最后一个换行符处截断
        newline_pos = text.rfind('\n', 0, 90)
        if newline_pos != -1:
            return text[:newline_pos]  # 不包括换行符

        # 如果没有找到任何标点符号或换行符，直接在第70个字符处截断
        return text[:90]

    def auto_wrap_text(text: str):
        """ 将文本每13个字自动换行，忽略已存在的换行符并重新计数。 """
        wrapped_text = []
        word_count = 0

        for char in text:
            if char == '\n':
                # 如果遇到换行符，添加到结果中并重置计数器
                wrapped_text.append(char)
                word_count = 0
            else:
                wrapped_text.append(char)
                word_count += 1
                if word_count == 13:
                    # 如果到达13个字，则添加换行符并重置计数器
                    wrapped_text.append('\n')
                    word_count = 0

        return ''.join(wrapped_text).strip()

    def is_image_file(filename):
        # 判断一个文件名是否为图片文件
        return any(filename.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.bmp'])

    def pick_pic(path, number):
        # 构造对应number的文件夹路径
        folder_path = os.path.join(path, str(number))
        # 获取文件夹中的所有文件和子目录
        files = os.listdir(folder_path)

        # 过滤出图片文件
        image_files = [os.path.join(folder_path, f)
                       for f in files if is_image_file(f)]

        # 如果没有图片文件，则返回一个错误消息
        if not image_files:
            logger.error('无对应贴画可供使用')

        # 随机选择一个图片文件
        chosen_image = random.choice(image_files)

        # 返回完整图片路径
        return chosen_image

    def add_texts(img: np.ndarray, texts: List[Dict[str, any]], font_path: str = os.path.join(DATA_DIR, 'arial.ttf')) -> str:
        """
        在图像上添加多个居中文本。

        参数:
        img (np.ndarray): 要添加文本的基础图像（OpenCV格式）。

        texts (list of dict): 每个元素都是一个字典，包含以下键值对：
                            - 'text': str, 要添加的文本内容。

                            - 'position': tuple, 文本的中心位置 (x, y)。

                            - 'font_size': int, 字体大小。

                            - 'color': tuple, 文本颜色 (R, G, B, A) 或者 (R, G, B)。
        font_path (str): 字体文件的路径，默认为'arial.ttf'。
        """
        # 将OpenCV图像转换为Pillow图像
        if img.shape[2] == 4:  # 如果图像有Alpha通道
            img_pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGRA2RGBA))
        else:  # 如果图像没有Alpha通道
            img_pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
        draw = ImageDraw.Draw(img_pil)

        # 预加载所有需要的字体大小
        fonts = {}
        for text_info in texts:
            font_size = text_info['font_size']
            if font_size not in fonts:
                fonts[font_size] = ImageFont.truetype(font_path, font_size)

        for text_info in texts:
            text = text_info['text']
            position = text_info['position']
            font_size = text_info['font_size']
            color = text_info['color']

            # 使用预加载的字体
            font = fonts[font_size]

            # 分割文本为多行
            lines = text.split('\n')

            # 计算每一行的宽度和高度
            line_widths = [abs(font.getbbox(line)[2] -
                               font.getbbox(line)[0]) for line in lines]
            line_heights = [
                abs(font.getbbox(line)[3] - font.getbbox(line)[1]) for line in lines]

            # 确定最长行的宽度，用于计算居中位置
            max_width = max(line_widths)

            # 计算所有行的总高度
            total_text_height = sum(line_heights)

            # 确定垂直居中的起始y坐标
            y = position[1] - total_text_height // 2

            # 计算水平居中的x坐标
            x = position[0] - max_width // 2

            # 遍历所有行并添加到图像上
            for i, line in enumerate(lines):
                # 当前行的宽度
                line_width = line_widths[i]

                # 调整x坐标以确保文本在竖直轴上对称
                adjusted_x = x + (max_width - line_width) // 2

                # 在图像上添加文字
                draw.text((adjusted_x, y), line, fill=color, font=font)

                # 更新y坐标以绘制下一行
                y += line_heights[i]

        # 将Pillow图像直接转换为JPEG格式并编码为Base64字符串
        buffered = io.BytesIO()
        img_pil.save(buffered, format="JPEG", quality=30)
        result = base64.b64encode(buffered.getvalue()).decode('utf-8')
        return result

    # 解码基础图像
    background = base64.b64decode(pre_pic)
    background = np.frombuffer(background, dtype=np.uint8)
    background = cv2.imdecode(background, cv2.IMREAD_UNCHANGED)

    background = cv2.resize(background, (1024, 1024),
                            interpolation=cv2.INTER_LANCZOS4)

    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(avatarurl, timeout=1)
            image_data = response.content
        avatar = np.frombuffer(image_data, dtype=np.uint8)
        avatar = cv2.imdecode(avatar, cv2.IMREAD_UNCHANGED)
    except:
        avatar = cv2.imread(os.path.join(
            DATA_DIR, 'images', 'essential', 'avatar.jpg'), cv2.IMREAD_UNCHANGED)

    avatar = np.frombuffer(image_data, dtype=np.uint8)
    avatar = cv2.imdecode(avatar, cv2.IMREAD_UNCHANGED)
    # 将头像设置为50%透明度
    if avatar is not None and avatar.shape[2] == 3:  # 如果没有alpha通道，添加一个
        avatar = cv2.cvtColor(avatar, cv2.COLOR_BGR2BGRA)
    avatar[:, :, 3] = 191

    # 为头像应用圆角效果
    height, width = avatar.shape[:2]
    radius = min(height, width) // 2
    mask = np.zeros((height, width), dtype=np.uint8)
    cv2.circle(mask, (width // 2, height // 2), radius, 255, -1)
    avatar = cv2.bitwise_and(avatar, avatar, mask=mask)

    cartoon_path = pick_pic(os.path.join(DATA_DIR, 'images', 'cartoon'), lv)
    if not os.path.exists(cartoon_path):
        logger.error("无对应贴画可供使用")
        return ""
    cartoon = cv2.imread(cartoon_path, cv2.IMREAD_UNCHANGED)

    model_path = os.path.join(DATA_DIR, 'images', 'essential', 'model.png')
    model = load_model_image(model_path)
    if model is None:
        return ""

    model = cv2.resize(model, (1024, 1024), interpolation=cv2.INTER_LANCZOS4)
    avatar = cv2.resize(avatar, (375, 375), interpolation=cv2.INTER_LANCZOS4)
    cartoon = cv2.resize(cartoon, (375, 375), interpolation=cv2.INTER_LANCZOS4)

    # 应用毛玻璃效果
    background = glass_effect(
        background, [(45, 62, 522, 121), (45, 252, 520, 694)])

    # 叠加图像
    def merge_layers(bottom: np.ndarray, top: np.ndarray, pos: Tuple[int, int]) -> np.ndarray:
        x, y = pos
        h, w, c = top.shape

        # 如果top图像是BGR格式，先转为BGRA
        if c == 3:
            top = cv2.cvtColor(top, cv2.COLOR_BGR2BGRA)

        # 创建一个与bottom相同大小的临时图像
        result = bottom.copy()

        # 确保不会越界
        if x < 0 or y < 0 or (x + w) > bottom.shape[1] or (y + h) > bottom.shape[0]:
            raise ValueError(
                "Position and size of top image exceed the boundaries of the bottom image.")

        # 获取要覆盖的区域
        roi = result[y:y+h, x:x+w]

        # 提取top图像的alpha通道并归一化
        top_alpha = top[:, :, 3] / 255.0

        # 对每个颜色通道应用Alpha混合
        for i in range(3):
            # 使用Alpha通道混合颜色
            roi[:, :, i] = (1.0 - top_alpha) * roi[:, :, i] + \
                top_alpha * top[:, :, i]

        return result

    background = merge_layers(background, model, (0, 0))
    background = merge_layers(background, avatar, (610, 75))
    background = merge_layers(background, cartoon, (610, 545))

    qq = await replace_qq(qq)
    str_love = str_love.replace(' ', '\n', 1)

    # 添加文本
    texts = [
        {'text': qq, 'position': (310, 113), 'font_size': 50,
         'color': (220, 220, 220)},
        {'text': f'好感度:{str_love}', 'position': (
            300, 372), 'font_size': 45, 'color': (0, 0, 0)},
        {'text': f'好感等级Lv.{lv_r}', 'position': (
            300, 500), 'font_size': 45, 'color': (0, 0, 0)}
    ]
    comment = await comment

    if comment:  # 如果有评论
        comment = truncate_text(comment)
        comment = auto_wrap_text(comment)
        texts.append({'text': comment, 'position': (300, 700),
                      'font_size': 35, 'color': (0, 0, 205)})

    # 使用add_texts函数添加所有文本到背景图像上
    result = add_texts(background, texts)
    end_time = time.time()
    duration = end_time - start_time
    logger.debug(f'本次图片合成耗时 {duration} ')

    return result
