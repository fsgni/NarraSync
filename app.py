# app.py
from flask import Flask, render_template, request, jsonify, send_file, after_this_request
import requests
import json
import os
import tempfile
import traceback # 用于更详细的错误日志
import wave # 导入 wave 模块
import uuid # 导入 uuid 模块，用于验证 UUID

# --- 配置 ---
VOICEVOX_API_URL = "http://127.0.0.1:50021" # 确保这是正确的地址
TEMP_AUDIO_DIR = './temp_audio' # 临时音频文件目录

# --- 新增：获取 WAV 文件时长的辅助函数 ---
def get_wav_duration(file_path):
    """使用 wave 模块获取 WAV 文件的时长（秒）"""
    try:
        with wave.open(file_path, 'rb') as wf:
            frames = wf.getnframes()
            rate = wf.getframerate()
            duration = frames / float(rate)
            return duration, None
    except wave.Error as e:
        err_msg = f"读取 WAV 文件头失败: {e} (文件: {file_path})"
        print(err_msg)
        return None, err_msg
    except FileNotFoundError:
        err_msg = f"计算时长时未找到文件: {file_path}"
        print(err_msg)
        return None, err_msg
    except Exception as e:
        err_msg = f"计算 WAV 时长时未知错误: {e} (文件: {file_path})"
        print(f"{err_msg}\n{traceback.format_exc()}")
        return None, err_msg

# --- Voicevox API 辅助函数 --- 
def check_voicevox_connection():
    """检查与 Voicevox 引擎的连接"""
    try:
        response = requests.get(f"{VOICEVOX_API_URL}/speakers", timeout=5)
        response.raise_for_status() 
        return True, None
    except requests.exceptions.Timeout:
        return False, f"连接 Voicevox 超时 ({VOICEVOX_API_URL})"
    except requests.exceptions.ConnectionError:
        return False, f"无法连接到 Voicevox 引擎，请确保其正在运行 ({VOICEVOX_API_URL})"
    except requests.exceptions.RequestException as e:
        return False, f"连接 Voicevox 时出错: {e}"
    except Exception as e:
        return False, f"连接 Voicevox 时发生未知错误: {e}"

def get_speakers():
    """获取所有可用的说话人"""
    connected, error = check_voicevox_connection()
    if not connected: return [], error
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
        speakers.sort(key=lambda x: x['id'])
        return speakers, None
    except Exception as e:
        print(f"获取说话人时出错: {traceback.format_exc()}")
        return [], f"获取说话人时出错: {e}"

def get_user_dict():
    """获取用户词典 (返回列表)"""
    connected, error = check_voicevox_connection()
    if not connected: return [], error
    dict_list = []
    try:
        response = requests.get(f"{VOICEVOX_API_URL}/user_dict")
        response.raise_for_status()
        user_dict = response.json() 
        for uuid, data in user_dict.items():
            data['uuid'] = uuid 
            dict_list.append(data)
        dict_list.sort(key=lambda x: x.get('surface', ''))
        return dict_list, None
    except Exception as e:
        print(f"获取用户词典时出错: {traceback.format_exc()}")
        return [], f"获取用户词典时出错: {e}"

def create_audio_query(text, speaker_id):
    """为文本和说话人创建音频查询"""
    connected, error = check_voicevox_connection()
    if not connected: return None, error
    if not text or not text.strip(): return None, "文本为空或仅包含空白。"
    if speaker_id is None: return None, "未选择说话人。"
    try:
        speaker_id = int(speaker_id) # 确保 ID 是整数
    except (ValueError, TypeError):
        return None, "无效的说话人 ID 格式。"

    try:
        params = {'text': text, 'speaker': speaker_id}
        response = requests.post(f"{VOICEVOX_API_URL}/audio_query", params=params, timeout=15)
        response.raise_for_status()
        return response.json(), None
    except requests.exceptions.RequestException as e:
        err_msg = f"创建查询失败 (Text: {text[:20]}...): {e}"
        try: # 尝试获取更详细的错误
            detail = e.response.json().get('detail', e.response.text)
            err_msg += f" | Detail: {detail}"
        except: pass
        print(err_msg)
        return None, err_msg
    except Exception as e:
        print(f"创建查询时未知错误: {traceback.format_exc()}")
        return None, f"创建查询时未知错误: {e}"

def create_synthesis(query_data, speaker_id):
    """根据音频查询数据合成音频, 返回临时文件路径"""
    connected, error = check_voicevox_connection()
    if not connected: return None, error
    if not query_data: return None, "无效的查询数据。"
    if speaker_id is None: return None, "未选择说话人。"
    try:
        speaker_id = int(speaker_id)
    except (ValueError, TypeError):
        return None, "无效的说话人 ID 格式。"

    tmp_audio_path = None
    try:
        # 确保临时目录存在
        os.makedirs(TEMP_AUDIO_DIR, exist_ok=True)

        params = {'speaker': speaker_id}
        headers = {'Content-Type': 'application/json'}
        response = requests.post(
            f"{VOICEVOX_API_URL}/synthesis",
            params=params,
            headers=headers,
            data=json.dumps(query_data),
            timeout=60 # 允许较长合成时间
        )
        response.raise_for_status()

        # 创建临时文件在指定目录下
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav", dir=TEMP_AUDIO_DIR) as tmp_audio:
            tmp_audio.write(response.content)
            tmp_audio_path = tmp_audio.name

        print(f"音频合成成功，保存到: {tmp_audio_path}")
        return tmp_audio_path, None

    except requests.exceptions.RequestException as e:
        err_msg = f"合成失败: {e}"
        try:
            detail = e.response.json().get('detail', e.response.text)
            err_msg += f" | Detail: {detail}"
        except: pass
        print(err_msg)
        # 出错时清理可能的临时文件
        if tmp_audio_path and os.path.exists(tmp_audio_path):
            try: os.remove(tmp_audio_path); print(f"已清理失败的临时文件: {tmp_audio_path}")
            except Exception as remove_err: print(f"清理失败临时文件出错: {remove_err}")
        return None, err_msg
    except Exception as e:
        print(f"合成时未知错误: {traceback.format_exc()}")
        if tmp_audio_path and os.path.exists(tmp_audio_path):
            try: os.remove(tmp_audio_path); print(f"已清理异常中的临时文件: {tmp_audio_path}")
            except Exception as remove_err: print(f"清理异常中临时文件出错: {remove_err}")
        return None, f"合成时未知错误: {e}"

def add_user_dict_word(surface, pronunciation, accent_type, word_type, priority):
    """添加新的用户词典条目"""
    connected, error = check_voicevox_connection()
    if not connected: return False, error
    if not surface or not pronunciation: return False, "表面形式和发音不能为空。"
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
        err_msg = f"添加词条失败: {e}"
        try:
            detail = e.response.json().get('detail', e.response.text)
            err_msg += f" | Detail: {detail}"
        except: pass
        print(err_msg)
        return False, err_msg
    except Exception as e:
        print(f"添加词条时未知错误: {traceback.format_exc()}")
        return False, f"添加词条时未知错误: {e}"

# --- 新增：更新和删除词典条目的辅助函数 --- 
def update_user_dict_word(word_uuid, surface, pronunciation, accent_type, word_type, priority):
    """更新指定 UUID 的用户词典条目"""
    connected, error = check_voicevox_connection()
    if not connected: return False, error
    if not surface or not pronunciation: return False, "表面形式和发音不能为空。"
    # 简单验证 UUID 格式
    try:
        uuid.UUID(word_uuid)
    except ValueError:
        return False, "无效的 UUID 格式。"
        
    try:
        params = {
            'surface': surface,
            'pronunciation': pronunciation,
            'accent_type': int(accent_type),
            'word_type': word_type,
            'priority': int(priority)
        }
        response = requests.put(f"{VOICEVOX_API_URL}/user_dict_word/{word_uuid}", params=params)
        response.raise_for_status() # 成功时通常返回 204 No Content
        print(f"成功更新词条: UUID='{word_uuid}', Surface='{surface}'")
        return True, f"成功更新词条 '{surface}' (UUID: {word_uuid})"
    except requests.exceptions.HTTPError as e:
        # 特别处理 404 Not Found
        if e.response.status_code == 404:
             err_msg = f"更新词条失败: 未找到指定 UUID 的词条 ({word_uuid})"
             print(err_msg)
             return False, err_msg
        # 处理其他 HTTP 错误 (如 422 Unprocessable Entity)
        err_msg = f"更新词条失败: {e}"
        try:
            detail = e.response.json().get('detail', e.response.text)
            err_msg += f" | Detail: {detail}"
        except: pass
        print(err_msg)
        return False, err_msg
    except requests.exceptions.RequestException as e:
        err_msg = f"更新词条时连接或请求错误: {e}"
        print(err_msg)
        return False, err_msg
    except Exception as e:
        print(f"更新词条时未知错误: {traceback.format_exc()}")
        return False, f"更新词条时未知错误: {e}"

def delete_user_dict_word(word_uuid):
    """删除指定 UUID 的用户词典条目"""
    connected, error = check_voicevox_connection()
    if not connected: return False, error
    # 简单验证 UUID 格式
    try:
        uuid.UUID(word_uuid)
    except ValueError:
        return False, "无效的 UUID 格式。"

    try:
        response = requests.delete(f"{VOICEVOX_API_URL}/user_dict_word/{word_uuid}")
        response.raise_for_status() # 成功时通常返回 204 No Content
        print(f"成功删除词条: UUID='{word_uuid}'")
        return True, f"成功删除词条 (UUID: {word_uuid})"
    except requests.exceptions.HTTPError as e:
        # 特别处理 404 Not Found
        if e.response.status_code == 404:
             err_msg = f"删除词条失败: 未找到指定 UUID 的词条 ({word_uuid})"
             print(err_msg)
             return False, err_msg
        # 处理其他 HTTP 错误
        err_msg = f"删除词条失败: {e}"
        try:
            detail = e.response.json().get('detail', e.response.text)
            err_msg += f" | Detail: {detail}"
        except: pass
        print(err_msg)
        return False, err_msg
    except requests.exceptions.RequestException as e:
        err_msg = f"删除词条时连接或请求错误: {e}"
        print(err_msg)
        return False, err_msg        
    except Exception as e:
        print(f"删除词条时未知错误: {traceback.format_exc()}")
        return False, f"删除词条时未知错误: {e}"

# --- Flask 应用 --- 
app = Flask(__name__)

@app.route('/')
def index():
    """渲染主页面"""
    return render_template('index.html')

@app.route('/api/status')
def api_status():
    """检查 Voicevox 连接状态"""
    connected, error = check_voicevox_connection()
    if connected:
        return jsonify({"status": "ok", "message": "成功连接到 Voicevox 引擎。"})
    else:
        # 返回 503 表示服务不可用
        return jsonify({"status": "error", "message": error}), 503

@app.route('/api/speakers')
def api_speakers():
    """获取说话人列表"""
    speakers, error = get_speakers()
    if error:
        # 返回 500 表示服务器内部错误
        return jsonify({"error": error}), 500
    return jsonify(speakers)

@app.route('/api/user_dict', methods=['GET'])
def api_get_user_dict():
    """获取用户词典"""
    dict_list, error = get_user_dict()
    if error:
        return jsonify({"error": error}), 500
    return jsonify(dict_list)

@app.route('/api/user_dict', methods=['POST'])
def api_add_user_dict():
    """添加用户词典条目"""
    if not request.is_json:
        return jsonify({"error": "Request must be JSON"}), 415
    
    data = request.json
    surface = data.get('surface')
    pronunciation = data.get('pronunciation')
    accent_type = data.get('accent_type', 0) # 提供默认值
    word_type = data.get('word_type', 'PROPER_NOUN')
    priority = data.get('priority', 5)

    if not surface or not pronunciation:
         return jsonify({"error": "表面形式和发音是必填项"}), 400

    success, message = add_user_dict_word(surface, pronunciation, accent_type, word_type, priority)

    if success:
        return jsonify({"message": message}), 201 # 201 Created 表示资源创建成功
    else:
        # 根据错误类型判断状态码，这里简化处理，用 400 或 500
        status_code = 400 if "不能为空" in message else 500 
        return jsonify({"error": message}), status_code

# --- 更新和删除词典条目的 API 端点 --- 
@app.route('/api/user_dict/<word_uuid>', methods=['PUT'])
def api_update_user_dict(word_uuid):
    """更新指定 UUID 的词典条目"""
    if not request.is_json:
        return jsonify({"error": "Request must be JSON"}), 415
    
    data = request.json
    surface = data.get('surface')
    pronunciation = data.get('pronunciation')
    accent_type = data.get('accent_type') # Let helper handle default if needed
    word_type = data.get('word_type')
    priority = data.get('priority')

    # 基本验证
    if not surface or not pronunciation:
         return jsonify({"error": "表面形式和发音是必填项"}), 400
    if accent_type is None or word_type is None or priority is None:
        return jsonify({"error": "缺少 accent_type, word_type 或 priority 字段"}), 400

    success, message = update_user_dict_word(word_uuid, surface, pronunciation, accent_type, word_type, priority)

    if success:
        return jsonify({"message": message}), 200 # OK for update
    else:
        # 根据错误消息判断状态码
        if "无效的 UUID" in message or "未找到" in message:
            status_code = 404 # Not Found
        elif "不能为空" in message or "缺少" in message:
             status_code = 400 # Bad Request
        else:
            status_code = 500 # Internal Server Error / Voicevox error
        return jsonify({"error": message}), status_code

@app.route('/api/user_dict/<word_uuid>', methods=['DELETE'])
def api_delete_user_dict(word_uuid):
    """删除指定 UUID 的词典条目"""
    success, message = delete_user_dict_word(word_uuid)

    if success:
        # 对于 DELETE 成功，通常返回 204 No Content，或者一个确认消息
        # return '', 204 
        return jsonify({"message": message}), 200 # Returning JSON message for consistency
    else:
        # 根据错误消息判断状态码
        if "无效的 UUID" in message or "未找到" in message:
            status_code = 404 # Not Found
        else:
            status_code = 500 # Internal Server Error / Voicevox error
        return jsonify({"error": message}), status_code

@app.route('/api/generate_audio', methods=['POST'])
def api_generate_audio():
    """为单行文本生成音频并返回文件"""
    if not request.is_json:
        return jsonify({"error": "Request must be JSON"}), 415

    data = request.json
    text = data.get('text')
    speaker_id = data.get('speaker_id')

    if not text or speaker_id is None:
        return jsonify({"error": "缺少文本或说话人 ID"}), 400

    # 1. 创建查询
    query_data, query_error = create_audio_query(text, speaker_id)
    if query_error:
        # 查询失败通常是客户端问题（如文本无效）或引擎问题
        return jsonify({"error": f"创建查询失败: {query_error}"}), 400

    # 2. 合成音频
    audio_path, synth_error = create_synthesis(query_data, speaker_id)
    if synth_error:
        # 合成失败更可能是引擎内部问题
        return jsonify({"error": f"合成音频失败: {synth_error}"}), 500
    
    if not audio_path or not os.path.exists(audio_path):
        return jsonify({"error": "合成音频后未找到文件路径"}), 500

    # 3. 返回音频文件，让 send_file 处理清理
    try:
        # send_file 会在发送后尝试关闭文件句柄
        # 使用 as_attachment=False 让浏览器尝试直接播放
        response = send_file(audio_path, mimetype='audio/wav', as_attachment=False)

        # 不再需要手动安排删除，但如果 send_file 不能自动删除，
        # 我们需要一种不同的策略，例如定期清理 temp_audio 目录。
        # 为了更安全地处理，我们可以注册一个回调来删除文件，
        # 以应对 send_file 可能不删除或无法删除的情况（虽然不太常见）。

        # 定义一个回调函数来删除文件
        def remove_file_after_request(response):
            try:
                os.remove(audio_path)
                print(f"请求处理完毕，已删除临时文件: {audio_path}")
            except Exception as e:
                print(f"请求结束后删除文件出错: {e} (文件: {audio_path})")
            return response

        # 将回调附加到响应对象上
        response.call_on_close(lambda: remove_file_after_request(response))

        return response

    except Exception as e:
        print(f"发送音频文件时出错: {e}")
        # 如果发送失败，仍然尝试删除文件
        if os.path.exists(audio_path):
            try:
                os.remove(audio_path)
                print(f"发送失败后清理临时文件: {audio_path}")
            except Exception as remove_error:
                print(f"发送失败后清理临时文件也失败: {remove_error}")
        return jsonify({"error": "发送音频文件时出错"}), 500

# --- 新增：批量生成音频 API --- 
@app.route('/api/generate_batch_audio', methods=['POST'])
def api_generate_batch_audio():
    """为多行文本批量生成音频，返回文件路径和时长列表"""
    if not request.is_json:
        return jsonify({"error": "Request must be JSON"}), 415

    data = request.json
    texts = data.get('texts')
    speaker_id = data.get('speaker_id')

    if not isinstance(texts, list) or not texts:
        return jsonify({"error": "缺少 'texts' 列表或列表为空"}), 400
    if speaker_id is None:
        return jsonify({"error": "缺少 'speaker_id'"}), 400

    results = []
    print(f"开始批量处理 {len(texts)} 行文本，说话人 ID: {speaker_id}")

    for index, text in enumerate(texts):
        result_item = {
            "index": index,
            "text": text,
            "status": "pending",
            "audio_path": None,
            "duration_seconds": None,
            "error": None
        }

        if not text or not text.strip():
            result_item["status"] = "error"
            result_item["error"] = "文本为空或仅包含空白。"
            results.append(result_item)
            print(f"  跳过第 {index+1} 行：文本为空。")
            continue

        print(f"  正在处理第 {index+1}/{len(texts)} 行: '{text[:30]}...'")
        # 1. 创建查询
        query_data, query_error = create_audio_query(text, speaker_id)
        if query_error:
            result_item["status"] = "error"
            result_item["error"] = f"创建查询失败: {query_error}"
            results.append(result_item)
            print(f"    错误：创建查询失败 - {query_error}")
            continue

        # 2. 合成音频
        audio_path, synth_error = create_synthesis(query_data, speaker_id)
        if synth_error:
            result_item["status"] = "error"
            result_item["error"] = f"合成音频失败: {synth_error}"
            results.append(result_item)
            print(f"    错误：合成音频失败 - {synth_error}")
            continue
        
        if not audio_path or not os.path.exists(audio_path):
            result_item["status"] = "error"
            result_item["error"] = "合成音频后未找到文件路径"
            results.append(result_item)
            print(f"    错误：合成后未找到文件路径")
            continue
            
        result_item["audio_path"] = audio_path

        # 3. 获取音频时长
        duration, duration_error = get_wav_duration(audio_path)
        if duration_error:
            # 时长获取失败不致命，但记录警告
            print(f"    警告：获取音频时长失败 - {duration_error}")
            result_item["error"] = f"成功生成音频，但获取时长失败: {duration_error}" 
            # 即使时长失败，也认为是部分成功
            result_item["status"] = "success_no_duration" 
        else:
            result_item["duration_seconds"] = duration
            result_item["status"] = "success"
            print(f"    成功：路径={audio_path}, 时长={duration:.3f}s")
            
        results.append(result_item)

    print(f"批量处理完成，共处理 {len(results)}/{len(texts)} 行。")
    return jsonify(results)

if __name__ == '__main__':
    # 确保临时目录存在
    os.makedirs(TEMP_AUDIO_DIR, exist_ok=True)
    # 运行 Flask 开发服务器
    # host='0.0.0.0' 允许局域网访问，如果需要的话
    # use_reloader=False 可以避免一些多进程问题，但开发时 True 更方便
    app.run(debug=True, port=5000, host='0.0.0.0') 