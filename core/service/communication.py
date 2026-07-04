# -*- coding: utf-8 -*-
"""
Communication Runners - 通信层拆分 (Phase 2)
负责3种通信模式的独立运行：
- FileModeRunner: MT5 Files 目录文件模式
- SocketModeRunner: TCP Socket 模式
- WebSocketModeRunner: WebSocket 模式

从 MT5AITradingService 拆分而来 (2026-07-04)
"""

import json
import time
import socket
import socketserver
import threading
import asyncio
import traceback
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, Callable

from core.logger import logger
from core.websocket_handler import WebSocketHandler, HAS_WEBSOCKETS
from core.mql5_data import get_mql5_data_manager
from core import config


# ==================== 辅助函数 ====================

def _utc_now_iso() -> str:
    return datetime.now().isoformat()


_V0_SAFE_HOLD = {
    "action": "HOLD",
    "confidence": 0.65,
    "reason": "安全回退: 处理返回空",
    "use_deepseek": False,
    "cached": False,
}


# ==================== Socket 负载解析 ====================

def parse_socket_payload(data: str):
    """Classify a socket payload without matching TEST inside JSON values.
    
    Returns:
        ("json", dict) | ("test", None) | ("healthcheck", None)
    """
    text = data.strip().strip("\x00")
    json_start = text.find("{")
    json_end = text.rfind("}")
    if json_start >= 0 and json_end > json_start:
        return "json", json.loads(text[json_start : json_end + 1])

    command = text.upper()
    if command == "TEST":
        return "test", None
    if command == "HEALTHCHECK":
        return "healthcheck", None

    return "json", json.loads(text)


# ==================== Socket Handler ====================

class AISocketHandler(socketserver.BaseRequestHandler):
    """AI Socket请求处理器 - 支持回调注入（Phase 2 重构）"""

    def handle(self):
        """高可靠的请求处理"""
        # 优先使用注入的 process_request 回调，回退到全局 get_ai_service()
        process_request = getattr(self.server, "_process_request_func", None)
        
        client_ip = self.client_address[0]
        start_time = time.time()

        try:
            self.request.settimeout(10.0)
            logger.info(f"[SOCKET] 连接来自 {client_ip}:{self.client_address[1]}")

            # 1. 接收数据
            raw_data = b""
            try:
                while True:
                    chunk = self.request.recv(4096)
                    if not chunk:
                        break
                    raw_data += chunk
                    if b"\n" in raw_data:
                        break
            except socket.timeout:
                pass

            if not raw_data:
                logger.warning("[WARN] 收到空数据")
                result = _V0_SAFE_HOLD
            else:
                data = raw_data.decode("utf-8", errors="ignore").strip()

                # 2. 解析
                try:
                    payload_type, request_data = parse_socket_payload(data)
                except json.JSONDecodeError as json_e:
                    logger.error(f"[ERR] JSON解析失败: {json_e}")
                    result = {
                        "error": str(json_e),
                        "action": "HOLD",
                        "confidence": 0.65,
                        "reason": "安全回退: JSON解析失败",
                        "use_deepseek": False,
                        "cached": False,
                    }
                    payload_type, request_data = "invalid", None

                if payload_type == "test":
                    logger.info("TEST 收到测试消息")
                    result = {"status": "ok", "message": "Server ready"}
                elif payload_type == "healthcheck":
                    logger.info("HEALTHCHECK 收到健康检查请求")
                    result = {
                        "status": "ok",
                        "message": "Service health check",
                        "timestamp": datetime.now().isoformat(),
                    }
                elif payload_type == "json":
                    try:
                        json_start = data.find("{")
                        json_end = data.rfind("}")
                        if json_start >= 0 and json_end > json_start:
                            json_str = data[json_start : json_end + 1]
                            request_data = json.loads(json_str)
                        else:
                            request_data = json.loads(data)

                        # MQL5 数据更新
                        if "type" in request_data and request_data["type"] == "mql5_data":
                            logger.info("[DATA] 收到 MQL5 数据更新")
                            try:
                                mql5_manager = get_mql5_data_manager()
                                success = mql5_manager.update_from_json(request_data)
                                result = {
                                    "status": "ok" if success else "error",
                                    "message": "数据更新成功" if success else "数据更新失败",
                                }
                            except Exception as e:
                                logger.error(f"更新 MQL5 数据异常: {e}")
                                result = {"status": "error", "message": str(e)}
                        else:
                            # 普通 AI 请求
                            logger.info(f"处理请求: {request_data.get('symbol', 'UNKNOWN')}")
                            if process_request:
                                try:
                                    result = process_request(request_data)
                                    if not result:
                                        result = _V0_SAFE_HOLD
                                except Exception as proc_e:
                                    logger.warning(f"[WARN] 处理异常: {proc_e}")
                                    result = {
                                        "action": "HOLD",
                                        "confidence": 0.65,
                                        "reason": f"安全回退: {str(proc_e)}",
                                        "use_deepseek": False,
                                        "cached": False,
                                    }
                            else:
                                result = {
                                    "action": "HOLD",
                                    "confidence": 0.0,
                                    "reason": "process_request 回调未注入",
                                    "use_deepseek": False,
                                    "cached": False,
                                }

                    except json.JSONDecodeError as json_e:
                        logger.error(f"[ERR] JSON解析失败: {json_e}")
                        result = {
                            "error": str(json_e),
                            "action": "HOLD",
                            "confidence": 0.65,
                            "reason": "安全回退: JSON解析失败",
                            "use_deepseek": False,
                            "cached": False,
                        }

            # 3. 确保结果有效
            if not result:
                result = {
                    "action": "HOLD",
                    "confidence": 0.0,
                    "reason": "无结果",
                    "use_deepseek": False,
                    "cached": False,
                }

            # 4. 发送响应
            response_str = json.dumps(result, ensure_ascii=False) + "\n"
            self.request.sendall(response_str.encode("utf-8"))

            # 5. 记录
            action = result.get("action", "UNKNOWN")
            conf = result.get("confidence", 0.0)
            elapsed = time.time() - start_time
            logger.info(f"[Socket] 响应: {action} (置信度: {conf:.2f}, 用时: {elapsed:.3f}s)")

        except Exception as e:
            logger.error(f"[ERR] handle异常: {e}")
            logger.error(f"   堆栈: {traceback.format_exc()}")
            try:
                error_result = {
                    "error": str(e),
                    "action": "HOLD",
                    "confidence": 0.0,
                    "reason": "服务器内部错误",
                    "use_deepseek": False,
                    "cached": False,
                }
                self.request.sendall(
                    (json.dumps(error_result, ensure_ascii=False) + "\n").encode("utf-8")
                )
            except (socket.error, OSError, BrokenPipeError) as send_err:
                logger.debug(f"[DEBUG] handle错误响应发送失败(客户端可能已断开): {send_err}")


class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    """支持多线程的TCP服务器"""
    allow_reuse_address = True
    daemon_threads = True
    request_queue_size = (
        config.MAX_CONCURRENT_CONNECTIONS
        if hasattr(config, "MAX_CONCURRENT_CONNECTIONS")
        else 10
    )


# ==================== FileModeRunner ====================

class FileModeRunner:
    """File模式通信运行器"""

    def __init__(
        self,
        process_request_func: Callable,
        file_handler,
        local_instance,
        observation_journal=None,
        running_getter: Optional[Callable[[], bool]] = None,
    ):
        self._process_request = process_request_func
        self._file_handler = file_handler
        self._local_instance = local_instance
        self._observation_journal = observation_journal
        self._running_getter = running_getter or (lambda: True)

    @property
    def running(self) -> bool:
        return self._running_getter()

    def _write_observation(self, request_data, response_data, write_ok):
        """写入观察日志（安全包装）"""
        if not getattr(config, "OBSERVATION_JOURNAL_ENABLED", True):
            return
        journal = getattr(self, "_observation_journal", None)
        if journal is None:
            return
        try:
            journal.record(request_data, response_data, response_write_ok=bool(write_ok))
        except Exception as e:
            logger.warning(f"[OBS] observation journal write skipped: {e}")

    def run(self):
        """File模式主循环"""
        logger.info("[DIR] 启动文件模式处理器...")
        mode = "file"  # 兼容 service_ready 写入

        while self.running:
            try:
                fh = self._file_handler
                fh.update_health_check()
                mt5_path = fh.find_request_file()
                if mt5_path is None:
                    time.sleep(0.1)
                    continue

                logger.info(f"[DIR] 找到请求文件，路径: {mt5_path}")
                fh.write_service_ready(mt5_path, self._local_instance.service_id, mode, ready=True)

                request_file = Path(mt5_path) / "ai_request.json"
                content = fh.safe_read(str(request_file))

                if not content:
                    logger.info(f"[WARN] 请求文件内容为空")
                    time.sleep(config.FILE_CHECK_INTERVAL)
                    continue

                logger.info(f"收到请求文件内容: {content[:200]}...")

                try:
                    request_data = json.loads(content)
                    # 注入时间戳（兼容原有 _utc_now_iso 调用）
                    request_data["_request_read_at"] = _utc_now_iso()
                    response_data = self._process_request(request_data)
                    if response_data:
                        response_data["response_written_at"] = _utc_now_iso()
                        logger.info(
                            "[RESPONSE] protocol=%s request_id=%s action=%s confidence=%s blocked_by=%s",
                            response_data.get("protocol_version"),
                            response_data.get("request_id"),
                            response_data.get("action"),
                            response_data.get("confidence"),
                            response_data.get("blocked_by"),
                        )
                        logger.info(
                            f"准备写入响应: {json.dumps(response_data, ensure_ascii=False)[:200]}..."
                        )

                        result = fh.write_response(response_data, mt5_path)
                        self._write_observation(request_data, response_data, result)

                        if result:
                            logger.info(f"[OK] 响应文件写入成功")
                        else:
                            logger.error(f"[ERR] 响应文件写入失败")

                except json.JSONDecodeError as e:
                    logger.error(f"[ERR] JSON解析失败: {e}, 原始数据: {content[:100]}")
                except Exception as e:
                    logger.error(f"[ERR] 处理请求异常: {e}, 文件: {request_file}")
                    logger.error(f"   堆栈: {traceback.format_exc()}")
                finally:
                    time.sleep(config.FILE_CHECK_INTERVAL)

            except Exception as e:
                logger.error(f"[ERR] 文件模式循环错误: {e}")
                time.sleep(0.1)


# ==================== SocketModeRunner ====================

class SocketModeRunner:
    """Socket模式通信运行器"""

    def __init__(
        self,
        process_request_func: Callable,
        host: Optional[str] = None,
        port: Optional[int] = None,
        running_getter: Optional[Callable[[], bool]] = None,
    ):
        self._process_request = process_request_func
        self._host = host or config.SOCKET_HOST
        self._port = port or config.SOCKET_PORT
        self._running_getter = running_getter or (lambda: True)
        self._server: Optional[ThreadedTCPServer] = None
        self._thread: Optional[threading.Thread] = None

    @property
    def running(self) -> bool:
        return self._running_getter()

    @property
    def server(self):
        return self._server

    @property
    def thread(self):
        return self._thread

    def start(self) -> threading.Thread:
        """启动Socket服务器，返回服务器线程"""
        logger.info(f"[SOCKET] 启动Socket服务器 ({self._host}:{self._port})...")

        try:
            self._server = ThreadedTCPServer((self._host, self._port), AISocketHandler)
            self._server.timeout = 1
            # 注入 process_request 回调
            self._server._process_request_func = self._process_request

            self._thread = threading.Thread(target=self._run_server, daemon=True)
            self._thread.start()

            logger.info(f"[OK] Socket服务器已启动，监听 {self._host}:{self._port}")
            return self._thread

        except Exception as e:
            logger.error(f"[ERR] 启动Socket服务器失败: {e}")
            raise

    def _run_server(self):
        """运行Socket服务器主循环"""
        try:
            while self.running:
                try:
                    self._server.handle_request()
                except Exception as e:
                    logger.debug(f"[DEBUG] Socket请求处理异常: {e}")
                    time.sleep(0.1)
        except Exception as e:
            logger.error(f"[ERR] Socket服务器运行异常: {e}")
        finally:
            if self._server:
                try:
                    self._server.server_close()
                except Exception as exc:
                    logger.debug(f"[DEBUG] Socket服务器关闭异常: {exc}")

    def shutdown(self):
        """安全关闭Socket服务器"""
        if self._server:
            try:
                self._server.shutdown()
                self._server.server_close()
            except Exception:
                pass


# ==================== WebSocketModeRunner ====================

class WebSocketModeRunner:
    """WebSocket模式通信运行器"""

    def __init__(
        self,
        process_request_func: Callable,
        host: Optional[str] = None,
        port: Optional[int] = None,
        running_getter: Optional[Callable[[], bool]] = None,
    ):
        self._process_request = process_request_func
        self._host = host or config.SOCKET_HOST
        self._port = port or (config.SOCKET_PORT + 1)
        self._running_getter = running_getter or (lambda: True)
        self._handler: Optional[WebSocketHandler] = None
        self._thread: Optional[threading.Thread] = None

    @property
    def running(self) -> bool:
        return self._running_getter()

    @property
    def handler(self):
        return self._handler

    @property
    def is_running(self) -> bool:
        return self._handler is not None and self._handler.running

    def start(self) -> bool:
        """启动WebSocket服务器，返回是否成功"""
        logger.info(f"[WS] 启动WebSocket服务器 ({self._host}:{self._port})...")

        try:
            if not HAS_WEBSOCKETS:
                raise ImportError("websockets library not installed")

            self._handler = WebSocketHandler(
                host=self._host,
                port=self._port,
                process_request_func=self._process_request,
            )

            def _run_ws_server():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

                async def _run():
                    started = await self._handler.start()
                    if not started:
                        return
                    while self.running and self._handler.running:
                        await asyncio.sleep(0.1)

                loop.run_until_complete(_run())

            self._thread = threading.Thread(target=_run_ws_server, daemon=True)
            self._thread.start()

            time.sleep(1.5)

            if self._handler.running:
                logger.info(f"[OK] WebSocket服务器已启动，监听 ws://{self._host}:{self._port}")
                return True
            else:
                logger.error("[ERR] WebSocket服务器启动失败")
                return False

        except Exception as e:
            logger.error(f"[ERR] 启动WebSocket服务器失败: {e}")
            logger.error(f"   堆栈: {traceback.format_exc()}")
            return False

    async def stop(self):
        """停止WebSocket服务器"""
        if self._handler:
            try:
                await self._handler.stop()
            except Exception:
                pass
