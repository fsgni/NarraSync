import os
import sys
import subprocess
import tempfile
import cv2  # 如果 add_titles_to_video 使用 cv2
import numpy as np # 如果 add_titles_to_video 使用 numpy
from PIL import Image, ImageDraw, ImageFont
import json
import traceback
import shutil # 需要用到

def create_title_image(text, font_size, color, width, height, position_x, position_y, background_image=None, font_name="默认"):
    """创建带有标题文本的图片，可选择添加背景图片
    
    Args:
        text: 标题文本
        font_size: 字体大小
        color: 字体颜色
        width, height: 视频尺寸
        position_x, position_y: 文本位置
        background_image: 可选的背景图片路径
        font_name: 字体名称
    
    Returns:
        PIL.Image: 生成的图片
    """
    # 创建透明图片 (整个视频尺寸)
    img = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # 使用用户设置的字体大小，确保它不小于18
    user_font_size = max(int(font_size), 18)
    
    # 定义描边粗细 (字体大小的0.1倍，最小为2像素)
    stroke_width = max(int(user_font_size * 0.1), 2)
    
    # 加载背景图片（如果有）
    if background_image and os.path.exists(background_image):
        try:
            # 加载背景图片
            bg = Image.open(background_image)
            
            # 转换为RGBA模式
            if bg.mode != 'RGBA':
                bg = bg.convert('RGBA')
            
            # 设置背景图片的大小 - 使用更大的比例
            # 背景图默认大小为视频宽度的1/3，高度等比例缩放
            # 但高度限制为视频高度的1/5，避免太大
            bg_width = width // 3
            bg_height = min(int(bg.height * (bg_width / bg.width)), height // 5)
            
            # 缩放背景图片
            bg = bg.resize((bg_width, bg_height), Image.LANCZOS)
            
            # 确保背景图不会超出视频边界
            if position_x + bg_width > width:
                position_x = width - bg_width
            if position_y + bg_height > height:
                position_y = height - bg_height
            
            # 将背景图粘贴到视频上
            img.paste(bg, (position_x, position_y), bg)
            
            # 尝试使用指定的字体或系统字体
            try:
                # 如果指定了字体且不是默认值
                if font_name and font_name != "默认":
                    # 首先尝试从fonts目录加载
                    font_paths = [
                        os.path.join("fonts", f"{font_name}.ttf"),
                        os.path.join("fonts", f"{font_name}.otf"),
                        os.path.join("fonts", f"{font_name}.ttc"),
                        # 尝试完整路径
                        font_name
                    ]
                    
                    font = None
                    for path in font_paths:
                        if os.path.exists(path):
                            try:
                                font = ImageFont.truetype(path, user_font_size)
                                print(f"使用指定字体: {path}")
                                break
                            except Exception as e:
                                print(f"无法加载字体 {path}: {e}")
                                continue
                    
                    # 如果找不到指定字体，回退到默认字体搜索
                    if font is None:
                        print(f"找不到指定字体: {font_name}，尝试系统字体")
                        raise Exception("找不到指定字体")
                else:
                    # 尝试常见的字体路径
                    font_paths = [
                        # Windows字体
                        "C:/Windows/Fonts/SimHei.ttf",    # 黑体
                        "C:/Windows/Fonts/msyh.ttc",      # 微软雅黑
                        "C:/Windows/Fonts/simsun.ttc",    # 宋体
                        "C:/Windows/Fonts/Arial.ttf",     # Arial
                        # 自定义字体目录
                        "fonts/SimHei.ttf",
                        "fonts/msyh.ttc",
                        "fonts/KEIFONT.TTF"  # 添加fonts目录中的字体
                    ]
                    
                    font = None
                    for path in font_paths:
                        if os.path.exists(path):
                            try:
                                font = ImageFont.truetype(path, user_font_size)
                                print(f"使用系统字体: {path}")
                                break
                            except Exception as e:
                                print(f"无法加载字体 {path}: {e}")
                                continue
                
                if font is None:
                    # 如果找不到任何字体，使用默认字体
                    font = ImageFont.load_default()
                    print("使用默认字体")
            except Exception as e:
                # 出错时使用默认字体
                print(f"加载字体时出错: {e}")
                font = ImageFont.load_default()
                print("使用默认字体")
            
            # 将颜色代码转换为RGB
            if color.startswith('#'):
                color = color[1:]
            r, g, b = int(color[0:2], 16), int(color[2:4], 16), int(color[4:6], 16)
            
            # 测量文本尺寸
            if hasattr(font, 'getbbox'):  # Pillow 8.0.0+
                text_bbox = font.getbbox(text)
                text_width = text_bbox[2] - text_bbox[0]
                text_height = text_bbox[3] - text_bbox[1]
            else:  # 兼容旧版本
                text_width, text_height = font.getsize(text)
            
            # 如果文本太大，超出背景图片宽度，调整字体大小
            if text_width > bg_width * 0.9:
                # 计算需要的缩放因子
                scale_factor = (bg_width * 0.9) / text_width
                # 重新计算字体大小
                adjusted_font_size = max(int(user_font_size * scale_factor), 18)
                print(f"文本太宽，调整字体大小从 {user_font_size} 到 {adjusted_font_size}")
                
                # 调整描边宽度
                stroke_width = max(int(adjusted_font_size * 0.1), 2)
                
                # 重新创建字体
                if font_name and font_name != "默认":
                    # 尝试指定字体
                    for path in font_paths:
                        if os.path.exists(path):
                            try:
                                font = ImageFont.truetype(path, adjusted_font_size)
                                break
                            except:
                                continue
                else:
                    # 尝试常见字体
                    for path in [
                        "C:/Windows/Fonts/SimHei.ttf",
                        "C:/Windows/Fonts/msyh.ttc",
                        "fonts/SimHei.ttf",
                        "fonts/KEIFONT.TTF"
                    ]:
                        if os.path.exists(path):
                            try:
                                font = ImageFont.truetype(path, adjusted_font_size)
                                break
                            except:
                                continue
                
                # 重新测量文本
                if hasattr(font, 'getbbox'):
                    text_bbox = font.getbbox(text)
                    text_width = text_bbox[2] - text_bbox[0]
                    text_height = text_bbox[3] - text_bbox[1]
                else:
                    text_width, text_height = font.getsize(text)
            
            # 计算文本位置 - 完全居中于背景图片
            text_x = position_x + (bg_width - text_width) // 2
            text_y = position_y + (bg_height - text_height) // 2
            
            # 先绘制黑色边框 (通过在文本周围多次绘制黑色文本来实现描边效果)
            offsets = []
            for x_offset in range(-stroke_width, stroke_width + 1):
                for y_offset in range(-stroke_width, stroke_width + 1):
                    # 跳过中心位置，因为那是原始文本的位置
                    if x_offset == 0 and y_offset == 0:
                        continue
                    # 计算边框位置
                    offsets.append((text_x + x_offset, text_y + y_offset))
            
            # 绘制所有黑色边框
            for offset_x, offset_y in offsets:
                draw.text((offset_x, offset_y), text, font=font, fill=(0, 0, 0, 255))
            
            # 最后绘制原始颜色的文本
            draw.text((text_x, text_y), text, font=font, fill=(r, g, b, 255))
            
            return img
        except Exception as e:
            print(f"处理背景图片时出错: {e}")
            # 继续使用常规方法
            pass
    
    # 如果没有背景图片或处理出错，使用常规方法
    # 尝试使用指定字体或系统字体
    try:
        # 如果指定了字体且不是默认值
        if font_name and font_name != "默认":
            # 首先尝试从fonts目录加载
            font_paths = [
                os.path.join("fonts", f"{font_name}.ttf"),
                os.path.join("fonts", f"{font_name}.otf"),
                os.path.join("fonts", f"{font_name}.ttc"),
                # 尝试完整路径
                font_name
            ]
            
            font = None
            for path in font_paths:
                if os.path.exists(path):
                    try:
                        font = ImageFont.truetype(path, user_font_size)
                        print(f"使用指定字体: {path}")
                        break
                    except Exception as e:
                        print(f"无法加载字体 {path}: {e}")
                        continue
            
            # 如果找不到指定字体，回退到默认字体搜索
            if font is None:
                print(f"找不到指定字体: {font_name}，尝试系统字体")
                raise Exception("找不到指定字体")
        else:
            # 尝试常见的字体路径
            font_paths = [
                # Windows字体
                "C:/Windows/Fonts/SimHei.ttf",    # 黑体
                "C:/Windows/Fonts/msyh.ttc",      # 微软雅黑
                "C:/Windows/Fonts/simsun.ttc",    # 宋体
                "C:/Windows/Fonts/Arial.ttf",     # Arial
                # 自定义字体目录
                "fonts/SimHei.ttf",
                "fonts/msyh.ttc",
                "fonts/KEIFONT.TTF"  # 添加fonts目录中的字体
            ]
            
            font = None
            for path in font_paths:
                if os.path.exists(path):
                    try:
                        font = ImageFont.truetype(path, user_font_size)
                        print(f"使用系统字体: {path}")
                        break
                    except Exception as e:
                        print(f"无法加载字体 {path}: {e}")
                        continue
        
        if font is None:
            # 如果找不到任何字体，使用默认字体
            font = ImageFont.load_default()
            print("使用默认字体")
    except Exception as e:
        # 出错时使用默认字体
        print(f"加载字体时出错: {e}")
        font = ImageFont.load_default()
        print("使用默认字体")
    
    # 将颜色代码转换为RGB
    if color.startswith('#'):
        color = color[1:]
    r, g, b = int(color[0:2], 16), int(color[2:4], 16), int(color[4:6], 16)
    
    # 测量文本尺寸
    if hasattr(font, 'getbbox'):  # Pillow 8.0.0+
        text_bbox = font.getbbox(text)
        text_width = text_bbox[2] - text_bbox[0]
        text_height = text_bbox[3] - text_bbox[1]
    else:  # 兼容旧版本
        text_width, text_height = font.getsize(text)
    
    # 先绘制黑色边框
    offsets = []
    for x_offset in range(-stroke_width, stroke_width + 1):
        for y_offset in range(-stroke_width, stroke_width + 1):
            # 跳过中心位置，因为那是原始文本的位置
            if x_offset == 0 and y_offset == 0:
                continue
            # 计算边框位置
            offsets.append((position_x + x_offset, position_y + y_offset))
    
    # 绘制所有黑色边框
    for offset_x, offset_y in offsets:
        draw.text((offset_x, offset_y), text, font=font, fill=(0, 0, 0, 255))
    
    # 最后绘制原始颜色的文本
    draw.text((position_x, position_y), text, font=font, fill=(r, g, b, 255))
    
    return img

def apply_scene_titles_to_video(all_titles, input_video=None, output_video=None):
    """将所有场景标题应用到视频
    
    Args:
        all_titles: 所有标题数据
        input_video: 输入视频路径，默认为output/webui_input_final.mp4
        output_video: 输出视频路径，默认为在输入文件名后添加_with_titles
        
    Returns:
        str: 处理结果信息
    """
    if not all_titles:
        return "没有标题需要添加"
    
    # 设置默认输入/输出视频路径
    if input_video is None:
        input_video = "output/webui_input_final.mp4"
    
    if output_video is None:
        input_name = os.path.splitext(input_video)[0]
        output_video = f"{input_name}_with_titles.mp4"
    
    if not os.path.exists(input_video):
        return f"错误：输入视频不存在 {input_video}"
    
    try:
        # 从key_scenes.json直接读取场景时间信息
        key_scenes_file = "output/key_scenes.json"
        if not os.path.exists(key_scenes_file):
            return "错误：找不到场景信息文件 output/key_scenes.json"
        
        with open(key_scenes_file, "r", encoding="utf-8") as f:
            scenes = json.load(f)
        
        print(f"从key_scenes.json成功读取到{len(scenes)}个场景信息")
        
        # 准备临时工作目录
        temp_dir = os.path.join("output", "temp_titles")
        os.makedirs(temp_dir, exist_ok=True)
        print(f"创建临时目录: {temp_dir}")
        
        # 准备视频文件
        temp_video = os.path.join(temp_dir, "temp_video.mp4")
        if os.path.exists(temp_video):
            os.remove(temp_video)
        shutil.copy2(input_video, temp_video)
        
        # 创建一个文本文件表示需要的场景
        scenes_file = os.path.join(temp_dir, "scenes.txt")
        with open(scenes_file, "w", encoding="utf-8") as f:
            f.write("# 场景ID,开始时间,结束时间,标题文本,颜色,字体大小,X位置,Y位置,背景图片,字体\n")
            for title in all_titles:
                # 检查是否使用精确时间
                if "exact_start_time" in title and "exact_end_time" in title:
                    # 直接使用精确时间
                    start_time = title["exact_start_time"]
                    end_time = title["exact_end_time"]
                    print(f"标题 '{title['text']}' 使用精确时间: {start_time:.2f}s - {end_time:.2f}s")
                else:
                    # 使用场景ID查找时间
                    # 获取场景时间范围
                    start_scene_idx = title["start_scene"] - 1
                    end_scene_idx = title["end_scene"] - 1
                    
                    # 确保索引范围有效
                    if start_scene_idx < 0 or start_scene_idx >= len(scenes):
                        print(f"警告：场景ID {title['start_scene']} 超出范围，已调整")
                        start_scene_idx = max(0, min(start_scene_idx, len(scenes) - 1))
                    
                    if end_scene_idx < 0 or end_scene_idx >= len(scenes):
                        print(f"警告：场景ID {title['end_scene']} 超出范围，已调整")
                        end_scene_idx = max(0, min(end_scene_idx, len(scenes) - 1))
                    
                    # 从场景中获取具体时间（单位：秒）
                    start_time = scenes[start_scene_idx]["start_time"]
                    
                    # 计算结束时间，处理可能没有end_time的情况
                    if "end_time" in scenes[end_scene_idx]:
                        end_time = scenes[end_scene_idx]["end_time"]
                    else:
                        # 如果没有end_time字段，使用start_time + duration
                        end_time = scenes[end_scene_idx]["start_time"] + scenes[end_scene_idx].get("duration", 5)
                
                # 获取背景图片路径和字体
                bg_image = title.get("background_image", "")
                font = title.get("font", "默认")
                
                print(f"标题 '{title['text']}' 将显示在时间段: {start_time:.2f}s - {end_time:.2f}s")
                
                # 写入场景信息，包括背景图片和字体
                f.write(f"{title.get('start_scene', 1)}-{title.get('end_scene', 1)},{start_time},{end_time},{title['text']},{title['color']},{title['size']},{title['position_x']},{title['position_y']},{bg_image},{font}\n")
        
        # 创建一个Python脚本来处理标题添加
        script_file = os.path.join(temp_dir, "add_titles.py")
        with open(script_file, "w", encoding="utf-8") as f:
            f.write('''
import os
import sys
import subprocess
from PIL import Image, ImageDraw, ImageFont

def create_title_image(text, font_size, color, width, height, position_x, position_y, background_image=None, font_name="默认"):
    """创建带有标题文本的图片，可选择添加背景图片
    
    Args:
        text: 标题文本
        font_size: 字体大小
        color: 字体颜色
        width, height: 视频尺寸
        position_x, position_y: 文本位置
        background_image: 可选的背景图片路径
        font_name: 字体名称
    
    Returns:
        PIL.Image: 生成的图片
    """
    # 创建透明图片 (整个视频尺寸)
    img = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # 使用用户设置的字体大小，确保它不小于18
    user_font_size = max(int(font_size), 18)
    
    # 定义描边粗细 (字体大小的0.1倍，最小为2像素)
    stroke_width = max(int(user_font_size * 0.1), 2)
    
    # 加载背景图片（如果有）
    if background_image and os.path.exists(background_image):
        try:
            # 加载背景图片
            bg = Image.open(background_image)
            
            # 转换为RGBA模式
            if bg.mode != 'RGBA':
                bg = bg.convert('RGBA')
            
            # 设置背景图片的大小 - 使用更大的比例
            # 背景图默认大小为视频宽度的1/3，高度等比例缩放
            # 但高度限制为视频高度的1/5，避免太大
            bg_width = width // 3
            bg_height = min(int(bg.height * (bg_width / bg.width)), height // 5)
            
            # 缩放背景图片
            bg = bg.resize((bg_width, bg_height), Image.LANCZOS)
            
            # 确保背景图不会超出视频边界
            if position_x + bg_width > width:
                position_x = width - bg_width
            if position_y + bg_height > height:
                position_y = height - bg_height
            
            # 将背景图粘贴到视频上
            img.paste(bg, (position_x, position_y), bg)
            
            # 尝试使用指定的字体或系统字体
            try:
                # 如果指定了字体且不是默认值
                if font_name and font_name != "默认":
                    # 首先尝试从fonts目录加载
                    font_paths = [
                        os.path.join("fonts", f"{font_name}.ttf"),
                        os.path.join("fonts", f"{font_name}.otf"),
                        os.path.join("fonts", f"{font_name}.ttc"),
                        # 尝试完整路径
                        font_name
                    ]
                    
                    font = None
                    for path in font_paths:
                        if os.path.exists(path):
                            try:
                                font = ImageFont.truetype(path, user_font_size)
                                print(f"使用指定字体: {path}")
                                break
                            except Exception as e:
                                print(f"无法加载字体 {path}: {e}")
                                continue
                    
                    # 如果找不到指定字体，回退到默认字体搜索
                    if font is None:
                        print(f"找不到指定字体: {font_name}，尝试系统字体")
                        raise Exception("找不到指定字体")
                else:
                    # 尝试常见的字体路径
                    font_paths = [
                        # Windows字体
                        "C:/Windows/Fonts/SimHei.ttf",    # 黑体
                        "C:/Windows/Fonts/msyh.ttc",      # 微软雅黑
                        "C:/Windows/Fonts/simsun.ttc",    # 宋体
                        "C:/Windows/Fonts/Arial.ttf",     # Arial
                        # 自定义字体目录
                        "fonts/SimHei.ttf",
                        "fonts/msyh.ttc",
                        "fonts/KEIFONT.TTF"  # 添加fonts目录中的字体
                    ]
                    
                    font = None
                    for path in font_paths:
                        if os.path.exists(path):
                            try:
                                font = ImageFont.truetype(path, user_font_size)
                                print(f"使用系统字体: {path}")
                                break
                            except Exception as e:
                                print(f"无法加载字体 {path}: {e}")
                                continue
                
                if font is None:
                    # 如果找不到任何字体，使用默认字体
                    font = ImageFont.load_default()
                    print("使用默认字体")
            except Exception as e:
                # 出错时使用默认字体
                print(f"加载字体时出错: {e}")
                font = ImageFont.load_default()
                print("使用默认字体")
            
            # 将颜色代码转换为RGB
            if color.startswith('#'):
                color = color[1:]
            r, g, b = int(color[0:2], 16), int(color[2:4], 16), int(color[4:6], 16)
            
            # 测量文本尺寸
            if hasattr(font, 'getbbox'):  # Pillow 8.0.0+
                text_bbox = font.getbbox(text)
                text_width = text_bbox[2] - text_bbox[0]
                text_height = text_bbox[3] - text_bbox[1]
            else:  # 兼容旧版本
                text_width, text_height = font.getsize(text)
            
            # 如果文本太大，超出背景图片宽度，调整字体大小
            if text_width > bg_width * 0.9:
                # 计算需要的缩放因子
                scale_factor = (bg_width * 0.9) / text_width
                # 重新计算字体大小
                adjusted_font_size = max(int(user_font_size * scale_factor), 18)
                print(f"文本太宽，调整字体大小从 {user_font_size} 到 {adjusted_font_size}")
                
                # 调整描边宽度
                stroke_width = max(int(adjusted_font_size * 0.1), 2)
                
                # 重新创建字体
                if font_name and font_name != "默认":
                    # 尝试指定字体
                    for path in font_paths:
                        if os.path.exists(path):
                            try:
                                font = ImageFont.truetype(path, adjusted_font_size)
                                break
                            except:
                                continue
                else:
                    # 尝试常见字体
                    for path in [
                        "C:/Windows/Fonts/SimHei.ttf",
                        "C:/Windows/Fonts/msyh.ttc",
                        "fonts/SimHei.ttf",
                        "fonts/KEIFONT.TTF"
                    ]:
                        if os.path.exists(path):
                            try:
                                font = ImageFont.truetype(path, adjusted_font_size)
                                break
                            except:
                                continue
                
                # 重新测量文本
                if hasattr(font, 'getbbox'):
                    text_bbox = font.getbbox(text)
                    text_width = text_bbox[2] - text_bbox[0]
                    text_height = text_bbox[3] - text_bbox[1]
                else:
                    text_width, text_height = font.getsize(text)
            
            # 计算文本位置 - 完全居中于背景图片
            text_x = position_x + (bg_width - text_width) // 2
            text_y = position_y + (bg_height - text_height) // 2
            
            # 先绘制黑色边框 (通过在文本周围多次绘制黑色文本来实现描边效果)
            offsets = []
            for x_offset in range(-stroke_width, stroke_width + 1):
                for y_offset in range(-stroke_width, stroke_width + 1):
                    # 跳过中心位置，因为那是原始文本的位置
                    if x_offset == 0 and y_offset == 0:
                        continue
                    # 计算边框位置
                    offsets.append((text_x + x_offset, text_y + y_offset))
            
            # 绘制所有黑色边框
            for offset_x, offset_y in offsets:
                draw.text((offset_x, offset_y), text, font=font, fill=(0, 0, 0, 255))
            
            # 最后绘制原始颜色的文本
            draw.text((text_x, text_y), text, font=font, fill=(r, g, b, 255))
            
            return img
        except Exception as e:
            print(f"处理背景图片时出错: {e}")
            # 继续使用常规方法
            pass
    
    # 如果没有背景图片或处理出错，使用常规方法
    # 尝试使用指定字体或系统字体
    try:
        # 如果指定了字体且不是默认值
        if font_name and font_name != "默认":
            # 首先尝试从fonts目录加载
            font_paths = [
                os.path.join("fonts", f"{font_name}.ttf"),
                os.path.join("fonts", f"{font_name}.otf"),
                os.path.join("fonts", f"{font_name}.ttc"),
                # 尝试完整路径
                font_name
            ]
            
            font = None
            for path in font_paths:
                if os.path.exists(path):
                    try:
                        font = ImageFont.truetype(path, user_font_size)
                        print(f"使用指定字体: {path}")
                        break
                    except Exception as e:
                        print(f"无法加载字体 {path}: {e}")
                        continue
            
            # 如果找不到指定字体，回退到默认字体搜索
            if font is None:
                print(f"找不到指定字体: {font_name}，尝试系统字体")
                raise Exception("找不到指定字体")
        else:
            # 尝试常见的字体路径
            font_paths = [
                # Windows字体
                "C:/Windows/Fonts/SimHei.ttf",    # 黑体
                "C:/Windows/Fonts/msyh.ttc",      # 微软雅黑
                "C:/Windows/Fonts/simsun.ttc",    # 宋体
                "C:/Windows/Fonts/Arial.ttf",     # Arial
                # 自定义字体目录
                "fonts/SimHei.ttf",
                "fonts/msyh.ttc",
                "fonts/KEIFONT.TTF"  # 添加fonts目录中的字体
            ]
            
            font = None
            for path in font_paths:
                if os.path.exists(path):
                    try:
                        font = ImageFont.truetype(path, user_font_size)
                        print(f"使用系统字体: {path}")
                        break
                    except Exception as e:
                        print(f"无法加载字体 {path}: {e}")
                        continue
        
        if font is None:
            # 如果找不到任何字体，使用默认字体
            font = ImageFont.load_default()
            print("使用默认字体")
    except Exception as e:
        # 出错时使用默认字体
        print(f"加载字体时出错: {e}")
        font = ImageFont.load_default()
        print("使用默认字体")
    
    # 将颜色代码转换为RGB
    if color.startswith('#'):
        color = color[1:]
    r, g, b = int(color[0:2], 16), int(color[2:4], 16), int(color[4:6], 16)
    
    # 测量文本尺寸
    if hasattr(font, 'getbbox'):  # Pillow 8.0.0+
        text_bbox = font.getbbox(text)
        text_width = text_bbox[2] - text_bbox[0]
        text_height = text_bbox[3] - text_bbox[1]
    else:  # 兼容旧版本
        text_width, text_height = font.getsize(text)
    
    # 先绘制黑色边框
    offsets = []
    for x_offset in range(-stroke_width, stroke_width + 1):
        for y_offset in range(-stroke_width, stroke_width + 1):
            # 跳过中心位置，因为那是原始文本的位置
            if x_offset == 0 and y_offset == 0:
                continue
            # 计算边框位置
            offsets.append((position_x + x_offset, position_y + y_offset))
    
    # 绘制所有黑色边框
    for offset_x, offset_y in offsets:
        draw.text((offset_x, offset_y), text, font=font, fill=(0, 0, 0, 255))
    
    # 最后绘制原始颜色的文本
    draw.text((position_x, position_y), text, font=font, fill=(r, g, b, 255))
    
    return img

def add_title_to_video(input_video, output_video, title_info):
    """将标题添加到视频中
    
    Args:
        input_video: 输入视频路径
        output_video: 输出视频路径
        title_info: 标题信息列表，每个元素为(开始时间,结束时间,标题文本,颜色,字体大小,X位置,Y位置,背景图片,字体名称)
    """
    # 获取视频分辨率
    cmd = ["ffprobe", "-v", "error", "-select_streams", "v:0", 
           "-show_entries", "stream=width,height", "-of", "csv=s=x:p=0", input_video]
    result = subprocess.run(cmd, capture_output=True, text=True)
    width, height = map(int, result.stdout.strip().split('x'))
    print(f"视频分辨率: {width}x{height}")
    
    # 为每个标题创建覆盖图片
    overlay_files = []
    filter_complex = []
    
    # 初始化输入流索引
    input_index = 0
    
    # 添加主视频输入
    inputs = ["-i", input_video]
    
    for i, (start_time, end_time, text, color, font_size, pos_x, pos_y, bg_image, font_name) in enumerate(title_info):
        # 处理背景图片路径
        bg_image_path = None
        if bg_image and bg_image.strip():
            possible_path = os.path.join("input_images/title_backgrounds", bg_image)
            if os.path.exists(possible_path):
                bg_image_path = possible_path
                print(f"使用标题背景图片: {bg_image_path}")
        
        # 创建标题图片
        img = create_title_image(
            text, int(font_size), color, width, height, 
            int(pos_x), int(pos_y), bg_image_path, font_name
        )
        
        # 保存为PNG文件
        overlay_file = f"title_{i}.png"
        overlay_path = os.path.join(os.path.dirname(output_video), overlay_file)
        img.save(overlay_path, "PNG")
        overlay_files.append(overlay_path)
        
        # 添加输入文件
        inputs.extend(["-i", overlay_path])
        input_index += 1
        
        # 添加叠加过滤器
        if i == 0:
            filter_complex.append(f"[0:v][{input_index}:v]overlay=0:0:enable='between(t,{start_time},{end_time})'[v{i}]")
        else:
            filter_complex.append(f"[v{i-1}][{input_index}:v]overlay=0:0:enable='between(t,{start_time},{end_time})'[v{i}]")
    
    # 构建完整命令
    filter_str = ";".join(filter_complex)
    map_option = f"[v{len(title_info)-1}]"
    
    cmd = ["ffmpeg", "-y"]
    cmd.extend(inputs)
    cmd.extend(["-filter_complex", filter_str])
    cmd.extend(["-map", map_option])
    cmd.extend(["-map", "0:a?"])
    cmd.extend(["-c:v", "libx264", "-c:a", "copy", output_video])
    
    print("执行命令:", " ".join(cmd))
    subprocess.run(cmd, check=True)
    
    # 清理临时文件
    for file in overlay_files:
        try:
            os.remove(file)
            print(f"已删除临时文件: {file}")
        except:
            print(f"无法删除临时文件: {file}")
    
    print(f"标题已成功添加到视频: {output_video}")

if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("用法: python add_titles.py <输入视频> <输出视频> <场景文件>")
        sys.exit(1)
    
    input_video = sys.argv[1]
    output_video = sys.argv[2]
    scenes_file = sys.argv[3]
    
    # 读取场景信息
    title_info = []
    with open(scenes_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                parts = line.split(",")
                if len(parts) >= 10:  # 注意这里改成10个参数，包括背景图片和字体
                    # 获取开始时间、结束时间、文本、颜色、字体大小、位置、背景图片和字体
                    start_time = float(parts[1])
                    end_time = float(parts[2])
                    text = parts[3]
                    color = parts[4]
                    font_size = int(parts[5])
                    pos_x = int(parts[6])
                    pos_y = int(parts[7])
                    bg_image = parts[8] if len(parts) > 8 else ""
                    font_name = parts[9] if len(parts) > 9 else "默认"
                    
                    title_info.append((start_time, end_time, text, color, font_size, pos_x, pos_y, bg_image, font_name))
    
    if not title_info:
        print("没有找到有效的标题信息")
        sys.exit(1)
    
    # 添加标题到视频
    add_title_to_video(input_video, output_video, title_info)
''')
        
        # 执行Python脚本来添加标题
        cmd = [sys.executable, script_file, temp_video, output_video, scenes_file]
        print(f"执行命令: {' '.join(cmd)}")
        
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        
        # 清理临时文件
        try:
            if os.path.exists(temp_video):
                os.remove(temp_video)
            if os.path.exists(scenes_file):
                os.remove(scenes_file)
            if os.path.exists(script_file):
                os.remove(script_file)
            # 保留临时目录，但可以考虑在将来完全删除
        except Exception as e:
            print(f"清理临时文件时出错: {e}")
        
        if result.returncode != 0:
            print(f"添加标题失败: {result.stderr}")
            return f"添加标题失败，详细错误信息已记录到控制台"
        
        if os.path.exists(output_video) and os.path.getsize(output_video) > 0:
            print(f"标题添加成功，输出文件: {output_video}")
            return f"标题添加成功！<br>输出文件: {output_video}"
        else:
            return "添加标题失败，输出文件不存在或为空"
    
    except Exception as e:
        import traceback
        print(f"应用场景标题时出错: {e}")
        print(traceback.format_exc())
        return f"错误：{str(e)}"