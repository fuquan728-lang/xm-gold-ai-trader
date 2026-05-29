#!/usr/bin/env python3
"""
快速测试web dashboard
"""

import sys
import os

print("="*70)
print("[TOOL] 测试web dashboard...")
print("="*70)

# Add project path
sys.path.insert(0, os.path.dirname(__file__))

try:
    print("\n📦 测试Flask导入...")
    from flask import Flask
    print("[OK] Flask已安装！")
    
    print("\n📦 测试web_dashboard导入...")
    from core.web_dashboard import WebDashboard
    print("[OK] WebDashboard导入成功！")
    
    print("\n-> 启动测试...")
    dashboard = WebDashboard(host="127.0.0.1", port=8000)
    print("[OK] WebDashboard对象创建成功！")
    
    print("\n="*70)
    print("[DONE] 测试通过！现在你可以：")
    print("1. 运行: python mt5_ai_service.py")
    print("2. 在浏览器打开: http://127.0.0.1:8000")
    print("="*70)
    
except ImportError as e:
    print(f"\n[ERR] 导入失败: {e}")
    if "flask" in str(e).lower():
        print("\n[TIP] 请安装Flask: pip install Flask")
    sys.exit(1)
    
except Exception as e:
    print(f"\n[ERR] 错误: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)