#!/usr/bin/env python3
"""
运行测试脚本并捕获输出
"""
import subprocess
import sys

def run_test():
    """运行测试脚本"""
    try:
        result = subprocess.run(
            [sys.executable, "test_account_data_simple.py"],
            cwd="d:\\搬家文件夹\\XM Global MT5",
            capture_output=True,
            text=True,
            encoding='utf-8'
        )
        
        print("=== 测试脚本输出 ===")
        print(result.stdout)
        
        if result.stderr:
            print("\n=== 错误输出 ===")
            print(result.stderr)
            
        print(f"\n=== 退出码: {result.returncode} ===")
        
        return result.returncode == 0
        
    except Exception as e:
        print(f"运行测试失败: {e}")
        return False

if __name__ == "__main__":
    success = run_test()
    sys.exit(0 if success else 1)