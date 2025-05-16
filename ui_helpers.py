import os
import glob
import sys
import json
import time
import platform
import subprocess
from pathlib import Path
from typing import List, Dict, Tuple, Optional, Any, Union
from PIL import Image, ImageDraw
from functools import lru_cache
import random

# 常量定义
INPUT_TEXTS_DIR = "input_texts"
INPUT_IMAGES_DIR = "input_images"
OUTPUT_DIR = "output"
FONTS_DIR = "fonts"
TITLE_BG_DIR = f"{INPUT_IMAGES_DIR}/title_backgrounds"
IMAGE_EXTENSIONS = ["png", "jpg", "jpeg", "gif"]

def list_files_with_extension(directory: str, extensions: List[str], 
                              empty_message: str = None) -> List[str]:
    """通用的文件列举函数
    
    Args:
        directory: 要列举文件的目录
        extensions: 文件扩展名列表，不包含点号(.)
        empty_message: 当没有找到文件时返回的消息，None表示返回空列表
        
    Returns:
        List[str]: 文件名列表，如果指定了empty_message且没有找到文件，则返回包含消息的列表
    """
    # 确保目录存在
    os.makedirs(directory, exist_ok=True)
    
    # 收集所有匹配的文件
    files = []
    for ext in extensions:
        files.extend(glob.glob(f"{directory}/*.{ext}"))
    
    # 如果没有找到文件且提供了空消息
    if not files and empty_message:
        return [empty_message]
    
    # 返回文件名（不包含路径）
    return [os.path.basename(f) for f in files]

def list_input_files() -> List[str]:
    """列出input_texts目录下的所有.txt文件
    
    Returns:
        List[str]: 文件名列表或包含提示消息的列表
    """
    return list_files_with_extension(
        INPUT_TEXTS_DIR, 
        ["txt"], 
        "没有找到文本文件。请在input_texts目录添加.txt文件或直接输入文本。"
    )

def list_character_images() -> List[str]:
    """列出input_images目录下的所有图片文件
    
    Returns:
        List[str]: 文件名列表，包含"不使用角色图片"选项
    """
    # 添加一个"不使用角色图片"的选项
    result = ["不使用角色图片"]
    
    # 获取图片文件
    images = list_files_with_extension(INPUT_IMAGES_DIR, IMAGE_EXTENSIONS)
    
    if images:
        result.extend(images)
    else:
        # 如果没有找到图片，添加提示信息
        result.append("没有找到图片文件。请在input_images目录添加图片。")
    
    return result

def list_video_files() -> List[str]:
    """列出output/videos目录下的所有.mp4文件
    
    Returns:
        List[str]: 文件路径列表
    """
    # 确保目录存在
    os.makedirs(f"{OUTPUT_DIR}/videos", exist_ok=True)
    
    # 收集所有匹配的文件（需要完整路径）
    files = glob.glob(f"{OUTPUT_DIR}/videos/*.mp4") + glob.glob(f"{OUTPUT_DIR}/*.mp4")
    
    return files

@lru_cache(maxsize=1)
def get_available_fonts() -> List[str]:
    """获取fonts文件夹中可用的字体列表
    
    Returns:
        List[str]: 可用的字体名称列表，包含"默认"选项
    """
    # 添加默认字体选项
    available_fonts = ["默认"]
    
    # 确保fonts目录存在
    os.makedirs(FONTS_DIR, exist_ok=True)
    
    # 扫描fonts目录中的所有字体文件
    font_files = []
    for ext in ["ttf", "otf", "ttc"]:
        font_files.extend(glob.glob(f"{FONTS_DIR}/*.{ext}"))
    
    if not font_files:
        print("fonts目录中没有找到字体文件，请添加.ttf或.otf格式的字体")
        return available_fonts
    
    try:
        import matplotlib.font_manager as fm
        
        # 添加fonts目录中的所有字体
        custom_fonts = []
        
        # 预加载所有字体文件
        font_objects = []
        for font_path in font_files:
            try:
                font_objects.append((font_path, fm.FontProperties(fname=font_path)))
            except Exception as e:
                print(f"无法加载字体 {font_path}: {e}")
        
        # 从预加载的字体中提取名称
        for font_path, font in font_objects:
            try:
                font_name = font.get_name()
                if font_name and font_name not in custom_fonts:
                    custom_fonts.append(font_name)
                    print(f"添加字体: {font_name} 从 {font_path}")
            except Exception as e:
                print(f"无法获取字体名称 {font_path}: {e}")
        
        # 将自定义字体添加到可用字体列表
        available_fonts.extend(sorted(custom_fonts))
        
        print(f"从fonts目录中找到 {len(custom_fonts)} 个可用字体")
        return available_fonts
    except Exception as e:
        print(f"获取字体列表时出错: {e}")
        return available_fonts

@lru_cache(maxsize=1)
def get_all_system_fonts() -> List[str]:
    """获取fonts目录中所有可用的字体
    
    Returns:
        List[str]: 字体名称列表或包含错误消息的列表
    """
    # 确保fonts目录存在
    os.makedirs(FONTS_DIR, exist_ok=True)
    
    # 扫描fonts目录中的所有字体文件
    font_files = []
    for ext in ["ttf", "otf", "ttc"]:
        font_files.extend(glob.glob(f"{FONTS_DIR}/*.{ext}"))
    
    if not font_files:
        return ["fonts目录中没有找到字体文件，请添加.ttf或.otf格式的字体"]
    
    try:
        import matplotlib.font_manager as fm
        
        # 获取所有字体并排序
        all_fonts = set()  # 使用集合避免重复
        
        # 批量处理字体
        for font_path in font_files:
            try:
                # 尝试加载字体并获取字体名称
                font = fm.FontProperties(fname=font_path)
                font_name = font.get_name()
                if font_name:
                    all_fonts.add(font_name)
            except Exception as e:
                print(f"无法加载字体 {font_path}: {e}")
        
        print(f"fonts目录中共有 {len(all_fonts)} 个字体")
        return sorted(all_fonts)
    except Exception as e:
        print(f"获取字体列表时出错: {e}")
        return ["获取字体失败，请检查matplotlib库是否正确安装"]

def get_available_voices() -> List[str]:
    """获取可用的角色声音列表
    
    Returns:
        List[str]: 可用的语音选项列表
    """
    # 创建不同类别的声音列表
    voice_choices = []
    
    # 获取VoiceVox声音
    try:
        from voice_generator import VoiceVoxGenerator
        voice_generator = VoiceVoxGenerator()
        voicevox_voices = voice_generator.list_speakers()
        # 添加VoiceVox前缀
        voicevox_choices = [f"VoiceVox: ID {id} - {name}" for id, name in voicevox_voices.items()]
        voice_choices.extend(voicevox_choices)
    except Exception as e:
        print(f"获取VoiceVox声音列表失败: {e}")
        voice_choices.append("VoiceVox: 服务不可用")
    
    # 获取OpenAI TTS声音
    try:
        from voice_generator import OpenAITTSGenerator
        openai_generator = OpenAITTSGenerator()
        openai_voices = openai_generator.list_speakers()
        
        # 获取OpenAI预设列表
        voice_presets = {}
        if hasattr(openai_generator, 'VOICE_PRESETS'):
            voice_presets = openai_generator.VOICE_PRESETS
        
        # 添加OpenAI前缀，并包含预设信息
        openai_choices = []
        for id, name in openai_voices.items():
            # 基本声音
            openai_choices.append(f"OpenAI: ID {id} - {name}")
            
            # 对于每种预设添加变体（除了default）
            for preset_name, preset_desc in voice_presets.items():
                if preset_name != "default":
                    # 提取预设的简短描述
                    short_desc = preset_name.capitalize()
                    if preset_name == "storyteller":
                        short_desc = "老人讲故事"
                    elif preset_name == "formal":
                        short_desc = "正式演讲"
                    elif preset_name == "cheerful":
                        short_desc = "欢快活泼"
                    
                    # 添加带预设的选项
                    openai_choices.append(f"OpenAI: ID {id} - {name} ({short_desc})")
        
        voice_choices.extend(openai_choices)
    except Exception as e:
        print(f"获取OpenAI TTS声音列表失败: {e}")
        try:
            # 手动添加OpenAI声音
            openai_voices = {
                1: "alloy",
                2: "echo", 
                3: "fable",
                4: "onyx",
                5: "nova",
                6: "shimmer",
                7: "coral"
            }
            openai_choices = []
            for id, name in openai_voices.items():
                # 基本声音
                openai_choices.append(f"OpenAI: ID {id} - {name}")
                
                # 添加预设变体
                presets = ["老人讲故事", "正式演讲", "欢快活泼"]
                for preset in presets:
                    openai_choices.append(f"OpenAI: ID {id} - {name} ({preset})")
            
            voice_choices.extend(openai_choices)
        except Exception:
            voice_choices.append("OpenAI TTS: 服务不可用")
    
    return voice_choices

def extract_voice_id(voice_selection: str) -> Tuple[str, int, Optional[str]]:
    """从语音选择文本中提取ID和类型
    
    Args:
        voice_selection: 语音选择字符串
        
    Returns:
        Tuple[str, int, Optional[str]]: 服务类型、语音ID和预设名称
    """
    try:
        # 从格式 "服务: ID X - 名称" 或 "服务: ID X - 名称 (预设)" 中提取服务类型和ID部分
        service_type = "voicevox"  # 默认
        voice_preset = None  # 默认无预设
        
        if "VoiceVox:" in voice_selection:
            service_type = "voicevox"
            voice_id = int(voice_selection.split(" - ")[0].replace("VoiceVox: ID ", ""))
        elif "OpenAI:" in voice_selection:
            service_type = "openai_tts"
            
            # 提取ID部分
            id_part = voice_selection.split(" - ")[0]
            voice_id = int(id_part.replace("OpenAI: ID ", ""))
            
            # 检查是否有预设信息
            if "(" in voice_selection and ")" in voice_selection:
                preset_info = voice_selection.split("(")[1].split(")")[0]
                
                # 映射中文描述到预设名称
                preset_mapping = {
                    "老人讲故事": "storyteller",
                    "正式演讲": "formal",
                    "欢快活泼": "cheerful",
                }
                
                voice_preset = preset_mapping.get(preset_info)
                if voice_preset:
                    print(f"检测到语音预设: {voice_preset}")
        else:
            # 默认为VoiceVox
            service_type = "voicevox"
            voice_id = 13
            
        return service_type, voice_id, voice_preset
    except Exception as e:
        print(f"提取声音ID时出错: {e}")
        return "voicevox", 13, None  # 默认返回VoiceVox，ID为13

def list_all_fonts() -> str:
    """列出所有fonts目录中的字体文件
    
    Returns:
        str: 格式化的字体列表字符串
    """
    fonts = get_available_fonts()
    fonts_text = "fonts目录中所有可用字体（可复制字体名称直接使用）:\n\n"
    fonts_text += "\n".join(fonts)
    return fonts_text

def cleanup_output_directories() -> str:
    """清理输出目录，删除之前生成的文件
    
    Returns:
        str: 清理结果消息
    """
    # 清理输出目录
    dirs_to_clean = [
        f"{OUTPUT_DIR}/audio", 
        f"{OUTPUT_DIR}/images", 
        f"{OUTPUT_DIR}/texts", 
        f"{OUTPUT_DIR}/videos"
    ]
    
    for dir_path in dirs_to_clean:
        try:
            if os.path.exists(dir_path):
                for item in os.listdir(dir_path):
                    item_path = os.path.join(dir_path, item)
                    if os.path.isfile(item_path):
                        os.remove(item_path)
                        print(f"已删除文件: {item_path}")
        except Exception as e:
            print(f"清理目录 {dir_path} 时出错: {e}")
    
    # 清理根输出目录中的特殊文件
    root_files_to_clean = [
        f"{OUTPUT_DIR}/key_scenes.json",
        f"{OUTPUT_DIR}/base_video.mp4",
        f"{OUTPUT_DIR}/final_video_moviepy.mp4",
        f"{OUTPUT_DIR}/temp_video_with_character.mp4"
    ]
    
    for file_path in root_files_to_clean:
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                print(f"已删除文件: {file_path}")
        except Exception as e:
            print(f"删除文件 {file_path} 时出错: {e}")
            
    print("已清理输出目录")
    return "已清理所有之前的输出文件" 

def create_sample_title_backgrounds() -> None:
    """创建示例标题背景图片"""
    # 确保目录存在
    os.makedirs(TITLE_BG_DIR, exist_ok=True)
    
    # 检查目录是否已有图片
    existing_files = []
    for ext in IMAGE_EXTENSIONS:
        existing_files.extend(glob.glob(f"{TITLE_BG_DIR}/*.{ext}"))
    
    # 如果目录非空，不创建示例
    if existing_files:
        return
    
    print("创建示例标题背景图片...")
    
    # 创建一些示例背景图片
    backgrounds = [
        {"name": "blue_gradient.png", "color1": (0, 96, 255, 180), "color2": (0, 32, 128, 220)},
        {"name": "red_gradient.png", "color1": (255, 64, 64, 180), "color2": (128, 0, 0, 220)},
        {"name": "green_gradient.png", "color1": (64, 255, 96, 180), "color2": (0, 128, 32, 220)},
        {"name": "purple_gradient.png", "color1": (128, 64, 255, 180), "color2": (64, 0, 128, 220)},
        {"name": "yellow_gradient.png", "color1": (255, 255, 64, 180), "color2": (192, 192, 0, 220)},
    ]
    
    # 创建背景的基本尺寸
    width, height = 800, 200
    
    # 批量处理图片创建
    for bg in backgrounds:
        # 创建渐变背景
        image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        
        # 预计算颜色值以提高性能
        color_steps = []
        for i in range(width):
            # 计算颜色渐变
            r = int(bg["color1"][0] + (bg["color2"][0] - bg["color1"][0]) * i / width)
            g = int(bg["color1"][1] + (bg["color2"][1] - bg["color1"][1]) * i / width)
            b = int(bg["color1"][2] + (bg["color2"][2] - bg["color1"][2]) * i / width)
            a = int(bg["color1"][3] + (bg["color2"][3] - bg["color1"][3]) * i / width)
            color_steps.append((r, g, b, a))
        
        # 绘制垂直线
        for i, color in enumerate(color_steps):
            draw.line([(i, 0), (i, height)], fill=color)
        
        # 保存图片
        image_path = os.path.join(TITLE_BG_DIR, bg["name"])
        image.save(image_path, "PNG")
        print(f"已创建示例背景图片: {bg['name']}")
    
    print(f"已创建 {len(backgrounds)} 个示例标题背景图片")

def list_title_background_images() -> List[str]:
    """列出标题背景图片目录下的所有图片文件
    
    Returns:
        List[str]: 背景图片文件名列表
    """
    # 确保目录存在
    os.makedirs(TITLE_BG_DIR, exist_ok=True)
    
    # 获取图片文件
    image_files = list_files_with_extension(TITLE_BG_DIR, IMAGE_EXTENSIONS)
    
    # 如果没有找到图片，创建示例背景
    if not image_files:
        create_sample_title_backgrounds()
        # 重新获取文件列表
        image_files = list_files_with_extension(TITLE_BG_DIR, IMAGE_EXTENSIONS)
        
    return image_files 

def format_text_for_shorts_gpt(raw_text: str) -> str:
    """
    使用 GPT-4o Mini 将文本格式化为适合短视频的字幕。

    Args:
        raw_text: 原始输入文本。

    Returns:
        格式化后的文本。
    """
    if not raw_text or not raw_text.strip():
        return "" # Return empty if input is empty

    print("开始使用 GPT 格式化文本 (Shorts 格式)...")
    
    # --- 构建 Prompt ---
    # 指示模型进行分行，每行尽量控制在7个字符左右，适应短视频竖屏显示
    # 强调保持自然和易读性，避免生硬截断
    prompt = f"""请将以下日文文本重新分行，以适应短视频（竖屏）的字幕显示。目标是创建易于快速阅读且自然的字幕。

格式要求：
1.  **语义完整性优先**：断句的首要原则是保持语义单元的完整性。**不要将一个完整的日语单词（例如，名词、动词、形容词、副词或固定短语）从中间拆分到两行。**
2.  **自然断点**：请在自然的停顿处（如助词后、逗号后、或语义清晰的短语结束后）进行换行。优先考虑符合日语阅读习惯的断点。
3.  **行长度**：在满足上述语义和自然断点的前提下，每行尽量控制在 **1-8 个字符左右**。
4.  **保持原文**：保持原文的**意思和风格**不变。
5.  **纯文本输出**：最终输出**只需要格式化后的文本**，不要包含任何解释、序号或其他多余内容。

原始文本：
「{raw_text}」

格式化后的文本：
"""

    # --- 调用 OpenAI API (占位符) ---
    formatted_text = ""
    try:
        # 1. 获取 API Key (例如从配置、环境变量等)
        # --- Use placeholder key for now --- 
        api_key = os.getenv("OPENAI_API_KEY") # Read from environment variable
        if not api_key:
            print("错误: OpenAI API Key 未在环境变量中配置!")
            return f"错误: OpenAI API Key 未配置!\n\n{raw_text}" # 返回错误信息和原文

        # 2. 初始化 OpenAI 客户端 (需要 pip install openai)
        # --- Make sure openai library is installed --- 
        from openai import OpenAI
        client = OpenAI(api_key=api_key)

        # 3. 调用 API
        # --- Make the API call --- 
        response = client.chat.completions.create(
            model="gpt-4o-mini", # Use gpt-4o-mini model
            messages=[
                {"role": "system", "content": "你是一个文本格式化助手，专门为短视频优化日语字幕分行，严格遵守用户提供的格式要求，特别是语义完整性和自然断点规则。"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2, # Lower temperature for more deterministic output
            max_tokens=1024 # Adjust max tokens if needed
        )
        
        # 4. 提取结果
        # --- Extract the formatted text --- 
        if response.choices:
            formatted_text = response.choices[0].message.content.strip()
            print("GPT 格式化完成。")
        else:
            print("警告: GPT 未返回有效结果。")
            formatted_text = f"警告: GPT 未返回有效结果。\n\n{raw_text}"

        # ---- 移除临时占位符逻辑 ----
        # print("警告: OpenAI API 调用部分未实现，返回添加了注释的原始文本。")
        # formatted_text = f"--- GPT 格式化 (待实现) ---
# {raw_text}"
        # ---- 结束移除临时占位符 ----
        
    except ImportError:
        print("错误: openai 库未安装。请运行 'pip install openai' 安装。")
        formatted_text = f"错误: openai 库未安装。请运行 'pip install openai' 安装。\n\n{raw_text}"
    except Exception as e:
        print(f"调用 GPT API 时出错: {e}")
        # 返回错误信息和原始文本，以便用户知道发生了什么
        formatted_text = f"错误: 调用 GPT API 时出错: {e}\n\n{raw_text}"

    return formatted_text 