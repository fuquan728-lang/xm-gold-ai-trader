#!/usr/bin/env python3
"""
简单Socket服务器 - 用于测试EA连接
"""

import socket
import json
import threading
import time
import sys

class SimpleSocketServer:
    def __init__(self, host='127.0.0.1', port=8080):
        self.host = host
        self.port = port
        self.server_socket = None
        self.running = False
        self.clients = []
        
    def start(self):
        """启动服务器"""
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(5)
            self.server_socket.settimeout(0.5)
            
            print(f"[INFO] Socket服务器启动在 {self.host}:{self.port}")
            print(f"[INFO] 等待EA连接...")
            
            self.running = True
            accept_thread = threading.Thread(target=self._accept_connections)
            accept_thread.daemon = True
            accept_thread.start()
            
            return True
            
        except Exception as e:
            print(f"[ERROR] 启动服务器失败: {e}")
            return False
    
    def _accept_connections(self):
        """接受客户端连接"""
        while self.running:
            try:
                client_socket, client_address = self.server_socket.accept()
                print(f"[INFO] 新客户端连接: {client_address}")
                
                client_thread = threading.Thread(
                    target=self._handle_client,
                    args=(client_socket, client_address)
                )
                client_thread.daemon = True
                client_thread.start()
                
                self.clients.append((client_socket, client_address, client_thread))
                
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    print(f"[ERROR] 接受连接时出错: {e}")
    
    def _handle_client(self, client_socket, client_address):
        """处理客户端连接"""
        try:
            client_socket.settimeout(5.0)
            
            while self.running:
                try:
                    # 接收数据
                    data = client_socket.recv(4096)
                    if not data:
                        print(f"[INFO] 客户端 {client_address} 断开连接")
                        break
                    
                    data_str = data.decode('utf-8').strip()
                    print(f"[INFO] 收到来自 {client_address} 的数据: {data_str[:100]}...")
                    
                    # 如果是TEST消息（EA的连接测试）
                    if data_str == 'TEST':
                        response = 'OK\n'
                        client_socket.send(response.encode())
                        print(f"[INFO] 响应TEST: OK")
                        continue
                    
                    # 尝试解析JSON请求
                    try:
                        request = json.loads(data_str)
                        print(f"[INFO] 解析JSON成功: {request}")
                        
                        # 模拟AI响应
                        response = {
                            'action': 'HOLD',
                            'confidence': 0.65,
                            'risk_score': 0.3,
                            'risk_level': 'LOW',
                            'spread_risk': 'LOW',
                            'analysis': '市场条件不明确，建议观望',
                            'timestamp': int(time.time())
                        }
                        
                        response_json = json.dumps(response, separators=(',', ':')) + '\n'
                        client_socket.send(response_json.encode())
                        print(f"[INFO] 发送响应: {response_json}")
                        
                    except json.JSONDecodeError:
                        # 不是JSON，可能是其他格式
                        print(f"[WARN] 无法解析JSON: {data_str}")
                        response = '{"error": "Invalid JSON format"}\n'
                        client_socket.send(response.encode())
                        
                except socket.timeout:
                    continue
                except Exception as e:
                    print(f"[ERROR] 处理客户端数据时出错: {e}")
                    break
                    
        except Exception as e:
            print(f"[ERROR] 处理客户端连接时出错: {e}")
        finally:
            try:
                client_socket.close()
            except:
                pass
            
            # 从客户端列表中移除
            self.clients = [(s, a, t) for s, a, t in self.clients 
                           if a != client_address]
    
    def stop(self):
        """停止服务器"""
        print("[INFO] 停止服务器...")
        self.running = False
        
        for client_socket, client_address, client_thread in self.clients:
            try:
                client_socket.close()
            except:
                pass
        
        if self.server_socket:
            try:
                self.server_socket.close()
            except:
                pass
        
        print("[INFO] 服务器已停止")

def main():
    print("=" * 60)
    print("简单Socket服务器 - MT5 EA连接测试")
    print("=" * 60)
    
    server = SimpleSocketServer()
    
    if not server.start():
        print("[ERROR] 无法启动服务器，请检查端口是否被占用")
        print("[INFO] 尝试使用其他端口...")
        
        # 尝试8081端口
        server = SimpleSocketServer(port=8081)
        if not server.start():
            return
    
    try:
        while True:
            time.sleep(1)
            print(f"[INFO] 服务器运行中... 客户端数: {len(server.clients)}")
            
    except KeyboardInterrupt:
        print("\n[INFO] 收到停止信号...")
    finally:
        server.stop()

if __name__ == "__main__":
    main()