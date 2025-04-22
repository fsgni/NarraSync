import os
import json
import shutil
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Union
from abc import ABC, abstractmethod

# 导入新的服务、配置和错误处理模块
from config import config
from errors import get_logger, error_handler, ProcessingError, FileError
from services import ServiceLocator, ImageGeneratorService

# 创建日志记录器
logger = get_logger("image_processor")

class ImageGenerator(ABC):
    """图像生成器基类"""
    
    def __init__(self):
        """初始化图像生成器"""
        pass
        
    @abstractmethod
    def generate_image(self, prompt: str, output_filename: str) -> str:
        """生成单个图像"""
        pass
        
    @abstractmethod
    def generate_images(self, key_scenes_file: str):
        """生成多个场景图像"""
        pass

class ImageProcessor:
    """图像处理器，封装图像生成、修改等功能"""
    
    def __init__(self):
        """初始化图像处理器"""
        self.output_dir = Path(config.get("paths", "output_images", default="output/images"))
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.modified_images_file = os.path.join(
            config.get("paths", "output", default="output"), 
            "modified_images.txt"
        )
        logger.debug(f"初始化图像处理器，输出目录: {self.output_dir}")
    
    def get_generator(self, generator_type: str, **kwargs) -> ImageGeneratorService:
        """创建图像生成器实例
        
        Args:
            generator_type: 生成器类型，如 "comfyui" 或 "midjourney"
            **kwargs: 附加参数，如 ComfyUI 的 style 等
            
        Returns:
            ImageGeneratorService: 图像生成器实例
        """
        # 使用服务定位器获取图像生成器
        logger.debug(f"获取图像生成器: {generator_type}, 参数: {kwargs}")
        return ServiceLocator.get_image_generator(generator_type, **kwargs)
    
    def _get_image_path(self, image_file: str) -> Path:
        """获取图像的完整路径
        
        Args:
            image_file: 图像文件名
            
        Returns:
            Path: 图像的完整路径
        """
        return self.output_dir / image_file
    
    def _get_key_scenes_file(self) -> str:
        """获取场景信息文件路径
        
        Returns:
            str: 场景信息文件的完整路径
        """
        return os.path.join(config.get("paths", "output", default="output"), "key_scenes.json")
    
    def _load_scenes(self, key_scenes_file: str) -> List[Dict[str, Any]]:
        """加载场景信息
        
        Args:
            key_scenes_file: 场景信息文件路径
            
        Returns:
            List[Dict[str, Any]]: 场景信息列表
            
        Raises:
            FileError: 找不到场景信息文件时抛出
            ProcessingError: 解析场景信息文件失败时抛出
        """
        if not os.path.exists(key_scenes_file):
            error_msg = f"找不到场景信息文件: {key_scenes_file}"
            logger.error(error_msg)
            raise FileError(error_msg)
        
        try:
            with open(key_scenes_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            error_msg = f"解析场景信息文件失败: {e}"
            logger.error(error_msg)
            raise ProcessingError(error_msg)
        except Exception as e:
            error_msg = f"读取场景信息文件失败: {e}"
            logger.error(error_msg)
            raise ProcessingError(error_msg)
    
    def _save_scenes(self, key_scenes_file: str, scenes: List[Dict[str, Any]]) -> None:
        """保存场景信息
        
        Args:
            key_scenes_file: 场景信息文件路径
            scenes: 场景信息列表
            
        Raises:
            ProcessingError: 保存场景信息文件失败时抛出
        """
        try:
            with open(key_scenes_file, "w", encoding="utf-8") as f:
                json.dump(scenes, f, ensure_ascii=False, indent=2)
            logger.debug(f"场景信息已保存到: {key_scenes_file}")
        except Exception as e:
            error_msg = f"保存场景信息文件失败: {e}"
            logger.error(error_msg)
            raise ProcessingError(error_msg)
    
    def _get_style_text(self, custom_style: Optional[str], image_style: Optional[str]) -> str:
        """根据风格设置获取风格文本
        
        Args:
            custom_style: 自定义风格
            image_style: 预设风格
            
        Returns:
            str: 风格文本，如果没有设置风格则返回空字符串
        """
        if custom_style and custom_style.strip():
            # 用户提供了自定义风格
            logger.info(f"使用自定义风格: {custom_style}")
            return custom_style
        elif image_style and image_style != "默认" and image_style != "无风格":
            # 使用预定义的风格
            style_map = config.get("image", "styles", default={
                "电影级品质": "cinematic lighting, movie quality, professional photography, 8k ultra HD",
                "水墨画风格": "traditional Chinese ink painting style, elegant, flowing ink, minimalist",
                "油画风格": "oil painting style, detailed brushwork, rich colors, artistic",
                "动漫风格": "anime style, vibrant colors, clean lines, expressive",
                "写实风格": "photorealistic, highly detailed, sharp focus, natural lighting",
                "梦幻风格": "dreamy atmosphere, soft lighting, ethereal colors, mystical",
                "动漫": "anime, manga style, vibrant colors, clean lines",
                "写实": "photorealistic, detailed, fine art, crisp details",
                "油画": "oil painting, artistic, textured, traditional art",
                "水彩": "watercolor painting, soft, flowing, artistic",
                "科幻": "sci-fi, futuristic, high tech, advanced technology",
                "奇幻": "fantasy, magical, mythical, enchanted world",
                "复古": "vintage, retro, nostalgic, historical aesthetic",
                "可爱": "cute, kawaii, adorable, pastel colors"
            })
            style_text = style_map.get(image_style, "high quality, detailed")
            logger.info(f"使用预设风格: {image_style} -> {style_text}")
            return style_text
        
        logger.info("使用默认风格")
        return ""
    
    def _create_placeholder_image(self, image_path: Path, scene_id: int, prompt: str) -> bool:
        """创建占位符图像
        
        Args:
            image_path: 图像保存路径
            scene_id: 场景ID
            prompt: 场景提示词
            
        Returns:
            bool: 是否成功创建占位符图像
        """
        logger.info(f"为场景 {scene_id} 创建占位符图像")
        
        # 确保输出目录存在
        image_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 占位符文本
        text = f"Scene {scene_id}\n{prompt}"
        
        # 尝试使用PIL创建占位符
        try:
            from PIL import Image, ImageDraw, ImageFont
            
            # 创建图像
            img = Image.new('RGB', (1280, 720), color=(0, 0, 128))  # 深蓝色背景
            draw = ImageDraw.Draw(img)
            
            # 添加文字
            try:
                # 尝试使用系统字体
                font_size = 40
                font = ImageFont.truetype("arial.ttf", font_size)
            except:
                # 如果找不到字体，使用默认字体
                font = ImageFont.load_default()
            
            # 绘制文本（处理不同版本的PIL）
            if hasattr(draw, 'textsize'):
                # 旧版PIL
                text_width, text_height = draw.textsize(text, font=font)
                position = ((1280 - text_width) // 2, (720 - text_height) // 2)
                draw.text(position, text, fill=(255, 255, 255), font=font)
            else:
                # 新版PIL
                draw.text((640, 360), text, fill=(255, 255, 255), font=font, 
                         anchor="mm", align="center")
            
            # 保存图像
            img.save(image_path)
            logger.info(f"已创建PIL占位符图像: {image_path}")
            return True
        except Exception as e:
            logger.error(f"使用PIL创建占位符图像失败: {e}")
        
        # 尝试使用matplotlib
        try:
            import matplotlib.pyplot as plt
            
            plt.figure(figsize=(12.8, 7.2))
            plt.text(0.5, 0.5, text, 
                    horizontalalignment='center', verticalalignment='center',
                    fontsize=20, color='white')
            plt.axis('off')
            plt.savefig(image_path, bbox_inches='tight', facecolor='blue')
            plt.close()
            logger.info(f"已创建matplotlib占位符图像: {image_path}")
            return True
        except Exception as mpl_e:
            logger.error(f"使用matplotlib创建占位符图像失败: {mpl_e}")
        
        # 创建空文件作为最后的尝试
        try:
            with open(image_path, "wb") as f:
                # 写入1x1像素的PNG图像
                f.write(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDAT\x08\xd7c\xf8\xff\xff?\x00\x05\xfe\x02\xfe\xdc\xccY\xe7\x00\x00\x00\x00IEND\xaeB`\x82")
            logger.info(f"已创建简单占位符图像: {image_path}")
            return True
        except Exception as e:
            logger.error(f"创建占位符图像失败: {e}")
            return False
    
    @error_handler(error_message="重新生成场景图片失败")
    def regenerate_scene_image(self, scene_index: int, scene_prompt: str, 
                             image_generator_type: str, aspect_ratio: Optional[str] = None, 
                             image_style: Optional[str] = None, custom_style: Optional[str] = None, 
                             comfyui_style: Optional[str] = None) -> str:
        """重新生成指定场景的图片
        
        Args:
            scene_index: 场景索引
            scene_prompt: 场景提示词
            image_generator_type: 图像生成器类型
            aspect_ratio: 图像比例
            image_style: 图像风格
            custom_style: 自定义风格
            comfyui_style: ComfyUI风格
            
        Returns:
            str: 状态信息
            
        Raises:
            FileError: 找不到场景信息文件时抛出
            ProcessingError: 场景索引无效或图像生成失败时抛出
        """
        # 读取场景信息
        key_scenes_file = self._get_key_scenes_file()
        scenes = self._load_scenes(key_scenes_file)
        
        # 检查场景索引是否有效
        scene_idx = int(scene_index) - 1
        if scene_idx < 0 or scene_idx >= len(scenes):
            raise ProcessingError(f"无效的场景索引: {scene_index}，场景总数: {len(scenes)}")
        
        # 更新场景提示词
        scene = scenes[scene_idx]
        old_prompt = scene.get("prompt", "")
        
        # 使用新提供的提示词替换原来的提示词
        scene["prompt"] = scene_prompt
        
        # 保存更新后的场景信息
        self._save_scenes(key_scenes_file, scenes)
        
        # 生成图像
        image_file = scene.get("image_file", "")
        if not image_file:
            image_file = f"scene_{scene_index:03d}.png"
            scene["image_file"] = image_file
        
        # 标记图片不再是手动上传的，强制重新生成
        if self.is_image_modified(image_file):
            self._unmark_image_as_modified(image_file)
        
        # 构造图像路径
        image_path = self._get_image_path(image_file)
        
        # 删除可能存在的旧图像
        if os.path.exists(image_path):
            os.remove(image_path)
            logger.info(f"已删除旧图片: {image_path}")
        
        # 获取图像生成器
        generator = self.get_generator(
            image_generator_type,
            style=comfyui_style if image_generator_type.lower() == "comfyui" else None
        )
        
        # 构造提示词
        if image_generator_type.lower() == "comfyui":
            # ComfyUI使用直接提示词
            full_prompt = scene_prompt
            logger.info(f"使用ComfyUI生成图片，提示词: {scene_prompt}")
        else:
            # MidJourney需要处理风格
            style_text = self._get_style_text(custom_style, image_style)
            full_prompt = f"{scene_prompt}, {style_text}" if style_text else scene_prompt
            logger.info(f"使用Midjourney生成图片，完整提示词: {full_prompt}")
        
        # 准备参数
        kwargs = {}
        if aspect_ratio and image_generator_type.lower() == "midjourney":
            kwargs["aspect_ratio"] = aspect_ratio
        
        # 生成图像
        try:
            generator.generate_image(full_prompt, image_file, **kwargs)
        except Exception as e:
            logger.error(f"图像生成失败: {e}")
            raise ProcessingError(f"图像生成失败: {str(e)}")
        
        # 检查图片是否成功生成
        if os.path.exists(image_path):
            logger.info(f"图片生成成功: {image_path}")
            return f"场景 {scene_index} 的图片已重新生成，提示词已从「{old_prompt}」更新为「{scene_prompt}」"
        else:
            raise ProcessingError(f"场景 {scene_index} 的图片生成失败，请检查图像生成器设置")
            
    def _unmark_image_as_modified(self, image_file: str) -> None:
        """取消标记图片为已修改状态
        
        Args:
            image_file: 图像文件名
        """
        if not os.path.exists(self.modified_images_file):
            return
            
        try:
            # 读取已修改图片列表
            with open(self.modified_images_file, "r", encoding="utf-8") as f:
                modified_images = [line.strip() for line in f.readlines()]
            
            # 移除该图片
            if image_file in modified_images:
                modified_images.remove(image_file)
                
                # 保存更新后的列表
                with open(self.modified_images_file, "w", encoding="utf-8") as f:
                    f.write("\n".join(modified_images))
                    
                logger.debug(f"已取消标记图片 {image_file} 的修改状态")
        except Exception as e:
            logger.warning(f"取消标记图片修改状态时出错: {e}")
    
    def _create_image_generator(self, image_generator_type: str, comfyui_style: Optional[str] = None) -> Optional[Union[ImageGeneratorService, Any]]:
        """创建图像生成器实例
        
        Args:
            image_generator_type: 图像生成器类型
            comfyui_style: ComfyUI风格
            
        Returns:
            Optional[Union[ImageGeneratorService, Any]]: 图像生成器实例，如果创建失败则返回None
        """
        logger.info("\n----- 创建图像生成器 -----")
        try:
            if image_generator_type.lower() == "comfyui":
                from image_generator import ComfyUIGenerator
                generator = ComfyUIGenerator(style=comfyui_style)
                logger.info(f"成功创建ComfyUI生成器 (风格: {comfyui_style})")
                return generator
            else:
                from midjourney_generator import MidjourneyGenerator
                generator = MidjourneyGenerator()
                logger.info(f"成功创建Midjourney生成器")
                return generator
        except Exception as e:
            logger.error(f"创建图像生成器失败: {e}")
            logger.info("将使用占位符图像作为替代")
            return None
    
    def _ensure_scene_has_image_file(self, scene: Dict[str, Any], index: int) -> None:
        """确保场景有图像文件名
        
        Args:
            scene: 场景信息
            index: 场景索引
        """
        if not scene.get("image_file"):
            scene["image_file"] = f"scene_{index+1:03d}.png"
            logger.info(f"为场景 {index+1} 添加缺失的image_file: {scene['image_file']}")
    
    @error_handler(error_message="处理场景图像失败")
    def process_scene_images(self, scenes: List[Dict[str, Any]], 
                           image_generator_type: str, 
                           aspect_ratio: Optional[str] = None, 
                           image_style: Optional[str] = None, 
                           custom_style: Optional[str] = None, 
                           comfyui_style: Optional[str] = None, 
                           no_regenerate: bool = False) -> List[Dict[str, Any]]:
        """处理多个场景的图片
        
        Args:
            scenes: 场景列表
            image_generator_type: 图像生成器类型
            aspect_ratio: 图像比例
            image_style: 图像风格
            custom_style: 自定义风格
            comfyui_style: ComfyUI风格
            no_regenerate: 是否不重新生成图片
            
        Returns:
            List[Dict[str, Any]]: 处理后的场景列表
        """
        logger.info("\n===== 开始处理场景图像 =====")
        logger.info(f"收到 {len(scenes)} 个场景")
        logger.info(f"图像生成器: {image_generator_type}")
        logger.info(f"不重新生成图片: {no_regenerate}")
        
        # 确保所有场景都有image_file和prompt字段
        for i, scene in enumerate(scenes):
            self._ensure_scene_has_image_file(scene, i)
            
            if not scene.get("prompt"):
                scene["prompt"] = f"Scene {i+1}"
                logger.info(f"为场景 {i+1} 添加默认提示词: {scene['prompt']}")
            
            # 确保输出目录存在
            os.makedirs(str(self.output_dir), exist_ok=True)
        
        # 如果选择不重新生成任何图片，直接返回场景列表
        if no_regenerate:
            logger.info("已选择不重新生成任何图片，保留所有现有图片")
            # 只对场景提示词进行更新
            for i, prompt_info in enumerate(scenes):
                scene_id = prompt_info.get("scene_id")
                prompt = prompt_info.get("prompt")
                
                # 如果提供了新的提示词，更新原始列表
                if scene_id and prompt:
                    scene_idx = int(scene_id) - 1
                    if 0 <= scene_idx < len(scenes):
                        scenes[scene_idx]["prompt"] = prompt
            
                # 确保每个场景都有image_file字段
                self._ensure_scene_has_image_file(scenes[i], i)
            
            return scenes
            
        # 创建图像生成器
        generator = self._create_image_generator(image_generator_type, comfyui_style)
        
        # 处理每个场景
        logger.info("\n----- 处理场景图像 -----")
        for i, scene in enumerate(scenes):
            logger.info(f"\n处理场景 {i+1}/{len(scenes)}...")
            
            # 获取场景ID和提示词
            scene_id = scene.get("scene_id", i+1)
            prompt = scene.get("prompt", f"Scene {i+1}")
            
            # 确保image_file字段存在
            self._ensure_scene_has_image_file(scene, i)
            
            # 构建图像路径
            image_file = scene.get("image_file")
            image_path = self._get_image_path(image_file)
            
            # 如果图片已被手动修改，跳过生成
            if self.is_image_modified(image_file):
                logger.info(f"图片已手动修改，跳过生成: {image_path}")
                continue
            
            # 如果图片已存在，跳过生成
            if os.path.exists(image_path):
                logger.info(f"图片已存在，跳过生成: {image_path}")
                continue
            
            # 确保有提示词和图片文件名
            if not prompt or not image_file:
                logger.info(f"场景 {i+1} 缺少提示词或图片文件名，无法生成图片")
                continue
            
            logger.info(f"场景 {i+1} 提示词: {prompt}")
            logger.info(f"场景 {i+1} 图像文件: {image_file}")
            
            # 尝试生成图像
            image_generated = False
            
            # 如果成功创建了生成器，使用它生成图像
            if generator:
                try:
                    # 根据生成器类型处理提示词和生成图像
                    if image_generator_type.lower() == "comfyui":
                        # 直接使用提示词
                        logger.info(f"使用ComfyUI生成图像: {image_file}")
                        result = generator.generate_image(prompt, image_file)
                        image_generated = os.path.exists(image_path)
                    else:
                        # 处理提示词
                        style_text = self._get_style_text(custom_style, image_style)
                        full_prompt = f"{prompt}, {style_text}" if style_text else prompt
                        
                        logger.info(f"完整提示词: {full_prompt}")
                        
                        # 生成图像
                        logger.info(f"使用Midjourney生成图像: {image_file}")
                        result = generator.generate_image(full_prompt, image_file, aspect_ratio=aspect_ratio)
                        image_generated = os.path.exists(image_path)
                    
                    if image_generated:
                        logger.info(f"成功生成图像: {image_path}")
                    else:
                        logger.info(f"图像生成失败: {image_path}")
                except Exception as e:
                    logger.error(f"生成图像时出错: {e}")
                    image_generated = False
            
            # 如果图像生成失败，创建占位符图像
            if not image_generated:
                self._create_placeholder_image(image_path, i+1, prompt)
        
        logger.info("\n===== 场景图像处理完成 =====")
        return scenes
    
    def is_image_modified(self, image_file: str) -> bool:
        """检查图片是否被修改过（手动上传等）
        
        Args:
            image_file: 图像文件名
            
        Returns:
            bool: 图片是否被修改过
        """
        if not os.path.exists(self.modified_images_file):
            return False
            
        try:
            with open(self.modified_images_file, "r", encoding="utf-8") as f:
                modified_images = [line.strip() for line in f.readlines()]
                return image_file in modified_images
        except Exception as e:
            logger.warning(f"检查图片修改状态时出错: {e}")
            return False 