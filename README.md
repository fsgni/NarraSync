# NarraSync - 智能故事视频生成器

NarraSync是一个集成化的故事视频生成工具，可以将文本故事自动转换为配有图像、语音和字幕的完整视频。该工具特别适合创作者、教育工作者和内容制作者快速将文字内容可视化。

## 主要功能

- **文本分析与场景提取**：自动将输入文本分割为逻辑场景
- **AI图像生成**：基于场景描述自动生成相关图像
- **文本转语音**：使用VoiceVox引擎将文本转换为自然语音
- **视频合成**：将图像、音频和字幕合成为完整视频
- **场景编辑**：支持修改场景提示词、重新生成或上传自定义图像
- **视频重组**：在修改场景后快速重新合成视频而无需重新生成所有资源

## 特色

- **双模式界面**：提供"一键生成"和"场景管理"两种操作模式
- **多引擎支持**：支持多种图像生成引擎（Stable Diffusion、ComfyUI等）
- **灵活的字幕配置**：可自定义字幕字体、大小、颜色和背景透明度
- **角色图像集成**：支持添加角色图像到视频中
- **多种视频处理引擎**：支持FFmpeg和MoviePy两种视频处理引擎

## 安装指南

### 前置要求

- Python 3.8+
- FFmpeg（用于视频处理）
- VOICEVOX引擎（用于语音合成）
- ComfyUI（用于图像生成）

### 安装步骤

1. 克隆仓库：
```bash
git clone https://github.com/yourusername/NarraSync.git
cd NarraSync
```

2. 安装依赖：
```bash
pip install -r requirements.txt
```

3. 确保以下外部依赖已安装：
   - FFmpeg已添加到系统PATH
   - VOICEVOX引擎已运行（默认端口50021）
   - 如使用ComfyUI，确保ComfyUI服务已运行

## 使用方法

### 启动WebUI

```bash
python webui_new.py
```

### 一键生成模式

1. 输入或选择文本文件
2. 配置图像生成参数（生成器类型、比例、风格）
3. 设置字幕参数（字体、大小、颜色、背景透明度）
4. 选择语音和视频处理引擎
5. 点击"一键生成"按钮
6. 等待处理完成后查看结果视频

### 场景管理模式

1. 生成视频后，切换到"场景管理"选项卡
2. 点击"刷新场景列表"加载现有场景
3. 使用滑块浏览并选择要编辑的场景
4. 修改场景提示词后点击"重新生成图片"，或点击"上传图片"上传自定义图像
5. 完成所有编辑后，点击"重新合成视频"生成最终视频
6. 新生成的视频将保存为"webui_input_final.mp4"

## 项目结构

```
NarraSync/
├── webui_new.py          # 主WebUI入口
├── full_process.py       # 完整处理流程
├── video_processor.py    # 视频处理核心
├── voice_generator.py    # 语音生成模块
├── image_processor.py    # 图像处理模块
├── scene_manager.py      # 场景管理
├── add_subtitles.py      # 字幕添加模块
├── add_character_image.py # 角色图像添加模块
├── ui_components.py      # UI组件定义
├── ui_helpers.py         # UI辅助函数
├── config.py             # 配置管理
├── errors.py             # 错误处理
├── input_texts/          # 输入文本目录
├── input_images/         # 输入图像目录
└── output/               # 输出目录
```
[MIT License](LICENSE)

*注：本项目仍在积极开发中，欢迎提交问题和建议！* 