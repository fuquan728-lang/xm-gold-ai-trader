#!/usr/bin/env python3
"""
MT5 AI Trading System - Enhanced WebSocket Handler (V4.0)

应用异步Python模式的WebSocket服务器，提供：
1. 连接池管理
2. 自动重连机制
3. 速率限制保护
4. 完善的错误处理
5. 连接状态监控
6. 性能优化
"""

import asyncio
import json
import time
import random
from typing import Dict, Any, Optional, Set, List, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum

try:
    import websockets
    from websockets.server import WebSocketServerProtocol
    from websockets.exceptions import ConnectionClosed, ConnectionClosedOK, ConnectionClosedError
    HAS_WEBSOCKETS = True
except ImportError:
    HAS_WEBSOCKETS = False
    print("[WARN] Warning: websockets library not installed. WebSocket mode unavailable.")

from core.logger import logger


class ConnectionStatus(Enum):
    """连接状态枚举"""
    CONNECTING = "connecting"
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    RECONNECTING = "reconnecting"
    ERROR = "error"


@dataclass
class ClientInfo:
    """客户端信息"""
    client_id: str
    websocket: WebSocketServerProtocol
    remote_address: tuple
    connected_at: datetime
    last_activity: datetime
    status: ConnectionStatus = ConnectionStatus.CONNECTED
    message_count: int = 0
    error_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


class ConnectionPool:
    """连接池管理器"""
    
    def __init__(self, max_connections: int = 1000, max_connections_per_ip: int = 10):
        self.max_connections = max_connections
        self.max_connections_per_ip = max_connections_per_ip
        self.clients: Dict[str, ClientInfo] = {}  # client_id -> ClientInfo
        self.ip_connections: Dict[str, Set[str]] = {}  # ip -> set of client_ids
        
    def add_client(self, client_info: ClientInfo) -> bool:
        """添加客户端到连接池"""
        client_id = client_info.client_id
        ip = client_info.remote_address[0]
        
        # 检查总连接数限制
        if len(self.clients) >= self.max_connections:
            logger.warning(f"[WARN] Connection pool full: {len(self.clients)}/{self.max_connections}")
            return False
        
        # 检查单个IP连接数限制
        ip_conns = self.ip_connections.get(ip, set())
        if len(ip_conns) >= self.max_connections_per_ip:
            logger.warning(f"[WARN] IP connection limit reached for {ip}: {len(ip_conns)}/{self.max_connections_per_ip}")
            return False
        
        # 添加客户端
        self.clients[client_id] = client_info
        
        # 更新IP连接映射
        if ip not in self.ip_connections:
            self.ip_connections[ip] = set()
        self.ip_connections[ip].add(client_id)
        
        logger.info(f"[OK] Client added to pool: {client_id} (IP: {ip}, total: {len(self.clients)})")
        return True
    
    def remove_client(self, client_id: str) -> Optional[ClientInfo]:
        """从连接池移除客户端"""
        client_info = self.clients.pop(client_id, None)
        if client_info:
            ip = client_info.remote_address[0]
            if ip in self.ip_connections:
                self.ip_connections[ip].discard(client_id)
                if not self.ip_connections[ip]:
                    del self.ip_connections[ip]
            logger.info(f"[OK] Client removed from pool: {client_id}")
        return client_info
    
    def get_client(self, client_id: str) -> Optional[ClientInfo]:
        """获取客户端信息"""
        return self.clients.get(client_id)
    
    def update_client_status(self, client_id: str, status: ConnectionStatus):
        """更新客户端状态"""
        if client_info := self.get_client(client_id):
            client_info.status = status
            client_info.last_activity = datetime.now()
    
    def increment_message_count(self, client_id: str):
        """增加客户端消息计数"""
        if client_info := self.get_client(client_id):
            client_info.message_count += 1
            client_info.last_activity = datetime.now()
    
    def increment_error_count(self, client_id: str):
        """增加客户端错误计数"""
        if client_info := self.get_client(client_id):
            client_info.error_count += 1
    
    def get_stats(self) -> Dict[str, Any]:
        """获取连接池统计信息"""
        status_counts = {}
        for status in ConnectionStatus:
            status_counts[status.value] = 0
        
        for client in self.clients.values():
            status_counts[client.status.value] += 1
        
        return {
            "total_clients": len(self.clients),
            "total_ips": len(self.ip_connections),
            "status_counts": status_counts,
            "max_connections": self.max_connections,
            "max_connections_per_ip": self.max_connections_per_ip
        }
    
    def cleanup_inactive(self, inactive_seconds: int = 300) -> List[str]:
        """清理非活动连接"""
        now = datetime.now()
        inactive_clients = []
        
        for client_id, client_info in list(self.clients.items()):
            inactive_time = (now - client_info.last_activity).total_seconds()
            if inactive_time > inactive_seconds:
                inactive_clients.append(client_id)
        
        removed_ids = []
        for client_id in inactive_clients:
            if client_info := self.remove_client(client_id):
                removed_ids.append(client_id)
                logger.info(f"[INFO] Removed inactive client: {client_id} (inactive for {inactive_seconds}s)")
        
        return removed_ids


class EnhancedWebSocketHandler:
    """增强版WebSocket服务器处理器（V4.0）"""
    
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8081,
        process_request_func: Optional[Callable] = None,
        max_connections: int = 1000,
        max_connections_per_ip: int = 10,
        rate_limit_per_client: int = 100,  # 每秒最大请求数
        inactive_timeout: int = 300,  # 秒
    ):
        self.host = host
        self.port = port
        self.process_request = process_request_func
        
        # 连接池管理
        self.connection_pool = ConnectionPool(
            max_connections=max_connections,
            max_connections_per_ip=max_connections_per_ip
        )
        
        # 速率限制
        self.rate_limit_per_client = rate_limit_per_client
        self.client_rate_limits: Dict[str, List[float]] = {}  # client_id -> timestamps
        
        # 超时设置
        self.inactive_timeout = inactive_timeout
        
        # 服务器状态
        self.server = None
        self.running = False
        self.request_count = 0
        self.total_messages = 0
        self.total_errors = 0
        
        # 清理任务
        self.cleanup_task = None
        
        logger.info(f"[OK] Enhanced WebSocket Handler initialized (host={host}, port={port})")
    
    async def _cleanup_inactive_clients(self):
        """定期清理非活动客户端"""
        while self.running:
            try:
                await asyncio.sleep(60)  # 每60秒清理一次
                removed = self.connection_pool.cleanup_inactive(self.inactive_timeout)
                if removed:
                    logger.info(f"[INFO] Cleaned {len(removed)} inactive clients")
            except asyncio.CancelledError:
                logger.info("[INFO] Cleanup task cancelled")
                break
            except Exception as e:
                logger.error(f"[ERR] Cleanup task error: {e}")
                await asyncio.sleep(5)  # 错误后等待5秒
    
    def _check_rate_limit(self, client_id: str) -> bool:
        """检查客户端速率限制"""
        now = time.time()
        timestamps = self.client_rate_limits.get(client_id, [])
        
        # 清理1秒前的记录
        recent_timestamps = [ts for ts in timestamps if now - ts < 1.0]
        
        # 检查是否超过限制
        if len(recent_timestamps) >= self.rate_limit_per_client:
            logger.warning(f"[WARN] Rate limit exceeded for client {client_id}: {len(recent_timestamps)} requests/sec")
            return False
        
        # 更新记录
        recent_timestamps.append(now)
        self.client_rate_limits[client_id] = recent_timestamps
        return True
    
    async def handle_connection(self, websocket: WebSocketServerProtocol):
        """处理单个连接（不需要path）"""
        remote_addr = websocket.remote_address
        client_id = f"{remote_addr[0]}:{remote_addr[1]}-{int(time.time()*1000)}"
        
        # 创建客户端信息
        client_info = ClientInfo(
            client_id=client_id,
            websocket=websocket,
            remote_address=remote_addr,
            connected_at=datetime.now(),
            last_activity=datetime.now(),
            status=ConnectionStatus.CONNECTING
        )
        
        # 尝试添加到连接池
        if not self.connection_pool.add_client(client_info):
            logger.warning(f"[WARN] Connection pool full, rejecting client {client_id}")
            await websocket.close(code=1008, reason="Connection pool full")
            return
        
        logger.info(f"📡 [WebSocket] 新连接: {client_id}")
        self.connection_pool.update_client_status(client_id, ConnectionStatus.CONNECTED)
        
        try:
            # 发送欢迎消息
            welcome_msg = {
                "type": "welcome",
                "client_id": client_id,
                "server_time": datetime.now().isoformat(),
                "rate_limit": self.rate_limit_per_client
            }
            await self._send_to_client(websocket, welcome_msg)
            
            # 处理消息循环
            async for message in websocket:
                if not self.running:
                    break
                    
                # 检查速率限制
                if not self._check_rate_limit(client_id):
                    error_msg = {
                        "type": "error",
                        "code": "RATE_LIMIT_EXCEEDED",
                        "message": f"Rate limit exceeded: {self.rate_limit_per_client} requests/sec"
                    }
                    await self._send_to_client(websocket, error_msg)
                    continue
                
                # 处理消息
                await self._handle_message(websocket, message, client_id)
                
                # 更新活动时间
                self.connection_pool.update_client_status(client_id, ConnectionStatus.CONNECTED)
                
        except ConnectionClosedOK:
            logger.info(f"📡 [WebSocket] 连接正常关闭: {client_id}")
        except ConnectionClosedError as e:
            logger.warning(f"[WARN] [WebSocket] 连接异常关闭: {client_id} - {e}")
            self.connection_pool.update_client_status(client_id, ConnectionStatus.ERROR)
            self.total_errors += 1
        except Exception as e:
            logger.error(f"[ERR] [WebSocket] 连接错误: {client_id} - {e}")
            import traceback
            traceback.print_exc()
            self.connection_pool.update_client_status(client_id, ConnectionStatus.ERROR)
            self.total_errors += 1
        finally:
            # 清理连接
            self.connection_pool.remove_client(client_id)
            logger.info(f"📡 [WebSocket] 客户端已断开: {client_id}")
    
    async def _handle_message(self, websocket: WebSocketServerProtocol, message: str, client_id: str):
        """处理收到的消息"""
        start_time = time.time()
        self.request_count += 1
        self.total_messages += 1
        self.connection_pool.increment_message_count(client_id)
        
        try:
            logger.info(f"📥 [WebSocket] 收到消息 ({client_id})")
            
            # 记录原始内容（限制长度）
            msg_preview = message[:200] + ("..." if len(message) > 200 else "")
            logger.debug(f"📥 原始内容: {msg_preview}")
            
            response = None
            
            # 处理特殊消息
            if message.strip().upper() == "PING":
                response = {
                    "type": "pong",
                    "server_time": datetime.now().isoformat(),
                    "client_id": client_id
                }
                logger.info(f"🏓 收到PING，返回PONG")
            
            elif message.strip().upper() == "STATUS":
                response = {
                    "type": "status",
                    "server_status": self.get_status(),
                    "client_status": self.connection_pool.get_client(client_id).__dict__ if self.connection_pool.get_client(client_id) else None,
                    "timestamp": datetime.now().isoformat()
                }
                
            else:
                # 解析JSON消息
                try:
                    request_data = json.loads(message)
                    request_type = request_data.get("type", "unknown")
                    symbol = request_data.get("symbol", "N/A")
                    
                    logger.info(f"📥 收到请求: type={request_type}, symbol={symbol}")
                    
                    # 调用处理器
                    if self.process_request:
                        response = self.process_request(request_data)
                    else:
                        response = {
                            "type": "error",
                            "action": "HOLD",
                            "confidence": 0.0,
                            "reason": "No processor available",
                            "symbol": symbol,
                            "analysis_time": datetime.now().isoformat()
                        }
                        
                except json.JSONDecodeError as e:
                    response = {
                        "type": "error",
                        "code": "JSON_PARSE_ERROR",
                        "message": f"JSON解析失败: {e}"
                    }
            
            # 发送响应
            if response:
                await self._send_to_client(websocket, response)
                elapsed = (time.time() - start_time) * 1000
                logger.info(f"[OK] [WebSocket] 请求处理完成 - {elapsed:.1f}ms")
            
        except Exception as e:
            logger.error(f"[ERR] 处理失败: {e}")
            import traceback
            traceback.print_exc()
            self.connection_pool.increment_error_count(client_id)
            self.total_errors += 1
            
            error_resp = {
                "type": "error",
                "code": "PROCESSING_ERROR",
                "message": f"处理失败: {e}"
            }
            await self._send_to_client(websocket, error_resp)
    
    async def _send_to_client(self, websocket: WebSocketServerProtocol, response: Dict[str, Any]):
        """发送消息到客户端"""
        try:
            response_str = json.dumps(response, ensure_ascii=False, separators=(',', ':'))
            await websocket.send(response_str)
            logger.debug(f"📤 [WebSocket] 响应已发送: {len(response_str)} bytes")
        except Exception as e:
            logger.error(f"[ERR] 发送响应失败: {e}")
    
    async def broadcast(self, message: Dict[str, Any], client_ids: Optional[List[str]] = None):
        """广播消息到所有或指定的客户端"""
        if not self.connection_pool.clients:
            return
        
        message_str = json.dumps(message, ensure_ascii=False)
        targets = []
        
        if client_ids:
            # 发送到指定客户端
            for client_id in client_ids:
                if client_info := self.connection_pool.get_client(client_id):
                    targets.append(client_info)
        else:
            # 发送到所有客户端
            targets = list(self.connection_pool.clients.values())
        
        if not targets:
            return
        
        # 并发发送
        send_tasks = []
        disconnected_clients = []
        
        for client_info in targets:
            try:
                send_tasks.append(client_info.websocket.send(message_str))
            except Exception:
                disconnected_clients.append(client_info.client_id)
        
        # 等待所有发送完成
        if send_tasks:
            await asyncio.gather(*send_tasks, return_exceptions=True)
        
        # 清理断开连接的客户端
        for client_id in disconnected_clients:
            self.connection_pool.remove_client(client_id)
        
        logger.info(f"[INFO] 广播完成: 发送到 {len(targets)} 个客户端")
    
    async def send_to_client(self, client_id: str, message: Dict[str, Any]) -> bool:
        """发送消息到指定客户端"""
        client_info = self.connection_pool.get_client(client_id)
        if not client_info:
            logger.warning(f"[WARN] Client not found: {client_id}")
            return False
        
        try:
            await self._send_to_client(client_info.websocket, message)
            return True
        except Exception as e:
            logger.error(f"[ERR] Failed to send to client {client_id}: {e}")
            self.connection_pool.remove_client(client_id)
            return False
    
    async def start(self):
        """启动增强版WebSocket服务器"""
        if not HAS_WEBSOCKETS:
            logger.error("[ERR] 缺少websockets库，无法启动WebSocket服务器")
            return False
        
        try:
            # 启动清理任务
            self.cleanup_task = asyncio.create_task(self._cleanup_inactive_clients())
            
            # 启动服务器
            self.server = await websockets.serve(
                self.handle_connection,
                self.host,
                self.port,
                ping_interval=30,  # 30秒ping间隔
                ping_timeout=10,   # 10秒ping超时
                max_size=2**20,    # 1MB最大消息大小
                compression=None
            )
            
            self.running = True
            logger.info(f"-> [WebSocket] 增强版服务器已启动: ws://{self.host}:{self.port}")
            logger.info(f"[INFO] 连接限制: 最大{self.connection_pool.max_connections}连接，每IP{self.connection_pool.max_connections_per_ip}连接")
            logger.info(f"[INFO] 速率限制: {self.rate_limit_per_client} 请求/秒/客户端")
            
            return True
            
        except Exception as e:
            logger.error(f"[ERR] [WebSocket] 启动失败: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    async def stop(self):
        """停止增强版WebSocket服务器"""
        self.running = False
        
        # 取消清理任务
        if self.cleanup_task:
            self.cleanup_task.cancel()
            try:
                await self.cleanup_task
            except asyncio.CancelledError:
                pass
        
        # 关闭所有连接
        for client_info in list(self.connection_pool.clients.values()):
            try:
                await client_info.websocket.close()
            except Exception:
                pass
        
        # 关闭服务器
        if self.server:
            self.server.close()
            await self.server.wait_closed()
        
        logger.info("[OK] [WebSocket] 增强版服务器已停止")
    
    def get_status(self) -> Dict[str, Any]:
        """获取服务器状态"""
        pool_stats = self.connection_pool.get_stats()
        
        return {
            "running": self.running,
            "host": self.host,
            "port": self.port,
            "connection_pool": pool_stats,
            "rate_limit_per_client": self.rate_limit_per_client,
            "inactive_timeout": self.inactive_timeout,
            "statistics": {
                "request_count": self.request_count,
                "total_messages": self.total_messages,
                "total_errors": self.total_errors,
                "uptime": getattr(self, "_start_time", None),
                "current_time": datetime.now().isoformat()
            }
        }
    
    def get_detailed_stats(self) -> Dict[str, Any]:
        """获取详细统计信息"""
        status = self.get_status()
        
        # 客户端详情
        clients_details = []
        for client_id, client_info in self.connection_pool.clients.items():
            clients_details.append({
                "client_id": client_id,
                "remote_address": client_info.remote_address,
                "status": client_info.status.value,
                "connected_at": client_info.connected_at.isoformat(),
                "last_activity": client_info.last_activity.isoformat(),
                "message_count": client_info.message_count,
                "error_count": client_info.error_count
            })
        
        status["clients_details"] = clients_details
        return status


# 使用示例
if __name__ == "__main__":
    async def example_process_request(request_data: Dict[str, Any]) -> Dict[str, Any]:
        """示例请求处理器"""
        return {
            "type": "response",
            "action": "BUY",
            "confidence": 0.85,
            "reason": "Example response from enhanced handler",
            "symbol": request_data.get("symbol", "N/A"),
            "timestamp": datetime.now().isoformat()
        }
    
    async def main():
        # 创建增强版处理器
        handler = EnhancedWebSocketHandler(
            host="127.0.0.1",
            port=8081,
            process_request_func=example_process_request,
            max_connections=500,
            max_connections_per_ip=20,
            rate_limit_per_client=50
        )
        
        # 启动服务器
        if await handler.start():
            print("Enhanced WebSocket server started")
            print(f"Status: {handler.get_status()}")
            
            # 运行一段时间
            try:
                await asyncio.sleep(3600)  # 运行1小时
            except KeyboardInterrupt:
                print("Shutting down...")
            finally:
                await handler.stop()
        else:
            print("Failed to start server")
    
    asyncio.run(main())