import websocket
import uuid
import json
import urllib.request
import urllib.parse
import os
import logging
from pathlib import Path
import time
import random
import traceback
from typing import Dict, Any, Optional, List, Union

# 设置日志
logger = logging.getLogger("image_generator")

class ComfyUIGenerator:
    """ComfyUI图像生成器，用于通过ComfyUI API生成图片"""
    
    def __init__(self, host: str = "127.0.0.1", port: str = "8188", style: Optional[str] = None):
        """
        初始化ComfyUI图像生成器
        
        Args:
            host: ComfyUI服务器主机名
            port: ComfyUI服务器端口
            style: 图像生成风格
        """
        self.server_address = f"{host}:{port}"
        self.client_id = str(uuid.uuid4())
        self.output_dir = Path("output/images")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"初始化ComfyUI生成器，服务器地址: {self.server_address}")
        
        # 可用的风格选项
        self.available_styles = {
            "水墨": "写实水墨水彩风格_F1_水墨.safetensors",
            "手绘": "星揽_手绘线条小清新漫画风格V2_v1.0.safetensors",
            "古风": "中国古典风格滤镜_flux_V1.0.safetensors",
            "插画": "Illustration_story book.safetensors",
            "写实": "adilson-farias-flux1-dev-v1-000088.safetensors",
            "电影": "Cinematic style 3 (FLUX).safetensors"  # 默认风格
        }
        
        # 设置风格
        self.style = style if style in self.available_styles else "电影"
        self.lora_name = self.available_styles[self.style]
        print(f"使用风格: {self.style} (Lora: {self.lora_name})")
        logger.info(f"使用风格: {self.style} (Lora: {self.lora_name})")
        
        # 加载工作流配置
        self.workflow = self._load_workflow()

    def _load_workflow(self) -> Dict[str, Any]:
        """
        加载工作流配置文件
        
        Returns:
            Dict: 工作流配置数据
            
        Raises:
            FileNotFoundError: 找不到工作流文件时抛出
            json.JSONDecodeError: JSON解析错误时抛出
        """
        workflow_file = "workflows/waterink.json"
        try:
            with open(workflow_file, "r", encoding="utf-8") as f:
                workflow = json.load(f)
                print("成功加载工作流配置")
                logger.info(f"成功加载工作流配置: {workflow_file}")
                return workflow
        except FileNotFoundError:
            error_msg = f"找不到工作流配置文件: {workflow_file}"
            print(error_msg)
            logger.error(error_msg)
            raise
        except json.JSONDecodeError as e:
            error_msg = f"工作流配置文件格式错误: {e}"
            print(error_msg)
            logger.error(error_msg)
            raise
        except Exception as e:
            error_msg = f"加载工作流配置失败: {e}"
            print(error_msg)
            logger.exception(error_msg)
            raise

    def set_style(self, style: str) -> bool:
        """
        设置图像生成风格
        
        Args:
            style: 风格名称
            
        Returns:
            bool: 设置是否成功
        """
        if style in self.available_styles:
            self.style = style
            self.lora_name = self.available_styles[style]
            print(f"已切换风格: {style} (Lora: {self.lora_name})")
            logger.info(f"已切换风格: {style} (Lora: {self.lora_name})")
            return True
        else:
            error_msg = f"未知风格: {style}，可用风格: {', '.join(self.available_styles.keys())}"
            print(error_msg)
            logger.warning(error_msg)
            return False

    def get_available_styles(self) -> List[str]:
        """
        获取所有可用的风格选项
        
        Returns:
            List[str]: 可用风格名称列表
        """
        return list(self.available_styles.keys())

    def queue_prompt(self, prompt: Dict[str, Any]) -> Dict[str, Any]:
        """
        发送提示词到队列
        
        Args:
            prompt: 提示词数据
            
        Returns:
            Dict: 服务器响应数据
            
        Raises:
            urllib.error.URLError: 网络错误或服务器不可用时抛出
            json.JSONDecodeError: 响应解析错误时抛出
        """
        try:
            p = {"prompt": prompt, "client_id": self.client_id}
            data = json.dumps(p).encode('utf-8')
            req = urllib.request.Request(f"http://{self.server_address}/prompt", data=data)
            
            with urllib.request.urlopen(req, timeout=30) as response:
                result = json.loads(response.read())
                logger.debug(f"提示词已发送到队列，prompt_id: {result.get('prompt_id')}")
                return result
        except urllib.error.URLError as e:
            error_msg = f"无法连接到ComfyUI服务器: {e}"
            logger.error(error_msg)
            raise
        except json.JSONDecodeError as e:
            error_msg = f"解析服务器响应失败: {e}"
            logger.error(error_msg)
            raise
        except Exception as e:
            error_msg = f"发送提示词时发生错误: {e}"
            logger.exception(error_msg)
            raise

    def get_image(self, filename: str, subfolder: str, folder_type: str) -> bytes:
        """
        获取生成的图片
        
        Args:
            filename: 文件名
            subfolder: 子文件夹
            folder_type: 文件夹类型
            
        Returns:
            bytes: 图片数据
            
        Raises:
            urllib.error.URLError: 网络错误或服务器不可用时抛出
        """
        try:
            data = {"filename": filename, "subfolder": subfolder, "type": folder_type}
            url_values = urllib.parse.urlencode(data)
            url = f"http://{self.server_address}/view?{url_values}"
            
            logger.debug(f"获取图片: {url}")
            with urllib.request.urlopen(url, timeout=30) as response:
                return response.read()
        except urllib.error.URLError as e:
            error_msg = f"获取图片失败: {e}"
            logger.error(error_msg)
            raise
        except Exception as e:
            error_msg = f"获取图片时发生错误: {e}"
            logger.exception(error_msg)
            raise

    def get_history(self, prompt_id: str) -> Dict[str, Any]:
        """
        获取生成历史
        
        Args:
            prompt_id: 提示词ID
            
        Returns:
            Dict: 历史数据
            
        Raises:
            urllib.error.URLError: 网络错误或服务器不可用时抛出
            json.JSONDecodeError: 响应解析错误时抛出
        """
        try:
            url = f"http://{self.server_address}/history/{prompt_id}"
            logger.debug(f"获取历史: {url}")
            
            with urllib.request.urlopen(url, timeout=30) as response:
                return json.loads(response.read())
        except urllib.error.URLError as e:
            error_msg = f"获取历史失败: {e}"
            logger.error(error_msg)
            raise
        except json.JSONDecodeError as e:
            error_msg = f"解析历史数据失败: {e}"
            logger.error(error_msg)
            raise
        except Exception as e:
            error_msg = f"获取历史时发生错误: {e}"
            logger.exception(error_msg)
            raise

    def get_images(self, ws: websocket.WebSocket, workflow: Dict[str, Any], output_file: Union[str, Path]) -> bool:
        """
        获取生成的图片并保存
        
        Args:
            ws: WebSocket连接
            workflow: 工作流配置
            output_file: 输出文件路径
            
        Returns:
            bool: 获取是否成功
        """
        try:
            # 打印工作流配置（调试用）
            logger.debug("工作流配置:")
            for node_id, node in workflow.items():
                if node["class_type"] == "CLIPTextEncode":
                    logger.debug(f"节点 {node_id}: {node['inputs']['text']}")
            
            # 发送提示词到队列
            prompt_id = self.queue_prompt(workflow)['prompt_id']
            print(f"提示词已发送，等待生成...")
            logger.info(f"提示词已发送，等待生成，prompt_id: {prompt_id}")

            # 等待生成完成
            timeout_counter = 0
            max_timeout = 300  # 最大等待时间（秒）
            
            while timeout_counter < max_timeout:
                try:
                    out = ws.recv()
                    if isinstance(out, str):
                        message = json.loads(out)
                        if message['type'] == 'executing':
                            data = message['data']
                            if data['node'] is not None:
                                node_id = data['node']
                                logger.debug(f"正在执行节点: {node_id}")
                            if data['node'] is None and data['prompt_id'] == prompt_id:
                                logger.info(f"生成完成，prompt_id: {prompt_id}")
                                break
                    else:
                        logger.debug("接收到非字符串消息")
                except websocket.WebSocketTimeoutException:
                    timeout_counter += 1
                    if timeout_counter % 10 == 0:  # 每10秒记录一次
                        logger.warning(f"等待生成超时，已等待 {timeout_counter} 秒")
                    continue
                except Exception as e:
                    logger.error(f"等待生成时出错: {e}")
                    break

            if timeout_counter >= max_timeout:
                logger.error(f"生成超时，超过 {max_timeout} 秒")
                return False

            # 获取生成结果
            try:
                history = self.get_history(prompt_id)
                if prompt_id not in history:
                    logger.error(f"无法找到生成历史，prompt_id: {prompt_id}")
                    return False
                
                history_data = history[prompt_id]
                for node_id in history_data['outputs']:
                    node_output = history_data['outputs'][node_id]
                    if 'images' in node_output:
                        for image in node_output['images']:
                            try:
                                image_data = self.get_image(image['filename'], image['subfolder'], image['type'])
                                # 确保输出目录存在
                                output_path = Path(output_file)
                                output_path.parent.mkdir(parents=True, exist_ok=True)
                                
                                # 保存图片
                                with open(output_path, 'wb') as f:
                                    f.write(image_data)
                                print(f"图片已保存: {output_file}")
                                logger.info(f"图片已保存: {output_file}")
                                return True
                            except Exception as e:
                                logger.error(f"保存图片时出错: {e}")
                                continue
                
                logger.warning(f"没有找到生成的图片，prompt_id: {prompt_id}")
                return False
            except Exception as e:
                logger.error(f"获取生成结果时出错: {e}")
                return False
        except Exception as e:
            error_msg = f"生成图片时出错: {e}"
            print(error_msg)
            logger.exception(error_msg)
            return False

    def _prepare_workflow(self, prompt: str) -> Dict[str, Any]:
        """
        准备工作流配置
        
        Args:
            prompt: 图像提示词
            
        Returns:
            Dict: 更新后的工作流配置
        """
        # 创建工作流的深拷贝
        workflow = json.loads(json.dumps(self.workflow))
        
        # 设置随机种子和更新提示词
        seed = random.randint(1, 9999999999)
        positive_prompt = prompt + ", masterpiece, best quality"
        negative_prompt = "text, watermark, bad quality, worst quality, low quality, illustration, 3d render, cartoon, anime, manga"
        
        # 更新工作流配置
        try:
            # KSampler 节点
            if "3" in workflow:
                workflow["3"]["inputs"]["seed"] = seed
            
            # 正面提示词节点
            if "6" in workflow:
                workflow["6"]["inputs"]["text"] = positive_prompt
            
            # 负面提示词节点
            if "7" in workflow:
                workflow["7"]["inputs"]["text"] = negative_prompt
            
            # 更新Lora模型
            for node_id, node in workflow.items():
                if node["class_type"] == "LoraLoader":
                    node["inputs"]["lora_name"] = self.lora_name
                    logger.debug(f"设置Lora模型: {self.lora_name}")
            
            logger.info(f"工作流准备完成，随机种子: {seed}")
            logger.debug(f"正面提示词: {positive_prompt}")
            logger.debug(f"负面提示词: {negative_prompt}")
            
            return workflow
        except KeyError as e:
            error_msg = f"工作流节点配置错误: {e}"
            logger.error(error_msg)
            raise
        except Exception as e:
            error_msg = f"准备工作流时出错: {e}"
            logger.exception(error_msg)
            raise

    def _create_websocket_connection(self) -> websocket.WebSocket:
        """
        创建WebSocket连接
        
        Returns:
            websocket.WebSocket: WebSocket连接对象
            
        Raises:
            websocket.WebSocketException: WebSocket连接错误时抛出
        """
        try:
            ws = websocket.WebSocket()
            ws.connect(f"ws://{self.server_address}/ws?clientId={self.client_id}")
            ws.settimeout(1.0)  # 设置1秒超时，防止永久阻塞
            logger.info(f"WebSocket连接已建立: {self.server_address}")
            return ws
        except websocket.WebSocketException as e:
            error_msg = f"WebSocket连接失败: {e}"
            logger.error(error_msg)
            raise
        except Exception as e:
            error_msg = f"创建WebSocket连接时出错: {e}"
            logger.exception(error_msg)
            raise

    def generate_images(self, key_scenes_file: str) -> List[str]:
        """
        为所有场景生成图片
        
        Args:
            key_scenes_file: 场景信息文件路径
            
        Returns:
            List[str]: 成功生成的图片文件路径列表
        """
        generated_images = []
        
        # 读取场景信息
        try:
            with open(key_scenes_file, "r", encoding="utf-8") as f:
                scenes = json.load(f)
            
            logger.info(f"找到 {len(scenes)} 个场景需要生成图片")
            print(f"找到 {len(scenes)} 个场景需要生成图片")
        except FileNotFoundError:
            error_msg = f"找不到场景信息文件: {key_scenes_file}"
            print(error_msg)
            logger.error(error_msg)
            return generated_images
        except json.JSONDecodeError as e:
            error_msg = f"场景信息文件格式错误: {e}"
            print(error_msg)
            logger.error(error_msg)
            return generated_images
        except Exception as e:
            error_msg = f"读取场景信息文件时出错: {e}"
            print(error_msg)
            logger.exception(error_msg)
            return generated_images
        
        # 连接 WebSocket
        try:
            ws = self._create_websocket_connection()
        except Exception as e:
            error_msg = f"无法连接到ComfyUI服务器: {e}"
            print(error_msg)
            logger.error(error_msg)
            return generated_images
        
        try:
            for scene in scenes:
                scene_id = scene.get('scene_id', 'unknown')
                print(f"\n生成场景 {scene_id} 的图片...")
                logger.info(f"生成场景 {scene_id} 的图片...")
                
                # 检查提示词
                if 'prompt' not in scene:
                    logger.warning(f"场景 {scene_id} 缺少提示词，跳过")
                    continue
                
                if 'image_file' not in scene:
                    logger.warning(f"场景 {scene_id} 缺少图片文件名，跳过")
                    continue
                
                print(f"提示词: {scene['prompt']}")
                logger.info(f"场景 {scene_id} 提示词: {scene['prompt'][:100]}...")
                
                # 准备输出文件名
                output_file = self.output_dir / scene['image_file']
                if output_file.exists():
                    print(f"图片已存在: {output_file}")
                    logger.info(f"图片已存在，跳过生成: {output_file}")
                    generated_images.append(str(output_file))
                    continue
                
                # 准备工作流
                try:
                    workflow = self._prepare_workflow(scene["prompt"])
                    
                    # 生成图片
                    success = self.get_images(ws, workflow, output_file)
                    if success:
                        generated_images.append(str(output_file))
                    else:
                        logger.warning(f"场景 {scene_id} 图片生成失败")
                        print("图片生成失败")
                except Exception as e:
                    error_msg = f"处理场景 {scene_id} 时出错: {e}"
                    print(error_msg)
                    logger.exception(error_msg)
                    continue
                
                # 等待一小段时间再生成下一张
                time.sleep(1)
        
        except Exception as e:
            error_msg = f"生成图片过程中出错: {e}"
            print(error_msg)
            logger.exception(error_msg)
        finally:
            try:
                ws.close()
                logger.info("WebSocket连接已关闭")
            except:
                pass
            
            return generated_images

    def generate_image(self, prompt: str, output_filename: str) -> Optional[str]:
        """
        生成单个图像
        
        Args:
            prompt: 图像提示词
            output_filename: 输出文件名
            
        Returns:
            Optional[str]: 生成的图像文件路径，如果失败则返回None
        """
        # 准备输出文件路径
        output_file = self.output_dir / output_filename
        if output_file.exists():
            print(f"图片已存在: {output_file}")
            logger.info(f"图片已存在，跳过生成: {output_file}")
            return str(output_file)
        
        logger.info(f"开始生成图片: {output_filename}")
        logger.info(f"提示词: {prompt[:100]}...")
        
        # 准备工作流
        try:
            workflow = self._prepare_workflow(prompt)
            
            # 打印基本信息
            print(f"设置随机种子: {workflow['3']['inputs']['seed']}")
            print(f"设置正面提示词: {workflow['6']['inputs']['text']}")
            print(f"设置负面提示词: {workflow['7']['inputs']['text']}")
            print(f"设置Lora模型: {self.lora_name}")
            
            # 连接 WebSocket
            try:
                ws = self._create_websocket_connection()
            except Exception as e:
                logger.error(f"无法连接到ComfyUI服务器: {e}")
                return None
            
            try:
                success = self.get_images(ws, workflow, output_file)
                if success:
                    return str(output_file)
                else:
                    logger.warning(f"图片生成失败: {output_filename}")
                    print("图片生成失败")
                    return None
            finally:
                ws.close()
                logger.debug("WebSocket连接已关闭")
        except Exception as e:
            error_msg = f"生成图片时出错: {e}"
            print(error_msg)
            logger.exception(error_msg)
            return None

if __name__ == "__main__":
    # 设置日志配置
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler("output/image_generator.log", mode='a'),
            logging.StreamHandler()
        ]
    )
    
    try:
        generator = ComfyUIGenerator()
        result = generator.generate_images("output/key_scenes.json")
        print(f"成功生成 {len(result)} 个图像")
    except Exception as e:
        print(f"图像生成过程中出错: {e}")
        traceback.print_exc() 