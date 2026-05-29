#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MT5 AI交易服务 - 企业级增强版 V3.0
提供 WebSocket/Socket/File/Auto 四种通信模式、完整监控系统、高性能架构
使用方法:
  python mt5_ai_service.py                      # 默认模式
  python mt5_ai_service.py --mode websocket     # 仅WebSocket模式
  python mt5_ai_service.py --mode socket        # 仅Socket模式
  python mt5_ai_service.py --mode file          # 仅File模式
  python mt5_ai_service.py --mode auto          # 自动模式(默认)
  python mt5_ai_service.py --log-file logs.log  # 同时输出到日志文件
"""

import sys
import time
import json
import signal
import argparse
import logging
import socket
import socketserver
import threading
import os
import asyncio
from datetime import datetime
from typing import Dict, Any, Optional, Union, Tuple
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

# 导入核心模块
from core.logger import setup_logger, logger, monitor
from core.cache import global_cache, tiered_cache
from core.ai_engine import AIAnalyzer
from core.weight_optimizer import get_weight_optimizer, ValidationStatus
from core.file_handler import file_handler
from core.validator import DataValidator, IndicatorAnalyzer, get_cache_key, get_fuzzy_cache_key, get_cache_keys_for_lookup
from core.http_client import get_http_client
from core.websocket_handler import WebSocketHandler, HAS_WEBSOCKETS
from core.web_dashboard import WebDashboard
from core.ha import get_service_registry, create_local_service_instance, ServiceStatus
from core.trading_recorder import get_trading_recorder
from core.mql5_data import get_mql5_data_manager
from core import config

try:
    from core.risk_manager import get_risk_manager, TradeRiskAssessment
    RISK_MANAGER_AVAILABLE = True
except ImportError as e:
    RISK_MANAGER_AVAILABLE = False
    logger.warning(f"[WARN]  风险管理器导入失败，将跳过风险评估: {e}")


# ==================== 全局状态 ====================
service_status = {
    "running": True,
    "current_mode": "auto",
    "socket_available": False,
    "last_mode_switch": None,
    "consecutive_failures": 0,
    "start_time": datetime.now()
}

mode_manager_instance = None


# ==================== Socket处理器 - 简化但高可靠版本 ====================
class AISocketHandler(socketserver.BaseRequestHandler):
    """AI Socket请求处理器 - 极度简化但高可靠版本"""
    
    def __init__(self, request, client_address, server):
        # 直接调用同模块函数，无需自引用导入
        self.ai_service = get_ai_service()
        super().__init__(request, client_address, server)
    
    def handle(self):
        """高可靠的请求处理"""
        client_ip = self.client_address[0]
        client_port = self.client_address[1]
        result = None
        start_time = time.time()
        
        try:
            self.request.settimeout(10.0)
            logger.info(f"📥 [Socket] 连接来自 {client_ip}:{client_port}")
            
            # 1. 接收数据
            raw_data = b''
            try:
                while True:
                    chunk = self.request.recv(4096)
                    if not chunk:
                        break
                    raw_data += chunk
                    if b'\n' in raw_data:
                        break
            except socket.timeout:
                pass
            
            if not raw_data:
                logger.warning("[WARN]  收到空数据")
                result = {"action": "HOLD", "confidence": 0.0, "reason": "空请求", "use_deepseek": False, "cached": False}
            else:
                # 2. 解码和清理
                data = raw_data.decode('utf-8', errors='ignore').strip()
                logger.info(f"[TEST] 收到原始数据 (hex): {raw_data.hex()}")
                logger.info(f"[TEST] 收到数据: {data[:200]}...")
                
                # 3. 测试消息和健康检查处理
                if "TEST" in data.upper():
                    logger.info("🧪 收到测试消息")
                    result = {"status": "ok", "message": "Server ready"}
                elif "HEALTHCHECK" in data.upper():
                    logger.info("🏥 收到健康检查请求")
                    # 返回完整的服务状态信息
                    result = {
                        "status": "ok",
                        "message": "Service health check",
                        "service_status": service_status,
                        "timestamp": datetime.now().isoformat(),
                        "socket_available": service_status.get("socket_available", False),
                        "current_mode": service_status.get("current_mode", "unknown"),
                        "uptime_seconds": (datetime.now() - service_status.get("start_time", datetime.now())).total_seconds() if "start_time" in service_status else 0
                    }
                else:
                    # 4. JSON解析
                    try:
                        json_start = data.find('{')
                        json_end = data.rfind('}')
                        if json_start >= 0 and json_end > json_start:
                            json_str = data[json_start:json_end+1]
                            request_data = json.loads(json_str)
                        else:
                            request_data = json.loads(data)
                        
                        # 5. 检查是否是 MQL5 数据更新请求
                        if "type" in request_data and request_data["type"] == "mql5_data":
                            logger.info("[DATA] 收到 MQL5 数据更新")
                            try:
                                mql5_manager = get_mql5_data_manager()
                                success = mql5_manager.update_from_json(request_data)
                                result = {
                                    "status": "ok" if success else "error",
                                    "message": "数据更新成功" if success else "数据更新失败"
                                }
                            except Exception as e:
                                logger.error(f"更新 MQL5 数据异常: {e}")
                                result = {"status": "error", "message": str(e)}
                        else:
                            # 6. 处理普通 AI 请求
                            logger.info(f"📥 处理请求: {request_data.get('symbol', 'UNKNOWN')}")
                            try:
                                result = self.ai_service.process_request(request_data)
                                if not result:
                                    result = {"action": "HOLD", "confidence": 0.0, "reason": "处理返回空", "use_deepseek": False, "cached": False}
                            except Exception as proc_e:
                                logger.warning(f"[WARN]  处理异常: {proc_e}")
                                result = {"action": "HOLD", "confidence": 0.0, "reason": f"处理异常: {str(proc_e)}", "use_deepseek": False, "cached": False}
                    
                    except json.JSONDecodeError as json_e:
                        logger.error(f"[ERR] JSON解析失败: {json_e}")
                        logger.error(f"   原始数据: {data[:200]}")
                        result = {"error": str(json_e), "action": "HOLD", "confidence": 0.0, "use_deepseek": False, "reason": "JSON解析失败", "cached": False}
            
            # 6. 确保结果有效
            if not result:
                result = {"action": "HOLD", "confidence": 0.0, "reason": "无结果", "use_deepseek": False, "cached": False}
            
            # 7. 发送响应
            response_str = json.dumps(result, ensure_ascii=False) + "\n"
            response_bytes = response_str.encode('utf-8')
            
            logger.info(f"📤 发送响应: {len(response_bytes)} 字节")
            self.request.sendall(response_bytes)
            logger.info(f"[OK] 响应发送成功")
            
            # 8. 记录结果
            action = result.get('action', 'UNKNOWN')
            conf = result.get('confidence', 0.0)
            elapsed = time.time() - start_time
            logger.info(f"📤 [Socket] 响应: {action} (置信度: {conf:.2f}, 用时: {elapsed:.3f}s)")
            
        except Exception as e:
            logger.error(f"[ERR] handle异常: {e}")
            import traceback
            logger.error(f"   堆栈: {traceback.format_exc()}")
            try:
                error_result = {"error": str(e), "action": "HOLD", "confidence": 0.0, "use_deepseek": False, "reason": "服务器内部错误", "cached": False}
                self.request.sendall((json.dumps(error_result, ensure_ascii=False) + "\n").encode('utf-8'))
            except:
                pass


class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    """支持多线程的TCP服务器"""
    allow_reuse_address = True
    daemon_threads = True
    request_queue_size = config.MAX_CONCURRENT_CONNECTIONS if hasattr(config, 'MAX_CONCURRENT_CONNECTIONS') else 10


# ==================== 主服务类 ====================
class MT5AITradingService:
    """MT5 AI交易服务 - V3.0 企业级增强版"""
    
    def __init__(self):
        self.running = False
        self.ai_analyzer = AIAnalyzer()
        self.validator = DataValidator()
        self.indicator_analyzer = IndicatorAnalyzer()
        self.last_status_print = time.time()
        self.status_print_interval = 60.0
        self.mode = "auto"
        self.socket_server = None
        self.socket_thread = None
        self.file_thread = None
        self.websocket_handler = None
        self.websocket_thread = None
        self.web_dashboard = None
        
        # 权重优化器
        self.weight_optimizer = get_weight_optimizer()
        
        # 高可用架构
        self.service_registry = get_service_registry()
        self.local_instance = create_local_service_instance(
            port=8000,
            websocket_port=8081,
            socket_port=8080
        )
        self.heartbeat_thread = None
        
        # 交易记录器 - 为PPO强化学习准备
        self.trading_recorder = get_trading_recorder()
        
        # 风险管理器（可选，依赖numpy/scipy）
        self.risk_manager = None
        if RISK_MANAGER_AVAILABLE:
            try:
                self.risk_manager = get_risk_manager()
                self.risk_manager.start()
                logger.info("[OK] 风险管理器已集成并启动")
            except Exception as e:
                logger.warning(f"[WARN]  风险管理器启动失败，将跳过风险评估: {e}")
        
        # 只有主线程可以注册信号处理器
        try:
            signal.signal(signal.SIGINT, self._signal_handler)
            signal.signal(signal.SIGTERM, self._signal_handler)
        except ValueError as e:
            if "signal only works in main thread" in str(e):
                logger.debug(f"[INFO] 非主线程，跳过信号处理器注册: {e}")
            else:
                raise
    
    def _signal_handler(self, signum, frame):
        logger.info("\n🔻 收到关闭信号，正在退出...")
        self.running = False
        self._cleanup()
        monitor.print_summary()
        logger.info("👋 再见！")
        sys.exit(0)
    
    def _cleanup(self):
        logger.info("🧹 正在清理资源...")
        # 停止风险管理器
        if self.risk_manager:
            try:
                self.risk_manager.stop()
                logger.info("🛑 风险管理器已停止")
            except Exception as e:
                logger.warning(f"[WARN]  风险管理器停止异常: {e}")
        # 清理高可用架构
        try:
            self.service_registry.unregister(self.local_instance.service_id)
            logger.info("👋 服务注销完成")
        except Exception as e:
            logger.warning(f"[WARN]  服务注销异常: {e}")
        
        try:
            self.service_registry.stop()
        except Exception as e:
            logger.warning(f"[WARN]  服务注册中心停止异常: {e}")
        
        try:
            file_handler.cleanup_health_check()
        except Exception:
            pass
        try:
            http_client = get_http_client()
            http_client.close()
        except Exception:
            pass
        if self.socket_server:
            try:
                self.socket_server.shutdown()
                self.socket_server.server_close()
            except Exception:
                pass
        if self.websocket_handler:
            try:
                asyncio.run(self.websocket_handler.stop())
            except Exception:
                pass
        logger.info("[OK] 清理完成")
    
    def _print_status(self, force: bool = False):
        now = time.time()
        if force or (now - self.last_status_print) >= self.status_print_interval:
            self.last_status_print = now
            stats = monitor.get_stats()
            
            status_msg = f"[UP] 状态: 请求={stats['total_requests']}"
            if stats['total_requests'] > 0:
                avg_ms = stats['average_response_time'] * 1000
                status_msg += f" | 平均={avg_ms:.0f}ms"
            
            cache_total = stats['cache_hits'] + stats['cache_misses']
            if cache_total > 0:
                hit_rate = stats['cache_hits'] / cache_total * 100
                status_msg += f" | 缓存={hit_rate:.0f}%"
            
            status_msg += f" | 模式={service_status['current_mode'].upper()}"
            logger.info(status_msg)
    
    def _update_trade_stats(self, trade_history: list):
        """更新交易统计"""
        if not trade_history:
            return
        
        # 统计变量
        total_trades = 0
        win_trades = 0
        loss_trades = 0
        total_profit = 0.0
        total_loss = 0.0
        buy_trades = 0
        sell_trades = 0
        sl_hits = 0  # 被止损次数
        tp_hits = 0  # 被止盈次数
        
        for trade in trade_history:
            if trade.get('entry') != 'OUT':  # 只统计平仓交易
                continue
            
            total_trades += 1
            profit = trade.get('profit', 0)
            trade_type = trade.get('type', '')
            sl = trade.get('sl', 0)
            tp = trade.get('tp', 0)
            price = trade.get('price', 0)
            comment = str(trade.get('comment', ''))
            
            # MT5平仓逻辑：OUT记录的deal_type是平仓方向，不是原始交易方向
            # - DEAL_TYPE_BUY OUT = 平空仓 → 原始交易是 SELL
            # - DEAL_TYPE_SELL OUT = 平多仓 → 原始交易是 BUY
            if trade_type == 'BUY':
                sell_trades += 1  # BUY OUT = 平空仓 = SELL开仓
            elif trade_type == 'SELL':
                buy_trades += 1   # SELL OUT = 平多仓 = BUY开仓
            
            if profit >= 0:
                win_trades += 1
                total_profit += profit
            else:
                loss_trades += 1
                total_loss += abs(profit)
                
                # 判断是否被止损
                if sl > 0:
                    sl_hits += 1
            
            # 判断是否被止盈
            if tp > 0:
                tp_hits += 1
        
        if total_trades > 0:
            win_rate = win_trades / total_trades * 100
            avg_win = total_profit / win_trades if win_trades > 0 else 0
            avg_loss = total_loss / loss_trades if loss_trades > 0 else 0
            profit_factor = total_profit / total_loss if total_loss > 0 else 0
            
            logger.info(f"[STATS] 交易统计 (最近{total_trades}笔):")
            logger.info(f"  总交易: {total_trades} | 盈利: {win_trades} | 亏损: {loss_trades} | 胜率: {win_rate:.1f}%")
            logger.info(f"  总盈利: ${total_profit:.2f} | 总亏损: ${total_loss:.2f} | 盈亏比: {profit_factor:.2f}")
            logger.info(f"  平均盈利: ${avg_win:.2f} | 平均亏损: ${avg_loss:.2f}")
            logger.info(f"  多单: {buy_trades} | 空单: {sell_trades}")
            
            # 存储统计结果供前端展示
            self._trade_stats = {
                'total_trades': total_trades,
                'win_trades': win_trades,
                'loss_trades': loss_trades,
                'win_rate': win_rate,
                'total_profit': total_profit,
                'total_loss': total_loss,
                'profit_factor': profit_factor,
                'avg_win': avg_win,
                'avg_loss': avg_loss,
                'buy_trades': buy_trades,
                'sell_trades': sell_trades,
                'sl_hits': sl_hits,
                'tp_hits': tp_hits
            }
            
            # 更新Dashboard显示
            if self.web_dashboard:
                self.web_dashboard.trade_stats = self._trade_stats.copy()
    
    def get_trade_stats(self) -> dict:
        """获取交易统计"""
        return getattr(self, '_trade_stats', {
            'total_trades': 0,
            'win_trades': 0,
            'loss_trades': 0,
            'win_rate': 0,
            'total_profit': 0,
            'total_loss': 0,
            'profit_factor': 0,
            'avg_win': 0,
            'avg_loss': 0,
            'buy_trades': 0,
            'sell_trades': 0,
            'sl_hits': 0,
            'tp_hits': 0
        })
    
    def _calculate_dynamic_sl_tp(self, symbol: str, action: str, confidence: float, 
                                  bid: float, ask: float, indicators: Optional[dict]) -> Tuple[int, int]:
        """
        动态计算止损止盈 pips 数
        
        ★ 单位约定（与EA端保持一致）：
            1 pip = 10 * _Point（MT5 黄金 _Point=0.01）
            即 1 pip = 0.10 美元
            30 pip = 3.00 美元，60 pip = 6.00 美元
        
        MT5 stops_level 通常 100-200 points = 10-20 pips
        → 止损最小值设 25 pips (2.50$)，避免 [invalid stops]
        
        基于以下因素调整：
        1. 市场波动率（ATR）
        2. 置信度
        3. 账户风险状态
        4. 品种特性（黄金vs外汇）
        
        返回: (stop_loss_pips, take_profit_pips)
        """
        # 基础止损止盈（外汇默认范围，单位: pips）
        base_sl = 30  # 30 pips = 3.00$ (外汇约30点)
        base_tp = 60  # 60 pips = 6.00$
        
        # 黄金/贵金属特殊处理（波动大，需要更宽止损）
        # 检测逻辑：XAU前缀、GOLD关键词、或以_结尾的MT5黄金品种（如GOLD_）
        sym_upper = symbol.upper()
        is_gold = (sym_upper.startswith("XAU") or 
                   "GOLD" in sym_upper or 
                   sym_upper.endswith("_"))  # MT5黄金品种惯例以_结尾
        if is_gold:
            # 黄金 stops_level 通常 100-300 points = 10-30 pips
            # 设 40 pips (4.00$) 确保超过最小距离
            base_sl = 40  # 40 pips = 4.00$
            base_tp = 80  # 80 pips = 8.00$，风险回报比 2:1
            logger.debug(f"[SL/TP] 黄金品种({symbol})，使用宽止损: SL={base_sl}pips(${base_sl*0.1:.1f}), TP={base_tp}pips(${base_tp*0.1:.1f})")
        
        # 从指标计算波动率
        volatility_multiplier = 1.0
        if indicators:
            # 使用RSI作为波动率参考
            rsi = indicators.get('rsi', 50)
            if rsi > 70 or rsi < 30:
                volatility_multiplier = 1.3  # 超买超卖区域波动大
            
            # 使用历史数据计算波动（ATR近似）
            history = indicators.get('recent_history', [])
            if len(history) >= 5:
                highs = [h.get('high', 0) for h in history]
                lows = [h.get('low', 0) for h in history]
                closes = [h.get('close', 0) for h in history]
                
                # 计算ATR近似（单位: 价格）
                true_ranges = []
                for i in range(1, len(closes)):
                    tr = max(
                        highs[i] - lows[i],
                        abs(highs[i] - closes[i-1]),
                        abs(lows[i] - closes[i-1])
                    )
                    true_ranges.append(tr)
                
                if true_ranges:
                    avg_atr = sum(true_ranges) / len(true_ranges)
                    # ATR单位：价格（如黄金3300价格，ATR=5.0表示5.00美元波动）
                    # 转换为pips：1 pip = 0.10$（MT5黄金_Point=0.01）
                    # ATR > 5.0$ = 50 pips → 高波动 → volatility_multiplier = 1.3
                    # ATR < 2.0$ = 20 pips → 低波动 → volatility_multiplier = 0.85
                    if avg_atr > 5.0:
                        volatility_multiplier = 1.3
                    elif avg_atr < 2.0:
                        volatility_multiplier = 0.85
        
        # 置信度调整（高置信度适当放宽止盈，低置信度收紧止损但保持盈亏比）
        if confidence < 0.65:
            # 边缘信号：大幅收紧SL和TP，保持最小1.5:1盈亏比
            sl_multiplier = 0.75
            tp_multiplier = 0.85  # 止盈也收紧，但盈亏比保持
        elif confidence < 0.70:
            # 偏弱信号：适度收紧
            sl_multiplier = 0.85
            tp_multiplier = 0.90
        elif confidence > 0.85:
            # 高置信度：适当放宽TP追求更大盈利
            sl_multiplier = 1.0
            tp_multiplier = 1.2
        else:
            # 中等置信度：标准倍数
            sl_multiplier = 1.0
            tp_multiplier = 1.0
        
        # 风险管理器调整
        risk_adjustment = 1.0
        if self.risk_manager:
            try:
                risk_level = self.risk_manager.risk_params.risk_level
                if hasattr(risk_level, 'value'):
                    if 'high' in risk_level.value.lower():
                        risk_adjustment = 0.7  # 高风险时收紧止损
                        logger.debug(f"[SL/TP] 高风险状态，止损收紧 x{risk_adjustment}")
                    elif 'low' in risk_level.value.lower():
                        risk_adjustment = 1.1  # 低风险时放宽
                        logger.debug(f"[SL/TP] 低风险状态，止损放宽 x{risk_adjustment}")
            except Exception as e:
                logger.debug(f"[SL/TP] 风险等级读取失败，使用默认倍数: {e}")
        
        # 计算最终止损止盈（分别使用SL和TP的调整系数）
        final_sl_multiplier = volatility_multiplier * sl_multiplier * risk_adjustment
        final_tp_multiplier = volatility_multiplier * tp_multiplier * risk_adjustment
        
        stop_loss_pips = int(base_sl * final_sl_multiplier)
        take_profit_pips = int(base_tp * final_tp_multiplier)
        
        # 确保风险回报比至少1.5:1
        if take_profit_pips < stop_loss_pips * 1.5:
            take_profit_pips = int(stop_loss_pips * 1.5)
        
        # 范围限制（单位: pips，1pip=0.10$）
        # SL最小25pips(2.50$)，确保超过MT5 stops_level(通常100-300 points=10-30pips)
        stop_loss_pips = max(25, min(150, stop_loss_pips))
        take_profit_pips = max(40, min(300, take_profit_pips))
        
        logger.debug(f"[SL/TP] 最终计算: SL={stop_loss_pips}pips(${stop_loss_pips*0.1:.1f}) "
                     f"TP={take_profit_pips}pips(${take_profit_pips*0.1:.1f}) "
                     f"SL乘数={final_sl_multiplier:.2f}, TP乘数={final_tp_multiplier:.2f}")
        
        return stop_loss_pips, take_profit_pips

    @staticmethod
    def _get_blocking_risk_reason(assessment) -> Optional[str]:
        """返回阻断交易的风险原因；无阻断风险则返回None。"""
        warnings = getattr(assessment, "warning_messages", None) or []
        blocking_keywords = (
            "保证金不足",
            "无法开仓",
            "保证金追缴",
            "立即平仓",
            "账户不允许",
            "交易被禁用",
            "风险评估失败",
            "margin insufficient",
            "not enough margin",
        )

        for warning in warnings:
            warning_text = str(warning)
            if any(keyword.lower() in warning_text.lower() for keyword in blocking_keywords):
                return warning_text

        position_size = getattr(assessment, "recommended_position_size", None)
        if position_size is not None and position_size <= 0:
            return "推荐仓位为0，禁止开仓"

        risk_reward_ratio = getattr(assessment, "risk_reward_ratio", None)
        if risk_reward_ratio is not None and risk_reward_ratio <= 0:
            return f"风险回报比{risk_reward_ratio:.2f}无效，禁止开仓"

        return None
    
    def analyze(self, symbol: str, bid: float, ask: float,
                current_time: float, history: Optional[list] = None,
                indicators: Optional[dict] = None,
                multi_timeframe: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        start_time = time.time()
        
        # 尝试多个缓存键（精确键 + 模糊键）
        cache_keys = get_cache_keys_for_lookup(symbol, bid, ask)
        cached_result = None
        used_cache_key = None
        
        for cache_key in cache_keys:
            cached = global_cache.get(cache_key)
            if cached:
                cached_result = cached
                used_cache_key = cache_key
                break
        
        if cached_result:
            is_exact_match = used_cache_key == cache_keys[0]  # 第一个键是精确键
            logger.info(f"💾 使用{'精确' if is_exact_match else '模糊'}缓存结果 (键: {used_cache_key})")
            monitor.record_cache_hit()
            return cached_result
        
        monitor.record_cache_miss()
        
        action = "HOLD"
        confidence = 0.5
        reason = ""
        
        # 用于存储动态止损止盈
        stop_loss_pips = None
        take_profit_pips = None
        
        if self.ai_analyzer.is_deepseek_available():
            prompt = self.ai_analyzer.build_prompt(symbol, bid, ask, current_time, history, indicators, multi_timeframe)
            ai_result = self.ai_analyzer.call_api(prompt)
            
            if ai_result:
                action = ai_result["action"]
                confidence = ai_result["confidence"]
                reason = ai_result["reason"]
                # 从AI结果中提取止损止盈
                stop_loss_pips = ai_result.get("stop_loss_pips")
                take_profit_pips = ai_result.get("take_profit_pips")
                action, confidence = self.indicator_analyzer.validate_and_adjust(
                    action, confidence, indicators, symbol, bid, ask
                )
                monitor.record_request(True, time.time() - start_time)
            else:
                logger.warning("[WARN]  AI分析失败，使用后备策略")
                action, confidence, reason = self.ai_analyzer.get_fallback_strategy(
                    symbol, bid, ask, indicators, multi_timeframe
                )
                monitor.record_request(True, time.time() - start_time)
        else:
            action, confidence, reason = self.ai_analyzer.get_fallback_strategy(
                symbol, bid, ask, indicators, multi_timeframe
            )
            monitor.record_request(True, time.time() - start_time)
        
        # 计算动态止损止盈（如果AI没有提供）
        if action in ['BUY', 'SELL'] and (stop_loss_pips is None or take_profit_pips is None):
            # 基于波动率计算
            sl, tp = self._calculate_dynamic_sl_tp(symbol, action, confidence, bid, ask, indicators)
            if stop_loss_pips is None:
                stop_loss_pips = sl
            if take_profit_pips is None:
                take_profit_pips = tp
        
        result = {
            "action": action,
            "confidence": confidence,
            "reason": reason,
            "symbol": symbol,
            "analysis_time": datetime.now().isoformat(),
            "use_deepseek": self.ai_analyzer.use_deepseek,
            "cached": False
        }
        
        # 添加动态止损止盈到结果（仅对交易信号）
        if action in ['BUY', 'SELL']:
            if stop_loss_pips is not None:
                result["stop_loss_pips"] = stop_loss_pips
            if take_profit_pips is not None:
                result["take_profit_pips"] = take_profit_pips
            logger.info(f"📊 动态止损止盈: SL={stop_loss_pips}点, TP={take_profit_pips}点")

        def downgrade_to_hold(downgrade_reason: str):
            result["original_action"] = result.get("action")
            result["original_confidence"] = result.get("confidence")
            result["original_reason"] = result.get("reason")
            result["action"] = "HOLD"
            result["confidence"] = 0.0
            result["reason"] = f"风险拦截: {downgrade_reason}"
            result["risk_downgrade_reason"] = downgrade_reason
            result.pop("stop_loss_pips", None)
            result.pop("take_profit_pips", None)
        
        # 风险评估：对交易信号进行多维度风险检查
        if action in ['BUY', 'SELL']:
            if not self.risk_manager:
                logger.warning("[RM] 风险管理器不可用，信号降级为HOLD")
                downgrade_to_hold("风险管理器不可用")
            else:
                try:
                    current_price = (bid + ask) / 2 if bid > 0 and ask > 0 else 0
                    if current_price <= 0:
                        logger.warning("[RM] 当前价格无效，信号降级为HOLD")
                        downgrade_to_hold("当前价格无效")
                    else:
                        # --- 多维度风险预检（不依赖assess_trade_risk） ---
                        spread = ask - bid if bid > 0 and ask > 0 else 0
                        spread_pct = (spread / current_price * 10000) if current_price > 0 else 0
                        
                        # 维度1: 点差异常检查（流动性不足）
                        if spread_pct > 50:  # 点差超过5个标准点
                            logger.warning(f"[RM]  点差异常({spread_pct:.1f}点)，流动性不足，信号降级为HOLD")
                            downgrade_to_hold(f"点差异常: {spread_pct:.1f}点，流动性不足")
                        else:
                            # 维度2: 完整风险评估
                            assessment = self.risk_manager.assess_trade_risk(
                                symbol=symbol,
                                action=action,
                                confidence=confidence,
                                current_price=current_price
                            )
                            # 将风险评估信息附加到结果中
                            result["risk_assessment"] = {
                                "risk_score": assessment.risk_score,
                                "risk_level": assessment.risk_level.value,
                                "recommended_position_size": assessment.recommended_position_size,
                                "recommended_stop_loss": assessment.recommended_stop_loss,
                                "recommended_take_profit": assessment.recommended_take_profit,
                                "risk_reward_ratio": assessment.risk_reward_ratio,
                                "warnings": assessment.warning_messages
                            }
                            
                            # 多维度降级逻辑
                            risk_reasons = []
                            blocking_risk_reason = self._get_blocking_risk_reason(assessment)
                            
                            # 维度2a: 风险评分过高
                            if assessment.risk_score >= 0.8:
                                risk_reasons.append(f"风险评分{assessment.risk_score:.2f}超过阈值0.8")
                            
                            # 维度2b: 风险回报比不足
                            if assessment.risk_reward_ratio < 1.0:
                                risk_reasons.append(f"风险回报比{assessment.risk_reward_ratio:.2f}低于1:1")
                            
                            # 维度2c: 置信度与风险评分不匹配
                            if confidence < 0.6 and assessment.risk_score > 0.5:
                                risk_reasons.append(f"低置信度({confidence:.2f})+高风险({assessment.risk_score:.2f})")
                            
                            # 根据风险原因数量决定处理方式
                            if blocking_risk_reason:
                                logger.warning(f"[RM]  阻断性风险触发({blocking_risk_reason})，信号降级为HOLD")
                                downgrade_to_hold(f"阻断性风险: {blocking_risk_reason}")
                            elif len(risk_reasons) >= 2:
                                logger.warning(f"[RM]  多维度风险触发(原因: {'; '.join(risk_reasons)})，信号降级为HOLD")
                                downgrade_to_hold(f"多维度风险: {'; '.join(risk_reasons)}")
                            elif assessment.risk_score >= 0.8:
                                logger.warning(f"[RM]  风险评分过高({assessment.risk_score:.2f})，信号降级为HOLD")
                                downgrade_to_hold(f"风险评分{assessment.risk_score:.2f}超过阈值0.8")
                            elif assessment.risk_score > 0.6:
                                logger.warning(f"[WARN]  风险评分偏高({assessment.risk_score:.2f})，保留信号但添加警告")
                                result["risk_warnings"] = risk_reasons
                except Exception as e:
                    logger.error(f"[RM] 风险评估异常，信号降级为HOLD: {e}")
                    downgrade_to_hold(f"风险评估异常: {str(e)[:120]}")
        
        # 存储到多个缓存键以提高命中率
        primary_cache_key = get_cache_key(symbol, bid, ask)  # 精确键
        global_cache.set(primary_cache_key, result)
        
        # 同时存储到主要模糊键（0.5点容忍度）
        fuzzy_cache_key = get_fuzzy_cache_key(symbol, bid, ask, tolerance_pips=0.5)
        if fuzzy_cache_key != primary_cache_key:
            global_cache.set(fuzzy_cache_key, result)
        
        logger.info(f"[AI] AI建议: {result.get('action', action)} | 置信度: {result.get('confidence', confidence):.2f}")
        if reason:
            logger.info(f"💭 分析原因: {reason[:80]}{'...' if len(reason) > 80 else ''}")
        
        return result
    
    def _heartbeat_loop(self):
        """心跳循环"""
        logger.info("[HEART] 心跳线程启动")
        while self.running:
            try:
                self.service_registry.heartbeat(self.local_instance.service_id)
                time.sleep(5)
            except Exception as e:
                logger.warning(f"[WARN]  心跳异常: {e}")
                time.sleep(1)
    
    def _monitor_account_data(self):
        """监控 MT5 账户数据文件"""
        logger.info("[DATA] 账户数据监控线程启动")
        
        # 可能的文件位置（优先使用 file_handler 找到的路径）
        possible_locations = []
        
        last_modified = 0
        
        while self.running:
            try:
                # 先尝试用 file_handler 的路径
                if file_handler._cached_path:
                    possible_locations.insert(0, file_handler._cached_path)
                
                # 添加常见 MT5 Files 目录
                common_paths = [
                    os.path.join(os.path.expanduser("~"), "AppData", "Roaming", "MetaQuotes", "Terminal", "*", "MQL5", "Files"),
                    os.path.join(os.path.expanduser("~"), "AppData", "Roaming", "MetaQuotes", "Terminal", "*", "Files"),
                ]
                
                account_file = None
                # 先检查 file_handler 的位置
                if file_handler._cached_path:
                    test_file = os.path.join(file_handler._cached_path, "mt5_account.json")
                    if os.path.exists(test_file):
                        account_file = test_file
                
                # 如果没找到，尝试其他常见位置
                if not account_file:
                    for path in common_paths:
                        import glob
                        matches = glob.glob(path)
                        for p in matches:
                            test_file = os.path.join(p, "mt5_account.json")
                            if os.path.exists(test_file):
                                account_file = test_file
                                break
                
                # 如果找到文件
                if account_file:
                    mtime = os.path.getmtime(account_file)
                    if mtime > last_modified:
                        last_modified = mtime
                        try:
                            with open(account_file, 'r', encoding='utf-8') as f:
                                content = f.read().strip()
                            
                            if content:
                                data = json.loads(content)
                                if data.get("type") == "mql5_data":
                                    mql5_manager = get_mql5_data_manager()
                                    success = mql5_manager.update_from_json(data)
                                    if success:
                                        logger.debug(f"[OK] 账户数据已更新")
                        except Exception as e:
                            logger.debug(f"[DATA] 读取账户数据异常: {e}")
                
                time.sleep(1)
            except Exception as e:
                logger.debug(f"[WARN]  账户数据监控异常: {e}")
                time.sleep(1)
    
    def process_request(self, request_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        try:
            # 高可用架构统计
            self.local_instance.increment_requests()

            if not isinstance(request_data, dict):
                raise ValueError("请求数据必须是JSON对象")

            if request_data.get("type") == "mql5_data":
                mql5_manager = get_mql5_data_manager()
                success = mql5_manager.update_from_json(request_data)
                return {
                    "status": "ok" if success else "error",
                    "action": "HOLD",
                    "confidence": 0.0,
                    "reason": "MQL5数据更新" if success else "MQL5数据更新失败",
                    "use_deepseek": False,
                    "cached": False
                }
            
            validated_request = dict(request_data)
            try:
                validated_request["bid"] = float(validated_request.get("bid"))
                validated_request["ask"] = float(validated_request.get("ask"))
                validated_request["time"] = float(validated_request.get("time", int(time.time())))
                self.validator.validate_request(validated_request)
            except Exception as validation_error:
                logger.warning(f"[SAFE] 请求校验失败，返回HOLD: {validation_error}")
                return {
                    "action": "HOLD",
                    "confidence": 0.0,
                    "reason": f"请求校验失败: {validation_error}",
                    "symbol": str(request_data.get("symbol", "UNKNOWN")),
                    "analysis_time": datetime.now().isoformat(),
                    "use_deepseek": False,
                    "cached": False
                }

            symbol = validated_request["symbol"].strip()
            bid = validated_request["bid"]
            ask = validated_request["ask"]
            current_time = validated_request["time"]
            history = request_data.get("history")
            indicators = request_data.get("indicators")
            multi_timeframe = request_data.get("multi_timeframe")
            account_data = request_data.get("account_data")  # 从请求中获取账户数据
            trade_history = request_data.get("trade_history", [])  # 交易历史数据
            
            # 更新MQL5数据管理器中的账户信息
            if isinstance(account_data, dict):
                mql5_manager = get_mql5_data_manager()
                balance = account_data.get("balance", 0.0)
                equity = account_data.get("equity", 0.0)
                margin_free = account_data.get("margin_free", 0.0)
                margin = account_data.get("margin", 0.0)
                margin_level = account_data.get("margin_level", 0.0)
                if margin <= 0 and (margin_free > 0 or equity > 0) and margin_level <= 0:
                    margin_level = 1000.0

                mql5_manager.account_info.balance = balance
                mql5_manager.account_info.equity = equity
                mql5_manager.account_info.margin_free = margin_free
                mql5_manager.account_info.margin = margin
                mql5_manager.account_info.margin_level = margin_level
                mql5_manager.account_info.profit = account_data.get("profit", 0.0)
                logger.debug(f"[DATA] 账户数据已更新: 净值={account_data.get('equity', 0):.2f}")
            
            # 更新交易历史数据并统计准确率
            if isinstance(trade_history, list) and trade_history:
                self._update_trade_stats(trade_history)
            
            logger.info(f"📥 收到请求: {symbol} Bid={bid} Ask={ask}")
            result = self.analyze(symbol, bid, ask, current_time, history, indicators, multi_timeframe)
            
            # Add to dashboard
            if result and self.web_dashboard:
                self.web_dashboard.add_signal(result)
                self.web_dashboard.record_request(True)
            
            # 记录AI分析 - 为PPO强化学习准备
            if result:
                action = result.get('action', 'HOLD')
                confidence = result.get('confidence', 0)
                
                self.trading_recorder.record_analysis(
                    symbol=symbol,
                    bid=bid,
                    ask=ask,
                    action=action,
                    confidence=confidence,
                    reason=result.get('reason', ''),
                    use_deepseek=result.get('use_deepseek', False),
                    cached=result.get('cached', False),
                    indicators=indicators,
                    history=history
                )
                
                # 如果是交易信号，记录开仓信息（等待实盘平仓后更新）
                if action in ['BUY', 'SELL'] and confidence > 0.5:
                    entry_price = ask if action == 'BUY' else bid
                    
                    trade_data = {
                        'symbol': symbol,
                        'action': action,
                        'entry_price': entry_price,
                        'exit_price': None,  # 等待实盘平仓后填入
                        'pnl': None,          # 等待实盘平仓后计算
                        'status': 'open',     # 标记为待平仓状态
                        'confidence': confidence,
                        'timestamp': datetime.now().isoformat()
                    }
                    
                    if self.web_dashboard:
                        self.web_dashboard.add_trade(trade_data)
                    
                    logger.info(f"[LOG] 记录开仓信号: {action} {symbol} @ {entry_price:.5f}")
            
            return result
        
        except Exception as e:
            logger.error(f"[ERR] 处理请求失败: {e}")
            import traceback
            logger.error(f"   堆栈: {traceback.format_exc()}")
            monitor.record_request(False, 0)
            if self.web_dashboard:
                self.web_dashboard.record_request(False)
            return {
                "action": "HOLD",
                "confidence": 0.0,
                "reason": f"处理请求异常: {str(e)}",
                "analysis_time": datetime.now().isoformat(),
                "use_deepseek": False,
                "cached": False
            }
    
    def get_weight_optimizer_status(self) -> Dict[str, Any]:
        """获取权重优化器状态"""
        return self.weight_optimizer.get_performance_report()
    
    def trigger_weight_adjustment(self, reason: str = "manual") -> bool:
        """手动触发权重调整"""
        return self.weight_optimizer.adjust_weights(reason)
    
    def _start_socket_mode(self):
        logger.info(f"🔌 启动Socket服务器 ({config.SOCKET_HOST}:{config.SOCKET_PORT})...")
        
        try:
            # 创建服务器实例
            self.socket_server = ThreadedTCPServer((config.SOCKET_HOST, config.SOCKET_PORT), AISocketHandler)
            
            # 设置服务器超时，防止阻塞
            self.socket_server.timeout = 1
            
            # 启动服务器线程
            self.socket_thread = threading.Thread(target=self._run_socket_server)
            self.socket_thread.daemon = True
            self.socket_thread.start()
            
            service_status["socket_available"] = True
            logger.info(f"[OK] Socket服务器已启动，监听 {config.SOCKET_HOST}:{config.SOCKET_PORT}")
            
        except Exception as e:
            logger.error(f"[ERR] 启动Socket服务器失败: {e}")
            service_status["socket_available"] = False
            raise
    
    def _run_socket_server(self):
        """运行Socket服务器的主循环"""
        try:
            # 使用serve_forever，但设置poll_interval以便可以检查running状态
            while self.running:
                try:
                    self.socket_server.handle_request()
                except Exception as e:
                    logger.debug(f"[DEBUG] Socket请求处理异常: {e}")
                    time.sleep(0.1)
        except Exception as e:
            logger.error(f"[ERR] Socket服务器运行异常: {e}")
        finally:
            if self.socket_server:
                try:
                    self.socket_server.server_close()
                except:
                    pass
    
    def _start_websocket_mode(self) -> bool:
        logger.info(f"-> 启动WebSocket服务器 ({config.SOCKET_HOST}:{config.SOCKET_PORT+1})...")
        
        try:
            if not HAS_WEBSOCKETS:
                raise ImportError("websockets library not installed")
            
            self.websocket_handler = WebSocketHandler(
                host=config.SOCKET_HOST,
                port=config.SOCKET_PORT + 1,
                process_request_func=self.process_request
            )
            
            def run_websocket_server():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                async def run():
                    started = await self.websocket_handler.start()
                    if not started:
                        return
                    
                    while self.running and self.websocket_handler.running:
                        await asyncio.sleep(0.1)
                
                loop.run_until_complete(run())
            
            self.websocket_thread = threading.Thread(target=run_websocket_server)
            self.websocket_thread.daemon = True
            self.websocket_thread.start()
            
            time.sleep(1.5)
            
            if self.websocket_handler.running:
                logger.info(f"[OK] WebSocket服务器已启动，监听 ws://{config.SOCKET_HOST}:{config.SOCKET_PORT+1}")
                return True
            else:
                logger.error("[ERR] WebSocket服务器启动失败")
                return False
            
        except Exception as e:
            logger.error(f"[ERR] 启动WebSocket服务器失败: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def _run_file_mode(self):
        logger.info("[DIR] 启动文件模式处理器...")
        
        while self.running:
            try:
                file_handler.update_health_check()
                mt5_path = file_handler.find_request_file()
                if mt5_path is None:
                    time.sleep(0.05)
                    continue
                
                logger.info(f"[DIR] 找到请求文件，路径: {mt5_path}")
                
                request_file = Path(mt5_path) / "ai_request.json"
                content = file_handler.safe_read(str(request_file))
                
                if not content:
                    logger.info(f"[WARN]  请求文件内容为空")
                    time.sleep(0.05)
                    continue
                
                logger.info(f"📥 收到请求文件内容: {content[:200]}...")
                
                try:
                    request_data = json.loads(content)
                    response_data = self.process_request(request_data)
                    if response_data:
                        logger.info(f"📤 准备写入响应文件，路径: {mt5_path}")
                        logger.info(f"📤 响应内容: {json.dumps(response_data, ensure_ascii=False)[:200]}...")
                        
                        result = file_handler.write_response(response_data, mt5_path)
                        
                        if result:
                            logger.info(f"[OK] 响应文件写入成功")
                        else:
                            logger.error(f"[ERR] 响应文件写入失败")
                
                except json.JSONDecodeError as e:
                    logger.error(f"[ERR] JSON解析失败: {e}")
                except Exception as e:
                    logger.error(f"[ERR] 处理请求异常: {e}")
                finally:
                    time.sleep(0.01)
            
            except Exception as e:
                logger.error(f"[ERR] 文件模式循环错误: {e}")
                time.sleep(0.1)
    
    def run(self, mode: str = "auto"):
        self.running = True
        self.mode = mode
        service_status["current_mode"] = mode
        service_status["start_time"] = datetime.now()
        
        # 启动高可用架构
        self.service_registry.start()
        self.service_registry.register(self.local_instance)
        logger.info(f"[OK] 高可用架构启动，服务ID: {self.local_instance.service_id}")
        
        # 启动心跳线程
        self.heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self.heartbeat_thread.start()
        
        # 启动账户数据监控线程
        self.account_monitor_thread = threading.Thread(target=self._monitor_account_data, daemon=True)
        self.account_monitor_thread.start()
        logger.info("[OK] 账户数据监控线程启动")
        
        print("\n" + "="*70)
        print("[TARGET] MT5 AI交易系统 - 企业级增强版 V3.0")
        print("="*70)
        print()
        print("[DATA] 配置信息:")
        print(f"  - 通信模式: {mode.upper()}")
        deepseek_status = self.ai_analyzer.get_deepseek_status()
        deepseek_prefix = "[OK]" if deepseek_status == "启用" else "[ERR]"
        print(f"  - DeepSeek: {deepseek_prefix} {deepseek_status}")
        print(f"  - 缓存大小: {config.CACHE_SIZE}")
        print(f"  - 置信度阈值: {config.MIN_CONFIDENCE}")
        print(f"  - 请求超时: {config.REQUEST_TIMEOUT}s")
        print(f"  - 服务ID: {self.local_instance.service_id}")
        
        if mode in ["websocket", "auto"]:
            print(f"  - WebSocket地址: ws://{config.SOCKET_HOST}:{config.SOCKET_PORT+1}")
        if mode in ["socket", "auto"]:
            print(f"  - Socket地址: {config.SOCKET_HOST}:{config.SOCKET_PORT}")
        
        print(f"  - Web Dashboard: http://127.0.0.1:8000")
        print()
        print("-> 服务已启动，等待请求...")
        print("="*70)
        print()
        
        # Start web dashboard
        self.web_dashboard = WebDashboard(host="127.0.0.1", port=8000)
        self.web_dashboard.start()
        
        self._print_status(force=True)
        
        try:
            # File模式：只运行文件
            if mode == "file":
                self._run_file_mode()
            
            # Socket模式：只运行Socket
            elif mode == "socket":
                self._start_socket_mode()
                while self.running:
                    self._print_status()
                    time.sleep(0.1)
            
            # WebSocket模式：只运行WebSocket
            elif mode == "websocket":
                if not self._start_websocket_mode():
                    raise RuntimeError("WebSocket服务器启动失败")
                while self.running:
                    self._print_status()
                    time.sleep(0.1)
            
            # Auto模式：同时运行WebSocket/Socket和文件模式！
            else:
                websocket_running = False
                try:
                    websocket_running = self._start_websocket_mode()
                    if websocket_running:
                        logger.info("[OK] WebSocket模式启动成功")
                    else:
                        logger.warning("[WARN]  WebSocket模式未启动，继续使用Socket/文件模式")
                except Exception as e:
                    logger.warning(f"[WARN]  WebSocket模式启动失败: {e}")
                
                socket_running = False
                try:
                    self._start_socket_mode()
                    socket_running = True
                    logger.info("[OK] Socket模式启动成功")
                except Exception as e:
                    logger.warning(f"[WARN]  Socket模式启动失败: {e}")
                
                # 同时运行文件模式（主线程）
                self._run_file_mode()
        
        except KeyboardInterrupt:
            logger.info("\n👋 用户中断，正在退出...")
            monitor.print_summary()
        finally:
            self._cleanup()


# ==================== 全局函数 ====================
_ai_service_instance = None

def get_ai_service() -> MT5AITradingService:
    global _ai_service_instance
    if _ai_service_instance is None:
        _ai_service_instance = MT5AITradingService()
    return _ai_service_instance


def main():
    parser = argparse.ArgumentParser(description="MT5 AI交易服务 - 企业级增强版 V3.0")
    parser.add_argument('--mode', type=str, default='auto', choices=['websocket', 'socket', 'file', 'auto'],
                        help='通信模式 (websocket/socket/file/auto，默认: auto)')
    parser.add_argument('--log-file', type=str, help='日志文件路径 (可选)')
    parser.add_argument('--verbose', '-v', action='store_true', help='详细日志模式')
    args = parser.parse_args()
    
    log_level = logging.DEBUG if args.verbose else logging.INFO
    global logger
    logger = setup_logger(log_file=args.log_file, level=log_level)
    
    try:
        if hasattr(config, 'config'):
            # core/config.py 使用实例模式，配置已在导入时自动加载
            logger.info("[OK] 配置已通过模块导入自动加载")
        elif not hasattr(config, 'config_loaded'):
            # 根目录 config.py 使用类变量模式，需要手动加载
            if hasattr(config, 'load_environment'):
                config.load_environment()
            if hasattr(config, 'validate'):
                config.validate()
    except Exception as e:
        logger.error(f"[ERR] 配置加载失败: {e}")
        sys.exit(1)
    
    global _ai_service_instance
    _ai_service_instance = MT5AITradingService()
    _ai_service_instance.run(mode=args.mode)


if __name__ == "__main__":
    main()
