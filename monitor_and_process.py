import time
import logging
import configparser
import subprocess
import os
import shutil
import sys
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from ui_helpers import format_text_for_shorts_gpt

# --- Configuration ---
CONFIG_FILE = 'monitor_config.ini'
LOG_FILE = 'monitor.log'
PROCESSED_LOG_FILE = 'processed_files.log' # Log file for processed files

# --- Setup Logging ---
log_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Log to file
file_handler = logging.FileHandler(LOG_FILE, encoding='utf-8')
file_handler.setFormatter(log_formatter)
logger.addHandler(file_handler)

# Log to console
stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setFormatter(log_formatter)
logger.addHandler(stream_handler)


# --- Load Configuration ---
def load_config():
    config = configparser.ConfigParser()
    if not Path(CONFIG_FILE).exists():
        logger.error(f"配置文件 {CONFIG_FILE} 未找到！请确保它与脚本在同一目录下。")
        sys.exit(1)
    try:
        config.read(CONFIG_FILE, encoding='utf-8')
        # Basic validation
        # PROCESSED_FOLDER is now optional
        required_paths = ['MONITORED_FOLDER', 'OUTPUT_VIDEO_FOLDER', 'FULL_PROCESS_SCRIPT', 'PYTHON_EXECUTABLE', 'DEFAULT_OUTPUT_SUBDIR'] 
        for key in required_paths:
            if not config.has_option('Paths', key) or not config['Paths'][key].strip():
                logger.error(f"配置文件 [Paths] 部分缺少或为空: {key}")
                sys.exit(1)
        if not config.has_section('ProcessingDefaults'):
             logger.warning(f"配置文件缺少 [ProcessingDefaults] 部分，将不使用任何默认参数运行处理脚本。")
             config.add_section('ProcessingDefaults') # Add empty section if missing

        # Convert relative paths to absolute relative to the script directory if necessary
        # Example: config['Paths']['MONITORED_FOLDER'] = str(Path(config['Paths']['MONITORED_FOLDER']).resolve())

        return config
    except configparser.Error as e:
        logger.error(f"读取配置文件 {CONFIG_FILE} 时出错: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"加载配置时发生意外错误: {e}")
        sys.exit(1)

# --- Helper to read processed files log ---
def get_processed_files() -> set:
    processed = set()
    log_path = Path(PROCESSED_LOG_FILE)
    if log_path.exists():
        try:
            with log_path.open('r', encoding='utf-8') as f:
                processed = {line.strip() for line in f if line.strip()}
        except Exception as e:
            logger.error(f"读取处理日志 {PROCESSED_LOG_FILE} 时出错: {e}")
    return processed

# --- Helper to add file to processed log ---
def add_to_processed_log(filename: str):
    log_path = Path(PROCESSED_LOG_FILE)
    try:
        with log_path.open('a', encoding='utf-8') as f:
            f.write(filename + '\n')
    except Exception as e:
        logger.error(f"写入处理日志 {PROCESSED_LOG_FILE} 时出错: {e}")

# --- Process File Function ---
def process_file(filepath, config):
    logger.info(f"检测到新文件: {filepath}")
    if not filepath.lower().endswith('.txt'):
        logger.info(f"跳过非 .txt 文件: {filepath}")
        return

    try:
        input_file = Path(filepath)
        input_filename = input_file.name
        input_filename_stem = input_file.stem # Filename without extension

        # --- Check if already processed ---
        processed_files = get_processed_files()
        if input_filename in processed_files:
            logger.info(f"文件 {input_filename} 已在处理日志中，跳过。")
            return
        # --- End Check ---
        
        paths_config = config['Paths']
        defaults_config = config['ProcessingDefaults']
        
        # --- Apply Shorts GPT Formatting if enabled --- 
        try:
            # --- Get raw string value and manually check ---
            format_shorts_raw = defaults_config.get('FORMAT_TEXT_SHORTS', 'false') # Get as string, default 'false'
            # Clean the value (remove comments, strip whitespace, lowercase)
            cleaned_value = format_shorts_raw.split('#')[0].strip().lower()
            should_format_shorts = cleaned_value in ['true', 'yes', '1']
            # --- End manual check ---
            if not should_format_shorts:
                 # Optional: Log if the original value wasn't explicitly 'false' or empty
                 if cleaned_value not in ['false', 'no', '0', '']:
                     logger.warning(f"配置文件中 FORMAT_TEXT_SHORTS 的值 ('{format_shorts_raw}') 不是有效的 true/yes/1，将禁用格式化。")

        except Exception as e: # Catch potential errors during .get()
             logger.error(f"读取 FORMAT_TEXT_SHORTS 配置时出错: {e}")
             should_format_shorts = False

        if should_format_shorts:
            logger.info(f"配置中 FORMAT_TEXT_SHORTS 为 True，准备开始格式化 {input_filename}...")
            logger.info(f"为文件 {input_filename} 应用 Shorts GPT 格式化...")
            try:
                # Read original content
                with input_file.open('r', encoding='utf-8') as f:
                    original_content = f.read()
                
                # Format content
                formatted_content = format_text_for_shorts_gpt(original_content)
                
                # Write formatted content back to the original file
                with input_file.open('w', encoding='utf-8') as f:
                    f.write(formatted_content)
                logger.info(f"已将格式化后的内容写回文件: {input_filename}")

            except FileNotFoundError:
                logger.error(f"在应用格式化时找不到文件: {input_filename}")
                return # Stop processing if file disappears
            except Exception as format_err:
                logger.error(f"应用 Shorts GPT 格式化时出错: {format_err}")
                # Decide whether to continue without formatting or stop
                logger.warning(f"将继续使用原始文件内容处理 {input_filename}")
                # return # Uncomment to stop processing on formatting error
        else:
            logger.info(f"配置中 FORMAT_TEXT_SHORTS 为 False 或解析失败，跳过格式化 {input_filename}。")
        # --- End Formatting --- 

        full_process_script = Path(paths_config['FULL_PROCESS_SCRIPT'])
        python_executable = paths_config['PYTHON_EXECUTABLE']
        # processed_folder = Path(paths_config['PROCESSED_FOLDER']) # No longer needed for moving
        output_video_folder = Path(paths_config['OUTPUT_VIDEO_FOLDER'])
        # Assuming output is relative to the full_process_script's parent directory
        script_dir = full_process_script.parent
        default_output_dir = script_dir / paths_config['DEFAULT_OUTPUT_SUBDIR']
        
        # Ensure target directories exist
        # processed_folder.mkdir(parents=True, exist_ok=True) # No longer needed for moving
        output_video_folder.mkdir(parents=True, exist_ok=True)

        # Construct the command
        command = [python_executable, str(full_process_script), str(input_file)]
        
        # Add default arguments from config
        for key, value in defaults_config.items():
            # --- Clean value: remove inline comments --- 
            cleaned_value = value.split('#')[0].strip() # Take part before # and strip whitespace
            # --- End Clean value ---
            
            if key.upper() == 'FORMAT_TEXT_SHORTS':
                continue # This was handled by pre-processing
            
            param_name = f"--{key.lower()}"
            val_lower = cleaned_value.lower() # Use cleaned value for checks

            # Handle boolean flags (only true/yes are added, false/no are skipped)
            if val_lower in ['true', 'yes']:
                command.append(param_name) # Append only the flag for true booleans
            elif val_lower in ['false', 'no', '']:
                 pass # Skip false boolean flags or empty values
            else:
                 # Treat all other non-empty values as arguments needing a value
                 command.append(param_name)
                 command.append(cleaned_value) # Append the cleaned value
                 
        logger.info(f"准备执行命令: {' '.join(command)}")

        # Run the process - run in the script's directory context
        # Use absolute path for input file to avoid issues with working directory
        process = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', errors='replace', cwd=script_dir)

        logger.info(f"脚本 {full_process_script.name} 对文件 {input_filename} 的处理已完成，返回码: {process.returncode}")
        if process.stdout:
            logger.info(f"""脚本输出 (stdout):
{process.stdout}""")
        if process.stderr:
            # Log stderr as warning or error based on return code
            if process.returncode == 0:
                logger.warning(f"""脚本输出 (stderr - 但返回码为0):
{process.stderr}""")
            else:
                logger.error(f"""脚本错误输出 (stderr):
{process.stderr}""")

        # Check result and move files / log processed
        if process.returncode == 0:
            logger.info(f"处理成功: {input_filename}")
            
            # --- Add to processed log ---
            add_to_processed_log(input_filename)
            logger.info(f"已将 {input_filename} 添加到处理日志。")
            # --- End Add to log ---

            # Find the output video file (adjust pattern if needed)
            expected_video_filename = f"{input_filename_stem}_final.mp4"
            output_video_path = default_output_dir / expected_video_filename
            
            if output_video_path.exists():
                target_video_path = output_video_folder / expected_video_filename
                try:
                    logger.info(f"移动视频文件 {output_video_path} 到 {target_video_path}")
                    shutil.move(str(output_video_path), str(target_video_path))
                except Exception as e:
                     logger.error(f"移动视频文件 {output_video_path} 失败: {e}")
            else:
                logger.warning(f"处理成功，但未找到预期的视频文件: {output_video_path}")

            # --- Remove moving the processed text file ---
            # target_text_path = processed_folder / input_file.name
            # try:
            #     logger.info(f"移动已处理文本文件 {input_file} 到 {target_text_path}")
            #     shutil.move(str(input_file), str(target_text_path))
            # except Exception as e:
            #      logger.error(f"移动文本文件 {input_file} 失败: {e}")
            # --- End Remove moving ---
                 
        else:
            logger.error(f"处理失败: {input_filename} (返回码: {process.returncode})。文件将保留在监控文件夹中，且未记录为已处理。")
            # Optionally move to an 'error' folder instead
            # error_folder = Path(paths_config.get('ERROR_FOLDER', 'error_files')) # Example
            # error_folder.mkdir(parents=True, exist_ok=True)
            # shutil.move(str(input_file), str(error_folder / input_file.name))

    except FileNotFoundError:
         logger.error(f"错误：找不到 Python 可执行文件 '{python_executable}' 或处理脚本 '{full_process_script}'. 请检查配置文件中的 PYTHON_EXECUTABLE 和 FULL_PROCESS_SCRIPT 路径。")
    except Exception as e:
        logger.exception(f"处理文件 {filepath} 时发生意外错误: {e}") # Use logger.exception to include traceback


# --- Watchdog Event Handler ---
class NewTextFileHandler(FileSystemEventHandler):
    def __init__(self, config):
        self.config = config
        self.processing_files = set() # Keep track of files being processed

    def on_created(self, event):
        if not event.is_directory and event.src_path.lower().endswith('.txt'):
            filepath = event.src_path
            # Avoid processing a file multiple times if events fire rapidly
            # Check against processing set *before* sleeping and checking log
            if filepath not in self.processing_files:
                 self.processing_files.add(filepath)
                 try:
                     # Give the file system a moment to settle, prevent reading empty files
                     time.sleep(1) 
                     # Double check the log file *after* sleep, before processing
                     if Path(filepath).name in get_processed_files():
                         logger.info(f"文件 {Path(filepath).name} 在等待后发现已在处理日志中，跳过。")
                     else:
                         process_file(filepath, self.config)
                 finally:
                     # Ensure the file is removed from the set even if processing fails
                     if filepath in self.processing_files:
                        self.processing_files.remove(filepath)

# --- Main Execution ---
if __name__ == "__main__":
    logger.info("--- 启动文件夹监控脚本 (使用处理日志) ---") # Updated log message
    config = load_config()
    
    monitored_folder = config['Paths']['MONITORED_FOLDER']
    
    # Ensure monitored folder exists
    Path(monitored_folder).mkdir(parents=True, exist_ok=True)

    logger.info(f"开始监控文件夹: {monitored_folder}")
    
    event_handler = NewTextFileHandler(config)
    observer = Observer()
    observer.schedule(event_handler, monitored_folder, recursive=False) # recursive=False: only watch top level
    observer.start()
    
    try:
        while True:
            # Keep the script running, check observer health periodically
            if not observer.is_alive():
                 logger.error("监控器意外停止，尝试重启...")
                 # Consider more robust restart logic if needed
                 observer = Observer()
                 observer.schedule(event_handler, monitored_folder, recursive=False)
                 observer.start()
            time.sleep(5) # Check every 5 seconds
    except KeyboardInterrupt:
        logger.info("接收到停止信号 (Ctrl+C)，正在停止监控...")
        observer.stop()
    except Exception as e:
         logger.exception("监控过程中发生未捕获的错误") # Log unexpected errors
         observer.stop()
    finally:
        observer.join() # Wait for the observer thread to finish
        logger.info("--- 监控脚本已停止 ---") 