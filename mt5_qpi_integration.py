#!/usr/bin/env python3
"""
MT5 QPI (Query Protocol Interface) 集成模块
通过Python MetaTrader5库直接获取资金数据、持仓信息等
"""

import os
import sys
import json
import time
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    print("[WARN] MetaTrader5库未安装，请运行: pip install MetaTrader5")
    MT5_AVAILABLE = False

from core.logger import logger
from core.config import config


class MT5QPIInterface:
    """MT5 QPI 接口类 - 通过Python直接连接MT5"""
    
    def __init__(self, config_obj=None):
        """初始化MT5连接"""
        self.config = config_obj or config
        self.connected = False
        self.account_info = {}
        self.positions = []
        self.orders = []
        self.symbols = []
        self.last_update = datetime.now()
        
        logger.info("MT5 QPI接口初始化完成")
    
    def connect(self, 
                server: str = "",
                login: int = 0,
                password: str = "",
                path: str = "") -> bool:
        """
        连接到MT5终端
        
        Args:
            server: 服务器名称
            login: 账号
            password: 密码
            path: MT5终端路径
            
        Returns:
            bool: 连接是否成功
        """
        if not MT5_AVAILABLE:
            logger.error("MetaTrader5库未安装")
            return False
        
        try:
            # 如果提供了路径，初始化MT5
            if path:
                if not os.path.exists(path):
                    logger.error(f"MT5终端路径不存在: {path}")
                    return False
                
                if not mt5.initialize(path=path):
                    logger.error(f"MT5初始化失败，错误码: {mt5.last_error()}")
                    return False
            
            # 如果提供了登录凭据，尝试登录
            if login > 0 and password and server:
                authorized = mt5.login(login, password, server)
                if not authorized:
                    logger.error(f"MT5登录失败，错误码: {mt5.last_error()}")
                    mt5.shutdown()
                    return False
            
            # 获取账户信息
            account = mt5.account_info()
            if account is None:
                logger.error(f"获取账户信息失败，错误码: {mt5.last_error()}")
                return False
            
            self.connected = True
            self.account_info = self._parse_account_info(account)
            
            logger.info(f"MT5连接成功: 账户={account.login}, 服务器={account.server}")
            return True
            
        except Exception as e:
            logger.error(f"MT5连接异常: {e}")
            return False
    
    def _parse_account_info(self, account) -> Dict[str, Any]:
        """解析账户信息"""
        return {
            "login": account.login,
            "balance": account.balance,
            "equity": account.equity,
            "margin": account.margin,
            "margin_free": account.margin_free,
            "margin_level": account.margin_level,
            "profit": account.profit,
            "currency": account.currency,
            "leverage": account.leverage,
            "server": account.server,
            "trade_mode": account.trade_mode,
            "trade_allowed": account.trade_allowed,
            "limit_orders": account.limit_orders,
            "margin_mode": account.margin_mode,
            "credit": account.credit,
            "name": account.name
        }
    
    def get_account_info(self) -> Dict[str, Any]:
        """获取账户资金数据"""
        if not self.connected:
            logger.warning("MT5未连接，尝试重新连接...")
            if not self._auto_connect():
                return {}
        
        try:
            account = mt5.account_info()
            if account is None:
                logger.error(f"获取账户信息失败，错误码: {mt5.last_error()}")
                return {}
            
            self.account_info = self._parse_account_info(account)
            self.last_update = datetime.now()
            
            return self.account_info
            
        except Exception as e:
            logger.error(f"获取账户信息异常: {e}")
            return {}
    
    def get_positions(self, symbol: str = "") -> List[Dict[str, Any]]:
        """获取持仓信息
        
        Args:
            symbol: 品种名称，为空时获取所有持仓
            
        Returns:
            List[Dict]: 持仓列表
        """
        if not self.connected:
            logger.warning("MT5未连接，尝试重新连接...")
            if not self._auto_connect():
                return []
        
        try:
            if symbol:
                positions = mt5.positions_get(symbol=symbol)
            else:
                positions = mt5.positions_get()
            
            if positions is None:
                logger.debug("没有持仓数据")
                return []
            
            parsed_positions = []
            for pos in positions:
                parsed_positions.append(self._parse_position(pos))
            
            self.positions = parsed_positions
            self.last_update = datetime.now()
            
            return parsed_positions
            
        except Exception as e:
            logger.error(f"获取持仓信息异常: {e}")
            return []
    
    def _parse_position(self, position) -> Dict[str, Any]:
        """解析持仓信息"""
        return {
            "ticket": position.ticket,
            "symbol": position.symbol,
            "type": "BUY" if position.type == mt5.ORDER_TYPE_BUY else "SELL",
            "volume": position.volume,
            "open_time": datetime.fromtimestamp(position.time).strftime("%Y-%m-%d %H:%M:%S"),
            "open_price": position.price_open,
            "sl": position.sl,
            "tp": position.tp,
            "current_price": position.price_current,
            "profit": position.profit,
            "swap": position.swap,
            "comment": position.comment,
            "magic": position.magic,
            "identifier": position.identifier
        }
    
    def get_orders(self) -> List[Dict[str, Any]]:
        """获取挂单信息"""
        if not self.connected:
            logger.warning("MT5未连接，尝试重新连接...")
            if not self._auto_connect():
                return []
        
        try:
            orders = mt5.orders_get()
            if orders is None:
                logger.debug("没有挂单数据")
                return []
            
            parsed_orders = []
            for order in orders:
                parsed_orders.append(self._parse_order(order))
            
            self.orders = parsed_orders
            self.last_update = datetime.now()
            
            return parsed_orders
            
        except Exception as e:
            logger.error(f"获取挂单信息异常: {e}")
            return []
    
    def _parse_order(self, order) -> Dict[str, Any]:
        """解析挂单信息"""
        order_type = "未知"
        if order.type == mt5.ORDER_TYPE_BUY:
            order_type = "BUY_LIMIT"
        elif order.type == mt5.ORDER_TYPE_SELL:
            order_type = "SELL_LIMIT"
        elif order.type == mt5.ORDER_TYPE_BUY_STOP:
            order_type = "BUY_STOP"
        elif order.type == mt5.ORDER_TYPE_SELL_STOP:
            order_type = "SELL_STOP"
        
        return {
            "ticket": order.ticket,
            "symbol": order.symbol,
            "type": order_type,
            "volume": order.volume_current,
            "open_price": order.price_open,
            "sl": order.sl,
            "tp": order.tp,
            "comment": order.comment,
            "magic": order.magic,
            "time_setup": datetime.fromtimestamp(order.time_setup).strftime("%Y-%m-%d %H:%M:%S"),
            "time_expiration": datetime.fromtimestamp(order.time_expiration).strftime("%Y-%m-%d %H:%M:%S") if order.time_expiration > 0 else ""
        }
    
    def get_symbol_info(self, symbol: str) -> Optional[Dict[str, Any]]:
        """获取品种信息"""
        if not self.connected:
            logger.warning("MT5未连接，尝试重新连接...")
            if not self._auto_connect():
                return None
        
        try:
            info = mt5.symbol_info(symbol)
            if info is None:
                logger.error(f"获取品种信息失败: {symbol}")
                return None
            
            return {
                "symbol": info.symbol,
                "bid": info.bid,
                "ask": info.ask,
                "point": info.point,
                "digits": info.digits,
                "spread": info.spread,
                "trade_mode": info.trade_mode,
                "swap_mode": info.swap_mode,
                "swap_long": info.swap_long,
                "swap_short": info.swap_short,
                "margin_initial": info.margin_initial,
                "margin_maintenance": info.margin_maintenance,
                "margin_hedged": info.margin_hedged,
                "volume_min": info.volume_min,
                "volume_max": info.volume_max,
                "volume_step": info.volume_step
            }
            
        except Exception as e:
            logger.error(f"获取品种信息异常: {e}")
            return None
    
    def get_all_symbols(self) -> List[str]:
        """获取所有可交易品种"""
        if not self.connected:
            logger.warning("MT5未连接，尝试重新连接...")
            if not self._auto_connect():
                return []
        
        try:
            symbols = mt5.symbols_get()
            if symbols is None:
                logger.error("获取品种列表失败")
                return []
            
            symbol_names = [symbol.name for symbol in symbols]
            self.symbols = symbol_names
            
            return symbol_names
            
        except Exception as e:
            logger.error(f"获取品种列表异常: {e}")
            return []
    
    def get_dashboard_data(self) -> Dict[str, Any]:
        """获取Dashboard显示用的综合数据"""
        account = self.get_account_info()
        positions = self.get_positions()
        orders = self.get_orders()
        
        total_position_profit = sum(p.get("profit", 0) for p in positions)
        total_position_volume = sum(p.get("volume", 0) for p in positions)
        
        return {
            "account": account,
            "positions": positions,
            "orders": orders,
            "position_count": len(positions),
            "order_count": len(orders),
            "total_position_profit": total_position_profit,
            "total_position_volume": total_position_volume,
            "last_update": self.last_update.strftime("%Y-%m-%d %H:%M:%S"),
            "connected": self.connected
        }
    
    def get_risk_assessment_data(self) -> Dict[str, Any]:
        """获取风险评估用的数据"""
        positions = self.get_positions()
        account = self.get_account_info()
        
        if not positions or not account:
            return {}
        
        total_exposure = sum(p.get("volume", 0) for p in positions)
        max_position_size = max([p.get("volume", 0) for p in positions]) if positions else 0
        
        # 计算集中度风险
        concentration_risk = 0.0
        if total_exposure > 0:
            concentration_risk = max_position_size / total_exposure
        
        # 计算账户健康度
        account_health = 0.0
        margin = account.get("margin", 0)
        margin_free = account.get("margin_free", 0)
        if margin > 0:
            account_health = margin_free / margin
        
        # 计算总盈亏
        total_profit = account.get("profit", 0) + sum(p.get("profit", 0) for p in positions)
        
        return {
            "total_exposure": total_exposure,
            "max_position_size": max_position_size,
            "concentration_risk": concentration_risk,
            "account_health": account_health,
            "margin_level": account.get("margin_level", 0),
            "total_profit": total_profit,
            "position_count": len(positions),
            "balance": account.get("balance", 0),
            "equity": account.get("equity", 0),
            "margin_used": margin,
            "margin_free": margin_free
        }
    
    def _auto_connect(self) -> bool:
        """自动连接MT5（使用配置中的默认设置）"""
        try:
            # 尝试从配置中获取MT5路径
            mt5_path = self.config.MT5_PRIMARY_PATH
            
            # 如果配置了路径但路径不存在，尝试不指定路径连接
            if mt5_path and not os.path.exists(mt5_path):
                logger.warning(f"配置的MT5路径不存在: {mt5_path}，尝试不指定路径连接")
                mt5_path = None
            
            # 如果路径存在但不是可执行文件，尝试不指定路径连接
            if mt5_path and os.path.isdir(mt5_path):
                logger.warning(f"配置的MT5路径是文件夹而非可执行文件: {mt5_path}，尝试不指定路径连接")
                mt5_path = None
            
            # 尝试连接到已运行的MT5终端
            if mt5_path:
                # 使用指定路径连接
                if not mt5.initialize(path=mt5_path):
                    logger.error(f"MT5初始化失败（路径: {mt5_path}），错误码: {mt5.last_error()}")
                    return False
            else:
                # 不指定路径连接（假设MT5已在运行）
                if not mt5.initialize():
                    logger.error(f"MT5初始化失败（无路径），错误码: {mt5.last_error()}")
                    return False
            
            # 检查是否已登录
            account = mt5.account_info()
            if account is None:
                logger.warning("MT5已连接但未登录，只能获取市场数据")
            
            self.connected = True
            logger.info("MT5自动连接成功")
            return True
            
        except Exception as e:
            logger.error(f"MT5自动连接异常: {e}")
            return False
    
    def shutdown(self):
        """关闭MT5连接"""
        if self.connected and MT5_AVAILABLE:
            mt5.shutdown()
            self.connected = False
            logger.info("MT5连接已关闭")


def test_mt5_qpi():
    """测试MT5 QPI集成功能"""
    print("=" * 70)
    print("测试 MT5 QPI 集成功能")
    print("=" * 70)
    
    # 检查MT5库是否可用
    if not MT5_AVAILABLE:
        print("[FAIL] MetaTrader5库未安装")
        print("请运行: pip install MetaTrader5")
        return False
    
    # 创建接口实例
    qpi = MT5QPIInterface()
    
    # 尝试自动连接
    print("\n[TEST] 尝试自动连接MT5...")
    if not qpi._auto_connect():
        print("[WARN] 自动连接失败，需要手动配置MT5路径")
        
        # 提示用户配置信息
        print("\n[MESSAGE] 需要配置以下信息:")
        print("1. MT5终端安装路径 (例如: C:/Program Files/MetaTrader 5/terminal64.exe)")
        print("2. 账户信息 (登录号、密码、服务器)")
        print("\n在 core/config.py 中添加配置:")
        print("MT5_PRIMARY_PATH = 'C:/Program Files/MetaTrader 5/terminal64.exe'")
        
        return False
    
    print("[PASS] MT5连接成功")
    
    # 测试账户信息获取
    print("\n[TEST] 测试账户信息获取...")
    account_info = qpi.get_account_info()
    if account_info:
        print(f"[PASS] 账户信息获取成功")
        print(f"  账号: {account_info.get('login', 'N/A')}")
        print(f"  余额: {account_info.get('balance', 0):.2f}")
        print(f"  净值: {account_info.get('equity', 0):.2f}")
        print(f"  杠杆: 1:{account_info.get('leverage', 0)}")
    else:
        print("[WARN] 账户信息获取失败，可能未登录")
    
    # 测试持仓信息获取
    print("\n[TEST] 测试持仓信息获取...")
    positions = qpi.get_positions()
    if positions:
        print(f"[PASS] 持仓信息获取成功: {len(positions)} 个持仓")
        for i, pos in enumerate(positions[:3]):  # 只显示前3个
            print(f"  持仓 {i+1}: {pos['symbol']} {pos['type']} {pos['volume']}手 "
                  f"盈亏: {pos['profit']:.2f}")
    else:
        print("[INFO] 没有持仓")
    
    # 测试品种信息获取
    print("\n[TEST] 测试品种信息获取...")
    symbols = qpi.get_all_symbols()
    if symbols:
        print(f"[PASS] 品种列表获取成功: {len(symbols)} 个品种")
        print(f"  示例: {symbols[:5]}...")  # 只显示前5个
    else:
        print("[WARN] 品种列表获取失败")
    
    # 测试Dashboard数据
    print("\n[TEST] 测试Dashboard数据获取...")
    dashboard = qpi.get_dashboard_data()
    if dashboard:
        print(f"[PASS] Dashboard数据获取成功")
        print(f"  持仓数: {dashboard.get('position_count', 0)}")
        print(f"  挂单数: {dashboard.get('order_count', 0)}")
        print(f"  总浮动盈亏: {dashboard.get('total_position_profit', 0):.2f}")
    else:
        print("[WARN] Dashboard数据获取失败")
    
    # 关闭连接
    qpi.shutdown()
    
    print("\n" + "=" * 70)
    print("[CONCLUSION] MT5 QPI 集成测试完成")
    print("=" * 70)
    
    return True


if __name__ == "__main__":
    test_mt5_qpi()