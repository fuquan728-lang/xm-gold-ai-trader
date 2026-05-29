
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DeepSeek API 测试脚本
用于验证 DeepSeek API 连接和功能
"""

import os
import sys
import json
import requests
from pathlib import Path

# 添加项目根目录
sys.path.insert(0, str(Path(__file__).parent))

# 加载环境变量
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent / '.env'
    if env_path.exists():
        load_dotenv(env_path)
        print("[OK] 已加载 .env 文件")
    else:
        print("[WARN] 未找到 .env 文件")
except ImportError:
    print("[WARN] 未安装 python-dotenv")

# 读取配置
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_API_URL = os.getenv("DEEPSEEK_API_URL", "https://api.deepseek.com/v1/chat/completions")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
USE_DEEPSEEK = os.getenv("USE_DEEPSEEK", "false").lower() == "true"

print("=" * 60)
print("DeepSeek API 配置检查")
print("=" * 60)

print(f"USE_DEEPSEEK: {USE_DEEPSEEK}")
print(f"API URL: {DEEPSEEK_API_URL}")
print(f"Model: {DEEPSEEK_MODEL}")
print(f"API Key: {'已配置' if DEEPSEEK_API_KEY else '[ERR] 未配置'}")

# 检查 API 密钥
if not DEEPSEEK_API_KEY:
    print("\n[ERR] ERROR: 没有配置 API 密钥！")
    print("请在 .env 文件中设置 DEEPSEEK_API_KEY")
    print("获取地址: https://platform.deepseek.com/api-keys")
    sys.exit(1)

if DEEPSEEK_API_KEY == "your-actual-deepseek-api-key-here":
    print("\n[ERR] ERROR: 使用的是示例 API 密钥！")
    print("请替换为您的真实 API 密钥")
    print("获取地址: https://platform.deepseek.com/api-keys")
    sys.exit(1)

if not USE_DEEPSEEK:
    print("\n[WARN] WARNING: USE_DEEPSEEK 目前设置为 false")
    print("测试完成后，请在 .env 文件中设置 USE_DEEPSEEK=true")

print("\n" + "=" * 60)
print("测试 API 连接...")
print("=" * 60)

# 测试 API 连接
headers = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {DEEPSEEK_API_KEY}"
}

payload = {
    "model": DEEPSEEK_MODEL,
    "messages": [
        {
            "role": "user",
            "content": "这是一个测试，请回复: {\"action\": \"BUY\", \"confidence\": 0.85, \"reason\": \"测试成功\"}"
        }
    ],
    "temperature": 0.3,
    "max_tokens": 200
}

try:
    print(f"正在发送请求到: {DEEPSEEK_API_URL}")
    response = requests.post(
        DEEPSEEK_API_URL,
        headers=headers,
        json=payload,
        timeout=30
    )

    print(f"响应状态码: {response.status_code}")

    if response.status_code == 200:
        print("[OK] API 连接成功！")
        result = response.json()

        print("\nAPI 响应内容:")
        print("-" * 60)
        content = result["choices"][0]["message"]["content"]
        print(content[:500])

        # 尝试提取 JSON
        try:
            first_brace = content.find('{')
            last_brace = content.rfind('}')
            if first_brace != -1 and last_brace > first_brace:
                json_str = content[first_brace:last_brace+1]
                data = json.loads(json_str)
                print("\n[OK] 成功解析 JSON 响应!")
                print(f"Action: {data.get('action')}")
                print(f"Confidence: {data.get('confidence')}")
                print(f"Reason: {data.get('reason')}")
        except Exception as e:
            print(f"[WARN] JSON 解析警告: {e}")

        print("\n" + "=" * 60)
        print("[DONE] DeepSeek API 测试成功！")
        print("=" * 60)
        print("\n下一步:")
        print("1. 在 .env 文件中设置: USE_DEEPSEEK=true")
        print("2. 重启 AI 服务")
        print("3. 现在 DeepSeek 将会处理交易分析！")

    else:
        print(f"\n[ERR] API 请求失败: {response.status_code}")
        print(response.text)
        print("\n请检查:")
        print("- API 密钥是否正确")
        print("- 网络连接是否正常")
        print("- DeepSeek 服务是否可用")

except Exception as e:
    print(f"\n[ERR] 请求异常: {e}")
    print("\n请检查:")
    print("- 网络连接")
    print("- API 密钥")
    print("- requests 模块是否已安装 (pip install requests)")
