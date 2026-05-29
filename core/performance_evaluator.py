#!/usr/bin/env python3
"""
科学智能交易系统 - 绩效评估体系
实时监控交易策略表现并生成详细报告
"""

import json
import time
import math
import statistics
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from enum import Enum
import threading
import csv
import io
import base64
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

from core.logger import logger
from core.datastore import get_datastore


class TimePeriod(Enum):
    """时间周期"""
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"
    ALL = "all"


class ReportFormat(Enum):
    """报告格式"""
    JSON = "json"
    CSV = "csv"
    HTML = "html"
    MARKDOWN = "markdown"
    EXCEL = "excel"


@dataclass
class PerformanceMetrics:
    """绩效指标"""
    # 基础统计
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    
    # 收益指标
    total_return: float = 0.0
    total_pnl: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    largest_win: float = 0.0
    largest_loss: float = 0.0
    profit_factor: float = 0.0
    expectancy: float = 0.0
    
    # 风险指标
    max_drawdown: float = 0.0
    max_drawdown_percent: float = 0.0
    current_drawdown: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0
    var_95: float = 0.0
    expected_shortfall: float = 0.0
    volatility: float = 0.0
    downside_volatility: float = 0.0
    
    # 其他指标
    avg_trade_duration: float = 0.0
    avg_bars_in_trade: int = 0
    recovery_factor: float = 0.0
    k_ratio: float = 0.0
    ulcer_index: float = 0.0
    martin_ratio: float = 0.0
    
    # 时间序列数据
    cumulative_returns: List[float] = None
    drawdown_series: List[float] = None
    daily_returns: List[float] = None
    
    def __post_init__(self):
        if self.cumulative_returns is None:
            self.cumulative_returns = []
        if self.drawdown_series is None:
            self.drawdown_series = []
        if self.daily_returns is None:
            self.daily_returns = []
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "win_rate": self.win_rate,
            "total_return": self.total_return,
            "total_pnl": self.total_pnl,
            "avg_win": self.avg_win,
            "avg_loss": self.avg_loss,
            "largest_win": self.largest_win,
            "largest_loss": self.largest_loss,
            "profit_factor": self.profit_factor,
            "expectancy": self.expectancy,
            "max_drawdown": self.max_drawdown,
            "max_drawdown_percent": self.max_drawdown_percent,
            "current_drawdown": self.current_drawdown,
            "sharpe_ratio": self.sharpe_ratio,
            "sortino_ratio": self.sortino_ratio,
            "calmar_ratio": self.calmar_ratio,
            "var_95": self.var_95,
            "expected_shortfall": self.expected_shortfall,
            "volatility": self.volatility,
            "downside_volatility": self.downside_volatility,
            "avg_trade_duration": self.avg_trade_duration,
            "avg_bars_in_trade": self.avg_bars_in_trade,
            "recovery_factor": self.recovery_factor,
            "k_ratio": self.k_ratio,
            "ulcer_index": self.ulcer_index,
            "martin_ratio": self.martin_ratio
        }


@dataclass
class StrategyAnalysis:
    """策略分析"""
    strategy_name: str
    symbol: str
    time_period: TimePeriod
    metrics: PerformanceMetrics
    trade_analysis: Dict[str, Any]
    equity_curve: List[Tuple[float, float]]  # 时间戳, 净值
    recommendations: List[str]
    timestamp: float


class PerformanceEvaluator:
    """绩效评估器"""
    
    def __init__(self):
        self.datastore = get_datastore()
        
        # 缓存
        self.metrics_cache: Dict[str, PerformanceMetrics] = {}
        self.reports_cache: Dict[str, Dict[str, Any]] = {}
        
        # 运行状态
        self.running = False
        self.monitor_thread: Optional[threading.Thread] = None
        
        # 配置
        self.report_dir = Path("reports")
        self.report_dir.mkdir(exist_ok=True)
        
        logger.info("[UP] 绩效评估器初始化完成")
    
    def start(self):
        """启动绩效监控"""
        if self.running:
            logger.warning("[WARN]  绩效评估器已在运行中")
            return
        
        self.running = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
        logger.info("-> 绩效评估器已启动")
    
    def stop(self):
        """停止绩效监控"""
        self.running = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5)
        logger.info("🛑 绩效评估器已停止")
    
    def _monitor_loop(self):
        """绩效监控循环"""
        logger.info("[REFRESH] 绩效监控循环开始")
        
        last_report_time = 0
        
        while self.running:
            try:
                current_time = time.time()
                
                # 每小时更新一次绩效指标
                if current_time - last_report_time > 3600:
                    self._update_all_metrics()
                    last_report_time = current_time
                
                # 每天生成一次完整报告
                now = datetime.now()
                if now.hour == 0 and now.minute < 10:  # 每天凌晨生成报告
                    self.generate_daily_report()
                
                time.sleep(60)  # 每分钟检查一次
                
            except Exception as e:
                logger.error(f"[ERR] 绩效监控循环异常: {e}")
                time.sleep(300)
    
    def _update_all_metrics(self):
        """更新所有绩效指标"""
        try:
            # 获取所有交易记录
            all_trades = self.datastore.get_trades(limit=1000)
            
            if not all_trades:
                logger.warning("[WARN]  无交易记录可用")
                return
            
            # 按策略分组
            strategies = {}
            for trade in all_trades:
                strategy = trade.get('strategy', 'default')
                if strategy not in strategies:
                    strategies[strategy] = []
                strategies[strategy].append(trade)
            
            # 计算每个策略的绩效指标
            for strategy, trades in strategies.items():
                metrics = self._calculate_metrics(trades)
                self.metrics_cache[strategy] = metrics
            
            logger.info(f"[DATA] 绩效指标更新完成: {len(strategies)}个策略")
            
        except Exception as e:
            logger.error(f"[ERR] 更新绩效指标失败: {e}")
    
    def _calculate_metrics(self, trades: List[Dict[str, Any]]) -> PerformanceMetrics:
        """计算绩效指标"""
        metrics = PerformanceMetrics()
        
        try:
            if not trades:
                return metrics
            
            # 基础统计
            metrics.total_trades = len(trades)
            
            # 分离盈利和亏损交易
            winning_trades = [t for t in trades if t.get('pnl', 0) > 0]
            losing_trades = [t for t in trades if t.get('pnl', 0) < 0]
            breakeven_trades = [t for t in trades if t.get('pnl', 0) == 0]
            
            metrics.winning_trades = len(winning_trades)
            metrics.losing_trades = len(losing_trades)
            
            if metrics.total_trades > 0:
                metrics.win_rate = metrics.winning_trades / metrics.total_trades
            
            # 收益指标
            total_pnl = sum(t.get('pnl', 0) for t in trades)
            metrics.total_pnl = total_pnl
            
            # 计算收益率（简化）
            initial_balance = 10000.0  # 假设初始余额
            metrics.total_return = total_pnl / initial_balance * 100
            
            if winning_trades:
                metrics.avg_win = statistics.mean(t.get('pnl', 0) for t in winning_trades)
                metrics.largest_win = max(t.get('pnl', 0) for t in winning_trades)
            
            if losing_trades:
                metrics.avg_loss = statistics.mean(abs(t.get('pnl', 0)) for t in losing_trades)
                metrics.largest_loss = min(t.get('pnl', 0) for t in losing_trades)
            
            total_gross_profit = sum(t.get('pnl', 0) for t in winning_trades)
            total_gross_loss = abs(sum(t.get('pnl', 0) for t in losing_trades))
            
            if total_gross_loss > 0:
                metrics.profit_factor = total_gross_profit / total_gross_loss
            elif total_gross_profit > 0:
                metrics.profit_factor = float('inf')
            else:
                metrics.profit_factor = 0.0
            
            # 期望值
            if metrics.total_trades > 0:
                metrics.expectancy = (
                    (metrics.win_rate * metrics.avg_win) - 
                    ((1 - metrics.win_rate) * metrics.avg_loss)
                )
            
            # 时间序列数据
            pnl_series = [t.get('pnl', 0) for t in trades]
            timestamps = [t.get('timestamp', 0) for t in trades]
            
            if pnl_series and timestamps:
                # 排序时间序列
                combined = sorted(zip(timestamps, pnl_series), key=lambda x: x[0])
                timestamps_sorted, pnl_sorted = zip(*combined)
                
                # 计算累计收益
                cumulative = np.cumsum(pnl_sorted)
                metrics.cumulative_returns = list(cumulative)
                
                # 计算回撤
                running_max = np.maximum.accumulate(cumulative)
                drawdowns = running_max - cumulative
                
                metrics.drawdown_series = list(drawdowns)
                
                if len(drawdowns) > 0:
                    metrics.max_drawdown = float(np.max(drawdowns))
                    metrics.current_drawdown = float(drawdowns[-1])
                    
                    if running_max[-1] > 0:
                        metrics.max_drawdown_percent = metrics.max_drawdown / running_max[-1] * 100
                
                # 计算风险指标
                if len(pnl_series) >= 10:
                    returns = np.array(pnl_series) / initial_balance
                    
                    # 夏普比率（年化）
                    if np.std(returns) > 0:
                        metrics.sharpe_ratio = (np.mean(returns) / np.std(returns)) * np.sqrt(252)
                    
                    # 索提诺比率
                    downside_returns = returns[returns < 0]
                    if len(downside_returns) > 0 and np.std(downside_returns) > 0:
                        metrics.sortino_ratio = (np.mean(returns) / np.std(downside_returns)) * np.sqrt(252)
                    
                    # 波动率（年化）
                    metrics.volatility = np.std(returns) * np.sqrt(252)
                    
                    # 下行波动率
                    metrics.downside_volatility = np.std(downside_returns) * np.sqrt(252) if len(downside_returns) > 0 else 0
                    
                    # Calmar比率
                    if metrics.max_drawdown > 0:
                        metrics.calmar_ratio = metrics.total_return / metrics.max_drawdown_percent
                    
                    # VaR和期望损失
                    sorted_returns = sorted(returns)
                    var_index = int(len(sorted_returns) * 0.05)
                    if var_index < len(sorted_returns):
                        metrics.var_95 = sorted_returns[var_index] * initial_balance
                        tail_losses = sorted_returns[:var_index]
                        if tail_losses:
                            metrics.expected_shortfall = np.mean(tail_losses) * initial_balance
                
                # 其他指标
                # 恢复因子
                if metrics.max_drawdown > 0:
                    metrics.recovery_factor = total_pnl / metrics.max_drawdown
                
                # K比率（趋势强度）
                if len(cumulative) >= 20:
                    x = np.arange(len(cumulative))
                    slope, intercept, r_value, p_value, std_err = stats.linregress(x, cumulative)
                    metrics.k_ratio = slope / std_err if std_err > 0 else 0
                
                # 溃疡指数
                if len(drawdowns) > 0:
                    metrics.ulcer_index = np.sqrt(np.mean(np.square(drawdowns)))
                
                # 马丁比率
                if metrics.ulcer_index > 0:
                    metrics.martin_ratio = total_pnl / metrics.ulcer_index
            
            # 交易持续时间（简化）
            if len(trades) > 0:
                durations = []
                for trade in trades:
                    open_time = trade.get('open_time', 0)
                    close_time = trade.get('close_time', 0)
                    if open_time > 0 and close_time > open_time:
                        durations.append(close_time - open_time)
                
                if durations:
                    metrics.avg_trade_duration = statistics.mean(durations)
            
        except Exception as e:
            logger.error(f"[ERR] 计算绩效指标失败: {e}")
        
        return metrics
    
    def get_strategy_metrics(self, strategy: str = "default", 
                            time_period: TimePeriod = TimePeriod.ALL) -> PerformanceMetrics:
        """获取策略绩效指标"""
        try:
            cache_key = f"{strategy}_{time_period.value}"
            
            if cache_key in self.metrics_cache:
                return self.metrics_cache[cache_key]
            
            # 获取交易记录
            trades = self.datastore.get_trades_by_strategy(strategy, limit=1000)
            
            # 根据时间周期过滤
            if time_period != TimePeriod.ALL:
                trades = self._filter_trades_by_period(trades, time_period)
            
            # 计算指标
            metrics = self._calculate_metrics(trades)
            
            # 缓存结果
            self.metrics_cache[cache_key] = metrics
            
            return metrics
            
        except Exception as e:
            logger.error(f"[ERR] 获取策略绩效指标失败: {e}")
            return PerformanceMetrics()
    
    def _filter_trades_by_period(self, trades: List[Dict[str, Any]], 
                                period: TimePeriod) -> List[Dict[str, Any]]:
        """根据时间周期过滤交易记录"""
        try:
            if not trades:
                return []
            
            now = datetime.now()
            cutoff_time = 0
            
            if period == TimePeriod.DAILY:
                cutoff_time = (now - timedelta(days=1)).timestamp()
            elif period == TimePeriod.WEEKLY:
                cutoff_time = (now - timedelta(weeks=1)).timestamp()
            elif period == TimePeriod.MONTHLY:
                cutoff_time = (now - timedelta(days=30)).timestamp()
            elif period == TimePeriod.QUARTERLY:
                cutoff_time = (now - timedelta(days=90)).timestamp()
            elif period == TimePeriod.YEARLY:
                cutoff_time = (now - timedelta(days=365)).timestamp()
            
            filtered_trades = [t for t in trades if t.get('timestamp', 0) >= cutoff_time]
            return filtered_trades
            
        except Exception as e:
            logger.error(f"[ERR] 过滤交易记录失败: {e}")
            return trades
    
    def analyze_strategy(self, strategy: str = "default", 
                        symbol: Optional[str] = None) -> StrategyAnalysis:
        """分析交易策略"""
        try:
            # 获取指标
            metrics = self.get_strategy_metrics(strategy)
            
            # 获取交易记录
            trades = self.datastore.get_trades_by_strategy(strategy, limit=500)
            
            if symbol:
                trades = [t for t in trades if t.get('symbol', '') == symbol]
            
            # 交易分析
            trade_analysis = self._analyze_trades(trades)
            
            # 净值曲线
            equity_curve = self._generate_equity_curve(trades)
            
            # 建议
            recommendations = self._generate_recommendations(metrics, trade_analysis)
            
            # 构建分析结果
            analysis = StrategyAnalysis(
                strategy_name=strategy,
                symbol=symbol or "ALL",
                time_period=TimePeriod.ALL,
                metrics=metrics,
                trade_analysis=trade_analysis,
                equity_curve=equity_curve,
                recommendations=recommendations,
                timestamp=time.time()
            )
            
            logger.info(f"[DATA] 策略分析完成: {strategy}")
            return analysis
            
        except Exception as e:
            logger.error(f"[ERR] 分析策略失败: {e}")
            return StrategyAnalysis(
                strategy_name=strategy,
                symbol=symbol or "ALL",
                time_period=TimePeriod.ALL,
                metrics=PerformanceMetrics(),
                trade_analysis={},
                equity_curve=[],
                recommendations=[f"分析失败: {str(e)}"],
                timestamp=time.time()
            )
    
    def _analyze_trades(self, trades: List[Dict[str, Any]]) -> Dict[str, Any]:
        """分析交易记录"""
        try:
            if not trades:
                return {}
            
            analysis = {
                "total_trades": len(trades),
                "by_symbol": {},
                "by_hour": {},
                "by_day": {},
                "by_month": {}
            }
            
            # 按品种分析
            for trade in trades:
                symbol = trade.get('symbol', 'unknown')
                if symbol not in analysis["by_symbol"]:
                    analysis["by_symbol"][symbol] = {
                        "count": 0,
                        "total_pnl": 0,
                        "winning": 0,
                        "losing": 0
                    }
                
                sym_data = analysis["by_symbol"][symbol]
                sym_data["count"] += 1
                sym_data["total_pnl"] += trade.get('pnl', 0)
                
                if trade.get('pnl', 0) > 0:
                    sym_data["winning"] += 1
                elif trade.get('pnl', 0) < 0:
                    sym_data["losing"] += 1
            
            # 按时间分析
            for trade in trades:
                timestamp = trade.get('timestamp', 0)
                if timestamp > 0:
                    dt = datetime.fromtimestamp(timestamp)
                    
                    # 按小时
                    hour = dt.hour
                    if hour not in analysis["by_hour"]:
                        analysis["by_hour"][hour] = {"count": 0, "total_pnl": 0}
                    analysis["by_hour"][hour]["count"] += 1
                    analysis["by_hour"][hour]["total_pnl"] += trade.get('pnl', 0)
                    
                    # 按星期
                    day = dt.strftime("%A")
                    if day not in analysis["by_day"]:
                        analysis["by_day"][day] = {"count": 0, "total_pnl": 0}
                    analysis["by_day"][day]["count"] += 1
                    analysis["by_day"][day]["total_pnl"] += trade.get('pnl', 0)
                    
                    # 按月份
                    month = dt.strftime("%B")
                    if month not in analysis["by_month"]:
                        analysis["by_month"][month] = {"count": 0, "total_pnl": 0}
                    analysis["by_month"][month]["count"] += 1
                    analysis["by_month"][month]["total_pnl"] += trade.get('pnl', 0)
            
            return analysis
            
        except Exception as e:
            logger.error(f"[ERR] 分析交易记录失败: {e}")
            return {}
    
    def _generate_equity_curve(self, trades: List[Dict[str, Any]]) -> List[Tuple[float, float]]:
        """生成净值曲线"""
        try:
            if not trades:
                return []
            
            # 按时间排序
            sorted_trades = sorted(trades, key=lambda x: x.get('timestamp', 0))
            
            equity_curve = []
            cumulative_pnl = 0
            initial_balance = 10000.0
            
            for trade in sorted_trades:
                timestamp = trade.get('timestamp', 0)
                pnl = trade.get('pnl', 0)
                
                cumulative_pnl += pnl
                equity = initial_balance + cumulative_pnl
                
                equity_curve.append((timestamp, equity))
            
            return equity_curve
            
        except Exception as e:
            logger.error(f"[ERR] 生成净值曲线失败: {e}")
            return []
    
    def _generate_recommendations(self, metrics: PerformanceMetrics, 
                                trade_analysis: Dict[str, Any]) -> List[str]:
        """生成建议"""
        recommendations = []
        
        try:
            # 基于绩效指标的建议
            if metrics.win_rate < 0.4:
                recommendations.append("胜率较低，建议优化入场策略或增加过滤条件")
            
            if metrics.profit_factor < 1.2:
                recommendations.append("盈利因子较低，建议优化止损止盈策略")
            
            if metrics.max_drawdown_percent > 20:
                recommendations.append("最大回撤较大，建议降低仓位或加强风险管理")
            
            if metrics.sharpe_ratio < 1.0:
                recommendations.append("夏普比率较低，策略风险调整后收益不佳")
            
            if metrics.expectancy < 0:
                recommendations.append("期望值为负，策略长期可能亏损")
            
            # 基于交易分析的建议
            if trade_analysis:
                # 检查品种集中度
                by_symbol = trade_analysis.get("by_symbol", {})
                if len(by_symbol) == 1:
                    symbol = list(by_symbol.keys())[0]
                    recommendations.append(f"交易过于集中({symbol})，建议分散投资")
                
                # 检查时间分布
                by_hour = trade_analysis.get("by_hour", {})
                if len(by_hour) <= 3:
                    recommendations.append("交易时间分布不均，建议全天候监控市场")
            
            # 如果没有问题，给予肯定
            if not recommendations:
                recommendations.append("策略表现良好，继续保持当前配置")
            
        except Exception as e:
            logger.error(f"[ERR] 生成建议失败: {e}")
            recommendations.append("无法生成建议，请检查数据完整性")
        
        return recommendations
    
    def generate_report(self, strategy: str = "default", 
                       report_format: ReportFormat = ReportFormat.HTML,
                       include_details: bool = True) -> str:
        """生成绩效报告"""
        try:
            # 分析策略
            analysis = self.analyze_strategy(strategy)
            
            # 生成报告
            if report_format == ReportFormat.JSON:
                report = self._generate_json_report(analysis)
            elif report_format == ReportFormat.HTML:
                report = self._generate_html_report(analysis, include_details)
            elif report_format == ReportFormat.MARKDOWN:
                report = self._generate_markdown_report(analysis, include_details)
            elif report_format == ReportFormat.CSV:
                report = self._generate_csv_report(analysis)
            else:
                report = self._generate_html_report(analysis, include_details)
            
            # 保存报告到文件
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"performance_report_{strategy}_{timestamp}.{report_format.value}"
            filepath = self.report_dir / filename
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(report)
            
            logger.info(f"[FILE] 绩效报告已生成: {filepath}")
            
            return str(filepath)
            
        except Exception as e:
            logger.error(f"[ERR] 生成绩效报告失败: {e}")
            return ""
    
    def _generate_json_report(self, analysis: StrategyAnalysis) -> str:
        """生成JSON报告"""
        try:
            report_data = {
                "strategy_name": analysis.strategy_name,
                "symbol": analysis.symbol,
                "time_period": analysis.time_period.value,
                "timestamp": datetime.fromtimestamp(analysis.timestamp).isoformat(),
                "performance_metrics": analysis.metrics.to_dict(),
                "trade_analysis": analysis.trade_analysis,
                "recommendations": analysis.recommendations,
                "equity_curve": analysis.equity_curve
            }
            
            return json.dumps(report_data, indent=2, ensure_ascii=False)
            
        except Exception as e:
            logger.error(f"[ERR] 生成JSON报告失败: {e}")
            return "{}"
    
    def _generate_html_report(self, analysis: StrategyAnalysis, include_details: bool) -> str:
        """生成HTML报告"""
        try:
            metrics = analysis.metrics
            trade_analysis = analysis.trade_analysis
            
            html = f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>交易绩效报告 - {analysis.strategy_name}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; color: #333; }}
        .header {{ text-align: center; margin-bottom: 30px; }}
        .section {{ margin-bottom: 30px; border: 1px solid #ddd; padding: 20px; border-radius: 5px; }}
        .section-title {{ font-size: 1.5em; color: #2c3e50; margin-bottom: 15px; border-bottom: 2px solid #3498db; padding-bottom: 5px; }}
        .metrics-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 15px; }}
        .metric-card {{ background: #f8f9fa; padding: 15px; border-radius: 5px; border-left: 4px solid #3498db; }}
        .metric-value {{ font-size: 1.8em; font-weight: bold; color: #2c3e50; }}
        .metric-label {{ font-size: 0.9em; color: #7f8c8d; margin-top: 5px; }}
        .positive {{ color: #27ae60; }}
        .negative {{ color: #e74c3c; }}
        .neutral {{ color: #f39c12; }}
        .recommendation {{ background: #fffde7; padding: 10px; margin: 5px 0; border-left: 4px solid #f39c12; }}
        table {{ width: 100%; border-collapse: collapse; margin: 15px 0; }}
        th, td {{ padding: 10px; text-align: left; border-bottom: 1px solid #ddd; }}
        th {{ background-color: #f2f2f2; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>[DATA] 交易策略绩效报告</h1>
        <p>策略: <strong>{analysis.strategy_name}</strong> | 品种: <strong>{analysis.symbol}</strong></p>
        <p>生成时间: {datetime.fromtimestamp(analysis.timestamp).strftime('%Y-%m-%d %H:%M:%S')}</p>
    </div>
    
    <div class="section">
        <div class="section-title">[UP] 关键绩效指标</div>
        <div class="metrics-grid">
            <div class="metric-card">
                <div class="metric-value {'positive' if metrics.total_pnl > 0 else 'negative'}">${metrics.total_pnl:,.2f}</div>
                <div class="metric-label">总盈亏</div>
            </div>
            <div class="metric-card">
                <div class="metric-value {'positive' if metrics.win_rate > 0.5 else 'negative'}">{metrics.win_rate:.1%}</div>
                <div class="metric-label">胜率</div>
            </div>
            <div class="metric-card">
                <div class="metric-value {'positive' if metrics.profit_factor > 1.5 else 'neutral' if metrics.profit_factor > 1.0 else 'negative'}">{metrics.profit_factor:.2f}</div>
                <div class="metric-label">盈利因子</div>
            </div>
            <div class="metric-card">
                <div class="metric-value {'positive' if metrics.sharpe_ratio > 1.5 else 'neutral' if metrics.sharpe_ratio > 1.0 else 'negative'}">{metrics.sharpe_ratio:.2f}</div>
                <div class="metric-label">夏普比率</div>
            </div>
            <div class="metric-card">
                <div class="metric-value negative">{metrics.max_drawdown_percent:.1f}%</div>
                <div class="metric-label">最大回撤</div>
            </div>
            <div class="metric-card">
                <div class="metric-value {'positive' if metrics.expectancy > 0 else 'negative'}">{metrics.expectancy:,.2f}</div>
                <div class="metric-label">期望值</div>
            </div>
        </div>
    </div>
    
    <div class="section">
        <div class="section-title">[DATA] 详细统计</div>
        <table>
            <tr>
                <th>指标</th>
                <th>数值</th>
                <th>说明</th>
            </tr>
            <tr>
                <td>总交易次数</td>
                <td>{metrics.total_trades}</td>
                <td>盈利: {metrics.winning_trades}, 亏损: {metrics.losing_trades}</td>
            </tr>
            <tr>
                <td>平均盈利</td>
                <td>${metrics.avg_win:,.2f}</td>
                <td>最大盈利: ${metrics.largest_win:,.2f}</td>
            </tr>
            <tr>
                <td>平均亏损</td>
                <td>${metrics.avg_loss:,.2f}</td>
                <td>最大亏损: ${metrics.largest_loss:,.2f}</td>
            </tr>
            <tr>
                <td>总收益率</td>
                <td>{metrics.total_return:.2f}%</td>
                <td>基于初始资金$10,000计算</td>
            </tr>
            <tr>
                <td>索提诺比率</td>
                <td>{metrics.sortino_ratio:.2f}</td>
                <td>考虑下行风险的风险调整后收益</td>
            </tr>
            <tr>
                <td>Calmar比率</td>
                <td>{metrics.calmar_ratio:.2f}</td>
                <td>收益与最大回撤的比率</td>
            </tr>
            <tr>
                <td>波动率</td>
                <td>{metrics.volatility:.1%}</td>
                <td>年化波动率</td>
            </tr>
            <tr>
                <td>VaR (95%)</td>
                <td>${metrics.var_95:,.2f}</td>
                <td>95%置信度的风险价值</td>
            </tr>
        </table>
    </div>
"""
            
            if include_details and trade_analysis:
                html += f"""
    <div class="section">
        <div class="section-title">[TEST] 详细分析</div>
        <h3>按品种分析</h3>
        <table>
            <tr>
                <th>品种</th>
                <th>交易次数</th>
                <th>总盈亏</th>
                <th>胜率</th>
            </tr>
"""
                
                for symbol, data in trade_analysis.get("by_symbol", {}).items():
                    count = data.get("count", 0)
                    total_pnl = data.get("total_pnl", 0)
                    winning = data.get("winning", 0)
                    win_rate = winning / count if count > 0 else 0
                    
                    html += f"""
            <tr>
                <td>{symbol}</td>
                <td>{count}</td>
                <td class="{{'positive' if total_pnl > 0 else 'negative'}}">${total_pnl:,.2f}</td>
                <td>{win_rate:.1%}</td>
            </tr>
"""
                
                html += """
        </table>
    </div>
"""
            
            html += f"""
    <div class="section">
        <div class="section-title">[TIP] 优化建议</div>
"""
            
            for rec in analysis.recommendations:
                html += f"""
        <div class="recommendation">[TIP] {rec}</div>
"""
            
            html += """
    </div>
    
    <div class="section">
        <div class="section-title">[LOG] 报告说明</div>
        <p>1. 本报告基于历史交易数据生成，不代表未来表现。</p>
        <p>2. 所有计算基于简化模型，实际交易中请考虑滑点、手续费等因素。</p>
        <p>3. 建议定期监控策略表现，及时调整参数。</p>
        <p>4. 投资有风险，入市需谨慎。</p>
    </div>
</body>
</html>
"""
            
            return html
            
        except Exception as e:
            logger.error(f"[ERR] 生成HTML报告失败: {e}")
            return "<html><body><h1>报告生成失败</h1></body></html>"
    
    def _generate_markdown_report(self, analysis: StrategyAnalysis, include_details: bool) -> str:
        """生成Markdown报告"""
        try:
            metrics = analysis.metrics
            
            md = f"""# [DATA] 交易策略绩效报告

## 基本信息
- **策略名称**: {analysis.strategy_name}
- **交易品种**: {analysis.symbol}
- **分析周期**: {analysis.time_period.value}
- **报告时间**: {datetime.fromtimestamp(analysis.timestamp).strftime('%Y-%m-%d %H:%M:%S')}

## [UP] 关键绩效指标

| 指标 | 数值 | 评价 |
|------|------|------|
| 总盈亏 | ${metrics.total_pnl:,.2f} | {'[OK] 盈利' if metrics.total_pnl > 0 else '[ERR] 亏损'} |
| 胜率 | {metrics.win_rate:.1%} | {'[OK] 良好' if metrics.win_rate > 0.6 else '[WARN]  一般' if metrics.win_rate > 0.5 else '[ERR] 较差'} |
| 盈利因子 | {metrics.profit_factor:.2f} | {'[OK] 优秀' if metrics.profit_factor > 2.0 else '[OK] 良好' if metrics.profit_factor > 1.5 else '[WARN]  一般' if metrics.profit_factor > 1.0 else '[ERR] 较差'} |
| 夏普比率 | {metrics.sharpe_ratio:.2f} | {'[OK] 优秀' if metrics.sharpe_ratio > 2.0 else '[OK] 良好' if metrics.sharpe_ratio > 1.5 else '[WARN]  一般' if metrics.sharpe_ratio > 1.0 else '[ERR] 较差'} |
| 最大回撤 | {metrics.max_drawdown_percent:.1f}% | {'[OK] 优秀' if metrics.max_drawdown_percent < 10 else '[OK] 良好' if metrics.max_drawdown_percent < 20 else '[WARN]  一般' if metrics.max_drawdown_percent < 30 else '[ERR] 较差'} |
| 期望值 | ${metrics.expectancy:,.2f} | {'[OK] 正期望' if metrics.expectancy > 0 else '[ERR] 负期望'} |

## [DATA] 详细统计

### 交易统计
- 总交易次数: {metrics.total_trades}
- 盈利交易: {metrics.winning_trades}
- 亏损交易: {metrics.losing_trades}
- 平均盈利: ${metrics.avg_win:,.2f}
- 平均亏损: ${metrics.avg_loss:,.2f}
- 最大盈利: ${metrics.largest_win:,.2f}
- 最大亏损: ${metrics.largest_loss:,.2f}

### 风险指标
- 总收益率: {metrics.total_return:.2f}%
- 索提诺比率: {metrics.sortino_ratio:.2f}
- Calmar比率: {metrics.calmar_ratio:.2f}
- 波动率: {metrics.volatility:.1%}
- VaR (95%): ${metrics.var_95:,.2f}
- 期望损失: ${metrics.expected_shortfall:,.2f}

## [TIP] 优化建议

"""
            
            for rec in analysis.recommendations:
                md += f"- {rec}\n"
            
            md += """
## [LOG] 报告说明

1. 本报告基于历史交易数据生成，不代表未来表现。
2. 所有计算基于简化模型，实际交易中请考虑滑点、手续费等因素。
3. 建议定期监控策略表现，及时调整参数。
4. 投资有风险，入市需谨慎。
"""
            
            return md
            
        except Exception as e:
            logger.error(f"[ERR] 生成Markdown报告失败: {e}")
            return "# 报告生成失败"
    
    def _generate_csv_report(self, analysis: StrategyAnalysis) -> str:
        """生成CSV报告"""
        try:
            output = io.StringIO()
            writer = csv.writer(output)
            
            # 写入标题
            writer.writerow(["交易策略绩效报告"])
            writer.writerow([f"策略名称: {analysis.strategy_name}"])
            writer.writerow([f"交易品种: {analysis.symbol}"])
            writer.writerow([f"分析周期: {analysis.time_period.value}"])
            writer.writerow([f"报告时间: {datetime.fromtimestamp(analysis.timestamp).strftime('%Y-%m-%d %H:%M:%S')}"])
            writer.writerow([])
            
            # 关键指标
            writer.writerow(["关键绩效指标"])
            writer.writerow(["指标", "数值"])
            writer.writerow(["总盈亏", f"${analysis.metrics.total_pnl:,.2f}"])
            writer.writerow(["胜率", f"{analysis.metrics.win_rate:.1%}"])
            writer.writerow(["盈利因子", f"{analysis.metrics.profit_factor:.2f}"])
            writer.writerow(["夏普比率", f"{analysis.metrics.sharpe_ratio:.2f}"])
            writer.writerow(["最大回撤", f"{analysis.metrics.max_drawdown_percent:.1f}%"])
            writer.writerow(["期望值", f"${analysis.metrics.expectancy:,.2f}"])
            writer.writerow([])
            
            # 详细统计
            writer.writerow(["详细统计"])
            writer.writerow(["总交易次数", analysis.metrics.total_trades])
            writer.writerow(["盈利交易", analysis.metrics.winning_trades])
            writer.writerow(["亏损交易", analysis.metrics.losing_trades])
            writer.writerow(["平均盈利", f"${analysis.metrics.avg_win:,.2f}"])
            writer.writerow(["平均亏损", f"${analysis.metrics.avg_loss:,.2f}"])
            writer.writerow([])
            
            # 建议
            writer.writerow(["优化建议"])
            for rec in analysis.recommendations:
                writer.writerow([rec])
            
            return output.getvalue()
            
        except Exception as e:
            logger.error(f"[ERR] 生成CSV报告失败: {e}")
            return "指标,数值\n生成失败,1"
    
    def generate_daily_report(self):
        """生成每日报告"""
        try:
            logger.info("📅 开始生成每日绩效报告...")
            
            # 生成所有策略的报告
            strategies = ["default"]  # 可以扩展为获取所有策略
            
            for strategy in strategies:
                # 生成HTML报告
                html_report = self.generate_report(
                    strategy=strategy,
                    report_format=ReportFormat.HTML,
                    include_details=True
                )
                
                # 生成Markdown报告（用于存档）
                md_report = self.generate_report(
                    strategy=strategy,
                    report_format=ReportFormat.MARKDOWN,
                    include_details=False
                )
                
                logger.info(f"[FILE] 每日报告生成完成: {strategy}")
            
            # 发送报告通知（可扩展为邮件、Slack等）
            self._send_report_notification()
            
        except Exception as e:
            logger.error(f"[ERR] 生成每日报告失败: {e}")
    
    def _send_report_notification(self):
        """发送报告通知（简化实现）"""
        try:
            # 这里可以集成邮件、Slack、钉钉等通知方式
            # 当前仅记录日志
            logger.info("📨 绩效报告通知已发送（模拟）")
            
        except Exception as e:
            logger.error(f"[ERR] 发送报告通知失败: {e}")


# 全局绩效评估器实例
_global_performance_evaluator: Optional[PerformanceEvaluator] = None


def get_performance_evaluator() -> PerformanceEvaluator:
    """获取全局绩效评估器实例"""
    global _global_performance_evaluator
    if not _global_performance_evaluator:
        _global_performance_evaluator = PerformanceEvaluator()
    return _global_performance_evaluator


if __name__ == "__main__":
    # 测试绩效评估系统
    print("="*70)
    print("[TOOL] 测试绩效评估体系")
    print("="*70)
    
    evaluator = PerformanceEvaluator()
    
    # 启动评估器
    evaluator.start()
    
    # 等待初始化
    time.sleep(1)
    
    # 获取策略指标
    print("\n[DATA] 获取策略绩效指标...")
    metrics = evaluator.get_strategy_metrics("default")
    
    if metrics.total_trades > 0:
        print(f"[OK] 绩效指标获取成功:")
        print(f"   总交易次数: {metrics.total_trades}")
        print(f"   胜率: {metrics.win_rate:.1%}")
        print(f"   总盈亏: ${metrics.total_pnl:,.2f}")
        print(f"   盈利因子: {metrics.profit_factor:.2f}")
        print(f"   最大回撤: {metrics.max_drawdown_percent:.1f}%")
        print(f"   夏普比率: {metrics.sharpe_ratio:.2f}")
    else:
        print("[WARN]  无交易记录，使用模拟数据...")
    
    # 生成HTML报告
    print("\n[FILE] 生成HTML报告...")
    report_path = evaluator.generate_report(
        strategy="default",
        report_format=ReportFormat.HTML,
        include_details=True
    )
    
    if report_path:
        print(f"[OK] HTML报告已生成: {report_path}")
    else:
        print("[ERR] HTML报告生成失败")
    
    # 停止评估器
    evaluator.stop()
    
    print("\n[OK] 绩效评估体系测试完成！")