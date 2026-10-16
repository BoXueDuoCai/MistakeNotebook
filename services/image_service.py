# ============================================================
# 图片扫描增强服务 (Pillow 实现)
# ============================================================
# 说明：
#   实现 enhance_image(image_path) 函数
#   模拟"全能扫描王"的黑白扫描件效果：
#     1. 灰度化
#     2. 自适应阈值二值化
#     3. 对比度拉伸
#   支持 high/medium/low 三档质量
# ============================================================

import os
from typing import Optional, Tuple
import uuid

from PIL import Image, ImageOps, ImageFilter

from config import ENHANCED_IMG_DIR, CACHE_DIR


def _to_grayscale(img: Image.Image) -> Image.Image:
    """转灰度图"""
    if img.mode != "L":
        img = img.convert("L")
    return img


def _autocontrast(img: Image.Image, cutoff: float = 2.0) -> Image.Image:
    """
    对比度拉伸 (去除背景阴影)
    cutoff: 两端裁剪的像素百分比
    """
    return ImageOps.autocontrast(img, cutoff=cutoff)


def _remove_shadow(img: Image.Image) -> Image.Image:
    """
    去除背景阴影 (形态学差分)
    原理：
      1. 用极大核做闭运算得到背景参考图 (含阴影，不含文字)
      2. 用原图减去背景，得到只含文字的差分图
      3. 反转差分图 (文字变黑，背景变白)
      4. 自适应对比度拉伸回 0-255
    注：保留原始尺寸，仅在内部缩小加速运算
    """
    from PIL import ImageChops

    orig_w, orig_h = img.size
    # 缩小到合理尺寸加速
    scale = min(1.0, 1500 / max(orig_w, orig_h))
    if scale < 1.0:
        small = img.resize((int(orig_w * scale), int(orig_h * scale)),
                            Image.LANCZOS)
    else:
        small = img

    # 取一个比图像尺寸略大的核 (用于"抹掉"文字得到纯背景)
    # 注：MaxFilter/MinFilter 要求 size 必须为奇数
    sw, sh = small.size
    kernel_size = max(15, min(sw, sh) // 30)
    if kernel_size % 2 == 0:
        kernel_size += 1  # 确保奇数
    # 用最大值滤波得到背景 (近似闭运算的膨胀部分)
    background = small.filter(ImageFilter.MaxFilter(kernel_size))
    # 再用最小值滤波平滑 (近似闭运算的腐蚀部分)
    background = background.filter(ImageFilter.MinFilter(kernel_size))

    # 用 background 减去 small 得到差分 (亮处对应文字位置)
    # subtract 后文字处值更小 (因为原图暗)，背景处接近 0
    diff = ImageChops.subtract(background, small)
    # 反转：文字处变白(255)，背景处变黑(0)
    diff = ImageOps.invert(diff)

    # 对比度归一化到 0-255
    diff = ImageOps.autocontrast(diff, cutoff=0.5)

    # 放大回原尺寸
    if scale < 1.0:
        diff = diff.resize((orig_w, orig_h), Image.LANCZOS)

    return diff


def _adaptive_threshold(img: Image.Image, block_size: int = 25,
                          C: int = 5) -> Image.Image:
    """
    自适应阈值二值化 (使用 OpenCV 风格的算法，纯 PIL 实现)
    block_size: 邻域大小 (奇数)
    C: 从均值中减去的常数

    原理：对每个像素，取其邻域均值作为阈值
    若 像素值 > 邻域均值 - C 则为白，否则为黑
    """
    import numpy as np

    arr = np.array(img)
    # 高斯模糊得到局部均值 (近似自适应阈值)
    blurred = img.filter(ImageFilter.GaussianBlur(radius=block_size // 2))
    blurred_arr = np.array(blurred)

    # 自适应阈值
    binary_arr = np.where(arr > (blurred_arr - C), 255, 0).astype(np.uint8)
    return Image.fromarray(binary_arr, mode="L")


def _global_threshold(img: Image.Image) -> Image.Image:
    """全局 Otsu 风格二值化 (作为快速备选)"""
    # 简单的 Otsu 实现
    import numpy as np
    arr = np.array(img)
    hist, _ = np.histogram(arr, bins=256, range=(0, 256))
    total = arr.size
    sum_total = np.sum(np.arange(256) * hist)
    sum_b = 0
    w_b = 0
    max_var = 0
    threshold = 127

    for t in range(256):
        w_b += hist[t]
        if w_b == 0:
            continue
        w_f = total - w_b
        if w_f == 0:
            break
        sum_b += t * hist[t]
        m_b = sum_b / w_b
        m_f = (sum_total - sum_b) / w_f
        var = w_b * w_f * (m_b - m_f) ** 2
        if var > max_var:
            max_var = var
            threshold = t

    return img.point(lambda p: 255 if p > threshold else 0, mode="1").convert("L")


def _sharpen(img: Image.Image) -> Image.Image:
    """锐化"""
    return img.filter(ImageFilter.UnsharpMask(radius=2, percent=150, threshold=3))


# -------------------- 主接口 --------------------
def enhance_image(image_path: str, quality: str = "high",
                  output_path: Optional[str] = None) -> str:
    """
    一键扫描增强 (Pillow 实现)

    步骤：
        1. 打开并转为灰度图
        2. 去除背景阴影 (形态学差分)
        3. 对比度自动拉伸 (autocontrast)
        4. 自适应阈值二值化 (低质量档使用全局 Otsu)
        5. 锐化文字

    :param image_path: 输入图片路径
    :param quality: high/medium/low
                   - high: 自适应阈值，效果最佳，速度最慢
                   - medium: 全局 Otsu，速度中等
                   - low: 仅做对比度拉伸，速度最快
    :param output_path: 输出路径，若为 None 则自动生成
    :return: 增强后图片路径
    """
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"图片不存在: {image_path}")

    # 1. 打开图片 (用 with 确保关闭)
    with Image.open(image_path) as src_img:
        # 复制出来 (避免 with 关闭后失效)
        img = src_img.copy()

    # 2. 灰度化
    img = _to_grayscale(img)

    # 3. 去阴影 (high 档才做，因为最耗时)
    if quality == "high":
        try:
            img = _remove_shadow(img)
        except Exception as e:
            print(f"[enhance_image] 去阴影失败: {e}")

    # 4. 对比度拉伸
    img = _autocontrast(img, cutoff=1.0)

    # 5. 二值化
    if quality == "high":
        try:
            img = _adaptive_threshold(img, block_size=31, C=5)
        except Exception as e:
            print(f"[enhance_image] 自适应阈值失败，回退到全局: {e}")
            img = _global_threshold(img)
    elif quality == "medium":
        img = _global_threshold(img)
    # low 档不做二值化

    # 6. 锐化
    if quality in ("high", "medium"):
        img = _sharpen(img)

    # 7. 保存
    if output_path is None:
        ext = ".png"
        out_name = f"enhanced_{uuid.uuid4().hex[:8]}{ext}"
        output_path = str(ENHANCED_IMG_DIR / out_name)

    # 确保是 RGB 或 L 模式保存
    if img.mode == "1":
        img = img.convert("L")

    img.save(output_path, "PNG", optimize=True)
    return output_path


def create_thumbnail(image_path: str, max_size: Tuple[int, int] = (200, 200),
                     output_path: Optional[str] = None) -> str:
    """生成缩略图"""
    with Image.open(image_path) as img:
        img.thumbnail(max_size, Image.LANCZOS)
        if output_path is None:
            out_name = f"thumb_{uuid.uuid4().hex[:8]}.png"
            output_path = str(CACHE_DIR / out_name)
        img.save(output_path, "PNG")
    return output_path


def crop_image_region(image_path: str, x: int, y: int, width: int, height: int,
                      output_path: Optional[str] = None) -> str:
    """
    裁剪图片指定区域 (用于错题图片裁剪出某一道题)
    :param x, y: 裁剪区域左上角坐标 (像素)
    :param width, height: 裁剪区域宽高 (像素)
    :return: 裁剪后图片路径
    """
    from config import CROPPED_IMG_DIR
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"图片不存在: {image_path}")

    with Image.open(image_path) as src:
        img = src.copy()

    orig_w, orig_h = img.size
    # 钳制到合法范围
    x = max(0, min(x, orig_w - 1))
    y = max(0, min(y, orig_h - 1))
    width = max(1, min(width, orig_w - x))
    height = max(1, min(height, orig_h - y))

    cropped = img.crop((x, y, x + width, y + height))

    if output_path is None:
        out_name = f"cropped_{uuid.uuid4().hex[:8]}.png"
        output_path = str(CROPPED_IMG_DIR / out_name)

    if cropped.mode == "1":
        cropped = cropped.convert("L")
    cropped.save(output_path, "PNG", optimize=True)
    return output_path


def get_image_info(image_path: str) -> dict:
    """获取图片基本信息"""
    with Image.open(image_path) as img:
        return {
            "size": img.size,
            "mode": img.mode,
            "format": img.format,
            "path": image_path,
        }
