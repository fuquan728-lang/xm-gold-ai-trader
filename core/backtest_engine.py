#!/usr/bin/env python3
"""
专业回测引擎 — Event-Driven Backtesting Framework

特性:
1. 严格逐Bar处理，无Look-ahead Bias
2. 真实滑点/佣金模型（XM经纪商规格）
3. Walk-Forward分析支持
4. 完整绩效报告（Sharpe/Sortino/Calmar/最大回撤/胜率/盈亏比）
5. 交易日志导出

数据格式: HistData.com CSV (time,open,high,low,close,tick_volume,spread,real_volume)
"""

import csv
import json
import math
import time
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple, Callable
from dataclasses import dataclass, field
from enum import Enum

import numpy as np

from core.logger import logger


# ==================== 数据模型 ====================

class OrderType(Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"


class OrderSide(Enum):
    BUY = "buy"
    SELL = "sell"


class OrderStatus(Enum):
    PENDING = "pending"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


@dataclass
class Bar:
    """单根K线数据"""
    time: datetime
    open: float
    high: float
    low: float
    close: float
    tick_volume: int = 0
    spread: float = 0.0


@dataclass
class Order:
    """订单"""
    id: int
    side: OrderSide
    order_type: OrderType
    volume: float
    price: float = 0.0          # 限价/止损价
    sl: float = 0.0
    tp: float = 0.0
    status: OrderStatus = OrderStatus.PENDING
    fill_price: float = 0.0
    fill_time: Optional[datetime] = None
    close_price: float = 0.0
    close_time: Optional[datetime] = None
    profit: float = 0.0
    profit_pct: float = 0.0
    exit_reason: str = ""


@dataclass
class Trade:
    """已完成交易记录"""
    id: int
    side: OrderSide
    entry_time: datetime
    entry_price: float
    exit_time: datetime
    exit_price: float
    volume: float
    profit: float
    profit_pct: float
    bars_held: int
    exit_reason: str
    sl_hit: bool = False
    tp_hit: bool = False


@dataclass
class BacktestResult:
    """回测结果"""
    symbol: str
    start_date: str
    end_date: str
    total_bars: int
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    total_profit: float
    total_loss: float
    net_profit: float
    profit_factor: float
    avg_win: float
    avg_loss: float
    max_drawdown: float
    max_drawdown_pct: float
    sharpe_ratio: float
    sortino_ratio: float
    calmar_ratio: float
    expectancy: float
    avg_bars_held: float
    commission_paid: float
    slippage_total: float

    # 权益曲线
    equity_curve: List[float] = field(default_factory=list)
    drawdown_curve: List[float] = field(default_factory=list)

    # 交易列表
    trades: List[Trade] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "period": f"{self.start_date} → {self.end_date}",
            "total_bars": self.total_bars,
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "win_rate_pct": round(self.win_rate * 100, 2),
            "net_profit": round(self.net_profit, 2),
            "profit_factor": round(self.profit_factor, 2),
            "avg_win": round(self.avg_win, 2),
            "avg_loss": round(self.avg_loss, 2),
            "max_drawdown_pct": round(self.max_drawdown_pct * 100, 2),
            "sharpe_ratio": round(self.sharpe_ratio, 2),
            "sortino_ratio": round(self.sortino_ratio, 2),
            "calmar_ratio": round(self.calmar_ratio, 2),
            "expectancy": round(self.expectancy, 2),
            "avg_bars_held": round(self.avg_bars_held, 1),
            "commission_paid": round(self.commission_paid, 2),
            "slippage_total": round(self.slippage_total, 2)
        }


# ==================== 数据加载器 ====================

class DataLoader:
    """HistData.com CSV 数据加载器"""

    @staticmethod
    def load_csv(filepath: str) -> List[Bar]:
        """加载CSV文件"""
        bars = []
        with open(filepath, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    bar = Bar(
                        time=datetime.fromisoformat(row['time']),
                        open=float(row['open']),
                        high=float(row['high']),
                        low=float(row['low']),
                        close=float(row['close']),
                        tick_volume=int(row.get('tick_volume', 0)),
                        spread=float(row.get('spread', 0))
                    )
                    bars.append(bar)
                except (ValueError, KeyError) as e:
                    continue
        return bars

    @staticmethod
    def split_train_test(bars: List[Bar], train_ratio: float = 0.7) -> Tuple[List[Bar], List[Bar]]:
        """按时间顺序分割训练/测试集"""
        split_idx = int(len(bars) * train_ratio)
        return bars[:split_idx], bars[split_idx:]


# ==================== 经纪商模型 ====================

@dataclass
class BrokerConfig:
    """XM经纪商配置"""
    # 黄金(XAUUSD)规格
    commission_per_lot: float = 0.0       # XM零佣金账户
    spread_pips: float = 1.5              # 典型点差(pips)
    min_sl_distance_pips: float = 10.0    # 最小止损距离
    contract_size: float = 100.0          # 合约大小(盎司)
    pip_value_per_lot: float = 10.0       # 每pip价值($, 标准手)
    slippage_pips_default: float = 0.3    # 默认滑点(pips)
    slippage_pips_news: float = 2.0       # 新闻时段滑点


class BrokerSimulator:
    """经纪商模拟器 — 滑点/佣金/保证金"""

    def __init__(self, config: BrokerConfig = None):
        self.config = config or BrokerConfig()
        self.total_commission = 0.0
        self.total_slippage = 0.0

    def apply_slippage(self, price: float, side: OrderSide, 
                       is_news_time: bool = False) -> float:
        """应用滑点（不利方向）"""
        slippage_pips = self.config.slippage_pips_news if is_news_time else self.config.slippage_pips_default
        slippage_price = slippage_pips * 0.10  # pips→价格距离

        if side == OrderSide.BUY:
            price += slippage_price  # 买入滑点向上
        else:
            price -= slippage_price  # 卖出滑点向下

        self.total_slippage += slippage_pips * 10.0  # $10/pip * pips
        return price

    def calculate_commission(self, volume: float) -> float:
        """计算佣金"""
        comm = self.config.commission_per_lot * volume
        self.total_commission += comm
        return comm

    def calculate_profit(self, side: OrderSide, entry: float, exit: float, 
                         volume: float) -> float:
        """计算交易盈亏"""
        if side == OrderSide.BUY:
            pips = (exit - entry) / 0.10
        else:
            pips = (entry - exit) / 0.10

        gross_profit = pips * self.config.pip_value_per_lot * volume
        commission = self.calculate_commission(volume)
        return gross_profit - commission


# ==================== 回测引擎核心 ====================

class BacktestEngine:
    """
    事件驱动回测引擎
    
    核心原则:
    1. 严格逐Bar处理 — 只使用当前Bar及之前的数据
    2. 信号在Bar开盘生成，在Bar收盘价执行
    3. 止损止盈在Bar内逐tick检查（使用High/Low模拟）
    """

    def __init__(self, 
                 initial_balance: float = 10000.0,
                 broker_config: BrokerConfig = None):
        self.initial_balance = initial_balance
        self.balance = initial_balance
        self.equity = initial_balance
        self.broker = BrokerSimulator(broker_config)

        # 订单/持仓管理
        self.orders: List[Order] = []
        self.open_positions: List[Order] = []
        self.closed_trades: List[Trade] = []
        self._order_id_counter = 1

        # 权益曲线
        self.equity_curve: List[float] = [initial_balance]
        self._peak_equity = initial_balance

        # 当前处理Bar索引
        self._current_bar_index = 0
        self._current_bar: Optional[Bar] = None

        # 信号生成器（外部注入）
        self.signal_generator: Optional[Callable] = None

    # ---- 订单管理 ----

    def submit_order(self, side: OrderSide, order_type: OrderType,
                     volume: float, price: float = 0.0,
                     sl_pips: float = 0.0, tp_pips: float = 0.0) -> int:
        """提交订单，返回订单ID"""
        if order_type == OrderType.MARKET:
            # 市价单应用滑点
            fill_price = self.broker.apply_slippage(
                self._current_bar.close, side
            )
        else:
            fill_price = price

        # 计算止损止盈价格
        sl_price = 0.0
        tp_price = 0.0
        if sl_pips > 0:
            if side == OrderSide.BUY:
                sl_price = fill_price - sl_pips * 0.10
                tp_price = fill_price + tp_pips * 0.10 if tp_pips > 0 else 0
            else:
                sl_price = fill_price + sl_pips * 0.10
                tp_price = fill_price - tp_pips * 0.10 if tp_pips > 0 else 0

        order = Order(
            id=self._order_id_counter,
            side=side,
            order_type=order_type,
            volume=volume,
            price=price,
            sl=sl_price,
            tp=tp_price,
            status=OrderStatus.FILLED if order_type == OrderType.MARKET else OrderStatus.PENDING,
            fill_price=fill_price,
            fill_time=self._current_bar.time
        )
        self._order_id_counter += 1

        if order.status == OrderStatus.FILLED:
            self.open_positions.append(order)
        else:
            self.orders.append(order)

        return order.id

    def close_position(self, order: Order, exit_price: float, 
                       exit_time: datetime, exit_reason: str):
        """平仓"""
        order.close_price = exit_price
        order.close_time = exit_time
        order.exit_reason = exit_reason

        # 计算盈亏
        order.profit = self.broker.calculate_profit(
            order.side, order.fill_price, exit_price, order.volume
        )
        order.profit_pct = order.profit / (self.initial_balance) * 100 if self.initial_balance > 0 else 0

        # 创建交易记录
        trade = Trade(
            id=order.id,
            side=order.side,
            entry_time=order.fill_time,
            entry_price=order.fill_price,
            exit_time=exit_time,
            exit_price=exit_price,
            volume=order.volume,
            profit=order.profit,
            profit_pct=order.profit_pct,
            bars_held=self._current_bar_index - getattr(order, '_entry_bar_idx', 0),
            exit_reason=exit_reason,
            sl_hit="sl" in exit_reason.lower(),
            tp_hit="tp" in exit_reason.lower()
        )
        self.closed_trades.append(trade)

        # 更新余额
        self.balance += order.profit

    # ---- Bar处理 ----

    def process_bar(self, bar: Bar, bar_index: int) -> Tuple[Optional[OrderSide], float]:
        """
        处理单根Bar
        
        Returns:
            (signal_side, signal_price): 生成的信号
        """
        self._current_bar = bar
        self._current_bar_index = bar_index

        # 1. 检查挂单是否触发
        self._check_pending_orders(bar)

        # 2. 检查持仓的止损/止盈
        self._check_position_stops(bar)

        # 3. 调用策略生成信号
        signal_side = None
        if self.signal_generator:
            signal_side = self.signal_generator(bar, bar_index, self)

        # 4. 更新权益
        self._update_equity(bar.close)

        return signal_side, bar.close

    def _check_pending_orders(self, bar: Bar):
        """检查挂单触发"""
        for order in list(self.orders):
            triggered = False
            if order.order_type == OrderType.LIMIT:
                if order.side == OrderSide.BUY and bar.low <= order.price:
                    order.fill_price = min(order.price, bar.open)
                    triggered = True
                elif order.side == OrderSide.SELL and bar.high >= order.price:
                    order.fill_price = max(order.price, bar.open)
                    triggered = True
            elif order.order_type == OrderType.STOP:
                if order.side == OrderSide.BUY and bar.high >= order.price:
                    order.fill_price = max(order.price, bar.open)
                    triggered = True
                elif order.side == OrderSide.SELL and bar.low <= order.price:
                    order.fill_price = min(order.price, bar.open)
                    triggered = True

            if triggered:
                order.status = OrderStatus.FILLED
                order.fill_time = bar.time
                self.orders.remove(order)
                self.open_positions.append(order)

    def _check_position_stops(self, bar: Bar):
        """检查持仓止损止盈（使用Bar内High/Low模拟tick级检查）"""
        for pos in list(self.open_positions):
            exit_price = None
            exit_reason = ""

            if pos.side == OrderSide.BUY:
                # BUY: SL低于进场价，TP高于进场价
                if pos.sl > 0 and bar.low <= pos.sl:
                    exit_price = pos.sl
                    exit_reason = "sl_hit"
                elif pos.tp > 0 and bar.high >= pos.tp:
                    exit_price = pos.tp
                    exit_reason = "tp_hit"
            else:
                # SELL: SL高于进场价，TP低于进场价
                if pos.sl > 0 and bar.high >= pos.sl:
                    exit_price = pos.sl
                    exit_reason = "sl_hit"
                elif pos.tp > 0 and bar.low <= pos.tp:
                    exit_price = pos.tp
                    exit_reason = "tp_hit"

            if exit_price:
                self.close_position(pos, exit_price, bar.time, exit_reason)
                self.open_positions.remove(pos)

    def _update_equity(self, current_price: float):
        """更新权益和权益曲线"""
        floating_profit = 0.0
        for pos in self.open_positions:
            if pos.side == OrderSide.BUY:
                floating_profit += (current_price - pos.fill_price) / 0.10 * \
                                   self.broker.config.pip_value_per_lot * pos.volume
            else:
                floating_profit += (pos.fill_price - current_price) / 0.10 * \
                                   self.broker.config.pip_value_per_lot * pos.volume

        self.equity = self.balance + floating_profit
        self._peak_equity = max(self._peak_equity, self.equity)
        self.equity_curve.append(self.equity)

    # ---- 批量运行 ----

    def run(self, bars: List[Bar], signal_generator: Optional[Callable] = None) -> BacktestResult:
        """运行回测"""
        if signal_generator:
            self.signal_generator = signal_generator

        start_time = time.time()
        for i, bar in enumerate(bars):
            self.process_bar(bar, i)

        # 收盘强制平仓所有持仓
        if self.open_positions:
            last_bar = bars[-1]
            for pos in list(self.open_positions):
                self.close_position(pos, last_bar.close, last_bar.time, "force_close_eod")
                self.open_positions.remove(pos)

        elapsed = time.time() - start_time
        logger.info(f"[BT] Backtest complete: {len(bars)} bars in {elapsed:.2f}s "
                     f"({len(bars)/elapsed:.0f} bars/s)")

        return self._generate_result(bars)

    def _generate_result(self, bars: List[Bar]) -> BacktestResult:
        """生成回测结果"""
        trades = self.closed_trades
        n = len(trades)

        if n == 0:
            return BacktestResult(
                symbol="", start_date="", end_date="",
                total_bars=len(bars), total_trades=0,
                winning_trades=0, losing_trades=0, win_rate=0,
                total_profit=0, total_loss=0, net_profit=0,
                profit_factor=0, avg_win=0, avg_loss=0,
                max_drawdown=0, max_drawdown_pct=0,
                sharpe_ratio=0, sortino_ratio=0, calmar_ratio=0,
                expectancy=0, avg_bars_held=0,
                commission_paid=0, slippage_total=0,
                equity_curve=self.equity_curve
            )

        winning = [t for t in trades if t.profit > 0]
        losing = [t for t in trades if t.profit <= 0]
        profits = [t.profit for t in trades]

        total_profit = sum(t.profit for t in winning) if winning else 0
        total_loss = abs(sum(t.profit for t in losing)) if losing else 0
        net_profit = self.balance - self.initial_balance
        profit_factor = total_profit / total_loss if total_loss > 0 else float('inf')
        win_rate = len(winning) / n if n > 0 else 0
        avg_win = total_profit / len(winning) if winning else 0
        avg_loss = total_loss / len(losing) if losing else 0

        # 回撤计算
        equity_arr = np.array(self.equity_curve)
        running_max = np.maximum.accumulate(equity_arr)
        drawdowns = (running_max - equity_arr) / running_max
        max_dd = np.max(drawdowns) if len(drawdowns) > 0 else 0
        max_dd_amount = np.max(running_max - equity_arr) if len(equity_arr) > 0 else 0

        # 风险指标
        returns = np.diff(equity_arr) / equity_arr[:-1] if len(equity_arr) > 1 else np.array([0])
        sharpe = np.mean(returns) / np.std(returns) * np.sqrt(252) if np.std(returns) > 0 else 0

        neg_returns = returns[returns < 0]
        sortino = np.mean(returns) / np.std(neg_returns) * np.sqrt(252) if len(neg_returns) > 0 and np.std(neg_returns) > 0 else 0

        calmar = (net_profit / self.initial_balance) / max_dd if max_dd > 0 else 0
        if net_profit < 0 and max_dd > 0:
            calmar = net_profit / self.initial_balance / max_dd

        expectancy = np.mean(profits) if n > 0 else 0
        avg_bars = np.mean([t.bars_held for t in trades]) if n > 0 else 0

        return BacktestResult(
            symbol="XAUUSD",
            start_date=bars[0].time.strftime("%Y-%m-%d") if bars else "",
            end_date=bars[-1].time.strftime("%Y-%m-%d") if bars else "",
            total_bars=len(bars),
            total_trades=n,
            winning_trades=len(winning),
            losing_trades=len(losing),
            win_rate=win_rate,
            total_profit=total_profit,
            total_loss=total_loss,
            net_profit=net_profit,
            profit_factor=profit_factor,
            avg_win=avg_win,
            avg_loss=avg_loss,
            max_drawdown=max_dd_amount,
            max_drawdown_pct=max_dd,
            sharpe_ratio=sharpe,
            sortino_ratio=sortino,
            calmar_ratio=calmar,
            expectancy=expectancy,
            avg_bars_held=avg_bars,
            commission_paid=self.broker.total_commission,
            slippage_total=self.broker.total_slippage,
            equity_curve=self.equity_curve,
            drawdown_curve=drawdowns.tolist(),
            trades=trades
        )

    def reset(self):
        """重置引擎状态"""
        self.balance = self.initial_balance
        self.equity = self.initial_balance
        self.broker.total_commission = 0.0
        self.broker.total_slippage = 0.0
        self.orders.clear()
        self.open_positions.clear()
        self.closed_trades.clear()
        self._order_id_counter = 1
        self.equity_curve = [self.initial_balance]
        self._peak_equity = self.initial_balance
        self._current_bar_index = 0


# ==================== Walk-Forward 分析 ====================

class WalkForwardAnalyzer:
    """
    Walk-Forward分析器
    
    将数据分为多个窗口：
    - 训练窗口（In-sample Optimization）
    - 测试窗口（Out-of-sample Validation）
    
    检测策略的过拟合程度和样本外稳定性。
    """

    def __init__(self, 
                 train_window_bars: int = 2000,
                 test_window_bars: int = 500,
                 initial_balance: float = 10000.0):
        self.train_window = train_window_bars
        self.test_window = test_window_bars
        self.initial_balance = initial_balance
        self.results: List[Dict[str, Any]] = []

    def run(self, bars: List[Bar], 
            strategy_factory: Callable) -> Dict[str, Any]:
        """
        运行Walk-Forward分析
        
        Args:
            bars: 完整历史数据
            strategy_factory: 策略工厂函数，返回(signal_generator, optimizer)
        """
        step = self.test_window
        segment_results = []
        is_stable = True
        
        for start in range(0, len(bars) - self.train_window - self.test_window, step):
            train_start = start
            train_end = start + self.train_window
            test_start = train_end
            test_end = min(test_start + self.test_window, len(bars))
            
            if test_end - test_start < 100:
                break
            
            # 训练集优化
            train_bars = bars[train_start:train_end]
            signal_gen, optimizer = strategy_factory()
            
            # 在训练集上找最优参数
            if optimizer:
                best_params = optimizer.optimize(train_bars, signal_gen)
            else:
                best_params = {}
            
            # 测试集验证
            test_bars = bars[test_start:test_end]
            engine = BacktestEngine(initial_balance=self.initial_balance)
            
            test_signal = strategy_factory(best_params)[0]
            result = engine.run(test_bars, test_signal)
            
            seg = {
                "segment": len(segment_results) + 1,
                "train_period": f"{train_bars[0].time.date()}→{train_bars[-1].time.date()}",
                "test_period": f"{test_bars[0].time.date()}→{test_bars[-1].time.date()}",
                "train_bars": len(train_bars),
                "test_bars": len(test_bars),
                "oos_net_profit": result.net_profit,
                "oos_sharpe": result.sharpe_ratio,
                "oos_win_rate": result.win_rate,
                "oos_max_dd": result.max_drawdown_pct,
                "params": best_params
            }
            segment_results.append(seg)
        
        # 稳定性评估
        if len(segment_results) >= 3:
            oos_sharpes = [s["oos_sharpe"] for s in segment_results]
            if np.mean(oos_sharpes) < 0:
                is_stable = False
            if np.std(oos_sharpes) > 1.5:
                is_stable = False  # 表现波动大→过拟合风险
        
        return {
            "segments": segment_results,
            "n_segments": len(segment_results),
            "avg_oos_sharpe": np.mean([s["oos_sharpe"] for s in segment_results]) if segment_results else 0,
            "avg_oos_win_rate": np.mean([s["oos_win_rate"] for s in segment_results]) if segment_results else 0,
            "avg_oos_max_dd": np.mean([s["oos_max_dd"] for s in segment_results]) if segment_results else 0,
            "is_stable": is_stable,
            "overfitting_warning": "HIGH" if not is_stable else "LOW"
        }


# ==================== 参数优化器 ====================

class ParameterOptimizer:
    """
    参数网格搜索优化器
    
    在训练集上搜索最优参数组合，
    以Sharpe Ratio为目标函数。
    """

    def __init__(self, param_grid: Dict[str, List[Any]],
                 initial_balance: float = 10000.0):
        self.param_grid = param_grid
        self.initial_balance = initial_balance
        self.best_params: Dict[str, Any] = {}
        self.best_score = -float('inf')
        self.all_results: List[Dict] = []

    def optimize(self, bars: List[Bar], 
                 strategy_factory: Callable) -> Dict[str, Any]:
        """网格搜索最优参数"""
        param_names = list(self.param_grid.keys())
        param_values = list(self.param_grid.values())

        total_combos = 1
        for v in param_values:
            total_combos *= len(v)

        logger.info(f"[OPT] Grid search: {total_combos} combinations over {len(bars)} bars")

        combo_idx = 0
        self._recurse_search(bars, strategy_factory, param_names, param_values, 
                             {}, 0, combo_idx, total_combos)

        logger.info(f"[OPT] Best: {self.best_params} → score={self.best_score:.3f}")
        return self.best_params

    def _recurse_search(self, bars, strategy_factory, names, values,
                        current_params, depth, combo_idx, total):
        if depth == len(names):
            # 评估当前参数组合
            try:
                signal_gen = strategy_factory(current_params)
                engine = BacktestEngine(initial_balance=self.initial_balance)
                result = engine.run(bars, signal_gen)

                score = result.sharpe_ratio
                self.all_results.append({
                    "params": current_params.copy(),
                    "sharpe": result.sharpe_ratio,
                    "net_profit": result.net_profit,
                    "max_dd": result.max_drawdown_pct,
                    "trades": result.total_trades
                })

                if score > self.best_score and result.total_trades >= 5:
                    self.best_score = score
                    self.best_params = current_params.copy()
            except Exception as e:
                logger.error(f"[OPT] Param eval failed: {e}")
            return

        name = names[depth]
        for val in values[depth]:
            current_params[name] = val
            self._recurse_search(bars, strategy_factory, names, values,
                                current_params, depth + 1, combo_idx, total)


# ==================== 报告生成器 ====================

class BacktestReporter:
    """回测报告生成器"""

    @staticmethod
    def format_result(result: BacktestResult) -> str:
        """格式化为可读报告"""
        d = result.to_dict()
        lines = [
            "=" * 60,
            f"  回测报告: {d['symbol']} | {d['period']}",
            "=" * 60,
            f"  总Bar数:        {d['total_bars']:>8}",
            f"  总交易数:       {d['total_trades']:>8}",
            f"  胜率:           {d['win_rate_pct']:>7.1f}%",
            f"  净盈亏:         ${d['net_profit']:>7.2f}",
            f"  盈亏比:         {d['profit_factor']:>8.2f}",
            f"  平均盈利:       ${d['avg_win']:>7.2f}",
            f"  平均亏损:       ${d['avg_loss']:>7.2f}",
            f"  最大回撤:       {d['max_drawdown_pct']:>7.2f}%",
            f"  夏普比率:       {d['sharpe_ratio']:>8.2f}",
            f"  索提诺比率:     {d['sortino_ratio']:>8.2f}",
            f"  卡玛比率:       {d['calmar_ratio']:>8.2f}",
            f"  期望值:         ${d['expectancy']:>7.2f}",
            f"  平均持仓Bar:    {d['avg_bars_held']:>7.1f}",
            f"  佣金:           ${d['commission_paid']:>7.2f}",
            f"  滑点成本:       ${d['slippage_total']:>7.2f}",
            "=" * 60
        ]
        return "\n".join(lines)

    @staticmethod
    def export_json(result: BacktestResult, filepath: str):
        """导出为JSON"""
        data = result.to_dict()
        data["trades"] = [
            {
                "id": t.id,
                "side": t.side.value,
                "entry": t.entry_time.isoformat(),
                "exit": t.exit_time.isoformat(),
                "entry_price": t.entry_price,
                "exit_price": t.exit_price,
                "profit": t.profit,
                "bars_held": t.bars_held,
                "reason": t.exit_reason
            }
            for t in result.trades
        ]
        data["equity_curve"] = result.equity_curve
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.info(f"[BT] Report exported: {filepath}")


# ==================== 快捷函数 ====================

def quick_backtest(data_file: str, 
                   signal_generator: Callable,
                   initial_balance: float = 10000.0,
                   start_date: str = None,
                   end_date: str = None) -> BacktestResult:
    """
    快速回测
    
    Args:
        data_file: HistData.com CSV文件路径
        signal_generator: 信号函数(bar, index, engine) → OrderSide or None
        initial_balance: 初始资金
        start_date/end_date: 日期过滤（可选）
    """
    bars = DataLoader.load_csv(data_file)
    
    if start_date:
        start_dt = datetime.fromisoformat(start_date)
        bars = [b for b in bars if b.time >= start_dt]
    if end_date:
        end_dt = datetime.fromisoformat(end_date)
        bars = [b for b in bars if b.time <= end_dt]
    
    engine = BacktestEngine(initial_balance=initial_balance)
    result = engine.run(bars, signal_generator)
    
    print(BacktestReporter.format_result(result))
    return result
