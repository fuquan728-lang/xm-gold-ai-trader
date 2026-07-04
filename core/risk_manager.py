#!/usr/bin/env python3
"""
科学智能交易系统 - 自适应风险控制机制
根据市场波动动态调整仓位、止损和风险暴露
集成MQL5实时账户和持仓数据
"""

import math
import time
import datetime as dt
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from enum import Enum
import threading
import statistics

import numpy as np
from scipy import stats

from core.logger import logger
from core.datastore import get_datastore
from core.market_data_analyzer import get_market_data_analyzer
from core.mql5_data import get_mql5_data_manager
from core.margin_manager import get_margin_manager
from core.pip_utils import (
    is_gold, is_jpy_pair, pips_to_points, 
    PIPS_PER_POINT_GOLD, POINTS_PER_PIP_GOLD,
    calculate_risk_per_lot, validate_sl_tp
)

# ── 风险阈值常量（集中管理，便于调优） ──
# 风险评分阈值
RISK_THRESHOLD_VERY_HIGH = 0.7
RISK_THRESHOLD_HIGH = 0.5
RISK_THRESHOLD_MEDIUM = 0.3
RISK_THRESHOLD_LOW = 0.1

# 波动率阈值
VOLATILITY_VERY_HIGH = 0.25
VOLATILITY_HIGH = 0.15
VOLATILITY_LOW = 0.05

# 仓位分级阈值（手数）
POSITION_MICRO = 0.02
POSITION_SMALL = 0.05
POSITION_MEDIUM = 0.1

# 历史记录容量限制
MAX_TRADE_HISTORY = 1000
MAX_DAILY_PNL = 250

# 保证金水平阈值
MARGIN_CRITICAL = 20.0
MARGIN_DANGER = 50.0
MARGIN_WARNING = 100.0
MARGIN_NORMAL = 200.0
MARGIN_COMFORTABLE = 500.0


class RiskLevel(Enum):
    """风险等级"""
    VERY_LOW = "very_low"      # 极低风险：波动率极低，趋势明确
    LOW = "low"                # 低风险：波动率低，趋势良好
    MEDIUM = "medium"          # 中等风险：正常波动
    HIGH = "high"              # 高风险：高波动，趋势不明
    VERY_HIGH = "very_high"    # 极高风险：极高波动，市场混乱


class PositionSizingMethod(Enum):
    """仓位大小计算方法"""
    FIXED_FRACTIONAL = "fixed_fractional"      # 固定分数
    KELLY_CRITERION = "kelly_criterion"        # 凯利公式
    VOLATILITY_ADJUSTED = "volatility_adjusted" # 波动率调整
    MARTINGALE = "martingale"                  # 马丁格尔（高风险）
    ANTI_MARTINGALE = "anti_martingale"        # 反马丁格尔


@dataclass
class RiskMetrics:
    """风险指标"""
    volatility: float                     # 波动率（年化）
    sharpe_ratio: float                   # 夏普比率
    max_drawdown: float                   # 最大回撤
    var_95: float                         # 95%置信度VaR
    expected_shortfall: float             # 期望损失
    win_rate: float                       # 胜率
    profit_factor: float                  # 盈利因子
    risk_reward_ratio: float              # 风险回报比
    current_drawdown: float               # 当前回撤
    consecutive_losses: int               # 连续亏损次数


@dataclass
class RiskParameters:
    """风险参数"""
    risk_level: RiskLevel
    max_position_size: float              # 最大仓位大小（占账户比例）
    max_daily_loss: float                 # 最大单日亏损（占账户比例）
    max_consecutive_losses: int           # 最大连续亏损次数
    stop_loss_pips: float                 # 止损点数
    take_profit_pips: float               # 止盈点数
    trailing_stop_pips: float             # 追踪止损点数
    volatility_multiplier: float          # 波动率乘数
    risk_per_trade: float                 # 每笔交易风险（占账户比例）
    position_sizing_method: PositionSizingMethod


@dataclass
class TradeRiskAssessment:
    """交易风险评估"""
    symbol: str
    action: str
    confidence: float
    recommended_position_size: float      # 推荐仓位大小（手数）
    recommended_stop_loss: float          # 推荐止损价格
    recommended_take_profit: float        # 推荐止盈价格
    risk_reward_ratio: float              # 风险回报比
    expected_value: float                 # 期望价值
    risk_score: float                     # 风险评分（0-1，越低越好）
    risk_level: RiskLevel
    warning_messages: List[str]


class RiskManager:
    """自适应风险管理器"""
    
    def __init__(self, account_balance: float = 10000.0):
        self.account_balance = account_balance
        self.equity = account_balance
        self.datastore = get_datastore()
        self.market_analyzer = get_market_data_analyzer()
        self.mql5_data = get_mql5_data_manager()
        self.margin_manager = get_margin_manager()
        
        # 风险参数
        self.risk_params = RiskParameters(
            risk_level=RiskLevel.MEDIUM,
            max_position_size=0.05,        # 最大5%仓位
            max_daily_loss=0.02,           # 最大单日亏损2%
            max_consecutive_losses=3,      # 最大连续亏损3次
            stop_loss_pips=30.0,           # 默认30点止损
            take_profit_pips=60.0,         # 默认60点止盈
            trailing_stop_pips=20.0,       # 追踪止损20点
            volatility_multiplier=1.0,
            risk_per_trade=0.01,           # 每笔交易风险1%
            position_sizing_method=PositionSizingMethod.VOLATILITY_ADJUSTED
        )
        
        # 风险指标
        self.risk_metrics = RiskMetrics(
            volatility=0.0,
            sharpe_ratio=0.0,
            max_drawdown=0.0,
            var_95=0.0,
            expected_shortfall=0.0,
            win_rate=0.5,
            profit_factor=1.0,
            risk_reward_ratio=1.5,
            current_drawdown=0.0,
            consecutive_losses=0
        )
        
        # 交易历史
        self.trade_history: List[Dict[str, Any]] = []
        self.daily_pnl: List[float] = []
        
        # 运行状态
        self.running = False
        self.monitor_thread: Optional[threading.Thread] = None
        
        # 危机模式标志（由MarginCrisisHandler设置）
        self.is_crisis_mode = False
        self.crisis_risk_params: Dict[str, Any] = {}
        
        # 市场波动率缓存
        self.volatility_cache: Dict[str, float] = {}
        
        logger.info("[RM]  自适应风险管理器初始化完成")
    
    def _prune_trade_history(self):
        """裁剪交易历史，防止内存无限增长"""
        if len(self.trade_history) > MAX_TRADE_HISTORY:
            self.trade_history = self.trade_history[-MAX_TRADE_HISTORY:]
        if len(self.daily_pnl) > MAX_DAILY_PNL:
            self.daily_pnl = self.daily_pnl[-MAX_DAILY_PNL:]
    
    def record_trade(self, trade: Dict[str, Any]):
        """记录交易并自动裁剪历史"""
        self.trade_history.append(trade)
        self._prune_trade_history()
    
    def start(self):
        """启动风险监控"""
        if self.running:
            logger.warning("[WARN]  风险管理器已在运行中")
            return
        
        self.running = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
        logger.info("-> 风险管理器已启动")
    
    def stop(self):
        """停止风险监控"""
        self.running = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5)
        logger.info("[STOP] 风险管理器已停止")
    
    def _monitor_loop(self):
        """风险监控循环"""
        logger.info("[REFRESH] 风险监控循环开始")
        
        last_metrics_update = 0
        
        while self.running:
            try:
                current_time = time.time()
                
                # 每5分钟更新一次风险指标
                if current_time - last_metrics_update > 300:
                    self._update_risk_metrics()
                    last_metrics_update = current_time
                
                # 监控账户风险
                self._monitor_account_risk()
                
                # 监控市场风险
                self._monitor_market_risk()
                
                time.sleep(10)  # 每10秒检查一次
                
            except Exception as e:
                logger.error(f"[ERR] 风险监控循环异常: {e}")
                time.sleep(30)
    
    def _update_risk_metrics(self):
        """更新风险指标"""
        try:
            # 从数据库获取最近的交易记录
            recent_trades = self.datastore.get_trades(limit=100)
            
            if not recent_trades:
                return
            
            # 计算胜率、盈利因子等
            winning_trades = [t for t in recent_trades if t.get('pnl', 0) > 0]
            losing_trades = [t for t in recent_trades if t.get('pnl', 0) < 0]
            
            total_wins = len(winning_trades)
            total_losses = len(losing_trades)
            total_trades = total_wins + total_losses
            
            if total_trades > 0:
                self.risk_metrics.win_rate = total_wins / total_trades
            
            # 计算盈利因子
            total_profit = sum(t.get('pnl', 0) for t in winning_trades)
            total_loss = abs(sum(t.get('pnl', 0) for t in losing_trades))
            
            if total_loss > 0:
                self.risk_metrics.profit_factor = total_profit / total_loss
            else:
                self.risk_metrics.profit_factor = float('inf') if total_profit > 0 else 1.0
            
            # 计算风险回报比（平均盈利/平均亏损）
            avg_win = np.mean([t.get('pnl', 0) for t in winning_trades]) if winning_trades else 0
            avg_loss = abs(np.mean([t.get('pnl', 0) for t in losing_trades])) if losing_trades else 0
            
            if avg_loss > 0:
                self.risk_metrics.risk_reward_ratio = avg_win / avg_loss
            else:
                self.risk_metrics.risk_reward_ratio = float('inf') if avg_win > 0 else 1.0
            
            # 计算最大回撤和当前回撤
            pnl_series = [t.get('pnl', 0) for t in recent_trades]
            cumulative_pnl = np.cumsum(pnl_series)
            
            if len(cumulative_pnl) > 0:
                running_max = np.maximum.accumulate(cumulative_pnl)
                drawdowns = running_max - cumulative_pnl
                
                if len(drawdowns) > 0:
                    self.risk_metrics.max_drawdown = float(np.max(drawdowns))
                    self.risk_metrics.current_drawdown = float(drawdowns[-1])
            
            # 计算波动率（基于PnL）
            if len(pnl_series) >= 10:
                returns = np.diff(pnl_series) / (np.abs(pnl_series[:-1]) + 1e-10)
                if len(returns) > 0:
                    # 年化波动率（假设每天有10笔交易）
                    daily_volatility = np.std(returns) * np.sqrt(10)
                    annual_volatility = daily_volatility * np.sqrt(252)
                    self.risk_metrics.volatility = float(annual_volatility)
            
            # 计算夏普比率（简化）
            if len(pnl_series) >= 10:
                avg_return = np.mean(pnl_series)
                std_return = np.std(pnl_series)
                if std_return > 0:
                    self.risk_metrics.sharpe_ratio = float(avg_return / std_return * np.sqrt(252))
            
            # 计算VaR和期望损失
            if len(pnl_series) >= 20:
                sorted_returns = sorted(pnl_series)
                var_index = int(len(sorted_returns) * 0.05)  # 95%置信度
                if var_index < len(sorted_returns):
                    self.risk_metrics.var_95 = float(sorted_returns[var_index])
                    
                    # 期望损失（超过VaR的平均损失）
                    tail_losses = sorted_returns[:var_index]
                    if tail_losses:
                        self.risk_metrics.expected_shortfall = float(np.mean(tail_losses))
            
            logger.debug(f"[DATA] 风险指标更新完成: 胜率={self.risk_metrics.win_rate:.2f}, "
                        f"盈利因子={self.risk_metrics.profit_factor:.2f}, "
                        f"最大回撤={self.risk_metrics.max_drawdown:.2f}")
                        
        except Exception as e:
            logger.error(f"[ERR] 更新风险指标失败: {e}")
    
    def _monitor_account_risk(self):
        """监控账户风险，使用MQL5实时数据"""
        try:
            # 从MQL5数据管理器获取实时数据
            realtime_data = self.mql5_data.get_real_time_data_summary()
            account_data = realtime_data.get("account_summary", {})
            positions_data = realtime_data.get("positions_summary", {})
            
            # 检查数据有效性：如果没有真实的MQL5数据，跳过风险监控
            if not account_data or account_data.get("balance", 0) == 0:
                # 首次启动或EA未连接，使用默认值，不触发紧急警告
                logger.debug(f"[DATA] 等待MQL5实时数据... (当前余额: {self.account_balance})")
                return
            
            # 更新账户余额和净值（使用真实数据）
            if account_data:
                self.account_balance = account_data.get("balance", self.account_balance)
                self.equity = account_data.get("equity", self.equity)
                
                # 计算当前浮动盈亏百分比
                floating_profit = account_data.get("floating_profit", 0)
                profit_percentage = floating_profit / self.account_balance if self.account_balance > 0 else 0
                
            # 检查保证金水平，使用智能保证金管理器
            margin_level = account_data.get("margin_level", 0)
            
            # 如果保证金水平为0或极低，可能是数据不完整，跳过预警
            if margin_level <= 0:
                logger.debug(f"[DATA] 保证金水平数据不完整: {margin_level}，跳过预警")
                return
            
            # 获取保证金建议
            margin_advice = self.margin_manager.get_margin_advice_for_trade(
                symbol="EURUSD",  # 示例品种，实际应根据需要调整
                position_size=0.1,  # 示例仓位
                current_price=1.0865  # 示例价格
            )
            
            # 根据保证金水平进行多级预警
            if margin_level < MARGIN_CRITICAL:
                logger.warning(f"[紧急] 保证金水平极低: {margin_level:.1f}%，立即采取措施！")
                # 自动降低风险等级
                self.risk_params.risk_level = RiskLevel.VERY_HIGH
                self._update_risk_parameters(self.risk_params.risk_level)
                
            elif margin_level < MARGIN_DANGER:
                logger.warning(f"[危险] 保证金水平危险: {margin_level:.1f}%，建议减仓")
                self.risk_params.risk_level = RiskLevel.HIGH
                self._update_risk_parameters(self.risk_params.risk_level)
                
            elif margin_level < MARGIN_WARNING:
                logger.warning(f"[警告] 保证金水平警告: {margin_level:.1f}%，需关注")
                if self.risk_params.risk_level.value < RiskLevel.HIGH.value:
                    self.risk_params.risk_level = RiskLevel.MEDIUM
                    self._update_risk_parameters(self.risk_params.risk_level)
                    
            elif margin_level < MARGIN_NORMAL:
                logger.info(f"[DATA] 保证金水平正常: {margin_level:.1f}%")
            
            # 检查持仓集中度风险
            if positions_data:
                total_volume = positions_data.get("total_volume", 0)
                position_count = positions_data.get("total_count", 0)
                by_symbol = positions_data.get("by_symbol", {})
                
                # 检查单品种风险
                for symbol, data in by_symbol.items():
                    symbol_volume = data.get("total_volume", 0)
                    if total_volume > 0:
                        concentration = symbol_volume / total_volume
                        if concentration > 0.5:  # 单品种持仓超过50%
                            logger.warning(f"[WARN]  {symbol}持仓集中度过高: {concentration:.1%}")
            
            # 检查当前回撤（基于真实权益）
            current_drawdown = self.account_balance - self.equity
            if self.account_balance > 0 and current_drawdown > 0 and current_drawdown > self.account_balance * 0.05:  # 超过5%回撤
                logger.warning(f"[WARN]  当前回撤较大: {current_drawdown:.2f} "
                              f"({current_drawdown/self.account_balance*100:.1f}%)")
                self.risk_metrics.current_drawdown = current_drawdown
            
            # 检查连续亏损（基于真实数据）
            if self.risk_metrics.consecutive_losses >= self.risk_params.max_consecutive_losses:
                logger.warning(f"[WARN]  连续亏损{self.risk_metrics.consecutive_losses}次，考虑暂停交易")
            
            # 根据风险指标调整风险等级
            self._adjust_risk_level()
            
        except Exception as e:
            logger.error(f"[ERR] 监控账户风险失败: {e}")
    
    def _monitor_market_risk(self):
        """监控市场风险"""
        try:
            symbols = ["EURUSD", "GBPUSD", "USDJPY", "GOLD"]
            
            for symbol in symbols:
                # 获取市场分析
                analysis = self.market_analyzer.get_market_analysis(symbol, "M1")
                
                if analysis and "volatility" in analysis:
                    volatility = analysis["volatility"]
                    self.volatility_cache[symbol] = volatility
                    
                    # 高波动率警告
                    if volatility > VOLATILITY_HIGH:  # 年化波动率超过15%
                        logger.warning(f"[WARN]  {symbol}波动率过高: {volatility:.2%}")
                        
        except Exception as e:
            logger.error(f"[ERR] 监控市场风险失败: {e}")
    
    def _adjust_risk_level(self):
        """根据风险指标调整风险等级"""
        old_level = self.risk_params.risk_level
        
        # 基于多个指标综合判断
        risk_score = 0.0
        
        # 波动率贡献
        if self.risk_metrics.volatility > VOLATILITY_VERY_HIGH:
            risk_score += 0.4
        elif self.risk_metrics.volatility > VOLATILITY_HIGH:
            risk_score += 0.2
        elif self.risk_metrics.volatility < VOLATILITY_LOW:
            risk_score -= 0.1
        
        # 回撤贡献
        drawdown_ratio = 0.0
        if self.account_balance > 0:
            drawdown_ratio = self.risk_metrics.current_drawdown / self.account_balance
            if drawdown_ratio > 0.08:
                risk_score += 0.3
            elif drawdown_ratio > 0.05:
                risk_score += 0.15
            elif drawdown_ratio < 0.02:
                risk_score -= 0.1
        
        # 胜率贡献
        if self.risk_metrics.win_rate < 0.4:
            risk_score += 0.2
        elif self.risk_metrics.win_rate < 0.5:
            risk_score += 0.1
        elif self.risk_metrics.win_rate > 0.7:
            risk_score -= 0.1
        
        # 盈利因子贡献
        if self.risk_metrics.profit_factor < 1.0:
            risk_score += 0.2
        elif self.risk_metrics.profit_factor < 1.2:
            risk_score += 0.1
        elif self.risk_metrics.profit_factor > 2.0:
            risk_score -= 0.1
        
        # 确定风险等级（使用集中管理的阈值常量）
        if risk_score >= RISK_THRESHOLD_VERY_HIGH:
            new_level = RiskLevel.VERY_HIGH
        elif risk_score >= RISK_THRESHOLD_HIGH:
            new_level = RiskLevel.HIGH
        elif risk_score >= RISK_THRESHOLD_MEDIUM:
            new_level = RiskLevel.MEDIUM
        elif risk_score >= RISK_THRESHOLD_LOW:
            new_level = RiskLevel.LOW
        else:
            new_level = RiskLevel.VERY_LOW
        
        if new_level != old_level:
            self.risk_params.risk_level = new_level
            self._update_risk_parameters(new_level)
            logger.info(f"[REFRESH] 风险等级调整: {old_level.value} -> {new_level.value} (风险分数: {risk_score:.2f})")
    
    def _update_risk_parameters(self, risk_level: RiskLevel):
        """根据风险等级更新风险参数"""
        if risk_level == RiskLevel.VERY_LOW:
            # 极低风险：积极交易
            self.risk_params.max_position_size = 0.08      # 8%
            self.risk_params.risk_per_trade = 0.02         # 2%
            self.risk_params.stop_loss_pips = 25.0
            self.risk_params.take_profit_pips = 75.0
            self.risk_params.volatility_multiplier = 0.8   # 降低波动率影响
            
        elif risk_level == RiskLevel.LOW:
            # 低风险：正常偏积极
            self.risk_params.max_position_size = 0.06      # 6%
            self.risk_params.risk_per_trade = 0.015        # 1.5%
            self.risk_params.stop_loss_pips = 30.0
            self.risk_params.take_profit_pips = 60.0
            self.risk_params.volatility_multiplier = 0.9
            
        elif risk_level == RiskLevel.MEDIUM:
            # 中等风险：标准参数
            self.risk_params.max_position_size = 0.05      # 5%
            self.risk_params.risk_per_trade = 0.01         # 1%
            self.risk_params.stop_loss_pips = 30.0
            self.risk_params.take_profit_pips = 60.0
            self.risk_params.volatility_multiplier = 1.0
            
        elif risk_level == RiskLevel.HIGH:
            # 高风险：保守，缩小仓位但保持合理盈亏比
            self.risk_params.max_position_size = 0.03      # 3%
            self.risk_params.risk_per_trade = 0.005        # 0.5%
            self.risk_params.stop_loss_pips = 30.0         # 收紧止损
            self.risk_params.take_profit_pips = 45.0       # 保持1:1.5盈亏比
            self.risk_params.volatility_multiplier = 1.2   # 增加波动率影响
            
        elif risk_level == RiskLevel.VERY_HIGH:
            # 极高风险：极度保守，暂停交易或最小仓位
            self.risk_params.max_position_size = 0.01      # 1%
            self.risk_params.risk_per_trade = 0.002        # 0.2%
            self.risk_params.stop_loss_pips = 25.0         # 收紧止损至最小有效值
            self.risk_params.take_profit_pips = 40.0       # 保持1:1.6盈亏比
            self.risk_params.volatility_multiplier = 1.5
    
    def assess_trade_risk_with_real_data(self, symbol: str, action: str, confidence: float, 
                                         current_price: float) -> TradeRiskAssessment:
        """基于实时MQL5数据评估交易风险"""
        warning_messages = []
        
        try:
            # 从MQL5数据管理器获取实时数据
            realtime_data = self.mql5_data.get_real_time_data_summary()
            account_data = realtime_data.get("account_summary", {})
            positions_data = realtime_data.get("positions_summary", {})
            
            # 使用实时账户数据
            current_equity = account_data.get("equity", self.equity)
            current_margin_free = account_data.get("margin_free", 0)
            current_margin_level = account_data.get("margin_level", 0)
            
            # 检查当前持仓情况
            existing_positions_for_symbol = 0
            symbol_positions = positions_data.get("by_symbol", {}).get(symbol, {})
            if symbol_positions:
                existing_positions_for_symbol = symbol_positions.get("position_count", 0)
                existing_volume_for_symbol = symbol_positions.get("total_volume", 0)
                
                # 如果已有该品种持仓，提示注意
                if existing_positions_for_symbol > 0:
                    warning_messages.append(f"当前已有{existing_positions_for_symbol}个{symbol}持仓")
            
            # 检查点差（取自 src/strategy 的高精度闸门逻辑）
            tick_data = realtime_data.get("tick_summary", {})
            if tick_data:
                bid = tick_data.get("bid", 0)
                ask = tick_data.get("ask", 0)
                point = tick_data.get("point", 0.01)
                if bid > 0 and ask > 0 and point > 0:
                    spread_points = (ask - bid) / point
                    max_spread = 350.0  # 默认最大点差
                    if spread_points > max_spread:
                        warning_messages.append(
                            f"点差过大: {spread_points:.1f} > {max_spread:.1f}点"
                        )
                        logger.warning(f"[WARN]  {symbol}点差过大: {spread_points:.1f}点")
            
            # 检查broker止损水平（MT5硬限制，取自 src/strategy）
            symbol_info = tick_data.get("symbol_info", {})
            trade_stops_level = symbol_info.get("trade_stops_level", 0)
            if trade_stops_level > 0 and self.risk_params.stop_loss_pips < trade_stops_level:
                logger.warning(
                    f"[WARN]  止损距离 {self.risk_params.stop_loss_pips} 小于broker限制 {trade_stops_level}"
                )
            
            # 检查保证金水平，使用智能保证金管理器优化
            margin_advice = self.margin_manager.get_margin_advice_for_trade(
                symbol=symbol,
                position_size=0.1,  # 初始估算，后续会调整
                current_price=current_price
            )
            
            current_margin_level = margin_advice["margin_level"]
            margin_sufficient = margin_advice["margin_sufficient"]
            warning_level = margin_advice["warning_level"]
            
            # 根据保证金建议调整仓位乘数
            # 防御性检查：File模式EA无法推送实时账户数据，margin_free=0但margin_level虚高
            # 此时应跳过保证金限制，避免误杀
            is_data_incomplete = (
                not margin_sufficient 
                and current_margin_level > 200.0 
                and margin_advice.get("margin_available", 0) <= 0
            )
            if is_data_incomplete:
                logger.debug(f"[DATA] 保证金数据不完整(File模式/EA未推送)，跳过保证金限制")
                margin_multiplier = 1.0
            elif warning_level == "critical" or not margin_sufficient:
                warning_messages.append(f"[紧急] 保证金不足，无法开仓: 水平{current_margin_level:.1f}%")
                margin_multiplier = 0.0  # 完全禁止开仓
            elif warning_level == "high":
                warning_messages.append(f"[危险] 保证金占用率高: 水平{current_margin_level:.1f}%，建议减少仓位")
                margin_multiplier = 0.3
            elif warning_level == "medium":
                warning_messages.append(f"[警告] 保证金水平中等: {current_margin_level:.1f}%，需谨慎")
                margin_multiplier = 0.6
            elif warning_level == "low":
                margin_multiplier = 1.0
            else:
                # 保守默认
                if current_margin_level < MARGIN_WARNING:
                    warning_messages.append(f"保证金水平过低: {current_margin_level:.1f}%")
                    margin_multiplier = max(0.1, current_margin_level / 200.0)
                else:
                    margin_multiplier = 1.0
            
            # 获取市场波动率
            volatility = self.volatility_cache.get(symbol, 0.1)  # 默认10%波动率
            
            # 计算波动率调整乘数
            vol_multiplier = 1.0 + (volatility - 0.1) * 5  # 波动率每增加1%，乘数增加0.05
            
            # 调整止损止盈点数（考虑实时数据）
            adjusted_stop_loss = self.risk_params.stop_loss_pips * vol_multiplier * self.risk_params.volatility_multiplier * margin_multiplier
            adjusted_take_profit = self.risk_params.take_profit_pips * vol_multiplier * self.risk_params.volatility_multiplier * margin_multiplier
            
            # 根据置信度调整风险
            confidence_multiplier = 0.5 + confidence  # 置信度0.5->1.0, 1.0->1.5
            
            # 计算推荐仓位大小（使用实时权益）
            position_size = self._calculate_position_size_with_real_data(
                symbol, current_price, adjusted_stop_loss, confidence_multiplier, current_equity
            )
            
            # 如果已有该品种持仓，减少新开仓规模
            if existing_positions_for_symbol > 0:
                position_size = position_size * max(0.1, 1.0 - existing_positions_for_symbol * 0.3)
                warning_messages.append(f"因已有持仓，仓位规模减少")
            
            # 计算止损止盈价格
            stop_loss_price, take_profit_price = self._calculate_stop_take_prices(
                symbol, action, current_price, adjusted_stop_loss, adjusted_take_profit
            )
            
            # 计算风险回报比（单位统一为美元）
            # adjusted_stop_loss 单位 = pip, pip_value = $/pip/标准手
            pip_value = self._get_pip_value(symbol, current_price)
            risk_per_lot = adjusted_stop_loss * pip_value  # 每手风险（美元）
            risk_amount = position_size * risk_per_lot  # 总风险金额（美元）
            reward_amount = position_size * adjusted_take_profit * pip_value  # 预期盈利（美元）
            
            risk_reward_ratio = reward_amount / risk_amount if risk_amount > 0 else 0
            
            # 计算期望价值
            expected_value = (confidence * reward_amount) - ((1 - confidence) * risk_amount)
            
            # 计算风险评分
            risk_score = self._calculate_risk_score(
                volatility, confidence, position_size, risk_reward_ratio
            )
            
            # 确定风险等级
            risk_level = self._determine_trade_risk_level(risk_score)
            
            # 生成警告信息
            if risk_score > 0.7:
                warning_messages.append("[WARN]  高风险交易：建议减少仓位或放弃")
            elif risk_score > 0.5:
                warning_messages.append("[WARN]  中等风险：建议调整止损或减少仓位")
            
            if risk_reward_ratio < 1.0:
                warning_messages.append("[WARN]  风险回报比低于1:1，不推荐")
            
            # 仓位验证：如果仓位远小于理论计算值，可能是保证金限制导致
            max_lots_by_margin_val = margin_advice.get("recommended_max_position", position_size)
            if position_size > 0.01 and position_size < 0.1 and max_lots_by_margin_val > 0.2:
                warning_messages.append("[WARN]  理论仓位较大但实际受限，建议检查保证金")
            
            # 构建风险评估结果
            assessment = TradeRiskAssessment(
                symbol=symbol,
                action=action,
                confidence=confidence,
                recommended_position_size=position_size,
                recommended_stop_loss=stop_loss_price,
                recommended_take_profit=take_profit_price,
                risk_reward_ratio=risk_reward_ratio,
                expected_value=expected_value,
                risk_score=risk_score,
                risk_level=risk_level,
                warning_messages=warning_messages
            )
            
            logger.info(f"[RM]  交易风险评估: {symbol} {action}, "
                       f"仓位: {position_size:.3f}, 风险评分: {risk_score:.2f}, "
                       f"风险回报比: {risk_reward_ratio:.2f}")
            
            return assessment
            
        except Exception as e:
            logger.error(f"[ERR] 交易风险评估失败: {e}")
            
            # 返回保守的默认评估
            return TradeRiskAssessment(
                symbol=symbol,
                action=action,
                confidence=confidence,
                recommended_position_size=0.01,
                recommended_stop_loss=current_price * 0.99 if action == "BUY" else current_price * 1.01,
                recommended_take_profit=current_price * 1.01 if action == "BUY" else current_price * 0.99,
                risk_reward_ratio=1.0,
                expected_value=0.0,
                risk_score=0.8,
                risk_level=RiskLevel.HIGH,
                warning_messages=[f"风险评估失败: {str(e)}"]
            )
    
    def assess_trade_risk(self, symbol: str, action: str, confidence: float, 
                         current_price: float) -> TradeRiskAssessment:
        """评估交易风险（兼容性包装，调用实时数据版本）"""
        return self.assess_trade_risk_with_real_data(symbol, action, confidence, current_price)
    
    def _calculate_position_size_with_real_data(self, symbol: str, current_price: float, 
                                               stop_loss_pips: float, confidence_multiplier: float, 
                                               current_equity: float) -> float:
        """基于实时MQL5数据计算仓位大小"""
        try:
            # 从MQL5数据管理器获取实时数据
            realtime_data = self.mql5_data.get_real_time_data_summary()
            account_data = realtime_data.get("account_summary", {})
            positions_data = realtime_data.get("positions_summary", {})
            
            # 使用实时权益计算风险金额
            risk_amount = current_equity * self.risk_params.risk_per_trade * confidence_multiplier
            
            # 获取智能保证金建议
            margin_advice = self.margin_manager.get_margin_advice_for_trade(
                symbol=symbol,
                position_size=0.1,  # 初始估算值
                current_price=current_price
            )
            
            margin_free = margin_advice["margin_available"]
            recommended_max_position = margin_advice["recommended_max_position"]
            margin_sufficient = margin_advice["margin_sufficient"]
            
            # 计算每pip价值（统一单位：pip）
            pip_value = self._get_pip_value(symbol, current_price)
            
            # 计算每手风险金额
            # stop_loss_pips 单位 = pip, pip_value = $/pip/标准手
            risk_per_lot = stop_loss_pips * pip_value
            
            if risk_per_lot <= 0:
                return 0.01  # 最小仓位
            
            # 计算基础手数
            lots = risk_amount / risk_per_lot
            
            # 应用多重限制（优先级从高到低）
            # 1. 保证金是否充足（强制限制）
            if not margin_sufficient:
                logger.warning(f"[WARN] 保证金不足，仓位限制为最小")
                return 0.01
            
            # 2. 智能保证金管理器推荐的最大仓位
            max_lots_by_margin = recommended_max_position
            
            # 3. 最大仓位限制（基于权益）
            max_lots_by_equity = (current_equity * self.risk_params.max_position_size) / (current_price * 100000)
            
            # 4. 波动率调整限制
            volatility = self.volatility_cache.get(symbol, 0.1)
            vol_multiplier = 1.0
            if volatility > VOLATILITY_VERY_HIGH:
                vol_multiplier = 0.25
            elif volatility > VOLATILITY_HIGH:
                vol_multiplier = 0.5
            elif volatility < VOLATILITY_LOW:
                vol_multiplier = 1.5
            
            # 5. 保证金水平调整
            margin_level = margin_advice["margin_level"]
            margin_multiplier = 1.0
            if margin_level < MARGIN_DANGER:
                margin_multiplier = 0.1
            elif margin_level < MARGIN_WARNING:
                margin_multiplier = 0.3
            elif margin_level < MARGIN_NORMAL:
                margin_multiplier = 0.7
            elif margin_level > MARGIN_COMFORTABLE:
                margin_multiplier = 1.2
            
            # 综合所有限制
            max_allowed_lots = min(max_lots_by_margin, max_lots_by_equity, 100.0)
            position_size = lots * vol_multiplier * margin_multiplier
            position_size = max(0.01, min(position_size, max_allowed_lots))
            
            # 根据仓位大小计算方法调整
            if self.risk_params.position_sizing_method == PositionSizingMethod.KELLY_CRITERION:
                # 凯利公式：f = (bp - q) / b
                win_rate = self.risk_metrics.win_rate
                avg_win = self.risk_metrics.risk_reward_ratio * 1.0  # 假设风险回报比
                avg_loss = 1.0
                
                b = avg_win / avg_loss  # 盈亏比
                p = win_rate
                q = 1 - win_rate
                
                if b > 0:
                    kelly_fraction = (b * p - q) / b
                    position_size *= max(0.1, min(kelly_fraction, 0.25))  # 限制在10%-25%之间
            
            elif self.risk_params.position_sizing_method == PositionSizingMethod.VOLATILITY_ADJUSTED:
                # 波动率调整：降低高波动品种的仓位
                volatility = self.volatility_cache.get(symbol, 0.1)
                if volatility > VOLATILITY_HIGH:
                    position_size *= 0.5
                elif volatility > VOLATILITY_VERY_HIGH:
                    position_size *= 0.25
            
            return round(position_size, 2)  # 保留两位小数
            
        except Exception as e:
            logger.error(f"[ERR] 计算仓位大小失败: {e}")
            return 0.01
    
    def _calculate_position_size(self, symbol: str, current_price: float, 
                                stop_loss_pips: float, confidence_multiplier: float) -> float:
        """计算仓位大小（兼容性方法）"""
        # 调用实时数据版本，使用当前权益
        return self._calculate_position_size_with_real_data(
            symbol, current_price, stop_loss_pips, confidence_multiplier, self.equity
        )
    
    def _get_pip_value(self, symbol: str, price: float) -> float:
        """
        获取每 pip 的美元价值（标准手）
        
        单位体系:
        - 黄金/XAUUSD: 1 pip = 0.10 价格单位 = 10 MT5 Points, 1 pip ≈ $10.00 (标准手)
        - 外汇: 1 pip = 0.0001 价格单位 = 10 MT5 Points, 1 pip ≈ $10.00 (标准手)
        - 日元对: 1 pip = 0.01 价格单位 = 100 MT5 Points, 1 pip ≈ $9.26 (标准手)
        
        本项目约定: stop_loss_pips/take_profit_pips 单位均为 pips
        """
        try:
            if "JPY" in symbol:
                return 9.26  # 日元对：每pip约$9.26（标准手）
            elif "XAU" in symbol.upper() or "GOLD" in symbol.upper():
                return 10.0  # 黄金：每pip约$10.00（标准手）
            else:
                return 10.0  # 主要货币对：每pip约$10.00（标准手）
                
        except Exception as e:
            logger.error(f"[ERR] 计算每pip价值失败: {e}")
            return 10.0
    
    def _calculate_stop_take_prices(self, symbol: str, action: str, current_price: float,
                                   stop_loss_pips: float, take_profit_pips: float) -> Tuple[float, float]:
        """
        计算止损止盈价格
        
        单位转换: pips → 价格距离
        - 黄金: 1 pip = 0.10 价格单位 (10 * _Point, _Point=0.01)
        - 外汇: 1 pip = 0.0001 价格单位 (5位报价)
        - 日元: 1 pip = 0.01 价格单位
        """
        try:
            # pip → 价格距离的转换因子
            if is_jpy_pair(symbol):
                pip_size = 0.01
            elif is_gold(symbol):
                pip_size = 0.10  # 1 pip = 0.10 (10 * 0.01 MT5 Point)
            else:
                pip_size = 0.0001  # 1 pip = 0.0001 (5位报价)
            
            if action == "BUY":
                stop_loss_price = current_price - (stop_loss_pips * pip_size)
                take_profit_price = current_price + (take_profit_pips * pip_size)
            else:  # SELL
                stop_loss_price = current_price + (stop_loss_pips * pip_size)
                take_profit_price = current_price - (take_profit_pips * pip_size)
            
            # 确保止损止盈价格合理
            if action == "BUY":
                if stop_loss_price >= current_price:
                    stop_loss_price = current_price * 0.995
                if take_profit_price <= current_price:
                    take_profit_price = current_price * 1.005
            else:
                if stop_loss_price <= current_price:
                    stop_loss_price = current_price * 1.005
                if take_profit_price >= current_price:
                    take_profit_price = current_price * 0.995
            
            return stop_loss_price, take_profit_price
            
        except Exception as e:
            logger.error(f"[ERR] 计算止损止盈价格失败: {e}")
            # 返回保守的默认值
            if action == "BUY":
                return current_price * 0.99, current_price * 1.01
            else:
                return current_price * 1.01, current_price * 0.99
    
    def _calculate_risk_score(self, volatility: float, confidence: float, 
                             position_size: float, risk_reward_ratio: float) -> float:
        """计算风险评分（0-1，越高风险越大）"""
        try:
            risk_score = 0.0
            
            # 波动率贡献（0-0.25） - 核心风险因素
            volatility_score = min(volatility / 0.3, 1.0) * 0.25
            risk_score += volatility_score
            
            # 置信度贡献（0-0.2，置信度越低风险越高） - 决策质量
            confidence_score = (1.0 - confidence) * 0.2
            risk_score += confidence_score
            
            # 仓位大小贡献（0-0.15） - 降低权重，避免仓位变化时评分跳变
            # 0.01-0.05手视为低仓位(0-0.05)，0.05-0.1手中等(0.05-0.1)，0.1+高仓位
            if position_size <= POSITION_MICRO:
                position_score = 0.0  # 极小仓位无额外风险
            elif position_size <= POSITION_SMALL:
                position_score = 0.05
            elif position_size <= POSITION_MEDIUM:
                position_score = 0.1
            else:
                position_score = 0.15
            risk_score += position_score
            
            # 风险回报比贡献（0-0.15）
            if risk_reward_ratio < 1.0:
                rr_score = (1.0 - risk_reward_ratio) * 0.25
                risk_score += rr_score
            elif risk_reward_ratio >= 2.0:
                # 高盈亏比降低风险
                risk_score -= 0.05
            
            # 趋势持续性风险（0-0.1） - 基于近期连续同向交易
            if hasattr(self, 'risk_metrics') and self.risk_metrics:
                recent_trades = getattr(self.risk_metrics, 'recent_trades', [])
                if len(recent_trades) >= 5:
                    # 计算最近5笔交易的方向一致性
                    directions = [t.get('direction') for t in recent_trades[-5:] if t.get('direction')]
                    if directions:
                        same_direction_ratio = directions.count(directions[0]) / len(directions)
                        if same_direction_ratio >= 0.8:  # 80%以上同向
                            trend_persistence_score = 0.1 * same_direction_ratio
                            risk_score += trend_persistence_score
            
            # 市场时段风险（0-0.05） - 低流动性时段风险略高
            current_hour = dt.datetime.now().hour
            if current_hour < 7 or current_hour > 22:  # 非活跃时段
                risk_score += 0.03
            elif 7 <= current_hour <= 8 or 20 <= current_hour <= 22:  # 开盘前后
                risk_score += 0.02
            
            # 确保评分在有效范围内
            return max(0.05, min(risk_score, 0.95))  # 设置最小0.05，避免评分为0
            
        except Exception as e:
            logger.error(f"[ERR] 计算风险评分失败: {e}")
            return 0.5
    
    def _determine_trade_risk_level(self, risk_score: float) -> RiskLevel:
        """根据风险评分确定交易风险等级"""
        if risk_score >= RISK_THRESHOLD_VERY_HIGH:
            return RiskLevel.VERY_HIGH
        elif risk_score >= RISK_THRESHOLD_HIGH:
            return RiskLevel.HIGH
        elif risk_score >= RISK_THRESHOLD_MEDIUM:
            return RiskLevel.MEDIUM
        elif risk_score >= RISK_THRESHOLD_LOW:
            return RiskLevel.LOW
        else:
            return RiskLevel.VERY_LOW
    
    def can_open_position(self, symbol: str, position_size: float) -> bool:
        """检查是否可以开仓"""
        try:
            # 检查最大仓位限制
            max_position_value = self.account_balance * self.risk_params.max_position_size
            position_value = position_size * 100000  # 简化计算
            
            if position_value > max_position_value:
                logger.warning(f"[WARN]  仓位超过最大限制: {position_value:.2f} > {max_position_value:.2f}")
                return False
            
            # 检查连续亏损
            if self.risk_metrics.consecutive_losses >= self.risk_params.max_consecutive_losses:
                logger.warning(f"[WARN]  连续亏损{self.risk_metrics.consecutive_losses}次，暂停开仓")
                return False
            
            # 检查当前回撤
            if self.risk_metrics.current_drawdown > self.account_balance * 0.1:  # 超过10%回撤
                logger.warning(f"[WARN]  当前回撤{self.risk_metrics.current_drawdown:.2f}，暂停开仓")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"[ERR] 检查开仓条件失败: {e}")
            return False
    
    def update_account_state(self, balance: float, equity: float, profit: float):
        """更新账户状态"""
        self.account_balance = balance
        self.equity = equity
        
        # 更新连续亏损计数
        if profit < 0:
            self.risk_metrics.consecutive_losses += 1
        else:
            self.risk_metrics.consecutive_losses = 0
        
        # 记录每日盈亏
        self.daily_pnl.append(profit)
        if len(self.daily_pnl) > 100:
            self.daily_pnl = self.daily_pnl[-100:]
    
    def get_risk_report(self) -> Dict[str, Any]:
        """获取风险报告"""
        return {
            "account": {
                "balance": self.account_balance,
                "equity": self.equity,
                "margin_used": self.account_balance - self.equity,
                "free_margin": self.equity
            },
            "risk_parameters": {
                "risk_level": self.risk_params.risk_level.value,
                "max_position_size": self.risk_params.max_position_size,
                "risk_per_trade": self.risk_params.risk_per_trade,
                "stop_loss_pips": self.risk_params.stop_loss_pips,
                "take_profit_pips": self.risk_params.take_profit_pips,
                "position_sizing_method": self.risk_params.position_sizing_method.value
            },
            "risk_metrics": {
                "volatility": self.risk_metrics.volatility,
                "sharpe_ratio": self.risk_metrics.sharpe_ratio,
                "max_drawdown": self.risk_metrics.max_drawdown,
                "current_drawdown": self.risk_metrics.current_drawdown,
                "var_95": self.risk_metrics.var_95,
                "expected_shortfall": self.risk_metrics.expected_shortfall,
                "win_rate": self.risk_metrics.win_rate,
                "profit_factor": self.risk_metrics.profit_factor,
                "risk_reward_ratio": self.risk_metrics.risk_reward_ratio,
                "consecutive_losses": self.risk_metrics.consecutive_losses
            },
            "market_volatility": dict(self.volatility_cache),
            "timestamp": datetime.now().isoformat()
        }


# 全局风险管理器实例
_global_risk_manager: Optional[RiskManager] = None


def get_risk_manager(account_balance: float = 10000.0) -> RiskManager:
    """获取全局风险管理器实例"""
    global _global_risk_manager
    if not _global_risk_manager:
        _global_risk_manager = RiskManager(account_balance)
    return _global_risk_manager


if __name__ == "__main__":
    # 测试风险管理系统
    print("="*70)
    print("[TOOL] 测试自适应风险管理系统")
    print("="*70)
    
    risk_manager = RiskManager(account_balance=10000.0)
    
    # 启动风险监控
    risk_manager.start()
    
    # 测试交易风险评估
    print("\n[RM]  测试交易风险评估...")
    assessment = risk_manager.assess_trade_risk(
        symbol="EURUSD",
        action="BUY",
        confidence=0.75,
        current_price=1.0850
    )
    
    if assessment:
        print(f"[OK] 风险评估完成:")
        print(f"   推荐仓位: {assessment.recommended_position_size:.3f}手")
        print(f"   推荐止损: {assessment.recommended_stop_loss:.5f}")
        print(f"   推荐止盈: {assessment.recommended_take_profit:.5f}")
        print(f"   风险回报比: {assessment.risk_reward_ratio:.2f}")
        print(f"   风险评分: {assessment.risk_score:.2f}")
        print(f"   风险等级: {assessment.risk_level.value}")
        
        if assessment.warning_messages:
            print("   [WARN]  警告信息:")
            for msg in assessment.warning_messages:
                print(f"     - {msg}")
    
    # 测试开仓条件检查
    print("\n[RM]  测试开仓条件检查...")
    can_open = risk_manager.can_open_position("EURUSD", 0.1)
    print(f"   可以开仓: {'是' if can_open else '否'}")
    
    # 获取风险报告
    print("\n[DATA] 风险报告:")
    report = risk_manager.get_risk_report()
    print(f"   账户余额: ${report['account']['balance']:.2f}")
    print(f"   风险等级: {report['risk_parameters']['risk_level']}")
    print(f"   最大仓位: {report['risk_parameters']['max_position_size']*100:.1f}%")
    print(f"   每笔交易风险: {report['risk_parameters']['risk_per_trade']*100:.1f}%")
    
    # 停止风险监控
    risk_manager.stop()
    
    print("\n[OK] 自适应风险管理系统测试完成！")