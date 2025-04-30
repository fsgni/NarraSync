import requests
import json

# --- 配置 ---
# 请确保这里的 IP 地址和端口与您运行 app.py 的地址匹配
API_URL = "http://192.168.110.180:5000/api/generate_batch_audio" 

# 请修改为您想测试的说话人 ID
SPEAKER_ID = 3 

# 您想批量生成音频的文本列表
TEXTS_TO_SYNTHESIZE = [
    "これはバッチ処理のテストです。",
    "ちゃんと動くかな？",
    "三行目のテキスト。",
    "", # 测试空行
    "最後の行です！"
]

# --- 发送请求 --- 
def test_batch_api():
    payload = {
        "speaker_id": SPEAKER_ID,
        "texts": TEXTS_TO_SYNTHESIZE
    }
    
    print(f"向 {API_URL} 发送请求...")
    print(f"数据: {json.dumps(payload, ensure_ascii=False, indent=2)}")
    
    try:
        response = requests.post(API_URL, json=payload, timeout=90) # 允许较长超时时间
        
        print(f"\n服务器响应状态码: {response.status_code}")
        
        # 尝试解析 JSON 响应
        try:
            response_data = response.json()
            print("服务器返回内容:")
            print(json.dumps(response_data, ensure_ascii=False, indent=2))
        except json.JSONDecodeError:
            print("错误：无法解析服务器返回的 JSON 数据。")
            print("服务器原始返回内容:")
            print(response.text)
            
    except requests.exceptions.ConnectionError:
        print(f"\n错误：无法连接到服务器 {API_URL}。请确保 Flask 应用正在运行，并且地址正确。")
    except requests.exceptions.Timeout:
        print(f"\n错误：连接服务器超时 ({API_URL})。")
    except requests.exceptions.RequestException as e:
        print(f"\n错误：请求过程中发生错误: {e}")

if __name__ == "__main__":
    test_batch_api() 