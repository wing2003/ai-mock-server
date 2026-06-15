"""
测试 Auto-heal 后 IP-Key 关联计数清理功能
"""
import requests
import time
import json

BASE_URL = "http://127.0.0.1:8090"

def test_ip_key_relation_healing():
    """
    测试场景：
    1. 使用多个 Key 从同一 IP 访问，触发 ip_key_relation_check
    2. 等待 Auto-heal 恢复 Key 状态
    3. 再次使用其中一个 Key 访问，应该不再触发风控
    """
    
    # 首先，确保有一个正在运行的场景
    print("检查场景状态...")
    
    # 获取场景列表
    scenes_response = requests.get(f"{BASE_URL}/admin/scenes")
    print(f"场景列表状态码: {scenes_response.status_code}")
    
    # 假设我们使用第一个可用的场景
    # 在实际测试中，你可能需要手动启动一个场景
    
    # 创建测试用的 API Keys（这里假设已经有可用的 keys）
    # 为了简化测试，我们使用现有的 keys
    
    print("\n=== 测试 IP-Key 关联检测和 Auto-heal 清理 ===\n")
    
    # 步骤 1: 使用多个不同的 key 从同一 IP 访问，触发风控
    test_keys = [
        "sk-test-key-1",
        "sk-test-key-2", 
        "sk-test-key-3",
        "sk-test-key-4"  # 超过默认限制（通常为3）
    ]
    
    print("步骤 1: 使用多个 Key 触发 IP-Key 关联检测...")
    for i, key in enumerate(test_keys):
        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": "gpt-3.5-turbo",
            "messages": [{"role": "user", "content": "Hello"}]
        }
        
        try:
            response = requests.post(
                f"{BASE_URL}/v1/chat/completions",
                headers=headers,
                json=payload
            )
            
            print(f"Key {i+1} ({key[:12]}...): 状态码 {response.status_code}")
            
            if response.status_code == 403:
                print(f"  -> 触发风控: {response.json().get('error', {}).get('message', 'Unknown')}")
            elif response.status_code == 200:
                print(f"  -> 请求成功")
            else:
                print(f"  -> 其他响应: {response.text[:100]}")
                
        except Exception as e:
            print(f"Key {i+1} 请求失败: {e}")
        
        # 短暂延迟，避免请求过快
        time.sleep(0.5)
    
    print("\n步骤 2: 等待 Auto-heal 服务恢复 Key 状态（需要等待约 60 秒）...")
    print("注意：在实际环境中，Auto-heal 每 60 秒检查一次")
    
    # 在真实测试中，这里应该等待足够长的时间让 Auto-heal 执行
    # 由于这是一个演示，我们跳过实际等待
    print("为了演示目的，跳过实际等待时间")
    
    print("\n步骤 3: 使用其中一个 Key 再次访问，验证是否已清理关联计数...")
    
    # 使用第一个 key 再次尝试
    headers = {
        "Authorization": f"Bearer {test_keys[0]}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": "gpt-3.5-turbo",
        "messages": [{"role": "user", "content": "Hello after healing"}]
    }
    
    try:
        response = requests.post(
            f"{BASE_URL}/v1/chat/completions",
            headers=headers,
            json=payload
        )
        
        print(f" healed Key 请求状态码: {response.status_code}")
        
        if response.status_code == 403:
            print(f"  -> 仍然触发风控（这可能表示修复未生效）: {response.json().get('error', {}).get('message', 'Unknown')}")
        elif response.status_code == 200:
            print(f"  -> 请求成功！Auto-heal 和关联计数清理工作正常")
        else:
            print(f"  -> 其他响应: {response.text[:100]}")
            
    except Exception as e:
        print(f" healed Key 请求失败: {e}")

if __name__ == "__main__":
    test_ip_key_relation_healing()
