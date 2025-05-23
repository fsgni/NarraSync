import requests
import json
import time
import os
import random
import string
from pathlib import Path
from dotenv import load_dotenv
import asyncio

class MidjourneyGenerator:
    def __init__(self, host=None, port=None):
        """初始化Midjourney生成器"""
        # 加载环境变量
        load_dotenv()
        
        # 从环境变量获取配置，如果未提供则使用默认值
        self.host = host or os.getenv("MIDJOURNEY_API_HOST", "localhost")
        self.port = port or os.getenv("MIDJOURNEY_API_PORT", "8080")
        
        self.api_base_url = f"http://{self.host}:{self.port}/mj"
        self.output_dir = Path("output/images")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        print(f"Midjourney生成器已初始化，API地址: {self.api_base_url}")
        
        # 验证API连接
        try:
            response = requests.get(f"{self.api_base_url}/task/list?limit=1", timeout=5)
            response.raise_for_status()
            print("Midjourney API连接成功!")
        except Exception as e:
            print(f"警告: 无法连接到Midjourney API: {e}")
            print("请确认以下几点:")
            print("1. Docker容器是否正在运行")
            print(f"2. API地址是否正确 (当前: http://{self.host}:{self.port}/mj)")
            print("3. 防火墙是否允许该连接")
            print("4. 环境变量 MIDJOURNEY_API_HOST 和 MIDJOURNEY_API_PORT 是否正确设置")
    
    def submit_imagine_task(self, prompt, aspect_ratio=None):
        """提交一个绘图任务
        
        Args:
            prompt: 图像生成提示词
            aspect_ratio: 图像比例，可选值为 "16:9", "9:16" 或 None (默认方形)
        """
        url = f"{self.api_base_url}/submit/imagine"
        
        # 确保prompt是字符串类型
        if not isinstance(prompt, str):
            print(f"警告: 提示词不是字符串类型，尝试转换。原始类型: {type(prompt)}")
            try:
                if isinstance(prompt, dict) and 'prompt' in prompt:
                    prompt = prompt['prompt']
                prompt = str(prompt)
            except Exception as e:
                print(f"转换提示词失败: {e}")
                return None
        
        # 增强提示词以提高质量
        enhanced_prompt = prompt + ", high quality, detailed"
        
        # 添加宽高比参数
        if aspect_ratio:
            if aspect_ratio == "16:9" or aspect_ratio == "9:16":
                # 确保使用正确的格式: --ar 16:9 而不是 --16:9
                enhanced_prompt += f" --ar {aspect_ratio}"
                print(f"使用宽高比: --ar {aspect_ratio}")
        
        print(f"最终提示词: {enhanced_prompt}")
        
        payload = {
            "prompt": enhanced_prompt,
            "base64": None,  # 不使用图片
            "notifyHook": None  # 不使用回调
        }
        
        headers = {
            "Content-Type": "application/json"
        }
        
        try:
            # 添加超时处理
            response = requests.post(url, json=payload, headers=headers, timeout=30)
            response.raise_for_status()  # 确保请求成功
            result = response.json()
            
            if result.get("code") not in [1, 22]:  # 1=成功，22=排队中
                error_code = result.get("code", "未知代码")
                error_desc = result.get('description', '未知错误')
                # 修改打印信息，包含错误代码
                print(f"!!! 任务提交失败! 代理返回代码: {error_code}, 描述: {error_desc}")
                return None
            
            task_id = result.get("result")
            print(f"绘图任务已提交，任务ID: {task_id}")
            return task_id
            
        except requests.exceptions.Timeout:
            print("提交任务超时，请检查网络连接和API服务器状态")
            return None
        except requests.exceptions.RequestException as e:
            print(f"提交任务时发生错误: {e}")
            return None
        except Exception as e:
            print(f"提交任务时发生未知错误: {e}")
            return None

    def submit_upscale_task(self, task_id, index):
        """提交一个放大任务，从初始4图中选择一张"""
        url = f"{self.api_base_url}/submit/simple-change"
        
        # 构建格式为"任务ID 操作"的content
        content = f"{task_id} U{index}"
        
        payload = {
            "content": content,
            "notifyHook": None
        }
        
        headers = {
            "Content-Type": "application/json"
        }
        
        try:
            print(f"提交放大请求：{content}")
            response = requests.post(url, json=payload, headers=headers, timeout=30)
            response.raise_for_status()  # 确保请求成功
            result = response.json()
            
            if result.get("code") == -1:
                print(f"API返回错误: {result.get('description', '未知错误')}")
            
            return result
        except requests.exceptions.Timeout:
            print("提交放大任务超时")
            return {"code": -1, "description": "请求超时"}
        except requests.exceptions.ConnectionError:
            print("连接API服务器失败")
            return {"code": -1, "description": "连接错误"}
        except Exception as e:
            print(f"提交放大任务时出错: {e}")
            return {"code": -1, "description": f"错误: {str(e)}"}

    def check_task_status(self, task_id):
        """检查任务状态"""
        url = f"{self.api_base_url}/task/{task_id}/fetch"
        
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()  # 确保请求成功
            return response.json()
        except requests.exceptions.Timeout:
            print("检查任务状态超时")
            return {"status": "ERROR", "description": "请求超时"}
        except requests.exceptions.ConnectionError:
            print("连接API服务器失败")
            return {"status": "ERROR", "description": "连接错误"}
        except Exception as e:
            print(f"检查任务状态时出错: {e}")
            return {"status": "ERROR", "description": f"错误: {str(e)}"}

    def download_image(self, image_url, save_path):
        """下载并保存图片"""
        try:
            # 添加必要的请求头模拟浏览器行为
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
                "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Referer": "https://www.midjourney.com/",
                "sec-ch-ua": '"Chromium";v="118", "Google Chrome";v="118", "Not=A?Brand";v="99"',
                "sec-ch-ua-platform": '"Windows"'
            }
            
            # 下载图片内容
            response = requests.get(image_url, headers=headers, stream=True, timeout=60)
            response.raise_for_status()  # 确保请求成功
            
            # 保存图片到文件
            save_path_obj = Path(save_path)
            save_path_obj.parent.mkdir(parents=True, exist_ok=True)
            
            with open(save_path_obj, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
                    
            print(f"图片已保存到: {save_path}")
            return True
        except requests.exceptions.Timeout:
            print("下载图片超时，请检查网络连接")
            # 将URL保存到文本文件，以便用户可以手动打开
            url_file = str(save_path) + "_url.txt"
            with open(url_file, 'w') as f:
                f.write(f"图片URL: {image_url}\n")
                f.write("由于下载超时，请在浏览器中手动打开此URL下载图片。")
            print(f"URL已保存到: {url_file}")
            return False
        except Exception as e:
            print(f"下载图片失败: {e}")
            
            # 如果是403错误，提供更多信息
            if isinstance(e, requests.exceptions.HTTPError) and e.response.status_code == 403:
                print("收到403 Forbidden错误。这通常意味着Discord拒绝了访问。")
                print("您可以尝试手动在浏览器中打开URL")
                
                # 将URL保存到文本文件，以便用户可以手动打开
                url_file = str(save_path) + "_url.txt"
                with open(url_file, 'w') as f:
                    f.write(f"图片URL: {image_url}\n")
                    f.write("由于访问限制，请在浏览器中手动打开此URL下载图片。")
                print(f"URL已保存到: {url_file}")
            return False

    async def wait_for_task_completion_async(self, task_id, max_retries=30, retry_interval=5):
        """异步等待任务完成并返回结果"""
        for i in range(max_retries):
            # 注意: check_task_status 本身还是同步的，但在异步函数中调用没问题
            # 如果 check_task_status 网络IO很重，理想情况下也应改为异步，但暂时先这样
            status_result = self.check_task_status(task_id)
            status = status_result.get("status")
            progress = status_result.get("progress", "未知")
            
            print(f"检查 {i+1}/{max_retries}: 状态={status}, 进度={progress}")
            
            if status == "SUCCESS":
                print("任务成功完成")
                return status_result
            elif status == "FAILURE":
                fail_reason = status_result.get("failReason", "未知")
                print(f"任务失败: {fail_reason}")
                return status_result
            elif status == "ERROR":
                print(f"检查任务状态出错: {status_result.get('description', '未知错误')}")
                # 尝试再次检查，可能是临时性网络问题
                time.sleep(2)
                continue
            
            if i < max_retries - 1:
                print(f"等待 {retry_interval} 秒后重试...")
                # 使用 asyncio.sleep 进行异步等待
                await asyncio.sleep(retry_interval) 
        
        print("等待超时")
        return None

    async def generate_image_async(self, prompt, output_filename=None, max_retries=3, aspect_ratio=None):
        """生成图像的完整流程 (异步版本)
        
        Args:
            prompt: 图像生成提示词
            output_filename: 输出文件名，如果不提供则自动生成
            max_retries: 最大重试次数
            aspect_ratio: 图像比例，可选值为 "16:9", "9:16" 或 None (默认方形)
        
        Returns:
            图像文件的路径 (str) 或 None (失败时)
        """
        # 确保 prompt 是字符串
        prompt = str(prompt)
        
        # 生成唯一文件名（如果未提供）
        if output_filename is None:
            random_suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
            output_filename = f"mj_image_{int(time.time())}_{random_suffix}.png"
        
        save_path = self.output_dir / output_filename

        # 主要生成逻辑，包含重试
        for attempt in range(max_retries):
            print(f"尝试生成图像 (第 {attempt + 1}/{max_retries} 次): {prompt[:50]}...")
            # 1. 提交初始绘图任务
            initial_task_id = self.submit_imagine_task(prompt, aspect_ratio=aspect_ratio)

            if initial_task_id:
                print(f"初始任务 {initial_task_id} 已提交，开始等待结果...")
                # 2. 等待初始任务完成 (异步)
                initial_result = await self.wait_for_task_completion_async(initial_task_id)

                if initial_result and initial_result.get("status") == "SUCCESS":
                    print(f"初始任务 {initial_task_id} 成功完成。")
                    initial_image_url = initial_result.get("imageUrl") # 获取四宫格图URL (可能用于调试)
                    if initial_image_url:
                        print(f"获取到初始四宫格图URL: {initial_image_url}")
                    else:
                        print(f"警告：初始任务 {initial_task_id} 成功但未找到图像URL")
                        # 即使没有URL，也可能继续尝试放大（某些情况下API可能不返回初始URL）

                    # --- 添加放大逻辑 ---
                    try:
                        # 3. 随机选择一个图像进行放大 (U1, U2, U3, U4)
                        upscale_index = random.randint(1, 4)
                        print(f"选择第 {upscale_index} 张图片进行放大...")
                        upscale_submission_result = self.submit_upscale_task(initial_task_id, upscale_index) # 同步提交

                        if upscale_submission_result.get("code") not in [1, 21, 22]: # 1=成功, 21=已存在, 22=排队中
                            reason = upscale_submission_result.get('description', '未知错误')
                            print(f"!!! 放大任务提交失败 (任务ID: {initial_task_id}, U{upscale_index}): {reason}")
                            # 决定是否重试整个流程
                            if attempt < max_retries - 1:
                                print("将重试整个生成流程...")
                                continue # 跳到下一次外层循环重试
                            else:
                                print("!!! 放大任务提交失败，达到最大重试次数")
                                return None # 达到最大重试次数

                        upscale_task_id = upscale_submission_result.get("result")
                        if not upscale_task_id:
                            print(f"!!! 放大任务提交后未获取到有效的任务ID: {upscale_submission_result}")
                            if attempt < max_retries - 1: continue
                            else:
                                print("!!! 放大任务未获取ID，达到最大重试次数")
                                return None

                        print(f"放大任务 {upscale_task_id} 已提交 (来自初始任务 {initial_task_id}, U{upscale_index})，等待完成...")

                        # 4. 等待放大任务完成 (异步)
                        final_result = await self.wait_for_task_completion_async(upscale_task_id)

                        if final_result and final_result.get("status") == "SUCCESS":
                            # 5. 下载最终的放大图像
                            final_image_url = final_result.get("imageUrl")
                            if final_image_url:
                                print(f"放大任务 {upscale_task_id} 成功，最终URL: {final_image_url}")
                                if self.download_image(final_image_url, save_path):
                                    return str(save_path) # 成功！返回路径
                                else:
                                    print(f"!!! 最终图像下载失败: {final_image_url}")
                                    # 下载失败，可能需要重试整个流程
                            else:
                                print(f"!!! 放大任务 {upscale_task_id} 成功但未找到最终图像URL")
                        else:
                            reason = final_result.get("failReason", "未知原因") if final_result else "等待超时"
                            print(f"!!! 放大任务 {upscale_task_id} 失败或超时: {reason}")
                    except Exception as upscale_err:
                         print(f"!!! 处理放大任务时发生异常: {upscale_err}")
                         # 出现异常也视为失败，可能需要重试

                else: # 初始任务失败或超时
                    reason = initial_result.get("failReason", "未知原因") if initial_result else "等待超时"
                    print(f"!!! 初始任务 {initial_task_id} 失败或超时: {reason}")
            else: # 提交初始任务失败
                print("!!! 提交初始任务失败")

            # 如果执行到这里，说明当前尝试失败
            print(f"--- 第 {attempt + 1} 次尝试失败 ---")

        print(f"图像生成失败，已达到最大重试次数: {prompt[:50]}...")
        return None

    def generate_image(self, prompt, output_filename=None, max_retries=3, aspect_ratio=None):
        """生成图像的完整流程
        
        Args:
            prompt: 图像生成提示词
            output_filename: 输出文件名，如果不提供则自动生成
            max_retries: 最大重试次数
            aspect_ratio: 图像比例，可选值为 "16:9", "9:16" 或 None (默认方形)
        
        Returns:
            生成的图像文件路径，如果失败则返回None
        """
        # 如果没有提供输出文件名，则自动生成一个
        if not output_filename:
            timestamp = int(time.time())
            random_str = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
            output_filename = f"mj_{timestamp}_{random_str}.png"
        
        # 确保输出目录存在
        output_path = self.output_dir / output_filename
        
        # 重试机制
        for attempt in range(max_retries):
            try:
                print(f"尝试 {attempt+1}/{max_retries} 生成图像...")
                
                # 1. 提交初始绘图任务
                initial_task_id = self.submit_imagine_task(prompt, aspect_ratio)
                if not initial_task_id:
                    print("提交初始任务失败，重试...")
                    continue
                
                # 2. 等待初始任务完成
                print("等待初始任务完成...")
                initial_result = self.wait_for_task_completion(initial_task_id)
                
                if not initial_result or initial_result.get("status") != "SUCCESS":
                    print("初始任务未成功完成")
                    continue  # 尝试重新提交
                
                # 保存初始的四宫格图像
                initial_image_url = initial_result.get("imageUrl")
                if initial_image_url:
                    # 不再保存grid图片，只记录URL用于调试
                    print(f"获取到初始四宫格图像URL: {initial_image_url}")
                else:
                    print("未找到初始图像URL")
                    continue  # 尝试重新提交
                
                # 3. 随机选择一个图像进行放大 (U1, U2, U3, U4)
                upscale_index = random.randint(1, 4)
                upscale_result = self.submit_upscale_task(initial_task_id, upscale_index)
                
                if upscale_result.get("code") not in [1, 21, 22]:  # 1=成功，21=已存在，22=排队中
                    print(f"放大任务提交失败: {upscale_result.get('description', '未知错误')}")
                    continue  # 尝试重新提交
                
                # 获取放大任务ID
                upscale_task_id = upscale_result.get("result")
                print(f"放大任务ID: {upscale_task_id}")
                
                # 4. 等待放大任务完成
                print("等待放大任务完成...")
                final_result = self.wait_for_task_completion(upscale_task_id)
                
                if not final_result or final_result.get("status") != "SUCCESS":
                    print("放大任务未成功完成")
                    continue  # 尝试重新提交
                
                # 5. 下载最终的放大图像
                final_image_url = final_result.get("imageUrl")
                if final_image_url:
                    download_success = self.download_image(final_image_url, output_path)
                    if not download_success:
                        print("最终图片无法自动下载")
                        continue  # 尝试重新提交
                    return output_path
                else:
                    print("未找到最终图片URL")
                    continue  # 尝试重新提交
            except Exception as e:
                print(f"生成图像时发生错误: {e}")
                time.sleep(5)  # 等待一段时间后重试
        
        print(f"经过{max_retries}次尝试后仍然失败")
        return None

    def generate_images(self, key_scenes_file: str):
        """为所有场景生成图片，与ComfyUIGenerator接口兼容"""
        try:
            # 读取场景信息
            with open(key_scenes_file, "r", encoding="utf-8") as f:
                scenes = json.load(f)
            
            print(f"找到 {len(scenes)} 个场景需要生成图片")
            
            success_count = 0
            for scene in scenes:
                print(f"\n生成场景 {scene['scene_id']} 的图片...")
                
                # 确保提取正确的提示词
                if isinstance(scene, dict) and 'prompt' in scene:
                    prompt = scene['prompt']
                else:
                    prompt = str(scene)
                
                print(f"提示词: {prompt}")
                
                # 准备输出文件名
                output_file = self.output_dir / scene['image_file']
                if output_file.exists():
                    print(f"图片已存在: {output_file}")
                    success_count += 1
                    continue
                
                # 使用Midjourney生成图片
                success = self.generate_image(prompt, output_file)
                
                if success:
                    success_count += 1
                    print(f"场景 {scene['scene_id']} 图片生成成功")
                else:
                    print(f"场景 {scene['scene_id']} 图片生成失败")
                
                # 等待一小段时间再生成下一张，避免API限流
                time.sleep(3)
            
            print(f"\n任务完成，成功生成 {success_count}/{len(scenes)} 个场景的图片")
            return success_count == len(scenes)
        except Exception as e:
            print(f"生成图片过程中发生错误: {e}")
            import traceback
            traceback.print_exc()
            return False


if __name__ == "__main__":
    # 测试代码
    generator = MidjourneyGenerator()
    
    # 测试API连接
    test_file = "output/images/test_midjourney.png"
    result = generator.generate_image(
        "a beautiful cat in ancient Chinese style, digital painting", 
        test_file
    )
    
    if result:
        print(f"测试成功! 图片已保存到: {test_file}")
    else:
        print("测试失败，请检查错误信息") 