#!/usr/bin/env python3
"""
Pip/Point 单位统一转换工具

MT5 价格单位体系:
  - _Point (MT5 Point): 最小价格变动单位
  - 外汇: _Point = 0.00001 (5位报价) 或 0.0001 (4位报价)
  - 黄金/XAUUSD: _Point = 0.01
  - 日元对: _Point = 0.001

Pip 定义 (行业标准):
  - 1 pip = 10 MT5 Points (外汇)
  - 1 pip = 10 MT5 Points = 0.10 价格单位 (黄金)
  - 1 pip = 100 MT5 Points (日元对)

本项目统一约定:
  - stop_loss_pips / take_profit_pips: 单位 = pips (1 pip = 10 * _Point)
  - EA端接收的点数 = pip数 (1:1 映射，EA内部会转换为MT5 Point计算SL/TP价格)
  - 风险评估中的"point_value": 每 1 MT5 Point 的价值（美元/手）
"""

from typing import Dict


# ==================== 品种分类 ====================

def is_gold(symbol: str) -> bool:
    """判断是否为黄金品种"""
    sym = symbol.upper()
    return sym.startswith("XAU") or "GOLD" in sym or sym == "GOLD_"


def is_jpy_pair(symbol: str) -> bool:
    """判断是否为日元对"""
    return "JPY" in symbol.upper()


# ==================== MT5 Point → 美元价值 ====================

# 每标准手(100k)每MT5 Point的价值（美元）
# 黄金: 1 Point = 0.01, 1手=100盎司, 所以1Point = $1.00?
# 实际上: MT5中 XAUUSD _Point=0.01, TickValue≈$1.0 (1手每个Point值$1.0)
# 外汇: _Point=0.00001, TickValue≈$1.0 (1手每个Point值$1.0)
# 简化为: 对于标准手, 每Point约等于$1.0 (对于大多数品种)
# 但小额交易中, 实际需要根据合约规格精确计算

def point_value_usd(symbol: str, lot_size: float = 1.0) -> float:
    """
    计算每MT5 Point的美元价值（指定手数）
    
    简化算法: 对黄金/外汇，标准手(1.0)每Point ≈ $1.00
    
    Args:
        symbol: 品种代码
        lot_size: 手数 (1.0 = 标准手, 0.01 = 微型手)
    Returns:
        每MT5 Point价值（美元）
    """
    base_value = 1.0  # 标准手每Point ≈ $1.00
    
    if is_jpy_pair(symbol):
        base_value = 1.0  # 日元对同样 ~$1/Point (但Point更大)
    
    return base_value * lot_size


# ==================== Pip ↔ Point 转换 ====================

PIPS_PER_POINT_GOLD = 0.1      # 1 MT5 Point = 0.1 pip (黄金)
POINTS_PER_PIP_GOLD = 10.0     # 1 pip = 10 MT5 Points (黄金)
PIPS_PER_POINT_FOREX = 0.1     # 1 MT5 Point = 0.1 pip (外汇)
POINTS_PER_PIP_FOREX = 10.0    # 1 pip = 10 MT5 Points (外汇)
PIPS_PER_POINT_JPY = 0.01      # 1 MT5 Point = 0.01 pip (日元)
POINTS_PER_PIP_JPY = 100.0     # 1 pip = 100 MT5 Points (日元)


def pips_to_points(pips: float, symbol: str = "XAUUSD") -> float:
    """Pips → MT5 Points 转换"""
    if is_jpy_pair(symbol):
        return pips * POINTS_PER_PIP_JPY
    return pips * POINTS_PER_PIP_GOLD


def points_to_pips(points: float, symbol: str = "XAUUSD") -> float:
    """MT5 Points → Pips 转换"""
    if is_jpy_pair(symbol):
        return points * PIPS_PER_POINT_JPY
    return points * PIPS_PER_POINT_GOLD


def pips_to_price(pips: float, symbol: str = "XAUUSD") -> float:
    """Pips → 价格距离转换 (SL/TP计算用)"""
    if is_jpy_pair(symbol):
        return pips * 0.01  # 1 pip = 0.01 (日元)
    return pips * 0.10  # 1 pip = 0.10 (黄金/外汇)


def price_to_pips(price_diff: float, symbol: str = "XAUUSD") -> float:
    """价格距离 → Pips 转换"""
    if is_jpy_pair(symbol):
        return price_diff / 0.01
    return price_diff / 0.10


# ==================== 风险计算工具 ====================

def calculate_risk_per_lot(sl_pips: float, symbol: str = "XAUUSD", lot_size: float = 1.0) -> float:
    """
    计算每手风险金额（美元）
    
    Args:
        sl_pips: 止损距离（pips）
        symbol: 品种
        lot_size: 手数
    Returns:
        风险金额（美元）
    """
    # 1 pip 的美元价值（标准手）
    pip_value = {
        "XAUUSD": 10.0,   # 1 pip = $10 (标准手)
        "GOLD": 10.0,
        "EURUSD": 10.0,
        "GBPUSD": 10.0,
        "USDJPY": 9.26,   # 1 pip ≈ $9.26 (标准手，但变化)
    }
    
    sym_upper = symbol.upper()
    if is_gold(sym_upper):
        base_pip_value = 10.0
    elif is_jpy_pair(sym_upper):
        base_pip_value = 9.26
    else:
        base_pip_value = 10.0  # 默认 $10/pip/标准手
    
    return sl_pips * base_pip_value * lot_size


def calculate_position_size(account_equity: float, risk_pct: float,
                           sl_pips: float, symbol: str = "XAUUSD") -> float:
    """
    基于风险百分比计算仓位大小
    
    Args:
        account_equity: 账户权益
        risk_pct: 风险百分比 (0.01 = 1%)
        sl_pips: 止损距离（pips）
        symbol: 品种
    Returns:
        推荐手数
    """
    risk_amount = account_equity * risk_pct
    risk_per_lot = calculate_risk_per_lot(sl_pips, symbol, 1.0)
    
    if risk_per_lot <= 0:
        return 0.01
    
    lots = risk_amount / risk_per_lot
    
    # 限制范围
    lots = max(0.01, min(lots, 5.0))
    
    # 取整到0.01
    lots = round(lots * 100) / 100
    
    return lots


# ==================== 验证工具 ====================

def validate_sl_tp(sl_pips: int, tp_pips: int, symbol: str = "XAUUSD") -> tuple:
    """
    验证止损止盈参数的合理性
    
    Returns:
        (is_valid, message, corrected_sl, corrected_tp)
    """
    messages = []
    sl, tp = sl_pips, tp_pips
    
    is_g = is_gold(symbol)
    min_sl = 20 if is_g else 15
    max_sl = 150 if is_g else 120
    min_tp = 40 if is_g else 30
    max_tp = 300 if is_g else 250
    
    if sl < min_sl:
        messages.append(f"止损过小({sl}pips < {min_sl}pips min)")
        sl = min_sl
    if sl > max_sl:
        messages.append(f"止损过大({sl}pips > {max_sl}pips max)")
        sl = max_sl
    
    if tp < min_tp:
        messages.append(f"止盈过小({tp}pips < {min_tp}pips min)")
        tp = min_tp
    if tp > max_tp:
        messages.append(f"止盈过大({tp}pips > {max_tp}pips max)")
        tp = max_tp
    
    # 盈亏比检查
    if tp < sl * 1.5:
        messages.append(f"盈亏比不足(TP={tp} < SL*1.5={sl*1.5})")
        tp = int(sl * 1.5)
    
    is_valid = len([m for m in messages if "过小" in m or "过大" in m]) == 0
    
    return is_valid, "; ".join(messages) if messages else "OK", sl, tp
