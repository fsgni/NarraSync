import os
from pathlib import Path
from text_processor import TextProcessor
from voice_generator import VoiceVoxGenerator
from story_analyzer import StoryAnalyzer
from image_generator import ComfyUIGenerator
from midjourney_generator import MidjourneyGenerator
from video_processor import VideoProcessor
import json
import subprocess
import argparse
import sys
import time
import shutil
import locale
import logging
import asyncio
from test_voice_generator import process_voice_generation
from scene_management import rewrite_prompt_with_ai

# 设置日志记录
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("output/narra_sync.log", mode='a'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("full_process")

# 定义Midjourney并发限制 (移除，改为函数参数)
# MAX_MJ_CONCURRENT_REQUESTS = 5 

# 设置系统编码为UTF-8，解决Windows命令行的编码问题
if sys.stdout.encoding != 'utf-8':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    elif hasattr(sys.stdout, 'buffer'):
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='backslashreplace')

def get_full_path(file_path, default_dir=None):
    """
    获取文件的完整路径
    
    Args:
        file_path: 原始文件路径
        default_dir: 默认目录，当file_path不包含目录时使用
        
    Returns:
        完整的文件路径
    """
    if not file_path:
        return None
    
    if os.path.isabs(file_path):
        return file_path
    elif default_dir and not os.path.dirname(file_path):
        return os.path.join(default_dir, file_path)
    return file_path

def try_read_with_encodings(file_path, encodings=None):
    """
    尝试使用多种编码读取文件
    
    Args:
        file_path: 文件路径
        encodings: 要尝试的编码列表，如果为None则使用默认编码列表
        
    Returns:
        tuple: (文件内容, 使用的编码) 如果所有编码都失败则返回 (None, None)
    """
    if encodings is None:
        # 获取系统默认编码
        system_encoding = locale.getpreferredencoding()
        encodings = ["utf-8", "utf-8-sig", "shift_jis", "euc-jp", "cp932", "iso-2022-jp"]
        if system_encoding not in encodings:
            encodings.append(system_encoding)
    
    # 尝试多种编码
    for encoding in encodings:
        try:
            print(f"尝试使用 {encoding} 编码读取文件...")
            with open(file_path, "r", encoding=encoding) as f:
                content = f.read()
            print(f"成功使用 {encoding} 编码读取文件")
            return content, encoding
        except UnicodeDecodeError:
            print(f"{encoding} 编码读取失败")
            continue
    
    # 如果所有编码都失败，尝试二进制读取
    print("所有文本编码都失败，尝试二进制读取...")
    try:
        with open(file_path, "rb") as f:
            binary_data = f.read()
            # 尝试检测编码
            try:
                import chardet
                detected = chardet.detect(binary_data)
                detected_encoding = detected["encoding"]
                confidence = detected["confidence"]
                print(f"检测到可能的编码: {detected_encoding}，置信度: {confidence}")
                if detected_encoding:
                    content = binary_data.decode(detected_encoding)
                    return content, detected_encoding
            except ImportError:
                print("chardet库未安装，无法自动检测编码")
                
            # 使用系统默认编码作为最后尝试
            system_encoding = locale.getpreferredencoding()
            try:
                content = binary_data.decode(system_encoding, errors="replace")
                print(f"使用系统编码 {system_encoding} 和替换错误策略成功读取")
                return content, f"{system_encoding} (替换错误)"
            except:
                content = binary_data.decode("utf-8", errors="replace")
                print("使用UTF-8编码和替换错误策略成功读取")
                return content, "utf-8 (替换错误)"
    except Exception as e:
        print(f"二进制读取失败: {e}")
    
    return None, None

def clean_output_directories():
    """清理输出目录中的旧文件"""
    try:
        logger.info("开始清理输出目录")
        # 定义需要清理的目录和文件类型
        cleanup_targets = [
            ("output/images", "*.png"),
            ("output/videos", "*.mp4"),
            ("output/audio", "*.*"),
            ("output/texts", "*.txt"),
            ("output", "*.mp4"),
            ("output", "*.srt"),
            ("output", "*.json")
        ]
        
        # 使用循环替代重复代码
        for dir_path, pattern in cleanup_targets:
            path = Path(dir_path)
            if path.exists():
                logger.debug(f"清理目录: {dir_path}, 文件模式: {pattern}")
                for file in path.glob(pattern):
                    try:
                        file.unlink()
                        print(f"已删除: {file}")
                        logger.debug(f"已删除文件: {file}")
                    except Exception as e:
                        error_msg = f"无法删除 {file}: {e}"
                        print(error_msg)
                        logger.error(error_msg)
        
        print("输出目录清理完成")
        logger.info("输出目录清理完成")
    except Exception as e:
        error_msg = f"清理输出目录时出错: {e}"
        print(error_msg)
        logger.exception(error_msg)

# 新增：异步并发生成图像的辅助函数
async def generate_images_concurrently(key_scenes, image_generator_type, aspect_ratio, image_style, custom_style, comfyui_style, mj_concurrency):
    logger.info(f"开始并发生成图像，并发数限制: {mj_concurrency}")
    image_files = []
    processed_scenes = [] # 用于存储包含生成结果的场景信息
    
    # 根据类型选择生成器
    if image_generator_type.lower() == "comfyui":
        generator = ComfyUIGenerator(style=comfyui_style)
        logger.info(f"使用 ComfyUI 生成器, 风格: {comfyui_style}")
        # TODO: ComfyUI 的并发逻辑可能不同，这里暂时保持原样或后续添加
        # 目前 ComfyUI 部分的并发未实现
        for i, scene in enumerate(key_scenes):
            # ... (保留原有 ComfyUI 生成逻辑, 非并发) ...
            scene_prompt = scene['prompt'] if isinstance(scene, dict) and 'prompt' in scene else str(scene)
            image_filename = scene['image_file'] if isinstance(scene, dict) and 'image_file' in scene else f"scene_{i+1:03d}.png"
            
            # 准备最终提示词 (合并风格等)
            final_prompt = scene_prompt # 简化示例，实际应包含风格处理
            if custom_style:
                final_prompt += f", {custom_style}"
            elif image_style:
                 final_prompt += f", {image_style}"
            # ... (添加其他通用修饰词) ...
            
            image_file = generator.generate_image(final_prompt, image_filename) # 同步调用
            if image_file:
                image_files.append(image_file)
                if isinstance(scene, dict):
                    scene['image_file_generated'] = image_file # 更新场景信息
                    processed_scenes.append(scene)
                logger.info(f"ComfyUI 场景 {i+1} 图像生成成功: {image_file}")
            else:
                logger.warning(f"ComfyUI 场景 {i+1} 图像生成结果为空")
                if isinstance(scene, dict):
                    processed_scenes.append(scene) # 即使失败也要保留场景结构
                    
    elif image_generator_type.lower() == "midjourney":
        generator = MidjourneyGenerator()
        logger.info("使用 Midjourney 生成器")
        semaphore = asyncio.Semaphore(mj_concurrency)
        
        async def generate_single_image_task(scene_index, scene_data):
            async with semaphore:
                logger.info(f"开始处理 Midjourney 场景 {scene_index + 1}")
                original_prompt = scene_data['prompt'] if isinstance(scene_data, dict) and 'prompt' in scene_data else str(scene_data)
                image_filename = scene_data['image_file'] if isinstance(scene_data, dict) and 'image_file' in scene_data else f"scene_{scene_index+1:03d}.png"
                
                # 准备最终提示词 (合并风格等)
                final_prompt = original_prompt # 先用原始提示词
                if custom_style:
                    final_prompt += f", {custom_style}"
                elif image_style:
                     final_prompt += f", {image_style}"
                # ... (添加其他通用修饰词) ...
                
                logger.debug(f"MJ 场景 {scene_index + 1} 初始最终提示词: {final_prompt[:100]}...")
                
                # 第一次尝试：调用异步生成方法
                image_file = await generator.generate_image_async(
                    final_prompt,
                    image_filename,
                    aspect_ratio=aspect_ratio
                )
                
                # 如果第一次尝试失败，尝试 AI 重写并重试一次
                if not image_file:
                    logger.warning(f"Midjourney 场景 {scene_index + 1} 第一次生成失败，尝试 AI 重写提示词...")
                    # 使用AI重写提示词 (重试次数设为0，表示这是第一次重写)
                    new_prompt = rewrite_prompt_with_ai(original_prompt, 0)
                    
                    # 更新场景提示词 (可选，看是否需要在最终结果中反映)
                    # if isinstance(scene_data, dict):
                    #     scene_data['prompt'] = new_prompt
                        
                    # 准备重试的最终提示词
                    retry_final_prompt = new_prompt
                    if custom_style:
                        retry_final_prompt += f", {custom_style}"
                    elif image_style:
                        retry_final_prompt += f", {image_style}"

                    logger.info(f"使用重写后的提示词重试 MJ 场景 {scene_index + 1}: {retry_final_prompt[:100]}...")
                    # 第二次尝试：使用重写后的提示词再次调用
                    image_file = await generator.generate_image_async(
                        retry_final_prompt,
                        image_filename,
                        aspect_ratio=aspect_ratio
                    )
                    # 检查第二次尝试结果
                    if not image_file:
                        logger.error(f"Midjourney 场景 {scene_index + 1} 使用重写提示词后仍然生成失败")
                        # 即使重试失败，也返回原始场景数据，只是没有成功标志
                        return {"index": scene_index, "scene_data": scene_data, "success": False}
                    else:
                        logger.info(f"Midjourney 场景 {scene_index + 1} 使用重写提示词后生成成功: {image_file}")
                        # 更新场景数据中的提示词为重写后的（如果需要）
                        if isinstance(scene_data, dict):
                           scene_data['prompt'] = new_prompt 
                        return {"index": scene_index, "scene_data": scene_data, "image_file": image_file, "success": True}

                # 如果第一次尝试成功
                else:
                    logger.info(f"Midjourney 场景 {scene_index + 1} 图像生成成功: {image_file}")
                    return {"index": scene_index, "scene_data": scene_data, "image_file": image_file, "success": True}

        # 创建所有并发任务
        tasks = [generate_single_image_task(i, scene) for i, scene in enumerate(key_scenes)]
        
        # 并发执行并收集结果
        logger.info(f"准备并发执行 {len(tasks)} 个 Midjourney 图像生成任务...")
        results = await asyncio.gather(*tasks)
        logger.info("所有 Midjourney 并发任务已完成处理。")
        
        # 按原始顺序处理结果
        processed_scenes = [None] * len(key_scenes) # 初始化结果列表
        for result in results:
            idx = result["index"]
            scene_data = result["scene_data"]
            if result["success"] and isinstance(scene_data, dict):
                scene_data['image_file_generated'] = result["image_file"]
                image_files.append(result["image_file"]) # 添加到成功列表
            elif isinstance(scene_data, dict):
                 # 即使失败也要保留场景结构
                 scene_data['image_file_generated'] = None 
            processed_scenes[idx] = scene_data # 按原索引放回结果
        
        # 过滤掉可能的None值（如果原始key_scenes有问题）
        processed_scenes = [s for s in processed_scenes if s is not None] 
            
    else:
        logger.error(f"不支持的图像生成器类型: {image_generator_type}")
        processed_scenes = key_scenes # 返回原始场景

    logger.info(f"图像生成完成，共成功生成 {len(image_files)} 个图像")
    return processed_scenes # 返回处理后的场景列表（可能包含生成的图片路径）

def process_story(input_file: str, image_generator_type: str = "comfyui", aspect_ratio: str = None, image_style: str = None, comfyui_style: str = None, font_name: str = None, font_size: int = None, font_color: str = None, bg_opacity: float = None, character_image: str = None, preserve_line_breaks: bool = False, speaker_id: int = 13, speed_scale: float = 1.0, mj_concurrency: int = 3, video_engine: str = "auto", no_regenerate_images: bool = False, tts_service: str = "voicevox", voice_preset: str = None, custom_style: str = None, talking_character: bool = False, closed_mouth_image: str = None, open_mouth_image: str = None, audio_sensitivity: float = 0.04):
    """
    完整的故事处理流程
    
    Args:
        input_file: 输入文本文件路径
        image_generator_type: 图像生成器类型，可选 "comfyui" 或 "midjourney"
        aspect_ratio: 图像比例，可选值为 "16:9", "9:16" 或 None (默认方形)，仅对midjourney有效
        image_style: 图像风格，例如: 'cinematic lighting, movie quality' 或 'ancient Chinese ink painting style'
        comfyui_style: ComfyUI的风格选项，可选值为 "水墨", "手绘", "古风", "插画", "写实", "电影"
        font_name: 字幕字体名称
        font_size: 字幕字体大小
        font_color: 字幕字体颜色 (十六进制，不含#)
        bg_opacity: 字幕背景不透明度 (0-1)
        character_image: 角色图片路径，如果提供则在右下角显示
        preserve_line_breaks: 是否保留文本中的原始换行
        speaker_id: 语音角色ID
        speed_scale: 语速调整 (例如 0.5 到 2.0)
        mj_concurrency: Midjourney 并发数 (默认 3)
        video_engine: 视频处理引擎，可选 "ffmpeg", "moviepy" 或 "auto"
        no_regenerate_images: 是否不重新生成图片，保留现有图片
        tts_service: 文本到语音服务类型，可选 "voicevox" 或 "openai_tts"
        voice_preset: 语音预设名称，如"storyteller", "formal", "cheerful"等，仅用于OpenAI TTS
        custom_style: 自定义风格
        talking_character: 是否启用会说话的角色效果
        closed_mouth_image: 闭嘴图片路径
        open_mouth_image: 张嘴图片路径
        audio_sensitivity: 音频灵敏度，控制嘴巴开合的阈值
    """
    # 检查输入文件是否存在
    full_input_path = get_full_path(input_file, "input_texts")
    
    # 验证文件存在
    if not os.path.exists(full_input_path):
        error_msg = f"错误: 找不到输入文件 {full_input_path}"
        print(error_msg)
        return error_msg
    
    # 先清理旧数据
    clean_output_directories()
    
    print("=== 开始处理故事 ===")
    print(f"输入文件: {full_input_path}")
    print(f"图像生成器: {image_generator_type}")
    if aspect_ratio and image_generator_type.lower() == "midjourney":
        print(f"图像比例: {aspect_ratio}")
    if image_style:
        print(f"图像风格: {image_style}")
    if comfyui_style and image_generator_type.lower() == "comfyui":
        print(f"ComfyUI风格: {comfyui_style}")
    if preserve_line_breaks:
        print("文本处理: 保留原始换行")
    else:
        print("文本处理: 智能分句")
    print(f"视频处理引擎: {video_engine}")
    
    # 创建所需目录
    for dir_name in ["output", "output/audio", "output/images", "output/texts", "output/videos"]:
        Path(dir_name).mkdir(parents=True, exist_ok=True)
    
    try:
        # 1. 文本处理
        print("\n1. 处理文本...")
        text_processor = TextProcessor()
        
        # 尝试读取文本文件
        text, used_encoding = try_read_with_encodings(full_input_path)
        
        if not text or not text.strip():
            error_msg = f"错误: 输入文件 {full_input_path} 为空或无法读取"
            print(error_msg)
            return error_msg
            
        # 根据用户选择决定是否保留原始换行
        if preserve_line_breaks:
            print("使用保留原始换行模式处理文本...")
            sentences = text_processor.process_japanese_text(text, preserve_line_breaks=True)
        else:
            print("使用智能分句模式处理文本...")
            sentences = text_processor.process_japanese_text(text)
        
        # 保存处理后的文本
        output_text_file = f"output/texts/{Path(full_input_path).name}"
        with open(output_text_file, "w", encoding="utf-8") as f:
            f.write("\n".join(sentences))
        print(f"文本处理完成，已保存到: {output_text_file}")
        
        # 2. 生成语音
        print("\n2. 生成语音...")
        audio_info_file = f"output/audio/{Path(full_input_path).stem}_audio_info.json"
        # 导入异步函数，并使用 asyncio.run 执行
        try:
            audio_info = asyncio.run(process_voice_generation(
                output_text_file, 
                "output/audio", 
                speaker_id=speaker_id, 
                speed_scale=speed_scale,
                use_dict=True,
                tts_service=tts_service,
                voice_preset=voice_preset
            ))
        except Exception as e:
            error_msg = f"运行并发语音生成时出错: {e}"
            print(error_msg)
            logger.error(error_msg)
            return error_msg # 或者抛出异常，根据错误处理策略
            
        print(f"语音生成完成，信息已保存到: {audio_info_file}")
        logger.info(f"语音生成完成: {len(audio_info)} 个文件，总时长 {sum(item.get('duration', 0) for item in audio_info if 'duration' in item):.2f}秒")
        
        # 3. 分析故事和生成场景
        print("\n3. 分析故事和生成场景...")
        analyzer = StoryAnalyzer()
        story_analysis = analyzer.analyze_story(text, full_input_path)
        key_scenes = analyzer.identify_key_scenes(sentences)
        
        # 保存场景信息
        with open("output/key_scenes.json", "w", encoding="utf-8") as f:
            json.dump(key_scenes, f, ensure_ascii=False, indent=2)
        print("场景分析完成，信息已保存")
        
        # 4. 生成图像
        print("\n4. 生成图像...")
        logger.info("开始生成图像")
        image_files = [] # 这个列表现在由并发函数内部管理并返回在processed_scenes中
        
        # 检查是否需要跳过图像生成
        if no_regenerate_images:
            print("已选择不重新生成图片模式，将保留所有现有图片")
            logger.info("已启用不重新生成图片模式")
            from image_processor import ImageProcessor
            image_processor = ImageProcessor()
            # 仅更新提示词 (这里可能也需要调整以适应新的场景结构)
            try:
                # 假设 process_scene_images 也能处理更新后的场景结构
                key_scenes = image_processor.process_scene_images(
                    key_scenes, 
                    image_generator_type,
                    aspect_ratio, 
                    image_style, 
                    custom_style,
                    comfyui_style,
                    no_regenerate=True
                )
                logger.info("成功更新场景提示词 (跳过生成)")
            except Exception as e:
                error_msg = f"更新场景提示词时出错: {e}"
                print(error_msg)
                logger.error(error_msg)
        else:
            # 调用新的并发图像生成函数
            try:
                logger.info("调用并发图像生成函数...")
                # 注意：这里使用了 asyncio.run() 来执行异步函数
                key_scenes = asyncio.run(generate_images_concurrently(
                    key_scenes,
                    image_generator_type,
                    aspect_ratio,
                    image_style,
                    custom_style,
                    comfyui_style,
                    mj_concurrency
                ))
                logger.info("并发图像生成函数执行完毕。")
                # 重新提取成功生成的图片文件列表（如果需要的话）
                image_files = [s['image_file_generated'] for s in key_scenes if isinstance(s, dict) and s.get('image_file_generated')]
            except Exception as e:
                 error_msg = f"并发生成图像时出错: {e}"
                 print(error_msg)
                 logger.exception(error_msg)
                 # 根据错误处理策略决定是否继续

        # 确认更新后的场景信息写回文件
        with open("output/key_scenes.json", "w", encoding="utf-8") as f:
            json.dump(key_scenes, f, ensure_ascii=False, indent=2)
        print("场景信息已更新并保存")
        
        # 5. 生成字幕
        print("\n5. 生成字幕...")
        srt_file = f"output/{Path(full_input_path).stem}.srt"
        from generate_srt import generate_srt
        generate_srt(audio_info_file, srt_file, respect_line_breaks=preserve_line_breaks)
        print(f"字幕生成完成: {srt_file}")
        
        # 6. 创建视频
        print("\n6. 创建视频...")
        base_video = "output/base_video.mp4"
        final_video = "output/final_video.mp4"
        
        # 使用新的VideoProcessor统一处理
        video_processor = VideoProcessor(engine=video_engine)
        print(f"使用 {video_processor.engine.upper()} 引擎处理视频")
        
        # 创建基础视频
        video_processor.create_base_video(audio_info_file, base_video)
        
        # 创建场景视频
        video_processor.create_video_with_scenes("output/key_scenes.json", base_video, final_video)
        
        # 如果提供了角色图片，添加角色图片
        if character_image and character_image != "不使用角色图片" and character_image != "没有找到图片文件。请在input_images目录添加图片。":
            print("\n6.1 添加角色图片...")
            print(f"角色图片路径: {character_image}")
            
            # 将角色图片转换为完整路径
            character_image_path = get_full_path(character_image, "input_images")
            
            # 检查图片是否存在
            if not os.path.exists(character_image_path):
                print(f"警告: 指定的角色图片不存在: {character_image_path}")
                # 尝试查找可能的图片位置
                possible_locations = [
                    os.path.join("output", os.path.basename(character_image)),
                    os.path.join("input_images", os.path.basename(character_image))
                ]
                for loc in possible_locations:
                    if os.path.exists(loc):
                        print(f"找到可能的替代图片: {loc}")
                        character_image_path = loc
                        break
                else:
                    print("无法找到替代图片，跳过角色图片添加")
                    character_image_path = None
            
            if character_image_path:
                # 创建临时视频文件
                temp_video_with_character = "output/temp_video_with_character.mp4"
                
                # 判断是否使用会说话的角色
                if talking_character and closed_mouth_image and open_mouth_image and closed_mouth_image != "不使用角色图片" and open_mouth_image != "不使用角色图片":
                    try:
                        print("使用会说话的角色效果...")
                        
                        # 准备闭嘴和张嘴图片路径
                        closed_mouth_path = get_full_path(closed_mouth_image, "input_images")
                        open_mouth_path = get_full_path(open_mouth_image, "input_images")
                        
                        # 检查图片是否存在
                        if not os.path.exists(closed_mouth_path) or not os.path.exists(open_mouth_path):
                            print(f"警告: 闭嘴或张嘴图片不存在，将使用普通角色图片")
                            # 使用普通角色图片模式
                            from add_character_image import add_character_image_to_video
                            success = add_character_image_to_video(final_video, character_image_path, temp_video_with_character)
                        else:
                            # 导入会说话角色模块
                            from add_talking_character import create_talking_character_video
                            
                            # 添加会说话的角色
                            success = create_talking_character_video(
                                final_video, 
                                closed_mouth_path, 
                                open_mouth_path, 
                                temp_video_with_character,
                                threshold=audio_sensitivity
                            )
                        
                        if success:
                            print(f"成功添加会说话的角色图片到视频")
                            # 使用带有角色图片的视频作为最终视频
                            final_video = temp_video_with_character
                        else:
                            print(f"添加会说话的角色图片失败，将使用原始视频继续处理")
                    except Exception as e:
                        print(f"添加会说话的角色过程中出错: {e}")
                        import traceback
                        traceback.print_exc()
                        print("将使用原始视频继续处理")
                else:
                    try:
                        # 使用普通角色图片
                        from add_character_image import add_character_image_to_video
                        success = add_character_image_to_video(final_video, character_image_path, temp_video_with_character)
                        if success:
                            print(f"成功添加角色图片到视频")
                            final_video = temp_video_with_character
                        else:
                            print(f"添加角色图片失败，将使用原始视频继续处理")
                    except Exception as e:
                        print(f"添加角色图片过程中出错: {e}")
                        import traceback
                        traceback.print_exc()
                        print("将使用原始视频继续处理")
        
        print("视频创建完成")
        
        # 7. 添加字幕
        print("\n7. 添加字幕...")
        output_video = f"output/{Path(full_input_path).stem}_final.mp4"
        
        # 使用传入的字幕设置参数
        subtitle_params = {}
        if font_name:
            subtitle_params["font_name"] = font_name
        if font_size:
            subtitle_params["font_size"] = font_size
        if font_color:
            subtitle_params["font_color"] = font_color
        if bg_opacity is not None:
            subtitle_params["bg_opacity"] = bg_opacity
        
        from add_subtitles import add_subtitles
        add_subtitles(final_video, srt_file, output_video, **subtitle_params)
        print(f"最终视频已生成: {output_video}")
        
        print("\n=== 处理完成 ===")
        return output_video
        
    except Exception as e:
        print(f"处理过程中发生错误: {e}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == "__main__":
    # 创建命令行参数解析器
    parser = argparse.ArgumentParser(description="故事视频生成器")
    parser.add_argument("input_file", nargs="?", help="输入文本文件名称或路径")
    parser.add_argument("--image_generator", choices=["comfyui", "midjourney"], default="comfyui",
                        help="选择图像生成器: comfyui (默认) 或 midjourney")
    parser.add_argument("-g", "--generator", choices=["comfyui", "midjourney"], default="comfyui",
                        help="选择图像生成器: comfyui (默认) 或 midjourney (与--image_generator相同)")
    parser.add_argument("--aspect_ratio", choices=["16:9", "9:16"], 
                        help="设置图像比例 (仅对midjourney有效): 16:9 (横屏) 或 9:16 (竖屏)")
    parser.add_argument("--image_style", 
                        help="设置图像风格，例如: 'cinematic lighting, movie quality' 或 'ancient Chinese ink painting style'")
    parser.add_argument("--custom_style", 
                        help="自定义图像风格，当选择'自定义风格'时使用")
    parser.add_argument("--comfyui_style", 
                        help="设置ComfyUI的风格选项，可选值为 '水墨', '手绘', '古风', '插画', '写实', '电影'")
    # 字幕设置参数
    parser.add_argument("--font_name", help="设置字幕字体名称")
    parser.add_argument("--font_size", type=int, help="设置字幕字体大小")
    parser.add_argument("--font_color", help="设置字幕字体颜色 (十六进制，不含#)")
    parser.add_argument("--bg_opacity", type=float, help="设置字幕背景不透明度 (0-1)")
    parser.add_argument("--character_image", help="设置角色图片路径，如果提供则在右下角显示")
    parser.add_argument("--preserve_line_breaks", action="store_true", help="保留文本中的原始换行")
    parser.add_argument("--speaker_id", type=int, default=13, help="设置语音角色ID")
    # 添加视频处理引擎选项
    parser.add_argument("--video_engine", choices=["ffmpeg", "moviepy", "auto"], default="auto",
                        help="选择视频处理引擎: ffmpeg, moviepy 或 auto (默认，自动选择)")
    # 添加不重新生成图片的选项
    parser.add_argument("--no_regenerate_images", action="store_true", help="不重新生成任何图片，保留现有图片")
    # 添加TTS服务类型参数
    parser.add_argument("--tts_service", choices=["voicevox", "openai_tts"], default="voicevox",
                        help="选择TTS服务类型: voicevox (默认) 或 openai_tts")
    # 添加语音预设参数
    parser.add_argument("--voice_preset", help="设置语音预设名称，如'storyteller', 'formal', 'cheerful'等，仅用于OpenAI TTS")
    # 添加语速参数
    parser.add_argument("--speed_scale", type=float, default=1.0, help="设置语音合成的语速 (例如 0.5 到 2.0)")
    # 添加 MJ 并发数参数
    parser.add_argument("--mj_concurrency", type=int, default=3, choices=[3, 10], help="设置 Midjourney 任务并发数 (默认 3)")
    # 添加会说话角色参数
    parser.add_argument("--talking_character", action="store_true", help="启用会说话的角色效果")
    parser.add_argument("--closed_mouth_image", help="设置闭嘴图片路径")
    parser.add_argument("--open_mouth_image", help="设置张嘴图片路径")
    parser.add_argument("--audio_sensitivity", type=float, default=0.04, help="设置音频灵敏度，控制嘴巴开合的阈值")
    args = parser.parse_args()

    # 打印参数信息，便于调试
    print("命令行参数:")
    print(f"  输入文件: {args.input_file}")
    print(f"  图像生成器: {args.image_generator}")
    print(f"  图像比例: {args.aspect_ratio}")
    print(f"  图像风格: {args.image_style}")
    print(f"  ComfyUI风格: {args.comfyui_style}")
    print(f"  字幕字体: {args.font_name}")
    print(f"  字体大小: {args.font_size}")
    print(f"  字体颜色: {args.font_color}")
    print(f"  背景不透明度: {args.bg_opacity}")
    print(f"  角色图片: {args.character_image}")
    print(f"  保留原始换行: {args.preserve_line_breaks}")
    print(f"  语音角色ID: {args.speaker_id}")
    print(f"  视频处理引擎: {args.video_engine}")
    print(f"  不重新生成图片: {args.no_regenerate_images}")
    print(f"  TTS服务类型: {args.tts_service}")
    print(f"  语音预设: {args.voice_preset}")
    print(f"  自定义风格: {args.custom_style}")
    print(f"  会说话角色: {args.talking_character}")
    print(f"  闭嘴图片: {args.closed_mouth_image}")
    print(f"  张嘴图片: {args.open_mouth_image}")
    print(f"  音频灵敏度: {args.audio_sensitivity}")

    # 设置图像生成器 (优先使用--image_generator)
    image_generator = args.image_generator
    if args.generator != "comfyui" and args.image_generator == "comfyui":
        image_generator = args.generator

    # 处理输入文件参数
    if args.input_file:
        input_file = args.input_file
    else:
        # 获取 input_texts 目录中的第一个 txt 文件
        input_dir = Path("input_texts")
        if not input_dir.exists():
            print(f"错误：输入目录 {input_dir} 不存在，正在创建...")
            input_dir.mkdir(parents=True)
            print("请在 input_texts 目录中放入文本文件后重试")
            sys.exit(1)
            
        txt_files = list(input_dir.glob("*.txt"))
        
        if not txt_files:
            print("错误：input_texts 目录中没有找到文本文件！")
            print("请在 input_texts 目录中放入文本文件后重试")
            sys.exit(1)
        
        # 使用找到的第一个文件
        input_file = str(txt_files[0])
    
    print(f"使用输入文件: {input_file}")
    
    # 处理函数已经包含文件存在性检查，直接调用
    result = process_story(
        input_file, 
        image_generator, 
        args.aspect_ratio, 
        args.image_style, 
        args.comfyui_style,
        args.font_name,
        args.font_size,
        args.font_color,
        args.bg_opacity,
        args.character_image,
        args.preserve_line_breaks,
        args.speaker_id,
        args.speed_scale,
        args.mj_concurrency,
        args.video_engine,
        args.no_regenerate_images,
        args.tts_service,
        args.voice_preset,
        args.custom_style,
        args.talking_character,
        args.closed_mouth_image,
        args.open_mouth_image,
        args.audio_sensitivity
    ) 
    
    if result is None or isinstance(result, str) and result.startswith("错误:"):
        sys.exit(1) 