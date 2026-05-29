#!/usr/bin/env python3
"""
快速Socket连接测试
"""

import socket
import time

def quick_test():
    print("快速Socket连接测试")
    print("目标: 127.0.0.1:8080")
    
    try:
        # 创建Socket
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(3.0)
        
        # 连接
        start = time.time()
        s.connect(('127.0.0.1', 8080))
        elapsed = (time.time() - start) * 1000
        
        print(f"[OK] 连接成功! 耗时: {elapsed:.1f}ms")
        
        # 发送测试消息
        s.send(b'TEST\n')
        print("[OK] 发送测试消息")
        
        # 接收响应
        s.settimeout(2.0)
        response = s.recv(1024)
        if response:
            print(f"[OK] 收到响应: {response}")
        else:
            print("[WARN] 收到空响应")
            
        s.close()
        print("[OK] 连接关闭")
        return True
        
    except ConnectionRefusedError:
        print("[ERR] 连接被拒绝 - 服务器未运行")
        return False
    except socket.timeout:
        print("[ERR] 连接超时")
        return False
    except Exception as e:
        print(f"[ERR] 错误: {e}")
        return False

if __name__ == "__main__":
    quick_test()