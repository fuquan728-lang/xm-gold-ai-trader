#!/usr/bin/env python3
"""
快速启动服务
"""

import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def start_service():
    """快速启动服务"""
    print("快速启动MT5 AI交易服务...")
    
    try:
        from mt5_ai_service import MT5AITradingService
        
        # 创建服务实例
        service = MT5AITradingService()
        
        # 启动服务（非阻塞）
        print("启动服务（后台模式）...")
        import threading
        
        def run_service():
            service.run(mode="auto")
        
        service_thread = threading.Thread(target=run_service, daemon=True)
        service_thread.start()
        
        # 等待服务启动
        print("等待服务初始化...")
        time.sleep(5)
        
        print("服务已启动:")
        print("  Socket: 127.0.0.1:8080")
        print("  WebSocket: ws://127.0.0.1:8081")
        print("  Dashboard: http://127.0.0.1:8000")
        print("  通信模式: AUTO")
        
        # 测试连接
        print("\n测试连接...")
        time.sleep(1)
        
        try:
            import socket
            sock = socket.socket()
            sock.settimeout(2)
            result = sock.connect_ex(('127.0.0.1', 8080))
            sock.close()
            
            if result == 0:
                print("[PASS] Socket端口8080监听正常")
            else:
                print("[FAIL] Socket端口8080未监听")
        except:
            pass
        
        # 保持主线程运行
        print("\n服务运行中...按Ctrl+C停止")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n停止服务...")
            service.running = False
            time.sleep(2)
            
    except Exception as e:
        print(f"[FAIL] 启动失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    start_service()