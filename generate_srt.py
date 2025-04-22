import json
import logging
from pathlib import Path
from datetime import timedelta
from typing import List, Dict, Any

# 设置日志
logger = logging.getLogger("generate_srt")

def format_srt_time(seconds: float) -> str:
    """
    将秒数转换为 SRT 时间格式 (HH:MM:SS,mmm)
    
    Args:
        seconds: 需要转换的秒数
        
    Returns:
        str: 格式化后的SRT时间字符串
    """
    td = timedelta(seconds=seconds)
    hours = int(td.total_seconds() // 3600)
    minutes = int((td.total_seconds() % 3600) // 60)
    seconds = td.total_seconds() % 60
    milliseconds = int((seconds % 1) * 1000)
    seconds = int(seconds)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"

def split_long_sentence(text: str, max_length: int = 25, respect_line_breaks: bool = False) -> str:
    """
    将长句子分成多行，避免标点符号单独成行
    
    Args:
        text: 要分割的文本
        max_length: 每行的最大长度
        respect_line_breaks: 是否尊重文本中原有的换行符
        
    Returns:
        str: 分割后的文本，如果需要分割则包含换行符
    """
    if not text:
        return ""
        
    # 如果需要尊重原始换行符，直接返回文本
    if respect_line_breaks and '\n' in text:
        return text
    
    if len(text) <= max_length:
        return text
    
    # 定义标点符号
    punctuations = ['。', '、', '，', '！', '？', '」', '』', '）', '：', '…']
    
    # 如果文本以引号开始，特殊处理
    if text.startswith('「') or text.startswith('『'):
        quote = text[0]
        inner_text = text[1:]
        # 递归处理内部文本
        inner_lines = split_long_sentence(inner_text, max_length - 1, respect_line_breaks)  # 减1为引号预留空间
        lines = [quote + line if i == 0 else line for i, line in enumerate(inner_lines.split('\n'))]
        return '\n'.join(lines)
    
    # 寻找最佳分割点
    best_split = max_length
    for i in range(max_length, 0, -1):
        if i >= len(text):
            continue
        # 避免在标点符号前分行
        if text[i] in punctuations:
            continue
        # 找到合适的分割点
        if text[i-1] not in punctuations:
            best_split = i
            break
    
    # 分割文本
    first_line = text[:best_split]
    remaining_text = text[best_split:]
    
    # 如果剩余文本不为空，递归处理
    if remaining_text:
        # 处理标点符号
        if remaining_text[0] in punctuations:
            first_line += remaining_text[0]
            remaining_text = remaining_text[1:]
        
        if remaining_text:
            return first_line + '\n' + split_long_sentence(remaining_text, max_length, respect_line_breaks)
    
    return first_line

def load_audio_info(audio_info_file: str) -> Dict[str, Any]:
    """
    加载音频信息文件
    
    Args:
        audio_info_file: 音频信息文件路径
        
    Returns:
        Dict: 音频信息数据字典
        
    Raises:
        FileNotFoundError: 文件不存在时抛出
        json.JSONDecodeError: JSON解析错误时抛出
    """
    try:
        logger.info(f"正在读取音频信息文件: {audio_info_file}")
        with open(audio_info_file, 'r', encoding='utf-8') as f:
            info = json.load(f)
        logger.info(f"成功加载音频信息，包含 {len(info.get('audio_files', []))} 个音频条目")
        return info
    except FileNotFoundError:
        error_msg = f"找不到音频信息文件: {audio_info_file}"
        logger.error(error_msg)
        raise FileNotFoundError(error_msg)
    except json.JSONDecodeError as e:
        error_msg = f"音频信息文件格式错误: {e}"
        logger.error(error_msg)
        raise

def create_srt_entries(audio_files: List[Dict[str, Any]], respect_line_breaks: bool = False) -> List[str]:
    """
    根据音频文件信息创建SRT条目
    
    Args:
        audio_files: 音频文件信息列表
        respect_line_breaks: 是否尊重文本中原有的换行符
        
    Returns:
        List[str]: SRT条目列表
    """
    srt_entries = []
    current_time = 0.0
    
    for i, audio in enumerate(audio_files, 1):
        try:
            # 获取开始和结束时间
            start_time = current_time
            duration = audio.get('duration', 0)
            end_time = start_time + duration
            
            # 检查并处理句子文本
            if 'sentence' not in audio:
                logger.warning(f"第 {i} 条音频信息缺少句子文本，将跳过")
                continue
                
            text = split_long_sentence(audio['sentence'], respect_line_breaks=respect_line_breaks)
            
            # 格式化字幕条目
            srt_entry = (
                f"{i}\n"
                f"{format_srt_time(start_time)} --> {format_srt_time(end_time)}\n"
                f"{text}\n"
            )
            srt_entries.append(srt_entry)
            
            # 更新当前时间
            current_time = end_time
        except Exception as e:
            logger.error(f"处理第 {i} 条字幕时出错: {e}")
            # 继续处理下一条，不中断整个流程
            continue
    
    return srt_entries

def generate_srt(audio_info_file: str, output_file: str, respect_line_breaks: bool = False):
    """
    根据音频信息生成 SRT 字幕文件
    
    Args:
        audio_info_file: 音频信息文件路径
        output_file: 输出的SRT文件路径
        respect_line_breaks: 是否尊重文本中原有的换行符
    """
    try:
        # 确保输出目录存在
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 读取音频信息
        info = load_audio_info(audio_info_file)
        
        # 获取音频文件信息
        audio_files = info.get('audio_files', [])
        if not audio_files:
            logger.warning(f"音频信息文件不包含任何音频条目: {audio_info_file}")
            print(f"警告: 音频信息文件不包含任何音频条目")
            return
        
        # 生成SRT条目
        srt_entries = create_srt_entries(audio_files, respect_line_breaks)
        
        # 计算总时长
        total_duration = sum(audio.get('duration', 0) for audio in audio_files)
        
        # 写入 SRT 文件
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write("\n".join(srt_entries))
        
        print(f"已生成字幕文件: {output_file}")
        print(f"总字幕条数: {len(srt_entries)}")
        print(f"总时长: {format_srt_time(total_duration)}")
        logger.info(f"成功生成字幕文件: {output_file}，共 {len(srt_entries)} 条，总时长 {format_srt_time(total_duration)}")
        
    except Exception as e:
        error_msg = f"生成SRT字幕文件时出错: {e}"
        print(error_msg)
        logger.exception(error_msg)
        raise

if __name__ == "__main__":
    # 设置日志配置
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler("output/generate_srt.log", mode='a'),
            logging.StreamHandler()
        ]
    )
    
    # 音频信息文件路径
    audio_info_file = "output/audio/audio_info.json"
    # 输出的 SRT 文件路径
    output_file = "output/audio/audio_info.srt"
    
    try:
        generate_srt(audio_info_file, output_file)
        print("字幕生成成功")
    except Exception as e:
        print(f"字幕生成失败: {e}")
        import traceback
        traceback.print_exc() 