import httpx
import numpy as np
from PIL import Image
import io
import base64
import asyncio


async def hidden_pic(out_pic: str, hidden_pic: str, type: int) -> str:
    """制作幻影坦克

    Args:
        out_pic (str): 表图URL
        hidden_pic (str): 里图URL
        type (int): 0为黑白幻影坦克,1为彩色幻影坦克

    Returns:
        str: 幻影坦克图片的Base64编码
    """

    async def get_pic(url: str) -> Image.Image:
        """
        异步下载图片并返回 PIL.Image.Image 对象。
        如果图片不是 JPEG 格式，将其转换为 JPEG 格式。
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url)
                response.raise_for_status()  # 抛出HTTP错误
                image_bytes = response.read()

            # 使用PIL将图片数据转换为Image对象
            image = Image.open(io.BytesIO(image_bytes))

            # 检查图片的格式，如果图片不是JPEG格式，进行转换
            if image.format not in ['JPEG', 'JPG']:
                image = image.convert('RGB')
                output = io.BytesIO()
                image.save(output, format='JPEG', quality=85)
                output.seek(0)
                image = Image.open(output)

            return image
        except Exception as e:
            raise Exception(f"Failed to download or process image from {url}: {e}")
    images = await asyncio.gather(get_pic(out_pic), get_pic(hidden_pic))
    image_f, image_b = images  # 假设urls列表中的顺序对应于image_f和image_b
    if type == 0:  # 黑白图像
        image_f = image_f.convert('L')
        image_b = image_b.convert('L')
        w_min = min(image_f.width, image_b.width)
        h_min = min(image_f.height, image_b.height)
        image_f = image_f.resize((w_min, h_min), Image.Resampling.LANCZOS)
        image_b = image_b.resize((w_min, h_min), Image.Resampling.LANCZOS)
        array_f = np.array(image_f, dtype=np.float64)
        array_b = np.array(image_b, dtype=np.float64)
        # 设置修正参数
        a = 10
        b = 6

        # 计算新的像素值
        mean_f = array_f * a / 10
        mean_b = array_b * b / 10

        A_new = 255 - mean_f + mean_b
        A_new = np.clip(A_new, 0, 255)

        # 避免除以零
        safe_A_new = np.where(A_new == 0, 1e-8, A_new)

        # 计算 mean_new
        mean_new = (255 * mean_b) / safe_A_new
        mean_new = np.clip(mean_new, 0, 255)

        # 转换为 uint8 类型
        A_new = A_new.astype(np.uint8)
        mean_new = mean_new.astype(np.uint8)

        # 创建新的 RGBA 图像
        pixel_new = np.dstack([mean_new, mean_new, mean_new, A_new])

        # 转换为 PIL 图像并保存
        new_image = Image.fromarray(pixel_new, 'RGBA')
    elif type == 1:  # 彩色幻影坦克
        # 调整大小到最小公共尺寸
        w_min = min(image_f.width, image_b.width)
        h_min = min(image_f.height, image_b.height)
        image_f = image_f.resize((w_min, h_min), Image.Resampling.LANCZOS)
        image_b = image_b.resize((w_min, h_min), Image.Resampling.LANCZOS)

        # 转换为NumPy数组
        array_f = np.array(image_f)
        array_b = np.array(image_b)

        # 设置修正参数
        a = 12
        b = 7

        # 对亮度信息进行修正
        array_f = array_f * (a / 10)
        array_b = array_b * (b / 10)

        # 计算delta值
        delta_r = array_b[:, :, 0] - array_f[:, :, 0]
        delta_g = array_b[:, :, 1] - array_f[:, :, 1]
        delta_b = array_b[:, :, 2] - array_f[:, :, 2]

        # 计算A_new
        coe_a = 8 + 255 / 256 + (delta_r - delta_b) / 256
        coe_b = 4 * delta_r + 8 * delta_g + 6 * delta_b + ((delta_r - delta_b) * (
            array_b[:, :, 0] + array_f[:, :, 0])) / 256 + (delta_r**2 - delta_b**2) / 512
        A_new = 255 + coe_b / (2 * coe_a)
        A_new = np.clip(A_new, 0, 255).astype(np.uint8)

        # 防止除以零
        A_new_safe = np.where(A_new == 0, 1e-8, A_new)

        # 处理A_new的特殊情况
        mask = A_new == 0
        R_new = np.where(
            mask, 0, (255 * array_b[:, :, 0] * b / 10) / A_new_safe)
        G_new = np.where(
            mask, 0, (255 * array_b[:, :, 1] * b / 10) / A_new_safe)
        B_new = np.where(
            mask, 0, (255 * array_b[:, :, 2] * b / 10) / A_new_safe)
        R_new = np.clip(R_new, 0, 255).astype(np.uint8)
        G_new = np.clip(G_new, 0, 255).astype(np.uint8)
        B_new = np.clip(B_new, 0, 255).astype(np.uint8)

        # 创建新的RGBA图像
        pixel_new = np.dstack([R_new, G_new, B_new, A_new])

        # 转换为PIL图像
        new_image = Image.fromarray(pixel_new, 'RGBA')

    if new_image:
        # 将图像转换为8位颜色深度
        new_image_8bit = new_image.convert(
            'P', palette=Image.ADAPTIVE, colors=256).convert('RGBA')

        # 将新图像保存为Base64编码的PNG格式
        buffered = io.BytesIO()
        new_image_8bit.save(buffered, format='PNG', optimize=True)
        encoded_image = base64.b64encode(buffered.getvalue()).decode('utf-8')
        return encoded_image
