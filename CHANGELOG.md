# 更新日志 | Changelog

## [v1.0.9] - 2023-03-07

### 新增
- **视频预览功能**：WebUI中添加了视频预览和下载功能，用户可以直接在界面上查看和下载生成的视频。
- **视频文件管理**：添加了视频文件浏览器，可以查看历史生成的所有视频文件。

### 改进
- **文件编码处理**：修复了Unicode编码问题，使用系统默认编码处理文件，解决中文路径和内容的兼容性问题。
- **文件路径处理**：优化输入文件路径处理逻辑，支持绝对路径和相对路径，自动在input_texts目录中查找文件。
- **错误处理增强**：增强了Midjourney API错误处理，包括超时处理、重试机制和详细的错误日志。
- **文件检查改进**：在处理前对输入文件进行全面的检查，提供清晰的错误信息。

### 修复
- **空文件检测**：添加对空文件的检测，防止处理空文本文件时出现问题。
- **目录创建**：确保所有需要的目录（包括output/videos）都会被正确创建。
- **WebUI显示优化**：改善WebUI界面布局和用户体验，添加刷新按钮和更详细的使用说明。

## [v1.0.8] - 2023-10-29

### 改进
- **提示词精简优化**：大幅精简图像生成提示词，移除不必要的词汇和修饰语，提高图像生成准确性。
- **提示词结构改进**：优化提示词结构，控制提示词长度在30个词以内，更加聚焦于必要的视觉元素。
- **括号和格式清理**：自动清理场景描述中的括号和多余格式，减少对图像生成模型的干扰。
- **一致性增强**：提高文化、地点、时代和风格等元素在提示词中的一致性表达。

## [v1.0.7] - 2023-10-28

### 新增
- **分段分析功能**：增加对长文本的分段分析支持，可以更精确地处理长故事。
- **段落级别提示词**：为长故事的不同段落生成更准确的场景描述和提示词。

### 改进
- **长文本处理**：优化长文本处理流程，自动检测文本长度并使用合适的分析方法。
- **资源利用**：通过分段处理减少单次API请求的数据量，提高分析的准确性和稳定性。

## [v1.0.6] - 2023-10-27

### 改进
- **提示词英语化**：添加自动翻译功能，确保所有图像生成提示词都使用英语，提高图像生成质量和一致性。
- **多语言支持增强**：改进对非英语故事的处理，自动将文化、地点、时代和风格等元素翻译成英语。

## [v1.0.5] - 2023-10-26

### 改进
- **场景提示词优化**：改进场景提示词生成逻辑，更好地整合故事分析结果（文化、地点、时代和风格）到最终的图像生成提示词中。
- **提示词结构优化**：调整提示词结构，确保分析出的背景信息始终包含在图像生成提示中，提高图像与故事背景的一致性。

## [v1.0.4] - 2023-10-25

### 新增
- 新增 CHANGELOG.md 文件，用于记录版本更新历史。
- 新增基于 Gradio 的 WebUI 界面，提供更直观的操作体验。

### 改进
- 优化故事分析模块，支持更准确的 JSON 解析和场景描述生成，确保时代背景和场景描述的一致性。
- 改进 GPT 提示词，确保模型能够处理任何时代背景的故事场景。
- WebUI 提供实时预览功能，可以查看生成的图像和场景描述。

### 修复
- 修复了 JSON 解析错误和 GPT 拒绝生成特定场景的问题。
- 添加了更健壮的错误处理机制，确保即使分析失败也能提供合理的默认值。

## v1.0.3 (2023-11-xx)

### 改进
- **视频特效优化**：解决了视频特效中的抖动和黑边问题
- **平滑过渡**：添加了淡入淡出效果，使场景切换更加自然
- **图片尺寸调整**：增加图片尺寸到视频尺寸的115%，确保不会出现黑边
- **动画参数优化**：调整动画参数，提供更微妙、更专业的电影效果

## v1.0.2 (2023-11-xx)

### 新增功能
- **发音词典系统**：新增 VOICEVOX 发音词典管理功能，可纠正常见发音错误
- **词典管理工具**：添加 `manage_dictionary.py` 命令行工具，方便管理发音词典

### 改进
- **简化图像提示词**：优化图像生成提示词，减少过度细节描述
- **电影效果增强**：改进视频制作流程，提供更自然的镜头转场效果
- **文档更新**：更新 README.md，添加新功能说明和使用示例

### 修复
- 修复了语音合成中的发音错误问题

## v1.0.0 (初始版本)

- 基本文本处理功能
- VOICEVOX 语音合成
- 故事场景分析
- ComfyUI 图像生成
- 视频制作和字幕添加

## [v1.1.0] - 2023-03-08

### 新增
- **图像比例选择**：为Midjourney图像生成器添加了16:9和9:16宽高比选项，支持生成横屏和竖屏图像。
- **图像风格选择**：添加了预设风格选择功能，包括电影级品质、水墨画风格、油画风格、动漫风格、写实风格和梦幻风格，以及自定义风格输入。
- **风格控制优化**：改进了风格词汇的处理逻辑，避免风格混淆，确保生成图像风格的一致性。

### 改进
- **输出目录清理**：优化了输出目录清理功能，确保在开始新的视频生成时彻底清理所有临时文件，包括音频文件、图像文件和JSON文件。
- **WebUI界面优化**：改进了WebUI界面，添加了风格选择和图像比例选择控件，提供更直观的用户体验。
- **错误处理增强**：进一步增强了错误处理机制，提供更清晰的错误信息和日志输出。