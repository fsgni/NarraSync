import subprocess
import os
import logging
from pathlib import Path
from typing import List, Optional, Tuple

# 设置日志
logger = logging.getLogger("add_subtitles")

def add_subtitles(video_file: str, srt_file: str, output_file: str, 
                 font_name: str = "UD Digi Kyokasho N-B", 
                 font_size: int = 18, 
                 font_color: str = "FFFFFF", 
                 bg_opacity: float = 0.5) -> str:
    """
    为视频添加字幕
    
    参数:
        video_file: 输入视频文件路径
        srt_file: SRT字幕文件路径
        output_file: 输出视频文件路径
        font_name: 字体名称 (默认使用日语数字教科书字体)
        font_size: 字体大小 (默认18，较小)
        font_color: 字体颜色 (默认白色 FFFFFF)
        bg_opacity: 背景透明度 (0-1，0为完全透明，1为不透明)
        
    返回:
        output_file: 输出视频文件路径
        
    可能抛出:
        FileNotFoundError: 如果输入文件不存在
        subprocess.CalledProcessError: 如果FFmpeg命令执行失败
    """
    logger.info(f"开始为视频添加字幕: {video_file}")
    
    # 检查输入文件是否存在
    if not os.path.exists(video_file):
        error_msg = f"视频文件不存在: {video_file}"
        logger.error(error_msg)
        raise FileNotFoundError(error_msg)
    
    if not os.path.exists(srt_file):
        error_msg = f"字幕文件不存在: {srt_file}"
        logger.error(error_msg)
        raise FileNotFoundError(error_msg)
    
    # 确保输出目录存在
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # 检查字体是否存在
    try:
        font_name = check_font_name(font_name)
        logger.info(f"使用字体: {font_name}")
    except Exception as e:
        logger.warning(f"检查字体时出错，将使用默认值: {e}")
        # 出错时继续使用原始字体名称
    
    # 构建FFmpeg命令
    bg_alpha = max(0, min(255, int(bg_opacity * 255)))  # 范围限制在0-255
    logger.debug(f"背景透明度: {bg_opacity} (Alpha值: {bg_alpha})")
    
    # 确保颜色值是6位十六进制
    if font_color and (len(font_color) == 7 and font_color.startswith('#')):
        font_color = font_color[1:]  # 移除#号
    elif not font_color or len(font_color) != 6:
        logger.warning(f"无效的字体颜色值: '{font_color}'，使用默认白色")
        font_color = "FFFFFF"  # 如果颜色值无效，使用默认白色
    
    # 将颜色值转换为BGR格式（FFmpeg需要）
    bgr_color = font_color[4:6] + font_color[2:4] + font_color[0:2]
    logger.debug(f"字体颜色: #{font_color} (BGR格式: {bgr_color})")
    
    cmd = [
        'ffmpeg', '-y',
        '-i', video_file,
        '-vf', f"subtitles={srt_file}:force_style='FontName={font_name},FontSize={font_size},PrimaryColour=&H{bgr_color},BackColour=&H{bg_alpha}000000,BorderStyle=4,Outline=1,Shadow=1,MarginV=30'",
        '-c:v', 'libx264',
        '-c:a', 'copy',
        output_file
    ]
    
    logger.debug(f"FFmpeg命令: {' '.join(cmd)}")
    
    try:
        # 执行命令
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            logger.error(f"FFmpeg命令执行失败: {result.stderr}")
            raise subprocess.CalledProcessError(result.returncode, cmd, result.stdout, result.stderr)
        
        # 检查输出文件是否已生成
        if not os.path.exists(output_file) or os.path.getsize(output_file) == 0:
            error_msg = f"输出文件不存在或为空: {output_file}"
            logger.error(error_msg)
            raise RuntimeError(error_msg)
            
        logger.info(f"成功添加字幕，输出文件: {output_file}")
        return output_file
    except subprocess.CalledProcessError as e:
        error_msg = f"FFmpeg执行失败: {e.stderr if hasattr(e, 'stderr') else str(e)}"
        logger.exception(error_msg)
        raise
    except Exception as e:
        error_msg = f"添加字幕过程中出错: {str(e)}"
        logger.exception(error_msg)
        raise

def get_system_fonts() -> List[str]:
    """
    获取系统中所有可用的字体
    
    返回:
        List[str]: 系统中所有可用字体的列表
    """
    try:
        import matplotlib.font_manager as fm
        # 强制刷新字体缓存
        try:
            # 较新版本的matplotlib
            fm.fontManager.addfont = lambda *args, **kwargs: None  # 防止可能的错误
            fm._load_fontmanager(try_read_cache=False)
        except:
            try:
                # 旧版本的matplotlib
                if hasattr(fm, '_rebuild'):
                    fm._rebuild()
                else:
                    # 最后的尝试，重新创建fontManager
                    fm.fontManager = fm.FontManager()
            except:
                logger.warning("无法刷新字体缓存，将使用当前加载的字体")
        
        fonts = [f.name for f in fm.fontManager.ttflist]
        logger.info(f"系统中找到 {len(fonts)} 个字体")
        return fonts
    except ImportError:
        logger.warning("未安装matplotlib，无法获取系统字体列表")
        return []
    except Exception as e:
        logger.error(f"获取系统字体时出错: {e}")
        return []

def detect_system_language() -> Tuple[str, List[str]]:
    """
    检测系统语言并返回相应的默认字体列表
    
    返回:
        Tuple[str, List[str]]: 系统语言代码和推荐字体列表
    """
    try:
        # 尝试检测系统语言
        import locale
        system_locale = locale.getdefaultlocale()[0]
        logger.info(f"系统语言区域: {system_locale}")
        
        # 根据系统语言选择合适的默认字体
        if system_locale:
            if system_locale.startswith('ja'):
                # 日语系统
                default_fonts = ["UD Digi Kyokasho N-B", "Yu Gothic", "MS Gothic", "Meiryo"]
                return system_locale, default_fonts
            elif system_locale.startswith('zh'):
                # 中文系统
                default_fonts = ["Microsoft YaHei", "SimHei", "SimSun", "KaiTi"]
                return system_locale, default_fonts
            else:
                # 其他语言系统
                default_fonts = ["Arial", "Helvetica", "Verdana", "Tahoma"]
                return system_locale, default_fonts
        else:
            # 无法检测系统语言，使用通用字体
            default_fonts = ["Arial", "Helvetica", "Verdana", "Tahoma"]
            return "unknown", default_fonts
    except Exception as e:
        logger.error(f"检测系统语言时出错: {e}")
        return "unknown", ["Arial", "Helvetica", "Verdana", "Tahoma"]

def check_font_name(font_name: str = "UD Digi Kyokasho N-B") -> str:
    """
    检查系统中是否存在指定字体，如果不存在则返回备选字体
    
    参数:
        font_name: 首选字体名称
    
    返回:
        str: 存在的字体名称
    """
    logger.info(f"检查字体: {font_name}")
    
    # 如果用户选择了"默认"，则尝试找到最适合的字体
    if font_name == "默认":
        system_locale, default_fonts = detect_system_language()
        print(f"系统语言区域: {system_locale}")
        logger.info(f"检测到系统语言: {system_locale}, 推荐字体: {', '.join(default_fonts)}")
    else:
        # 用户指定了字体，将其作为首选
        default_fonts = [font_name]
    
    try:
        # 获取系统字体
        fonts = get_system_fonts()
        
        # 打印所有字体名称，帮助调试
        print(f"系统中找到 {len(fonts)} 个字体")
        
        # 检查用户指定的字体是否存在
        for preferred_font in default_fonts:
            if preferred_font in fonts:
                print(f"使用字体: {preferred_font}")
                logger.info(f"找到完全匹配的字体: {preferred_font}")
                return preferred_font
        
        # 如果用户指定的字体不存在，尝试找到类似的字体
        for preferred_font in default_fonts:
            for system_font in fonts:
                if preferred_font.lower() in system_font.lower():
                    print(f"找到类似字体: {system_font} (替代 {preferred_font})")
                    logger.info(f"找到类似字体: {system_font} (替代 {preferred_font})")
                    return system_font
        
        # 查找日语字体
        japanese_fonts = [f for f in fonts if "digi" in f.lower() or "kyokasho" in f.lower() or 
                          "教科書" in f or "gothic" in f.lower() or "mincho" in f.lower() or 
                          "meiryo" in f.lower() or "yu" in f.lower()]
        
        if japanese_fonts:
            print(f"使用日语字体: {japanese_fonts[0]}")
            logger.info(f"使用日语字体: {japanese_fonts[0]}")
            return japanese_fonts[0]
            
        # 查找中文字体
        chinese_fonts = [f for f in fonts if "simhei" in f.lower() or "yahei" in f.lower() or 
                         "simsun" in f.lower() or "kaiti" in f.lower() or "fangsong" in f.lower() or
                         "黑体" in f or "宋体" in f or "楷体" in f or "仿宋" in f]
        
        if chinese_fonts:
            print(f"使用中文字体: {chinese_fonts[0]}")
            logger.info(f"使用中文字体: {chinese_fonts[0]}")
            return chinese_fonts[0]
        
        # 查找备选字体
        for backup_font in ["SimHei", "Microsoft YaHei", "Arial", "Helvetica", "Verdana"]:
            if backup_font in fonts:
                print(f"使用备选字体: {backup_font}")
                logger.info(f"使用备选字体: {backup_font}")
                return backup_font
        
        # 如果找不到合适的字体，返回系统中的第一个字体
        if fonts:
            print(f"使用系统第一个字体: {fonts[0]}")
            logger.info(f"使用系统第一个字体: {fonts[0]}")
            return fonts[0]
        
        # 如果实在找不到任何字体，返回原始字体名称
        print(f"未找到任何字体，使用原始名称: {font_name}")
        logger.warning(f"未找到任何字体，使用原始名称: {font_name}")
        return font_name
    except Exception as e:
        print(f"检查字体时出错: {e}")
        logger.exception(f"检查字体时出错: {e}")
        return font_name

if __name__ == "__main__":
    # 设置日志配置
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler("output/add_subtitles.log", mode='a'),
            logging.StreamHandler()
        ]
    )
    
    try:
    # 先检查字体
        print("检查系统字体...")
        font_name = check_font_name()
        
        # 输入视频
        video_file = "output/final_video_moviepy.mp4"
        # 字幕文件
        srt_file = "output/豚.srt"
        # 输出文件
        output_file = "output/TESTTEST_final.mp4"
        
        if not os.path.exists(video_file):
            available_videos = list(Path("output").glob("*.mp4"))
            if available_videos:
                video_file = str(available_videos[0])
                print(f"找到替代视频文件: {video_file}")
                logger.info(f"找到替代视频文件: {video_file}")
            else:
                raise FileNotFoundError(f"找不到视频文件: {video_file}")
                
        if not os.path.exists(srt_file):
            available_srt = list(Path("output").glob("*.srt"))
            if available_srt:
                srt_file = str(available_srt[0])
                print(f"找到替代字幕文件: {srt_file}")
                logger.info(f"找到替代字幕文件: {srt_file}")
            else:
                raise FileNotFoundError(f"找不到字幕文件: {srt_file}")
        
        # 添加字幕
        add_subtitles(video_file, srt_file, output_file, font_name=font_name)
        print(f"成功添加字幕，输出文件: {output_file}")
    except Exception as e:
        print(f"添加字幕失败: {e}")
        logger.exception("添加字幕失败")
        import traceback
        traceback.print_exc() 