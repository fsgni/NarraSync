import json
import requests
import os
from pathlib import Path

class PronunciationDictionary:
    def __init__(self, host="127.0.0.1", port="50021", dict_file="dictionaries/voicevox_dict.json"):
        """初始化发音词典管理器"""
        self.base_url = f"http://{host}:{port}"
        self.dict_file = dict_file
        
        # 确保字典文件目录存在
        Path(os.path.dirname(dict_file)).mkdir(parents=True, exist_ok=True)
        
        # 加载本地词典文件（如果存在）
        self.local_dict = self.load_local_dictionary()
    
    def load_local_dictionary(self):
        """从本地文件加载词典"""
        try:
            if os.path.exists(self.dict_file):
                with open(self.dict_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            return {}
        except Exception as e:
            print(f"加载本地词典时出错: {e}")
            return {}
    
    def save_local_dictionary(self, dictionary):
        """保存词典到本地文件"""
        try:
            with open(self.dict_file, "w", encoding="utf-8") as f:
                json.dump(dictionary, f, ensure_ascii=False, indent=2)
            print(f"词典已保存到: {self.dict_file}")
        except Exception as e:
            print(f"保存词典时出错: {e}")
    
    def get_voicevox_dictionary(self):
        """获取VOICEVOX当前的用户词典"""
        try:
            response = requests.get(f"{self.base_url}/user_dict")
            if response.status_code == 200:
                # 直接解析响应文本
                return json.loads(response.text)
            else:
                print(f"获取VOICEVOX词典失败: {response.text}")
                return {}
        except Exception as e:
            print(f"获取VOICEVOX词典时出错: {e}")
            import traceback
            traceback.print_exc()  # 打印详细错误信息
            return {}
    
    def add_word(self, surface, pronunciation, accent_type=0):
        """添加单词到VOICEVOX词典"""
        try:
            # 使用查询参数而不是JSON请求体
            params = {
                "surface": surface,
                "pronunciation": pronunciation,
                "accent_type": accent_type
            }
            
            response = requests.post(
                f"{self.base_url}/user_dict_word",
                params=params  # 使用params而不是json
            )
            
            if response.status_code == 200:
                # 打印响应内容，帮助调试
                print(f"响应内容: {response.text}")
                
                # 尝试解析响应
                try:
                    response_data = response.json()
                    if isinstance(response_data, dict) and "uuid" in response_data:
                        word_uuid = response_data["uuid"]
                    else:
                        # 如果响应不是预期的格式，使用响应文本作为UUID
                        word_uuid = response.text.strip('"')  # 去除可能的引号
                except:
                    # 如果无法解析为JSON，直接使用响应文本
                    word_uuid = response.text.strip('"')
                
                print(f"已添加词典条目: {surface} -> {pronunciation} (UUID: {word_uuid})")
                
                # 更新本地词典
                self.local_dict[surface] = {
                    "pronunciation": pronunciation,
                    "accent_type": accent_type,
                    "uuid": word_uuid
                }
                self.save_local_dictionary(self.local_dict)
                
                return word_uuid
            else:
                print(f"添加词典条目失败: {surface}, 错误: {response.text}")
                return None
        except Exception as e:
            print(f"添加词典条目时出错: {e}")
            import traceback
            traceback.print_exc()  # 打印详细错误信息
            return None
    
    def remove_word(self, surface):
        """从VOICEVOX词典中删除单词"""
        if surface in self.local_dict and "uuid" in self.local_dict[surface]:
            word_uuid = self.local_dict[surface]["uuid"]
            try:
                response = requests.delete(f"{self.base_url}/user_dict_word/{word_uuid}")
                if response.status_code == 204:
                    print(f"已删除词典条目: {surface}")
                    # 从本地词典中删除
                    del self.local_dict[surface]
                    self.save_local_dictionary(self.local_dict)
                    return True
                else:
                    print(f"删除词典条目失败: {surface}, 错误: {response.text}")
                    return False
            except Exception as e:
                print(f"删除词典条目时出错: {e}")
                return False
        else:
            print(f"词典中不存在条目: {surface}")
            return False
    
    def sync_with_voicevox(self):
        """同步本地词典和VOICEVOX词典"""
        # 获取VOICEVOX当前词典
        voicevox_dict = self.get_voicevox_dictionary()
        
        # 创建UUID到单词的映射
        uuid_to_word = {}
        for word_uuid, word_info in voicevox_dict.items():
            surface = word_info["surface"]
            uuid_to_word[word_uuid] = surface
            
            # 更新本地词典
            if surface not in self.local_dict:
                self.local_dict[surface] = {
                    "pronunciation": word_info["pronunciation"],
                    "accent_type": word_info["accent_type"],
                    "uuid": word_uuid
                }
        
        # 检查本地词典中是否有VOICEVOX中不存在的条目
        for surface, word_info in list(self.local_dict.items()):
            if "uuid" in word_info and word_info["uuid"] not in uuid_to_word:
                # 重新添加到VOICEVOX
                print(f"重新添加词典条目: {surface}")
                self.add_word(
                    surface,
                    word_info["pronunciation"],
                    word_info["accent_type"]
                )
        
        # 保存更新后的本地词典
        self.save_local_dictionary(self.local_dict)
        print("词典同步完成")
    
    def import_from_file(self, file_path):
        """从JSON文件导入词典"""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                import_dict = json.load(f)
            
            success_count = 0
            for surface, word_info in import_dict.items():
                if isinstance(word_info, dict) and "pronunciation" in word_info:
                    # 新格式: {"word": {"pronunciation": "...", "accent_type": 0}}
                    pronunciation = word_info["pronunciation"]
                    accent_type = word_info.get("accent_type", 0)
                else:
                    # 旧格式: {"word": "pronunciation"}
                    pronunciation = word_info
                    accent_type = 0
                
                if self.add_word(surface, pronunciation, accent_type):
                    success_count += 1
            
            print(f"成功导入 {success_count}/{len(import_dict)} 个词典条目")
            return success_count
        except Exception as e:
            print(f"导入词典时出错: {e}")
            return 0
    
    def export_to_file(self, file_path):
        """导出词典到JSON文件"""
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(self.local_dict, f, ensure_ascii=False, indent=2)
            print(f"词典已导出到: {file_path}")
            return True
        except Exception as e:
            print(f"导出词典时出错: {e}")
            return False
    
    def add_common_corrections(self):
        """添加常见的发音纠正"""
        corrections = {
            # 人名
           
            
            # 地名
            
            
            # 常见错误发音
            
            
            # 专有名词
       
        }
        
        success_count = 0
        for surface, pronunciation in corrections.items():
            if self.add_word(surface, pronunciation):
                success_count += 1
        
        print(f"成功添加 {success_count}/{len(corrections)} 个常见发音纠正")
        return success_count

# 使用示例
if __name__ == "__main__":
    dict_manager = PronunciationDictionary()
    
    # 同步词典
    dict_manager.sync_with_voicevox()
    
    # 添加常见纠正
    dict_manager.add_common_corrections()
    
    # 添加自定义词条
    #dict_manager.add_word("専有名詞", "センユウメイシ")
    #dict_manager.add_word("人工知能", "ジンコウチノウ")
    
    # 导出词典
    dict_manager.export_to_file("dictionaries/custom_dict.json") 