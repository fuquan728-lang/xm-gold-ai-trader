import sys
sys.path.append('.')
from mt5_ai_service import MTAIService
import time
import threading

def test_service_with_dashboard():
    print("=== 测试主服务中的仪表盘启动 ===")
    
    # 创建服务实例
    print("1. 创建MTAIService实例...")
    service = MTAIService(service_id="test_dashboard")
    
    # 手动启动仪表盘（模拟服务启动过程）
    print("2. 启动服务...")
    service.web_dashboard = service.WebDashboard(host="127.0.0.1", port=8000)
    
    # 检查仪表盘实例
    print(f"3. 仪表盘实例: {service.web_dashboard}")
    print(f"   仪表盘类型: {type(service.web_dashboard)}")
    
    # 启动仪表盘
    print("4. 启动仪表盘...")
    service.web_dashboard.start()
    
    # 等待启动
    time.sleep(3)
    
    # 检查状态
    print(f"5. 仪表盘运行状态: {service.web_dashboard.running}")
    print(f"   线程状态: {service.web_dashboard.thread.is_alive() if service.web_dashboard.thread else '无线程'}")
    
    # 模拟服务处理请求
    print("6. 模拟添加信号...")
    signal_data = {
        "symbol": "GOLD_",
        "action": "SELL",
        "confidence": 0.75,
        "reason": "测试信号"
    }
    service.web_dashboard.add_signal(signal_data)
    
    # 获取统计数据
    print("7. 获取统计数据...")
    import http.client
    try:
        conn = http.client.HTTPConnection("127.0.0.1", 8000, timeout=5)
        conn.request("GET", "/api/stats")
        response = conn.getresponse()
        data = response.read().decode('utf-8')
        print(f"   统计数据: {data[:200]}")
        conn.close()
    except Exception as e:
        print(f"   获取统计错误: {e}")
    
    print("\n=== 测试完成 ===")
    
    # 不停止仪表盘，继续运行
    print("仪表盘继续运行，可以在浏览器中访问 http://127.0.0.1:8000")

if __name__ == "__main__":
    test_service_with_dashboard()