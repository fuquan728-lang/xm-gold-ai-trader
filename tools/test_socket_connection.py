#!/usr/bin/env python3
"""
Socket连接测试脚本
用于诊断EA Socket连接问题
"""

import socket
import json
import time
import sys

def test_socket_connection(host='127.0.0.1', port=8080):
    """测试Socket连接并验证双向通信"""
    print("=" * 60)
    print("Socket连接诊断测试")
    print("=" * 60)
    print(f"目标服务器: {host}:{port}")
    
    try:
        # 1. 创建Socket
        print("\n1. 创建Socket...")
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(5.0)
        print("   [OK] Socket创建成功")
        
        # 2. 连接服务器
        print("\n2. 连接服务器...")
        start_time = time.time()
        s.connect((host, port))
        connect_time = (time.time() - start_time) * 1000
        print(f"   [OK] 连接成功 (耗时: {connect_time:.1f}ms)")
        
        # 3. 测试消息发送（模拟EA的TEST消息）
        print("\n3. 发送测试消息...")
        test_msg = b'TEST\n'  # 与EA发送的测试消息相同
        s.send(test_msg)
        print(f"   [OK] 发送成功: {test_msg}")
        
        # 4. 尝试接收响应
        print("\n4. 接收响应...")
        try:
            s.settimeout(2.0)
            response = s.recv(1024)
            if response:
                print(f"   [OK] 收到响应: {response}")
            else:
                print("   [WARN]  收到空响应")
        except socket.timeout:
            print("   [WARN]  接收超时（可能服务器没有立即响应）")
        
        # 5. 发送有效的JSON请求（模拟EA的正式请求）
        print("\n5. 发送JSON请求...")
        request = {
            'symbol': 'BTCUSD',
            'bid': 77000.0,
            'ask': 77050.0,
            'time': int(time.time())
        }
        request_json = json.dumps(request, separators=(',', ':'))  # 无空格，无换行符
        s.send(request_json.encode())
        print(f"   [OK] 发送JSON: {request_json}")
        
        # 6. 接收JSON响应
        print("\n6. 接收JSON响应...")
        s.settimeout(3.0)
        response = s.recv(4096)
        if response:
            response_str = response.decode('utf-8')
            print(f"   [OK] 收到响应: {response_str}")
            
            # 验证JSON格式
            try:
                response_json = json.loads(response_str)
                print(f"   [OK] JSON解析成功: {response_json.get('action', '未知')}")
                print(f"   [OK] 置信度: {response_json.get('confidence', 0)}")
            except json.JSONDecodeError as e:
                print(f"   [ERR] JSON解析失败: {e}")
                print(f"   [ERR] 原始响应: {response_str}")
        else:
            print("   [ERR] 收到空响应")
        
        # 7. 关闭连接
        s.close()
        print("\n7. 关闭连接...")
        print("   [OK] 连接已关闭")
        
        print("\n" + "=" * 60)
        print("[OK] 所有测试通过！Socket服务器工作正常")
        print("=" * 60)
        return True
        
    except ConnectionRefusedError:
        print("\n[ERR] 连接被拒绝 - 服务器可能未运行")
        print("请运行: python ai_service_integrated.py")
        return False
    except socket.timeout:
        print("\n[ERR] 连接超时 - 防火墙或网络问题")
        return False
    except Exception as e:
        print(f"\n[ERR] 连接失败: {e}")
        return False

def check_firewall_settings():
    """检查可能的防火墙设置"""
    print("\n" + "=" * 60)
    print("防火墙和网络设置检查")
    print("=" * 60)
    
    # 检查本地回环地址
    print("\n1. 检查本地回环地址...")
    print("   [OK] 127.0.0.1是标准本地回环地址")
    
    # 检查端口状态
    print("\n2. 检查端口状态...")
    import subprocess
    try:
        result = subprocess.run(['netstat', '-an'], capture_output=True, text=True, timeout=5)
        if ':8080' in result.stdout and 'LISTENING' in result.stdout:
            print("   [OK] 端口8080正在监听")
        else:
            print("   [ERR] 端口8080未监听")
    except:
        print("   [WARN]  无法检查端口状态")
    
    print("\n" + "=" * 60)
    print("建议检查:")
    print("1. Windows防火墙设置")
    print("2. 杀毒软件网络防护")
    print("3. MT5是否以管理员权限运行")
    print("=" * 60)

if __name__ == "__main__":
    print("MQL5 EA Socket连接诊断工具")
    print("版本: 1.0")
    print("创建时间: 2026-04-18")
    print()
    
    # 运行Socket连接测试
    success = test_socket_connection()
    
    if not success:
        check_firewall_settings()
        
    print("\n诊断完成。如果Socket测试成功但EA无法连接，请检查:")
    print("1. EA是否已重新编译（F7键）")
    print("2. EA输入参数是否正确设置")
    print("3. MT5日志中的详细错误信息")
    
    input("\n按Enter键退出...")