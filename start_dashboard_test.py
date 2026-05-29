import sys
sys.path.append('.')
from core.web_dashboard import WebDashboard
import time
import threading
import socket

print("测试仪表盘启动...")

# 创建仪表盘实例
dashboard = WebDashboard(host="127.0.0.1", port=8000)

print("正在启动仪表盘...")
dashboard.start()

# 等待服务器启动
time.sleep(3)

# 检查线程状态
print(f"仪表盘运行状态: {dashboard.running}")
print(f"线程状态: {'已启动' if dashboard.thread and dashboard.thread.is_alive() else '未启动'}")

# 检查端口
def check_port_available(port=8000):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(('127.0.0.1', port))
        sock.close()
        return True  # 端口可用
    except OSError:
        return False  # 端口被占用

print(f"端口8000可用性: {'可用' if check_port_available(8000) else '被占用'}")

# 尝试连接
try:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(2)
    result = sock.connect_ex(('127.0.0.1', 8000))
    sock.close()
    if result == 0:
        print("✅ 仪表盘端口可连接")
    else:
        print(f"❌ 仪表盘端口不可连接 (错误码: {result})")
except Exception as e:
    print(f"连接错误: {e}")

# 检查内部状态
print(f"仪表盘主机: {dashboard.host}")
print(f"仪表盘端口: {dashboard.port}")

# 等待一会让服务器启动
print("等待5秒让服务器完全启动...")
time.sleep(5)

print("测试完成")