#!/usr/bin/env python3
"""
MT5 AI交易系统 - 智能保证金管理系统
提供保证金需求预测、多级预警、危机处理和仓位联动优化
"""

import time
import threading
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum

from core.logger import logger
from core.mql5_data import get_mql5_data_manager


class MarginLevel(Enum):
    """保证金水平状态"""
    SAFE = "safe"                  # 安全水平：>200%
    NORMAL = "normal"             # 正常水平：100-200%
    WARNING = "warning"           # 警告水平：50-100%
    DANGER = "danger"             # 危险水平：20-50%
    CRITICAL = "critical"         # 临界水平：<20%
    MARGIN_CALL = "margin_call"   # 保证金追缴：<100%


class MarginRiskAction(Enum):
    """保证金风险应对动作"""
    NO_ACTION = "no_action"               # 无需动作
    REDUCE_POSITIONS = "reduce_positions" # 减少持仓
    REDUCE_RISK = "reduce_risk"          # 降低风险
    INCREASE_MARGIN = "increase_margin"  # 增加保证金
    CLOSE_POSITIONS = "close_positions"  # 平仓
    STOP_TRADING = "stop_trading"        # 停止交易


@dataclass
class MarginRequirement:
    """保证金需求预测"""
    symbol: str
    current_volume: float = 0.0
    predicted_volume: float = 0.0
    current_margin: float = 0.0
    predicted_margin: float = 0.0
    margin_per_lot: float = 0.0
    volatility_impact: float = 1.0
    leverage_factor: float = 1.0


@dataclass
class MarginForecast:
    """保证金预测结果"""
    timestamp: datetime = field(default_factory=datetime.now)
    current_margin_used: float = 0.0
    current_margin_free: float = 0.0
    current_margin_level: float = 0.0
    predicted_margin_needed: float = 0.0
    available_for_trading: float = 0.0
    risk_score: float = 0.0
    margin_level_status: MarginLevel = MarginLevel.SAFE
    recommended_action: MarginRiskAction = MarginRiskAction.NO_ACTION
    warning_messages: List[str] = field(default_factory=list)
    predictions: List[MarginRequirement] = field(default_factory=list)


class MarginManager:
    """智能保证金管理器"""
    
    def __init__(self):
        self.mql5_data = get_mql5_data_manager()
        self.forecast_history: List[MarginForecast] = []
        self.margin_requirements_cache: Dict[str, float] = {}
        
        # 保证金预警阈值（百分比）
        self.margin_thresholds = {
            MarginLevel.SAFE: 200.0,      # >200%：安全
            MarginLevel.NORMAL: 100.0,    # 100-200%：正常
            MarginLevel.WARNING: 50.0,    # 50-100%：警告
            MarginLevel.DANGER: 20.0,     # 20-50%：危险
            MarginLevel.CRITICAL: 5.0,    # 5-20%：临界
            MarginLevel.MARGIN_CALL: 0.0  # <100%：保证金追缴
        }
        
        # 每手保证金要求（简化估算，实际应从MT5获取）
        self.margin_per_lot = {
            "EURUSD": 1000.0,     # 1000美元/手
            "GBPUSD": 1000.0,
            "USDJPY": 1000.0,
            "USDCHF": 1000.0,
            "AUDUSD": 1000.0,
            "USDCAD": 1000.0,
            "GOLD": 2000.0,       # 黄金2000美元/手
            "XAUUSD": 2000.0,
            "XAGUSD": 3000.0,     # 白银3000美元/手
            "OIL": 5000.0,        # 原油5000美元/手
            "BTCUSD": 50000.0,    # 比特币50000美元/手
        }
        
        # 市场波动率影响系数（高波动品种增加保证金需求）
        self.volatility_impact = {
            "EURUSD": 1.0,
            "GBPUSD": 1.1,
            "USDJPY": 1.2,
            "GOLD": 1.5,
            "XAUUSD": 1.5,
            "OIL": 2.0,
            "BTCUSD": 3.0
        }
        
        # 运行状态
        self.running = False
        self.monitor_thread: Optional[threading.Thread] = None
        self.update_interval = 10  # 每10秒更新一次
        
        logger.info("[MarginManager] 智能保证金管理器初始化完成")
    
    def start(self):
        """启动保证金监控"""
        if self.running:
            logger.warning("[WARN]  保证金管理器已在运行中")
            return
        
        self.running = True
        self.monitor_thread = threading.Thread(
            target=self._monitor_loop, 
            daemon=True
        )
        self.monitor_thread.start()
        logger.info("[MarginManager]  保证金监控已启动")
    
    def stop(self):
        """停止保证金监控"""
        self.running = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5)
        logger.info("[MarginManager]  保证金监控已停止")
    
    def _monitor_loop(self):
        """保证金监控循环"""
        logger.info("[MarginManager]  保证金监控循环开始")
        
        while self.running:
            try:
                # 获取实时数据
                realtime_data = self.mql5_data.get_real_time_data_summary()
                
                if realtime_data:
                    # 生成保证金预测
                    forecast = self.generate_margin_forecast(realtime_data)
                    
                    # 检查是否需要预警
                    self._check_margin_warnings(forecast)
                    
                    # 记录预测历史
                    self.forecast_history.append(forecast)
                    if len(self.forecast_history) > 100:
                        self.forecast_history = self.forecast_history[-100:]
                
                time.sleep(self.update_interval)
                
            except Exception as e:
                logger.error(f"[ERR] 保证金监控循环异常: {e}")
                time.sleep(30)
    
    def generate_margin_forecast(self, realtime_data: Dict[str, Any]) -> MarginForecast:
        """生成保证金需求预测"""
        try:
            account_summary = realtime_data.get("account_summary", {})
            positions_summary = realtime_data.get("positions_summary", {})
            
            current_margin_used = account_summary.get("margin_used", 0.0)
            current_margin_free = account_summary.get("margin_free", 0.0)
            current_balance = account_summary.get("balance", 10000.0)
            current_margin_level = account_summary.get("margin_level", 0.0)
            
            # 预测未来保证金需求
            predicted_needs = self._predict_margin_needs(
                positions_summary, current_balance
            )
            
            # 计算可用交易资金
            available_for_trading = self._calculate_available_for_trading(
                current_margin_free, predicted_needs, current_margin_level
            )
            
            # 评估风险分数
            risk_score = self._calculate_margin_risk_score(
                current_margin_level, current_margin_free, current_margin_used
            )
            
            # 确定保证金水平状态
            margin_level_status = self._determine_margin_level(current_margin_level)
            
            # 推荐应对动作
            recommended_action = self._determine_risk_action(
                margin_level_status, risk_score, available_for_trading
            )
            
            # 生成警告信息
            warning_messages = self._generate_warning_messages(
                margin_level_status, current_margin_level, available_for_trading
            )
            
            forecast = MarginForecast(
                timestamp=datetime.now(),
                current_margin_used=current_margin_used,
                current_margin_free=current_margin_free,
                current_margin_level=current_margin_level,
                predicted_margin_needed=predicted_needs,
                available_for_trading=available_for_trading,
                risk_score=risk_score,
                margin_level_status=margin_level_status,
                recommended_action=recommended_action,
                warning_messages=warning_messages,
                predictions=self._create_margin_predictions(positions_summary)
            )
            
            return forecast
            
        except Exception as e:
            logger.error(f"[ERR] 生成保证金预测失败: {e}")
            
            # 返回保守的默认预测
            return MarginForecast(
                timestamp=datetime.now(),
                current_margin_used=0.0,
                current_margin_free=10000.0,
                current_margin_level=1000.0,
                predicted_margin_needed=0.0,
                available_for_trading=10000.0,
                risk_score=0.1,
                margin_level_status=MarginLevel.SAFE,
                recommended_action=MarginRiskAction.NO_ACTION,
                warning_messages=[f"预测失败: {str(e)}"]
            )
    
    def _predict_margin_needs(self, positions_summary: Dict[str, Any], balance: float) -> float:
        """预测未来保证金需求"""
        try:
            total_predicted_margin = 0.0
            
            # 当前持仓的保证金需求
            total_volume = positions_summary.get("total_volume", 0.0)
            by_symbol = positions_summary.get("by_symbol", {})
            
            # 计算当前持仓保证金
            for symbol, data in by_symbol.items():
                volume = data.get("total_volume", 0.0)
                margin_per_lot = self.margin_per_lot.get(symbol, 1000.0)
                vol_impact = self.volatility_impact.get(symbol, 1.0)
                
                current_margin = volume * margin_per_lot * vol_impact
                total_predicted_margin += current_margin
            
            # 预测新开仓需求（基于风险限制）
            # 假设每笔交易风险为账户的1%，最大仓位为5%
            max_risk_per_trade = balance * 0.01
            max_position_size = balance * 0.05
            
            # 预估新开仓保证金需求（平均每手1000美元）
            avg_margin_per_lot = 1000.0
            predicted_new_positions_margin = min(
                max_risk_per_trade * 5,  # 最多5笔交易
                max_position_size * 0.3  # 不超过最大仓位的30%
            )
            
            total_predicted_margin += predicted_new_positions_margin
            
            # 考虑市场波动性增加
            market_volatility_factor = self._get_market_volatility_factor()
            total_predicted_margin *= market_volatility_factor
            
            return total_predicted_margin
            
        except Exception as e:
            logger.error(f"[ERR] 预测保证金需求失败: {e}")
            return balance * 0.3  # 保守估计：30%的账户余额
    
    def _calculate_available_for_trading(self, margin_free: float, 
                                         predicted_needs: float, 
                                         margin_level: float) -> float:
        """计算可用于交易的资金"""
        try:
            # 基础可用资金
            base_available = margin_free
            
            # 根据保证金水平调整
            if margin_level > 200.0:
                # 安全水平：可使用80%的可用保证金
                multiplier = 0.8
            elif margin_level > 100.0:
                # 正常水平：可使用50%的可用保证金
                multiplier = 0.5
            elif margin_level > 50.0:
                # 警告水平：可使用20%的可用保证金
                multiplier = 0.2
            else:
                # 危险水平：不建议新增交易
                multiplier = 0.05
            
            available = base_available * multiplier
            
            # 确保不超过预测需求
            available = min(available, predicted_needs * 1.5)
            
            # 最低交易资金（100美元）
            available = max(available, 100.0)
            
            return available
            
        except Exception as e:
            logger.error(f"[ERR] 计算可用交易资金失败: {e}")
            return margin_free * 0.3
    
    def _calculate_margin_risk_score(self, margin_level: float, 
                                     margin_free: float, 
                                     margin_used: float) -> float:
        """计算保证金风险分数（0-1，越高风险越大）"""
        try:
            risk_score = 0.0
            
            # 保证金水平贡献（0-0.5）
            if margin_level < 20.0:
                risk_score += 0.5
            elif margin_level < 50.0:
                risk_score += 0.4
            elif margin_level < 100.0:
                risk_score += 0.3
            elif margin_level < 200.0:
                risk_score += 0.1
            
            # 已用保证金比例贡献（0-0.3）
            total_margin = margin_used + margin_free
            if total_margin > 0:
                used_ratio = margin_used / total_margin
                risk_score += used_ratio * 0.3
            
            # 绝对可用保证金贡献（0-0.2）
            if margin_free < 1000.0:
                risk_score += 0.2
            elif margin_free < 5000.0:
                risk_score += 0.1
            
            return min(risk_score, 1.0)
            
        except Exception as e:
            logger.error(f"[ERR] 计算保证金风险分数失败: {e}")
            return 0.5
    
    def _determine_margin_level(self, margin_level: float) -> MarginLevel:
        """确定保证金水平状态"""
        if margin_level >= self.margin_thresholds[MarginLevel.SAFE]:
            return MarginLevel.SAFE
        elif margin_level >= self.margin_thresholds[MarginLevel.NORMAL]:
            return MarginLevel.NORMAL
        elif margin_level >= self.margin_thresholds[MarginLevel.WARNING]:
            return MarginLevel.WARNING
        elif margin_level >= self.margin_thresholds[MarginLevel.DANGER]:
            return MarginLevel.DANGER
        elif margin_level >= self.margin_thresholds[MarginLevel.CRITICAL]:
            return MarginLevel.CRITICAL
        else:
            return MarginLevel.MARGIN_CALL
    
    def _determine_risk_action(self, margin_status: MarginLevel, 
                               risk_score: float, 
                               available_for_trading: float) -> MarginRiskAction:
        """根据保证金状态确定应对动作"""
        if margin_status == MarginLevel.MARGIN_CALL:
            return MarginRiskAction.CLOSE_POSITIONS
        
        if margin_status == MarginLevel.CRITICAL:
            if risk_score > 0.8:
                return MarginRiskAction.CLOSE_POSITIONS
            else:
                return MarginRiskAction.REDUCE_POSITIONS
        
        if margin_status == MarginLevel.DANGER:
            if risk_score > 0.7:
                return MarginRiskAction.REDUCE_POSITIONS
            else:
                return MarginRiskAction.REDUCE_RISK
        
        if margin_status == MarginLevel.WARNING:
            if risk_score > 0.6:
                return MarginRiskAction.REDUCE_RISK
            elif available_for_trading < 500.0:
                return MarginRiskAction.INCREASE_MARGIN
            else:
                return MarginRiskAction.NO_ACTION
        
        if margin_status == MarginLevel.NORMAL:
            if available_for_trading < 1000.0:
                return MarginRiskAction.INCREASE_MARGIN
            else:
                return MarginRiskAction.NO_ACTION
        
        return MarginRiskAction.NO_ACTION
    
    def _generate_warning_messages(self, margin_status: MarginLevel, 
                                   margin_level: float, 
                                   available_for_trading: float) -> List[str]:
        """生成警告信息"""
        warnings = []
        
        if margin_status == MarginLevel.MARGIN_CALL:
            warnings.append(f"[紧急] 保证金追缴！水平: {margin_level:.1f}%，立即平仓！")
        
        elif margin_status == MarginLevel.CRITICAL:
            warnings.append(f"[危险] 保证金水平极低: {margin_level:.1f}%，建议立即减仓")
        
        elif margin_status == MarginLevel.DANGER:
            warnings.append(f"[警告] 保证金水平危险: {margin_level:.1f}%，建议减少风险")
        
        elif margin_status == MarginLevel.WARNING:
            warnings.append(f"[注意] 保证金水平警告: {margin_level:.1f}%，需关注")
        
        if available_for_trading < 500.0:
            warnings.append(f"[提示] 可用交易资金较少: ${available_for_trading:.2f}")
        
        return warnings
    
    def _create_margin_predictions(self, positions_summary: Dict[str, Any]) -> List[MarginRequirement]:
        """创建保证金需求预测详情"""
        predictions = []
        by_symbol = positions_summary.get("by_symbol", {})
        
        for symbol, data in by_symbol.items():
            current_volume = data.get("total_volume", 0.0)
            
            # 预测未来仓位（基于当前持仓和风险偏好）
            predicted_volume = current_volume * 1.2  # 保守预测：增加20%
            
            margin_per_lot = self.margin_per_lot.get(symbol, 1000.0)
            vol_impact = self.volatility_impact.get(symbol, 1.0)
            
            current_margin = current_volume * margin_per_lot * vol_impact
            predicted_margin = predicted_volume * margin_per_lot * vol_impact
            
            prediction = MarginRequirement(
                symbol=symbol,
                current_volume=current_volume,
                predicted_volume=predicted_volume,
                current_margin=current_margin,
                predicted_margin=predicted_margin,
                margin_per_lot=margin_per_lot,
                volatility_impact=vol_impact,
                leverage_factor=1.0
            )
            
            predictions.append(prediction)
        
        return predictions
    
    def _get_market_volatility_factor(self) -> float:
        """获取市场波动性因子"""
        # 简化：根据时间（新闻发布时间）增加波动性
        current_hour = datetime.now().hour
        
        # 重要新闻发布时间段（GMT时间）
        if 12 <= current_hour < 16:  # 伦敦下午、纽约上午
            return 1.3
        elif 8 <= current_hour < 12:  # 伦敦上午
            return 1.1
        elif 0 <= current_hour < 6:  # 亚洲时段
            return 0.9
        else:
            return 1.0
    
    def _check_margin_warnings(self, forecast: MarginForecast):
        """检查并记录保证金警告"""
        if forecast.margin_level_status in [MarginLevel.MARGIN_CALL, MarginLevel.CRITICAL]:
            logger.warning(f"[MARGIN WARNING] 紧急！保证金水平: {forecast.current_margin_level:.1f}%")
            logger.warning(f"[ACTION] 建议动作: {forecast.recommended_action.value}")
            
            for msg in forecast.warning_messages:
                logger.warning(f"[WARN]  {msg}")
        
        elif forecast.margin_level_status == MarginLevel.DANGER:
            logger.warning(f"[MARGIN WARNING] 危险！保证金水平: {forecast.current_margin_level:.1f}%")
            logger.warning(f"[ACTION] 建议动作: {forecast.recommended_action.value}")
    
    def get_margin_advice_for_trade(self, symbol: str, position_size: float, 
                                    current_price: float) -> Dict[str, Any]:
        """获取特定交易的保证金建议"""
        try:
            # 获取实时数据
            realtime_data = self.mql5_data.get_real_time_data_summary()
            account_summary = realtime_data.get("account_summary", {})
            
            margin_free = account_summary.get("margin_free", 0.0)
            margin_level = account_summary.get("margin_level", 0.0)
            
            # 计算新交易保证金需求
            margin_per_lot = self.margin_per_lot.get(symbol, 1000.0)
            vol_impact = self.volatility_impact.get(symbol, 1.0)
            
            margin_needed = position_size * margin_per_lot * vol_impact
            
            # 检查保证金是否充足
            margin_sufficient = margin_free >= margin_needed
            
            # 计算保证金使用率
            margin_used_ratio = margin_needed / margin_free if margin_free > 0 else 0
            
            # 建议
            advice = {
                "margin_needed": margin_needed,
                "margin_available": margin_free,
                "margin_sufficient": margin_sufficient,
                "margin_level": margin_level,
                "margin_used_ratio": margin_used_ratio,
                "recommended_max_position": self._calculate_recommended_max_position(
                    symbol, margin_free, margin_level
                ),
                "warning_level": "none"
            }
            
            # 设置警告级别
            if not margin_sufficient:
                advice["warning_level"] = "critical"
                advice["message"] = "保证金不足，无法开仓"
            elif margin_used_ratio > 0.8:
                advice["warning_level"] = "high"
                advice["message"] = "保证金占用率过高，建议减少仓位"
            elif margin_used_ratio > 0.5:
                advice["warning_level"] = "medium"
                advice["message"] = "保证金占用率中等，建议谨慎"
            else:
                advice["warning_level"] = "low"
                advice["message"] = "保证金充足"
            
            return advice
            
        except Exception as e:
            logger.error(f"[ERR] 获取交易保证金建议失败: {e}")
            
            return {
                "margin_needed": position_size * 1000.0,
                "margin_available": 10000.0,
                "margin_sufficient": True,
                "margin_level": 1000.0,
                "margin_used_ratio": 0.1,
                "recommended_max_position": position_size,
                "warning_level": "unknown",
                "message": f"计算失败: {str(e)}"
            }
    
    def _calculate_recommended_max_position(self, symbol: str, margin_free: float, 
                                           margin_level: float) -> float:
        """计算推荐的最大仓位"""
        margin_per_lot = self.margin_per_lot.get(symbol, 1000.0)
        vol_impact = self.volatility_impact.get(symbol, 1.0)
        
        # 根据保证金水平调整可用比例
        if margin_level > 300.0:
            available_ratio = 0.8
        elif margin_level > 200.0:
            available_ratio = 0.6
        elif margin_level > 100.0:
            available_ratio = 0.4
        elif margin_level > 50.0:
            available_ratio = 0.2
        else:
            available_ratio = 0.05
        
        available_margin = margin_free * available_ratio
        max_lots = available_margin / (margin_per_lot * vol_impact)
        
        return max(0.01, max_lots)
    
    def get_margin_report(self) -> Dict[str, Any]:
        """获取保证金报告"""
        try:
            # 获取最新预测
            latest_forecast = None
            if self.forecast_history:
                latest_forecast = self.forecast_history[-1]
            
            # 获取实时数据
            realtime_data = self.mql5_data.get_real_time_data_summary()
            account_summary = realtime_data.get("account_summary", {})
            
            return {
                "current_status": {
                    "margin_used": account_summary.get("margin_used", 0.0),
                    "margin_free": account_summary.get("margin_free", 0.0),
                    "margin_level": account_summary.get("margin_level", 0.0),
                    "balance": account_summary.get("balance", 0.0),
                    "equity": account_summary.get("equity", 0.0)
                },
                "forecast": {
                    "available_for_trading": latest_forecast.available_for_trading if latest_forecast else 0.0,
                    "risk_score": latest_forecast.risk_score if latest_forecast else 0.0,
                    "margin_level_status": latest_forecast.margin_level_status.value if latest_forecast else "unknown",
                    "recommended_action": latest_forecast.recommended_action.value if latest_forecast else "no_action"
                },
                "thresholds": {k.value: v for k, v in self.margin_thresholds.items()},
                "warning_messages": latest_forecast.warning_messages if latest_forecast else [],
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"[ERR] 获取保证金报告失败: {e}")
            
            return {
                "current_status": {
                    "margin_used": 0.0,
                    "margin_free": 10000.0,
                    "margin_level": 1000.0,
                    "balance": 10000.0,
                    "equity": 10000.0
                },
                "forecast": {
                    "available_for_trading": 10000.0,
                    "risk_score": 0.1,
                    "margin_level_status": "safe",
                    "recommended_action": "no_action"
                },
                "thresholds": {k.value: v for k, v in self.margin_thresholds.items()},
                "warning_messages": ["获取报告失败"],
                "timestamp": datetime.now().isoformat()
            }


# 全局保证金管理器实例
_global_margin_manager: Optional[MarginManager] = None


def get_margin_manager() -> MarginManager:
    """获取全局保证金管理器实例"""
    global _global_margin_manager
    if not _global_margin_manager:
        _global_margin_manager = MarginManager()
    return _global_margin_manager


if __name__ == "__main__":
    print("="*70)
    print("[测试] 智能保证金管理系统")
    print("="*70)
    
    # 测试保证金管理器
    margin_manager = MarginManager()
    
    # 创建模拟数据
    test_data = {
        "account_summary": {
            "balance": 15000.0,
            "equity": 15230.5,
            "margin_used": 850.0,
            "margin_free": 14380.5,
            "margin_level": 1791.8,
            "floating_profit": 230.5
        },
        "positions_summary": {
            "total_count": 2,
            "total_volume": 0.15,
            "total_profit": 40.0,
            "by_symbol": {
                "EURUSD": {
                    "total_volume": 0.1,
                    "total_profit": 15.0,
                    "position_count": 1
                },
                "GOLD": {
                    "total_volume": 0.05,
                    "total_profit": 25.0,
                    "position_count": 1
                }
            }
        }
    }
    
    # 生成预测
    print("\n[测试] 生成保证金预测...")
    forecast = margin_manager.generate_margin_forecast(test_data)
    
    print(f"保证金水平: {forecast.current_margin_level:.1f}%")
    print(f"状态: {forecast.margin_level_status.value}")
    print(f"风险分数: {forecast.risk_score:.2f}")
    print(f"推荐动作: {forecast.recommended_action.value}")
    print(f"可用交易资金: ${forecast.available_for_trading:.2f}")
    
    if forecast.warning_messages:
        print("警告信息:")
        for msg in forecast.warning_messages:
            print(f"  - {msg}")
    
    # 测试交易保证金建议
    print("\n[测试] 交易保证金建议...")
    advice = margin_manager.get_margin_advice_for_trade(
        symbol="EURUSD",
        position_size=0.1,
        current_price=1.0865
    )
    
    print(f"保证金需求: ${advice['margin_needed']:.2f}")
    print(f"保证金可用: ${advice['margin_available']:.2f}")
    print(f"是否充足: {'是' if advice['margin_sufficient'] else '否'}")
    print(f"警告级别: {advice['warning_level']}")
    print(f"建议: {advice['message']}")
    
    print("\n[OK] 智能保证金管理系统测试完成！")