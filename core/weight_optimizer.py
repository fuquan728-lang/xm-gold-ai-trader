#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
交易策略权重优化器
实现系统性的多时间框架权重动态调整、评估和记录功能
"""

import json
import time
import threading
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path
from dataclasses import dataclass, asdict
from enum import Enum


class TriggerReason(Enum):
    """权重调整触发原因"""
    PERFORMANCE_DEGRADATION = "performance_degradation"  # 性能下降
    MARKET_CONDITION_CHANGE = "market_condition_change"  # 市场环境变化
    SCHEDULED_OPTIMIZATION = "scheduled_optimization"  # 定时优化
    MANUAL_INTERVENTION = "manual_intervention"  # 人工干预


class ValidationStatus(Enum):
    """验证状态"""
    PASSED = "passed"
    FAILED = "failed"
    PENDING = "pending"


@dataclass
class WeightSnapshot:
    """权重快照"""
    timestamp: float
    weights: Dict[str, float]
    trigger_reason: str
    performance_before: Dict[str, Any]
    performance_after: Optional[Dict[str, Any]] = None
    validation_status: str = ValidationStatus.PENDING.value
    notes: str = ""


@dataclass
class TradeSignal:
    """交易信号记录"""
    timestamp: float
    symbol: str
    action: str
    confidence: float
    bid: float
    ask: float
    multi_timeframe_signals: Dict[str, str]  # 各时间框架信号
    result: Optional[str] = None  # 交易结果：win/loss/pending


@dataclass
class WeightConfig:
    """权重配置"""
    default_weights: Dict[str, float]
    min_weight: float
    max_weight: float
    max_adjustment_per_step: float
    evaluation_period: int  # 评估周期（交易次数）
    performance_threshold: float  # 性能阈值（如0.6胜率）
    cooldown_period: int  # 权重调整冷却期（秒）


class WeightOptimizer:
    """交易策略权重优化器"""
    
    def __init__(self, config: Optional[WeightConfig] = None, data_dir: str = "./weights"):
        """
        初始化权重优化器
        
        参数:
            config: 权重配置
            data_dir: 数据存储目录
        """
        # 默认配置
        self.config = config or WeightConfig(
            default_weights={'h1': 0.35, 'h4': 0.35, 'd1': 0.30},
            min_weight=0.10,
            max_weight=0.60,
            max_adjustment_per_step=0.10,
            evaluation_period=20,
            performance_threshold=0.55,
            cooldown_period=3600  # 1小时
        )
        
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # 先初始化logger
        from .logger import logger
        self.logger = logger
        
        # 初始化权重
        self.current_weights = self.config.default_weights.copy()
        self.weights_history: List[WeightSnapshot] = []
        self.signal_history: List[TradeSignal] = []
        
        # 文件写入锁（防止多线程同时保存导致文件损坏）
        self._save_lock = threading.Lock()
        
        # 状态管理
        self.last_adjustment_time = 0.0
        
        # 性能跟踪
        self.performance_metrics = {
            'total_trades': 0,
            'wins': 0,
            'losses': 0,
            'total_pnl': 0.0,
            'current_weight_performance': {}  # 当前权重下各时间框架的表现
        }
        
        self._load_weights()
        self.logger.info("[OK] 权重优化器初始化完成")
    
    def _load_weights(self) -> None:
        """加载历史权重"""
        try:
            weights_file = self.data_dir / "weights_history.json"
            if weights_file.exists():
                with open(weights_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.weights_history = [WeightSnapshot(**item) for item in data.get('history', [])]
                    if self.weights_history:
                        self.current_weights = self.weights_history[-1].weights
                        self.last_adjustment_time = self.weights_history[-1].timestamp
                        self.logger.info(f"📥 加载历史权重，当前权重: {self.current_weights}")
        except Exception as e:
            self.logger.warning(f"[WARN]  加载权重历史失败: {str(e)}")
    
    def _save_weights(self) -> None:
        """保存权重历史（线程安全）"""
        try:
            with self._save_lock:
                weights_file = self.data_dir / "weights_history.json"
                data = {
                    'last_updated': time.time(),
                    'history': [asdict(ws) for ws in self.weights_history]
                }
                with open(weights_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            self.logger.error(f"[ERR] 保存权重历史失败: {str(e)}")
    
    def get_current_weights(self) -> Dict[str, float]:
        """
        获取当前权重
        
        返回:
            当前多时间框架权重
        """
        return self.current_weights.copy()
    
    def record_signal(self, signal: TradeSignal) -> None:
        """
        记录交易信号
        
        参数:
            signal: 交易信号
        """
        self.signal_history.append(signal)
        
        # 限制历史大小
        if len(self.signal_history) > 1000:
            self.signal_history = self.signal_history[-1000:]
        
        # 保存信号
        self._save_signals()
        
        # 更新性能指标
        if signal.result:
            self._update_performance(signal)
        
        # 检查是否需要调整权重
        self._check_weight_adjustment()
    
    def _save_signals(self) -> None:
        """保存信号历史"""
        try:
            signals_file = self.data_dir / "signal_history.json"
            # 只保存最近的500个信号
            recent_signals = self.signal_history[-500:]
            data = {
                'last_updated': time.time(),
                'signals': [asdict(s) for s in recent_signals]
            }
            with open(signals_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            self.logger.error(f"[ERR] 保存信号历史失败: {str(e)}")
    
    def _update_performance(self, signal: TradeSignal) -> None:
        """
        更新性能指标
        
        参数:
            signal: 交易信号
        """
        self.performance_metrics['total_trades'] += 1
        
        if signal.result == "win":
            self.performance_metrics['wins'] += 1
        elif signal.result == "loss":
            self.performance_metrics['losses'] += 1
        
        # 更新各时间框架表现
        for tf, tf_signal in signal.multi_timeframe_signals.items():
            if tf not in self.performance_metrics['current_weight_performance']:
                self.performance_metrics['current_weight_performance'][tf] = {
                    'signals': 0, 'wins': 0
                }
            self.performance_metrics['current_weight_performance'][tf]['signals'] += 1
            if signal.result == "win" and tf_signal == signal.action:
                self.performance_metrics['current_weight_performance'][tf]['wins'] += 1
    
    def calculate_timeframe_performance(self, timeframe: str) -> Optional[float]:
        """
        计算特定时间框架的性能
        
        参数:
            timeframe: 时间框架
        
        返回:
            胜率（如果有足够数据）
        """
        perf = self.performance_metrics['current_weight_performance'].get(timeframe, {})
        signals = perf.get('signals', 0)
        
        if signals < self.config.evaluation_period:
            return None  # 数据不足
        
        return perf.get('wins', 0) / signals
    
    def should_adjust_weights(self) -> Tuple[bool, Optional[str]]:
        """
        检查是否应该调整权重
        
        返回:
            (是否需要调整, 触发原因)
        """
        current_time = time.time()
        
        # 检查冷却期
        if current_time - self.last_adjustment_time < self.config.cooldown_period:
            return False, None
        
        # 检查是否有足够的交易数据
        if self.performance_metrics['total_trades'] < self.config.evaluation_period:
            return False, None
        
        # 计算总体胜率
        total_trades = self.performance_metrics['total_trades']
        win_rate = self.performance_metrics['wins'] / max(total_trades, 1)
        
        # 检查是否低于阈值
        if win_rate < self.config.performance_threshold:
            return True, TriggerReason.PERFORMANCE_DEGRADATION.value
        
        # 检查各时间框架表现差异
        tfs = list(self.current_weights.keys())
        if len(tfs) >= 2:
            perf_data = []
            for tf in tfs:
                tf_perf = self.calculate_timeframe_performance(tf)
                if tf_perf is not None:
                    perf_data.append(tf_perf)
            
            if len(perf_data) >= 2:
                max_perf = max(perf_data)
                min_perf = min(perf_data)
                if max_perf - min_perf > 0.2:  # 差异超过20%
                    return True, TriggerReason.MARKET_CONDITION_CHANGE.value
        
        return False, None
    
    def _check_weight_adjustment(self) -> None:
        """检查并可能调整权重"""
        need_adjustment, reason = self.should_adjust_weights()
        if need_adjustment:
            self.adjust_weights(reason)
    
    def adjust_weights(self, trigger_reason: str = TriggerReason.SCHEDULED_OPTIMIZATION.value) -> bool:
        """
        调整权重
        
        参数:
            trigger_reason: 触发原因
        
        返回:
            是否成功调整
        """
        # 计算调整前的性能
        performance_before = {
            'timestamp': time.time(),
            'total_trades': self.performance_metrics['total_trades'],
            'win_rate': self.performance_metrics['wins'] / max(self.performance_metrics['total_trades'], 1),
            'timeframe_performance': self.performance_metrics['current_weight_performance'].copy()
        }
        
        # 计算新权重
        new_weights = self._calculate_new_weights()
        
        # 验证新权重
        if not self._validate_weights(new_weights):
            self.logger.warning("[WARN]  新权重验证失败，保持原权重")
            return False
        
        # 创建快照
        snapshot = WeightSnapshot(
            timestamp=time.time(),
            weights=new_weights.copy(),
            trigger_reason=trigger_reason,
            performance_before=performance_before,
            notes=f"调整前权重: {self.current_weights}"
        )
        
        # 更新权重
        old_weights = self.current_weights.copy()
        self.current_weights = new_weights.copy()
        self.last_adjustment_time = time.time()
        
        # 保存历史
        self.weights_history.append(snapshot)
        self._save_weights()
        
        # 重置当前权重下的性能跟踪
        self.performance_metrics['current_weight_performance'] = {}
        
        self.logger.info(f"[REFRESH] 权重调整成功: {old_weights} -> {new_weights} (原因: {trigger_reason})")
        return True
    
    def _calculate_new_weights(self) -> Dict[str, float]:
        """
        计算新的权重分配
        
        返回:
            新的权重字典
        """
        current_weights = self.current_weights.copy()
        tf_list = list(current_weights.keys())
        
        # 计算各时间框架的表现
        tf_performances = {}
        total_performance = 0.0
        
        for tf in tf_list:
            perf = self.calculate_timeframe_performance(tf)
            # 如果没有足够数据，使用平均表现
            if perf is None:
                tf_performances[tf] = 0.5
            else:
                tf_performances[tf] = perf
            total_performance += tf_performances[tf]
        
        # 避免除零
        total_performance = max(total_performance, 0.01)
        
        # 基于表现计算目标权重
        target_weights = {}
        for tf in tf_list:
            target_weights[tf] = tf_performances[tf] / total_performance
        
        # 限制调整幅度 - 先进行初步限制
        constrained_weights = {}
        for tf in tf_list:
            current_weight = current_weights[tf]
            max_delta = self.config.max_adjustment_per_step
            min_w = self.config.min_weight
            max_w = self.config.max_weight
            
            constrained_weights[tf] = max(min_w, min(max_w, max(
                current_weight - max_delta,
                min(current_weight + max_delta, target_weights[tf])
            )))
        
        # 归一化，同时确保不会超出权重调整限制
        max_iterations = 10
        new_weights = constrained_weights.copy()
        
        for _ in range(max_iterations):
            total_weight = sum(new_weights.values())
            
            # 如果总和已经接近1，我们完成了
            if abs(total_weight - 1.0) < 0.001:
                break
            
            # 计算调整因子
            adjustment_factor = 1.0 / total_weight if total_weight > 0 else 1.0
            
            # 应用调整因子，但保持在权重变化限制内
            temp_weights = {}
            for tf in tf_list:
                # 计算候选权重
                candidate = new_weights[tf] * adjustment_factor
                
                # 再次限制权重变化幅度
                current_weight = current_weights[tf]
                max_delta = self.config.max_adjustment_per_step
                min_w = self.config.min_weight
                max_w = self.config.max_weight
                
                # 限制在允许的变化范围内
                temp_weights[tf] = max(min_w, min(max_w, max(
                    current_weight - max_delta,
                    min(current_weight + max_delta, candidate)
                )))
            
            # 检查是否进一步迭代可以改善
            old_total = total_weight
            new_total = sum(temp_weights.values())
            
            if abs(new_total - 1.0) < abs(old_total - 1.0):
                new_weights = temp_weights.copy()
            else:
                break
        
        # 最后再进行一次精确的权重限制验证
        for tf in tf_list:
            new_weights[tf] = max(self.config.min_weight, 
                                  min(self.config.max_weight, new_weights[tf]))
        
        # 最终归一化，但确保不会超出权重变化限制
        total_new = sum(new_weights.values())
        if total_new > 0 and abs(total_new - 1.0) > 0.001:
            adjustment_factor = 1.0 / total_new
            
            # 计算归一化后的权重，但确保不会超出变化限制
            final_weights = {}
            for tf in tf_list:
                current_weight = current_weights[tf]
                max_delta = self.config.max_adjustment_per_step
                min_w = self.config.min_weight
                max_w = self.config.max_weight
                
                # 归一化后的候选值
                candidate = new_weights[tf] * adjustment_factor
                
                # 限制在允许的变化范围内
                final_weights[tf] = max(min_w, min(max_w, max(
                    current_weight - max_delta,
                    min(current_weight + max_delta, candidate)
                )))
            
            # 再次确保总和接近1（通过微调）
            final_total = sum(final_weights.values())
            if final_total > 0:
                # 调整幅度很小，所以直接使用
                new_weights = final_weights
        
        # 最后一次验证，确保所有权重都在限制范围内
        for tf in tf_list:
            current_weight = current_weights[tf]
            max_delta = self.config.max_adjustment_per_step
            min_w = self.config.min_weight
            max_w = self.config.max_weight
            
            # 确保权重在限制范围内
            new_weights[tf] = max(min_w, min(max_w, max(
                current_weight - max_delta,
                min(current_weight + max_delta, new_weights[tf])
            )))
        
        return new_weights
    
    def _validate_weights(self, weights: Dict[str, float]) -> bool:
        """
        验证权重是否有效
        
        参数:
            weights: 待验证的权重
        
        返回:
            是否有效
        """
        if abs(sum(weights.values()) - 1.0) > 0.001:  # 总和必须接近1
            return False
        
        for tf, w in weights.items():
            if w < self.config.min_weight or w > self.config.max_weight:
                return False
        
        return True
    
    def validate_weight_adjustment(self, evaluation_trades: int = 20) -> ValidationStatus:
        """
        验证权重调整的效果
        
        参数:
            evaluation_trades: 用于评估的交易数量
        
        返回:
            验证状态
        """
        if not self.weights_history:
            return ValidationStatus.PENDING
        
        last_snapshot = self.weights_history[-1]
        
        # 检查是否有足够的新交易数据用于评估
        recent_trades = [s for s in self.signal_history if s.timestamp > last_snapshot.timestamp]
        if len(recent_trades) < evaluation_trades:
            return ValidationStatus.PENDING
        
        # 计算调整后的性能
        recent_wins = sum(1 for s in recent_trades if s.result == "win")
        recent_win_rate = recent_wins / max(len(recent_trades), 1)
        
        performance_before = last_snapshot.performance_before.get('win_rate', 0)
        
        # 更新快照
        last_snapshot.performance_after = {
            'win_rate': recent_win_rate,
            'trades_evaluated': len(recent_trades),
            'trades_won': recent_wins
        }
        
        # 判断是否成功
        if recent_win_rate > performance_before:
            last_snapshot.validation_status = ValidationStatus.PASSED.value
            result = ValidationStatus.PASSED
        else:
            last_snapshot.validation_status = ValidationStatus.FAILED.value
            result = ValidationStatus.FAILED
        
        self._save_weights()
        
        self.logger.info(f"[DATA] 权重调整验证结果: {result.value}, 胜率变化: {performance_before:.2f} -> {recent_win_rate:.2f}")
        return result
    
    def get_performance_report(self) -> Dict[str, Any]:
        """
        获取性能报告
        
        返回:
            性能报告字典
        """
        total_trades = self.performance_metrics['total_trades']
        win_rate = self.performance_metrics['wins'] / max(total_trades, 1)
        
        report = {
            'timestamp': time.time(),
            'total_trades': total_trades,
            'wins': self.performance_metrics['wins'],
            'losses': self.performance_metrics['losses'],
            'win_rate': win_rate,
            'current_weights': self.current_weights.copy(),
            'timeframe_performance': self.performance_metrics['current_weight_performance'].copy(),
            'last_adjustment_time': self.last_adjustment_time,
            'weights_history_length': len(self.weights_history)
        }
        
        return report


# 单例实例
_optimizer_instance: Optional[WeightOptimizer] = None


def get_weight_optimizer(config: Optional[WeightConfig] = None) -> WeightOptimizer:
    """
    获取权重优化器单例
    
    参数:
        config: 权重配置（仅在首次调用时使用）
    
    返回:
        权重优化器实例
    """
    global _optimizer_instance
    if _optimizer_instance is None:
        _optimizer_instance = WeightOptimizer(config)
    return _optimizer_instance
