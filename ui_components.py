import gradio as gr
from typing import Dict, List, Any, Optional, Union
from video_processing import process_story
from ui_helpers import list_input_files, get_available_fonts, list_all_fonts, list_character_images, format_text_for_shorts_gpt

# 常量定义
DEFAULT_FONT_SIZE = 18
DEFAULT_BG_OPACITY = 0.5
DEFAULT_FONT_COLOR = "#FFFFFF"
DEFAULT_AUDIO_SENSITIVITY = 0.04

# 图像生成相关常量
IMAGE_GENERATORS = ["comfyui", "midjourney"]
ASPECT_RATIOS = ["默认方形", "16:9", "9:16"]
COMFYUI_STYLES = ["默认(电影)", "水墨", "清新二次元", "古风", "童話2", "童話1", "电影"]
IMAGE_STYLE_TYPES = ["无风格", "电影级品质", "水墨画风格", "油画风格", "动漫风格", "写实风格", "梦幻风格", "自定义风格"]
VIDEO_RESOLUTIONS = ["16:9 (1920x1080)", "9:16 (1080x1920)"]
VIDEO_ENGINES = ["auto", "ffmpeg", "moviepy"]

def show_upload_panel() -> gr.components.Component:
    """显示上传图片面板
    
    Returns:
        gr.components.Component: Gradio更新组件
    """
    return gr.update(visible=True)

def hide_upload_panel() -> gr.components.Component:
    """隐藏上传图片面板
    
    Returns:
        gr.components.Component: Gradio更新组件
    """
    return gr.update(visible=False)

def update_video_dropdown() -> gr.components.Component:
    """更新视频下拉列表
    
    Returns:
        gr.components.Component: 更新后的视频下拉列表
    """
    from ui_helpers import list_video_files
    videos = list_video_files()
    return gr.Dropdown.update(choices=videos, value=videos[0] if videos else None)

def update_ui_based_on_generator(generator_type: str) -> tuple:
    """根据图像生成器类型更新UI组件可见性
    
    Args:
        generator_type: 图像生成器类型
        
    Returns:
        tuple: 更新后的UI组件状态
    """
    if generator_type == "comfyui":
        return gr.update(visible=False), gr.update(visible=True)
    else:
        return gr.update(visible=True), gr.update(visible=False)

def _create_input_text_area() -> tuple:
    """创建文本输入区域
    
    Returns:
        tuple: 文本输入框和文件选择组件
    """
    from ui_helpers import list_input_files
    
    text_input = gr.Textbox(
        label="输入故事文本",
        placeholder="在这里输入您的故事...",
        lines=10
    )
    
    with gr.Row():
        refresh_button = gr.Button("刷新文件列表")
        format_text_button_shorts = gr.Button("Shorts格式化 (GPT)", variant="secondary")
        file_dropdown = gr.Dropdown(
            label="或者选择一个文件",
            choices=list_input_files(),
            interactive=True
        )
    
    return text_input, refresh_button, format_text_button_shorts, file_dropdown

def _create_image_settings() -> tuple:
    """创建图像生成设置区域
    
    Returns:
        tuple: 图像生成相关组件
    """
    with gr.Row():
        image_generator = gr.Radio(
            label="选择图像生成方式",
            choices=IMAGE_GENERATORS,
            value=IMAGE_GENERATORS[0]
        )
        
        aspect_ratio = gr.Radio(
            label="选择图像比例 (仅对Midjourney有效)",
            choices=ASPECT_RATIOS,
            value=ASPECT_RATIOS[0],
            visible=True
        )
        
        # --- 添加 Midjourney 并发设置 --- 
        mj_concurrency_selector = gr.Radio(
            label="Midjourney 并发数", 
            choices=[3, 10], 
            value=3, 
            info="选择 MJ 任务并发数。",
            visible=True
        )
    
    mj_concurrency_warning = gr.Markdown(
        "⚠️ **警告**：选择 10 并发数建议仅在 **Fast 模式** 下使用，否则可能因速率限制导致大量失败。", 
        visible=False
    )
    # --- 结束 Midjourney 并发设置 --- 
    
    with gr.Row():
        comfyui_style = gr.Radio(
            label="ComfyUI风格选择 (仅对ComfyUI有效)",
            choices=COMFYUI_STYLES,
            value=COMFYUI_STYLES[0],
            visible=True
        )
    
    with gr.Row():
        image_style_type = gr.Radio(
            label="选择图像风格",
            choices=IMAGE_STYLE_TYPES,
            value=IMAGE_STYLE_TYPES[0]
        )
        
        custom_style = gr.Textbox(
            label="自定义风格 (仅在选择'自定义风格'时生效)",
            placeholder="例如: cinematic lighting, detailed, 8k ultra HD...",
            visible=True
        )
    
    return image_generator, aspect_ratio, comfyui_style, image_style_type, custom_style, mj_concurrency_selector, mj_concurrency_warning

def _create_subtitle_settings() -> tuple:
    """创建字幕设置区域
    
    Returns:
        tuple: 字幕相关组件
    """
    from ui_helpers import get_available_fonts
    
    # 移除Accordion，直接显示组件
    with gr.Row():
        with gr.Column(scale=1):
            font_name = gr.Dropdown(
                label="字幕字体",
                choices=get_available_fonts(),
                value="默认"
            )
            refresh_fonts_button = gr.Button("刷新字体列表", size="sm")
        with gr.Column(scale=1):
            font_size = gr.Slider(
                label="字体大小",
                minimum=12,
                maximum=36,
                value=DEFAULT_FONT_SIZE,
                step=1
            )
    with gr.Row():
        with gr.Column(scale=1):
            font_color = gr.ColorPicker(
                label="字体颜色",
                value=DEFAULT_FONT_COLOR
            )
        with gr.Column(scale=1):
            bg_opacity = gr.Slider(
                label="背景不透明度",
                minimum=0,
                maximum=1,
                value=DEFAULT_BG_OPACITY,
                step=0.1
            )
    # 新增：字幕垂直位置滑块
    with gr.Row():
        subtitle_vertical_offset = gr.Slider(
            label="字幕垂直位置 (0为默认底部, 正值向下, 负值向上)",
            minimum=-150,
            maximum=150,
            value=0,
            step=1,
            info="调整字幕距离底部的距离 (单位: 像素)"
            )
    
    # 字体说明和管理收起到折叠面板中
    with gr.Accordion("字体管理", open=False):
        gr.Markdown("""
        **字体使用说明**:
        - 在fonts目录中放置.ttf或.otf格式的字体文件
        - 点击"刷新字体列表"按钮更新可用字体
        - 选择"默认"将使用系统默认字体
        - 某些字体可能不支持特定语言的字符，请选择适合您内容的字体
        """)
        
        show_all_fonts_button = gr.Button("查看fonts目录中的字体")
        all_fonts_output = gr.Textbox(
            label="fonts目录中的可用字体",
            placeholder="点击上方按钮查看fonts目录中的字体...",
            lines=10,
            visible=False
        )
    
    return font_name, refresh_fonts_button, font_size, font_color, bg_opacity, subtitle_vertical_offset, show_all_fonts_button, all_fonts_output

def _create_voice_settings() -> tuple:
    """创建声音设置区域
    
    Returns:
        tuple: 声音设置相关组件
    """
    from ui_helpers import get_available_voices
    
    # 声音选择
    voice_dropdown = gr.Dropdown(
        label="选择角色声音",
        choices=get_available_voices(),
        value="VoiceVox: ID 13 - 青山龍星" # Update default based on new format
    )
    
    # 语速调整滑块
    _scale_slider = gr.Slider(
        label="语速 (Speed)",
        minimum=0.5,
        maximum=2.0,
        value=1.0,
        step=0.1,
        info="调整语音合成的速度 (1.0为正常速度)",
        interactive=True
    )
    
    return voice_dropdown, _scale_slider # Keep internal name, but return key will be different

def _create_other_settings() -> dict:
    """创建其他设置区域
    
    Returns:
        dict: 其他设置相关组件
    """
    from ui_helpers import list_character_images
    
    # 移除顶层Accordion，直接显示关键组件
    # 基本设置
    with gr.Row():
        preserve_line_breaks = gr.Checkbox(
            label="保留文本原始换行",
            value=False,
            info="选中此项将在生成字幕时保留原文本的换行符"
        )
        video_resolution = gr.Radio(
            choices=VIDEO_RESOLUTIONS,
            value=VIDEO_RESOLUTIONS[0],
            label="视频分辨率",
            info="选择视频输出分辨率比例"
        )
    
    # 角色图片设置
    with gr.Row():
        character_image = gr.Dropdown(
            label="添加角色形象",
            choices=list_character_images(),
            value="不使用角色图片"
        )
        refresh_character_button = gr.Button("刷新角色形象列表", size="sm")
    
    # 说话角色功能放到一个小折叠面板中以节省空间
    with gr.Accordion("角色说话效果设置", open=False):
        # 添加说话角色功能
        with gr.Row():
            talking_character = gr.Checkbox(
                label="启用角色说话效果",
                value=False,
                info="启用后需要提供闭嘴和张嘴两张图片"
            )
        
        # 说话角色选项区域
        talking_character_options = gr.Row(visible=False)
        with talking_character_options:
            with gr.Column(scale=1):
                closed_mouth_image = gr.Dropdown(
                    label="闭嘴图片",
                    choices=list_character_images(),
                    value="不使用角色图片"
                )
            with gr.Column(scale=1):
                open_mouth_image = gr.Dropdown(
                    label="张嘴图片",
                    choices=list_character_images(),
                    value="不使用角色图片"
                )
        
        talking_sensitivity = gr.Row(visible=False)
        with talking_sensitivity:
            audio_sensitivity = gr.Slider(
                label="音频灵敏度",
                minimum=0.01,
                maximum=0.2,
                value=0.03,
                step=0.01,
                info="数值越小，嘴巴动作越灵敏"
            )
    
    components = {
        "preserve_line_breaks": preserve_line_breaks,
        "character_image": character_image,
        "refresh_character_button": refresh_character_button,
        "talking_character": talking_character,
        "talking_character_options": talking_character_options,
        "talking_sensitivity": talking_sensitivity,
        "closed_mouth_image": closed_mouth_image,
        "open_mouth_image": open_mouth_image, 
        "audio_sensitivity": audio_sensitivity,
        "video_resolution": video_resolution
    }
    
    return components

def create_main_ui() -> Dict[str, Any]:
    """创建主要的UI组件
    
    Returns:
        Dict[str, Any]: 包含所有UI组件的字典
    """
    # 创建一键生成选项卡
    with gr.Row():
        with gr.Column(scale=2):
            # 创建输入文本区域
            text_input, refresh_button, format_text_button_shorts, file_dropdown = _create_input_text_area()
            
            # 使用Tab整理各种设置，使UI更加紧凑
            with gr.Tabs():
                with gr.TabItem("图像设置"):
                    # 创建图像设置区域
                    image_generator, aspect_ratio, comfyui_style, image_style_type, custom_style, mj_concurrency_selector, mj_concurrency_warning = _create_image_settings()
                
                with gr.TabItem("声音与字幕"):
                    # 创建声音设置区域
                    voice_dropdown, speed_scale_slider_component = _create_voice_settings()
                    
                    # 创建字幕设置区域 - 直接展开而不是放在折叠面板中
                    font_name, refresh_fonts_button, font_size, font_color, bg_opacity, subtitle_vertical_offset, show_all_fonts_button, all_fonts_output = _create_subtitle_settings()
                
                with gr.TabItem("角色与效果"):
                    # 创建其他设置区域 - 直接展开而不是放在折叠面板中
                    other_settings_dict = _create_other_settings() # Returns a dict now
            
            # 创建视频引擎选择和处理按钮 - 放在tabs外面以保持可见性
            with gr.Row():
                with gr.Column(scale=3):
                    video_engine = gr.Radio(
                        choices=VIDEO_ENGINES,
                        value=VIDEO_ENGINES[0],
                        label="视频处理引擎",
                        info="选择视频生成引擎，auto会自动选择最适合的引擎"
                    )
                    # --- Add new Slider for Max Scene Duration ---
                    max_scene_duration_slider_component = gr.Slider( # Renamed variable to avoid conflict if already in components
                        minimum=1.0, maximum=20.0, value=5.0, step=0.5,
                        label="场景最大时长(秒)",
                        info="控制单个场景的最长持续时间，值越小场景越多，节奏越快。",
                        interactive=True
                    )
                with gr.Column(scale=2):
                    one_click_process_button = gr.Button("一键生成", variant="primary", size="lg")
        
        with gr.Column(scale=3):
            output_text = gr.Markdown("等待处理...")
            output_video = gr.Video(
                label="生成的视频",
                visible=True,
                interactive=False
            )
    
    # --- 整合所有组件到 components 字典 (确保在事件处理之前完成) ---
    components = {
        "text_input": text_input,
        "file_dropdown": file_dropdown,
        "refresh_button": refresh_button,
        "format_text_button_shorts": format_text_button_shorts,
        "image_generator": image_generator,
        "aspect_ratio": aspect_ratio,
        "comfyui_style": comfyui_style,
        "image_style_type": image_style_type,
        "custom_style": custom_style,
        "mj_concurrency_selector": mj_concurrency_selector, 
        "mj_concurrency_warning": mj_concurrency_warning, 
        "font_name": font_name,
        "refresh_fonts_button": refresh_fonts_button,
        "font_size": font_size,
        "font_color": font_color,
        "bg_opacity": bg_opacity,
        "subtitle_vertical_offset": subtitle_vertical_offset,
        "show_all_fonts_button": show_all_fonts_button,
        "all_fonts_output": all_fonts_output,
        "voice_dropdown": voice_dropdown,
        "speed_scale_slider": speed_scale_slider_component,
        "video_engine": video_engine,
        "max_scene_duration_slider": max_scene_duration_slider_component,
        "one_click_process_button": one_click_process_button,
        "output_text": output_text,
        "output_video": output_video
    }
    
    # 添加其他设置中的组件 (它们本身就是字典，可以直接更新)
    components.update(other_settings_dict)
    # --- 结束组件整合 --- 
    
    # === 事件处理 (主流程) - 确保所有引用都通过 components 字典 ===
    # 刷新文件列表
    components["refresh_button"].click(fn=lambda: gr.Dropdown.update(choices=list_input_files()), inputs=None, outputs=components["file_dropdown"])
    
    # 刷新字体列表
    components["refresh_fonts_button"].click(fn=lambda: gr.Dropdown.update(choices=get_available_fonts()), inputs=None, outputs=components["font_name"])
    
    # 显示/隐藏所有字体列表
    components["show_all_fonts_button"].click(
        fn=lambda: gr.update(visible=True, value="\n".join(list_all_fonts()) or "fonts目录为空或不存在"), 
        inputs=None, 
        outputs=components["all_fonts_output"]
    )
    
    # 刷新角色形象列表
    components["refresh_character_button"].click(fn=lambda: gr.Dropdown.update(choices=list_character_images()), inputs=None, outputs=components["character_image"])
    
    # 联动：根据是否启用说话角色显示/隐藏选项
    components["talking_character"].change(
        fn=lambda enabled: (gr.update(visible=enabled), gr.update(visible=enabled)), 
        inputs=components["talking_character"], 
        outputs=[components["talking_character_options"], components["talking_sensitivity"]]
    )
    
    # 联动：根据图像生成器显示/隐藏 MJ/ComfyUI 特定选项
    components["image_generator"].change(
        fn=update_ui_based_on_generator, # 使用已有的辅助函数
        inputs=components["image_generator"],
        outputs=[components["aspect_ratio"], components["comfyui_style"]] 
    )
    
    # 联动：根据图像生成器显示/隐藏 MJ 并发选项和警告
    components["image_generator"].change(
        fn=lambda choice: (gr.update(visible=(choice == 'midjourney')), gr.update(visible=False if choice != 'midjourney' else (components["mj_concurrency_selector"].value == 10))), # 切换时隐藏警告, 但保留初始状态
        inputs=components["image_generator"],
        outputs=[components["mj_concurrency_selector"], components["mj_concurrency_warning"]]
    )
    
    # 联动：根据 MJ 并发数显示/隐藏警告
    components["mj_concurrency_selector"].change(
        fn=lambda choice: gr.update(visible=(choice == 10)), 
        inputs=components["mj_concurrency_selector"], 
        outputs=components["mj_concurrency_warning"]
    )

    # 联动：根据图像风格类型显示/隐藏自定义风格输入框
    components["image_style_type"].change(
        fn=lambda choice: gr.update(visible=(choice == '自定义风格')), # 仅当选择自定义风格时显示
        inputs=components["image_style_type"],
        outputs=components["custom_style"]
    )

    # --- Add event handler for the new format button ---
    components["format_text_button_shorts"].click(
        fn=format_text_for_shorts_gpt, # Connect to the backend function
        inputs=[components["text_input"]], # Input is the current text
        outputs=[components["text_input"]] # Output updates the text input
    )
    # --- End event handler ---

    # 一键生成按钮点击事件 (确保输入列表正确引用 components 字典中的键)
    components["one_click_process_button"].click(
        fn=process_story, 
        inputs=[
            components["file_dropdown"],         # 输入文件路径
            components["text_input"],            # 或直接输入文本
            components["image_generator"],       # 图像生成器类型
            components["aspect_ratio"],          # 图像比例
            components["image_style_type"],      # 图像风格类型
            components["custom_style"],          # 自定义风格文本
            components["comfyui_style"],         # ComfyUI特定风格
            components["font_name"],             # 字幕字体名称
            components["font_size"],             # 字幕字体大小
            components["font_color"],            # 字幕字体颜色
            components["bg_opacity"],            # 字幕背景不透明度
            components["character_image"],       # 角色图片路径
            components["preserve_line_breaks"],  # 是否保留原始换行
            components["voice_dropdown"],        # 角色声音
            components["speed_scale_slider"],    # 语速
            components["mj_concurrency_selector"],# MJ 并发数选择器
            components["video_resolution"],      # 视频分辨率
            components["video_engine"],          # 视频处理引擎
            components["talking_character"],     # 是否启用说话角色
            components["closed_mouth_image"],    # 闭嘴图片
            components["open_mouth_image"],      # 张嘴图片
            components["audio_sensitivity"],     # 音频敏感度
            # 假设有个 no_regenerate_images 的 Checkbox (如果需要从 UI 控制)
            gr.Checkbox(value=False, visible=False), # 临时占位符
            components["max_scene_duration_slider"] # Max Scene Duration
        ],
        outputs=[components["output_text"], components["output_video"]], 
        api_name="process_story_main"
    )
    
    return components

def _create_scene_editing_components() -> Dict[str, Any]:
    """创建场景编辑相关组件
    
    Returns:
        Dict[str, Any]: 场景编辑组件
    """
    # 创建场景编辑区域
    scene_editor = gr.Column(visible=False)
    with scene_editor:
        # 使用两列布局
        with gr.Row():
            # 左侧放文本内容和滑块
            with gr.Column(scale=2):
                # 场景滑块 - 增强视觉效果和清晰度
                scene_slider = gr.Slider(
                    minimum=1,
                    maximum=1,
                    value=1,
                    step=1,
                    label="👉 选择场景 (滑动选择您想编辑的场景) 👈",
                    interactive=True,
                    visible=False,
                    elem_id="scene_slider_enhanced",
                    container=True,
                    scale=3  # 增大滑块比例
                )
                current_scene_content = gr.Markdown(label="场景内容")
                current_scene_prompt = gr.Textbox(
                    label="场景提示词",
                    placeholder="编辑提示词以生成新的图像...",
                    lines=3
                )
                # 按钮放在底部一行
                with gr.Row():
                    regenerate_image_button = gr.Button("重新生成图片", variant="primary", size="sm")
                    upload_image_button = gr.Button("上传图片", size="sm")
            
            # 右侧放图片预览
            with gr.Column(scale=3):
                # 场景图片预览
                current_scene_image = gr.Image(
                    label="场景图片预览",
                    type="filepath",
                    interactive=False
                )
    
    return {
        "scene_editor": scene_editor,
        "current_scene_content": current_scene_content,
        "current_scene_prompt": current_scene_prompt,
        "current_scene_image": current_scene_image,
        "scene_slider": scene_slider,
        "regenerate_image_button": regenerate_image_button,
        "upload_image_button": upload_image_button
    }

def _create_upload_panel() -> Dict[str, Any]:
    """创建上传图片面板
    
    Returns:
        Dict[str, Any]: 上传面板组件
    """
    # 上传图片对话框
    upload_image_panel = gr.Column(visible=False)
    with upload_image_panel:
        gr.Markdown("## 上传自定义图片")
        scene_upload_image = gr.Image(
            type="filepath",
            label="选择图片"
        )
        with gr.Row():
            upload_confirm_button = gr.Button("确认上传", variant="primary")
            upload_cancel_button = gr.Button("取消")
    
    return {
        "upload_image_panel": upload_image_panel,
        "scene_upload_image": scene_upload_image,
        "upload_confirm_button": upload_confirm_button,
        "upload_cancel_button": upload_cancel_button
    }

def create_scene_management_ui() -> Dict[str, Any]:
    """创建场景管理UI组件
    
    Returns:
        Dict[str, Any]: 包含所有场景管理UI组件的字典
    """
    with gr.Row():
        with gr.Column(scale=2):
            with gr.Row():
                # 刷新场景按钮和场景计数在同一行
                refresh_scenes_button = gr.Button("刷新场景列表", variant="primary", size="sm")
                scene_count_label = gr.Markdown("场景: 0/0", visible=False)
            
            # 场景标题信息
            scene_info = gr.Markdown("请先在「一键生成」选项卡中生成视频，然后在此管理场景。")
            
            # 场景缩略图 - 使用HTML替代Gallery
            scene_thumbnails = gr.HTML(label="场景缩略图", visible=False)
            
            # 移除Gallery组件，只使用滑块
            scene_gallery = None

    # 创建场景编辑组件
    editing_components = _create_scene_editing_components()
    
    # 创建上传面板
    upload_components = _create_upload_panel()
    
    # 注意：以下元素将在webui_new.py中重新创建，这里只是创建占位符
    # 创建空对象而不是实际UI元素
    recompose_video_button = None
    no_regenerate_images = None
    clear_modifications_button = None
    
    # 隐藏的控制组件
    scene_controls = gr.Row(visible=False)
    with scene_controls:
        scene_index = gr.Number(label="场景索引", value=1, elem_id="scene_index")
        scene_prompt = gr.Textbox(label="场景提示词", elem_id="scene_prompt")
        all_prompts = gr.Textbox(label="所有提示词", elem_id="all_prompts")
    
    # 视频预览最后显示
    scene_video_preview = gr.Video(
        label="预览视频",
        interactive=False
    )
    
    # 整合所有组件
    components = {
        "refresh_scenes_button": refresh_scenes_button,
        "scene_info": scene_info,
        "scene_count_label": scene_count_label,
        "scene_thumbnails": scene_thumbnails,
        "scene_gallery": scene_gallery,
    }
    
    # 添加场景编辑组件
    components.update(editing_components)
    
    # 添加上传面板组件
    components.update(upload_components)
    
    # 添加其他控制组件
    components.update({
        "scene_controls": scene_controls,
        "scene_index": scene_index,
        "scene_prompt": scene_prompt,
        "all_prompts": all_prompts,
        "scene_video_preview": scene_video_preview
    })
    
    return components 