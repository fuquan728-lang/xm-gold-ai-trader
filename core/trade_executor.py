#!/usr/bin/env python3
"""
科学智能交易系统 - 自动化交易执行模块
支持多交易平台接口对接和订单管理
"""

import json
import time
import threading
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from enum import Enum
from abc import ABC, abstractmethod
import queue

from core.logger import logger
from core.datastore import get_datastore
from core.risk_manager import get_risk_manager, TradeRiskAssessment


class TradingPlatform(Enum):
    """交易平台"""
    MT5 = "mt5"
    OANDA = "oanda"
    IBKR = "ibkr"  # Interactive Brokers
    ALPACA = "alpaca"
    BINANCE = "binance"


class OrderType(Enum):
    """订单类型"""
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"
    TRAILING_STOP = "trailing_stop"


class OrderStatus(Enum):
    """订单状态"""
    PENDING = "pending"
    SUBMITTED = "submitted"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    EXPIRED = "expired"


@dataclass
class Order:
    """订单数据结构"""
    order_id: str
    symbol: str
    order_type: OrderType
    action: str  # "BUY" or "SELL"
    quantity: float
    price: Optional[float] = None
    stop_price: Optional[float] = None
    limit_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    status: OrderStatus = OrderStatus.PENDING
    created_time: float = 0
    filled_time: Optional[float] = None
    filled_price: Optional[float] = None
    filled_quantity: float = 0
    commission: float = 0
    platform: TradingPlatform = TradingPlatform.MT5
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
        if self.created_time == 0:
            self.created_time = time.time()


@dataclass
class Position:
    """持仓数据结构"""
    position_id: str
    symbol: str
    action: str  # "BUY" or "SELL"
    quantity: float
    entry_price: float
    current_price: float
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    unrealized_pnl: float = 0
    realized_pnl: float = 0
    opened_time: float = 0
    platform: TradingPlatform = TradingPlatform.MT5
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
        if self.opened_time == 0:
            self.opened_time = time.time()
        
        # 计算未实现盈亏
        self._update_unrealized_pnl()
    
    def _update_unrealized_pnl(self):
        """更新未实现盈亏"""
        price_diff = self.current_price - self.entry_price
        if self.action == "SELL":
            price_diff = -price_diff
        
        # 简化计算：假设标准手
        self.unrealized_pnl = price_diff * self.quantity * 100000
    
    def update_price(self, current_price: float):
        """更新当前价格"""
        self.current_price = current_price
        self._update_unrealized_pnl()


class TradingInterface(ABC):
    """交易接口抽象基类"""
    
    @abstractmethod
    def connect(self) -> bool:
        """连接到交易平台"""
        pass
    
    @abstractmethod
    def disconnect(self):
        """断开连接"""
        pass
    
    @abstractmethod
    def place_order(self, order: Order) -> str:
        """下单"""
        pass
    
    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        """取消订单"""
        pass
    
    @abstractmethod
    def modify_order(self, order_id: str, **kwargs) -> bool:
        """修改订单"""
        pass
    
    @abstractmethod
    def get_order_status(self, order_id: str) -> Optional[Order]:
        """获取订单状态"""
        pass
    
    @abstractmethod
    def get_positions(self) -> List[Position]:
        """获取持仓列表"""
        pass
    
    @abstractmethod
    def close_position(self, position_id: str, quantity: Optional[float] = None) -> bool:
        """平仓"""
        pass
    
    @abstractmethod
    def get_account_info(self) -> Dict[str, Any]:
        """获取账户信息"""
        pass
    
    @abstractmethod
    def get_market_price(self, symbol: str) -> Optional[float]:
        """获取市场价格"""
        pass


class MT5TradingInterface(TradingInterface):
    """MT5交易接口"""
    
    def __init__(self):
        self.connected = False
        self.orders: Dict[str, Order] = {}
        self.positions: Dict[str, Position] = {}
        
        # 使用文件通信与MT5 EA交互
        self.file_handler = None  # 将使用现有的file_handler
        
        logger.info("MT5交易接口初始化完成")
    
    def connect(self) -> bool:
        """连接到MT5平台"""
        try:
            # 这里简化实现，实际应检查MT5终端连接状态
            # 使用现有的文件通信机制
            
            # 导入现有的file_handler
            from core.file_handler import file_handler
            
            self.file_handler = file_handler
            self.connected = True
            
            logger.info("[OK] MT5交易接口连接成功")
            return True
            
        except Exception as e:
            logger.error(f"[ERR] MT5连接失败: {e}")
            self.connected = False
            return False
    
    def disconnect(self):
        """断开MT5连接"""
        self.connected = False
        logger.info("MT5交易接口已断开")
    
    def place_order(self, order: Order) -> str:
        """通过MT5下单"""
        if not self.connected:
            logger.error("[ERR] MT5未连接，无法下单")
            return ""
        
        try:
            # 生成订单ID
            order_id = f"MT5_{int(time.time() * 1000)}_{order.symbol}"
            order.order_id = order_id
            order.status = OrderStatus.SUBMITTED
            
            # 构建订单指令
            order_instruction = {
                "type": "place_order",
                "order_id": order_id,
                "symbol": order.symbol,
                "action": order.action,
                "quantity": order.quantity,
                "price": order.price,
                "stop_loss": order.stop_loss,
                "take_profit": order.take_profit,
                "order_type": order.order_type.value,
                "timestamp": time.time()
            }
            
            # 通过文件通信发送指令给MT5 EA
            # 这里简化实现，实际应使用文件或Socket通信
            
            # 模拟订单执行
            logger.info(f"📤 MT5下单指令: {order.symbol} {order.action} {order.quantity}手")
            
            # 模拟订单填充
            time.sleep(0.1)  # 模拟网络延迟
            
            order.status = OrderStatus.FILLED
            order.filled_time = time.time()
            order.filled_price = order.price or self.get_market_price(order.symbol)
            order.filled_quantity = order.quantity
            
            # 记录订单
            self.orders[order_id] = order
            
            # 如果是市价单，创建持仓
            if order.order_type == OrderType.MARKET and order.status == OrderStatus.FILLED:
                position_id = f"POS_{order_id}"
                position = Position(
                    position_id=position_id,
                    symbol=order.symbol,
                    action=order.action,
                    quantity=order.quantity,
                    entry_price=order.filled_price,
                    current_price=order.filled_price,
                    stop_loss=order.stop_loss,
                    take_profit=order.take_profit,
                    platform=TradingPlatform.MT5
                )
                self.positions[position_id] = position
            
            logger.info(f"[OK] MT5订单执行完成: {order_id}, 价格: {order.filled_price}")
            
            return order_id
            
        except Exception as e:
            logger.error(f"[ERR] MT5下单失败: {e}")
            order.status = OrderStatus.REJECTED
            return ""
    
    def cancel_order(self, order_id: str) -> bool:
        """取消MT5订单"""
        if order_id not in self.orders:
            logger.warning(f"[WARN]  订单不存在: {order_id}")
            return False
        
        try:
            order = self.orders[order_id]
            
            # 只能取消待处理或已提交的订单
            if order.status not in [OrderStatus.PENDING, OrderStatus.SUBMITTED]:
                logger.warning(f"[WARN]  订单状态不可取消: {order.status.value}")
                return False
            
            # 发送取消指令
            cancel_instruction = {
                "type": "cancel_order",
                "order_id": order_id,
                "timestamp": time.time()
            }
            
            logger.info(f"📤 MT5取消订单指令: {order_id}")
            
            # 模拟取消成功
            order.status = OrderStatus.CANCELLED
            
            logger.info(f"[OK] MT5订单取消成功: {order_id}")
            return True
            
        except Exception as e:
            logger.error(f"[ERR] MT5取消订单失败: {e}")
            return False
    
    def modify_order(self, order_id: str, **kwargs) -> bool:
        """修改MT5订单"""
        if order_id not in self.orders:
            logger.warning(f"[WARN]  订单不存在: {order_id}")
            return False
        
        try:
            order = self.orders[order_id]
            
            # 只能修改待处理或已提交的订单
            if order.status not in [OrderStatus.PENDING, OrderStatus.SUBMITTED]:
                logger.warning(f"[WARN]  订单状态不可修改: {order.status.value}")
                return False
            
            # 更新订单参数
            for key, value in kwargs.items():
                if hasattr(order, key):
                    setattr(order, key, value)
            
            # 发送修改指令
            modify_instruction = {
                "type": "modify_order",
                "order_id": order_id,
                "updates": kwargs,
                "timestamp": time.time()
            }
            
            logger.info(f"📤 MT5修改订单指令: {order_id}, 更新: {kwargs}")
            
            # 模拟修改成功
            logger.info(f"[OK] MT5订单修改成功: {order_id}")
            return True
            
        except Exception as e:
            logger.error(f"[ERR] MT5修改订单失败: {e}")
            return False
    
    def get_order_status(self, order_id: str) -> Optional[Order]:
        """获取MT5订单状态"""
        return self.orders.get(order_id)
    
    def get_positions(self) -> List[Position]:
        """获取MT5持仓列表"""
        return list(self.positions.values())
    
    def close_position(self, position_id: str, quantity: Optional[float] = None) -> bool:
        """平MT5仓位"""
        if position_id not in self.positions:
            logger.warning(f"[WARN]  持仓不存在: {position_id}")
            return False
        
        try:
            position = self.positions[position_id]
            
            close_quantity = quantity or position.quantity
            
            # 构建平仓指令
            close_instruction = {
                "type": "close_position",
                "position_id": position_id,
                "symbol": position.symbol,
                "action": "SELL" if position.action == "BUY" else "BUY",
                "quantity": close_quantity,
                "timestamp": time.time()
            }
            
            logger.info(f"📤 MT5平仓指令: {position.symbol} {close_quantity}手")
            
            # 模拟平仓执行
            if close_quantity >= position.quantity:
                # 完全平仓
                del self.positions[position_id]
                logger.info(f"[OK] MT5完全平仓: {position_id}")
            else:
                # 部分平仓
                position.quantity -= close_quantity
                logger.info(f"[OK] MT5部分平仓: {position_id}, 剩余仓位: {position.quantity}")
            
            return True
            
        except Exception as e:
            logger.error(f"[ERR] MT5平仓失败: {e}")
            return False
    
    def get_account_info(self) -> Dict[str, Any]:
        """获取MT5账户信息"""
        try:
            # 简化实现，返回模拟数据
            # 实际应从MT5终端获取真实数据
            
            account_info = {
                "balance": 10000.0,
                "equity": 10250.0,
                "margin": 250.0,
                "free_margin": 10000.0,
                "margin_level": 4100.0,
                "profit": 250.0,
                "currency": "USD",
                "leverage": 100,
                "account_number": "123456",
                "server": "XMGlobal-MT5"
            }
            
            return account_info
            
        except Exception as e:
            logger.error(f"[ERR] 获取MT5账户信息失败: {e}")
            return {}
    
    def get_market_price(self, symbol: str) -> Optional[float]:
        """获取MT5市场价格"""
        try:
            # 简化实现，返回模拟价格
            # 实际应从MT5终端获取实时报价
            
            price_map = {
                "EURUSD": 1.0850,
                "GBPUSD": 1.2650,
                "USDJPY": 151.50,
                "GOLD": 2350.0,
                "XAUUSD": 2350.0
            }
            
            return price_map.get(symbol, 0.0)
            
        except Exception as e:
            logger.error(f"[ERR] 获取MT5市场价格失败: {e}")
            return None


class TradeExecutor:
    """交易执行管理器"""
    
    def __init__(self, platform: TradingPlatform = TradingPlatform.MT5):
        self.platform = platform
        self.trading_interface: Optional[TradingInterface] = None
        self.datastore = get_datastore()
        self.risk_manager = get_risk_manager()
        
        # 初始化交易接口
        self._init_trading_interface()
        
        # 订单队列
        self.order_queue = queue.Queue()
        
        # 运行状态
        self.running = False
        self.execution_thread: Optional[threading.Thread] = None
        
        logger.info(f"-> 交易执行管理器初始化完成，平台: {platform.value}")
    
    def _init_trading_interface(self):
        """初始化交易接口"""
        if self.platform == TradingPlatform.MT5:
            self.trading_interface = MT5TradingInterface()
        else:
            # 未来可以添加其他平台接口
            logger.error(f"[ERR] 不支持的交易平台: {self.platform.value}")
            self.trading_interface = None
    
    def start(self):
        """启动交易执行器"""
        if self.running:
            logger.warning("[WARN]  交易执行器已在运行中")
            return
        
        # 连接交易平台
        if not self.trading_interface or not self.trading_interface.connect():
            logger.error("[ERR] 无法连接到交易平台")
            return
        
        self.running = True
        self.execution_thread = threading.Thread(target=self._execution_loop, daemon=True)
        self.execution_thread.start()
        logger.info("-> 交易执行器已启动")
    
    def stop(self):
        """停止交易执行器"""
        self.running = False
        
        # 断开交易平台连接
        if self.trading_interface:
            self.trading_interface.disconnect()
        
        if self.execution_thread:
            self.execution_thread.join(timeout=10)
        
        logger.info("🛑 交易执行器已停止")
    
    def _execution_loop(self):
        """交易执行循环"""
        logger.info("[REFRESH] 交易执行循环开始")
        
        while self.running:
            try:
                # 处理订单队列
                self._process_order_queue()
                
                # 监控持仓和风险
                self._monitor_positions()
                
                # 更新账户信息
                self._update_account_info()
                
                time.sleep(1)  # 每秒检查一次
                
            except Exception as e:
                logger.error(f"[ERR] 交易执行循环异常: {e}")
                time.sleep(5)
    
    def _process_order_queue(self):
        """处理订单队列"""
        try:
            # 处理最多10个订单
            for _ in range(min(10, self.order_queue.qsize())):
                try:
                    order_data = self.order_queue.get_nowait()
                    self._execute_order(order_data)
                    self.order_queue.task_done()
                except queue.Empty:
                    break
                except Exception as e:
                    logger.error(f"[ERR] 处理订单失败: {e}")
        except Exception as e:
            logger.error(f"[ERR] 处理订单队列失败: {e}")
    
    def _execute_order(self, order_data: Dict[str, Any]):
        """执行单个订单"""
        try:
            symbol = order_data.get("symbol", "")
            action = order_data.get("action", "")
            confidence = order_data.get("confidence", 0.5)
            
            if not symbol or not action:
                logger.warning("[WARN]  订单数据缺少必要字段")
                return
            
            # 获取当前价格
            current_price = self.trading_interface.get_market_price(symbol)
            if not current_price:
                logger.error(f"[ERR] 无法获取{symbol}的价格")
                return
            
            # 进行风险评估
            risk_assessment = self.risk_manager.assess_trade_risk(
                symbol=symbol,
                action=action,
                confidence=confidence,
                current_price=current_price
            )
            
            # 检查是否可以开仓
            can_open = self.risk_manager.can_open_position(
                symbol, risk_assessment.recommended_position_size
            )
            
            if not can_open:
                logger.warning(f"[WARN]  风险检查未通过，取消{symbol}订单")
                return
            
            # 创建订单
            order = Order(
                order_id="",  # 将由接口生成
                symbol=symbol,
                order_type=OrderType.MARKET,
                action=action,
                quantity=risk_assessment.recommended_position_size,
                price=current_price,
                stop_loss=risk_assessment.recommended_stop_loss,
                take_profit=risk_assessment.recommended_take_profit,
                platform=self.platform
            )
            
            # 执行订单
            order_id = self.trading_interface.place_order(order)
            
            if order_id:
                logger.info(f"[OK] 订单执行成功: {order_id}")
                
                # 记录交易
                trade_id = self.datastore.record_trade(
                    symbol=symbol,
                    action=action,
                    entry_price=current_price,
                    position_size=risk_assessment.recommended_position_size,
                    stop_loss=risk_assessment.recommended_stop_loss,
                    take_profit=risk_assessment.recommended_take_profit
                )
                
                # 更新风险评估信息
                order.metadata["risk_assessment"] = {
                    "risk_score": risk_assessment.risk_score,
                    "risk_level": risk_assessment.risk_level.value,
                    "risk_reward_ratio": risk_assessment.risk_reward_ratio,
                    "expected_value": risk_assessment.expected_value
                }
                
                logger.info(f"[LOG] 交易记录已保存 [ID: {trade_id}]")
                
            else:
                logger.error(f"[ERR] 订单执行失败: {symbol} {action}")
                
        except Exception as e:
            logger.error(f"[ERR] 执行订单失败: {e}")
    
    def _monitor_positions(self):
        """监控持仓"""
        try:
            if not self.trading_interface:
                return
            
            positions = self.trading_interface.get_positions()
            
            for position in positions:
                # 更新当前价格
                current_price = self.trading_interface.get_market_price(position.symbol)
                if current_price:
                    position.update_price(current_price)
                    
                    # 检查止损止盈
                    self._check_stop_loss_take_profit(position, current_price)
                    
                    # 检查追踪止损
                    self._check_trailing_stop(position, current_price)
                    
        except Exception as e:
            logger.error(f"[ERR] 监控持仓失败: {e}")
    
    def _check_stop_loss_take_profit(self, position: Position, current_price: float):
        """检查止损止盈"""
        try:
            if position.action == "BUY":
                # 多头仓位
                if position.stop_loss and current_price <= position.stop_loss:
                    logger.warning(f"[WARN]  {position.symbol}触及止损: {current_price} <= {position.stop_loss}")
                    self.trading_interface.close_position(position.position_id)
                    
                elif position.take_profit and current_price >= position.take_profit:
                    logger.info(f"[OK]  {position.symbol}触及止盈: {current_price} >= {position.take_profit}")
                    self.trading_interface.close_position(position.position_id)
                    
            else:  # SELL
                # 空头仓位
                if position.stop_loss and current_price >= position.stop_loss:
                    logger.warning(f"[WARN]  {position.symbol}触及止损: {current_price} >= {position.stop_loss}")
                    self.trading_interface.close_position(position.position_id)
                    
                elif position.take_profit and current_price <= position.take_profit:
                    logger.info(f"[OK]  {position.symbol}触及止盈: {current_price} <= {position.take_profit}")
                    self.trading_interface.close_position(position.position_id)
                    
        except Exception as e:
            logger.error(f"[ERR] 检查止损止盈失败: {e}")
    
    def _check_trailing_stop(self, position: Position, current_price: float):
        """检查追踪止损"""
        try:
            # 简化实现：固定距离追踪止损
            trailing_distance = 20  # 20点
            
            if "trailing_stop_price" not in position.metadata:
                position.metadata["trailing_stop_price"] = None
            
            if position.action == "BUY":
                # 多头：价格上涨时更新追踪止损
                if position.metadata["trailing_stop_price"] is None:
                    position.metadata["trailing_stop_price"] = position.entry_price - trailing_distance * 0.0001
                
                new_trailing_stop = current_price - trailing_distance * 0.0001
                if new_trailing_stop > position.metadata["trailing_stop_price"]:
                    position.metadata["trailing_stop_price"] = new_trailing_stop
                    position.stop_loss = new_trailing_stop
                    logger.debug(f"[UP] 更新追踪止损: {position.symbol} -> {new_trailing_stop:.5f}")
                    
            else:  # SELL
                # 空头：价格下跌时更新追踪止损
                if position.metadata["trailing_stop_price"] is None:
                    position.metadata["trailing_stop_price"] = position.entry_price + trailing_distance * 0.0001
                
                new_trailing_stop = current_price + trailing_distance * 0.0001
                if new_trailing_stop < position.metadata["trailing_stop_price"]:
                    position.metadata["trailing_stop_price"] = new_trailing_stop
                    position.stop_loss = new_trailing_stop
                    logger.debug(f"[UP] 更新追踪止损: {position.symbol} -> {new_trailing_stop:.5f}")
                    
        except Exception as e:
            logger.error(f"[ERR] 检查追踪止损失败: {e}")
    
    def _update_account_info(self):
        """更新账户信息"""
        try:
            if not self.trading_interface:
                return
            
            account_info = self.trading_interface.get_account_info()
            
            if account_info:
                # 更新风险管理器的账户状态
                self.risk_manager.update_account_state(
                    balance=account_info.get("balance", 0),
                    equity=account_info.get("equity", 0),
                    profit=account_info.get("profit", 0)
                )
                
        except Exception as e:
            logger.error(f"[ERR] 更新账户信息失败: {e}")
    
    def submit_order(self, symbol: str, action: str, confidence: float, **kwargs):
        """提交订单到执行队列"""
        try:
            order_data = {
                "symbol": symbol,
                "action": action,
                "confidence": confidence,
                "timestamp": time.time(),
                **kwargs
            }
            
            self.order_queue.put(order_data)
            logger.info(f"📥 订单已提交到队列: {symbol} {action}")
            
        except Exception as e:
            logger.error(f"[ERR] 提交订单失败: {e}")
    
    def get_execution_status(self) -> Dict[str, Any]:
        """获取执行状态"""
        try:
            positions = []
            if self.trading_interface:
                positions = [
                    {
                        "symbol": p.symbol,
                        "action": p.action,
                        "quantity": p.quantity,
                        "entry_price": p.entry_price,
                        "current_price": p.current_price,
                        "unrealized_pnl": p.unrealized_pnl
                    }
                    for p in self.trading_interface.get_positions()
                ]
            
            return {
                "platform": self.platform.value,
                "connected": self.trading_interface is not None and self.trading_interface.connected,
                "queue_size": self.order_queue.qsize(),
                "active_positions": len(positions),
                "positions": positions,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"[ERR] 获取执行状态失败: {e}")
            return {}


# 全局交易执行器实例
_global_trade_executor: Optional[TradeExecutor] = None


def get_trade_executor(platform: TradingPlatform = TradingPlatform.MT5) -> TradeExecutor:
    """获取全局交易执行器实例"""
    global _global_trade_executor
    if not _global_trade_executor:
        _global_trade_executor = TradeExecutor(platform)
    return _global_trade_executor


if __name__ == "__main__":
    # 测试交易执行系统
    print("="*70)
    print("[TOOL] 测试自动化交易执行系统")
    print("="*70)
    
    executor = TradeExecutor(TradingPlatform.MT5)
    
    # 启动执行器
    executor.start()
    
    # 等待连接
    time.sleep(1)
    
    # 提交测试订单
    print("\n📥 提交测试订单...")
    executor.submit_order(
        symbol="EURUSD",
        action="BUY",
        confidence=0.75
    )
    
    # 等待订单执行
    time.sleep(2)
    
    # 获取执行状态
    print("\n[DATA] 执行状态:")
    status = executor.get_execution_status()
    print(f"   平台: {status['platform']}")
    print(f"   连接状态: {'已连接' if status['connected'] else '未连接'}")
    print(f"   队列大小: {status['queue_size']}")
    print(f"   活跃持仓: {status['active_positions']}")
    
    if status['positions']:
        for pos in status['positions']:
            print(f"   - {pos['symbol']} {pos['action']} {pos['quantity']}手 @ {pos['entry_price']}")
            print(f"     当前价格: {pos['current_price']}, 未实现盈亏: {pos['unrealized_pnl']:.2f}")
    
    # 停止执行器
    executor.stop()
    
    print("\n[OK] 自动化交易执行系统测试完成！")