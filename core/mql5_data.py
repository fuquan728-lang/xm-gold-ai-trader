#!/usr/bin/env python3
"""
MT5 AI Trading System - MQL5 Data Integration Module
获取账户资金、持仓、交易记录等数据
"""

import os
import sys
import json
import threading
import time
from datetime import datetime
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.logger import logger


@dataclass
class AccountInfo:
    """账户信息"""
    balance: float = 0.0          # 余额
    equity: float = 0.0           # 净值
    margin: float = 0.0           # 已用保证金
    margin_free: float = 0.0      # 可用保证金
    margin_level: float = 0.0     # 保证金水平
    profit: float = 0.0           # 浮动盈亏
    currency: str = "USD"         # 货币
    leverage: int = 100           # 杠杆
    account: int = 0              # 账号
    server: str = ""              # 服务器


@dataclass
class Position:
    """持仓信息"""
    ticket: int = 0               # 订单号
    symbol: str = ""              # 品种
    type: str = ""                # 类型: BUY/SELL
    volume: float = 0.0           # 手数
    open_time: str = ""           # 开仓时间
    open_price: float = 0.0       # 开仓价
    sl: float = 0.0               # 止损
    tp: float = 0.0               # 止盈
    current_price: float = 0.0    # 当前价
    profit: float = 0.0           # 盈亏
    swap: float = 0.0             # 库存费
    comment: str = ""             # 备注


@dataclass
class TradeHistory:
    """历史交易"""
    ticket: int = 0               # 订单号
    symbol: str = ""              # 品种
    type: str = ""                # 类型
    volume: float = 0.0           # 手数
    open_time: str = ""           # 开仓时间
    open_price: float = 0.0       # 开仓价
    close_time: str = ""          # 平仓时间
    close_price: float = 0.0      # 平仓价
    profit: float = 0.0           # 盈亏
    swap: float = 0.0             # 库存费
    commission: float = 0.0       # 手续费
    comment: str = ""             # 备注


class MQL5DataManager:
    """MQL5 数据管理器"""
    
    def __init__(self):
        self.account_info = AccountInfo()
        self.positions: List[Position] = []
        self.trade_history: List[TradeHistory] = []
        
        # 扩展字段
        self.market_data: Dict[str, Any] = {}
        self.symbols_info: Dict[str, Any] = {}
        self.broker_info: Dict[str, Any] = {}
        
        self.last_update = datetime.now()
        self.update_callback = None
        
        self._lock = threading.Lock()
        
        logger.info("MQL5 数据管理器初始化完成 - 支持完整数据集成")
    
    def update_from_json(self, data: Dict[str, Any]) -> bool:
        """从 JSON 数据更新（通过 Socket/WebSocket/文件）"""
        try:
            with self._lock:
                # 确保包含所有必需的数据类别
                if "type" in data and data["type"] == "mql5_data":
                    # 完整MQL5数据包
                    if "account" in data:
                        self._update_account(data["account"])
                    
                    if "positions" in data:
                        self._update_positions(data["positions"])
                    
                    if "history" in data:
                        self._update_history(data["history"])
                    
                    # 新增市场数据支持（可选）
                    if "market_data" in data:
                        self._update_market_data(data["market_data"])
                    
                    # 新增品种信息（可选）
                    if "symbols" in data:
                        self._update_symbols(data["symbols"])
                else:
                    # 向后兼容模式
                    if "account" in data:
                        self._update_account(data["account"])
                    
                    if "positions" in data:
                        self._update_positions(data["positions"])
                    
                    if "history" in data:
                        self._update_history(data["history"])
                
                self.last_update = datetime.now()
                
                if self.update_callback:
                    self.update_callback(self)
                
                logger.info(f"[数据更新] 成功更新MQL5数据，持仓:{len(self.positions)}，净值:{self.account_info.equity:.2f}")
                return True
        except Exception as e:
            logger.error(f"更新 MQL5 数据失败: {e}")
            return False
    
    def _update_account(self, data: Dict[str, Any]):
        """更新账户信息"""
        try:
            self.account_info.balance = data.get("balance", 0.0)
            self.account_info.equity = data.get("equity", 0.0)
            self.account_info.margin = data.get("margin", 0.0)
            self.account_info.margin_free = data.get("margin_free", 0.0)
            self.account_info.margin_level = data.get("margin_level", 0.0)
            if (
                self.account_info.margin <= 0
                and (self.account_info.margin_free > 0 or self.account_info.equity > 0)
                and self.account_info.margin_level <= 0
            ):
                self.account_info.margin_level = 1000.0
            self.account_info.profit = data.get("profit", 0.0)
            self.account_info.currency = data.get("currency", "USD")
            self.account_info.leverage = data.get("leverage", 100)
            self.account_info.account = data.get("account", 0)
            self.account_info.server = data.get("server", "")
            
            logger.debug(f"账户信息已更新: 净值={self.account_info.equity}, "
                        f"浮动盈亏={self.account_info.profit}")
        except Exception as e:
            logger.error(f"更新账户信息失败: {e}")
    
    def _update_positions(self, data_list: List[Dict[str, Any]]):
        """更新持仓信息"""
        try:
            self.positions = []
            for item in data_list:
                pos = Position(
                    ticket=item.get("ticket", 0),
                    symbol=item.get("symbol", ""),
                    type=item.get("type", ""),
                    volume=item.get("volume", 0.0),
                    open_time=item.get("open_time", ""),
                    open_price=item.get("open_price", 0.0),
                    sl=item.get("sl", 0.0),
                    tp=item.get("tp", 0.0),
                    current_price=item.get("current_price", 0.0),
                    profit=item.get("profit", 0.0),
                    swap=item.get("swap", 0.0),
                    comment=item.get("comment", "")
                )
                self.positions.append(pos)
            
            logger.debug(f"持仓信息已更新: {len(self.positions)} 个持仓")
        except Exception as e:
            logger.error(f"更新持仓信息失败: {e}")
    
    def _update_history(self, data_list: List[Dict[str, Any]]):
        """更新历史交易"""
        try:
            self.trade_history = []
            for item in data_list:
                trade = TradeHistory(
                    ticket=item.get("ticket", 0),
                    symbol=item.get("symbol", ""),
                    type=item.get("type", ""),
                    volume=item.get("volume", 0.0),
                    open_time=item.get("open_time", ""),
                    open_price=item.get("open_price", 0.0),
                    close_time=item.get("close_time", ""),
                    close_price=item.get("close_price", 0.0),
                    profit=item.get("profit", 0.0),
                    swap=item.get("swap", 0.0),
                    commission=item.get("commission", 0.0),
                    comment=item.get("comment", "")
                )
                self.trade_history.append(trade)
            
            logger.debug(f"历史交易已更新: {len(self.trade_history)} 条记录")
        except Exception as e:
            logger.error(f"更新历史交易失败: {e}")

    def _update_market_data(self, data: Dict[str, Any]):
        """更新市场数据（可选扩展）"""
        try:
            # 这里可以存储市场数据用于后续分析
            # 例如：市场情绪、波动率等
            if not hasattr(self, 'market_data'):
                self.market_data = {}
            
            for key, value in data.items():
                self.market_data[key] = value
            
            logger.debug(f"市场数据已更新: {len(data)} 项")
        except Exception as e:
            logger.error(f"更新市场数据失败: {e}")

    def _update_symbols(self, symbols_list: List[Dict[str, Any]]):
        """更新品种信息（可选扩展）"""
        try:
            # 存储品种信息：点差、手续费、最小交易量等
            if not hasattr(self, 'symbols_info'):
                self.symbols_info = {}
            
            for symbol_data in symbols_list:
                symbol = symbol_data.get("symbol", "")
                if symbol:
                    self.symbols_info[symbol] = {
                        "spread": symbol_data.get("spread", 0.0),
                        "commission": symbol_data.get("commission", 0.0),
                        "min_lot": symbol_data.get("min_lot", 0.01),
                        "max_lot": symbol_data.get("max_lot", 100.0),
                        "lot_step": symbol_data.get("lot_step", 0.01),
                        "digits": symbol_data.get("digits", 5),
                        "swap_long": symbol_data.get("swap_long", 0.0),
                        "swap_short": symbol_data.get("swap_short", 0.0),
                        "currency_base": symbol_data.get("currency_base", ""),
                        "currency_profit": symbol_data.get("currency_profit", ""),
                        "tick_value": symbol_data.get("tick_value", 0.0)
                    }
            
            logger.debug(f"品种信息已更新: {len(self.symbols_info)} 个品种")
        except Exception as e:
            logger.error(f"更新品种信息失败: {e}")
    
    def get_dashboard_data(self) -> Dict[str, Any]:
        """获取 Dashboard 显示用的数据"""
        with self._lock:
            total_position_profit = sum(p.profit for p in self.positions)
            
            return {
                "account": asdict(self.account_info),
                "positions": [asdict(p) for p in self.positions],
                "history_count": len(self.trade_history),
                "total_position_profit": total_position_profit,
                "last_update": self.last_update.strftime("%Y-%m-%d %H:%M:%S"),
                "position_count": len(self.positions)
            }
    
    def get_risk_assessment_data(self) -> Dict[str, Any]:
        """获取风险评估用的数据"""
        with self._lock:
            total_exposure = sum(p.volume for p in self.positions)
            max_position_size = max([p.volume for p in self.positions]) if self.positions else 0
            
            # 计算集中度风险
            concentration_risk = 0.0
            if total_exposure > 0:
                concentration_risk = max_position_size / total_exposure
            
            # 计算账户健康度
            account_health = 0.0
            if self.account_info.margin > 0:
                account_health = self.account_info.margin_free / self.account_info.margin
            
            return {
                "total_exposure": total_exposure,
                "max_position_size": max_position_size,
                "concentration_risk": concentration_risk,
                "account_health": account_health,
                "margin_level": self.account_info.margin_level,
                "total_profit": self.account_info.profit + sum(p.profit for p in self.positions),
                "position_count": len(self.positions)
            }
    
    def get_real_time_data_summary(self) -> Dict[str, Any]:
        """获取实时数据摘要，用于AI决策"""
        with self._lock:
            # 按品种分组持仓
            symbol_positions = {}
            for pos in self.positions:
                symbol = pos.symbol
                if symbol not in symbol_positions:
                    symbol_positions[symbol] = {
                        "total_volume": 0,
                        "total_profit": 0,
                        "position_count": 0
                    }
                symbol_positions[symbol]["total_volume"] += pos.volume
                symbol_positions[symbol]["total_profit"] += pos.profit
                symbol_positions[symbol]["position_count"] += 1
            
            return {
                "account_summary": {
                    "balance": self.account_info.balance,
                    "equity": self.account_info.equity,
                    "margin_used": self.account_info.margin,
                    "margin_free": self.account_info.margin_free,
                    "margin_level": self.account_info.margin_level,
                    "floating_profit": self.account_info.profit
                },
                "positions_summary": {
                    "total_count": len(self.positions),
                    "total_volume": sum(p.volume for p in self.positions),
                    "total_profit": sum(p.profit for p in self.positions),
                    "by_symbol": symbol_positions
                },
                "last_update": self.last_update.strftime("%Y-%m-%d %H:%M:%S")
            }
    
    def get_raw_data(self) -> Dict[str, Any]:
        """获取原始数据"""
        with self._lock:
            return {
                "account_info": asdict(self.account_info),
                "positions": [asdict(p) for p in self.positions],
                "trade_history": [asdict(t) for t in self.trade_history],
                "market_data": self.market_data,
                "symbols_info": self.symbols_info,
                "broker_info": self.broker_info,
                "last_update": self.last_update.isoformat()
            }

    def get_complete_broker_data(self) -> Dict[str, Any]:
        """获取完整的经纪商数据（Python AI分析所需全部数据）"""
        with self._lock:
            # 计算账户健康指标
            total_exposure = sum(p.volume for p in self.positions)
            max_position_size = max([p.volume for p in self.positions]) if self.positions else 0
            
            # 品种风险敞口
            symbol_exposure = {}
            for pos in self.positions:
                symbol = pos.symbol
                if symbol not in symbol_exposure:
                    symbol_exposure[symbol] = {
                        "total_volume": 0,
                        "total_profit": 0,
                        "position_count": 0
                    }
                symbol_exposure[symbol]["total_volume"] += pos.volume
                symbol_exposure[symbol]["total_profit"] += pos.profit
                symbol_exposure[symbol]["position_count"] += 1
            
            return {
                # 账户核心数据
                "account": {
                    "balance": self.account_info.balance,
                    "equity": self.account_info.equity,
                    "margin_used": self.account_info.margin,
                    "margin_free": self.account_info.margin_free,
                    "margin_level": self.account_info.margin_level,
                    "floating_profit": self.account_info.profit,
                    "currency": self.account_info.currency,
                    "leverage": self.account_info.leverage,
                    "account_number": self.account_info.account,
                    "server": self.account_info.server,
                    "timestamp": self.last_update.isoformat()
                },
                
                # 持仓分析
                "positions": {
                    "total_count": len(self.positions),
                    "total_volume": sum(p.volume for p in self.positions),
                    "total_profit": sum(p.profit for p in self.positions),
                    "by_symbol": symbol_exposure,
                    "max_position_size": max_position_size,
                    "total_exposure": total_exposure
                },
                
                # 品种信息（用于风险计算）
                "symbols": self.symbols_info,
                
                # 风险指标
                "risk_metrics": {
                    "concentration_risk": max_position_size / total_exposure if total_exposure > 0 else 0,
                    "account_health": self.account_info.margin_free / self.account_info.margin if self.account_info.margin > 0 else 0,
                    "drawdown_potential": self.account_info.profit / self.account_info.equity if self.account_info.equity > 0 else 0,
                    "leverage_utilization": self.account_info.margin / self.account_info.equity if self.account_info.equity > 0 else 0
                },
                
                # 市场数据
                "market_conditions": self.market_data,
                
                # 经纪商信息
                "broker": self.broker_info
            }


# 全局实例
_mql5_data_manager: Optional[MQL5DataManager] = None


def get_mql5_data_manager() -> MQL5DataManager:
    """获取全局 MQL5 数据管理器实例"""
    global _mql5_data_manager
    if _mql5_data_manager is None:
        _mql5_data_manager = MQL5DataManager()
    return _mql5_data_manager
