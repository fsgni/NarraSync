import os
import json
import shutil
from pathlib import Path
import traceback

class SceneManager:
    """场景管理类，负责处理场景的加载、更新、刷新等操作"""
    
    def __init__(self):
        """初始化场景管理器"""
        self.key_scenes_file = "output/key_scenes.json"
        self.images_dir = "output/images"
        self.modified_images_file = "output/modified_images.txt"
    
    def load_scenes(self):
        """加载所有场景信息"""
        if not os.path.exists(self.key_scenes_file):
            return []
        
        try:
            with open(self.key_scenes_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"读取场景信息出错: {e}")
            return []
    
    def save_scenes(self, scenes):
        """保存场景信息"""
        try:
            with open(self.key_scenes_file, "w", encoding="utf-8") as f:
                json.dump(scenes, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"保存场景信息出错: {e}")
            return False
    
    def get_scene_count(self):
        """获取场景总数"""
        scenes = self.load_scenes()
        return len(scenes)
    
    def get_scene(self, scene_idx):
        """获取指定索引的场景"""
        scenes = self.load_scenes()
        if 0 <= scene_idx < len(scenes):
            return scenes[scene_idx]
        return None
    
    def update_scene_prompt(self, scene_idx, prompt):
        """更新场景提示词"""
        scenes = self.load_scenes()
        if 0 <= scene_idx < len(scenes):
            scenes[scene_idx]["prompt"] = prompt
            return self.save_scenes(scenes)
        return False
    
    def get_scene_image_path(self, scene_idx):
        """获取场景图片路径"""
        scene = self.get_scene(scene_idx)
        if scene and "image_file" in scene:
            image_path = f"{self.images_dir}/{scene['image_file']}"
            if os.path.exists(image_path):
                return image_path
        return None
    
    def upload_scene_image(self, scene_index, image_path):
        """上传自定义图片替换场景图片
        
        Args:
            scene_index: 场景索引（从1开始）
            image_path: 上传的图片路径
            
        Returns:
            str: 状态信息
        """
        try:
            if not os.path.exists(self.key_scenes_file):
                return "找不到场景信息文件，请先生成视频"
            
            scenes = self.load_scenes()
            
            # 检查场景索引是否有效
            scene_idx = int(scene_index) - 1
            if scene_idx < 0 or scene_idx >= len(scenes):
                return f"无效的场景索引: {scene_index}，场景总数: {len(scenes)}"
            
            # 检查上传的图片是否存在
            if not image_path or not os.path.exists(image_path):
                return "上传的图片不存在"
            
            # 获取场景图片文件名
            scene = scenes[scene_idx]
            image_file = scene.get("image_file", "")
            if not image_file:
                image_file = f"scene_{scene_index}.png"
                scene["image_file"] = image_file
            
            # 构造目标图片路径
            target_path = f"{self.images_dir}/{image_file}"
            
            # 复制上传的图片到目标路径
            shutil.copy2(image_path, target_path)
            
            # 将此图片标记为已手动修改
            self._mark_image_as_modified(image_file)
            
            # 保存更新后的场景信息
            self.save_scenes(scenes)
            
            return f"场景 {scene_index} 的图片已替换为上传的图片"
        except Exception as e:
            print(f"上传图片时出错: {e}")
            return f"上传图片失败: {e}"
    
    def _mark_image_as_modified(self, image_file):
        """将图片标记为已手动修改"""
        modified_images = []
        if os.path.exists(self.modified_images_file):
            try:
                with open(self.modified_images_file, "r", encoding="utf-8") as f:
                    modified_images = [line.strip() for line in f.readlines()]
            except:
                pass
        
        if image_file not in modified_images:
            modified_images.append(image_file)
            
            with open(self.modified_images_file, "w", encoding="utf-8") as f:
                f.write("\n".join(modified_images))
    
    def is_image_modified(self, image_file):
        """检查图片是否已被手动修改"""
        if not os.path.exists(self.modified_images_file):
            print(f"图片修改标记文件不存在: {self.modified_images_file}")
            return False
            
        try:
            with open(self.modified_images_file, "r", encoding="utf-8") as f:
                modified_images = [line.strip() for line in f.readlines()]
                is_modified = image_file in modified_images
                if is_modified:
                    print(f"图片 {image_file} 已被手动修改，将不会重新生成")
                return is_modified
        except Exception as e:
            print(f"读取修改标记文件出错: {e}")
            return False
            
    def clear_modified_images(self):
        """清除所有已修改图片的标记"""
        if os.path.exists(self.modified_images_file):
            try:
                os.remove(self.modified_images_file)
                print(f"已清除所有图片修改标记，下次将重新生成所有图片")
                return True
            except Exception as e:
                print(f"清除图片修改标记文件失败: {e}")
                return False
        else:
            print("图片修改标记文件不存在，无需清除")
            return True
    
    def load_scene_details(self, scene_idx, video_path):
        """加载选中场景的详细信息
        
        Args:
            scene_idx: 场景索引（从1开始）
            video_path: 视频路径
            
        Returns:
            tuple: (内容, 提示词, 图片路径, 场景索引, 场景信息)
        """
        if not video_path:
            return {
                "content": "请先生成视频",
                "prompt": "",
                "image_path": None,
                "scene_idx": 0,
                "scene_count_label": "场景: 0/0"
            }
        
        if not os.path.exists(self.key_scenes_file):
            return {
                "content": "找不到场景信息文件",
                "prompt": "",
                "image_path": None,
                "scene_idx": 0,
                "scene_count_label": "场景: 0/0"
            }
        
        try:
            scenes = self.load_scenes()
                
            scene_count = len(scenes)
            if scene_count == 0:
                return {
                    "content": "没有找到场景",
                    "prompt": "",
                    "image_path": None,
                    "scene_idx": 0,
                    "scene_count_label": "场景: 0/0"
                }
            
            # 确保场景索引在有效范围内
            # 确保scene_idx是整数
            if isinstance(scene_idx, list) and len(scene_idx) > 0:
                scene_idx = scene_idx[0]  # 如果是列表，取第一个元素
            
            try:
                scene_idx = int(float(scene_idx))  # 先转为float再转为int，处理可能的小数情况
            except (TypeError, ValueError):
                scene_idx = 1  # 如果转换失败，默认为第一个场景
            
            scene_idx = max(1, min(scene_idx, scene_count))
            scene_idx_zero_based = scene_idx - 1  # 转换为0基索引
            
            scene = scenes[scene_idx_zero_based]
            # 安全地获取场景属性，提供默认值
            content = scene.get("content", f"场景 {scene_idx} 无内容")
            
            # 如果sentences字段存在，优先使用sentences中的台词
            sentences = scene.get("sentences", [])
            if sentences and isinstance(sentences, list) and len(sentences) > 0:
                # 合并所有句子作为内容
                content = "\n".join(sentences)
            
            prompt = scene.get("prompt", "")
            image_file = scene.get("image_file", "")
            
            # 确保images目录存在
            os.makedirs(self.images_dir, exist_ok=True)
            
            # 构建图片路径
            image_path = f"{self.images_dir}/{image_file}" if image_file else None
            image_exists = image_path and os.path.exists(image_path)
            
            # 创建用于显示的场景内容，确保台词清晰可见
            display_content = f"### 场景 {scene_idx}\n\n**台词/内容：**\n{content}\n\n"
            
            # 如果图片不存在，添加提示信息
            if image_file and not image_exists:
                display_content += f"\n\n**注意：图片不存在或已被删除。** 你可以上传新图片或重新生成图片。"
                print(f"警告: 场景 {scene_idx} 的图片不存在: {image_path}")
            
            return {
                "content": display_content,
                "prompt": prompt,
                "image_path": image_path if image_exists else None,
                "scene_idx": scene_idx,
                "scene_count_label": f"场景: {scene_idx}/{scene_count}"
            }
        except Exception as e:
            print(f"加载场景详情出错: {str(e)}")
            print(traceback.format_exc())
            return {
                "content": f"加载场景详情出错: {str(e)}",
                "prompt": "",
                "image_path": None,
                "scene_idx": 0,
                "scene_count_label": "场景: 0/0"
            }
    
    def get_gallery_images(self):
        """获取所有场景的缩略图列表"""
        scenes = self.load_scenes()
        gallery_images = []
        
        for i, scene in enumerate(scenes):
            scene_id = i + 1
            image_file = scene.get("image_file", "")
            
            # 构建图片路径
            image_path = f"{self.images_dir}/{image_file}" if image_file else ""
            if os.path.exists(image_path):
                # 添加图片和标签
                gallery_images.append((image_path, f"场景 {scene_id}"))
            else:
                # 记录缺失图片
                print(f"场景 {scene_id} 没有图片")
        
        return gallery_images
    
    def refresh_scene_list(self, video_path):
        """刷新场景列表，返回UI更新信息
        
        Args:
            video_path: 视频路径
            
        Returns:
            dict: 包含UI组件更新信息
        """
        if not video_path:
            return {
                "slider": {"minimum": 1, "maximum": 1, "value": 1, "visible": False},
                "count_label": {"value": "场景: 0/0", "visible": False},
                "gallery": {"value": [], "visible": False},
                "editor": {"visible": False},
                "recompose_button": {"visible": False}
            }
        
        if not os.path.exists(self.key_scenes_file):
            return {
                "slider": {"minimum": 1, "maximum": 1, "value": 1, "visible": False},
                "count_label": {"value": "找不到场景信息文件", "visible": True},
                "gallery": {"value": [], "visible": False},
                "editor": {"visible": False},
                "recompose_button": {"visible": False}
            }
        
        try:
            scenes = self.load_scenes()
            
            # 更新滑块范围
            scene_count = len(scenes)
            if scene_count == 0:
                return {
                    "slider": {"minimum": 1, "maximum": 1, "value": 1, "visible": False},
                    "count_label": {"value": "没有找到场景", "visible": True},
                    "gallery": {"value": [], "visible": False},
                    "editor": {"visible": False},
                    "recompose_button": {"visible": False}
                }
            
            # 获取所有场景的缩略图
            gallery_images = self.get_gallery_images()
            
            return {
                "slider": {"minimum": 1, "maximum": scene_count, "value": 1, "visible": True},
                "count_label": {"value": f"场景: 1/{scene_count}", "visible": True},
                "gallery": {"value": gallery_images, "visible": True},
                "editor": {"visible": True},
                "recompose_button": {"visible": True}
            }
        except Exception as e:
            print(f"读取场景列表出错: {str(e)}")
            print(traceback.format_exc())
            return {
                "slider": {"minimum": 1, "maximum": 1, "value": 1, "visible": False},
                "count_label": {"value": f"读取场景信息出错: {str(e)}", "visible": True},
                "gallery": {"value": [], "visible": False},
                "editor": {"visible": False},
                "recompose_button": {"visible": False}
            }
            
    def generate_scene_thumbnails(self):
        """生成场景缩略图HTML"""
        scenes = self.load_scenes()
        if not scenes:
            return ""
            
        thumbnails_html = """
        <style>
            .scene-thumbnails {
                display: flex;
                flex-wrap: wrap;
                gap: 10px;
                margin-top: 10px;
            }
            .scene-thumbnail {
                position: relative;
                cursor: pointer;
                transition: transform 0.2s;
                border: 2px solid transparent;
            }
            .scene-thumbnail:hover {
                transform: scale(1.05);
                border-color: #2196F3;
            }
            .scene-thumbnail.selected {
                border-color: #FF5722;
            }
            .scene-thumbnail img {
                width: 120px;
                height: 120px;
                object-fit: cover;
                border-radius: 4px;
            }
            .scene-thumbnail .scene-label {
                position: absolute;
                bottom: 0;
                left: 0;
                right: 0;
                background: rgba(0,0,0,0.7);
                color: white;
                padding: 4px;
                font-size: 12px;
                text-align: center;
                border-bottom-left-radius: 4px;
                border-bottom-right-radius: 4px;
            }
        </style>
        <div class="scene-thumbnails">
        """
        
        for i, scene in enumerate(scenes):
            scene_id = i + 1
            image_file = scene.get("image_file", "")
            
            # 构建图片路径
            image_path = f"{self.images_dir}/{image_file}" if image_file else ""
            if os.path.exists(image_path):
                thumbnails_html += f"""
                <div class="scene-thumbnail" onclick="selectScene({scene_id})" id="scene-thumb-{scene_id}">
                    <img src="file={image_path}" alt="场景 {scene_id}" />
                    <div class="scene-label">场景 {scene_id}</div>
                </div>
                """
            else:
                # 使用占位图
                thumbnails_html += f"""
                <div class="scene-thumbnail" onclick="selectScene({scene_id})" id="scene-thumb-{scene_id}">
                    <div style="width:120px;height:120px;background:#eee;display:flex;align-items:center;justify-content:center;border-radius:4px;">
                        <span>无图片</span>
                    </div>
                    <div class="scene-label">场景 {scene_id}</div>
                </div>
                """
        
        # 添加JavaScript函数
        thumbnails_html += """
        </div>
        <script>
            function selectScene(sceneId) {
                // 移除所有选中状态
                document.querySelectorAll('.scene-thumbnail').forEach(el => {
                    el.classList.remove('selected');
                });
                
                // 设置当前选中状态
                document.getElementById('scene-thumb-' + sceneId).classList.add('selected');
                
                // 设置滑块值 (通过模拟更改事件)
                const slider = document.getElementById('scene_slider');
                if (slider) {
                    slider.value = sceneId;
                    // 触发change事件
                    const event = new Event('change');
                    slider.dispatchEvent(event);
                }
            }
        </script>
        """
        
        return thumbnails_html 