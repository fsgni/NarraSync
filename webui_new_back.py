import gradio as gr
import os
import sys
import locale
import platform
import json
import subprocess # 添加这个以确保字幕添加可用
import shutil
import time
import random
import glob  # 添加glob模块导入
from pathlib import Path  # 添加Path导入

# 导入模块化组件
from ui_helpers import (
    list_input_files, list_character_images, get_available_fonts, 
    list_all_fonts, cleanup_output_directories, get_available_voices,
    list_title_background_images
)
from ui_components import (
    show_upload_panel, hide_upload_panel, update_video_dropdown, 
    update_ui_based_on_generator, create_main_ui, create_scene_management_ui
)
from video_processing import process_story
from scene_management import (
    upload_scene_image, collect_all_prompts, clear_modified_images,
    load_scene_details, refresh_scene_list as sm_refresh_scene_list, generate_scene_thumbnails,
    gallery_select
)
from scene_manager import SceneManager
from image_processor import ImageProcessor

# 添加SRT解析函数
def parse_srt_file(srt_path):
    """解析SRT字幕文件，提取时间轴信息
    
    Args:
        srt_path: SRT文件路径
        
    Returns:
        list: 字幕项列表，每项包含 {index, start_time, end_time, content}
    """
    subtitles = []
    
    try:
        with open(srt_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 分割为单独的字幕项
        subtitle_blocks = content.strip().split('\n\n')
        
        for block in subtitle_blocks:
            lines = block.strip().split('\n')
            if len(lines) >= 3:  # 至少需要索引、时间轴和内容
                try:
                    # 解析索引
                    index = int(lines[0])
                    
                    # 解析时间轴 (格式: 00:00:20,000 --> 00:00:25,000)
                    time_line = lines[1]
                    times = time_line.split(' --> ')
                    start_time = parse_srt_time(times[0])
                    end_time = parse_srt_time(times[1])
                    
                    # 提取内容
                    subtitle_content = '\n'.join(lines[2:])
                    
                    # 添加到列表
                    subtitles.append({
                        'index': index,
                        'start_time': start_time,
                        'end_time': end_time,
                        'content': subtitle_content
                    })
                except Exception as e:
                    print(f"解析字幕块时出错: {e}, 块内容: {block}")
                    continue
        
        print(f"成功解析字幕文件，共有 {len(subtitles)} 项字幕")
        return subtitles
    except Exception as e:
        print(f"解析SRT文件时出错: {e}")
        return []

def parse_srt_time(time_str):
    """将SRT时间格式转换为秒数
    
    Args:
        time_str: SRT时间字符串 (00:00:20,000)
        
    Returns:
        float: 秒数
    """
    # 替换逗号为点
    time_str = time_str.replace(',', '.')
    
    # 分割时间部分
    h, m, s = time_str.split(':')
    
    # 转换为秒
    total_seconds = int(h) * 3600 + int(m) * 60 + float(s)
    
    return total_seconds

# 直接从add_subtitles导入函数，避免在函数内部导入
from add_subtitles import add_subtitles

# 设置系统编码为UTF-8，解决Windows命令行的编码问题
if sys.stdout.encoding != 'utf-8':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    elif hasattr(sys.stdout, 'buffer'):
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='backslashreplace')

# 初始化全局实例
scene_manager = SceneManager()
image_processor = ImageProcessor()

# 添加一个直接使用FFmpeg添加字幕的函数
def add_subtitles_direct_ffmpeg(video_file, srt_file, output_file, font_name="Arial"):
    """直接使用FFmpeg命令添加字幕，作为备选方案
    
    Args:
        video_file: 输入视频文件
        srt_file: SRT字幕文件
        output_file: 输出视频文件
        font_name: 字体名称
        
    Returns:
        bool: 是否成功
    """
    try:
        # 构建一个简单的FFmpeg命令来添加字幕
        cmd = [
            'ffmpeg', '-y',
            '-i', video_file,
            '-vf', f"subtitles={srt_file}:force_style='FontName={font_name},FontSize=24'",
            '-c:a', 'copy',
            output_file
        ]
        
        # 执行命令
        print(f"执行FFmpeg命令: {' '.join(cmd)}")
        subprocess.run(cmd, check=True)
        
        # 检查输出文件是否存在
        if os.path.exists(output_file):
            return True
        return False
    except Exception as e:
        print(f"直接FFmpeg添加字幕失败: {e}")
        return False

# 添加新的只重新合成视频的函数
def recompose_video_only(video_engine, character_image=None, font_name=None, font_size=None, font_color=None, bg_opacity=None, talking_character=None, closed_mouth_image=None, open_mouth_image=None, audio_sensitivity=None):
    """只重新合成视频，保留现有的音频和图片资源
    
    Args:
        video_engine: 视频处理引擎
        character_image: 角色图片
        font_name, font_size, font_color, bg_opacity: 字幕参数
        talking_character: 说话角色
        closed_mouth_image: 闭嘴图片
        open_mouth_image: 张嘴图片
        audio_sensitivity: 音频敏感度
        
    Returns:
        tuple: (状态信息, 视频路径)
    """
    import os
    import time
    import glob
    from pathlib import Path
    from video_processor import VideoProcessor
    from config import config
    from errors import get_logger
    
    logger = get_logger("recompose")
    
    try:
        output = "开始重新合成视频...\n"
        
        # 添加调试信息：列出当前视频文件
        print("\n=== 当前视频文件状态 ===")
        video_files = [f for f in os.listdir("output") if f.endswith(".mp4")]
        for file in video_files:
            file_path = os.path.join("output", file)
            file_size_mb = os.path.getsize(file_path) / 1024 / 1024
            file_mod_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(os.path.getmtime(file_path)))
            print(f"文件: {file}, 大小: {file_size_mb:.2f} MB, 修改时间: {file_mod_time}")
        print("=== 视频文件状态结束 ===\n")
        
        # 显示合成参数
        print("\n=== 重新合成参数 ===")
        print(f"视频引擎: {video_engine}")
        print(f"角色图片: {character_image}")
        print(f"说话角色启用: {talking_character}")
        if talking_character:
            print(f"闭嘴图片: {closed_mouth_image}")
            print(f"张嘴图片: {open_mouth_image}")
            print(f"音频敏感度: {audio_sensitivity}")
        print(f"字幕字体: {font_name}")
        print(f"字体大小: {font_size}")
        print(f"字体颜色: {font_color}")
        print(f"背景透明度: {bg_opacity}")
        print("=== 参数信息结束 ===\n")
        
        # 检查必要的文件
        key_scenes_file = "output/key_scenes.json"
        base_video = "output/base_video.mp4"
        
        if not os.path.exists(key_scenes_file):
            return "错误：找不到场景信息文件，请先生成完整视频", None
            
        if not os.path.exists(base_video):
            return "错误：找不到基础视频，请先生成完整视频", None
            
        # 获取输入文件名，用于最终输出文件名
        input_files = glob.glob("input_texts/*.txt")
        input_file_stem = "webui_input"  # 默认名称
        if input_files:
            # 使用最近修改的输入文件
            latest_input = max(input_files, key=os.path.getmtime)
            input_file_stem = Path(latest_input).stem
        
        # 使用正确的字幕文件路径 - 基于输入文件名
        srt_file = f"output/{input_file_stem}.srt"
        
        # 设置输出文件路径 - 使用固定文件名覆盖原有文件
        final_video = "output/final_video.mp4"
        final_video_with_char = "output/final_video_with_char.mp4"
        output_video_final = f"output/{input_file_stem}_final.mp4"
        
        # 初始化视频处理器
        processor = VideoProcessor(engine=video_engine)
        output += f"使用 {processor.engine.upper()} 引擎处理视频\n"
        
        # 1. 使用现有基础视频
        output += "使用现有基础视频...\n"
        
        # 2. 创建场景视频
        output += "创建场景视频...\n"
        # 直接覆盖原来的final_video.mp4
        processor.create_video_with_scenes(key_scenes_file, base_video, final_video)
        
        # 3. 如果提供了角色图片，添加角色图片
        current_video = final_video
        if character_image and character_image != "不使用角色图片" and character_image != "没有找到图片文件。请在input_images目录添加图片。":
            output += "添加角色图片...\n"
            
            # 删除旧的会说话角色视频，确保重新生成
            if os.path.exists("output/temp_video_with_character.mp4"):
                print("删除旧的会说话角色视频，确保使用最新图片...")
                try:
                    os.remove("output/temp_video_with_character.mp4")
                    print("旧的会说话角色视频已删除")
                except Exception as e:
                    print(f"无法删除旧的视频文件: {e}")
            
            # 使用新生成的场景视频添加角色
            character_image_path = os.path.join("input_images", character_image)
            
            # 判断是否启用会说话的角色
            if talking_character and closed_mouth_image and open_mouth_image and closed_mouth_image != "不使用角色图片" and open_mouth_image != "不使用角色图片":
                try:
                    output += "使用会说话的角色效果...\n"
                    print("创建新的会说话角色视频，使用最新场景...")
                    
                    # 准备闭嘴和张嘴图片路径
                    closed_mouth_path = os.path.join("input_images", closed_mouth_image)
                    open_mouth_path = os.path.join("input_images", open_mouth_image)
                    
                    # 检查图片是否存在
                    if not os.path.exists(closed_mouth_path) or not os.path.exists(open_mouth_path):
                        output += f"警告: 闭嘴或张嘴图片不存在，将使用普通角色图片\n"
                        # 使用普通角色图片模式
                        from add_character_image import add_character_image_to_video
                        
                        # 创建临时视频文件
                        final_video_with_char = "output/final_video_with_char.mp4"
                        
                        success = add_character_image_to_video(current_video, character_image_path, final_video_with_char)
                    else:
                        # 导入会说话角色模块
                        from add_talking_character import create_talking_character_video
                        
                        # 创建临时视频文件
                        final_video_with_char = "output/temp_video_with_character.mp4"
                        
                        # 添加会说话的角色
                        success = create_talking_character_video(
                            current_video, 
                            closed_mouth_path, 
                            open_mouth_path, 
                            final_video_with_char,
                            threshold=audio_sensitivity
                        )
                    
                    if success:
                        output += f"成功添加会说话的角色图片到视频\n"
                        # 使用带有角色图片的视频作为最终视频
                        current_video = final_video_with_char
                    else:
                        output += f"添加会说话的角色图片失败，将使用原始视频继续处理\n"
                except Exception as e:
                    output += f"添加会说话角色图片过程中出错: {str(e)}\n"
                    import traceback
                    error_details = traceback.format_exc()
                    logger.error(f"添加会说话角色图片失败: {str(e)}\n{error_details}")
                    output += "将使用原始视频继续处理\n"
            else:
                # 使用普通角色图片
                try:
                    from add_character_image import add_character_image_to_video
                    
                    # 创建临时视频文件
                    final_video_with_char = "output/final_video_with_char.mp4"
                    
                    success = add_character_image_to_video(current_video, character_image_path, final_video_with_char)
                    if success:
                        output += f"成功添加角色图片到视频\n"
                        current_video = final_video_with_char
                    else:
                        output += f"添加角色图片失败，将使用原始视频继续处理\n"
                except Exception as e:
                    output += f"添加角色图片过程中出错: {e}\n"
                    import traceback
                    error_details = traceback.format_exc()
                    logger.error(f"添加角色图片失败: {str(e)}\n{error_details}")
                    output += "将使用原始视频继续处理\n"
        
        # 4. 添加字幕
        if os.path.exists(srt_file):
            print(f"准备添加字幕文件: {srt_file}")
            # 准备字幕参数
            font_name = font_name if font_name else "Arial"
            font_size = font_size if font_size else 24
            font_color = font_color.replace('#', '') if font_color else "FFFFFF"
            bg_opacity = bg_opacity if bg_opacity is not None else 0.5
            
            print(f"字幕参数: 字体={font_name}, 大小={font_size}, 颜色={font_color}, 背景透明度={bg_opacity}")
            
            try:
                print("尝试使用add_subtitles函数添加字幕...")
                # 检查当前文件和字幕文件是否存在
                if not os.path.exists(current_video):
                    raise FileNotFoundError(f"当前视频文件不存在: {current_video}")
                if not os.path.exists(srt_file):
                    raise FileNotFoundError(f"字幕文件不存在: {srt_file}")
                
                # 调用add_subtitles函数
                subtitle_output = os.path.join("output", "final_video_with_subtitle.mp4")
                add_subtitles(
                    current_video, 
                    srt_file, 
                    subtitle_output,
                    font_name=font_name,
                    font_size=font_size,
                    font_color=font_color,
                    bg_opacity=float(bg_opacity)
                )
                
                # 检查输出文件是否存在
                if os.path.exists(subtitle_output) and os.path.getsize(subtitle_output) > 0:
                    current_video = subtitle_output
                    print(f"字幕添加成功，输出文件: {current_video}")
                else:
                    raise FileNotFoundError(f"添加字幕后的输出文件不存在或为空: {subtitle_output}")
                    
            except Exception as e:
                print(f"使用add_subtitles函数添加字幕失败: {e}")
                print("尝试使用备用方法(直接FFmpeg)添加字幕...")
                
                subtitle_output = os.path.join("output", "final_video_with_subtitle.mp4")
                if add_subtitles_direct_ffmpeg(current_video, srt_file, subtitle_output, font_name):
                    current_video = subtitle_output
                    print(f"使用备用方法添加字幕成功，输出文件: {current_video}")
                else:
                    print(f"所有方法添加字幕失败！将继续使用无字幕视频: {current_video}")
        else:
            print(f"警告：找不到字幕文件: {srt_file}，将创建无字幕的最终视频。")
        
        # 复制当前视频到最终输出文件
        final_output = output_video_final  # 使用正确的最终输出文件名 webui_input_final.mp4
        print(f"正在将 {current_video} 复制到 {final_output}")
        output += f"正在将 {current_video} 复制到 {final_output}\n"
        shutil.copy2(current_video, final_output)
        print(f"最终视频已创建: {final_output}")
        
        # 返回视频路径
        return final_output
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        logger.error(f"重新合成视频失败: {str(e)}\n{error_details}")
        return None

# 重新生成指定场景的图片（带重试功能）
def on_regenerate_scene_image_with_retry(scene_id, image_generator_type, aspect_ratio, image_style, custom_style, comfyui_style, current_scenes, prompt):
    """重新生成指定场景的图片（带敏感词自动处理功能）
    
    Args:
        scene_id: 场景ID
        image_generator_type: 图像生成器类型
        aspect_ratio: 图像比例
        image_style: 图像风格
        custom_style: 自定义风格
        comfyui_style: ComfyUI风格
        current_scenes: 当前场景列表
        prompt: 用户修改后的提示词
        
    Returns:
        str: 操作状态信息
    """
    if not current_scenes:
        return "错误：没有有效的场景数据可以处理"
        
    try:
        # 确保场景数据是有效的列表
        scenes = json.loads(current_scenes) if isinstance(current_scenes, str) else current_scenes
        
        # 更新场景提示词
        scene_idx = int(scene_id) - 1
        if 0 <= scene_idx < len(scenes):
            scenes[scene_idx]["prompt"] = prompt
        
        # 调用带重试的重新生成函数
        from scene_management import regenerate_scene_image_with_retry
        status_code, message, image_file = regenerate_scene_image_with_retry(
            scene_id, scenes, 
            image_generator_type, aspect_ratio, 
            image_style, custom_style, comfyui_style,
            max_retries=3  # 最多重试3次
        )
        
        # 处理返回结果
        if status_code == 200:
            # 更新场景数据到文件
            from scene_manager import SceneManager
            scene_manager = SceneManager()
            scene_manager.save_scenes(scenes)
            return f"成功：{message}，图像文件: {image_file}"
        else:
            return f"错误：{message}"
    except Exception as e:
        import traceback
        print(f"重新生成场景图像出错: {e}")
        print(traceback.format_exc())
        return f"错误：{str(e)}"

# 修改add_scene_title函数，添加背景图片支持
def add_scene_title(title_text, start_scene, end_scene, title_color, title_size, position_x, position_y, background_image, all_titles, title_font="默认"):
    """添加或更新场景标题
    
    Args:
        title_text: 标题文本
        start_scene: 起始场景ID
        end_scene: 结束场景ID
        title_color: 字体颜色
        title_size: 字体大小
        position_x: 左边距
        position_y: 上边距
        background_image: 背景图片文件
        all_titles: 当前的所有标题数据
        title_font: 字体名称
        
    Returns:
        tuple: (更新后的标题数据, 状态信息)
    """
    if not title_text or not title_text.strip():
        return all_titles, "错误：标题文本不能为空"
    
    try:
        # 转换为整数
        start_scene = int(start_scene)
        end_scene = int(end_scene)
        
        # 验证场景ID范围
        if start_scene < 1:
            return all_titles, "错误：起始场景ID必须大于等于1"
        if end_scene < start_scene:
            return all_titles, "错误：结束场景ID必须大于等于起始场景ID"
        
        # 处理背景图片
        background_file = None
        if background_image is not None and background_image != "":
            # 确保title_backgrounds目录存在
            title_bg_dir = "input_images/title_backgrounds"
            os.makedirs(title_bg_dir, exist_ok=True)
            
            # 检查背景图片是字符串路径还是文件对象
            if isinstance(background_image, str):
                # 直接复制文件
                file_name = f"title_bg_{int(time.time())}_{os.path.basename(background_image)}"
                background_path = os.path.join(title_bg_dir, file_name)
                shutil.copy2(background_image, background_path)
                background_file = file_name
                print(f"背景图片已复制到: {background_path}")
            elif hasattr(background_image, 'name'):
                # 处理File组件返回的文件路径
                file_name = f"title_bg_{int(time.time())}_{os.path.basename(background_image.name)}"
                background_path = os.path.join(title_bg_dir, file_name)
                
                # 使用shutil复制文件
                try:
                    shutil.copy2(background_image.name, background_path)
                    background_file = file_name
                    print(f"背景图片已复制到: {background_path}")
                except Exception as e:
                    print(f"复制背景图片时出错: {e}")
                    return all_titles, f"错误：复制背景图片失败 - {str(e)}"
        
        # 准备新标题数据
        new_title = {
            "text": title_text.strip(),
            "start_scene": start_scene,
            "end_scene": end_scene,
            "color": title_color.lstrip('#'),  # 移除可能存在的#前缀
            "size": int(title_size),
            "position_x": int(position_x),
            "position_y": int(position_y),
            "background_image": background_file,  # 添加背景图片字段
            "font": title_font,  # 添加字体字段
            "id": f"title_{len(all_titles) + 1}_{int(time.time())}"  # 生成唯一ID
        }
        
        # 检查是否有重叠的标题范围，如果有则更新
        updated = False
        for i, title in enumerate(all_titles):
            # 如果有完全重叠的范围，直接替换
            if title["start_scene"] == start_scene and title["end_scene"] == end_scene:
                all_titles[i] = new_title
                updated = True
                break
        
        # 如果没有重叠，添加新标题
        if not updated:
            all_titles.append(new_title)
        
        # 按起始场景ID排序
        all_titles.sort(key=lambda x: x["start_scene"])
        
        return all_titles, f"成功{'更新' if updated else '添加'}标题：'{title_text}' (场景 {start_scene}-{end_scene})"
    
    except Exception as e:
        import traceback
        print(f"添加场景标题时出错: {e}")
        print(traceback.format_exc())
        return all_titles, f"错误：{str(e)}"

# 添加一个删除标题的函数
def delete_scene_title(title_index, all_titles):
    """删除指定索引的场景标题
    
    Args:
        title_index: 要删除的标题索引（从1开始）
        all_titles: 当前的所有标题数据
        
    Returns:
        tuple: (更新后的标题数据, 状态信息)
    """
    try:
        # 转换为0-based索引
        index = int(title_index) - 1
        
        # 检查索引是否有效
        if index < 0 or index >= len(all_titles):
            return all_titles, f"错误：无效的标题索引 {title_index}"
        
        # 获取要删除的标题文本
        title_text = all_titles[index]["text"]
        
        # 删除标题
        del all_titles[index]
        
        return all_titles, f"成功删除标题：'{title_text}'"
    
    except Exception as e:
        import traceback
        print(f"删除场景标题时出错: {e}")
        print(traceback.format_exc())
        return all_titles, f"错误：{str(e)}"

# 修改预览函数，添加背景图片显示
def preview_scene_titles(all_titles):
    """生成所有场景标题的HTML预览
    
    Args:
        all_titles: 所有标题数据
        
    Returns:
        str: HTML预览代码
    """
    if not all_titles:
        return "<p>暂无标题</p>"
    
    html = "<div style='max-height: 300px; overflow-y: auto;'>"
    html += "<table style='width: 100%; border-collapse: collapse;'>"
    html += "<tr><th>ID</th><th>标题文本</th><th>场景范围</th><th>样式</th><th>字体</th><th>背景图片</th></tr>"
    
    for i, title in enumerate(all_titles):
        # 生成标题样式预览
        style_preview = f"<span style='color: #{title['color']}; font-size: {min(title['size'], 24)}px;'>{title['text']}</span>"
        
        # 获取字体信息
        font_info = title.get("font", "默认")
        
        # 生成背景图片预览
        bg_preview = "无"
        if title.get("background_image"):
            bg_path = os.path.join("input_images/title_backgrounds", title["background_image"])
            if os.path.exists(bg_path):
                bg_preview = f"<img src='file={bg_path}' style='max-height: 30px; max-width: 60px;'>"
        
        html += f"<tr style='border-bottom: 1px solid #ccc;'>"
        html += f"<td>{i+1}</td>"
        html += f"<td>{title['text']}</td>"
        html += f"<td>{title['start_scene']} - {title['end_scene']}</td>"
        html += f"<td>{style_preview}</td>"
        html += f"<td>{font_info}</td>"
        html += f"<td>{bg_preview}</td>"
        html += "</tr>"
    
    html += "</table></div>"
    
    return html

# 添加从文本标题导入到标题管理器的函数
def import_text_scene_titles(all_titles):
    """从文本阶段提取的标题导入到标题管理器，并基于字幕时间轴决定位置
    
    Args:
        all_titles: 当前的所有标题数据
        
    Returns:
        tuple: (更新后的标题数据, 状态信息)
    """
    try:
        # 检查是否存在场景标题文件
        if not os.path.exists("output/scene_titles.json"):
            return all_titles, "未找到场景标题文件，请确认已在文本中添加[标题:XXX]标记"
        
        # 获取输入文件名
        input_files = glob.glob("input_texts/*.txt")
        input_file_stem = "webui_input"  # 默认名称
        if input_files:
            # 使用最近修改的输入文件
            latest_input = max(input_files, key=os.path.getmtime)
            input_file_stem = Path(latest_input).stem
        
        # 字幕文件路径
        srt_file = f"output/{input_file_stem}.srt"
        
        # 解析字幕文件
        subtitles = []
        if os.path.exists(srt_file):
            subtitles = parse_srt_file(srt_file)
            if subtitles:
                print(f"成功解析字幕文件，共有 {len(subtitles)} 项字幕")
            else:
                print(f"字幕文件解析结果为空，将回退到场景匹配模式")
        else:
            print(f"字幕文件不存在: {srt_file}，将回退到场景匹配模式")
            
        # 读取场景标题
        with open("output/scene_titles.json", "r", encoding="utf-8") as f:
            text_titles = json.load(f)
        
        if not text_titles:
            return all_titles, "场景标题文件为空，未找到[标题:XXX]标记"
            
        # 读取场景信息（用于备选匹配）
        scenes = []
        if os.path.exists("output/key_scenes.json"):
            with open("output/key_scenes.json", "r", encoding="utf-8") as f:
                scenes = json.load(f)
        
        # 获取标题背景图片列表
        from ui_helpers import list_title_background_images
        background_images = list_title_background_images()
        
        # 设置KEIFONT作为默认字体
        subtitle_font = "KEIFONT"  # 直接指定KEIFONT为默认字体
        
        # 检查字体是否存在
        font_exists = False
        from ui_helpers import get_available_fonts
        available_fonts = get_available_fonts()
        
        # 检查KEIFONT是否在可用字体列表中
        if subtitle_font in available_fonts:
            font_exists = True
            print(f"使用KEIFONT字体: {subtitle_font}")
        else:
            # 检查fonts目录中是否有这个字体文件
            keifont_paths = [
                "fonts/KEIFONT.TTF",
                "fonts/keifont.ttf",
                "fonts/KEIFONT.ttf",
                "fonts/Keifont.ttf"
            ]
            
            font_file_exists = False
            for path in keifont_paths:
                if os.path.exists(path):
                    font_file_exists = True
                    print(f"找到KEIFONT字体文件: {path}")
                    break
            
            if not font_file_exists:
                print(f"警告: KEIFONT字体文件未找到，将使用默认字体")
                subtitle_font = "默认"
        
        # 设置更大的默认字体大小
        default_font_size = 52  # 默认字体大小增加到52
        
        # 将文本标题与字幕或场景匹配
        imported_count = 0
        subtitle_matches = 0
        scene_matches = 0
        new_titles = []  # 使用新列表存储所有新导入的标题
        
        for title in text_titles:
            title_text = title.get("text", "")
            title_pos = title.get("position", 0)
            
            # 随机选择背景图片
            background_file = None
            if background_images:
                import random
                background_file = random.choice(background_images)
                print(f"为标题 '{title_text}' 选择了背景图片: {background_file}")
            
            # 基于字幕内容搜索最匹配的时间点
            matched_by_subtitle = False
            
            if subtitles:
                # 找出包含或最接近标题内容的字幕
                best_match = None
                best_score = 0.3  # 最低匹配阈值
                
                # 清理标题文本用于匹配（移除标题标记等）
                clean_title = title_text.replace("[标题:", "").replace("]", "").strip()
                
                for sub in subtitles:
                    # 直接包含匹配
                    if clean_title.lower() in sub['content'].lower():
                        best_match = sub
                        best_score = 1.0
                        print(f"标题'{clean_title}'完全匹配到字幕: {sub['content']}")
                        break
                    
                    # 计算单词重叠率
                    title_words = set(clean_title.lower().split())
                    sub_words = set(sub['content'].lower().split())
                    
                    if title_words and sub_words:
                        common_words = title_words & sub_words
                        score = len(common_words) / len(title_words)
                        
                        if score > best_score:
                            best_score = score
                            best_match = sub
                            print(f"标题'{clean_title}'与字幕匹配度: {score:.2f}, 内容: {sub['content']}")
                
                if best_match:
                    # 使用匹配字幕的时间
                    start_time = best_match['start_time']
                    end_time = best_match['end_time']
                    
                    # 增加显示持续时间（如果太短）
                    if end_time - start_time < 3.0:
                        end_time = start_time + 3.0
                    
                    print(f"标题 '{clean_title}' 匹配到字幕，显示时间: {start_time:.2f}s - {end_time:.2f}s")
                    
                    # 尝试找出最接近的场景（仅用于UI显示）
                    start_scene = 1
                    end_scene = 1
                    if scenes:
                        for i, scene in enumerate(scenes):
                            scene_start = scene.get("start_time", 0)
                            scene_end = scene_start + scene.get("duration", 0)
                            if scene_start <= start_time < scene_end:
                                start_scene = i + 1
                            if scene_start <= end_time < scene_end:
                                end_scene = i + 1
                    
                    # 创建新标题
                    new_title = {
                        "text": clean_title,
                        "exact_start_time": start_time,  # 存储精确时间
                        "exact_end_time": end_time,
                        "start_scene": start_scene,  # 依然保留场景ID以兼容UI
                        "end_scene": end_scene,
                        "color": "FFFFFF",  # 默认白色
                        "size": default_font_size,  # 使用更大的默认字体大小
                        "position_x": 50,  # 默认居中位置
                        "position_y": 50,
                        "background_image": background_file,
                        "font": subtitle_font,  # 使用字幕相同的字体
                        "id": f"title_{len(all_titles) + imported_count + 1}_{int(time.time())}"
                    }
                    
                    # 添加到新标题列表
                    new_titles.append(new_title)
                    imported_count += 1
                    subtitle_matches += 1
                    matched_by_subtitle = True
            
            # 如果没有通过字幕匹配，回退到场景匹配模式
            if not matched_by_subtitle:
                # 找到最近的场景（原有逻辑）
                closest_scene = 1  # 默认第一个场景
                min_distance = float('inf')
                
                for i, scene in enumerate(scenes):
                    scene_pos = scene.get("position", 0) if hasattr(scene, "position") else i
                    distance = abs(title_pos - scene_pos) if hasattr(title, "position") else abs(i - 0)
                    if distance < min_distance:
                        min_distance = distance
                        closest_scene = i + 1  # 场景ID从1开始
                
                # 获取场景时间
                start_time = 0
                end_time = 5  # 默认5秒
                if scenes and closest_scene <= len(scenes):
                    scene = scenes[closest_scene-1]
                    start_time = scene.get("start_time", 0)
                    end_time = start_time + scene.get("duration", 5)
                
                # 创建新标题
                new_title = {
                    "text": title_text.replace("[标题:", "").replace("]", "").strip(),
                    "exact_start_time": start_time,  # 存储场景时间为精确时间
                    "exact_end_time": end_time,
                    "start_scene": closest_scene,
                    "end_scene": closest_scene,  # 默认仅应用于单个场景
                    "color": "FFFFFF",  # 默认白色
                    "size": default_font_size,  # 使用更大的默认字体大小
                    "position_x": 50,  # 默认居中位置
                    "position_y": 50,
                    "background_image": background_file,
                    "font": subtitle_font,  # 使用字幕相同的字体
                    "id": f"title_{len(all_titles) + imported_count + 1}_{int(time.time())}"
                }
                
                # 添加到新标题列表
                new_titles.append(new_title)
                imported_count += 1
                scene_matches += 1
                
        # 按开始时间排序新标题
        new_titles.sort(key=lambda x: x.get("exact_start_time", 0))
        
        # 延长每个标题的显示时间直到下一个标题出现
        for i in range(len(new_titles) - 1):
            current_title = new_titles[i]
            next_title = new_titles[i + 1]
            
            # 将当前标题的结束时间设置为下一个标题的开始时间
            current_title["exact_end_time"] = next_title["exact_start_time"]
            print(f"延长标题 '{current_title['text']}' 的显示时间至: {current_title['exact_start_time']:.2f}s - {current_title['exact_end_time']:.2f}s")
        
        # 延长最后一个标题到视频结束（尝试获取视频总长度）
        if new_titles and scenes:
            last_title = new_titles[-1]
            # 尝试找出视频的结束时间
            video_end_time = 0
            for scene in scenes:
                end = scene.get("start_time", 0) + scene.get("duration", 0)
                if end > video_end_time:
                    video_end_time = end
            
            if video_end_time > 0:
                last_title["exact_end_time"] = video_end_time
                print(f"延长最后一个标题 '{last_title['text']}' 的显示时间至视频结束: {last_title['exact_start_time']:.2f}s - {video_end_time:.2f}s")
        
        # 将新标题添加到当前标题列表
        all_titles.extend(new_titles)
        
        return all_titles, f"成功导入{imported_count}个标题（使用字幕字体，字体大小{default_font_size}）并设置为连续显示"
    
    except Exception as e:
        import traceback
        print(f"导入场景标题时出错: {e}")
        print(traceback.format_exc())
        return all_titles, f"错误：{str(e)}"

# 获取场景时间信息
def get_scene_timestamps(key_scenes_file=None):
    """获取场景的时间戳信息
    
    Args:
        key_scenes_file: 场景信息文件路径，默认为output/key_scenes.json
        
    Returns:
        list: 场景时间戳列表，每个元素为(开始时间, 结束时间)，单位为秒
    """
    if key_scenes_file is None:
        key_scenes_file = "output/key_scenes.json"
    
    if not os.path.exists(key_scenes_file):
        print(f"场景信息文件不存在: {key_scenes_file}")
        return []
    
    try:
        with open(key_scenes_file, "r", encoding="utf-8") as f:
            scenes = json.load(f)
        
        # 从场景中提取时间信息
        timestamps = []
        for scene in scenes:
            start_time = scene.get("start_time", 0)
            duration = scene.get("duration", 5)  # 默认5秒
            end_time = start_time + duration
            timestamps.append((start_time, end_time))
        
        # 如果没有时间信息，使用预估值
        if not timestamps or all(t[0] == 0 for t in timestamps):
            print("场景文件中没有时间信息，使用预估时间")
            # 使用video_duration.py获取视频时长和场景数
            from video_processor import VideoProcessor
            processor = VideoProcessor()
            video_path = "output/webui_input_final.mp4"
            if os.path.exists(video_path):
                video_duration = processor.get_video_duration(video_path)
                scene_count = len(scenes)
                # 平均分配时长
                if scene_count > 0:
                    scene_duration = video_duration / scene_count
                    timestamps = [(i * scene_duration, (i + 1) * scene_duration) for i in range(scene_count)]
        
        return timestamps
    
    except Exception as e:
        import traceback
        print(f"获取场景时间戳时出错: {e}")
        print(traceback.format_exc())
        return []

# 修改Python脚本中的create_title_image函数，添加背景图片支持
# 在apply_scene_titles_to_video函数中修改脚本部分

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

# 创建Gradio界面
with gr.Blocks(title="故事视频生成器", theme=gr.themes.Soft()) as demo:
    # 创建共享的状态变量
    current_output_video = gr.State(value=None)
    
    with gr.Tabs():
        # 一键生成选项卡
        with gr.TabItem("一键生成"):
            gr.Markdown("# 故事视频生成器")
            gr.Markdown("输入文本或选择已有文件，一键生成视频。")
            
            # 创建主UI组件
            main_ui = create_main_ui()
            
            # 获取UI组件
            text_input = main_ui["text_input"]
            file_dropdown = main_ui["file_dropdown"]
            refresh_button = main_ui["refresh_button"]
            image_generator = main_ui["image_generator"]
            aspect_ratio = main_ui["aspect_ratio"]
            comfyui_style = main_ui["comfyui_style"]
            image_style_type = main_ui["image_style_type"]
            custom_style = main_ui["custom_style"]
            font_name = main_ui["font_name"]
            refresh_fonts_button = main_ui["refresh_fonts_button"]
            font_size = main_ui["font_size"]
            font_color = main_ui["font_color"]
            bg_opacity = main_ui["bg_opacity"]
            show_all_fonts_button = main_ui["show_all_fonts_button"]
            all_fonts_output = main_ui["all_fonts_output"]
            voice_dropdown = main_ui["voice_dropdown"]
            preserve_line_breaks = main_ui["preserve_line_breaks"]
            character_image = main_ui["character_image"]
            refresh_character_button = main_ui["refresh_character_button"]
            video_engine = main_ui["video_engine"]
            video_resolution = main_ui["video_resolution"]
            one_click_process_button = main_ui["one_click_process_button"]
            output_text = main_ui["output_text"]
            output_video = main_ui["output_video"]
            
            # 控制说话角色选项显示
            talking_character = main_ui["talking_character"]
            talking_character_options = main_ui["talking_character_options"]
            talking_sensitivity = main_ui["talking_sensitivity"]
            closed_mouth_image = main_ui["closed_mouth_image"]
            open_mouth_image = main_ui["open_mouth_image"]
            audio_sensitivity = main_ui["audio_sensitivity"]
            
        # 场景管理选项卡
        with gr.TabItem("场景管理"):
            # gr.Markdown("# 场景管理")
            # gr.Markdown("在这里您可以管理视频场景，修改提示词，重新生成或上传图片。")
            
            # # 添加使用说明
            # gr.Markdown("""
            # ### 使用说明
            
            # 1. 首先点击"刷新场景列表"按钮加载场景
            # 2. **使用滑块选择想要编辑的场景**（推荐方式）
            # 3. 修改提示词后，点击"重新生成图片"按钮
            # 4. 或者点击"上传图片"按钮上传自定义图片
            # 5. 完成所有编辑后，点击"重新合成视频"生成最终视频
            # """, elem_id="scene_management_instructions")
            
            # 创建场景管理UI组件
            scene_ui = create_scene_management_ui()
            
            # 获取场景管理UI组件
            refresh_scenes_button = scene_ui["refresh_scenes_button"]
            scene_info = scene_ui["scene_info"]
            scene_count_label = scene_ui["scene_count_label"]
            scene_thumbnails = scene_ui["scene_thumbnails"]
            scene_gallery = scene_ui["scene_gallery"]
            scene_slider = scene_ui["scene_slider"]
            scene_editor = scene_ui["scene_editor"]
            current_scene_content = scene_ui["current_scene_content"]
            current_scene_prompt = scene_ui["current_scene_prompt"]
            current_scene_image = scene_ui["current_scene_image"]
            regenerate_image_button = scene_ui["regenerate_image_button"]
            upload_image_button = scene_ui["upload_image_button"]
            upload_image_panel = scene_ui["upload_image_panel"]
            scene_upload_image = scene_ui["scene_upload_image"]
            upload_confirm_button = scene_ui["upload_confirm_button"]
            upload_cancel_button = scene_ui["upload_cancel_button"]
            scene_controls = scene_ui["scene_controls"]
            scene_index = scene_ui["scene_index"]
            scene_prompt = scene_ui["scene_prompt"]
            all_prompts = scene_ui["all_prompts"]
            scene_video_preview = scene_ui["scene_video_preview"]
            
            # 重新合成视频和清除修改按钮
            with gr.Row():
                recompose_video_button = gr.Button("重新合成视频", variant="primary", visible=True)
                clear_modifications_button = gr.Button("重新生成所有图片", variant="secondary", visible=True)
            
            # 不重新生成图片选项（隐藏）
            no_regenerate_images = gr.Checkbox(
                label="不重新生成任何图片",
                value=True,
                visible=False
            )
            
            # 场景缩略图显示
            scene_thumbnails = gr.HTML(visible=True)
            
            # 添加标题管理部分
            with gr.Accordion("场景标题管理", open=False):
                gr.Markdown("### 添加场景标题")
                gr.Markdown("为指定场景范围添加标题，标题将显示在视频上。可选择添加背景图片来增强视觉效果。")
                
                # 添加导入说明
                gr.Markdown("**使用文本标题标记**：在文本中使用 `[标题:标题文本]` 格式添加标题，系统会自动提取并关联到最近的场景。")
                
                # 添加导入按钮
                with gr.Row():
                    import_text_titles_button = gr.Button("导入文本标题", variant="secondary")
                    gr.Markdown("将自动从 `input_images/title_backgrounds` 目录随机选择背景图片应用到导入的标题。")
                
                with gr.Row():
                    title_text = gr.Textbox(label="标题文本", placeholder="输入要显示的标题文本")
                    title_color = gr.ColorPicker(label="字体颜色", value="#FFFFFF")
                
                with gr.Row():
                    start_scene = gr.Number(label="起始场景ID", value=1, precision=0)
                    end_scene = gr.Number(label="结束场景ID", value=1, precision=0)
                
                with gr.Row():
                    # 添加字体选择下拉框
                    title_font = gr.Dropdown(label="字体", choices=get_available_fonts(), value="默认")
                    title_size = gr.Slider(minimum=12, maximum=72, value=36, step=1, label="字体大小")
                
                with gr.Row():
                    title_position_x = gr.Slider(minimum=10, maximum=200, value=20, step=1, label="左边距 (像素)")
                    title_position_y = gr.Slider(minimum=10, maximum=200, value=30, step=1, label="上边距 (像素)")
                
                # 添加刷新字体按钮
                with gr.Row():
                    refresh_title_font_button = gr.Button("刷新字体列表")
                
                # 添加背景图片上传组件
                with gr.Row():
                    title_background = gr.File(label="标题背景图片 (可选)", file_types=["image"], type="filepath")
                    gr.Markdown("上传背景图片后，标题将显示在背景图片上方。背景图片会根据视频尺寸自动调整大小。")
                
                with gr.Row():
                    add_title_button = gr.Button("添加/更新标题", variant="primary")
                    preview_titles_button = gr.Button("预览所有标题")
                    apply_titles_button = gr.Button("将所有标题应用到视频", variant="primary")
                
                # 添加删除标题的UI组件
                with gr.Row():
                    title_select = gr.Number(label="选择要删除的标题ID", value=1, precision=0, elem_id="title-select-input")
                    delete_title_button = gr.Button("删除选中标题", variant="stop", elem_id="delete-title-button")
                
                title_status = gr.Textbox(label="状态信息", interactive=False)
                title_preview = gr.HTML(label="标题预览")
                
                # 隐藏的状态变量，存储所有标题信息
                all_titles_data = gr.State(value=[])
    
    # 设置按钮事件和处理
    
    # 一键生成选项卡事件
    refresh_button.click(fn=list_input_files, outputs=[file_dropdown])
    refresh_fonts_button.click(fn=get_available_fonts, outputs=[font_name])
    refresh_character_button.click(
        fn=lambda: (list_character_images(), list_character_images(), list_character_images()),
        outputs=[character_image, closed_mouth_image, open_mouth_image]
    )
    show_all_fonts_button.click(fn=list_all_fonts, outputs=[all_fonts_output])
    
    # 根据图像生成器类型更新UI显示
    image_generator.change(
        fn=update_ui_based_on_generator,
        inputs=image_generator,
        outputs=[aspect_ratio, comfyui_style]
    )
    
    # 当选中"启用角色说话效果"时，显示相关选项
    talking_character.change(
        fn=lambda x: (gr.update(visible=x), gr.update(visible=x)),
        inputs=[talking_character],
        outputs=[talking_character_options, talking_sensitivity]
    )
    
    # 刷新角色图片列表时同时更新闭嘴和张嘴图片选项
    refresh_character_button.click(
        fn=lambda: (list_character_images(), list_character_images(), list_character_images()),
        outputs=[character_image, closed_mouth_image, open_mouth_image]
    )
    
    # 一键生成按钮事件
    one_click_process_button.click(
        fn=process_story,
        inputs=[
            text_input, file_dropdown, image_generator, aspect_ratio, image_style_type, 
            custom_style, comfyui_style, font_name, font_size, font_color, bg_opacity,
            character_image, preserve_line_breaks, voice_dropdown, video_engine, video_resolution,
            talking_character, closed_mouth_image, open_mouth_image, audio_sensitivity
        ],
        outputs=[output_text, output_video]
    ).then(
        fn=lambda video_path: (video_path, gr.update(value=video_path)),
        inputs=[output_video],
        outputs=[current_output_video, scene_video_preview]
    ).then(
        fn=lambda x: webui_refresh_scene_list(x),
        inputs=[scene_video_preview],
        outputs=[
            scene_slider, 
            scene_count_label, 
            scene_editor,
            recompose_video_button
        ]
    )
    
    # 场景管理选项卡事件
    
    # 刷新场景列表
    refresh_scenes_button.click(
        fn=lambda x: webui_refresh_scene_list(x),
        inputs=[scene_video_preview],
        outputs=[
            scene_slider, 
            scene_count_label, 
            scene_editor,
            recompose_video_button
        ]
    ).then(
        fn=generate_scene_thumbnails,
        outputs=[scene_thumbnails]
    )
    
    # 滑块变化事件
    scene_slider.change(
        fn=load_scene_details,
        inputs=[scene_slider, scene_video_preview],
        outputs=[
            current_scene_content,
            current_scene_prompt,
            current_scene_image,
            scene_index,
            scene_count_label
        ]
    )
    
    # 重新生成图片按钮
    regenerate_image_button.click(
        fn=lambda scene_id, prompt, generator, ratio, style, custom, comfyui_style: 
            on_regenerate_scene_image_with_retry(scene_id, generator, ratio, style, custom, comfyui_style, scene_manager.load_scenes(), prompt),
        inputs=[
            scene_index,
            current_scene_prompt,
            image_generator,
            aspect_ratio,
            image_style_type,
            custom_style,
            comfyui_style
        ],
        outputs=[scene_info]
    ).then(
        fn=load_scene_details,
        inputs=[scene_slider, scene_video_preview],
        outputs=[
            current_scene_content,
            current_scene_prompt,
            current_scene_image,
            scene_index,
            scene_count_label
        ]
    )
    
    # 上传图片相关事件
    upload_image_button.click(
        fn=show_upload_panel,
        outputs=[upload_image_panel]
    )
    
    upload_cancel_button.click(
        fn=hide_upload_panel,
        outputs=[upload_image_panel]
    )
    
    # 上传确认按钮处理
    upload_confirm_button.click(
        fn=upload_scene_image,
        inputs=[scene_index, scene_upload_image],
        outputs=[scene_info]
    ).then(
        fn=hide_upload_panel,
        outputs=[upload_image_panel]
    ).then(
        fn=load_scene_details,
        inputs=[scene_slider, scene_video_preview],
        outputs=[
            current_scene_content,
            current_scene_prompt,
            current_scene_image,
            scene_index,
            scene_count_label
        ]
    )
    
    # 重新合成视频按钮
    recompose_video_button.click(
        fn=recompose_video_only,  # 直接使用函数，现在它只返回一个路径
        inputs=[
            video_engine,
            character_image,
            font_name, font_size, font_color, bg_opacity,
            talking_character, closed_mouth_image, open_mouth_image, audio_sensitivity
        ],
        outputs=[scene_video_preview]
    ).then(
        fn=lambda video_path: f"视频重新合成完成！最终文件：{video_path}" if video_path else "视频重新合成失败",
        inputs=[scene_video_preview],
        outputs=[scene_info]
    )
    
    # 单独处理scene_video_preview值的变化，确保按钮不会消失
    scene_video_preview.change(
        fn=lambda x: webui_refresh_scene_list(x) if x else (
            gr.update(visible=True),
            gr.update(visible=True),
            gr.update(visible=True),
            gr.update(visible=True)
        ),
        inputs=[scene_video_preview],
        outputs=[
            scene_slider, 
            scene_count_label, 
            scene_editor,
            recompose_video_button
        ]
    )
    
    # 清除修改标记的按钮
    clear_modifications_button.click(
        fn=clear_modified_images,
        outputs=[scene_info]
    )
    
    # 场景标题管理相关事件
    add_title_button.click(
        fn=add_scene_title,
        inputs=[
            title_text, start_scene, end_scene, 
            title_color, title_size, title_position_x, title_position_y,
            title_background, all_titles_data, title_font
        ],
        outputs=[all_titles_data, title_status]
    ).then(
        fn=preview_scene_titles,
        inputs=[all_titles_data],
        outputs=[title_preview]
    )
    
    preview_titles_button.click(
        fn=preview_scene_titles,
        inputs=[all_titles_data],
        outputs=[title_preview]
    )
    
    apply_titles_button.click(
        fn=apply_scene_titles_to_video,
        inputs=[all_titles_data],
        outputs=[title_status]
    ).then(
        fn=lambda: "标题已应用到视频，可以在output目录中找到带有标题的视频文件",
        outputs=[scene_info]
    )

    # 删除标题按钮事件
    delete_title_button.click(
        fn=delete_scene_title,
        inputs=[title_select, all_titles_data],
        outputs=[all_titles_data, title_status]
    ).then(
        fn=preview_scene_titles,
        inputs=[all_titles_data],
        outputs=[title_preview]
    )

    # 添加刷新字体按钮事件
    refresh_title_font_button.click(
        fn=get_available_fonts, 
        outputs=[title_font]
    )
    
    # 添加导入文本标题按钮事件
    import_text_titles_button.click(
        fn=import_text_scene_titles,
        inputs=[all_titles_data],
        outputs=[all_titles_data, title_status]
    ).then(
        fn=preview_scene_titles,
        inputs=[all_titles_data],
        outputs=[title_preview]
    )

# 添加一个包装函数，将场景管理的返回值转换为正确的格式
def webui_refresh_scene_list(video_path):
    """转换刷新场景列表的返回格式以兼容gradio"""
    result = sm_refresh_scene_list(video_path)
    
    # 转换为Gradio所需的格式，返回4个组件状态 (移除了Gallery)
    return (
        gr.update(
            minimum=result["slider"]["minimum"], 
            maximum=result["slider"]["maximum"], 
            value=result["slider"]["value"], 
            visible=result["slider"]["visible"]
        ),
        gr.update(
            value=result["count_label"]["value"], 
            visible=result["count_label"]["visible"]
        ),
        gr.update(visible=result["editor"]["visible"]),
        gr.update(visible=result["recompose_button"]["visible"])
    )

# 启动服务
if __name__ == "__main__":
    demo.launch(share=True)  