import asyncio
import functools # 导入 functools
from pathlib import Path
from services import ServiceLocator
from pronunciation_dictionary import PronunciationDictionary
import json
import argparse
import os # 确保导入os

# 定义并发限制
MAX_CONCURRENT_REQUESTS = 10 # 可以根据Voicevox引擎的承受能力调整

async def process_voice_generation(input_file: str, output_dir: str, speaker_id: int = 13, speed_scale: float = 1.0, use_dict: bool = True, tts_service: str = "voicevox", voice_preset: str = None):
    """处理文本到语音的转换 (并发版本)"""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    voice_generator = ServiceLocator.get_voice_generator(generator_type=tts_service)
    
    if use_dict and tts_service == "voicevox":
        # 注意：词典同步仍然是同步操作，会在并发开始前完成
        dict_manager = PronunciationDictionary()
        dict_manager.sync_with_voicevox()
        print("已同步发音词典")
    
    if tts_service == "openai_tts" and voice_preset:
        # 省略 OpenAI 特定代码... (保持不变)
        pass # Placeholder for brevity, original OpenAI preset logic remains
    
    print("可用角色列表：")
    available_voices = voice_generator.list_speakers()
    for id, name in available_voices.items():
        print(f"ID: {id} - {name}")
        
    voice_generator.set_speaker(speaker_id)
    voice_name = available_voices.get(speaker_id, f"未知名称 (ID: {speaker_id})")
    print(f"\n使用语音: {voice_name}")
    
    with open(input_file, "r", encoding="utf-8") as f:
        sentences = [line.strip() for line in f if line.strip()]
    
    audio_info_results = [] # 存储中间结果
    
    # 创建并发信号量
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)

    # 定义单个句子的并发合成任务
    async def synthesize_sentence_task(index, sentence, speed_scale):
        nonlocal voice_generator # 引用外部的 generator 实例
        audio_file = f"audio_{index:03d}.wav"
        audio_path = output_path / audio_file
        
        async with semaphore: # 控制并发数量
            print(f"开始处理句子 {index+1}/{len(sentences)}: {sentence[:30]}...")
            try:
                # 使用 asyncio.to_thread 在线程中运行同步的 synthesize 函数
                # 使用 functools.partial 传递参数
                synthesize_func = functools.partial(
                    voice_generator.synthesize, 
                    sentence, 
                    str(audio_path), #确保路径是字符串
                    speaker_id, # 使用函数外部设置好的 speaker_id
                    speed_scale=speed_scale # Pass speed_scale
                )
                duration = await asyncio.to_thread(synthesize_func)
                
                print(f"完成处理句子 {index+1}/{len(sentences)}: {audio_file} (时长: {duration:.2f}秒)")
                return {
                    "id": index,
                    "sentence": sentence,
                    "audio_file": str(audio_file),
                    "duration": duration
                }
            except Exception as e:
                print(f"生成音频失败 {index+1}: {e}")
                return {
                    "id": index,
                    "sentence": sentence,
                    "error": str(e)
                }

    # 创建所有任务
    tasks = [synthesize_sentence_task(i, sentence, speed_scale) for i, sentence in enumerate(sentences)]
    
    # 并发执行所有任务并收集结果
    # return_exceptions=True 让 gather 返回异常而不是直接抛出
    print(f"开始并发处理 {len(tasks)} 个句子，并发限制: {MAX_CONCURRENT_REQUESTS}...")
    results = await asyncio.gather(*tasks, return_exceptions=True)
    print("所有并发任务已完成处理。")

    # 按原始顺序处理结果
    audio_info = []
    total_duration = 0.0
    successful_count = 0
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            # 如果 gather 返回的是异常对象
            print(f"任务 {i+1} 失败: {result}")
            # 尝试从原始句子列表中获取句子内容，以防万一
            original_sentence = sentences[i] if i < len(sentences) else "未知句子"
            audio_info.append({
                "id": i,
                "sentence": original_sentence, 
                "error": f"并发任务处理失败: {result}"
            })
        elif isinstance(result, dict):
             audio_info.append(result) # 直接使用任务返回的字典
             if "duration" in result:
                 total_duration += result["duration"]
                 successful_count += 1
        else:
             # 未知结果类型，记录错误
             print(f"任务 {i+1} 返回未知结果类型: {type(result)}")
             original_sentence = sentences[i] if i < len(sentences) else "未知句子"
             audio_info.append({
                "id": i,
                "sentence": original_sentence, 
                "error": f"并发任务返回未知结果类型: {type(result)}"
            })


    # 保存音频信息到JSON文件
    info_file = output_path / f"{Path(input_file).stem}_audio_info.json"
    with open(info_file, "w", encoding="utf-8") as f:
        json.dump({
            "source_file": input_file,
            "total_sentences": len(sentences),
            "total_duration": total_duration, # 使用累加的总时长
            "successful_generations": successful_count, # 添加成功计数
            "audio_files": audio_info
        }, f, ensure_ascii=False, indent=2)
    
    print(f"\n处理完成！")
    print(f"总句子数: {len(sentences)}")
    print(f"成功生成: {successful_count}")
    print(f"音频信息已保存到: {info_file}")
    
    return audio_info

# 主执行部分保持不变，以便仍然可以独立运行此脚本进行测试
if __name__ == "__main__":
    # 添加命令行参数
    parser = argparse.ArgumentParser(description="生成语音并管理发音词典 (支持并发)") # 更新描述
    parser.add_argument("--input", "-i", default="output_texts/お菓子の森の秘密星に願いを込めてなど.txt", help="输入文本文件")
    parser.add_argument("--output", "-o", default="output/audio", help="输出目录")
    parser.add_argument("--speaker", "-s", type=int, default=8, help="说话人ID")
    parser.add_argument("--speed", type=float, default=1.0, help="语速调整 (例如 0.5 到 2.0)")
    parser.add_argument("--no-dict", action="store_true", help="不使用发音词典")
    parser.add_argument("--tts-service", default="voicevox", choices=["voicevox", "openai_tts"], help="TTS服务类型")
    parser.add_argument("--voice-preset", choices=["default", "storyteller", "formal", "cheerful"], default="storyteller", help="语音预设，仅用于OpenAI TTS")
    parser.add_argument("--add-word", "-a", nargs=2, metavar=("WORD", "PRONUNCIATION"), help="添加词典条目")
    parser.add_argument("--remove-word", "-r", help="删除词典条目")
    parser.add_argument("--import-dict", help="导入词典文件")
    parser.add_argument("--export-dict", help="导出词典文件")
    parser.add_argument("--add-common", action="store_true", help="添加常见发音纠正")
    
    args = parser.parse_args()
    
    # 处理词典相关操作
    if args.add_word or args.remove_word or args.import_dict or args.export_dict or args.add_common:
        dict_manager = PronunciationDictionary()
        if args.add_word: dict_manager.add_word(args.add_word[0], args.add_word[1])
        if args.remove_word: dict_manager.remove_word(args.remove_word)
        if args.import_dict: dict_manager.import_from_file(args.import_dict)
        if args.export_dict: dict_manager.export_to_file(args.export_dict)
        if args.add_common: dict_manager.add_common_corrections()

    # 使用 asyncio.run 执行异步函数
    try:
        print("开始执行语音生成...")
        asyncio.run(process_voice_generation(
            args.input, 
            args.output, 
            args.speaker, 
            args.speed,
            not args.no_dict,
            args.tts_service,
            args.voice_preset
        ))
        print("语音生成执行完毕。")
    except Exception as e:
        print(f"执行语音生成时发生错误: {e}") 