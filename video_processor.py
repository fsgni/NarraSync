"""视频处理服务模块

提供视频处理功能，支持FFmpeg和MoviePy两种处理引擎。
"""

import os
import subprocess
import platform
import json
import shutil
import time
import re
import math
import random
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional, Union

# 检查MoviePy可用性
MOVIEPY_AVAILABLE = False
try:
    from moviepy.editor import VideoFileClip, AudioFileClip, ImageClip, concatenate_videoclips
    try:
        from moviepy.video.fx.resize import resize
    except ImportError:
        from moviepy.video.fx.all import resize
    MOVIEPY_AVAILABLE = True
except ImportError:
    pass

# 导入新架构组件
from config import config
from errors import get_logger, error_handler, VideoProcessingError, FileError
from services import VideoProcessorService, ServiceFactory

# 创建日志记录器
logger = get_logger("video_processor")

class VideoProcessor(VideoProcessorService):
    """统一的视频处理器类，支持使用FFmpeg或MoviePy处理视频"""
    
    def __init__(self, engine: str = "auto"):
        """初始化视频处理器
        
        Args:
            engine: 视频处理引擎，可选 "ffmpeg", "moviepy", "auto"
                   - "ffmpeg": 使用FFmpeg命令行工具
                   - "moviepy": 使用MoviePy库
                   - "auto": 自动选择可用的引擎，优先FFmpeg
        """
        self.engine = self._select_engine(engine)
        # 从配置中获取分辨率设置
        self.resolution = config.get("video", "resolution", default=(1920, 1080))
        self.fps = config.get("video", "fps", default=30)
        self.max_retries = config.get("processing", "max_retries", default=3)
        self.retry_delay = config.get("processing", "retry_delay", default=1.0)
        logger.info(f"已选择 {self.engine.upper()} 作为图片合成视频引擎")
        logger.info(f"视频分辨率设置为: {self.resolution[0]}x{self.resolution[1]}")
    
    def _select_engine(self, engine: str) -> str:
        """选择合适的视频处理引擎
        
        Args:
            engine: 请求的引擎类型
            
        Returns:
            实际使用的引擎名称
        """
        if engine.lower() == "auto":
            # 检查ffmpeg是否可用
            if self._is_ffmpeg_available():
                return "ffmpeg"
            elif MOVIEPY_AVAILABLE:
                return "moviepy"
            else:
                logger.warning("没有可用的视频处理引擎。尝试使用FFmpeg作为备选...")
                return "ffmpeg"  # 即使不可用也返回ffmpeg，后面会再次检查
        
        elif engine.lower() == "ffmpeg":
            # 检查 ffmpeg 可用性但不抛出异常
            if not self._is_ffmpeg_available():
                logger.warning("FFmpeg不可用，但仍将尝试使用它")
            return "ffmpeg"
        
        elif engine.lower() == "moviepy":
            # 再次尝试导入 MoviePy
            if not MOVIEPY_AVAILABLE:
                try:
                    global VideoFileClip, AudioFileClip, ImageClip, concatenate_videoclips, resize
                    from moviepy.editor import VideoFileClip, AudioFileClip, ImageClip, concatenate_videoclips
                    try:
                        from moviepy.video.fx.resize import resize
                    except ImportError:
                        from moviepy.video.fx.all import resize
                    logger.info("成功导入MoviePy库")
                    return "moviepy"
                except ImportError as e:
                    logger.warning(f"MoviePy不可用 ({str(e)})。将尝试使用FFmpeg作为备选...")
                    return "ffmpeg"
            return "moviepy"
        
        else:
            logger.warning(f"不支持的视频处理引擎: {engine}。将使用FFmpeg作为备选...")
            return "ffmpeg"
    
    def _is_ffmpeg_available(self) -> bool:
        """检查FFmpeg是否可用
        
        Returns:
            是否可用
        """
        try:
            # 尝试执行ffmpeg命令查看版本信息
            result = subprocess.run(
                ["ffmpeg", "-version"], 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE,
                check=False,
                shell=(platform.system() == "Windows")
            )
            
            # 检查返回码
            if result.returncode == 0:
                # 解析版本信息
                version_output = result.stdout.decode('utf-8', errors='ignore')
                version_match = re.search(r'ffmpeg version ([^\s]+)', version_output)
                if version_match:
                    version = version_match.group(1)
                    logger.info(f"FFmpeg可用，版本: {version}")
                else:
                    logger.info("FFmpeg可用，但无法确定版本")
                return True
            else:
                logger.warning("FFmpeg命令返回非零状态码")
                return False
        except (subprocess.SubprocessError, FileNotFoundError) as e:
            logger.warning(f"FFmpeg不可用: {e}")
            return False
    
    def _with_retry(self, func, *args, error_msg="操作失败", **kwargs):
        """带有重试功能的函数调用
        
        Args:
            func: 要调用的函数
            *args: 函数参数
            error_msg: 错误消息前缀
            **kwargs: 函数关键字参数
            
        Returns:
            函数调用结果
            
        Raises:
            VideoProcessingError: 如果所有重试都失败
        """
        last_error = None
        for attempt in range(self.max_retries):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                last_error = e
                retry_count = attempt + 1
                if retry_count < self.max_retries:
                    logger.warning(f"{error_msg}: {e}，重试中 ({retry_count}/{self.max_retries})...")
                    time.sleep(self.retry_delay * (1.5 ** attempt))  # 指数退避
                else:
                    logger.error(f"{error_msg}: {e}，重试次数已用尽")
        
        # 所有重试都失败
        if last_error:
            raise VideoProcessingError(f"{error_msg}，重试次数已用尽", details={"last_error": str(last_error)})
        else:
            raise VideoProcessingError(f"{error_msg}，未知错误")
    
    @error_handler(error_message="创建基础视频失败")
    def create_base_video(self, audio_info_file: str, output_video: str) -> str:
        """创建基础视频（带有纯色背景和音频）
        
        Args:
            audio_info_file: 包含音频信息的JSON文件路径
            output_video: 输出视频文件路径
            
        Returns:
            str: 输出视频文件路径
        """
        # 确保输出目录存在
        output_dir = os.path.dirname(output_video)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)
        
        # 基础视频创建始终使用FFmpeg，不考虑引擎设置
        logger.info("创建基础视频 (始终使用FFmpeg引擎)")
        try:
            return self._create_base_video_ffmpeg(audio_info_file, output_video)
        except Exception as e:
            logger.error(f"使用FFmpeg创建基础视频失败: {str(e)}")
            # 如果ffmpeg失败且MoviePy可用，仍尝试使用它作为备选
            if MOVIEPY_AVAILABLE:
                logger.info("尝试使用MoviePy作为基础视频创建的备选方案...")
                return self._create_base_video_moviepy(audio_info_file, output_video)
            else:
                raise VideoProcessingError("创建基础视频失败，且无可用备选方案", details={"error": str(e)})
    
    def _create_base_video_ffmpeg(self, audio_info_file: str, output_video: str) -> str:
        """使用FFmpeg创建基础视频"""
        # 读取音频信息
        with open(audio_info_file, "r", encoding="utf-8") as f:
            audio_info = json.load(f)
        
        total_duration = audio_info.get("total_duration", 0)
        
        # 检查是否有直接的output_audio字段
        audio_file = audio_info.get("output_audio")
        
        # 如果没有output_audio字段，尝试合并所有音频文件
        if not audio_file or not os.path.exists(audio_file):
            logger.info("未找到合并后的音频文件，将尝试合并所有音频文件...")
            
            # 创建临时合并文件
            merged_audio = os.path.join(os.path.dirname(audio_info_file), "merged_audio.wav")
            
            # 创建音频文件列表
            audio_files = []
            for audio_info_item in audio_info.get("audio_files", []):
                audio_item_file = audio_info_item.get("audio_file")
                if audio_item_file:
                    # 确保路径是绝对路径
                    if not os.path.isabs(audio_item_file):
                        audio_item_file = os.path.join(os.path.dirname(audio_info_file), audio_item_file)
                    
                    if os.path.exists(audio_item_file):
                        audio_files.append(audio_item_file)
            
            if not audio_files:
                raise FileNotFoundError("无法找到任何音频文件，无法继续创建视频")
            
            # 创建临时文件来保存合并列表
            with open("temp_audio_list.txt", "w", encoding="utf-8") as f:
                for file in audio_files:
                    f.write(f"file '{file}'\n")
            
            # 使用ffmpeg合并音频文件
            try:
                subprocess.run(
                    ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", "temp_audio_list.txt", "-c", "copy", merged_audio],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=True,
                    shell=(platform.system() == "Windows")
                )
                logger.info(f"成功合并音频文件: {merged_audio}")
                
                # 更新音频文件路径
                audio_file = merged_audio
            except subprocess.CalledProcessError as e:
                logger.error(f"合并音频文件失败: {e.stderr.decode() if e.stderr else str(e)}")
                if os.path.exists("temp_audio_list.txt"):
                    os.remove("temp_audio_list.txt")
                raise
            except Exception as e:
                logger.error(f"合并音频文件时发生错误: {str(e)}")
                if os.path.exists("temp_audio_list.txt"):
                    os.remove("temp_audio_list.txt")
                raise
        
        if not audio_file or not os.path.exists(audio_file):
            raise FileNotFoundError(f"最终音频文件不存在: {audio_file}")
        
        logger.info(f"使用音频文件: {audio_file}")
        
        # 使用ffmpeg创建基础视频
        try:
            # 构建ffmpeg命令
            cmd = [
                "ffmpeg", "-y",
                "-f", "lavfi",
                "-i", f"color=c=black:s={self.resolution[0]}x{self.resolution[1]}:r={self.fps}",
                "-i", audio_file,
                "-c:v", "libx264",
                "-c:a", "aac",
                "-shortest",
                output_video
            ]
            
            # 执行命令
            subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
                shell=(platform.system() == "Windows")
            )
            
            logger.info(f"成功创建基础视频: {output_video}")
            return output_video
            
        except subprocess.CalledProcessError as e:
            logger.error(f"FFmpeg命令执行失败: {e.stderr.decode() if e.stderr else str(e)}")
            raise VideoProcessingError("创建基础视频失败", details={"ffmpeg_error": str(e)})
        except Exception as e:
            logger.error(f"创建基础视频时发生错误: {str(e)}")
            raise VideoProcessingError("创建基础视频失败", details={"error": str(e)})
    
    def _create_base_video_moviepy(self, audio_info_file: str, output_video: str) -> str:
        """使用MoviePy创建基础视频"""
        # 读取音频信息
        with open(audio_info_file, "r", encoding="utf-8") as f:
            audio_info = json.load(f)
        
        # 检查是否有直接的output_audio字段
        audio_file = audio_info.get("output_audio")
        
        # 如果没有output_audio字段，尝试合并所有音频文件
        if not audio_file or not os.path.exists(audio_file):
            logger.info("未找到合并后的音频文件，将尝试合并所有音频文件...")
            
            # 创建临时合并文件
            merged_audio = os.path.join(os.path.dirname(audio_info_file), "merged_audio.wav")
            
            # 使用ffmpeg合并文件（更简单）
            try:
                # 先创建合并列表
                audio_files = []
                for audio_info_item in audio_info.get("audio_files", []):
                    audio_item_file = audio_info_item.get("audio_file")
                    if audio_item_file:
                        # 确保路径是绝对路径
                        if not os.path.isabs(audio_item_file):
                            audio_item_file = os.path.join(os.path.dirname(audio_info_file), audio_item_file)
                        
                        if os.path.exists(audio_item_file):
                            audio_files.append(audio_item_file)
                
                if not audio_files:
                    raise FileNotFoundError("无法找到任何音频文件，无法继续创建视频")
                
                # 使用MoviePy合并音频文件
                audio_clips = [AudioFileClip(file) for file in audio_files]
                final_audio = concatenate_videoclips(audio_clips)
                final_audio.write_audiofile(merged_audio)
                
                # 关闭音频剪辑
                for clip in audio_clips:
                    clip.close()
                final_audio.close()
                
                logger.info(f"成功合并音频文件: {merged_audio}")
                
                # 更新音频文件路径
                audio_file = merged_audio
            except Exception as e:
                logger.error(f"合并音频文件失败: {str(e)}")
                
                # 尝试使用FFmpeg作为备选
                logger.info("尝试使用FFmpeg合并音频文件...")
                with open("temp_audio_list.txt", "w", encoding="utf-8") as f:
                    for file in audio_files:
                        f.write(f"file '{file}'\n")
                
                try:
                    subprocess.run(
                        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", "temp_audio_list.txt", "-c", "copy", merged_audio],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        check=True,
                        shell=(platform.system() == "Windows")
                    )
                    logger.info(f"成功使用FFmpeg合并音频文件: {merged_audio}")
                    
                    # 更新音频文件路径
                    audio_file = merged_audio
                except Exception as e2:
                    logger.error(f"使用FFmpeg合并音频文件失败: {str(e2)}")
                    raise
                finally:
                    if os.path.exists("temp_audio_list.txt"):
                        os.remove("temp_audio_list.txt")
        
        if not audio_file or not os.path.exists(audio_file):
            raise FileNotFoundError(f"最终音频文件不存在: {audio_file}")
        
        logger.info(f"使用音频文件: {audio_file}")
        
        # 创建音频剪辑
        audio_clip = AudioFileClip(audio_file)
        
        # 使用配置的分辨率设置
        width, height = self.resolution
        logger.info(f"创建基础视频，使用分辨率: {width}x{height}")
        
        # 创建黑色背景视频
        black_clip = ImageClip(
            (width, height), 
            color=(0, 0, 0), 
            duration=audio_clip.duration
        )
        
        # 添加音频
        video_clip = black_clip.set_audio(audio_clip)
        
        # 导出视频
        video_clip.write_videofile(
            output_video,
            codec="libx264",
            audio_codec="aac",
            fps=24
        )
        
        # 清理
        video_clip.close()
        audio_clip.close()
        
        return output_video
    
    def create_video_with_scenes(self, key_scenes_file: str, base_video: str, output_video: str) -> str:
        """
        使用场景图片创建视频
        
        Args:
            key_scenes_file: 包含场景信息的JSON文件路径
            base_video: 基础视频文件路径
            output_video: 输出视频文件路径
            
        Returns:
            str: 输出视频文件路径
        """
        # 根据选择的引擎调用不同的实现
        if self.engine == "ffmpeg":
            try:
                return self._create_video_with_scenes_ffmpeg(key_scenes_file, base_video, output_video)
            except Exception as e:
                logger.error(f"使用FFmpeg处理场景视频失败: {str(e)}")
                if MOVIEPY_AVAILABLE:
                    logger.info("尝试使用MoviePy作为备选...")
                    return self._create_video_with_scenes_moviepy(key_scenes_file, base_video, output_video)
                else:
                    raise
        else:  # moviepy
            if not MOVIEPY_AVAILABLE:
                logger.warning("MoviePy不可用，尝试使用FFmpeg作为备选...")
                return self._create_video_with_scenes_ffmpeg(key_scenes_file, base_video, output_video)
            
            try:
                return self._create_video_with_scenes_moviepy(key_scenes_file, base_video, output_video)
            except Exception as e:
                logger.error(f"使用MoviePy处理场景视频失败: {str(e)}")
                logger.info("尝试使用FFmpeg作为备选...")
                return self._create_video_with_scenes_ffmpeg(key_scenes_file, base_video, output_video)
    
    def _create_video_with_scenes_ffmpeg(self, key_scenes_file: str, base_video: str, output_video: str) -> str:
        """使用FFmpeg创建带有场景的视频"""
        try:
            # 读取场景信息
            with open(key_scenes_file, "r", encoding="utf-8") as f:
                scenes = json.load(f)
            
            # 创建临时目录
            temp_dir = os.path.join(os.path.dirname(output_video), "temp_scenes")
            os.makedirs(temp_dir, exist_ok=True)
            
            # 处理每个场景
            scene_videos = []
            for i, scene in enumerate(scenes):
                scene_image = scene.get("image_file")
                if not scene_image or not os.path.exists(scene_image):
                    logger.warning(f"场景 {i+1} 的图片不存在: {scene_image}")
                    continue
                
                # 创建场景视频
                scene_video = os.path.join(temp_dir, f"scene_{i+1}.mp4")
                start_time = scene.get("start_time", 0)
                duration = scene.get("duration", 0)
                
                # 构建ffmpeg命令
                cmd = [
                    "ffmpeg", "-y",
                    "-loop", "1",
                    "-i", scene_image,
                    "-c:v", "libx264",
                    "-t", str(duration),
                    "-vf", f"scale={self.resolution[0]}:{self.resolution[1]}:force_original_aspect_ratio=decrease,pad={self.resolution[0]}:{self.resolution[1]}:(ow-iw)/2:(oh-ih)/2",
                    scene_video
                ]
                
                # 执行命令
                subprocess.run(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=True,
                    shell=(platform.system() == "Windows")
                )
                
                scene_videos.append(scene_video)
            
            if not scene_videos:
                raise VideoProcessingError("没有有效的场景视频可以处理")
            
            # 创建场景列表文件
            scene_list_file = os.path.join(temp_dir, "scene_list.txt")
            with open(scene_list_file, "w", encoding="utf-8") as f:
                for video in scene_videos:
                    f.write(f"file '{video}'\n")
            
            # 合并所有场景视频
            merged_video = os.path.join(temp_dir, "merged_scenes.mp4")
            cmd = [
                "ffmpeg", "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", scene_list_file,
                "-c", "copy",
                merged_video
            ]
            
            subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
                shell=(platform.system() == "Windows")
            )
            
            # 从基础视频中提取音频
            audio_file = os.path.join(temp_dir, "audio.aac")
            cmd = [
                "ffmpeg", "-y",
                "-i", base_video,
                "-vn",
                "-acodec", "copy",
                audio_file
            ]
            
            subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
                shell=(platform.system() == "Windows")
            )
            
            # 合并视频和音频
            cmd = [
                "ffmpeg", "-y",
                "-i", merged_video,
                "-i", audio_file,
                "-c:v", "copy",
                "-c:a", "aac",
                output_video
            ]
            
            subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
                shell=(platform.system() == "Windows")
            )
            
            # 清理临时文件
            shutil.rmtree(temp_dir, ignore_errors=True)
            
            logger.info(f"成功创建场景视频: {output_video}")
            return output_video
            
        except subprocess.CalledProcessError as e:
            logger.error(f"FFmpeg命令执行失败: {e.stderr.decode() if e.stderr else str(e)}")
            raise VideoProcessingError("创建场景视频失败", details={"ffmpeg_error": str(e)})
        except Exception as e:
            logger.error(f"创建场景视频时发生错误: {str(e)}")
            raise VideoProcessingError("创建场景视频失败", details={"error": str(e)})
    
    def _create_video_with_scenes_moviepy(self, key_scenes_file: str, base_video: str, output_video: str) -> str:
        """使用MoviePy和场景图片创建视频，添加电影级动画效果"""
        # 读取场景信息
        with open(key_scenes_file, "r", encoding="utf-8") as f:
            scenes = json.load(f)
        
        # 确保输出图片目录存在
        images_dir = "output/images"
        os.makedirs(images_dir, exist_ok=True)
        logger.info(f"确保图片目录存在: {images_dir}")
        
        # 加载基础视频
        base_clip = VideoFileClip(base_video)
        # 使用配置的分辨率设置
        video_width, video_height = self.resolution
        logger.info(f"使用配置的视频分辨率: {video_width}x{video_height}")
        
        # 如果没有场景，直接返回基础视频
        if not scenes:
            logger.info("没有场景信息，直接使用基础视频")
            base_clip.write_videofile(output_video, codec="libx264", audio_codec="aac", fps=24)
            base_clip.close()
            return output_video
        
        # 打印所有场景信息
        logger.info(f"读取到 {len(scenes)} 个场景")
        
        # 创建所有场景的图片剪辑
        clips = [base_clip]  # 首先添加基础视频
        
        # 为每个场景设置固定的随机种子，确保效果一致
        random.seed(42)
        
        # 处理每个场景
        for i, scene in enumerate(scenes):
            try:
                # 获取场景时间信息
                start_time = scene.get("start_time", 0)
                end_time = scene.get("end_time", 0)
                duration = end_time - start_time
                image_file = scene.get("image_file", "")
                
                if not image_file:
                    logger.warning(f"场景 {i+1} 缺少图片文件名，跳过")
                    continue
                
                # 构造图像路径
                image_path = f"output/images/{image_file}"
                
                # 打印路径检查信息
                logger.info(f"检查图片路径: {image_path}")
                
                if not os.path.exists(image_path):
                    logger.warning(f"警告: 图像文件不存在: {image_path}")
                    # 尝试检查其他可能的位置
                    alt_path = f"output/{image_file}"
                    if os.path.exists(alt_path):
                        logger.info(f"找到替代位置的图像: {alt_path}")
                        # 复制到正确位置
                        shutil.copy(alt_path, image_path)
                        logger.info(f"已复制图像到: {image_path}")
                    else:
                        logger.warning(f"无法找到场景 {i+1} 的图片，跳过")
                        continue
                else:
                    logger.info(f"找到图片: {image_path}")
                
                logger.info(f"处理图片: {image_path}")
                
                # 随机选择电影效果类型 (0=缓慢平移, 1=缓慢放大, 2=缓慢缩小)
                effect_type = random.randint(0, 2)
                
                # 加载图片
                img_clip = ImageClip(image_path)
                
                # 计算图片和视频的宽高比
                img_aspect = img_clip.w / img_clip.h
                video_aspect = video_width / video_height
                
                # 确保图片覆盖整个视频区域 - 减小安全边距
                safe_margin_factor = 1.15 # Changed from 1.08 to 1.15
                if img_aspect > video_aspect:  # 图片更宽
                    # 高度匹配视频，宽度按比例
                    img_height = video_height * safe_margin_factor
                    img_width = img_height * img_aspect
                else:  # 图片更高或相等
                    # 宽度匹配视频，高度按比例
                    img_width = video_width * safe_margin_factor
                    img_height = img_width / img_aspect
                
                # 调整图片大小
                img_clip = img_clip.resize(width=img_width, height=img_height)
                
                # 应用效果
                if effect_type == 0:  # 缓慢平移
                    # 随机选择平移方向
                    pan_direction = random.randint(0, 3)  # 0=左到右, 1=右到左, 2=上到下, 3=下到上
                    
                    # 计算平移距离 - 减小移动幅度
                    pan_distance = min(img_width, img_height) * 0.03 # Changed from 0.05
                    
                    # 定义位置函数
                    def pos_func(t):
                        # 线性移动，确保整个持续时间内都在移动
                        progress = t / duration
                        
                        if pan_direction == 0:  # 从左到右
                            x = -img_width/2 + video_width/2 - pan_distance/2 + progress * pan_distance
                            y = -img_height/2 + video_height/2
                        elif pan_direction == 1:  # 从右到左
                            x = -img_width/2 + video_width/2 + pan_distance/2 - progress * pan_distance
                            y = -img_height/2 + video_height/2
                        elif pan_direction == 2:  # 从上到下
                            x = -img_width/2 + video_width/2
                            y = -img_height/2 + video_height/2 - pan_distance/2 + progress * pan_distance
                        else:  # 从下到上
                            x = -img_width/2 + video_width/2
                            y = -img_height/2 + video_height/2 + pan_distance/2 - progress * pan_distance
                        
                        return (int(x), int(y))
                    
                elif effect_type == 1:  # 缓慢放大
                    # 从小到大缓慢放大 - 减小放大比例
                    start_scale = 1.0
                    end_scale = 1.03 # Changed from 1.05
                    
                    # 定义缩放函数
                    def zoom_func(t):
                        # 线性缩放
                        progress = t / duration
                        return start_scale + (end_scale - start_scale) * progress
                    
                    # 应用缩放效果
                    img_clip = img_clip.resize(lambda t: (int(img_width * zoom_func(t)), 
                                                         int(img_height * zoom_func(t))))
                    
                    # 定义位置函数 - 保持居中
                    def pos_func(t):
                        scale = zoom_func(t)
                        x = -img_width * scale / 2 + video_width / 2
                        y = -img_height * scale / 2 + video_height / 2
                        return (int(x), int(y))
                    
                else:  # 缓慢缩小
                    # 从大到小缓慢缩小 - 减小缩小比例
                    # start_scale = 1.03 # Changed from 1.05
                    # end_scale = 1.0
                    start_scale = 1.0 + (safe_margin_factor - 1.0) * 0.8 # Start from 80% of the new margin
                    end_scale = 1.005 # Ensure it ends slightly larger than the base calculated img_width/height
                    
                    # 定义缩放函数
                    def zoom_func(t):
                        # 线性缩放
                        progress = t / duration
                        return start_scale + (end_scale - start_scale) * progress
                    
                    # 应用缩放效果
                    img_clip = img_clip.resize(lambda t: (int(img_width * zoom_func(t)), 
                                                         int(img_height * zoom_func(t))))
                    
                    # 定义位置函数 - 保持居中
                    def pos_func(t):
                        scale = zoom_func(t)
                        x = -img_width * scale / 2 + video_width / 2
                        y = -img_height * scale / 2 + video_height / 2
                        return (int(x), int(y))
                
                # 设置持续时间和开始时间
                img_clip = img_clip.set_duration(duration).set_start(start_time)
                
                # 设置位置
                img_clip = img_clip.set_position(pos_func)
                
                # 添加淡入淡出效果
                # 计算淡入淡出时间 - 较短场景使用较短的淡入淡出时间
                fade_duration = min(0.5, duration / 10)  # 最长0.5秒，或者场景时长的1/10
                
                # 应用淡入淡出效果
                img_clip = img_clip.fadein(fade_duration).fadeout(fade_duration)
                
                # 添加到剪辑列表
                clips.append(img_clip)
                logger.info(f"已添加图片: {image_file} 效果类型: {effect_type} 淡入淡出: {fade_duration:.2f}秒")
                
            except Exception as e:
                logger.error(f"处理图片 {scene.get('image_file', '未知')} 时出错: {e}")
                import traceback
                traceback.print_exc()
        
        # 合成最终视频
        logger.info(f"合成视频，共 {len(clips)} 个剪辑...")
        
        # 创建合成视频 - 使用CompositeVideoClip
        from moviepy.editor import CompositeVideoClip
        final_clip = CompositeVideoClip(clips, size=(video_width, video_height))
        
        # 导出视频
        logger.info(f"写入视频文件: {output_video}")
        final_clip.write_videofile(
            output_video,
            codec="libx264",
            audio_codec="aac",
            temp_audiofile="temp-audio.m4a",
            remove_temp=True,
            fps=30,  # 使用较高帧率
            preset="slow",
            bitrate="5000k"
        )
        
        # 清理
        base_clip.close()
        final_clip.close()
        for clip in clips[1:]:
            try:
                clip.close()
            except:
                pass
        
        logger.info("MoviePy视频处理完成！")
        return output_video
    
    @error_handler(error_message="添加字幕失败")
    def add_subtitles(self, video_file: str, srt_file: str, output_file: str, **kwargs) -> str:
        """为视频添加字幕
        
        Args:
            video_file: 视频文件路径
            srt_file: SRT字幕文件路径
            output_file: 输出视频文件路径
            **kwargs: 字幕样式参数，包括:
                - font_file: 字体文件
                - font_size: 字体大小
                - font_color: 字体颜色
                - outline_color: 轮廓颜色
                - outline_width: 轮廓宽度
                
        Returns:
            生成的视频文件路径
        """
        # 确保输出目录存在
        output_dir = os.path.dirname(output_file)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)
        
        # 默认字幕样式参数
        font_file = kwargs.get('font_file', config.get("subtitles", "font_file", default="fonts/NotoSansSC-Medium.otf"))
        font_size = kwargs.get('font_size', config.get("subtitles", "font_size", default=24))
        font_color = kwargs.get('font_color', config.get("subtitles", "font_color", default="white"))
        outline_color = kwargs.get('outline_color', config.get("subtitles", "outline_color", default="black"))
        outline_width = kwargs.get('outline_width', config.get("subtitles", "outline_width", default=1.5))
        
        # 确保字幕文件存在
        if not os.path.exists(srt_file):
            raise FileError(f"字幕文件不存在: {srt_file}")
        
        # 确保视频文件存在
        if not os.path.exists(video_file):
            raise FileError(f"视频文件不存在: {video_file}")
        
        # 确保字体文件存在
        if not os.path.exists(font_file):
            font_file = "fonts/NotoSansSC-Medium.otf"  # 备选默认字体
            if not os.path.exists(font_file):
                raise FileError(f"字体文件不存在: {font_file}")
        
        logger.info(f"为视频 {video_file} 添加字幕，使用字幕文件 {srt_file}")
        
        # 使用FFmpeg添加字幕
        return self._with_retry(
            self._add_subtitles_ffmpeg,
            video_file, 
            srt_file, 
            output_file, 
            font_file, 
            font_size, 
            font_color, 
            outline_color, 
            outline_width,
            error_msg=f"添加字幕到视频 {video_file} 失败"
        )
    
    def _add_subtitles_ffmpeg(self, video_file: str, srt_file: str, output_file: str, 
                              font_file: str, font_size: int, font_color: str, 
                              outline_color: str, outline_width: float) -> str:
        """使用FFmpeg为视频添加字幕
        
        Args:
            视频文件、字幕文件和输出路径，以及样式参数
            
        Returns:
            输出视频路径
        """
        # 构建FFmpeg命令
        cmd = [
            "ffmpeg",
            "-i", video_file,
            "-vf", f"subtitles={srt_file}:force_style='FontName={font_file},FontSize={font_size},"
                  f"PrimaryColour={self._convert_color_to_ass(font_color)},"
                  f"OutlineColour={self._convert_color_to_ass(outline_color)},"
                  f"BorderStyle=1,Outline={outline_width},Shadow=0'",
            "-c:a", "copy",
            "-y",
            output_file
        ]
        
        logger.info(f"运行FFmpeg命令添加字幕...")
        
        # 执行命令
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
            shell=(platform.system() == "Windows")
        )
        
        logger.info(f"已成功添加字幕，输出文件: {output_file}")
        return output_file
    
    def _convert_color_to_ass(self, color: str) -> str:
        """将颜色名称转换为ASS格式的颜色代码
        
        Args:
            color: 颜色名称或十六进制颜色代码
            
        Returns:
            ASS格式的颜色代码
        """
        # 常见颜色映射
        color_map = {
            "white": "&HFFFFFF&",
            "black": "&H000000&",
            "red": "&H0000FF&",
            "green": "&H00FF00&",
            "blue": "&HFF0000&",
            "yellow": "&H00FFFF&"
        }
        
        # 检查是否为已知颜色名称
        if color.lower() in color_map:
            return color_map[color.lower()]
        
        # 尝试解析16进制颜色代码 (#RRGGBB)
        if color.startswith("#") and len(color) == 7:
            r = int(color[1:3], 16)
            g = int(color[3:5], 16)
            b = int(color[5:7], 16)
            # ASS格式为 &HBBGGRR&
            return f"&H{b:02X}{g:02X}{r:02X}&"
        
        # 默认返回白色
        logger.warning(f"无法识别的颜色 '{color}'，使用默认值白色")
        return "&HFFFFFF&"
    
    @error_handler(error_message="添加角色图片失败")
    def add_character_image(self, video_file: str, character_image: str, output_file: str) -> str:
        """为视频添加角色图片
        
        Args:
            video_file: 视频文件路径
            character_image: 角色图片文件路径
            output_file: 输出视频文件路径
            
        Returns:
            生成的视频文件路径
        """
        # 确保输出目录存在
        output_dir = os.path.dirname(output_file)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)
        
        # 确保文件存在
        if not os.path.exists(video_file):
            raise FileError(f"视频文件不存在: {video_file}")
        
        if not os.path.exists(character_image):
            raise FileError(f"角色图片不存在: {character_image}")
        
        logger.info(f"在视频 {video_file} 上添加角色图片 {character_image}")
        
        return self._with_retry(
            self._add_character_image_ffmpeg,
            video_file,
            character_image,
            output_file,
            error_msg=f"在视频 {video_file} 上添加角色图片失败"
        )
    
    def _add_character_image_ffmpeg(self, video_file: str, character_image: str, output_file: str) -> str:
        """使用FFmpeg为视频添加角色图片
        
        Args:
            video_file: 视频文件路径
            character_image: 角色图片文件路径
            output_file: 输出视频文件路径
            
        Returns:
            生成的视频文件路径
        """
        # 确定视频分辨率
        cmd_probe = [
            "ffprobe",
            "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height",
            "-of", "json",
            video_file
        ]
        
        result = subprocess.run(
            cmd_probe,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
            shell=(platform.system() == "Windows")
        )
        
        video_info = json.loads(result.stdout)
        if 'streams' in video_info and video_info['streams']:
            width = int(video_info['streams'][0]['width'])
            height = int(video_info['streams'][0]['height'])
        else:
            width = 1920
            height = 1080
            logger.warning(f"无法获取视频分辨率，使用默认值 {width}x{height}")
        
        # 角色图片位置和大小设置
        overlay_width = width // 4  # 角色图片宽度为视频宽度的1/4
        position_x = width - overlay_width - 20  # 距离右边界20像素
        position_y = height - overlay_width - 20  # 距离底部20像素，假设图片为正方形
        
        # 构建FFmpeg命令
        cmd = [
            "ffmpeg",
            "-i", video_file,
            "-i", character_image,
            "-filter_complex", 
                f"[1:v]scale={overlay_width}:-1,format=rgba[overlay]; " +
                f"[0:v][overlay]overlay={position_x}:{position_y}:format=auto",
            "-c:a", "copy",
            "-y",
            output_file
        ]
        
        logger.info(f"运行FFmpeg命令添加角色图片...")
        
        # 执行命令
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
            shell=(platform.system() == "Windows")
        )
        
        logger.info(f"已成功添加角色图片，输出文件: {output_file}")
        return output_file

    def get_video_duration(self, video_file):
        """获取视频时长
        
        Args:
            video_file: 视频文件路径
            
        Returns:
            float: 视频时长（秒）
        """
        try:
            # 使用FFmpeg获取视频信息
            cmd = [
                "ffprobe",
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "json",
                video_file
            ]
            
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            
            if result.returncode != 0:
                print(f"获取视频时长失败: {result.stderr}")
                return 0
            
            # 解析JSON输出
            data = json.loads(result.stdout)
            duration = float(data["format"]["duration"])
            return duration
            
        except Exception as e:
            print(f"获取视频时长时出错: {e}")
            return 0

# 兼容旧版本的函数
def create_base_video(audio_info_file, output_file, resolution=(1920, 1080)):
    """兼容旧版本的函数，使用默认引擎创建基础视频"""
    processor = VideoProcessor()
    return processor.create_base_video(audio_info_file, output_file)

def create_video_with_scenes_moviepy(key_scenes_file, input_video, output_file):
    """兼容旧版本的函数，使用MoviePy引擎创建视频"""
    processor = VideoProcessor(engine="moviepy")
    return processor.create_video_with_scenes(key_scenes_file, input_video, output_file)

def create_video_with_scenes_ffmpeg(key_scenes_file, input_video, output_file, batch_size=5):
    """兼容旧版本的函数，使用FFmpeg引擎创建视频"""
    processor = VideoProcessor(engine="ffmpeg")
    return processor._create_video_with_scenes_ffmpeg(key_scenes_file, input_video, output_file, batch_size)

# 主程序入口点
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="视频处理工具")
    parser.add_argument("--engine", choices=["ffmpeg", "moviepy", "auto"], default="auto",
                        help="选择视频处理引擎 (默认: auto)")
    parser.add_argument("--audio_info", default="output/audio/audio_info.json",
                        help="音频信息文件路径")
    parser.add_argument("--scenes", default="output/key_scenes.json",
                        help="场景信息JSON文件路径")
    parser.add_argument("--base_video", default="output/base_video.mp4",
                        help="基础视频输出路径")
    parser.add_argument("--output", default="output/final_video.mp4",
                        help="最终视频输出路径")
    parser.add_argument("--skip_base", action="store_true",
                        help="跳过基础视频生成步骤")
    
    args = parser.parse_args()
    
    # 创建视频处理器
    processor = VideoProcessor(engine=args.engine)
    
    # 处理视频
    if not args.skip_base:
        logger.info("步骤1: 创建基础视频...")
        processor.create_base_video(args.audio_info, args.base_video)
    
    logger.info("\n步骤2: 创建最终视频...")
    processor.create_video_with_scenes(args.scenes, args.base_video, args.output)
    
    logger.info(f"\n处理完成! 最终视频已保存至: {args.output}") 