import socket
import sys

def check_port(port=8000):
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        result = sock.connect_ex(('127.0.0.1', port))
        sock.close()
        if result == 0:
            print(f'端口 {port} 正在监听')
            return True
        else:
            print(f'端口 {port} 未监听 (错误码: {result})')
            return False
    except Exception as e:
        print(f'检查端口错误: {e}')
        return False

if __name__ == '__main__':
    print('检查仪表盘状态...')
    if not check_port(8000):
        print('仪表盘未在8000端口运行')
    
    # 检查配置文件
    try:
        from core import config
        if hasattr(config, 'DASHBOARD_PORT'):
            print(f'配置中的dashboard端口: {config.DASHBOARD_PORT}')
        else:
            print('配置中未定义DASHBOARD_PORT')
    except Exception as e:
        print(f'导入配置错误: {e}')