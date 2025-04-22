import os
import subprocess
import sys
import tempfile
import numpy as np
from PIL import Image
import shutil
import json
from pathlib import Path
import time

def check_ffmpeg_available():
    """检查ffmpeg是否可用"""
    try:
        result = subprocess.run(["ffmpeg", "-version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode == 0:
            print(f"ffmpeg可用: {result.stdout.splitlines()[0]}")
            return True
        else:
            print(f"ffmpeg命令返回错误: {result.stderr}")
            return False
    except FileNotFoundError:
        print("错误: 找不到ffmpeg命令。请确保ffmpeg已安装并添加到系统PATH中。")
        return False
    except Exception as e:
        print(f"检查ffmpeg时出错: {e}")
        return False

def extract_audio(video_file, output_audio_file):
    """从视频中提取音频"""
    cmd = [
        "ffmpeg",
        "-i", video_file,
        "-vn",                   # 不要视频
        "-acodec", "pcm_s16le",  # 转换为PCM格式
        "-ar", "16000",          # 设置采样率
        "-y",                    # 覆盖已有文件
        output_audio_file
    ]
    
    print(f"提取音频命令: {' '.join(cmd)}")
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    
    if result.returncode != 0:
        print(f"提取音频失败: {result.stderr}")
        return False
    
    print(f"音频提取成功: {output_audio_file}")
    return True

def _run_ffmpeg_command(cmd, error_msg="执行命令失败"):
    """执行FFmpeg命令并处理结果
    
    Args:
        cmd: 要执行的命令列表
        error_msg: 出错时显示的消息
    
    Returns:
        成功返回(True, stdout, stderr)，失败返回(False, None, stderr)
    """
    try:
        print(f"执行命令: {' '.join(cmd)}")
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        
        if result.returncode == 0:
            return True, result.stdout, result.stderr
        else:
            print(f"{error_msg}: {result.stderr}")
            return False, None, result.stderr
    except Exception as e:
        print(f"{error_msg}: {str(e)}")
        return False, None, str(e)

def _get_audio_duration(audio_file):
    """获取音频文件的时长
    
    Args:
        audio_file: 音频文件路径
    
    Returns:
        音频时长(秒)，失败返回None
    """
    duration_cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "json",
        audio_file
    ]
    
    success, stdout, _ = _run_ffmpeg_command(duration_cmd, "获取音频时长失败")
    if success and stdout:
        try:
            duration_data = json.loads(stdout)
            return float(duration_data["format"]["duration"])
        except (json.JSONDecodeError, KeyError) as e:
            print(f"解析音频时长失败: {e}")
    return None

def _convert_to_wav(audio_file, output_wav):
    """将音频文件转换为WAV格式
    
    Args:
        audio_file: 原始音频文件
        output_wav: 输出WAV文件路径
    
    Returns:
        成功返回True，失败返回False
    """
    cmd_convert = [
        "ffmpeg",
        "-i", audio_file,
        "-acodec", "pcm_s16le",  # 转换为PCM格式
        "-ar", "16000",          # 设置采样率
        "-y",                    # 覆盖已有文件
        output_wav
    ]
    success, _, _ = _run_ffmpeg_command(cmd_convert, "转换音频格式失败")
    return success

def _analyze_wav_volume(wav_file, step, threshold):
    """分析WAV文件音量并生成张嘴状态序列
    
    Args:
        wav_file: WAV文件路径
        step: 采样步长(秒)
        threshold: 音量阈值
    
    Returns:
        原始张嘴状态列表，格式为[(时间点, 是否张嘴), ...]
    """
    try:
        import wave
        
        # 打开WAV文件
        with wave.open(wav_file, 'rb') as wf:
            # 获取音频参数
            channels = wf.getnchannels()
            sample_width = wf.getsampwidth()
            frame_rate = wf.getframerate()
            n_frames = wf.getnframes()
            
            # 读取所有数据
            raw_data = wf.readframes(n_frames)
            
            # 将字节数据转换为numpy数组
            if sample_width == 1:
                dtype = np.uint8
            elif sample_width == 2:
                dtype = np.int16
            elif sample_width == 4:
                dtype = np.int32
            else:
                raise ValueError("不支持的采样宽度")
            
            # 将原始字节转换为数字数组
            samples = np.frombuffer(raw_data, dtype=dtype)
            
            if channels > 1:
                # 如果是立体声，取平均值
                samples = samples.reshape(-1, channels)
                samples = samples.mean(axis=1)
            
            # 计算每个时间窗口的音量级别
            window_size = int(frame_rate * step)  # 每step秒的样本数
            num_windows = int(np.ceil(len(samples) / window_size))
            
            raw_mouth_states = []
            max_possible_volume = np.iinfo(dtype).max
            
            for i in range(num_windows):
                start = i * window_size
                end = min(start + window_size, len(samples))
                window_samples = samples[start:end]
                
                # 计算窗口内的音量 (RMS)
                if len(window_samples) > 0:
                    volume = np.sqrt(np.mean(window_samples.astype(np.float64)**2))
                    
                    # 归一化音量
                    normalized_volume = volume / max_possible_volume
                    
                    # 根据阈值确定是否张嘴
                    is_mouth_open = normalized_volume > threshold
                    
                    # 添加时间点和张嘴状态
                    time_point = i * step
                    raw_mouth_states.append((time_point, is_mouth_open))
                    
                    print(f"时间 {time_point:.1f}s: 音量 {normalized_volume:.4f}, {'张嘴' if is_mouth_open else '闭嘴'}")
            
            print(f"已生成 {len(raw_mouth_states)} 个原始张嘴状态")
            return raw_mouth_states
            
    except Exception as e:
        print(f"分析WAV音量出错: {e}")
        import traceback
        traceback.print_exc()
        return None

def _optimize_mouth_states(raw_states, min_duration, audio_duration):
    """优化口型状态，合并相似状态并过滤短暂状态
    
    Args:
        raw_states: 原始张嘴状态列表 [(时间点, 是否张嘴), ...]
        min_duration: 最小持续时间(秒)
        audio_duration: 音频总时长
    
    Returns:
        优化后的张嘴状态列表
    """
    if not raw_states:
        return [(0.0, False)]  # 默认闭嘴状态
    
    # 优化1: 合并连续相同状态
    optimized_states = []
    current_state = None
    current_start = 0
    
    for i, (time_point, is_open) in enumerate(raw_states):
        if current_state is None:
            # 第一个状态
            current_state = is_open
            current_start = time_point
        elif current_state != is_open:
            # 状态改变
            optimized_states.append((current_start, current_state))
            current_state = is_open
            current_start = time_point
            
        # 处理最后一个状态
        if i == len(raw_states) - 1:
            optimized_states.append((current_start, current_state))
    
    print(f"合并相同状态后: {len(optimized_states)} 个状态")
    
    # 优化2: 过滤掉过短的张嘴状态
    filtered_states = []
    for i, (time_point, is_open) in enumerate(optimized_states):
        # 计算持续时间
        if i < len(optimized_states) - 1:
            duration = optimized_states[i+1][0] - time_point
        else:
            # 最后一个状态持续到结束
            duration = audio_duration - time_point
            
        # 过滤短暂张嘴
        if not is_open or duration >= min_duration:
            filtered_states.append((time_point, is_open))
            
    print(f"过滤短张嘴后: {len(filtered_states)} 个状态")
    
    # 如果没有任何状态变化，添加一个闭嘴状态点
    if not filtered_states:
        filtered_states.append((0.0, False))
        
    return filtered_states

def _generate_fallback_states(duration, step):
    """生成后备的张嘴状态序列（简单模式）
    
    当正常分析失败时使用此函数生成简单的模式
    
    Args:
        duration: 音频时长
        step: 采样步长
    
    Returns:
        简单的张嘴状态序列
    """
    print("使用简单方法生成张嘴序列...")
    raw_mouth_states = []
    num_frames = int(duration / step) + 1
    
    for i in range(num_frames):
        time_point = i * step
        # 简单的模式：每3帧张嘴一次
        is_open = (i % 3 == 0)
        raw_mouth_states.append((time_point, is_open))
    
    return raw_mouth_states

def analyze_audio_volume(audio_file, threshold=0.05, min_duration=0.1, sample_step=0.1):
    """分析音频文件的音量，返回应该张嘴的时间点列表
    
    Args:
        audio_file: 音频文件路径
        threshold: 音量阈值，范围0-1，默认0.05（降低阈值使更容易触发）
        min_duration: 最小张嘴持续时间(秒)，默认0.1（降低最小持续时间）
        sample_step: 采样步长(秒)，默认0.1（提高采样频率）
    
    Returns:
        优化后的张嘴状态列表，每项为(时间点,是否张嘴)
    """
    # 1. 获取音频长度
    audio_duration = _get_audio_duration(audio_file)
    if not audio_duration:
        print("无法获取音频时长")
        return None
    print(f"音频时长: {audio_duration}秒")
    
    # 2. 自适应调整采样步长（可选，保持原有行为）
    # 对于极长的视频，可以考虑自动调整采样步长以提高性能
    # adjusted_step = sample_step
    # if audio_duration > 300:  # 5分钟以上的视频
    #     adjusted_step = max(sample_step, 0.15)
    # sample_step = adjusted_step
    
    # 3. 转换音频格式为WAV用于分析
    temp_wav = "output/temp_speech.wav"
    if not _convert_to_wav(audio_file, temp_wav):
        print("转换音频格式失败")
        return _generate_fallback_states(audio_duration, sample_step)
    
    # 4. 分析WAV文件音量
    raw_mouth_states = _analyze_wav_volume(temp_wav, sample_step, threshold)
    
    # 5. 清理临时文件
    try:
        if os.path.exists(temp_wav):
            os.remove(temp_wav)
    except Exception as e:
        print(f"清理临时WAV文件失败: {e}")
    
    # 6. 如果分析失败，使用简单的后备方法
    if not raw_mouth_states:
        return _generate_fallback_states(audio_duration, sample_step)
    
    # 7. 优化口型状态
    return _optimize_mouth_states(raw_mouth_states, min_duration, audio_duration)

def prepare_character_images(closed_mouth_path, open_mouth_path, video_width, video_height):
    """准备角色图片，调整大小并保存为临时文件"""
    try:
        # 处理闭嘴图片
        pil_closed = Image.open(closed_mouth_path)
        if pil_closed.mode != 'RGBA':
            if pil_closed.mode == 'RGB':
                rgba_img = Image.new('RGBA', pil_closed.size, (0, 0, 0, 0))
                rgba_img.paste(pil_closed, (0, 0))
                pil_closed = rgba_img
            else:
                pil_closed = pil_closed.convert('RGBA')
        
        # 处理张嘴图片
        pil_open = Image.open(open_mouth_path)
        if pil_open.mode != 'RGBA':
            if pil_open.mode == 'RGB':
                rgba_img = Image.new('RGBA', pil_open.size, (0, 0, 0, 0))
                rgba_img.paste(pil_open, (0, 0))
                pil_open = rgba_img
            else:
                pil_open = pil_open.convert('RGBA')
        
        # 确保两张图片大小一致
        if pil_closed.size != pil_open.size:
            print(f"警告: 闭嘴图片 ({pil_closed.size}) 和张嘴图片 ({pil_open.size}) 大小不一致，将调整为相同大小")
            # 使用闭嘴图片的大小作为标准
            pil_open = pil_open.resize(pil_closed.size, Image.LANCZOS)
        
        # 获取图片尺寸
        char_width, char_height = pil_closed.size
        char_aspect = char_width / char_height
        
        # 调整大小，保持宽高比，最大尺寸为500x500
        if char_width > char_height:
            new_width = min(500, char_width)
            new_height = int(new_width / char_aspect)
        else:
            new_height = min(500, char_height)
            new_width = int(new_height * char_aspect)
        
        print(f"调整图片大小: {char_width}x{char_height} -> {new_width}x{new_height}")
        
        # 调整大小
        pil_closed = pil_closed.resize((new_width, new_height), Image.LANCZOS)
        pil_open = pil_open.resize((new_width, new_height), Image.LANCZOS)
        
        # 保存处理后的图片
        temp_closed_path = "output/temp_closed_mouth.png"
        temp_open_path = "output/temp_open_mouth.png"
        
        pil_closed.save(temp_closed_path, format="PNG", optimize=True)
        pil_open.save(temp_open_path, format="PNG", optimize=True)
        
        # 计算右下角位置，留出边距
        x_pos = video_width - new_width - 20
        y_pos = video_height - new_height - 0  # 改为0像素的边距，使图片紧贴底部
        
        return temp_closed_path, temp_open_path, x_pos, y_pos
    
    except Exception as e:
        print(f"准备角色图片时出错: {e}")
        import traceback
        traceback.print_exc()
        return None, None, 0, 0

def create_talking_character_video(input_video, closed_mouth_image, open_mouth_image, output_video, threshold=0.2):
    """
    使用ffmpeg创建会说话角色效果的视频
    
    参数:
        input_video: 输入视频文件路径
        closed_mouth_image: 闭嘴角色图片路径
        open_mouth_image: 张嘴角色图片路径
        output_video: 输出视频文件路径
        threshold: 音量阈值，超过此值时角色张嘴，范围0-1
    """
    print(f"\n===== 开始创建会说话角色视频 =====")
    print(f"输入视频: {input_video}")
    print(f"闭嘴图片: {closed_mouth_image}")
    print(f"张嘴图片: {open_mouth_image}")
    print(f"输出视频: {output_video}")
    print(f"音量阈值: {threshold}")
    
    # 创建临时目录
    temp_dir = "output/talking_char_temp"
    os.makedirs(temp_dir, exist_ok=True)
    
    # 检查ffmpeg是否可用
    if not check_ffmpeg_available():
        print("由于ffmpeg不可用，无法创建会说话角色视频")
        return False
    
    # 检查输入文件
    if not os.path.exists(input_video):
        print(f"错误: 输入视频不存在: {input_video}")
        return False
    
    if not os.path.exists(closed_mouth_image):
        print(f"错误: 闭嘴图片不存在: {closed_mouth_image}")
        return False
    
    if not os.path.exists(open_mouth_image):
        print(f"错误: 张嘴图片不存在: {open_mouth_image}")
        return False
    
    # 确保输出目录存在
    os.makedirs(os.path.dirname(os.path.abspath(output_video)), exist_ok=True)
    
    try:
        # 提取音频
        audio_file = os.path.join(temp_dir, "audio.wav")
        if not extract_audio(input_video, audio_file):
            print("提取音频失败，无法继续处理")
            return False
        
        # 获取视频信息
        print("获取视频信息...")
        ffprobe_cmd = [
            "ffprobe", 
            "-v", "error", 
            "-select_streams", "v:0", 
            "-show_entries", "stream=width,height,r_frame_rate", 
            "-of", "json", 
            input_video
        ]
        
        success, stdout, stderr = _run_ffmpeg_command(ffprobe_cmd, "获取视频信息失败")
        if not success:
            return False
        
        # 解析视频信息
        video_info = json.loads(stdout)
        
        if not video_info.get("streams"):
            print(f"无法获取视频流信息")
            return False
        
        video_width = int(video_info["streams"][0]["width"])
        video_height = int(video_info["streams"][0]["height"])
        
        # 解析帧率
        frame_rate_str = video_info["streams"][0]["r_frame_rate"]
        frame_rate_parts = frame_rate_str.split('/')
        if len(frame_rate_parts) == 2:
            frame_rate = float(frame_rate_parts[0]) / float(frame_rate_parts[1])
        else:
            frame_rate = float(frame_rate_str)
        
        print(f"视频尺寸: {video_width}x{video_height}, 帧率: {frame_rate}fps")
        
        # 分析音频，确定张嘴时间
        print("分析音频...")
        # 使用优化的参数: 采样步长0.3秒, 最小张嘴时长0.3秒
        mouth_states = analyze_audio_volume(audio_file, threshold, min_duration=0.15, sample_step=0.15)
        if not mouth_states:
            print("分析音频失败，无法继续处理")
            return False
        
        # 准备角色图片
        temp_closed_path, temp_open_path, x_pos, y_pos = prepare_character_images(
            closed_mouth_image, open_mouth_image, video_width, video_height
        )
        
        if not temp_closed_path or not temp_open_path:
            print("准备角色图片失败，无法继续处理")
            return False
        
        # 创建口型变化视频
        print("创建口型变化视频...")
        
        # 获取视频时长
        duration_cmd = [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "json",
            input_video
        ]
        
        success, stdout, stderr = _run_ffmpeg_command(duration_cmd, "获取视频时长失败")
        if not success:
            return False
            
        duration_data = json.loads(stdout)
        video_duration = float(duration_data["format"]["duration"])
        print(f"视频时长: {video_duration}秒")
        
        # 用简单的方法：使用闭嘴图片作为基础，在需要张嘴的时候切换
        # 创建一个张嘴时间表作为ffmpeg滤镜表达式
        mouth_expr = []
        open_segments = 0
        
        for i, (time_point, is_open) in enumerate(mouth_states):
            if i < len(mouth_states) - 1:
                next_time = mouth_states[i + 1][0]
                if is_open:
                    # 只添加真正的张嘴状态
                    mouth_expr.append(f"between(t,{time_point},{next_time})")
                    open_segments += 1
            else:
                # 最后一个状态
                if is_open:
                    mouth_expr.append(f"gte(t,{time_point})")
                    open_segments += 1
        
        print(f"生成了{open_segments}个张嘴片段表达式")
        
        # 如果表达式过长，分批处理
        MAX_EXPR_PER_BATCH = 50  # 每批最多50个表达式
        batched_exprs = []
        
        for i in range(0, len(mouth_expr), MAX_EXPR_PER_BATCH):
            batch = mouth_expr[i:i+MAX_EXPR_PER_BATCH]
            batched_exprs.append("+".join(batch))
        
        # 合并所有批次
        if batched_exprs:
            enable_expr = "+".join([f"({expr})" for expr in batched_exprs])
        else:
            enable_expr = "0"  # 如果没有表达式，则默认为0（始终不启用）
        
        print(f"最终表达式长度: {len(enable_expr)} 字符")
        
        # 创建临时滤镜脚本文件，避免命令行长度限制
        filter_script_path = os.path.join(temp_dir, "filter_complex.txt")
        with open(filter_script_path, "w", encoding="utf-8") as f:
            # 写入滤镜表达式
            f.write(f"[0:v][1:v]overlay={x_pos}:{y_pos}[tmp];\n")
            f.write(f"[tmp][2:v]overlay={x_pos}:{y_pos}:enable='{enable_expr}'")
        
        print(f"已创建滤镜脚本文件: {filter_script_path}")
        
        # 构建ffmpeg命令，使用-filter_complex_script替代-filter_complex
        ffmpeg_cmd = [
            "ffmpeg",
            "-i", input_video,      # 原始视频
            "-i", temp_closed_path, # 闭嘴图片
            "-i", temp_open_path,   # 张嘴图片
            "-filter_complex_script", filter_script_path,  # 使用滤镜脚本文件
            "-c:a", "copy",         # 复制音频流
            "-y",                   # 覆盖输出文件
            output_video
        ]
        
        success, _, stderr = _run_ffmpeg_command(ffmpeg_cmd, "创建会说话角色视频失败")
        if not success:
            # 保存错误信息到文件
            with open("output/ffmpeg_error.txt", "w", encoding="utf-8") as f:
                f.write(stderr)
            return False
        
        print(f"成功创建会说话角色视频: {output_video}")
        
        # 清理临时文件
        try:
            if os.path.exists(filter_script_path):
                os.remove(filter_script_path)
            shutil.rmtree(temp_dir)
            if os.path.exists(temp_closed_path):
                os.remove(temp_closed_path)
            if os.path.exists(temp_open_path):
                os.remove(temp_open_path)
        except Exception as e:
            print(f"清理临时文件时出错: {e}")
        
        return True
    
    except Exception as e:
        print(f"处理过程中出错: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    if len(sys.argv) < 5:
        print("用法: python add_talking_character.py <输入视频> <闭嘴图片> <张嘴图片> <输出视频> [音量阈值(0-1)]")
        sys.exit(1)
    
    input_video = sys.argv[1]
    closed_mouth_image = sys.argv[2]
    open_mouth_image = sys.argv[3]
    output_video = sys.argv[4]
    
    threshold = 0.2  # 默认阈值
    if len(sys.argv) > 5:
        try:
            threshold = float(sys.argv[5])
            if threshold < 0 or threshold > 1:
                print(f"警告: 阈值应在0-1范围内，已调整为默认值0.2")
                threshold = 0.2
        except:
            print(f"警告: 无法解析阈值参数 '{sys.argv[5]}'，使用默认值0.2")
    
    create_talking_character_video(input_video, closed_mouth_image, open_mouth_image, output_video, threshold) 