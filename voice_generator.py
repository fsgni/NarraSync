"""语音生成服务模块

提供与VOICEVOX引擎和OpenAI TTS API的交互功能，实现文本到语音的转换。
"""
import requests
import json
import wave
import time
import os
import asyncio
from pathlib import Path
from typing import Dict, Any, Optional, List, Union, Callable, TypeVar

# 导入新架构组件
from config import config
from errors import get_logger, error_handler, VoiceVoxError, ProcessingError
from services import VoiceGeneratorService, ServiceFactory

# 导入OpenAI SDK
from openai import OpenAI
try:
    from openai import AsyncOpenAI
    from openai.helpers import LocalAudioPlayer
    ASYNC_OPENAI_AVAILABLE = True
except ImportError:
    ASYNC_OPENAI_AVAILABLE = False

# 获取日志记录器
logger = get_logger("voice_generator")

# 定义泛型类型变量，用于with_retry方法
T = TypeVar('T')

class OpenAITTSGenerator(VoiceGeneratorService):
    """OpenAI TTS语音生成器实现"""
    
    # 预设语音指令配置
    VOICE_PRESETS = {
        "default": "",
        "storyteller": """
            Accent/Affect: Warm, refined, and gently instructive, reminiscent of a friendly art instructor.

            Tone: Calm, encouraging, and articulate, clearly describing each step with patience.

            Pacing: Slow and deliberate, pausing often to allow the listener to follow instructions comfortably.

            Emotion: Cheerful, supportive, and pleasantly enthusiastic; convey genuine enjoyment and appreciation of art.

            Pronunciation: Clearly articulate artistic terminology (e.g., "brushstrokes," "landscape," "palette") with gentle emphasis.

            Personality Affect: Friendly and approachable with a hint of sophistication; speak confidently and reassuringly, guiding users through each painting step patiently and warmly.
        """,
        "formal": """
            Voice Affect: Measured, articulate, and precise; project professionalism and clarity.
            
            Tone: Authoritative, informative, and composed—present information with objectivity and expertise.
            
            Pacing: Even and methodical; maintain consistent rhythm appropriate for formal communication.
            
            Emotion: Controlled and restrained; prioritize clarity of information over emotional expression.
            
            Pronunciation: Crisp and precise articulation of all syllables; particular attention to technical terms.
            
            Pauses: Strategic pauses between major points or sections, highlighting structure and aiding comprehension.
        """,
        "cheerful": """
            Voice Affect: Bright, energetic, and uplifting; project enthusiasm and positivity.
            
            Tone: Warm, friendly, and inviting—speak with genuine delight and encouragement.
            
            Pacing: Lively and buoyant; slightly faster than average with dynamic variations.
            
            Emotion: Expressive joy and excitement; convey a sense of optimism and good humor.
            
            Pronunciation: Clear with natural inflection rising on positive words; emphasize pleasant descriptors.
            
            Pauses: Brief, natural pauses that maintain energy while avoiding rushing; slight pause before particularly positive points.
        """
    }
    
    def __init__(self, api_key=None, model=None):
        """初始化OpenAI TTS生成器
        
        Args:
            api_key: OpenAI API密钥，默认从配置获取
            model: TTS模型，默认从配置获取
        """
        # 尝试导入dotenv以支持.env文件
        try:
            from dotenv import load_dotenv
            # 加载.env文件中的环境变量
            load_dotenv()
            logger.debug("已从.env文件加载环境变量")
        except ImportError:
            pass  # 忽略导入错误，不影响主要功能
            
        # 从配置获取参数，如果未指定
        self.api_key = api_key or os.getenv("OPENAI_API_KEY") or config.get("services", "openai", "api_key", default="")
        self.model = model or config.get("services", "openai", "tts_model", default="gpt-4o-mini-tts")
        
        if not self.api_key:
            logger.warning("未设置OpenAI API密钥，请在配置中设置services.openai.api_key或添加OPENAI_API_KEY环境变量")
        else:
            logger.debug("成功获取OpenAI API密钥")
        
        # 重试配置
        self.max_retries = config.get("processing", "max_retries", default=3)
        self.retry_delay = config.get("processing", "retry_delay", default=1.0)
        
        # 创建OpenAI客户端 (同步)
        self.client = OpenAI(api_key=self.api_key)
        
        # 如果可用，创建异步客户端
        self.async_client = None
        if ASYNC_OPENAI_AVAILABLE:
            self.async_client = AsyncOpenAI(api_key=self.api_key)
            logger.debug("异步OpenAI客户端初始化成功")
        
        # OpenAI TTS支持的声音列表
        self.speakers = {
            1: "alloy",
            2: "echo", 
            3: "fable",
            4: "onyx",
            5: "nova",
            6: "shimmer",
            7: "coral"  # 新增的声音
        }
        
        self.speaker = config.get("services", "openai", "default_voice", default=1)
        
        # 当前使用的语音预设
        self.voice_preset = "default"
    
    def list_speakers(self) -> Dict[int, str]:
        """列出所有可用的说话人
        
        Returns:
            说话人字典，ID到名称的映射
        """
        return self.speakers
    
    def set_speaker(self, speaker_id: int) -> bool:
        """设置当前说话人
        
        Args:
            speaker_id: 说话人ID
            
        Returns:
            是否设置成功
        """
        if speaker_id in self.speakers:
            self.speaker = speaker_id
            logger.debug(f"已设置OpenAI TTS说话人: {speaker_id} ({self.speakers.get(speaker_id, '未知')})")
            return True
        else:
            logger.warning(f"无效的OpenAI TTS说话人ID: {speaker_id}")
            return False
    
    def set_voice_preset(self, preset_name: str) -> bool:
        """设置语音预设
        
        Args:
            preset_name: 预设名称
            
        Returns:
            是否设置成功
        """
        if preset_name in self.VOICE_PRESETS:
            self.voice_preset = preset_name
            logger.debug(f"已设置语音预设: {preset_name}")
            return True
        else:
            available_presets = ", ".join(self.VOICE_PRESETS.keys())
            logger.warning(f"无效的语音预设: {preset_name}，可用预设: {available_presets}")
            return False
    
    def get_voice_instructions(self, preset_name: Optional[str] = None) -> str:
        """获取语音指令
        
        Args:
            preset_name: 预设名称，如果为None则使用当前预设
            
        Returns:
            语音指令文本
        """
        preset = preset_name or self.voice_preset
        return self.VOICE_PRESETS.get(preset, "")
    
    def _with_retry(self, func: Callable[..., T], *args, error_msg: str = "操作失败", **kwargs) -> T:
        """带有重试功能的函数调用
        
        Args:
            func: 要调用的函数
            *args: 函数参数
            error_msg: 错误消息前缀
            **kwargs: 函数关键字参数
            
        Returns:
            函数调用结果
            
        Raises:
            ProcessingError: 如果所有重试都失败
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
            raise ProcessingError(f"{error_msg}，重试次数已用尽", details={"last_error": str(last_error)})
        else:
            raise ProcessingError(f"{error_msg}，未知错误")

    def _ensure_output_dir(self, output_path: str) -> None:
        """确保输出目录存在
        
        Args:
            output_path: 输出文件路径
        """
        output_dir = os.path.dirname(output_path)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)
            logger.debug(f"已创建输出目录: {output_dir}")

    def _get_file_paths(self, output_path: str) -> tuple[str, str]:
        """获取MP3和WAV文件路径
        
        Args:
            output_path: 原始输出路径
            
        Returns:
            (MP3文件路径, WAV文件路径)
        """
        # 确保output_path是字符串
        output_path = str(output_path)
        
        # 如果目标是WAV，将临时文件保存为MP3
        if output_path.lower().endswith('.wav'):
            temp_mp3_path = output_path[:-4] + '.mp3'
            final_wav_path = output_path
        else:
            # 如果目标不是WAV，指定WAV路径
            temp_mp3_path = output_path
            final_wav_path = output_path.rsplit('.', 1)[0] + '.wav'
        
        return temp_mp3_path, final_wav_path

    def _convert_mp3_to_wav(self, mp3_path: str, wav_path: str) -> float:
        """将MP3转换为WAV并返回音频时长
        
        Args:
            mp3_path: MP3文件路径
            wav_path: WAV文件路径
            
        Returns:
            音频时长（秒）
        """
        try:
            # 尝试使用pydub
            try:
                from pydub import AudioSegment
                audio = AudioSegment.from_file(mp3_path)
                audio.export(wav_path, format="wav")
                
                # 删除临时MP3文件
                if os.path.exists(wav_path) and mp3_path != wav_path:
                    os.remove(mp3_path)
                    logger.debug(f"已删除临时MP3文件: {mp3_path}")
                
                # 使用辅助方法获取WAV时长
                return self._get_wav_duration(wav_path)
            except ImportError:
                # 如果pydub不可用，尝试使用ffmpeg
                try:
                    import subprocess
                    
                    # 使用ffmpeg转换为WAV
                    cmd = ['ffmpeg', '-i', mp3_path, '-y', wav_path]
                    subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    
                    # 删除临时MP3文件
                    if os.path.exists(wav_path) and mp3_path != wav_path:
                        os.remove(mp3_path)
                        logger.debug(f"已使用ffmpeg将MP3转换为WAV格式: {wav_path}")
                    
                    # 使用辅助方法获取WAV时长
                    return self._get_wav_duration(wav_path)
                except Exception as ffmpeg_err:
                    logger.warning(f"使用ffmpeg转换失败: {ffmpeg_err}")
                    
                    # 如果目标是WAV但只生成了MP3，尝试直接重命名
                    if mp3_path != wav_path:
                        try:
                            import shutil
                            shutil.copy(mp3_path, wav_path)
                            logger.debug(f"已将MP3文件复制为WAV文件: {wav_path}")
                        except Exception as copy_err:
                            logger.warning(f"复制文件失败: {copy_err}")
                    
                    # 使用估算方法
                    return self._estimate_duration_from_chars(None)
        except Exception as e:
            logger.warning(f"获取音频时长时出错: {e}，使用估算值")
            # 简单估计
            return self._estimate_duration_from_chars(None)

    def _estimate_duration_from_chars(self, text: Optional[str]) -> float:
        """根据文本字符估算音频时长
        
        Args:
            text: 文本内容，如果为None则返回默认时长
            
        Returns:
            估计的音频时长（秒）
        """
        if not text:
            return 3.0
            
        char_count = len(text)
        chinese_char_count = sum(1 for char in text if '\u4e00' <= char <= '\u9fff')
        chinese_ratio = chinese_char_count / char_count if char_count > 0 else 0
        estimated_duration = char_count * (0.3 * chinese_ratio + 0.1 * (1 - chinese_ratio))
        logger.debug(f"估算音频时长: {estimated_duration:.2f}秒 (中文比例: {chinese_ratio:.2f})")
        return estimated_duration

    async def _synthesize_async(self, text: str, output_path: str, voice: str, model: str, instructions: Optional[str] = None):
        """异步方式生成语音
        
        Args:
            text: 文本内容
            output_path: 输出文件路径
            voice: 声音名称
            model: 模型名称
            instructions: 语音指令
            
        Returns:
            音频时长（秒）
        """
        if not self.async_client:
            raise ProcessingError("异步OpenAI客户端不可用，请确保安装了最新版本的openai包")
        
        # 确保输出目录存在
        self._ensure_output_dir(output_path)
        
        # 获取文件路径
        temp_mp3_path, final_wav_path = self._get_file_paths(output_path)
        
        # 准备参数
        kwargs = {
            "model": model,
            "voice": voice,
            "input": text,
            "response_format": "mp3"  # 使用mp3格式输出
        }
        
        if instructions:
            kwargs["instructions"] = instructions
        
        # 异步创建语音并保存到临时MP3文件
        try:
            async with self.async_client.audio.speech.with_streaming_response.create(**kwargs) as response:
                with open(temp_mp3_path, 'wb') as f:
                    async for chunk in response.iter_bytes():
                        f.write(chunk)
            
            logger.debug(f"已保存语音到临时MP3文件: {temp_mp3_path}")
            
            # 将MP3转换为WAV并获取时长
            try:
                # 尝试使用pydub
                return self._convert_mp3_to_wav(temp_mp3_path, final_wav_path)
            except ImportError:
                logger.warning("无法导入pydub库，使用估算音频时长")
                return self._estimate_duration_from_chars(text)
            
        except Exception as e:
            logger.error(f"异步语音合成失败: {e}")
            raise

    def synthesize(self, text: str, output_path: str, speaker_id: Optional[int] = None, speed_scale: float = 1.0) -> float:
        """生成语音
        
        Args:
            text: 文本内容
            output_path: 输出文件路径
            speaker_id: 说话人ID
            speed_scale: 语速调整，1.0为默认值
            
        Returns:
            音频时长（秒）
        """
        speaker_id = speaker_id or self.speaker
        voice = self.speakers.get(speaker_id, "alloy")
        
        # 获取语音指令
        instructions = None
        if self.voice_preset != "default":
            instructions = self.get_voice_instructions()
            logger.debug(f"使用当前预设语音指令: {self.voice_preset}")
        
        # 记录语音合成信息
        logger.info(f"使用OpenAI TTS合成语音，声音: {voice}{' (带指令)' if instructions else ''}")
        
        # 确保output_path是字符串
        output_path = str(output_path)
        
        # 如果有异步客户端并且模型支持，尝试使用异步API
        if self.async_client and "gpt-4o" in self.model:
            try:
                logger.debug(f"使用异步API合成语音，模型: {self.model}")
                loop = asyncio.get_event_loop()
                duration = loop.run_until_complete(
                    self._synthesize_async(text, output_path, voice, self.model, instructions)
                )
                logger.info(f"异步语音合成成功，时长: {duration:.2f}秒")
                return duration
            except Exception as e:
                logger.warning(f"异步语音合成失败，将尝试同步API: {e}")
                # 继续使用同步API
        
        # 使用同步API
        def _synthesize_speech():
            # 准备API参数
            kwargs = {
                "model": self.model,
                "voice": voice,
                "input": text,
                "response_format": "mp3"  # 使用MP3格式，更通用
            }
            
            # 尝试使用instructions参数
            try:
                if instructions:
                    kwargs["instructions"] = instructions
                response = self.client.audio.speech.create(**kwargs)
            except Exception as e:
                # 如果API不支持instructions参数或有其他错误
                if "unexpected keyword" in str(e) and "instructions" in str(e):
                    logger.warning("当前OpenAI API版本不支持instructions参数，将忽略语音预设")
                    if "instructions" in kwargs:
                        del kwargs["instructions"]
                    response = self.client.audio.speech.create(**kwargs)
                else:
                    # 如果是其他错误，则重新抛出
                    raise
            
            # 确保输出目录存在
            self._ensure_output_dir(output_path)
            
            # 获取文件路径
            temp_mp3_path, final_wav_path = self._get_file_paths(output_path)
            
            # 保存到临时MP3文件
            response.stream_to_file(temp_mp3_path)
            logger.debug(f"已保存语音到临时MP3文件: {temp_mp3_path}")
            
            # 将MP3转换为WAV并获取时长
            return self._convert_mp3_to_wav(temp_mp3_path, final_wav_path)
        
        # 执行带重试的合成操作
        try:
            duration = self._with_retry(_synthesize_speech, error_msg="OpenAI TTS语音合成失败")
            logger.info(f"语音合成成功，时长: {duration:.2f}秒")
            return duration
        except Exception as e:
            logger.error(f"OpenAI TTS语音合成失败: {e}")
            # 如果出错则返回估计的时长
            estimated_duration = self._estimate_duration_from_chars(text)
            logger.warning(f"返回估计的音频时长: {estimated_duration:.2f}秒")
            return estimated_duration
    
    def process_text_with_voices(self, text: str, voice_mapping: Dict[str, int]) -> float:
        """使用多个角色处理文本（在OpenAI TTS中不支持，使用默认声音）
        
        Args:
            text: 文本内容，可能包含角色标记
            voice_mapping: 角色到声音ID的映射
            
        Returns:
            总音频时长（秒）
        """
        logger.warning("OpenAI TTS不支持多角色处理，将使用默认声音")
        return self.synthesize(text, "output/audio/combined_audio.wav")
    
    def batch_synthesize(self, texts: List[str], output_dir: str, 
                     filename_pattern: str = "audio_{:03d}.wav",
                     speaker_id: Optional[int] = None,
                     voice_preset: Optional[str] = None) -> Dict[str, Any]:
        """批量合成语音
        
        Args:
            texts: 文本列表
            output_dir: 输出目录
            filename_pattern: 文件名模式
            speaker_id: 说话人ID
            voice_preset: 语音预设名称
            
        Returns:
            包含合成结果的字典
        """
        # 确保输出目录存在
        os.makedirs(output_dir, exist_ok=True)
        
        results = []
        total_duration = 0.0
        
        # 如果是讲故事场景，使用storyteller预设
        current_preset = voice_preset or self.voice_preset
        if not voice_preset:
            logger.info("批量语音合成默认使用storyteller预设")
            current_preset = "storyteller"
        
        for i, text in enumerate(texts):
            if not text.strip():
                logger.debug(f"跳过空文本 #{i+1}")
                continue
                
            output_file = os.path.join(output_dir, filename_pattern.format(i))
            
            try:
                logger.info(f"合成文本 #{i+1}: {text[:30]}...")
                duration = self.synthesize(
                    text, 
                    output_file, 
                    speaker_id,
                    voice_preset=current_preset
                )
                
                results.append({
                    "index": i,
                    "text": text,
                    "file": output_file,
                    "duration": duration
                })
                
                total_duration += duration
                logger.debug(f"文本 #{i+1} 合成完成，时长: {duration:.2f}秒")
                
            except Exception as e:
                logger.error(f"合成文本 #{i+1} 时出错: {e}")
                # 继续处理下一个文本
        
        logger.info(f"批量合成完成，共 {len(results)} 个文件，总时长: {total_duration:.2f}秒")
        
        return {
            "files": results,
            "total_duration": total_duration,
            "output_dir": output_dir
        }

    def _get_wav_duration(self, wav_file_path: str) -> float:
        """获取WAV文件的播放时长
        
        Args:
            wav_file_path: WAV文件路径
            
        Returns:
            音频时长（秒）
        """
        try:
            # 确保是字符串路径
            wav_file_path = str(wav_file_path)
            
            with wave.open(wav_file_path, 'rb') as wav_file:
                frames = wav_file.getnframes()
                rate = wav_file.getframerate()
                duration = frames / float(rate)
                logger.debug(f"WAV文件时长: {duration:.2f}秒")
                return duration
        except Exception as e:
            logger.warning(f"无法读取WAV文件时长: {e}")
            # 通过文件大小估算
            try:
                file_size = os.path.getsize(wav_file_path)
                # WAV文件每秒约占用176KB (16位, 44.1kHz, 立体声)
                estimated_duration = file_size / (176 * 1024)
                logger.debug(f"通过文件大小估算WAV时长: {estimated_duration:.2f}秒")
                return estimated_duration
            except Exception:
                # 如果无法获取文件大小，返回默认值
                return 3.0

# 注册服务类
ServiceFactory.register("openai_tts", OpenAITTSGenerator)

class VoiceVoxGenerator(VoiceGeneratorService):
    """VOICEVOX语音生成器实现"""
    
    def __init__(self, host=None, port=None, speaker=None):
        """初始化语音生成器
        
        Args:
            host: VOICEVOX服务器主机，默认从配置获取
            port: VOICEVOX服务器端口，默认从配置获取
            speaker: 默认说话人ID，默认从配置获取
        """
        # 从配置获取参数，如果未指定
        self.host = host or config.get("services", "voicevox", "host", default="127.0.0.1")
        self.port = port or config.get("services", "voicevox", "port", default="50021")
        self.base_url = f"http://{self.host}:{self.port}"
        self.speaker = speaker or config.get("services", "voicevox", "default_speaker", default=13)
        
        # 重试配置
        self.max_retries = config.get("processing", "max_retries", default=3)
        self.retry_delay = config.get("processing", "retry_delay", default=1.0)
        self.timeout = config.get("processing", "timeout", default=10.0)
        
        # VOICEVOX 角色列表
        self.speakers = {
            1: "四国めたん",
            2: "ずんだもん",
            3: "春日部つむぎ",
            4: "雨晴はう",
            7: "小夜/SAYO",
            8: "ナースロボ＿タイプＴ",
            9: "春歌ナナ",
            10: "波音リツ",
            11: "玄野武宏",
            12: "白上虎太郎",
            13: "青山龍星",
            14: "冥鳴ひまり",
            15: "九州そら",
            16: "もち子さん",
            17: "剣崎雌雄"
        }
    
        # 临时文件路径
        self.temp_dir = Path(config.get("paths", "temp", default="temp"))
        os.makedirs(self.temp_dir, exist_ok=True)
        
        # 检查服务是否可用
        self._check_service_available()
    
    def _check_service_available(self):
        """检查VOICEVOX服务是否可用"""
        try:
            response = requests.get(f"{self.base_url}/version", timeout=self.timeout)
            if response.status_code == 200:
                version = response.text.strip('"')
                logger.info(f"VOICEVOX服务可用，版本: {version}")
                return True
            else:
                logger.warning(f"VOICEVOX服务响应异常: {response.status_code}")
                return False
        except Exception as e:
            logger.warning(f"VOICEVOX服务不可用: {e}")
            return False
    
    def list_speakers(self) -> Dict[int, str]:
        """列出所有可用的说话人
        
        Returns:
            说话人字典，ID到名称的映射
        """
        try:
            # 尝试从服务器获取最新的说话人列表
            response = requests.get(f"{self.base_url}/speakers", timeout=self.timeout)
            if response.status_code == 200:
                speakers_data = response.json()
                speakers = {}
                for speaker_info in speakers_data:
                    speaker_id = speaker_info.get("speaker_id")
                    speaker_name = speaker_info.get("name")
                    if speaker_id is not None and speaker_name:
                        speakers[speaker_id] = speaker_name
                
                if speakers:
                    self.speakers = speakers
                    logger.debug(f"从服务器获取到 {len(speakers)} 个说话人")
        except Exception as e:
            logger.warning(f"获取说话人列表失败: {e}，使用内置列表")
        
        return self.speakers
    
    def set_speaker(self, speaker_id: int) -> bool:
        """设置当前说话人
        
        Args:
            speaker_id: 说话人ID
            
        Returns:
            是否设置成功
        """
        if speaker_id in self.speakers:
            self.speaker = speaker_id
            logger.debug(f"已设置说话人: {speaker_id} ({self.speakers.get(speaker_id, '未知')})")
            return True
        else:
            logger.warning(f"无效的说话人ID: {speaker_id}")
        return False
    
    def _with_retry(self, func: Callable[..., T], *args, error_msg: str = "操作失败", **kwargs) -> T:
        """带有重试功能的函数调用
        
        Args:
            func: 要调用的函数
            *args: 函数参数
            error_msg: 错误消息前缀
            **kwargs: 函数关键字参数
            
        Returns:
            函数调用结果
            
        Raises:
            VoiceVoxError: 如果所有重试都失败
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
            raise VoiceVoxError(f"{error_msg}，重试次数已用尽", details={"last_error": str(last_error)})
        else:
            raise VoiceVoxError(f"{error_msg}，未知错误")
    
    def _ensure_output_dir(self, output_path: str) -> None:
        """确保输出目录存在
        
        Args:
            output_path: 输出文件路径
        """
        output_dir = os.path.dirname(output_path)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)
            logger.debug(f"已创建输出目录: {output_dir}")
    
    def _create_temp_path(self, suffix=".wav") -> Path:
        """创建临时文件路径
        
        Args:
            suffix: 文件后缀
            
        Returns:
            临时文件路径
        """
        timestamp = int(time.time() * 1000)
        random_part = os.urandom(4).hex()
        filename = f"temp_{timestamp}_{random_part}{suffix}"
        return self.temp_dir / filename
    
    def _cleanup_temp_file(self, file_path: Path) -> None:
        """清理临时文件
        
        Args:
            file_path: 文件路径
        """
        if file_path.exists():
            try:
                file_path.unlink()
                logger.debug(f"已删除临时文件: {file_path}")
            except Exception as e:
                logger.warning(f"删除临时文件失败: {e}")
    
    def _get_audio_from_query(self, query: Dict[str, Any], speaker: int) -> bytes:
        """从查询参数获取音频数据
        
        Args:
            query: 音频查询参数
            speaker: 说话人ID
            
        Returns:
            音频二进制数据
            
        Raises:
            VoiceVoxError: 如果获取音频失败
        """
        params = {"speaker": speaker}
        headers = {"Content-Type": "application/json"}
        response = requests.post(
            f"{self.base_url}/synthesis",
            params=params,
            data=json.dumps(query),
            headers=headers,
            timeout=self.timeout
        )
        
        if response.status_code != 200:
            raise VoiceVoxError(f"合成音频失败: HTTP {response.status_code}")
        
        return response.content
    
    def get_audio_query(self, text, speaker=None) -> Dict[str, Any]:
        """获取音频查询参数
        
        Args:
            text: 要合成的文本
            speaker: 说话人ID，默认使用当前说话人
            
        Returns:
            音频查询参数
            
        Raises:
            VoiceVoxError: 如果获取查询参数失败
        """
        speaker = speaker or self.speaker
        
        # 定义内部函数用于重试
        def _get_query():
            params = {"text": text, "speaker": speaker}
            response = requests.post(
                f"{self.base_url}/audio_query", 
                params=params,
                timeout=self.timeout
            )
            
            if response.status_code != 200:
                raise VoiceVoxError(f"获取音频查询参数失败: HTTP {response.status_code}")
            
            return response.json()
        
        # 执行带重试的操作
        return self._with_retry(_get_query, error_msg="获取音频查询参数失败")
    
    def get_audio_duration(self, text, speaker=None, speed_scale: float = 1.0) -> Optional[float]:
        """获取音频时长（秒）
        
        Args:
            text: 要合成的文本
            speaker: 说话人ID，默认使用当前说话人
            speed_scale: 语速调整，1.0为默认值
            
        Returns:
            音频时长，如果失败则返回None
        """
        speaker = speaker or self.speaker
        temp_path = self._create_temp_path()
        
        try:
            # 获取音频查询参数
            query = self.get_audio_query(text, speaker)
            
            # Modify query for speed for accurate duration estimation if needed
            # For now, we assume default speed for duration check, or rely on synthesize's output.
            # If exact duration *with speed* is needed beforehand, modify query here:
            # query["speedScale"] = speed_scale
            
            # 获取音频并保存到临时文件
            audio_data = self._with_retry(
                self._get_audio_from_query, 
                query, 
                speaker, 
                error_msg="合成临时音频失败"
            )
            temp_path.write_bytes(audio_data)
            
            # 从音频文件读取实际时长
            with wave.open(str(temp_path), 'rb') as wav_file:
                frames = wav_file.getnframes()
                rate = wav_file.getframerate()
                duration = frames / float(rate)
            
            logger.debug(f"获取到音频时长: {duration:.2f}秒")
            return duration
            
        except Exception as e:
            logger.error(f"获取音频时长失败: {e}")
            return None
        finally:
            # 清理临时文件
            self._cleanup_temp_file(temp_path)
    
    def synthesize(self, text: str, output_path: str, speaker_id: Optional[int] = None, speed_scale: float = 1.0) -> float:
        """生成语音并返回时长
        
        Args:
            text: 要合成的文本
            output_path: 输出文件路径
            speaker_id: 说话人ID，默认使用当前说话人
            speed_scale: 语速调整，1.0为默认值
            
        Returns:
            音频时长（秒）
            
        Raises:
            VoiceVoxError: 如果语音合成失败
        """
        # 确保输出目录存在
        self._ensure_output_dir(output_path)
        
        speaker = speaker_id or self.speaker
        
        try:
            # 获取音频查询参数
            query = self.get_audio_query(text, speaker)
            
            # ---> Modify the query object to set the speed <--- 
            query["speedScale"] = speed_scale 
            logger.debug(f"设置语速 speedScale: {speed_scale}")
            
            # 获取音频并保存到输出文件
            audio_data = self._with_retry(
                self._get_audio_from_query, 
                query, 
                speaker, 
                error_msg=f"合成音频失败: {text[:20]}..."
            )
            Path(output_path).write_bytes(audio_data)
            
            # 获取实际音频时长
            with wave.open(str(output_path), 'rb') as wav_file:
                frames = wav_file.getnframes()
                rate = wav_file.getframerate()
                duration = frames / float(rate)
            
            logger.info(f"成功生成音频: {os.path.basename(output_path)}, 时长: {duration:.2f}秒")
            return duration
                
        except Exception as e:
            # 如果是VoiceVoxError，直接抛出
            if isinstance(e, VoiceVoxError):
                raise
            
            # 其他异常包装为VoiceVoxError
            raise VoiceVoxError(f"生成音频失败: {text[:20]}...", details={"error": str(e)})
    
    def process_text_with_voices(self, text: str, voice_mapping: Dict[str, int]) -> float:
        """处理带有说话者标记的文本，使用不同的声音
        
        Args:
            text: 文本内容
            voice_mapping: 说话者到声音ID的映射
            
        Returns:
            音频时长（秒）
        """
        # 这是未完成的功能，仅提供基本实现
        current_speaker = "narrator"
        
        # 识别说话者和对话
        if text.startswith("「") or text.startswith("『"):
            # 这里可以添加更复杂的逻辑来识别说话者
            logger.debug("检测到对话，但未能确定说话者")
        
        # 使用对应的声音ID
        speaker_id = voice_mapping.get(current_speaker, self.speaker)
        logger.debug(f"使用说话者 '{current_speaker}' (ID: {speaker_id}) 处理文本")
        
        # 生成临时文件路径
        temp_output = os.path.join(
            config.get("paths", "output_audio", default="output/audio"),
            f"temp_{int(time.time())}.wav"
        )
        
        # 合成音频
        return self.synthesize(text, temp_output, speaker_id)
    
    def batch_synthesize(self, texts: List[str], output_dir: str, 
                     filename_pattern: str = "audio_{:03d}.wav",
                     speaker_id: Optional[int] = None) -> Dict[str, Any]:
        """批量生成多个语音文件
        
        Args:
            texts: 要合成的文本列表
            output_dir: 输出目录
            filename_pattern: 文件名模式，使用格式化字符串
            speaker_id: 说话人ID，默认使用当前说话人
            
        Returns:
            包含音频信息的字典
        """
        # 确保输出目录存在
        if not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)
        
        speaker = speaker_id or self.speaker
        audio_files = []
        total_duration = 0.0
        successful_count = 0
        
        for i, text in enumerate(texts):
            if not text.strip():
                logger.warning(f"跳过空文本: 索引 {i}")
                continue
                
            try:
                # 生成文件名
                filename = filename_pattern.format(i)
                output_path = os.path.join(output_dir, filename)
            
                # 合成音频
                duration = self.synthesize(text, output_path, speaker)
                
                # 记录信息
                audio_files.append({
                    "id": i,
                    "sentence": text,
                    "audio_file": filename,
                    "duration": duration
                })
                
                total_duration += duration
                successful_count += 1
                logger.info(f"已生成音频 {i+1}/{len(texts)}: {filename} (时长: {duration:.2f}秒)")
                
            except Exception as e:
                logger.error(f"生成音频失败 {i}: {e}")
                audio_files.append({
                    "id": i,
                    "sentence": text,
                    "error": str(e)
                })
        
        # 返回批量处理结果
        result = {
            "total_sentences": len(texts),
            "successful_generations": successful_count,
            "total_duration": total_duration,
            "audio_files": audio_files
        }
        
        logger.info(f"批量合成完成: 成功 {successful_count}/{len(texts)}，总时长: {total_duration:.2f}秒")
        return result

# 注册VoiceVox服务
ServiceFactory.register("voicevox", VoiceVoxGenerator) 