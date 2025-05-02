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
import logging
import io
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

def build_command(input_file: str, config: VideoProcessingConfig, subtitle_vertical_offset: int = 0, speed_scale: float = 1.0) -> List[str]:
    """构建命令行
    
    Args:
        input_file: 输入文件名
        config: 视频处理配置
        subtitle_vertical_offset: 字幕垂直偏移量 (新增)
        speed_scale: 语速调整 (新增)
        
    Returns:
        List[str]: 命令行参数列表
    """
    # 提取语音ID、服务类型和预设
    service_type, speaker_id, voice_preset = extract_voice_id(config.voice_dropdown)
    
    # 构建基础命令
    cmd = [sys.executable, "full_process.py", input_file, "--image_generator", config.image_generator_type]
    
    # 添加配置参数
    _add_audio_params(cmd, service_type, speaker_id, voice_preset, speed_scale)
    _add_video_params(cmd, config.video_engine)
    _add_image_params(cmd, config.image_generator_type, config.aspect_ratio, 
                      config.image_style_type, config.custom_style, config.comfyui_style)
    _add_subtitle_params(cmd, config.font_name, config.font_size, config.font_color, config.bg_opacity, subtitle_vertical_offset)
    _add_character_params(cmd, config.character_image, config.preserve_line_breaks, 
                         config.talking_character, config.closed_mouth_image, 
                         config.open_mouth_image, config.audio_sensitivity)
    
    # 打印完整命令
    print("\n执行命令:", " ".join(cmd))
    return cmd

def _add_audio_params(cmd: List[str], service_type: str, speaker_id: int, voice_preset: Optional[str], speed_scale: float = 1.0) -> None:
    """添加音频相关参数
    
    Args:
        cmd: 命令行参数列表
        service_type: 服务类型
        speaker_id: 说话人ID
        voice_preset: 语音预设
        speed_scale: 语速调整 (新增)
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

    # 添加语速调整参数
    if speed_scale != 1.0:
        cmd.extend(["--speed", str(speed_scale)])
        print(f"添加语速调整: {speed_scale}")

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
                        font_color: Optional[str], bg_opacity: Optional[float],
                        subtitle_vertical_offset: int = 0) -> None:
    """添加字幕相关参数
    
    Args:
        cmd: 命令行参数列表
        font_name: 字体名称
        font_size: 字体大小
        font_color: 字体颜色
        bg_opacity: 背景不透明度
        subtitle_vertical_offset: 字幕垂直偏移量 (默认0)
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
    
    # 新增：添加垂直偏移量参数（如果非默认值）
    if subtitle_vertical_offset != 0:
        cmd.extend(["--subtitle_vertical_offset", str(subtitle_vertical_offset)])
        print(f"添加字幕垂直偏移量: {subtitle_vertical_offset}")

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
    """运行子进程并实时产生输出，现在主要用于日志传递"""
    output_log = ""
    return_code = -1
    process = None # Initialize process to None
    try:
        process = subprocess.Popen(
            cmd, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.STDOUT,
            text=True,
                encoding='utf-8',
                errors='replace', 
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
        )
    
        if process.stdout:
            for line in iter(process.stdout.readline, ''):
                if line:
                    output_log += line
                    yield line, None
            # Ensure stdout is closed if loop finishes
            if process.stdout and not process.stdout.closed:
                 process.stdout.close()
            
        return_code = process.wait()
        
        if return_code != 0:
            yield f"错误: 进程返回错误码 {return_code}\\n", None
        else:
            yield "进程成功完成\\n", None
            
    except FileNotFoundError:
        yield f"错误: 无法找到执行程序 {cmd[0]}. 请确保Python和相关依赖已正确安装并添加到PATH。\\n", None
    except Exception as e:
        yield f"运行子进程时出错: {e}\\n", None
    finally:
        # Ensure resources are cleaned up even if errors occur during Popen
        if process and process.stdout and not process.stdout.closed:
            process.stdout.close()
        # We might not need to yield anything in finally, just cleanup

def find_latest_video() -> Optional[str]:
    """查找最新的视频文件"""
    # Use Path for better path handling
    output_dir = Path(OUTPUT_DIR)
    video_files = list(output_dir.glob("*.mp4")) + list(output_dir.glob("videos/*.mp4"))
    if video_files:
        # Use pathlib's stat().st_mtime for modification time
        return str(max(video_files, key=lambda p: p.stat().st_mtime))
    return None

def process_story(
    text_input: str, selected_file: str, image_generator_type: str, aspect_ratio: str, 
                  image_style_type: str, custom_style: Optional[str] = None, comfyui_style: Optional[str] = None, 
                  font_name: Optional[str] = None, font_size: Optional[int] = None, 
                  font_color: Optional[str] = None, bg_opacity: Optional[float] = None, 
    subtitle_vertical_offset: int = 0, 
                  character_image: Optional[str] = None, preserve_line_breaks: bool = False, 
                  voice_dropdown: str = DEFAULT_VOICE, 
                  speed_scale: float = 1.0, # Default value from full_process
                  video_engine: str = "auto", 
                  video_resolution: str = "auto", talking_character: bool = False, 
                  closed_mouth_image: Optional[str] = None, open_mouth_image: Optional[str] = None, 
    audio_sensitivity: float = DEFAULT_AUDIO_SENSITIVITY, 
    # Add missing parameters from ui_components call
    mj_concurrency: int = 3, # Default value from full_process
    no_regenerate_images: bool = False # Value from placeholder
) -> Generator[Union[Tuple[str, Optional[str], str]], None, None]:
    """处理故事文本并生成视频，捕获日志信息
        
    Yields:
        tuple: (状态文本, 视频路径或None, 日志字符串)
    """
    # --- 日志捕获设置 ---
    log_stream = io.StringIO()
    root_logger = logging.getLogger() 
    log_handler = logging.StreamHandler(log_stream)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    log_handler.setFormatter(formatter)
    original_level = root_logger.level
    root_logger.addHandler(log_handler)
    if root_logger.level == logging.NOTSET or root_logger.level > logging.INFO:
         root_logger.setLevel(logging.INFO) 
    # --- 日志捕获设置结束 ---

    logger = logging.getLogger(__name__) 
    final_video_path = None
    status_message = ""
    error_occurred = False
    log_string = ""
    
    # The main try block for the entire process
    try:
        logger.info("开始处理故事...")

        # Create config object (assuming VideoProcessingConfig exists and is correct)
        # Add the missing parameters to the config object creation if needed
        proc_config = VideoProcessingConfig(
            text_input=text_input, selected_file=selected_file, 
            image_generator_type=image_generator_type, aspect_ratio=aspect_ratio, 
            image_style_type=image_style_type, custom_style=custom_style, comfyui_style=comfyui_style,
            font_name=font_name, font_size=font_size, font_color=font_color, bg_opacity=bg_opacity,
            character_image=character_image, preserve_line_breaks=preserve_line_breaks, 
            voice_dropdown=voice_dropdown, video_engine=video_engine, video_resolution=video_resolution,
            talking_character=talking_character, closed_mouth_image=closed_mouth_image,
            open_mouth_image=open_mouth_image, audio_sensitivity=audio_sensitivity,
            # Ensure mj_concurrency, speed_scale, no_regenerate_images are handled by config or passed separately
    )
    
        # 1. Validate inputs (assuming validate_inputs exists)
        logger.info("验证输入...")
        error = validate_inputs(proc_config)
        if error: # Correct indentation for the if block
            status_message = error
            logger.error(error)
            error_occurred = True
            raise Exception(error)
        
        # 2. Prepare input file (assuming prepare_input_file exists)
        logger.info("准备输入文件...")
        input_file = prepare_input_file(proc_config)
        logger.info(f"使用输入文件: {input_file}")
        
        # 3. Update video resolution (assuming update_video_resolution exists)
        logger.info(f"更新视频分辨率设置: {video_resolution}")
        update_video_resolution(video_resolution)
        
        # 4. Build command (assuming build_command exists)
        logger.info("构建处理命令...")
        # Pass the new parameters to build_command if necessary
        cmd = build_command(input_file, proc_config, subtitle_vertical_offset, speed_scale)
        log_stream.write("构建的命令:\n" + " ".join(cmd) + "\n\nRunning...") 
        status_message = "构建命令完成，开始执行...\n"
        yield status_message, None, log_stream.getvalue()
        
        # 5. Execute main process (full_process.py)
        logger.info("开始执行 full_process.py ...")
        process = subprocess.Popen(
            cmd, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.STDOUT, 
            text=True, 
            encoding='utf-8',
            errors='replace', 
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
        )

        # --- Stage detection mapping --- 
        stage_keywords = {
            "处理文本...": "正在处理文本...",
            "生成语音...": "正在生成语音...",
            "故事分析和场景识别...": "正在分析场景...",
            "生成图像...": "正在生成图像...",
            "生成字幕...": "正在生成字幕...",
            "创建视频...": "正在合成视频...",
            "处理完成": "处理完成！",
            "处理过程中发生错误": "处理失败！", # Add error detection
        }
        current_stage_message = "正在执行..." # Initial stage message

        if process.stdout: # Correct indentation
            for line in iter(process.stdout.readline, ''):
                if line:
                    log_stream.write(line) 
                    
                    # --- Check for stage update --- 
                    cleaned_line = line.strip()
                    for keyword, stage_msg in stage_keywords.items():
                        if keyword in cleaned_line:
                            current_stage_message = stage_msg
                            logger.info(f"检测到新阶段: {current_stage_message}") # Log stage change
                            break # Use the first keyword found on the line
                    
                    # Yield the potentially updated status message
                    yield current_stage_message, None, log_stream.getvalue() 
            # Ensure stdout is closed if loop finishes
            if process.stdout and not process.stdout.closed:
                process.stdout.close()

        return_code = process.wait()
        logger.info(f"full_process.py 执行完成，返回码: {return_code}")
        
        if return_code != 0:
            error_msg = f"错误: 处理过程中发生错误，请检查日志了解详情。返回码: {return_code}"
            status_message = "处理失败！" # Update final status on error
            logger.error(error_msg)
            error_occurred = True
            raise Exception(error_msg)
    
        # 6. Find latest video
        logger.info("查找生成的视频文件...")
        final_video_path = find_latest_video()
        
        if final_video_path:
            success_msg = f"处理完成！视频已保存到: {final_video_path}"
            status_message = "处理完成！" # Update final status on success
            logger.info(success_msg)
        else:
            error_msg = "错误: 处理完成，但未找到输出视频文件。"
            status_message = "处理失败！(未找到视频)" # Update final status
            logger.error(error_msg)
            error_occurred = True
            raise Exception(error_msg)

    except Exception as e: # Aligned with the main try
        if not error_occurred:
            import traceback
            error_details = traceback.format_exc()
            status_message = f"发生意外错误: {e}" # Update status on unexpected error
            logger.error(f"处理故事时发生意外错误: {e}\n{error_details}")
        error_occurred = True
        
    finally: # Aligned with the main try
        # --- 日志捕获清理 ---
        log_stream.seek(0)
        log_string = log_stream.read()
        log_handler.close()
        root_logger.removeHandler(log_handler)
        if 'original_level' in locals() and root_logger.level != original_level:
             root_logger.setLevel(original_level)
        # --- 日志捕获清理结束 ---
        
        # Final yield with the complete log and final status message
        yield status_message, final_video_path if not error_occurred else None, log_string 