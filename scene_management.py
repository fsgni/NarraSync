import os
import json
from pathlib import Path
import shutil
from PIL import Image
from typing import Dict, Any, Tuple, List, Optional
import requests
import asyncio

# 导入配置和错误处理模块
from config import config
from errors import FileError, ProcessingError, get_logger, error_handler
from services import ServiceLocator
# 导入 StoryAnalyzer
from story_analyzer import StoryAnalyzer

# 创建日志记录器
logger = get_logger("scene_management")

# 修改：使用 StoryAnalyzer 中的方法重写提示词
def rewrite_prompt_with_ai(original_prompt, retry_count=0):
    """使用 StoryAnalyzer 中的 LLM 方法重写提示词，避开敏感词

    Args:
        original_prompt: 原始提示词
        retry_count: 当前重试次数

    Returns:
        str: 重写后的提示词
    """
    try:
        # 获取 StoryAnalyzer 实例
        # 注意：这里假设 StoryAnalyzer 可以直接实例化。
        # 如果您的架构要求通过 ServiceLocator 获取，请相应修改。
        analyzer = StoryAnalyzer()
        
        # 调用 StoryAnalyzer 中的重写方法
        rewritten_prompt = analyzer.rewrite_prompt_for_sensitivity(original_prompt, retry_count)
        
        logger.info(f"成功从 StoryAnalyzer 获取重写后的提示词 (重试 {retry_count})")
        return rewritten_prompt
        
    except Exception as e:
        logger.error(f"调用 StoryAnalyzer 重写提示词失败: {e}")
        # 出错时返回稍微修改的原始提示词作为回退
        return original_prompt + f" (rewrite attempt {retry_count + 1} failed)"

@error_handler(error_message="上传场景图片失败")
def upload_scene_image(scene_index, image_path):
    """上传自定义图片替换场景图片"""
    if not image_path:
        raise FileError("未提供图片路径")
    
    # 确保输出目录存在
    output_dir = config.get("paths", "output_images", default="output/images")
    os.makedirs(output_dir, exist_ok=True)
        
    # 使用场景管理器
    from scene_manager import SceneManager
    scene_manager = SceneManager()
    
    # 检查场景数据是否存在
    scenes = scene_manager.load_scenes()
    if not scenes:
        raise FileError("没有找到场景数据。请先生成视频再上传图片。")
    
    # 转换场景索引
    try:
        clean_index = int(float(str(scene_index).strip()))
        if clean_index < 1:
            clean_index = 1
    except (TypeError, ValueError, AttributeError):
        clean_index = 1
    
    # 检查索引是否有效
    scene_idx = clean_index - 1
    if scene_idx < 0 or scene_idx >= len(scenes):
        raise FileError(f"场景索引 {clean_index} 超出有效范围 1-{len(scenes)}")
    
    # 获取场景
    scene = scenes[scene_idx]
    
    # 检查图片路径是否存在
    if not os.path.exists(image_path):
        raise FileError(f"上传失败：图片不存在 - {image_path}")
    
    # 获取或创建图像文件名
    image_file = scene.get("image_file", f"scene_{clean_index:03d}.png")
    scene["image_file"] = image_file
    scene_manager.save_scenes(scenes)
    
    # 构建目标路径并复制图片
    target_path = os.path.join(output_dir, image_file)
    try:
        shutil.copy2(image_path, target_path)
    except Exception as e:
        logger.warning(f"无法直接复制图片: {e}，尝试使用PIL")
        try:
            # 尝试使用PIL打开并保存图片
            img = Image.open(image_path)
            img.save(target_path)
        except Exception as e2:
            raise FileError(f"保存图片失败: {e2}")
    
    # 标记图片为已修改
    scene_manager._mark_image_as_modified(image_file)
    
    if os.path.exists(target_path):
        logger.info(f"场景 {clean_index} 的图片已成功上传")
        return f"场景 {clean_index} 的图片已成功上传"
    else:
        raise FileError(f"图片未能成功保存到 {target_path}")

@error_handler(error_message="收集场景提示词失败")
def collect_all_prompts():
    """收集所有场景的提示词"""
    key_scenes_file = os.path.join(config.get("paths", "output", default="output"), "key_scenes.json")
    if not os.path.exists(key_scenes_file):
        return "[]"
    
    with open(key_scenes_file, "r", encoding="utf-8") as f:
        scenes = json.load(f)
        
    prompts_data = []
    for i, scene in enumerate(scenes):
        prompt = scene.get("prompt", "")
        prompts_data.append({
            "scene_id": i + 1,
            "prompt": prompt
        })
        
    return json.dumps(prompts_data, ensure_ascii=False)

@error_handler(error_message="清除修改标记失败")
def clear_modified_images():
    """清除所有已修改图片的标记"""
    from scene_manager import SceneManager
    scene_manager = SceneManager()
    result = scene_manager.clear_modified_images()
    
    if result:
        logger.info("已清除所有修改标记")
        return "已清除所有修改标记，下次重新合成视频时将重新生成所有图片"
    else:
        raise ProcessingError("清除修改标记失败")

@error_handler(error_message="加载场景详情失败")
def load_scene_details(scene_idx, video_path):
    """加载选中场景的详细信息"""
    from scene_manager import SceneManager
    scene_manager = SceneManager()
    scene_details = scene_manager.load_scene_details(scene_idx, video_path)
    return (
        scene_details["content"],
        scene_details["prompt"],
        scene_details["image_path"],
        scene_details["scene_idx"],
        scene_details["scene_count_label"]
    )

@error_handler(error_message="刷新场景列表失败")
def refresh_scene_list(video_path):
    """刷新场景列表"""
    from scene_manager import SceneManager
    scene_manager = SceneManager()
    return scene_manager.refresh_scene_list(video_path)

@error_handler(error_message="生成场景缩略图失败")
def generate_scene_thumbnails():
    """生成场景缩略图HTML"""
    from scene_manager import SceneManager
    scene_manager = SceneManager()
    return scene_manager.generate_scene_thumbnails()

@error_handler(error_message="选择场景失败")
def gallery_select(evt, scene_video_path):
    """当用户在Gallery中选择图片时触发"""
    try:
        # 处理不同类型的输入
        if hasattr(evt, 'index'):
            scene_idx = (evt.index() if callable(evt.index) else evt.index) + 1
        elif isinstance(evt, (int, str)) and not str(evt).startswith('C:'):
            scene_idx = int(str(evt).split(',')[0] if ',' in str(evt) else evt) + 1
        else:
            scene_idx = 1
    except Exception:
        scene_idx = 1
    
    return load_scene_details(scene_idx, scene_video_path)

@error_handler(error_message="重新生成场景图片失败")
async def regenerate_scene_image_async(scene_id, scenes, image_generator_type, aspect_ratio, image_style, custom_style, comfyui_style):
    """重新生成指定场景的图片 (异步版本)
    
    Args:
        scene_id: 场景ID
        scenes: 当前场景列表，其中已包含更新后的提示词
        image_generator_type: 图像生成器类型
        aspect_ratio: 图像比例
        image_style: 图像风格
        custom_style: 自定义风格
        comfyui_style: ComfyUI风格
        
    Returns:
        tuple: (状态码, 消息, 图像文件名)
    """
    # 检查场景索引是否有效
    scene_idx = int(scene_id) - 1
    if scene_idx < 0 or scene_idx >= len(scenes):
        return 400, f"无效的场景索引: {scene_id}，场景总数: {len(scenes)}", None
    
    # 获取场景
    scene = scenes[scene_idx]
    scene_prompt = scene.get("prompt", "")
    
    # 确保图像文件名存在
    image_file = scene.get("image_file", f"scene_{scene_id:03d}.png")
    scene["image_file"] = image_file
    
    # 保存场景数据
    output_path = os.path.join(config.get("paths", "output", default="output"), "key_scenes.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(scenes, f, ensure_ascii=False, indent=2)
    
    # 使用服务定位器获取图像生成器
    image_generator = ServiceLocator.get_image_generator(image_generator_type)
    
    # 设置风格
    if image_generator_type == "comfyui" and comfyui_style:
        image_generator.set_style(comfyui_style)
    
    # 生成图像
    output_filename = image_file
    kwargs = {}
    
    # 添加其他参数
    if aspect_ratio and aspect_ratio != "默认方形":
        kwargs["aspect_ratio"] = aspect_ratio
    
    # 添加图像风格
    final_style = None
    if image_style == "自定义风格" and custom_style:
        final_style = custom_style
    elif image_style != "无风格" and image_style != "自定义风格":
        # 从配置中获取预设风格
        styles = config.get("image", "styles", default={})
        final_style = styles.get(image_style)
    
    if final_style:
        # 将风格添加到提示词
        enhanced_prompt = f"{scene_prompt}, {final_style}"
    else:
        enhanced_prompt = scene_prompt
    
    # 重新生成图片
    logger.info(f"开始重新生成图片，场景ID: {scene_id}, 提示词: {enhanced_prompt}")
    try:
        # 如果是 Midjourney，调用异步方法
        if image_generator_type.lower() == "midjourney":
            output_filepath = await image_generator.generate_image_async(enhanced_prompt, output_filename, **kwargs)
        else: # ComfyUI 或其他保持同步调用
            output_filepath = image_generator.generate_image(enhanced_prompt, output_filename, **kwargs)

        if not output_filepath:
            # 如果返回 None，也认为是失败
            raise ProcessingError("图像生成器未能返回有效的文件路径")
            
        logger.info(f"图片生成成功: {output_filepath}")
        
        # 获取场景管理器并标记图片为已修改
        from scene_manager import SceneManager
        scene_manager = SceneManager()
        scene_manager._mark_image_as_modified(image_file)
        
        return 200, f"场景 {scene_id} 的图片已成功重新生成", image_file
    except Exception as e:
        logger.error(f"生成图片失败: {e}")
        # 添加更详细的打印输出到后台命令行
        import traceback
        print(f"--- regenerate_scene_image_async 捕获到异常 ---")
        print(f"场景ID: {scene_id}")
        print(f"使用的提示词: {enhanced_prompt}")
        print(f"详细错误信息: {e}")
        print(traceback.format_exc())
        print(f"--- 异常信息结束 ---")
        # 返回的 message 保持不变，依然是原始错误
        return 500, f"生成图片失败: {str(e)}", None 

@error_handler(error_message="重新生成场景图片失败")
def regenerate_scene_image_with_retry(scene_id, scenes, image_generator_type, aspect_ratio, image_style, custom_style, comfyui_style, max_retries=3):
    """重新生成指定场景的图片，出现敏感词时尝试重写提示词
    
    Args:
        scene_id: 场景ID
        scenes: 当前场景列表，其中已包含更新后的提示词
        image_generator_type: 图像生成器类型
        aspect_ratio: 图像比例
        image_style: 图像风格
        custom_style: 自定义风格
        comfyui_style: ComfyUI风格
        max_retries: 最大重试次数
        
    Returns:
        tuple: (状态码, 消息, 图像文件名)
    """
    # 检查场景索引是否有效
    scene_idx = int(scene_id) - 1
    if scene_idx < 0 or scene_idx >= len(scenes):
        return 400, f"无效的场景索引: {scene_id}，场景总数: {len(scenes)}", None
    
    # 获取场景
    scene = scenes[scene_idx]
    original_prompt = scene.get("prompt", "")
    
    # 尝试使用原始提示词生成 (调用异步版本)
    logger.info(f"尝试使用原始提示词生成图片，场景ID: {scene_id}, 提示词: {original_prompt}")
    # 使用 asyncio.run() 来同步执行异步函数
    try:
        status, message, image_file = asyncio.run(regenerate_scene_image_async(
        scene_id, scenes, image_generator_type, aspect_ratio, image_style, custom_style, comfyui_style
        ))
    except Exception as run_err: # 捕获 asyncio.run 可能的错误
        logger.error(f"运行 regenerate_scene_image_async 时出错: {run_err}")
        status, message, image_file = 500, f"内部错误: {run_err}", None
    
    # 如果成功则直接返回
    if status == 200:
        return status, message, image_file
    
    # 如果失败且有重试次数，尝试使用AI重写提示词
    retry_count = 0
    current_prompt = original_prompt
    
    while status != 200 and retry_count < max_retries:
        retry_count += 1
        logger.info(f"第 {retry_count}/{max_retries} 次重试，场景ID: {scene_id}")
        
        # 使用AI重写提示词
        new_prompt = rewrite_prompt_with_ai(current_prompt, retry_count)
        
        # 更新场景提示词
        scene["prompt"] = new_prompt
        scenes[scene_idx] = scene
        
        # 尝试使用新提示词生成 (调用异步版本)
        logger.info(f"使用重写后的提示词重试，场景ID: {scene_id}, 新提示词: {new_prompt}")
        # 使用 asyncio.run() 来同步执行异步函数
        try:
            status, message, image_file = asyncio.run(regenerate_scene_image_async(
            scene_id, scenes, image_generator_type, aspect_ratio, image_style, custom_style, comfyui_style
            ))
        except Exception as run_err:
            logger.error(f"运行 regenerate_scene_image_async (重试) 时出错: {run_err}")
            status, message, image_file = 500, f"内部错误: {run_err}", None
        
        # 更新当前提示词用于下一次重试
        current_prompt = new_prompt
    
    # 如果所有重试都失败，恢复原始提示词并返回最后一次尝试的结果
    if status != 200:
        logger.warning(f"所有重试都失败，恢复原始提示词，场景ID: {scene_id}")
        scene["prompt"] = original_prompt
        scenes[scene_idx] = scene
        
        # 保存场景数据
        output_path = os.path.join(config.get("paths", "output", default="output"), "key_scenes.json")
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(scenes, f, ensure_ascii=False, indent=2)
            
        return 500, f"生成图片失败，已尝试 {max_retries} 次重写提示词", None
    
    return status, f"在第 {retry_count} 次重试后成功生成图片: {message}", image_file 