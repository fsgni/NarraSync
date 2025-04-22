import MeCab
from typing import List, Dict, Tuple
import re
import os
import json

class TextProcessor:
    def __init__(self):
        """初始化 MeCab"""
        self.mecab = MeCab.Tagger()
        self.max_chars_per_line = 35  # 增加字符限制
    
    def _split_long_sentence(self, sentence):
        """使用 MeCab 进行更智能的长句分割"""
        # 如果是引号内的对话，使用特殊处理
        if sentence.startswith('「') or sentence.startswith('『'):
            return self._split_dialog(sentence)
            
        # 使用 MeCab 进行详细分析
        nodes = []
        node = self.mecab.parseToNode(sentence)
        
        # 定义标点符号集合
        punctuation_marks = {
            "。", "！", "？", "、", "，", "」", "』", ")", "）", "}", "】", "』", "〕",
            ".", "!", "?", ",", ")", "}", "]"
        }
        
        # 收集所有节点
        while node:
            if node.surface:
                nodes.append({
                    'surface': node.surface,
                    'pos': node.feature.split(',')[0],
                    'feature': node.feature
                })
            node = node.next
        
        # 预处理：找出所有可能的分割点
        split_points = []
        current_length = 0
        for i, node in enumerate(nodes):
            surface = node['surface']
            current_length += len(surface)
            
            # 如果不是标点符号，且在合适的位置
            if (surface not in punctuation_marks and 
                current_length >= self.max_chars_per_line * 0.7 and
                current_length <= self.max_chars_per_line):
                
                # 检查是否是合适的分割词
                if (node['pos'] == "助詞" and surface in ["は", "が", "を", "に", "へ", "で", "から"] or
                    node['pos'] == "接続助詞" and surface in ["て", "で"]):
                    
                    # 检查后面是否紧跟标点符号
                    next_node = nodes[i + 1] if i + 1 < len(nodes) else None
                    if not next_node or next_node['surface'] not in punctuation_marks:
                        split_points.append(i)
        
        # 如果没有找到合适的分割点，返回原句
        if not split_points and len(sentence) <= self.max_chars_per_line * 1.3:
            return [sentence]
        
        # 根据分割点分句
        parts = []
        current = []
        current_length = 0
        last_split = 0
        
        for i, node in enumerate(nodes):
            surface = node['surface']
            next_length = current_length + len(surface)
            
            # 如果当前是标点符号，总是加到当前行
            if surface in punctuation_marks:
                if current:
                    current.append(surface)
                    current_length += len(surface)
                elif parts:
                    parts[-1] += surface
                continue
            
            # 检查是否需要在这里分行
            if i in split_points:
                current.append(surface)
                parts.append(''.join(current))
                current = []
                current_length = 0
                last_split = i
            else:
                # 如果距离上次分割太远，强制分割
                if current_length > self.max_chars_per_line and i > last_split:
                    if current:
                        parts.append(''.join(current))
                        current = [surface]
                        current_length = len(surface)
                        last_split = i
                else:
                    current.append(surface)
                    current_length += len(surface)
        
        # 处理剩余部分
        if current:
            last_part = ''.join(current)
            if parts and len(parts[-1] + last_part) <= self.max_chars_per_line:
                parts[-1] += last_part
            else:
                parts.append(last_part)
        
        return parts or [sentence]

    def _split_dialog(self, text):
        """特别处理对话文本"""
        # 找到对话的开始和结束
        dialog_end = text.find('」') if '」' in text else text.find('』')
        if dialog_end == -1:
            return [text]
            
        dialog = text[:dialog_end+1]
        rest = text[dialog_end+1:].strip()
        
        result = []
        # 只有在对话特别长时才分割（增加容忍度）
        if len(dialog) <= self.max_chars_per_line * 1.5:  # 增加到1.5倍
            result.append(dialog)
        else:
            # 保留开始的引号
            quote = dialog[0]
            inner_text = dialog[1:-1]
            
            # 在标点符号处分割
            parts = []
            current = quote
            for char in inner_text:
                current += char
                # 只在句子真的很长时才分割
                if (char in ["、", "，", "！", "？", "。"] and 
                    len(current) >= self.max_chars_per_line * 1.2):
                    parts.append(current)
                    current = ""
            
            # 处理最后一部分
            if current:
                current += "」"
                parts.append(current)
            
            result.extend(parts)
        
        # 处理对话后的内容
        if rest:
            # 如果剩余部分不是很长，就和对话放在一起
            if len(rest) <= self.max_chars_per_line * 0.3:  # 添加这个判断
                result[-1] += rest
            else:
                if len(rest) > self.max_chars_per_line:
                    result.extend(self._split_long_sentence(rest))
                else:
                    result.append(rest)
        
        return result

    def _fix_quote_position(self, text):
        """修复引号位置，确保在句子末尾"""
        # 处理开头的引号
        if text.startswith('」'):
            text = text[1:] + '」'
        if text.startswith('』'):
            text = text[1:] + '』'
        
        return text

    def process_japanese_text(self, text: str, preserve_line_breaks: bool = False) -> List[str]:
        """
        处理文本，返回句子列表
        
        Args:
            text: 要处理的文本
            preserve_line_breaks: 是否保留原始换行符
            
        Returns:
            处理后的句子列表
        """
        # 提取文本中的场景标题
        text, scene_titles = self.extract_scene_titles(text)
        
        # 保存场景标题到临时文件
        if scene_titles:
            self.save_scene_titles(scene_titles)
        
        if not text:
            return []
        
        if preserve_line_breaks:
            # 保留原始换行，简单按行分割
            sentences = []
            for line in text.splitlines():
                line = line.strip()
                if line:
                    sentences.append(line)
            return sentences
        
        # 预处理：替换常见断句符号，确保它们前后有空格
        text = re.sub(r'([。！？；;：:!?.])', r'\1 ', text)
        text = re.sub(r'([\n\r])', r' ', text)
            
        # 分割成初步的句子
        raw_sentences = re.split(r'[。！？；;：:!?.\n\r]+\s*', text)
        
        # 合并过短的句子（少于10个字符）
        sentences = []
        current = ""
        
        for s in raw_sentences:
            s = s.strip()
            if not s:
                continue
                
            if len(current) == 0:
                current = s
            elif len(s) < 10:  # 如果句子太短
                current += "，" + s
            else:
                if current:
                    sentences.append(current)
                current = s
        
        if current:
                sentences.append(current)
                
        return sentences
    
    def extract_scene_titles(self, text: str) -> Tuple[str, List[Dict]]:
        """
        从文本中提取场景标题标记
        
        Args:
            text: 原始文本
            
        Returns:
            Tuple[str, List[Dict]]: 处理后的文本（删除标记）和提取的标题列表
        """
        # 匹配标题标记，格式为：[标题:标题文本]
        title_pattern = r'\[标题:(.*?)\]'
        titles = []
        title_positions = []
        
        # 查找所有标题标记
        for match in re.finditer(title_pattern, text):
            title_text = match.group(1).strip()
            position = match.start()
            titles.append({
                "text": title_text,
                "position": position
            })
            title_positions.append((match.start(), match.end()))
        
        # 从原文本中删除标题标记
        # 从后向前删除，以保持索引准确
        processed_text = text
        for start, end in sorted(title_positions, reverse=True):
            processed_text = processed_text[:start] + processed_text[end:]
        
        # 返回处理后的文本和标题列表
        return processed_text, titles
    
    def save_scene_titles(self, titles: List[Dict]):
        """
        保存场景标题到临时文件，供后续处理使用
        
        Args:
            titles: 标题列表，每个标题包含text和position
        """
        # 确保输出目录存在
        os.makedirs("output", exist_ok=True)
        
        # 保存到JSON文件
        with open("output/scene_titles.json", "w", encoding="utf-8") as f:
            json.dump(titles, f, ensure_ascii=False, indent=2)
        
        print(f"已保存{len(titles)}个场景标题到output/scene_titles.json")

    def process_text_with_preserved_line_breaks(self, text):
        """处理文本并保留原始的换行符
        
        每个换行符都被视为一个单独的句子分隔符，保留用户控制的换行。
        """
        sentences = []
        
        # 按换行符分割文本
        lines = text.split('\n')
        
        for line in lines:
            line = line.strip()
            if not line:  # 跳过空行
                continue
                
            # 如果行长度适中，直接添加
            if len(line) <= self.max_chars_per_line:
                sentences.append(line)
            else:
                # 对过长的行进行智能分割
                parts = self._split_long_sentence(line)
                sentences.extend(parts)
                
        return sentences

    def process_text_with_speakers(self, text_info: List[Dict]) -> List[Dict]:
        """处理带说话者信息的文本"""
        processed_sentences = []
        
        for sentence in text_info:
            text = sentence["text"]
            speaker = sentence["speaker"]
            
            # 如果文本太长，进行分割
            if len(text) > self.max_chars_per_line:
                parts = self._split_long_sentence(text)
                for part in parts:
                    processed_sentences.append({
                        "text": part,
                        "speaker": speaker,
                        "type": sentence["type"]
                    })
            else:
                processed_sentences.append(sentence)
        
        return processed_sentences 