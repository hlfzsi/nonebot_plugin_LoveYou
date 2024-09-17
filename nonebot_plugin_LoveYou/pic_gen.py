import re
import os
import random
from . import DATA_DIR
import base64
import io
import httpx
from PIL import ImageDraw, ImageFont, ImageFilter, Image
from nonebot import logger
from .love_manager import get_both_love, get_range, replace_qq
from .config import result
from .AI_chat import qingyunke, baidu_ai
(
    bot_name, baseline, rate, master,
    search_love_reply, botreact, model, role,
    API_Key, Secret_Key, tank_enable, Ca, Cb,
    lv_enable, La, Lb, Lc, Ld,
    Le, Lf, Lg, Lh, Li, Lj,
    lv1_reply, lv2_reply, lv3_reply, lv4_reply, lv5_reply, memory
) = result


async def pic_reply(qq, pre_pic, name, avatarurl):

    def truncate_text(text: str):
        # 如果文本长度小于等于49，直接返回
        if len(text) <= 49:
            return text

        # 定义中英文标点符号
        punctuation = r'[。！？”’》〉」』】〕、·…—～﹏`\'\"!@#$%^&*()-_=+]}|;:.>/?]'

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

    def add_centered_text(image: Image.Image, text: str, position, font_size: int, color, font_path=os.path.join(DATA_DIR, 'arial.ttf')):
        # 加载字体
        font = ImageFont.truetype(font_path, font_size)

        # 创建一个可以在给定图像上绘图的对象
        draw = ImageDraw.Draw(image)

        # 分割文本为多行
        lines = text.split('\n')

        # 计算每一行的宽度和高度
        line_widths = [abs(font.getbbox(line)[2] - font.getbbox(line)[0])
                       for line in lines]
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

        # 返回添加了文字的图像
        return image

    def glass_effect(img: Image.Image, regions):
        """  
        对图像中的指定区域应用毛玻璃效果（模糊处理），忽略透明度。  

        :param image_path: 原始图像文件的路径（支持RGBA格式）。  
        :param regions: 一个包含两个元组的列表，每个元组定义了一个要模糊的区域(x, y, width, height)。  
        :return: 返回一个新图像，其中指定区域被应用了模糊效果。  
        """
        for x, y, w, h in regions:
            region = img.crop((x, y, x+w, y+h))
            blurred_region = region.filter(ImageFilter.GaussianBlur(radius=3))
            img.paste(blurred_region, (x, y))
        return img
    background = base64.b64decode(pre_pic)
    background = io.BytesIO(background)
    background = Image.open(background)
    int_love, str_love = await get_both_love(qq)
    background = background.resize((1024, 1024), Image.LANCZOS)
    lv = get_range(int_love)
    if lv == None and int_love > 0:
        lv = 5
        lv_r = 'Nan'
    elif lv == None and int_love <= 0:
        lv = 1
        lv_r = 'Nan'
    else:
        lv_r = str(lv)

    async with httpx.AsyncClient() as client:
        response = await client.get(avatarurl)
        image_data = response.content
    avatar = Image.open(io.BytesIO(image_data))
    cartoon = pick_pic(os.path.join(DATA_DIR, 'images', 'cartoon'), lv)
    cartoon = Image.open(cartoon)
    model = Image.open(os.path.join(DATA_DIR, 'images', 'essential', 'model.png'))
    model = model.resize((1024, 1024), Image.LANCZOS)
    avatar = avatar.resize((375, 375), Image.LANCZOS)
    cartoon = cartoon.resize((375, 375), Image.LANCZOS)
    cartoon = cartoon.convert('RGBA')
    background = background.convert('RGBA')
    model = model.convert('RGBA')
    background = glass_effect(
        background, [(45, 62, 522, 121), (45, 252, 520, 694)])
    background.paste(avatar, (610, 545))
    background.paste(cartoon, (610, 75), cartoon)
    background.paste(model, (0, 0), model)
    qq = await replace_qq(qq)
    str_love = str_love.replace(' ', '\n', 1)
    background = add_centered_text(
        background, qq, (310, 113), 50, (220, 220, 220))
    background = add_centered_text(
        background, f'好感度:{str_love}', (300, 372), 45, (0, 0, 0))
    background = add_centered_text(
        background, f'好感等级Lv.{lv_r}', (300, 500), 45, (0, 0, 0))
    try:
        if model != 'qingyunke':
            comment = await baidu_ai(f'你有什么想对我说的话', qq, int_love, name, str(lv))
        else:
            comment = await qingyunke(f'我在{bot_name}心中的印象是什么')
    except:
        comment = ''
    if comment != '':
        comment = truncate_text(comment)
        comment = auto_wrap_text(comment)
        background = add_centered_text(
            background, f'{comment}', (300, 700), 35, (0, 0, 205))
    background = background.convert('RGB')
    buffered = io.BytesIO()
    background.save(buffered, format='JPEG', optimize=True)
    result = buffered.getvalue()
    result = base64.b64encode(result).decode('utf-8')
    return result
