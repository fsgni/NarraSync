import os
import sys
import json
import time
import subprocess
import glob
import random
import math
import numpy as np
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Generator, Any, Union
from dataclasses import dataclass
from ui_helpers import extract_voice_id, cleanup_output_directories
from config import config

# 常量定义
INPUT_TEXTS_DIR = "input_texts"
OUTPUT_DIR = "output"
INPUT_IMAGES_DIR = "input_images"
DEFAULT_VOICE = "ID: 13 - 青山龍星"
DEFAULT_AUDIO_SENSITIVITY = 0.2

# 风格预设
STYLE_PRESETS = {
    "电影级品质": "cinematic lighting, movie quality, professional photography, 8k ultra HD",
    "水墨画风格": "traditional Chinese ink painting style, elegant, flowing ink, minimalist",
    "油画风格": "oil painting style, detailed brushwork, rich colors, artistic",
    "动漫风格": "anime style, vibrant colors, clean lines, expressive",
    "写实风格": "photorealistic, highly detailed, sharp focus, natural lighting",
    "梦幻风格": "dreamy atmosphere, soft lighting, ethereal colors, mystical"
}

@dataclass
class VideoProcessingConfig:
    """视频处理配置数据类"""
    # 输入设置
    text_input: str = ""
    selected_file: str = ""
    
    # 图像生成设置
    image_generator_type: str = "comfyui"
    aspect_ratio: str = "默认方形"
    image_style_type: str = "无风格"
    custom_style: Optional[str] = None
    comfyui_style: Optional[str] = None
    
    # 字幕设置
    font_name: Optional[str] = None
    font_size: Optional[int] = None
    font_color: Optional[str] = None
    bg_opacity: Optional[float] = None
    
    # 角色设置
    character_image: Optional[str] = None
    preserve_line_breaks: bool = False
    talking_character: bool = False
    closed_mouth_image: Optional[str] = None
    open_mouth_image: Optional[str] = None
    audio_sensitivity: float = DEFAULT_AUDIO_SENSITIVITY
    
    # 语音设置
    voice_dropdown: str = DEFAULT_VOICE
    
    # 视频设置
    video_engine: str = "auto"
    video_resolution: str = "auto"

def validate_inputs(config: VideoProcessingConfig) -> Optional[str]:
    """验证输入配置
    
    Args:
        config: 视频处理配置
        
    Returns:
        Optional[str]: 错误信息，如果没有错误则返回None
    """
    if not config.text_input and not config.selected_file:
        return "错误: 请输入文本或选择一个文件"
    
    if config.selected_file:
        full_path = os.path.join(INPUT_TEXTS_DIR, config.selected_file)
        if not os.path.exists(full_path):
            return f"错误: 文件 {full_path} 不存在"
    
    if config.character_image and config.character_image != "不使用角色图片" and config.character_image != "没有找到图片文件。请在input_images目录添加图片。":
        character_image_path = os.path.join(INPUT_IMAGES_DIR, config.character_image)
        if not os.path.exists(character_image_path):
            print(f"警告: 指定的角色图片不存在: {character_image_path}")
    
    return None

def prepare_input_file(config: VideoProcessingConfig) -> str:
    """准备输入文件
    
    Args:
        config: 视频处理配置
        
    Returns:
        str: 输入文件名
    """
    # 确保input_texts目录存在
    os.makedirs(INPUT_TEXTS_DIR, exist_ok=True)
    
    # 如果有直接输入的文本，将其保存到文件
    if config.text_input:
        with open(f"{INPUT_TEXTS_DIR}/webui_input.txt", "w", encoding="utf-8") as f:
            f.write(config.text_input)
        return "webui_input.txt"
    else:
        return config.selected_file

def update_video_resolution(resolution: str) -> None:
    """更新视频分辨率配置
    
    Args:
        resolution: 视频分辨率设置
    """
    if resolution == "9:16 (1080x1920)":
        config.set("video", "resolution", (1080, 1920))
        config.save()  # 保存配置到文件
        print("设置视频分辨率为: 9:16 (1080x1920)")
    else:  # 默认为16:9
        config.set("video", "resolution", (1920, 1080))
        config.save()  # 保存配置到文件
        print("设置视频分辨率为: 16:9 (1920x1080)")

def build_command(input_file: str, config: VideoProcessingConfig) -> List[str]:
    """构建命令行
    
    Args:
        input_file: 输入文件名
        config: 视频处理配置
        
    Returns:
        List[str]: 命令行参数列表
    """
    # 提取语音ID、服务类型和预设
    service_type, speaker_id, voice_preset = extract_voice_id(config.voice_dropdown)
    
    # 构建基础命令
    cmd = [sys.executable, "full_process.py", input_file, "--image_generator", config.image_generator_type]
    
    # 添加配置参数
    _add_audio_params(cmd, service_type, speaker_id, voice_preset)
    _add_video_params(cmd, config.video_engine)
    _add_image_params(cmd, config.image_generator_type, config.aspect_ratio, 
                      config.image_style_type, config.custom_style, config.comfyui_style)
    _add_subtitle_params(cmd, config.font_name, config.font_size, config.font_color, config.bg_opacity)
    _add_character_params(cmd, config.character_image, config.preserve_line_breaks, 
                         config.talking_character, config.closed_mouth_image, 
                         config.open_mouth_image, config.audio_sensitivity)
    
    # 打印完整命令
    print("\n执行命令:", " ".join(cmd))
    return cmd

def _add_audio_params(cmd: List[str], service_type: str, speaker_id: int, voice_preset: Optional[str]) -> None:
    """添加音频相关参数
    
    Args:
        cmd: 命令行参数列表
        service_type: 服务类型
        speaker_id: 说话人ID
        voice_preset: 语音预设
    """
    # 添加语音ID参数
    cmd.extend(["--speaker_id", str(speaker_id)])
    print(f"添加语音ID: {speaker_id}")
    
    # 添加TTS服务类型参数
    cmd.extend(["--tts_service", service_type])
    print(f"添加TTS服务类型: {service_type}")
    
    # 如果使用OpenAI TTS，添加语音预设参数
    if service_type == "openai_tts":
        # 如果从语音选择中提取了预设，则使用该预设，否则默认使用storyteller
        preset_to_use = voice_preset or "storyteller"
        cmd.extend(["--voice_preset", preset_to_use])
        print(f"添加OpenAI TTS语音预设: {preset_to_use}")

def _add_video_params(cmd: List[str], video_engine: str) -> None:
    """添加视频相关参数
    
    Args:
        cmd: 命令行参数列表
        video_engine: 视频引擎
    """
    # 添加视频引擎参数
    cmd.extend(["--video_engine", video_engine])
    print(f"添加视频引擎参数: --video_engine {video_engine}")

def _add_image_params(cmd: List[str], generator_type: str, aspect_ratio: str, 
                     style_type: str, custom_style: Optional[str], comfyui_style: Optional[str]) -> None:
    """添加图像相关参数
    
    Args:
        cmd: 命令行参数列表
        generator_type: 图像生成器类型
        aspect_ratio: 宽高比
        style_type: 图像风格类型
        custom_style: 自定义风格
        comfyui_style: ComfyUI风格
    """
    # 如果选择了图像比例且使用的是midjourney，添加aspect_ratio参数
    if aspect_ratio and aspect_ratio != "默认方形" and generator_type == "midjourney":
        cmd.extend(["--aspect_ratio", aspect_ratio])
        print(f"添加宽高比参数: --aspect_ratio {aspect_ratio}")
    
    # 处理图像风格
    final_style = None
    if style_type == "自定义风格" and custom_style:
        final_style = custom_style
        # 添加自定义风格参数
        cmd.extend(["--custom_style", custom_style])
        print(f"添加自定义风格: {custom_style}")
    elif style_type != "无风格" and style_type != "自定义风格":
        # 使用预设风格
        final_style = STYLE_PRESETS.get(style_type)
    
    if final_style and style_type != "自定义风格":
        cmd.extend(["--image_style", final_style])
        print(f"添加图像风格: {final_style}")
    
    # 如果使用ComfyUI并选择了风格，添加comfyui_style参数
    if generator_type == "comfyui" and comfyui_style and comfyui_style != "默认(电影)":
        cmd.extend(["--comfyui_style", comfyui_style])
        print(f"添加ComfyUI风格: {comfyui_style}")

def _add_subtitle_params(cmd: List[str], font_name: Optional[str], font_size: Optional[int], 
                        font_color: Optional[str], bg_opacity: Optional[float]) -> None:
    """添加字幕相关参数
    
    Args:
        cmd: 命令行参数列表
        font_name: 字体名称
        font_size: 字体大小
        font_color: 字体颜色
        bg_opacity: 背景不透明度
    """
    # 添加字幕设置参数
    if font_name and font_name != "默认":
        cmd.extend(["--font_name", font_name])
        print(f"添加字幕字体: {font_name}")
    
    if font_size:
        cmd.extend(["--font_size", str(font_size)])
        print(f"添加字体大小: {font_size}")
    
    if font_color and font_color != "#FFFFFF":
        # 移除颜色代码中的#
        color_code = font_color.replace("#", "")
        cmd.extend(["--font_color", color_code])
        print(f"添加字体颜色: {color_code}")
    
    if bg_opacity is not None and bg_opacity != 0.5:
        cmd.extend(["--bg_opacity", str(bg_opacity)])
        print(f"添加背景不透明度: {bg_opacity}")

def _add_character_params(cmd: List[str], character_image: Optional[str], preserve_line_breaks: bool,
                         talking_character: bool, closed_mouth_image: Optional[str], 
                         open_mouth_image: Optional[str], audio_sensitivity: float) -> None:
    """添加角色相关参数
    
    Args:
        cmd: 命令行参数列表
        character_image: 角色图片
        preserve_line_breaks: 是否保留换行
        talking_character: 是否启用会说话的角色
        closed_mouth_image: 闭嘴图片
        open_mouth_image: 张嘴图片
        audio_sensitivity: 音频灵敏度
    """
    # 添加角色图片参数
    if character_image and character_image != "不使用角色图片" and character_image != "没有找到图片文件。请在input_images目录添加图片。":
        character_image_path = os.path.join(INPUT_IMAGES_DIR, character_image)
        if os.path.exists(character_image_path):
            cmd.extend(["--character_image", character_image_path])
            print(f"添加角色图片: {character_image_path}")
        else:
            print(f"警告: 指定的角色图片不存在: {character_image_path}")
    
    # 添加保留原始换行参数
    if preserve_line_breaks:
        cmd.extend(["--preserve_line_breaks"])
        print("添加参数: --preserve_line_breaks (保留文本原始换行)")
    
    # 添加talking_character参数
    if talking_character:
        cmd.extend(["--talking_character"])
        print("添加参数: --talking_character (启用会说话的角色)")
    
    # 添加closed_mouth_image参数
    if closed_mouth_image:
        cmd.extend(["--closed_mouth_image", closed_mouth_image])
        print(f"添加closed_mouth_image参数: {closed_mouth_image}")
    
    # 添加open_mouth_image参数
    if open_mouth_image:
        cmd.extend(["--open_mouth_image", open_mouth_image])
        print(f"添加open_mouth_image参数: {open_mouth_image}")
    
    # 添加audio_sensitivity参数
    cmd.extend(["--audio_sensitivity", str(audio_sensitivity)])
    print(f"添加audio_sensitivity参数: {audio_sensitivity}")

def run_process(cmd: List[str]) -> Generator[Tuple[str, Optional[str]], None, None]:
    """运行进程并获取实时输出
    
    Args:
        cmd: 命令行参数列表
        
    Yields:
        Tuple[str, Optional[str]]: 输出文本和视频路径
    """
    # 运行命令并实时获取输出
    process = subprocess.Popen(
        cmd, 
        stdout=subprocess.PIPE, 
        stderr=subprocess.STDOUT,
        text=True,
        encoding='utf-8',  # 强制使用UTF-8编码
        errors='replace'   # 添加错误处理策略
    )
    
    output = ""
    
    for line in process.stdout:
        try:
            output += line
            yield output, None
        except UnicodeError:
            # 如果出现编码错误，添加一个替代消息
            output += "[无法显示的字符]\n"
            yield output, None
    
    process.wait()
    
    # 处理完成后的结果
    if process.returncode != 0:
        output += f"\n处理完成，但存在错误 (返回码: {process.returncode})"
    else:
        output += "\n处理完成！"
        
        # 找到生成的视频文件
        latest_video = find_latest_video()
        if latest_video:
            output += f"\n生成的视频: {latest_video}"
            output += f"\n👆 可以在上方的视频播放器中预览，或点击视频下方的下载按钮保存到本地"
            yield output, latest_video
            return
    
    yield output, None

def find_latest_video() -> Optional[str]:
    """找到最近生成的视频文件
    
    Returns:
        Optional[str]: 视频文件路径或None
    """
    video_files = glob.glob(f"{OUTPUT_DIR}/*.mp4") + glob.glob(f"{OUTPUT_DIR}/videos/*.mp4")
    if video_files:
        return max(video_files, key=os.path.getmtime)
    return None

def process_story(text_input: str, selected_file: str, image_generator_type: str, aspect_ratio: str, 
                  image_style_type: str, custom_style: Optional[str] = None, comfyui_style: Optional[str] = None, 
                  font_name: Optional[str] = None, font_size: Optional[int] = None, 
                  font_color: Optional[str] = None, bg_opacity: Optional[float] = None, 
                  character_image: Optional[str] = None, preserve_line_breaks: bool = False, 
                  voice_dropdown: str = DEFAULT_VOICE, video_engine: str = "auto", 
                  video_resolution: str = "auto", talking_character: bool = False, 
                  closed_mouth_image: Optional[str] = None, open_mouth_image: Optional[str] = None, 
                  audio_sensitivity: float = DEFAULT_AUDIO_SENSITIVITY) -> Generator[Tuple[str, Optional[str]], None, None]:
    """处理故事文本，生成视频，并返回结果
    
    Args:
        text_input: 直接输入的文本
        selected_file: 选择的文件
        image_generator_type: 图像生成器类型 (comfyui or midjourney)
        aspect_ratio: 图像比例 (16:9, 9:16, 等)
        image_style_type: 图像风格类型
        custom_style: 自定义风格
        comfyui_style: ComfyUI风格
        font_name: 字体名称
        font_size: 字体大小
        font_color: 字体颜色
        bg_opacity: 背景不透明度
        character_image: 角色图片
        preserve_line_breaks: 是否保留换行
        voice_dropdown: 语音选择下拉框的值
        video_engine: 视频处理引擎
        video_resolution: 视频分辨率
        talking_character: 是否启用会说话的角色
        closed_mouth_image: 闭嘴图片路径
        open_mouth_image: 张嘴图片路径
        audio_sensitivity: 音频灵敏度阈值
        
    Yields:
        Tuple[str, Optional[str]]: 输出文本和视频路径
    """
    # 创建配置对象
    config = VideoProcessingConfig(
        text_input=text_input,
        selected_file=selected_file,
        image_generator_type=image_generator_type,
        aspect_ratio=aspect_ratio,
        image_style_type=image_style_type,
        custom_style=custom_style,
        comfyui_style=comfyui_style,
        font_name=font_name,
        font_size=font_size,
        font_color=font_color,
        bg_opacity=bg_opacity,
        character_image=character_image,
        preserve_line_breaks=preserve_line_breaks,
        voice_dropdown=voice_dropdown,
        video_engine=video_engine,
        video_resolution=video_resolution,
        talking_character=talking_character,
        closed_mouth_image=closed_mouth_image,
        open_mouth_image=open_mouth_image,
        audio_sensitivity=audio_sensitivity
    )
    
    # 验证输入
    error = validate_inputs(config)
    if error:
        yield error, None
        return
    
    # 清理之前的输出文件
    cleanup_message = cleanup_output_directories()
    yield f"开始处理...\n{cleanup_message}\n\n", None
    
    # 设置分辨率
    update_video_resolution(config.video_resolution)
    
    # 准备输入文件
    input_file = prepare_input_file(config)
    
    # 构建命令
    cmd = build_command(input_file, config)
    
    # 运行进程并获取输出
    yield from run_process(cmd) 