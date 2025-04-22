"""服务接口模块

提供各种服务的抽象接口和工厂方法，降低组件间的直接依赖。
"""
from abc import ABC, abstractmethod
import importlib
import inspect
from typing import Dict, Any, Optional, List, Type, TypeVar, Generic, cast

from config import config
from errors import ServiceError, get_logger, error_handler

logger = get_logger("services")

# 泛型类型变量，用于服务工厂类型提示
T = TypeVar('T')

class ServiceFactory(Generic[T]):
    """服务工厂类
    
    提供注册和创建服务的通用机制，可按类型参数实例化为特定服务的工厂
    """
    
    _services: Dict[str, Type[T]] = {}
    
    @classmethod
    def register(cls, service_type: str, service_class: Type[T]) -> None:
        """注册服务类
        
        Args:
            service_type: 服务类型标识
            service_class: 服务实现类
            
        Raises:
            ServiceError: 当服务类型已注册且与新服务类不同时
        """
        if service_type in cls._services and cls._services[service_type] != service_class:
            logger.warning(f"服务类型 '{service_type}' 已被重新注册，从 {cls._services[service_type].__name__} 到 {service_class.__name__}")
        
        cls._services[service_type] = service_class
        logger.debug(f"已注册服务: {service_type} -> {service_class.__name__}")
    
    @classmethod
    @error_handler(error_message="创建服务实例失败")
    def create(cls, service_type: str, **kwargs) -> T:
        """创建服务实例
        
        Args:
            service_type: 服务类型标识
            **kwargs: 传递给服务构造函数的参数
            
        Returns:
            T: 服务实例
            
        Raises:
            ServiceError: 如果指定类型的服务未注册或实例化失败
        """
        if service_type not in cls._services:
            available_services = ", ".join(cls._services.keys()) or "无"
            raise ServiceError(f"未知的服务类型: '{service_type}'，可用服务类型: {available_services}")
        
        service_class = cls._services[service_type]
        
        try:
            # 检查参数是否匹配
            signature = inspect.signature(service_class.__init__)
            # 移除self参数
            parameters = list(signature.parameters.values())[1:]
            
            # 检查必要参数
            required_params = [p.name for p in parameters if p.default == inspect.Parameter.empty and p.name != 'self']
            missing_params = [p for p in required_params if p not in kwargs]
            
            if missing_params:
                raise ServiceError(f"创建 {service_type} 服务实例缺少必要参数: {', '.join(missing_params)}")
            
            # 创建实例
            instance = service_class(**kwargs)
            logger.debug(f"已创建服务实例: {service_type} -> {instance.__class__.__name__}")
            return instance
        except Exception as e:
            if isinstance(e, ServiceError):
                raise
            raise ServiceError(f"创建服务实例 '{service_type}' 失败: {str(e)}")
    
    @classmethod
    def get_service_types(cls) -> List[str]:
        """获取所有注册的服务类型
        
        Returns:
            List[str]: 服务类型列表
        """
        return list(cls._services.keys())

# 图像生成器接口
class ImageGeneratorService(ABC):
    """图像生成服务接口"""
    
    @abstractmethod
    def generate_image(self, prompt: str, output_filename: str, **kwargs) -> str:
        """生成图像
        
        Args:
            prompt: 图像提示词
            output_filename: 输出文件名
            **kwargs: 额外参数
            
        Returns:
            str: 生成的图像文件路径
            
        Raises:
            ServiceError: 当图像生成失败时
        """
        pass
    
    @abstractmethod
    def generate_images(self, key_scenes_file: str, **kwargs) -> List[str]:
        """生成多个场景图像
        
        Args:
            key_scenes_file: 关键场景JSON文件路径
            **kwargs: 额外参数
            
        Returns:
            List[str]: 生成的图像文件路径列表
            
        Raises:
            ServiceError: 当批量图像生成失败时
            FileError: 当关键场景文件不存在或无法读取时
        """
        pass
    
    @abstractmethod
    def get_available_styles(self) -> List[str]:
        """获取可用的风格列表
        
        Returns:
            List[str]: 风格名称列表
        """
        pass
    
    @abstractmethod
    def set_style(self, style: str) -> bool:
        """设置图像生成风格
        
        Args:
            style: 风格名称
            
        Returns:
            bool: 是否设置成功
        """
        pass

# 语音生成器接口
class VoiceGeneratorService(ABC):
    """语音生成服务接口"""
    
    @abstractmethod
    def synthesize(self, text: str, output_path: str, speaker_id: Optional[int] = None) -> float:
        """生成语音
        
        Args:
            text: 文本内容
            output_path: 输出文件路径
            speaker_id: 说话人ID
            
        Returns:
            float: 音频时长（秒）
            
        Raises:
            ServiceError: 当语音生成失败时
            FileError: 当无法写入输出文件时
        """
        pass
    
    @abstractmethod
    def list_speakers(self) -> Dict[int, str]:
        """列出所有可用的说话人
        
        Returns:
            Dict[int, str]: 说话人字典，ID到名称的映射
        """
        pass
    
    @abstractmethod
    def set_speaker(self, speaker_id: int) -> bool:
        """设置当前说话人
        
        Args:
            speaker_id: 说话人ID
            
        Returns:
            bool: 是否设置成功
            
        Raises:
            ServiceError: 当指定的说话人ID不存在时
        """
        pass

# 视频处理服务接口
class VideoProcessorService(ABC):
    """视频处理服务接口"""
    
    @abstractmethod
    def create_base_video(self, audio_info_file: str, output_video: str) -> str:
        """创建基础视频
        
        Args:
            audio_info_file: 音频信息文件路径
            output_video: 输出视频文件路径
            
        Returns:
            str: 生成的视频文件路径
            
        Raises:
            FileError: 当音频信息文件不存在或无法读取时
            ServiceError: 当视频创建失败时
        """
        pass
    
    @abstractmethod
    def create_video_with_scenes(self, key_scenes_file: str, base_video: str, output_video: str) -> str:
        """创建带场景的视频
        
        Args:
            key_scenes_file: 关键场景JSON文件路径
            base_video: 基础视频文件路径
            output_video: 输出视频文件路径
            
        Returns:
            str: 生成的视频文件路径
            
        Raises:
            FileError: 当输入文件不存在时
            ServiceError: 当视频处理失败时
        """
        pass
    
    @abstractmethod
    def add_subtitles(self, video_file: str, srt_file: str, output_file: str, **kwargs) -> str:
        """为视频添加字幕
        
        Args:
            video_file: 视频文件路径
            srt_file: SRT字幕文件路径
            output_file: 输出视频文件路径
            **kwargs: 字幕样式参数
            
        Returns:
            str: 生成的视频文件路径
            
        Raises:
            FileError: 当输入文件不存在时
            ServiceError: 当字幕添加失败时
        """
        pass
    
    @abstractmethod
    def add_character_image(self, video_file: str, character_image: str, output_file: str) -> str:
        """为视频添加角色图片
        
        Args:
            video_file: 视频文件路径
            character_image: 角色图片文件路径
            output_file: 输出视频文件路径
            
        Returns:
            str: 生成的视频文件路径
            
        Raises:
            FileError: 当输入文件不存在时
            ServiceError: 当添加角色图片失败时
        """
        pass

# 服务定位器
class ServiceLocator:
    """服务定位器，用于获取服务实例"""
    
    _instances: Dict[str, Any] = {}
    _initialization_in_progress: Dict[str, bool] = {}  # 用于检测循环依赖
    
    @classmethod
    def _get_service(cls, key: str, creator_func, *args, **kwargs) -> Any:
        """通用服务获取逻辑
        
        Args:
            key: 服务缓存键
            creator_func: 创建服务的函数
            *args, **kwargs: 传递给创建函数的参数
            
        Returns:
            Any: 服务实例
            
        Raises:
            ServiceError: 当发生循环依赖或创建服务失败时
        """
        # 检测循环依赖
        if cls._initialization_in_progress.get(key, False):
            raise ServiceError(f"检测到服务初始化的循环依赖: {key}")
        
        if key not in cls._instances:
            try:
                cls._initialization_in_progress[key] = True
                cls._instances[key] = creator_func(*args, **kwargs)
            except Exception as e:
                if isinstance(e, ServiceError):
                    raise
                raise ServiceError(f"创建服务 '{key}' 失败: {str(e)}")
            finally:
                cls._initialization_in_progress[key] = False
        
        return cls._instances[key]
    
    @classmethod
    @error_handler(error_message="获取图像生成器失败")
    def get_image_generator(cls, generator_type: Optional[str] = None, **kwargs) -> ImageGeneratorService:
        """获取图像生成器
        
        Args:
            generator_type: 生成器类型，如果为None则使用配置中的默认值
            **kwargs: 传递给构造函数的参数
            
        Returns:
            ImageGeneratorService: 图像生成器实例
            
        Raises:
            ServiceError: 当创建图像生成器失败时
        """
        if generator_type is None:
            generator_type = config.get("image", "default_generator", default="comfyui")
            logger.debug(f"使用默认图像生成器类型: {generator_type}")
        
        key = f"image_generator:{generator_type}"
        
        def create_generator():
            # 延迟导入，避免循环依赖
            if generator_type == "comfyui":
                from image_generator import ComfyUIGenerator
                generator_class = ComfyUIGenerator
            elif generator_type == "midjourney":
                from midjourney_generator import MidjourneyGenerator
                generator_class = MidjourneyGenerator
            else:
                raise ServiceError(f"未知的图像生成器类型: {generator_type}")
            
            logger.info(f"创建图像生成器: {generator_type}")
            return generator_class(**kwargs)
        
        return cast(ImageGeneratorService, cls._get_service(key, create_generator))
    
    @classmethod
    @error_handler(error_message="获取语音生成器失败")
    def get_voice_generator(cls, generator_type: Optional[str] = None, **kwargs) -> VoiceGeneratorService:
        """获取语音生成器
        
        Args:
            generator_type: 生成器类型，如果为None则使用配置中的默认值
            **kwargs: 传递给构造函数的参数
            
        Returns:
            VoiceGeneratorService: 语音生成器实例
            
        Raises:
            ServiceError: 当创建语音生成器失败时
        """
        if generator_type is None:
            generator_type = config.get("voice", "default_generator", default="voicevox")
            logger.debug(f"使用默认语音生成器类型: {generator_type}")
        
        key = f"voice_generator:{generator_type}"
        
        def create_generator():
            # 延迟导入，避免循环依赖
            from voice_generator import VoiceVoxGenerator, OpenAITTSGenerator
            
            if generator_type == "voicevox":
                logger.info(f"创建VoiceVox语音生成器")
                return VoiceVoxGenerator(**kwargs)
            elif generator_type == "openai_tts":
                logger.info(f"创建OpenAI TTS语音生成器")
                return OpenAITTSGenerator(**kwargs)
            else:
                raise ServiceError(f"未知的语音生成器类型: {generator_type}")
        
        return cast(VoiceGeneratorService, cls._get_service(key, create_generator))
    
    @classmethod
    @error_handler(error_message="获取视频处理器失败")
    def get_video_processor(cls, engine: Optional[str] = None, **kwargs) -> VideoProcessorService:
        """获取视频处理器
        
        Args:
            engine: 视频引擎类型，如果为None则使用配置中的默认值
            **kwargs: 传递给构造函数的参数
            
        Returns:
            VideoProcessorService: 视频处理器实例
            
        Raises:
            ServiceError: 当创建视频处理器失败时
        """
        if engine is None:
            engine = config.get("video", "default_engine", default="auto")
            logger.debug(f"使用默认视频引擎: {engine}")
        
        key = f"video_processor:{engine}"
        
        def create_processor():
            # 延迟导入，避免循环依赖
            from video_processor import VideoProcessor
            logger.info(f"创建视频处理器，引擎: {engine}")
            return VideoProcessor(engine=engine, **kwargs)
        
        return cast(VideoProcessorService, cls._get_service(key, create_processor))
    
    @classmethod
    def clear_instances(cls) -> None:
        """清除所有缓存的实例，主要用于测试和重置服务状态"""
        cls._instances.clear()
        cls._initialization_in_progress.clear()
        logger.info("已清除所有服务实例缓存")

# 添加懒加载功能，避免循环导入问题
@error_handler(error_message="加载服务模块失败")
def load_service_modules() -> List[str]:
    """加载所有服务模块
    
    Returns:
        List[str]: 成功加载的模块列表
    """
    modules = [
        "voice_generator",
        "image_generator",
        "midjourney_generator",
        "video_processor"
    ]
    
    loaded_modules = []
    for module_name in modules:
        try:
            importlib.import_module(module_name)
            logger.debug(f"已加载服务模块: {module_name}")
            loaded_modules.append(module_name)
        except ImportError as e:
            logger.warning(f"无法加载服务模块 {module_name}: {e}")
    
    if not loaded_modules:
        logger.warning("未能加载任何服务模块")
    
    return loaded_modules

# 自动加载服务模块
load_service_modules() 