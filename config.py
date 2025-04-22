"""全局配置管理模块

提供统一的配置访问接口，支持默认值、环境变量和配置文件覆盖。
"""
import os
import json
from pathlib import Path
from typing import Dict, Any, Optional, List, Union
import logging

def get_logger(name):
    """获取日志记录器"""
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    return logger

logger = get_logger("config")

class Config:
    """配置管理类"""
    
    # 默认配置
    _defaults = {
        # 服务配置
        "services": {
            "voicevox": {
                "host": "localhost",
                "port": 50021,
                "default_speaker": 13
            },
            "comfyui": {
                "host": "localhost", 
                "port": 8188,
                "default_style": "电影"
            },
            "midjourney": {
                "mode": "api",
                "api_url": "https://api.example.com/midjourney",
                "api_key": ""
            },
            "openai": {
                "api_key": "",
                "tts_model": "gpt-4o-mini-tts",
                "default_voice": 1
            }
        },
        
        # 路径配置
        "paths": {
            "input_texts": "input_texts",
            "input_images": "input_images",
            "output": "output",
            "output_images": "output/images",
            "output_audio": "output/audio",
            "output_videos": "output/videos",
            "dictionaries": "dictionaries",
            "fonts": "fonts",
            "workflows": "workflows",
            "temporary": "temp"
        },
        
        # 视频配置
        "video": {
            "resolution": (1920, 1080),
            "fps": 30,
            "default_engine": "auto",
            "default_font": {
                "name": "UD Digi Kyokasho N-B",
                "size": 18,
                "color": "FFFFFF",
                "bg_opacity": 0.5
            }
        },
        
        # 图像配置
        "image": {
            "default_generator": "comfyui",
            "styles": {
                "电影级品质": "cinematic lighting, movie quality, professional photography, 8k ultra HD",
                "水墨画风格": "traditional Chinese ink painting style, elegant, flowing ink, minimalist",
                "油画风格": "oil painting style, detailed brushwork, rich colors, artistic",
                "动漫风格": "anime style, vibrant colors, clean lines, expressive",
                "写实风格": "photorealistic, highly detailed, sharp focus, natural lighting",
                "梦幻风格": "dreamy atmosphere, soft lighting, ethereal colors, mystical"
            },
            "comfyui_styles": {
                "水墨": "写实水墨水彩风格_F1_水墨.safetensors",
                "手绘": "星揽_手绘线条小清新漫画风格V2_v1.0.safetensors",
                "古风": "中国古典风格滤镜_flux_V1.0.safetensors",
                "插画": "Illustration_story book.safetensors",
                "写实": "adilson-farias-flux1-dev-v1-000088.safetensors",
                "电影": "Cinematic style 3 (FLUX).safetensors" 
            }
        },
        
        # 处理配置
        "processing": {
            "max_retries": 3,
            "retry_delay": 1.0,
            "timeout": 30.0
        },
        
        # UI配置
        "ui": {
            "default_font": "SimHei",
            "default_font_size": 24,
            "default_font_color": "FFFFFF",
            "default_bg_opacity": 0.5
        },
        
        # 调试配置
        "debug": {
            "verbose_logging": False,
            "save_intermediate_files": False
        }
    }
    
    _instance = None
    _config = {}
    
    def __new__(cls):
        """单例模式实现"""
        if cls._instance is None:
            cls._instance = super(Config, cls).__new__(cls)
            cls._instance._initialize()
        return cls._instance
    
    def _initialize(self):
        """初始化配置"""
        # 加载默认配置
        self._config = self._defaults.copy()
        
        # 加载配置文件(如果存在)
        config_path = Path("config.json")
        if config_path.exists():
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    file_config = json.load(f)
                    # 递归合并配置
                    self._merge_configs(self._config, file_config)
            except Exception as e:
                print(f"加载配置文件出错: {e}")
                
        # 加载环境变量配置 (示例: NARRA_VOICEVOX_HOST)
        self._load_from_env()
        
        # 创建必要的目录
        self._create_directories()
    
    def _merge_configs(self, base: Dict, override: Dict):
        """递归合并配置字典"""
        for key, value in override.items():
            if isinstance(value, dict) and key in base and isinstance(base[key], dict):
                self._merge_configs(base[key], value)
            else:
                base[key] = value
    
    def _load_from_env(self):
        """从环境变量加载配置"""
        # 示例: NARRA_VOICEVOX_HOST -> config['services']['voicevox']['host']
        for env_name, env_value in os.environ.items():
            if env_name.startswith("NARRA_"):
                # 解析配置路径
                path = env_name[6:].lower().split("_")
                
                # 递归查找和设置配置项
                current = self._config
                for i, part in enumerate(path):
                    if i == len(path) - 1:
                        # 尝试转换值类型
                        try:
                            # 尝试作为JSON解析
                            env_value = json.loads(env_value)
                        except:
                            # 如果不是有效的JSON，保留原始字符串
                            pass
                        current[part] = env_value
                    else:
                        if part not in current:
                            current[part] = {}
                        current = current[part]
    
    def _create_directories(self):
        """创建配置中定义的必要目录"""
        for dir_name, dir_path in self._config["paths"].items():
            Path(dir_path).mkdir(parents=True, exist_ok=True)
    
    def get(self, *path, default=None):
        """获取配置值
        
        Args:
            *path: 配置路径，如 get("services", "voicevox", "host")
            default: 如果配置不存在，返回的默认值
            
        Returns:
            配置值或默认值
        """
        current = self._config
        for part in path:
            if not isinstance(current, dict) or part not in current:
                return default
            current = current[part]
        return current
    
    def set(self, *path_and_value):
        """设置配置值
        
        Args:
            *path_and_value: 配置路径和值，最后一个参数是值
                如 set("services", "voicevox", "host", "localhost")
        """
        if len(path_and_value) < 2:
            raise ValueError("需要至少一个路径参数和值参数")
        
        path = path_and_value[:-1]
        value = path_and_value[-1]
        
        current = self._config
        for i, part in enumerate(path):
            if i == len(path) - 1:
                current[part] = value
            else:
                if part not in current:
                    current[part] = {}
                current = current[part]
    
    def save(self, file_path: str = "config.json"):
        """保存当前配置到文件
        
        Args:
            file_path: 保存的文件路径
        """
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(self._config, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"保存配置出错: {e}")
            return False
    
    def reset(self):
        """重置为默认配置"""
        self._config = self._defaults.copy()
        self._create_directories()

# 导出全局单例
config = Config()

# 便捷访问函数
def get_config(*path, default=None):
    """获取配置的快捷方法"""
    return config.get(*path, default=default) 