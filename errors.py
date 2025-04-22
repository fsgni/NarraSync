"""错误处理与日志模块

提供统一的异常类层次结构和日志记录功能。
"""
import logging
import sys
import traceback
from typing import Optional, Dict, Any, Union, List, Tuple
from pathlib import Path

# 设置日志格式
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("narra_sync.log", encoding="utf-8")
    ]
)

# 创建根日志器
logger = logging.getLogger("narra_sync")

class NarraSyncError(Exception):
    """所有自定义异常的基类"""
    
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        """初始化异常
        
        Args:
            message: 错误信息
            details: 详细错误信息，可以包含调试数据
        """
        self.message = message
        self.details = details or {}
        super().__init__(message)
    
    def log(self, level: int = logging.ERROR):
        """记录错误日志
        
        Args:
            level: 日志级别
        """
        log_message = f"{self.__class__.__name__}: {self.message}"
        if self.details:
            log_message += f" - Details: {self.details}"
        logger.log(level, log_message)
        
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典，用于API响应
        
        Returns:
            包含错误信息的字典
        """
        return {
            "error": self.__class__.__name__,
            "message": self.message,
            "details": self.details
        }

# 配置错误
class ConfigError(NarraSyncError):
    """配置相关错误"""
    pass

# 服务错误
class ServiceError(NarraSyncError):
    """外部服务访问错误"""
    pass

class VoiceVoxError(ServiceError):
    """VoiceVox服务错误"""
    pass

class ComfyUIError(ServiceError):
    """ComfyUI服务错误"""
    pass

class MidjourneyError(ServiceError):
    """Midjourney服务错误"""
    pass

# 处理错误
class ProcessingError(NarraSyncError):
    """处理过程中的错误"""
    pass

class AudioProcessingError(ProcessingError):
    """音频处理错误"""
    pass

class ImageProcessingError(ProcessingError):
    """图像处理错误"""
    pass

class VideoProcessingError(ProcessingError):
    """视频处理错误"""
    pass

class TextProcessingError(ProcessingError):
    """文本处理错误"""
    pass

# 文件错误
class FileError(NarraSyncError):
    """文件操作错误"""
    pass

class FileNotFoundError(FileError):
    """文件未找到错误"""
    pass

class FileAccessError(FileError):
    """文件访问错误"""
    pass

class FileFormatError(FileError):
    """文件格式错误"""
    pass

# 用于统一处理异常的函数
def handle_exception(exception: Exception, log_level: int = logging.ERROR) -> Dict[str, Any]:
    """处理异常并返回统一格式的错误信息
    
    Args:
        exception: 捕获到的异常
        log_level: 日志级别
        
    Returns:
        统一格式的错误信息字典
    """
    # 如果是我们的自定义异常
    if isinstance(exception, NarraSyncError):
        exception.log(level=log_level)
        return exception.to_dict()
        
    # 其他未知异常
    error_msg = str(exception)
    error_type = exception.__class__.__name__
    error_trace = traceback.format_exc()
    
    logger.log(log_level, f"Unhandled exception: {error_type}: {error_msg}\n{error_trace}")
    
    return {
        "error": error_type,
        "message": error_msg,
        "details": {"traceback": error_trace}
    }

def safe_execute(func, *args, error_message="操作执行失败", log_level=logging.ERROR, **kwargs):
    """安全执行函数并处理异常
    
    Args:
        func: 要执行的函数
        *args: 函数参数
        error_message: 错误消息前缀
        log_level: 日志级别
        **kwargs: 函数关键字参数
        
    Returns:
        函数返回值或错误信息
    """
    try:
        return func(*args, **kwargs)
    except Exception as e:
        error_info = handle_exception(e, log_level=log_level)
        error_detail = f"{error_message}: {error_info['message']}"
        logger.log(log_level, error_detail)
        return {"error": error_detail}

# 日志辅助函数
def get_logger(name: str) -> logging.Logger:
    """获取指定名称的日志器
    
    Args:
        name: 日志器名称，通常为模块名
        
    Returns:
        配置好的日志器
    """
    return logging.getLogger(f"narra_sync.{name}")

# 错误检查装饰器
def error_handler(error_message: str = "操作失败", log_level: int = logging.ERROR):
    """错误处理装饰器
    
    Args:
        error_message: 错误消息前缀
        log_level: 错误日志级别
        
    Returns:
        装饰后的函数
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                handle_exception(e, log_level)
                if isinstance(e, NarraSyncError):
                    return {"error": f"{error_message}: {e.message}"}
                else:
                    return {"error": f"{error_message}: {str(e)}"}
        return wrapper
    return decorator 