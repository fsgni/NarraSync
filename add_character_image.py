import os
import subprocess
from pathlib import Path
import sys
from PIL import Image
import shutil

def check_ffmpeg_available():
    """检查ffmpeg是否可用"""
    try:
        result = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True)
        if result.returncode == 0:
            print(f"ffmpeg可用: {result.stdout.splitlines()[0]}")
            return True
        else:
            print(f"ffmpeg命令返回错误: {result.stderr}")
            return False
    except FileNotFoundError:
        print("错误: 找不到ffmpeg命令。请确保ffmpeg已安装并添加到系统PATH中。")
        return False
    except Exception as e:
        print(f"检查ffmpeg时出错: {e}")
        return False

def add_character_image_to_video(input_video, character_image, output_video):
    """
    使用ffmpeg将角色图片添加到视频右下角，保留透明度
    
    参数:
        input_video: 输入视频文件路径
        character_image: 角色图片路径
        output_video: 输出视频文件路径
    """
    print(f"\n===== 开始添加角色图片 =====")
    print(f"输入视频: {input_video}")
    print(f"角色图片: {character_image}")
    print(f"输出视频: {output_video}")
    
    # 检查ffmpeg是否可用
    if not check_ffmpeg_available():
        print("由于ffmpeg不可用，无法添加角色图片")
        return False
    
    # 检查输入文件
    if not os.path.exists(input_video):
        print(f"错误: 输入视频不存在: {input_video}")
        return False
    
    if not os.path.exists(character_image):
        print(f"错误: 角色图片不存在: {character_image}")
        # 尝试查找可能的图片位置
        possible_locations = [
            os.path.join("output", os.path.basename(character_image)),
            os.path.join("input_images", os.path.basename(character_image))
        ]
        for loc in possible_locations:
            if os.path.exists(loc):
                print(f"找到可能的替代图片: {loc}")
                character_image = loc
                break
        else:
            print("无法找到替代图片")
            return False
    
    # 确保输出目录存在
    os.makedirs(os.path.dirname(os.path.abspath(output_video)), exist_ok=True)
    
    try:
        # 获取视频信息
        print("获取视频信息...")
        ffprobe_cmd = [
            "ffprobe", 
            "-v", "error", 
            "-select_streams", "v:0", 
            "-show_entries", "stream=width,height", 
            "-of", "csv=p=0", 
            input_video
        ]
        
        print(f"执行命令: {' '.join(ffprobe_cmd)}")
        result = subprocess.run(ffprobe_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"获取视频信息失败: {result.stderr}")
            return False
        
        # 解析视频宽高
        dimensions = result.stdout.strip().split(',')
        if len(dimensions) != 2:
            print(f"无法解析视频尺寸: {result.stdout}")
            return False
        
        video_width, video_height = map(int, dimensions)
        print(f"视频尺寸: {video_width}x{video_height}")
        
        # 处理角色图片
        print(f"处理角色图片: {character_image}")
        try:
            pil_img = Image.open(character_image)
        except Exception as e:
            print(f"打开图片失败: {e}")
            # 尝试复制图片到临时位置再打开
            temp_img = "output/temp_character_copy.png"
            try:
                shutil.copy2(character_image, temp_img)
                print(f"已复制图片到: {temp_img}")
                pil_img = Image.open(temp_img)
            except Exception as e2:
                print(f"复制并打开图片失败: {e2}")
                return False
        
        # 强制转换为RGBA模式，确保透明通道被保留
        print(f"原始图片模式: {pil_img.mode}")
        if pil_img.mode != 'RGBA':
            print(f"正在转换为RGBA模式...")
            # 如果图片是RGB模式，创建一个新的RGBA图片
            if pil_img.mode == 'RGB':
                # 创建一个新的RGBA图片
                rgba_img = Image.new('RGBA', pil_img.size, (0, 0, 0, 0))
                # 将原图复制到新图片，设置完全不透明
                rgba_img.paste(pil_img, (0, 0))
                pil_img = rgba_img
            else:
                # 对于其他模式，直接转换
                pil_img = pil_img.convert('RGBA')
        
        has_alpha = pil_img.mode == 'RGBA'
        print(f"图片模式: {pil_img.mode}, 是否有透明通道: {has_alpha}")
        
        # 调整角色图片大小，保持宽高比，最大尺寸为500x500
        char_width, char_height = pil_img.size
        char_aspect = char_width / char_height
        
        if char_width > char_height:
            # 宽度为主导
            new_width = min(500, char_width)
            new_height = int(new_width / char_aspect)
        else:
            # 高度为主导
            new_height = min(500, char_height)
            new_width = int(new_height * char_aspect)
        
        print(f"调整图片大小: {char_width}x{char_height} -> {new_width}x{new_height}")
        
        # 调整大小
        pil_img = pil_img.resize((new_width, new_height), Image.LANCZOS)
        
        # 保存处理后的图片
        temp_img_path = "output/temp_character_resized.png"
        print(f"保存调整大小后的图片到: {temp_img_path}")
        pil_img.save(temp_img_path, format="PNG", optimize=True, compress_level=0)
        
        # 验证保存的图片是否保留了透明通道
        saved_img = Image.open(temp_img_path)
        print(f"保存后的图片模式: {saved_img.mode}, 是否有透明通道: {saved_img.mode == 'RGBA'}")
        
        # 计算右下角位置，留出20像素的边距
        x_pos = video_width - new_width - 20
        y_pos = video_height - new_height - 10
        
        # 使用ffmpeg添加角色图片到视频
        print("使用ffmpeg添加角色图片到视频...")
        ffmpeg_cmd = [
            "ffmpeg",
            "-i", input_video,
            "-i", temp_img_path,
            "-filter_complex", f"overlay={x_pos}:{y_pos}",
            "-c:v", "libx264",  # 使用H.264编码
            "-pix_fmt", "yuv420p",  # 使用标准像素格式
            "-c:a", "copy",
            "-y",  # 覆盖输出文件
            output_video
        ]
        
        print(f"执行ffmpeg命令: {' '.join(ffmpeg_cmd)}")
        result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            print(f"添加角色图片失败: {result.stderr}")
            return False
        
        print(f"成功添加角色图片到视频: {output_video}")
        return True
    
    except Exception as e:
        print(f"处理过程中出错: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("用法: python add_character_image.py <输入视频> <角色图片> <输出视频>")
        sys.exit(1)
    
    input_video = sys.argv[1]
    character_image = sys.argv[2]
    output_video = sys.argv[3]
    
    success = add_character_image_to_video(input_video, character_image, output_video)
    if success:
        print("处理完成!")
    else:
        print("处理失败!")
        sys.exit(1) 