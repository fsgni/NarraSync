# voicevox_dict_editor.py (重构版)
import gradio as gr
import requests
import json
import os
import tempfile
import soundfile as sf
import io
import html

# --- 配置 ---
VOICEVOX_API_URL = "http://127.0.0.1:50021"
MAX_LINES_DISPLAY = 100 # 限制选择器中显示的最大行数，防止过多选项

# --- Voicevox API 辅助函数 ---

def check_voicevox_connection():
    """检查与 Voicevox 引擎的连接"""
    try:
        response = requests.get(f"{VOICEVOX_API_URL}/speakers")
        response.raise_for_status() # 如果状态码不是 2xx 则抛出异常
        # print("成功连接到 Voicevox 引擎。") # 减少打印
        return True, None
    except requests.exceptions.RequestException as e:
        error_message = f"无法连接到 Voicevox 引擎 ({VOICEVOX_API_URL}): {e}"
        print(error_message)
        return False, error_message
    except Exception as e:
        error_message = f"连接 Voicevox 时发生未知错误: {e}"
        print(error_message)
        return False, error_message

def get_speakers():
    """获取所有可用的说话人"""
    connected, error = check_voicevox_connection()
    if not connected:
        return [], error

    speakers = []
    try:
        response = requests.get(f"{VOICEVOX_API_URL}/speakers")
        response.raise_for_status()
        data = response.json()
        for speaker in data:
            for style in speaker.get('styles', []):
                speakers.append({
                    'name': f"{speaker['name']} ({style['name']})",
                    'id': style['id']
                })
        # 按 ID 排序，方便查找
        speakers.sort(key=lambda x: x['id'])
        # print(f"获取到 {len(speakers)} 个说话人。") # 减少打印
        return speakers, None
    except requests.exceptions.RequestException as e:
        error_message = f"获取说话人列表时出错: {e}"
        print(error_message)
        return [], error_message
    except Exception as e:
        error_message = f"处理说话人数据时出错: {e}"
        print(error_message)
        return [], error_message

def get_user_dict():
    """获取用户词典"""
    connected, error = check_voicevox_connection()
    if not connected:
        # return {}, error # API 返回的是字典，但我们处理成列表
        return [], error # 返回空列表和错误信息

    try:
        response = requests.get(f"{VOICEVOX_API_URL}/user_dict")
        response.raise_for_status()
        user_dict = response.json()
        # print(f"获取到 {len(user_dict)} 条用户词典条目。") # 减少打印
        # 将字典转换为列表，方便 Gradio 处理，并添加原始 key (uuid)
        dict_list = []
        for uuid, data in user_dict.items():
            data['uuid'] = uuid # 将 uuid 添加到字典内部
            dict_list.append(data)
        # 按 surface 排序
        dict_list.sort(key=lambda x: x.get('surface', ''))
        return dict_list, None
    except requests.exceptions.RequestException as e:
        error_message = f"获取用户词典时出错: {e}"
        print(error_message)
        return [], error_message # 返回空列表
    except Exception as e:
        error_message = f"处理用户词典数据时出错: {e}"
        print(error_message)
        return [], error_message # 返回空列表

def create_audio_query(text, speaker_id):
    """为文本和说话人创建音频查询"""
    connected, error = check_voicevox_connection()
    if not connected:
        return None, error

    if not text or not text.strip(): # 检查是否为空或只有空白
        return None, "跳过空行或空白行。"
    if speaker_id is None:
        return None, "请选择一个说话人。"

    try:
        params = {'text': text, 'speaker': speaker_id}
        response = requests.post(f"{VOICEVOX_API_URL}/audio_query", params=params)
        response.raise_for_status()
        print(f"为文本 '{text[:20]}...' (Speaker ID: {speaker_id}) 创建 Audio Query 成功。") # 打印部分文本
        return response.json(), None
    except requests.exceptions.RequestException as e:
        error_message = f"创建 Audio Query 时出错: {e}. 文本: '{text[:20]}...'"
        print(error_message)
        try:
            error_detail = e.response.json().get('detail')
            if isinstance(error_detail, list): # 错误详情可能是列表
                 error_message += f" 详情: {error_detail[0].get('msg') if error_detail else ''}"
            elif isinstance(error_detail, str):
                 error_message += f" 详情: {error_detail}"
            elif error_detail:
                 error_message += f" 详情: {str(error_detail)}"
        except:
            pass
        return None, error_message
    except Exception as e:
        error_message = f"创建 Audio Query 时发生未知错误: {e}"
        print(error_message)
        return None, error_message

def create_synthesis(query_data, speaker_id):
    """根据音频查询数据合成音频"""
    connected, error = check_voicevox_connection()
    if not connected:
        return None, error
    if not query_data:
        return None, "无效的 Audio Query 数据。"
    if speaker_id is None:
        return None, "请选择一个说话人。"

    tmp_audio_path = None # 初始化路径变量
    try:
        params = {'speaker': speaker_id}
        headers = {'Content-Type': 'application/json'}
        response = requests.post(
            f"{VOICEVOX_API_URL}/synthesis",
            params=params,
            headers=headers,
            data=json.dumps(query_data),
            timeout=60 # 增加超时时间以防长句合成慢
        )
        response.raise_for_status()

        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp_audio:
            tmp_audio.write(response.content)
            tmp_audio_path = tmp_audio.name # 获取路径

        print(f"音频合成成功 (Speaker ID: {speaker_id})，保存到: {tmp_audio_path}")
        # 返回临时文件的路径，让 Gradio 处理
        return tmp_audio_path, None

    except requests.exceptions.RequestException as e:
        error_message = f"合成音频时出错: {e}"
        print(error_message)
        try:
            error_detail = e.response.json().get('detail')
            if isinstance(error_detail, list):
                 error_message += f" 详情: {error_detail[0].get('msg') if error_detail else ''}"
            elif isinstance(error_detail, str):
                 error_message += f" 详情: {error_detail}"
            elif error_detail:
                 error_message += f" 详情: {str(error_detail)}"
        except:
            pass
        # 出错时尝试清理可能的临时文件
        if tmp_audio_path and os.path.exists(tmp_audio_path):
           try:
               os.remove(tmp_audio_path)
               print(f"已清理失败合成的临时文件: {tmp_audio_path}")
           except Exception as remove_err:
               print(f"清理失败的临时文件时出错: {remove_err}")
        return None, error_message
    except Exception as e:
        error_message = f"合成音频时发生未知错误: {e}"
        print(error_message)
         # 出错时尝试清理可能的临时文件
        if tmp_audio_path and os.path.exists(tmp_audio_path):
           try:
               os.remove(tmp_audio_path)
               print(f"已清理异常中的临时文件: {tmp_audio_path}")
           except Exception as remove_err:
               print(f"清理异常中的临时文件时出错: {remove_err}")
        return None, error_message

def add_user_dict_word(surface, pronunciation, accent_type, word_type, priority):
    """添加新的用户词典条目"""
    connected, error = check_voicevox_connection()
    if not connected:
        return False, error

    if not surface or not pronunciation:
        return False, "表面形式 (Surface) 和发音 (Pronunciation) 不能为空。"

    try:
        params = {
            'surface': surface,
            'pronunciation': pronunciation,
            'accent_type': int(accent_type),
            'word_type': word_type,
            'priority': int(priority)
        }
        response = requests.post(f"{VOICEVOX_API_URL}/user_dict_word", params=params)
        response.raise_for_status()
        new_uuid = response.text.strip().replace('"', '')
        print(f"成功添加词条: Surface='{surface}', Pronunciation='{pronunciation}', UUID='{new_uuid}'")
        return True, f"成功添加词条 '{surface}' (UUID: {new_uuid})"
    except requests.exceptions.RequestException as e:
        error_message = f"添加词条时出错: {e}"
        try:
            error_detail = e.response.json().get('detail')
            if isinstance(error_detail, list):
                error_message += f" 详情: {error_detail[0].get('msg') if error_detail else ''}"
            elif isinstance(error_detail, str):
                 error_message += f" 详情: {error_detail}"
            elif error_detail:
                 error_message += f" 详情: {str(error_detail)}"
            else:
                error_message += f" 状态码: {e.response.status_code}, 响应: {e.response.text}"
        except Exception as parse_err:
             error_message += f" 状态码: {e.response.status_code if hasattr(e, 'response') else 'N/A'}, 无法解析错误详情: {parse_err}"
        print(error_message)
        return False, error_message
    except Exception as e:
        error_message = f"添加词条时发生未知错误: {e}"
        print(error_message)
        return False, error_message

# --- 新的 Gradio UI ---
def build_ui_revamped():
    # 获取初始数据
    initial_speakers, speaker_error = get_speakers()
    initial_speaker_choices = [(s['name'], s['id']) for s in initial_speakers] if initial_speakers else []
    initial_dict, dict_error = get_user_dict()
    initial_dict_list = initial_dict if isinstance(initial_dict, list) else []

    # 处理初始错误
    initial_status = ""
    if speaker_error: initial_status += f"加载说话人失败: {speaker_error}\n"
    if dict_error: initial_status += f"加载用户词典失败: {dict_error}\n"
    conn_ok, conn_err = check_voicevox_connection()
    if not conn_ok and not initial_status: initial_status = f"无法连接到 Voicevox 引擎: {conn_err}"

    # 存储分割后的行/句及其原始文本
    processed_lines_state = gr.State([])

    with gr.Blocks(title="Voicevox 脚本校对与词典编辑器") as demo:
        gr.Markdown("# Voicevox 脚本校对与词典编辑器")
        status_textbox = gr.Textbox(label="状态", value=initial_status, interactive=False, lines=3)

        with gr.Row():
            # 左侧：脚本处理与预览
            with gr.Column(scale=2):
                gr.Markdown("### 1. 输入脚本并处理")
                script_input = gr.Textbox(
                    label="粘贴或输入完整脚本",
                    placeholder="请在此处输入您的日文脚本...",
                    lines=15
                )
                with gr.Row():
                    speaker_dropdown = gr.Dropdown(
                        label="选择说话人",
                        choices=initial_speaker_choices,
                        value=initial_speaker_choices[0][1] if initial_speaker_choices else None,
                        interactive=True, scale=3
                    )
                    refresh_speakers_btn = gr.Button("刷新", scale=1)
                process_script_btn = gr.Button("处理脚本", variant="secondary")

                gr.Markdown("### 2. 预览与交互")
                line_selector = gr.Radio(
                    label="选择要预览或编辑的行/句",
                    choices=[], # 初始为空，处理后填充
                    interactive=True
                )
                with gr.Row():
                    play_selected_btn = gr.Button("播放选中")
                    edit_selected_btn = gr.Button("编辑选中词语") # 触发填充下方编辑区
                audio_player = gr.Audio(label="选中行/句音频", type="filepath", interactive=False)

            # 右侧：词典编辑与显示
            with gr.Column(scale=1):
                gr.Markdown("### 3. 用户词典编辑")
                gr.Markdown('在这里添加、修改或删除词典条目。点击"编辑选中词语"后，对应文本会填充到下方。')
                with gr.Blocks(): # 使用 Blocks 嵌套以控制布局
                    surface_input = gr.Textbox(label="表面形式 (Surface)")
                    pronunciation_input = gr.Textbox(label="发音 (Pronunciation - 片假名)")
                    accent_type_input = gr.Number(label="声调类型 (Accent Type)", value=0, precision=0)
                    with gr.Row():
                         word_type_input = gr.Dropdown(label="词语类型", choices=["PROPER_NOUN", "COMMON_NOUN", "VERB", "ADJECTIVE", "SUFFIX", "USER"], value="PROPER_NOUN")
                         priority_input = gr.Slider(label="优先级", minimum=0, maximum=10, value=5, step=1)
                    uuid_input = gr.Textbox(label="UUID (用于更新/删除)", interactive=False, placeholder="选中现有词条时显示")
                    with gr.Row():
                        add_word_btn = gr.Button("添加新词条", variant="primary")
                        update_word_btn = gr.Button("更新词条 (待实现)")
                        delete_word_btn = gr.Button("删除词条 (待实现)", variant="stop")

                gr.Markdown("### 4. 当前用户词典")
                refresh_dict_btn = gr.Button("刷新词典列表")
                dict_display = gr.DataFrame(
                    headers=["surface", "pronunciation", "accent_type", "word_type", "priority", "uuid"],
                    datatype=["str", "str", "number", "str", "number", "str"],
                    value=initial_dict_list,
                    label="用户词典",
                    interactive=False,
                    row_count=(10, "dynamic"),
                    col_count=(6, "fixed")
                 )

        # --- 事件处理 ---

        # 刷新说话人
        def refresh_speakers_ui(current_speaker_id):
            speakers, error = get_speakers()
            if error:
                return gr.update(), f"刷新说话人失败: {error}"
            else:
                choices = [(s['name'], s['id']) for s in speakers]
                new_value = current_speaker_id if current_speaker_id is not None and any(c[1] == current_speaker_id for c in choices) else (choices[0][1] if choices else None)
                return gr.update(choices=choices, value=new_value), "说话人列表已刷新。"
        refresh_speakers_btn.click(
            refresh_speakers_ui,
            inputs=[speaker_dropdown],
            outputs=[speaker_dropdown, status_textbox]
        )

        # 处理脚本，填充选择器
        def process_script(script_text):
            if not script_text:
                return gr.update(choices=[], value=None), [], "请输入脚本。" # 清空选择器和状态
            lines = [line.strip() for line in script_text.splitlines() if line.strip()] # 分割并去空行
            if not lines:
                return gr.update(choices=[], value=None), [], "脚本为空或只包含空行。"

            # 创建 Radio 的选项 (显示行号和部分文本)
            choices = [f"{i+1}: {line[:30]}{'...' if len(line)>30 else ''}" for i, line in enumerate(lines[:MAX_LINES_DISPLAY])] # 限制显示数量

            # 存储原始行文本和对应的选项标签
            processed_lines = [{"label": choice, "text": lines[i]} for i, choice in enumerate(choices)]

            status_msg = f"脚本已处理，共 {len(lines)} 行。"
            if len(lines) > MAX_LINES_DISPLAY:
                status_msg += f" 选择器中仅显示前 {MAX_LINES_DISPLAY} 行。"

            # 同时清空之前的音频播放器
            return gr.update(choices=choices, value=choices[0] if choices else None), processed_lines, status_msg, gr.update(value=None)
        process_script_btn.click(
            process_script,
            inputs=[script_input],
            outputs=[line_selector, processed_lines_state, status_textbox, audio_player] # 添加 audio_player 到 outputs
        )

        # 播放选中的行/句
        def play_selected(selected_label, processed_lines, speaker_id):
            if not selected_label:
                return None, "请先选择一行。"
            if not processed_lines:
                 return None, "请先处理脚本。" # 防止状态为空时出错

            # 从状态中找到对应的原始文本
            selected_text = None
            for item in processed_lines:
                if item["label"] == selected_label:
                    selected_text = item["text"]
                    break

            if selected_text is None:
                 # 在实践中，如果 selected_label 来自 choices，这里不应该发生
                 return None, f"错误：找不到标签 '{selected_label}' 对应的原始文本。"

            query_data, query_error = create_audio_query(selected_text, speaker_id)
            if query_error:
                # 对 query_error 进行字符串转换和转义，以防包含特殊字符
                error_msg = html.escape(str(query_error))
                return None, f"创建音频查询失败: {error_msg}"

            audio_path, synth_error = create_synthesis(query_data, speaker_id)
            if synth_error:
                error_msg = html.escape(str(synth_error))
                return None, f"合成音频失败: {error_msg}"

            # 成功时返回音频路径和成功消息
            return audio_path, f"已生成选中行的音频。"
        play_selected_btn.click(
            play_selected,
            inputs=[line_selector, processed_lines_state, speaker_dropdown],
            outputs=[audio_player, status_textbox]
        )

        # 编辑选中的行/句 (填充到编辑区)
        def edit_selected(selected_label, processed_lines):
            if not selected_label:
                return gr.update(), "请先选择一行。" # 不改变 surface_input, 更新状态
            if not processed_lines:
                return gr.update(), "请先处理脚本。"

            selected_text = None
            for item in processed_lines:
                if item["label"] == selected_label:
                    selected_text = item["text"]
                    break

            if selected_text is None:
                return gr.update(), f"错误：找不到标签 '{selected_label}' 对应的原始文本。"

            # 更新 surface 输入框，清空其他（因为用户可能只想添加新读法）
            return gr.update(value=selected_text), f"已将选中行文本填充到'表面形式'输入框，请填写正确发音。", gr.update(value=""), gr.update(value=0), gr.update(value="PROPER_NOUN"), gr.update(value=5), gr.update(value="")
        edit_selected_btn.click(
            edit_selected,
            inputs=[line_selector, processed_lines_state],
            outputs=[surface_input, status_textbox, pronunciation_input, accent_type_input, word_type_input, priority_input, uuid_input]
        )


        # 刷新词典
        def refresh_dictionary_ui():
            dict_list, error = get_user_dict()
            value_to_update = dict_list if isinstance(dict_list, list) else []
            msg = f"刷新词典失败: {error}" if error else "用户词典已刷新。"
            return gr.update(value=value_to_update), msg
        refresh_dict_btn.click(refresh_dictionary_ui, outputs=[dict_display, status_textbox])

        # 添加新词条的处理
        def handle_add_word(surface, pronunciation, accent_type, word_type, priority):
            # ... (与之前相同，但需要确保刷新后表格更新) ...
            success, message = add_user_dict_word(surface, pronunciation, accent_type, word_type, priority)
            dict_list, error = get_user_dict() # 重新获取词典
            value_to_update = dict_list if isinstance(dict_list, list) else []
            if error:
                message += f" | 刷新词典列表失败: {error}"
            # 无论是否刷新成功，都返回从 API 调用获取的消息
            # 清空输入
            return gr.update(value=value_to_update), message, gr.update(value=""), gr.update(value=""), gr.update(value=0)
        add_word_btn.click(
            handle_add_word,
            inputs=[surface_input, pronunciation_input, accent_type_input, word_type_input, priority_input],
            outputs=[dict_display, status_textbox, surface_input, pronunciation_input, accent_type_input]
        )

        # --- TODO: 词典编辑功能 (更新、删除、选中行填充) ---

    return demo

if __name__ == "__main__":
    # 启动前检查连接
    connected, error = check_voicevox_connection()
    if not connected:
        print(f"启动错误: {error}")
        print("请确保 Voicevox 引擎正在运行，并且 VOICEVOX_API_URL 设置正确。")

    app = build_ui_revamped() # 使用新的 UI 构建函数
    app.launch(inbrowser=True) 