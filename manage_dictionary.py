import argparse
from pronunciation_dictionary import PronunciationDictionary

def main():
    parser = argparse.ArgumentParser(description="管理VOICEVOX发音词典")
    
    # 添加命令行参数
    parser.add_argument("--add", "-a", nargs=2, metavar=("WORD", "PRONUNCIATION"), help="添加词典条目")
    parser.add_argument("--remove", "-r", help="删除词典条目")
    parser.add_argument("--list", "-l", action="store_true", help="列出所有词典条目")
    parser.add_argument("--import", "-i", dest="import_file", help="从文件导入词典")
    parser.add_argument("--export", "-e", dest="export_file", help="导出词典到文件")
    parser.add_argument("--sync", "-s", action="store_true", help="同步本地词典和VOICEVOX词典")
    parser.add_argument("--add-common", "-c", action="store_true", help="添加常见发音纠正")
    
    args = parser.parse_args()
    
    # 初始化词典管理器
    dict_manager = PronunciationDictionary()
    
    # 处理命令
    if args.add:
        dict_manager.add_word(args.add[0], args.add[1])
    
    elif args.remove:
        dict_manager.remove_word(args.remove)
    
    elif args.list:
        local_dict = dict_manager.local_dict
        print(f"本地词典中有 {len(local_dict)} 个条目:")
        for surface, info in sorted(local_dict.items()):
            print(f"  {surface} -> {info['pronunciation']}")
    
    elif args.import_file:
        dict_manager.import_from_file(args.import_file)
    
    elif args.export_file:
        dict_manager.export_to_file(args.export_file)
    
    elif args.sync:
        dict_manager.sync_with_voicevox()
    
    elif args.add_common:
        dict_manager.add_common_corrections()
    
    else:
        parser.print_help()

if __name__ == "__main__":
    main() 