#!/usr/bin/env python
"""Narra-Sync 架构示例

这个示例展示了如何使用新的架构组件：
1. 配置管理
2. 错误处理
3. 服务接口
"""
import os
import sys
from pathlib import Path

# 导入新的架构组件
from config import config
from errors import get_logger, error_handler, ProcessingError, handle_exception
from services import ServiceLocator

# 创建日志记录器
logger = get_logger("example")

@error_handler(error_message="示例处理失败")
def process_example():
    """示例处理函数，展示如何使用新架构"""
    logger.info("开始示例处理...")
    
    # 1. 使用配置
    logger.info("1. 配置管理示例")
    voicevox_host = config.get("services", "voicevox", "host", default="127.0.0.1")
    voicevox_port = config.get("services", "voicevox", "port", default=50021)
    logger.info(f"VoiceVox配置: {voicevox_host}:{voicevox_port}")
    
    # 修改配置
    config.set("services", "voicevox", "default_speaker", 8)
    logger.info(f"默认语音人物ID已更新为: {config.get('services', 'voicevox', 'default_speaker')}")
    
    # 2. 服务定位器
    logger.info("\n2. 服务定位器示例")
    try:
        # 获取图像生成器
        generator_type = config.get("image", "default_generator", default="comfyui")
        logger.info(f"获取图像生成器: {generator_type}")
        
        # 这里只是演示，通常不需要try-except，因为@error_handler已经处理了异常
        image_generator = ServiceLocator.get_image_generator(generator_type)
        logger.info(f"图像生成器获取成功，可用风格: {image_generator.get_available_styles()}")
        
        # 获取语音生成器
        logger.info("获取语音生成器...")
        voice_generator = ServiceLocator.get_voice_generator()
        speakers = voice_generator.list_speakers()
        logger.info(f"语音生成器获取成功，找到 {len(speakers)} 个说话人")
        
        # 获取视频处理器
        engine = config.get("video", "default_engine", default="auto")
        logger.info(f"获取视频处理器: {engine}")
        video_processor = ServiceLocator.get_video_processor(engine)
        logger.info("视频处理器获取成功")
        
    except Exception as e:
        # 错误处理示例
        error_info = handle_exception(e)
        logger.error(f"服务获取失败: {error_info['message']}")
        return {"error": error_info['message']}
    
    # 3. 错误处理
    logger.info("\n3. 错误处理示例")
    
    # 故意引发错误以展示错误处理
    try:
        result = risky_operation()
        logger.info(f"风险操作结果: {result}")
    except Exception as e:
        logger.warning("预期到的错误被捕获并处理")
    
    logger.info("示例处理完成")
    return {"status": "success", "message": "示例处理完成"}

@error_handler(error_message="风险操作失败")
def risky_operation():
    """一个可能引发错误的操作"""
    logger.info("执行风险操作...")
    raise ProcessingError("这是一个演示错误")

def main():
    """主函数"""
    logger.info("="*50)
    logger.info("Narra-Sync 架构示例")
    logger.info("="*50)
    
    # 创建输出目录
    for dir_path in config.get("paths").values():
        Path(dir_path).mkdir(parents=True, exist_ok=True)
        logger.info(f"已确保目录存在: {dir_path}")
    
    # 执行示例处理
    result = process_example()
    
    # 打印结果
    if "error" in result:
        logger.error(f"处理失败: {result['error']}")
        sys.exit(1)
    else:
        logger.info(f"处理成功: {result['message']}")
        sys.exit(0)

if __name__ == "__main__":
    main() 