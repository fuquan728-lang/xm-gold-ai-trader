#!/usr/bin/env python3
"""
MT5 AI交易系统 - 保证金危机处理模块
处理保证金紧急情况：追缴、爆仓风险、流动性危机等
"""

import time
import threading
import json
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum

from core.logger import logger
from core.mql5_data import get_mql5_data_manager
from core.margin_manager import get_margin_manager, MarginLevel, MarginRiskAction
from core.file_handler import file_handler


class CrisisSeverity(Enum):
    """危机严重程度"""
    LOW = "low"            # 低风险：预警级别
    MEDIUM = "medium"      # 中风险：需要干预
    HIGH = "high"          # 高风险：紧急处理
    CRITICAL = "critical"  # 临界风险：立即行动


class CrisisAction(Enum):
    """危机处理动作"""
    MONITOR_ONLY = "monitor_only"          # 仅监控
    REDUCE_RISK_PARAMS = "reduce_risk_params"  # 降低风险参数
    CLOSE_SMALL_POSITIONS = "close_small_positions"  # 平小额持仓
    CLOSE_LOSING_POSITIONS = "close_losing_positions"  # 平亏损持仓
    CLOSE_ALL_POSITIONS = "close_all_positions"  # 平所有持仓
    STOP_ALL_TRADING = "stop_all_trading"  # 停止所有交易
    NOTIFY_USER = "notify_user"            # 通知用户


@dataclass
class PositionToClose:
    """待平仓持仓信息"""
    ticket: int
    symbol: str
    type: str
    volume: float
    open_price: float
    current_price: float
    profit: float
    profit_pct: float
    priority_score: float  # 优先级分数（越高越优先平仓）


@dataclass
class CrisisPlan:
    """危机处理计划"""
    timestamp: datetime = field(default_factory=datetime.now)
    severity: CrisisSeverity = CrisisSeverity.LOW
    margin_level: float = 0.0
    crisis_score: float = 0.0
    primary_action: CrisisAction = CrisisAction.MONITOR_ONLY
    secondary_actions: List[CrisisAction] = field(default_factory=list)
    positions_to_close: List[PositionToClose] = field(default_factory=list)
    risk_adjustments: Dict[str, Any] = field(default_factory=dict)
    estimated_time_to_margin_call: float = 0.0  # 预计到保证金追缴的时间（小时）
    recovery_plan: List[str] = field(default_factory=list)
    user_notifications: List[str] = field(default_factory=list)


class MarginCrisisHandler:
    """保证金危机处理器"""
    
    def __init__(self):
        self.mql5_data = get_mql5_data_manager()
        self.margin_manager = get_margin_manager()
        
        # 危机计划历史
        self.crisis_plans: List[CrisisPlan] = []
        
        # 危机阈值
        self.crisis_thresholds = {
            CrisisSeverity.LOW: {
                "margin_level": 100.0,      # 100-200%
                "crisis_score": 0.3,
                "check_interval": 300       # 每5分钟检查
            },
            CrisisSeverity.MEDIUM: {
                "margin_level": 50.0,       # 50-100%
                "crisis_score": 0.5,
                "check_interval": 60        # 每1分钟检查
            },
            CrisisSeverity.HIGH: {
                "margin_level": 20.0,       # 20-50%
                "crisis_score": 0.7,
                "check_interval": 30        # 每30秒检查
            },
            CrisisSeverity.CRITICAL: {
                "margin_level": 10.0,       # <20%
                "crisis_score": 0.9,
                "check_interval": 10        # 每10秒检查
            }
        }
        
        # 危机应对策略
        self.crisis_response_strategies = {
            CrisisSeverity.LOW: [
                CrisisAction.REDUCE_RISK_PARAMS,
                CrisisAction.MONITOR_ONLY
            ],
            CrisisSeverity.MEDIUM: [
                CrisisAction.CLOSE_SMALL_POSITIONS,
                CrisisAction.REDUCE_RISK_PARAMS,
                CrisisAction.NOTIFY_USER
            ],
            CrisisSeverity.HIGH: [
                CrisisAction.CLOSE_LOSING_POSITIONS,
                CrisisAction.CLOSE_SMALL_POSITIONS,
                CrisisAction.REDUCE_RISK_PARAMS,
                CrisisAction.NOTIFY_USER
            ],
            CrisisSeverity.CRITICAL: [
                CrisisAction.CLOSE_ALL_POSITIONS,
                CrisisAction.STOP_ALL_TRADING,
                CrisisAction.NOTIFY_USER
            ]
        }
        
        # 运行状态
        self.running = False
        self.crisis_monitor_thread: Optional[threading.Thread] = None
        self.in_crisis_mode = False
        self.last_crisis_check = datetime.now()
        
        logger.info("[CrisisHandler] 保证金危机处理器初始化完成")
    
    def start(self):
        """启动危机监控"""
        if self.running:
            logger.warning("[WARN]  危机处理器已在运行中")
            return
        
        self.running = True
        self.crisis_monitor_thread = threading.Thread(
            target=self._crisis_monitor_loop, 
            daemon=True
        )
        self.crisis_monitor_thread.start()
        logger.info("[CrisisHandler]  危机监控已启动")
    
    def stop(self):
        """停止危机监控"""
        self.running = False
        if self.crisis_monitor_thread:
            self.crisis_monitor_thread.join(timeout=5)
        logger.info("[CrisisHandler]  危机监控已停止")
    
    def _crisis_monitor_loop(self):
        """危机监控循环"""
        logger.info("[CrisisHandler]  危机监控循环开始")
        
        while self.running:
            try:
                # 获取实时数据
                realtime_data = self.mql5_data.get_real_time_data_summary()
                
                if realtime_data:
                    # 检查危机状态
                    crisis_status = self.check_crisis_status(realtime_data)
                    
                    if crisis_status["severity"] != CrisisSeverity.LOW:
                        # 生成危机处理计划
                        crisis_plan = self.generate_crisis_plan(crisis_status)
                        
                        # 执行危机处理
                        self.execute_crisis_plan(crisis_plan)
                        
                        # 记录危机事件
                        self.crisis_plans.append(crisis_plan)
                        if len(self.crisis_plans) > 50:
                            self.crisis_plans = self.crisis_plans[-50:]
                        
                        # 设置危机模式标志
                        self.in_crisis_mode = True
                        
                        logger.warning(f"[CRISIS] 危机处理已触发: {crisis_status['severity'].value}")
                    else:
                        # 正常状态，清除危机模式
                        if self.in_crisis_mode:
                            logger.info("[CRISIS] 危机已解除，返回正常模式")
                            self.in_crisis_mode = False
                
                # 根据危机严重程度调整检查间隔
                check_interval = self._get_check_interval(crisis_status["severity"] if 'crisis_status' in locals() else {"severity": CrisisSeverity.LOW})
                time.sleep(check_interval)
                
            except Exception as e:
                logger.error(f"[ERR] 危机监控循环异常: {e}")
                time.sleep(60)
    
    def _get_check_interval(self, severity: CrisisSeverity) -> int:
        """根据危机严重程度获取检查间隔"""
        return self.crisis_thresholds.get(severity, {}).get("check_interval", 300)
    
    def check_crisis_status(self, realtime_data: Dict[str, Any]) -> Dict[str, Any]:
        """检查危机状态"""
        try:
            account_summary = realtime_data.get("account_summary", {})
            positions_summary = realtime_data.get("positions_summary", {})
            
            margin_level = account_summary.get("margin_level", 0.0)
            margin_free = account_summary.get("margin_free", 0.0)
            margin_used = account_summary.get("margin_used", 0.0)
            floating_profit = account_summary.get("floating_profit", 0.0)
            
            # 计算危机分数
            crisis_score = self._calculate_crisis_score(
                margin_level, margin_free, margin_used, floating_profit
            )
            
            # 确定危机严重程度
            severity = self._determine_crisis_severity(margin_level, crisis_score)
            
            # 评估爆仓风险
            margin_call_risk = self._assess_margin_call_risk(
                margin_level, margin_free, positions_summary
            )
            
            return {
                "severity": severity,
                "margin_level": margin_level,
                "crisis_score": crisis_score,
                "margin_call_risk": margin_call_risk,
                "timestamp": datetime.now().isoformat(),
                "account_data": {
                    "margin_free": margin_free,
                    "margin_used": margin_used,
                    "floating_profit": floating_profit
                }
            }
            
        except Exception as e:
            logger.error(f"[ERR] 检查危机状态失败: {e}")
            
            return {
                "severity": CrisisSeverity.LOW,
                "margin_level": 1000.0,
                "crisis_score": 0.1,
                "margin_call_risk": 0.0,
                "timestamp": datetime.now().isoformat(),
                "account_data": {}
            }
    
    def _calculate_crisis_score(self, margin_level: float, margin_free: float, 
                                margin_used: float, floating_profit: float) -> float:
        """计算危机分数（0-1，越高越危险）"""
        try:
            crisis_score = 0.0
            
            # 保证金水平贡献（0-0.4）
            if margin_level < 20.0:
                crisis_score += 0.4
            elif margin_level < 50.0:
                crisis_score += 0.3
            elif margin_level < 100.0:
                crisis_score += 0.2
            elif margin_level < 200.0:
                crisis_score += 0.1
            
            # 浮动盈亏贡献（0-0.3）
            if floating_profit < -1000.0:  # 亏损超过1000美元
                crisis_score += 0.3
            elif floating_profit < -500.0:
                crisis_score += 0.2
            elif floating_profit < -200.0:
                crisis_score += 0.1
            
            # 可用保证金比例贡献（0-0.3）
            total_margin = margin_used + margin_free
            if total_margin > 0:
                free_ratio = margin_free / total_margin
                if free_ratio < 0.1:  # 可用保证金少于10%
                    crisis_score += 0.3
                elif free_ratio < 0.2:
                    crisis_score += 0.2
                elif free_ratio < 0.3:
                    crisis_score += 0.1
            
            return min(crisis_score, 1.0)
            
        except Exception as e:
            logger.error(f"[ERR] 计算危机分数失败: {e}")
            return 0.0
    
    def _determine_crisis_severity(self, margin_level: float, crisis_score: float) -> CrisisSeverity:
        """确定危机严重程度"""
        if margin_level < self.crisis_thresholds[CrisisSeverity.CRITICAL]["margin_level"]:
            return CrisisSeverity.CRITICAL
        elif margin_level < self.crisis_thresholds[CrisisSeverity.HIGH]["margin_level"]:
            return CrisisSeverity.HIGH
        elif margin_level < self.crisis_thresholds[CrisisSeverity.MEDIUM]["margin_level"]:
            return CrisisSeverity.MEDIUM
        else:
            return CrisisSeverity.LOW
    
    def _assess_margin_call_risk(self, margin_level: float, margin_free: float, 
                                 positions_summary: Dict[str, Any]) -> float:
        """评估保证金追缴风险（0-1，越高风险越大）"""
        try:
            if margin_level >= 100.0:
                return 0.0
            
            # 基础风险（保证金水平低于100%）
            base_risk = (100.0 - margin_level) / 100.0
            
            # 持仓风险加成
            total_volume = positions_summary.get("total_volume", 0.0)
            if total_volume > 10.0:  # 总持仓超过10手
                base_risk += 0.3
            elif total_volume > 5.0:
                base_risk += 0.2
            elif total_volume > 2.0:
                base_risk += 0.1
            
            # 可用保证金风险加成
            if margin_free < 100.0:  # 可用保证金少于100美元
                base_risk += 0.3
            elif margin_free < 500.0:
                base_risk += 0.2
            elif margin_free < 1000.0:
                base_risk += 0.1
            
            return min(base_risk, 1.0)
            
        except Exception as e:
            logger.error(f"[ERR] 评估保证金追缴风险失败: {e}")
            return 0.0
    
    def generate_crisis_plan(self, crisis_status: Dict[str, Any]) -> CrisisPlan:
        """生成危机处理计划"""
        try:
            severity = crisis_status["severity"]
            margin_level = crisis_status["margin_level"]
            crisis_score = crisis_status["crisis_score"]
            
            # 获取当前持仓数据
            raw_data = self.mql5_data.get_raw_data()
            positions = raw_data.get("positions", [])
            
            # 分析待平仓持仓
            positions_to_close = self._analyze_positions_to_close(positions, severity)
            
            # 确定主要和次要动作
            primary_action, secondary_actions = self._determine_crisis_actions(severity)
            
            # 计算风险调整参数
            risk_adjustments = self._calculate_risk_adjustments(severity, margin_level)
            
            # 估算到保证金追缴的时间
            estimated_time = self._estimate_time_to_margin_call(crisis_status)
            
            # 生成恢复计划
            recovery_plan = self._generate_recovery_plan(severity, margin_level)
            
            # 生成用户通知
            user_notifications = self._generate_user_notifications(severity, margin_level, crisis_score)
            
            plan = CrisisPlan(
                timestamp=datetime.now(),
                severity=severity,
                margin_level=margin_level,
                crisis_score=crisis_score,
                primary_action=primary_action,
                secondary_actions=secondary_actions,
                positions_to_close=positions_to_close,
                risk_adjustments=risk_adjustments,
                estimated_time_to_margin_call=estimated_time,
                recovery_plan=recovery_plan,
                user_notifications=user_notifications
            )
            
            return plan
            
        except Exception as e:
            logger.error(f"[ERR] 生成危机处理计划失败: {e}")
            
            return CrisisPlan(
                timestamp=datetime.now(),
                severity=CrisisSeverity.LOW,
                margin_level=1000.0,
                crisis_score=0.0,
                primary_action=CrisisAction.MONITOR_ONLY,
                risk_adjustments={},
                recovery_plan=["恢复失败，请手动处理"],
                user_notifications=[f"危机计划生成失败: {str(e)}"]
            )
    
    def _analyze_positions_to_close(self, positions: List[Dict[str, Any]], 
                                    severity: CrisisSeverity) -> List[PositionToClose]:
        """分析待平仓持仓（优先级排序）"""
        positions_to_close = []
        
        try:
            for pos in positions:
                profit = pos.get("profit", 0.0)
                volume = pos.get("volume", 0.0)
                open_price = pos.get("open_price", 0.0)
                current_price = pos.get("current_price", 0.0)
                
                # 计算盈亏百分比
                profit_pct = 0.0
                if open_price > 0 and current_price > 0:
                    if pos.get("type", "").upper() == "BUY":
                        profit_pct = (current_price - open_price) / open_price * 100
                    else:  # SELL
                        profit_pct = (open_price - current_price) / open_price * 100
                
                # 计算优先级分数（越高越优先平仓）
                priority_score = 0.0
                
                # 亏损持仓优先级高
                if profit < 0:
                    priority_score += 0.4
                    # 亏损越多优先级越高
                    loss_pct = abs(profit_pct)
                    priority_score += min(loss_pct / 10.0, 0.3)  # 每10%亏损增加0.3分
                
                # 小额持仓优先级较高（易于平仓）
                if volume < 0.1:  # 小于0.1手
                    priority_score += 0.3
                elif volume < 0.5:
                    priority_score += 0.2
                
                # 根据危机严重程度调整
                if severity == CrisisSeverity.CRITICAL:
                    # 危机情况下，所有持仓都考虑平仓
                    priority_score += 0.5
                elif severity == CrisisSeverity.HIGH:
                    priority_score += 0.3
                
                # 高波动品种优先级较高
                symbol = pos.get("symbol", "")
                if symbol in ["GOLD", "XAUUSD", "OIL", "BTCUSD"]:
                    priority_score += 0.2
                
                # 创建待平仓持仓信息
                if priority_score > 0.1:  # 只考虑优先级较高的持仓
                    position_info = PositionToClose(
                        ticket=pos.get("ticket", 0),
                        symbol=symbol,
                        type=pos.get("type", ""),
                        volume=volume,
                        open_price=open_price,
                        current_price=current_price,
                        profit=profit,
                        profit_pct=profit_pct,
                        priority_score=priority_score
                    )
                    
                    positions_to_close.append(position_info)
            
            # 按优先级排序（从高到低）
            positions_to_close.sort(key=lambda x: x.priority_score, reverse=True)
            
            # 根据危机严重程度限制数量
            if severity == CrisisSeverity.LOW:
                positions_to_close = positions_to_close[:3]
            elif severity == CrisisSeverity.MEDIUM:
                positions_to_close = positions_to_close[:5]
            elif severity == CrisisSeverity.HIGH:
                positions_to_close = positions_to_close[:10]
            # CRITICAL 保留所有
            
            return positions_to_close
            
        except Exception as e:
            logger.error(f"[ERR] 分析待平仓持仓失败: {e}")
            return []
    
    def _determine_crisis_actions(self, severity: CrisisSeverity) -> Tuple[CrisisAction, List[CrisisAction]]:
        """确定危机处理动作"""
        strategies = self.crisis_response_strategies.get(severity, [CrisisAction.MONITOR_ONLY])
        
        if len(strategies) == 0:
            return CrisisAction.MONITOR_ONLY, []
        
        primary_action = strategies[0]
        secondary_actions = strategies[1:] if len(strategies) > 1 else []
        
        return primary_action, secondary_actions
    
    def _calculate_risk_adjustments(self, severity: CrisisSeverity, margin_level: float) -> Dict[str, Any]:
        """计算风险调整参数"""
        adjustments = {}
        
        if severity == CrisisSeverity.CRITICAL:
            adjustments = {
                "risk_per_trade": 0.001,      # 每笔交易风险0.1%
                "max_position_size": 0.005,   # 最大仓位0.5%
                "stop_loss_multiplier": 0.5,  # 止损缩小50%
                "take_profit_multiplier": 0.3, # 止盈缩小70%
                "volatility_multiplier": 0.3,  # 波动率影响减小70%
                "trading_enabled": False      # 禁止开新仓
            }
        elif severity == CrisisSeverity.HIGH:
            adjustments = {
                "risk_per_trade": 0.002,      # 0.2%
                "max_position_size": 0.01,    # 1%
                "stop_loss_multiplier": 0.7,  # 止损缩小30%
                "take_profit_multiplier": 0.5, # 止盈缩小50%
                "volatility_multiplier": 0.5,  # 波动率影响减小50%
                "trading_enabled": True       # 允许交易但限制严格
            }
        elif severity == CrisisSeverity.MEDIUM:
            adjustments = {
                "risk_per_trade": 0.005,      # 0.5%
                "max_position_size": 0.02,    # 2%
                "stop_loss_multiplier": 0.8,  # 止损缩小20%
                "take_profit_multiplier": 0.7, # 止盈缩小30%
                "volatility_multiplier": 0.7,  # 波动率影响减小30%
                "trading_enabled": True
            }
        else:  # LOW
            adjustments = {
                "risk_per_trade": 0.01,       # 1%
                "max_position_size": 0.05,    # 5%
                "stop_loss_multiplier": 1.0,  # 正常止损
                "take_profit_multiplier": 1.0, # 正常止盈
                "volatility_multiplier": 1.0,  # 正常波动率影响
                "trading_enabled": True
            }
        
        # 根据保证金水平进一步调整
        if margin_level < 50.0:
            for key in ["risk_per_trade", "max_position_size"]:
                if key in adjustments:
                    adjustments[key] *= 0.5
        
        return adjustments
    
    def _estimate_time_to_margin_call(self, crisis_status: Dict[str, Any]) -> float:
        """估算到保证金追缴的时间（小时）"""
        try:
            margin_level = crisis_status["margin_level"]
            margin_call_risk = crisis_status["margin_call_risk"]
            
            if margin_level >= 100.0:
                return float('inf')  # 无风险
            
            # 基于当前保证金水平和风险估算
            if margin_call_risk > 0.8:
                return 0.1  # 10分钟
            elif margin_call_risk > 0.6:
                return 0.5  # 30分钟
            elif margin_call_risk > 0.4:
                return 1.0  # 1小时
            elif margin_call_risk > 0.2:
                return 2.0  # 2小时
            else:
                return 4.0  # 4小时
                
        except Exception as e:
            logger.error(f"[ERR] 估算保证金追缴时间失败: {e}")
            return 1.0
    
    def _generate_recovery_plan(self, severity: CrisisSeverity, margin_level: float) -> List[str]:
        """生成恢复计划"""
        recovery_steps = []
        
        if severity == CrisisSeverity.CRITICAL:
            recovery_steps = [
                "1. 立即平掉所有亏损持仓",
                "2. 平掉50%的小额持仓",
                "3. 入金增加保证金（建议增加50%账户余额）",
                "4. 降低风险参数至最低水平",
                "5. 暂停所有新开仓交易24小时",
                "6. 监控保证金水平恢复至200%以上"
            ]
        elif severity == CrisisSeverity.HIGH:
            recovery_steps = [
                "1. 平掉亏损超过5%的持仓",
                "2. 平掉30%的小额持仓",
                "3. 入金增加保证金（建议增加30%账户余额）",
                "4. 将风险参数降低70%",
                "5. 暂停高风险品种交易",
                "6. 监控保证金水平恢复至150%以上"
            ]
        elif severity == CrisisSeverity.MEDIUM:
            recovery_steps = [
                "1. 平掉亏损超过10%的持仓",
                "2. 平掉20%的小额持仓",
                "3. 考虑入金增加保证金",
                "4. 将风险参数降低50%",
                "5. 避免开新仓直到情况改善",
                "6. 监控保证金水平恢复至120%以上"
            ]
        else:  # LOW
            recovery_steps = [
                "1. 监控持仓情况",
                "2. 准备减仓计划",
                "3. 调整风险参数降低30%",
                "4. 关注市场波动",
                "5. 定期检查保证金水平"
            ]
        
        # 添加时间估计
        estimated_recovery_time = {
            CrisisSeverity.CRITICAL: "48小时",
            CrisisSeverity.HIGH: "24小时",
            CrisisSeverity.MEDIUM: "12小时",
            CrisisSeverity.LOW: "6小时"
        }
        
        recovery_steps.append(f"预计恢复时间: {estimated_recovery_time.get(severity, '未知')}")
        
        return recovery_steps
    
    def _generate_user_notifications(self, severity: CrisisSeverity, 
                                    margin_level: float, crisis_score: float) -> List[str]:
        """生成用户通知"""
        notifications = []
        
        if severity == CrisisSeverity.CRITICAL:
            notifications.append(f"[紧急] 保证金危机！水平: {margin_level:.1f}%")
            notifications.append("[行动] 立即采取措施防止爆仓")
            notifications.append("[建议] 立即登录账户检查并处理")
            
        elif severity == CrisisSeverity.HIGH:
            notifications.append(f"[危险] 保证金水平危险: {margin_level:.1f}%")
            notifications.append("[行动] 建议立即减仓或入金")
            notifications.append(f"[风险] 危机分数: {crisis_score:.2f}")
            
        elif severity == CrisisSeverity.MEDIUM:
            notifications.append(f"[警告] 保证金水平警告: {margin_level:.1f}%")
            notifications.append("[行动] 建议减仓或调整风险参数")
            notifications.append("[监控] 系统已启动增强监控")
            
        else:  # LOW
            notifications.append(f"[注意] 保证金水平较低: {margin_level:.1f}%")
            notifications.append("[建议] 关注持仓风险")
        
        return notifications
    
    def execute_crisis_plan(self, plan: CrisisPlan):
        """执行危机处理计划"""
        try:
            logger.warning(f"[CRISIS] 执行危机处理计划: {plan.severity.value}")
            
            # 记录计划详情
            self._log_crisis_plan_details(plan)
            
            # 执行主要动作
            self._execute_crisis_action(plan.primary_action, plan)
            
            # 执行次要动作
            for action in plan.secondary_actions:
                self._execute_crisis_action(action, plan)
            
            # 应用风险调整
            self._apply_risk_adjustments(plan.risk_adjustments)
            
            # 发送用户通知
            self._send_user_notifications(plan.user_notifications)
            
            logger.info(f"[CRISIS] 危机处理计划执行完成")
            
        except Exception as e:
            logger.error(f"[ERR] 执行危机处理计划失败: {e}")
    
    def _log_crisis_plan_details(self, plan: CrisisPlan):
        """记录危机计划详情"""
        logger.warning(f"[CRISIS] 计划详情:")
        logger.warning(f"  严重程度: {plan.severity.value}")
        logger.warning(f"  保证金水平: {plan.margin_level:.1f}%")
        logger.warning(f"  危机分数: {plan.crisis_score:.2f}")
        logger.warning(f"  主要动作: {plan.primary_action.value}")
        logger.warning(f"  预计到追缴时间: {plan.estimated_time_to_margin_call:.1f}小时")
        
        if plan.positions_to_close:
            logger.warning(f"  待平仓持仓 ({len(plan.positions_to_close)}个):")
            for i, pos in enumerate(plan.positions_to_close[:3]):  # 只显示前3个
                logger.warning(f"    {i+1}. {pos.symbol} {pos.type} {pos.volume:.2f}手 "
                              f"盈亏: ${pos.profit:.2f} ({pos.priority_score:.2f}分)")
    
    def _execute_crisis_action(self, action: CrisisAction, plan: CrisisPlan):
        """执行单个危机动作"""
        try:
            if action == CrisisAction.MONITOR_ONLY:
                logger.info("[CRISIS] 动作: 增强监控模式")
                # 监控逻辑已在主循环中
                
            elif action == CrisisAction.REDUCE_RISK_PARAMS:
                logger.warning("[CRISIS] 动作: 降低风险参数")
                # 风险调整已在 apply_risk_adjustments 中处理
                
            elif action == CrisisAction.CLOSE_SMALL_POSITIONS:
                logger.warning("[CRISIS] 动作: 平小额持仓")
                self._close_small_positions(plan.positions_to_close)
                
            elif action == CrisisAction.CLOSE_LOSING_POSITIONS:
                logger.warning("[CRISIS] 动作: 平亏损持仓")
                self._close_losing_positions(plan.positions_to_close)
                
            elif action == CrisisAction.CLOSE_ALL_POSITIONS:
                logger.warning("[CRISIS] 动作: 平所有持仓")
                self._close_all_positions(plan.positions_to_close)
                
            elif action == CrisisAction.STOP_ALL_TRADING:
                logger.warning("[CRISIS] 动作: 停止所有交易")
                # 需要与交易执行器集成
                self._stop_all_trading()
                
            elif action == CrisisAction.NOTIFY_USER:
                logger.info("[CRISIS] 动作: 通知用户")
                # 通知逻辑已在 _send_user_notifications 中处理
                
        except Exception as e:
            logger.error(f"[ERR] 执行危机动作失败 ({action.value}): {e}")
    
    def _close_small_positions(self, positions_to_close: List[PositionToClose]):
        """平小额持仓（小于0.1手）"""
        small_positions = [p for p in positions_to_close if p.volume < 0.1]
        
        if not small_positions:
            logger.info("[CRISIS] No small positions to close")
            return
        
        logger.warning(f"[CRISIS] Closing small positions: {len(small_positions)} position(s)")
        
        fh = file_handler
        for pos in small_positions:
            try:
                close_order = {
                    "action": "close_position",
                    "ticket": pos.ticket,
                    "symbol": pos.symbol,
                    "volume": pos.volume,
                    "type": "SELL" if pos.type.upper() == "BUY" else "BUY",
                    "reason": f"margin_crisis_small_close",
                    "priority_score": pos.priority_score
                }
                # 通过文件通信发送平仓指令到MQL5 EA
                fh.write_json_to_file("close_order.json", close_order)
                logger.warning(
                    f"[CRISIS] Sent close order: ticket={pos.ticket} "
                    f"{pos.symbol} {pos.volume}lot profit=${pos.profit:.2f}"
                )
            except Exception as e:
                logger.error(f"[ERR] Failed to close position {pos.ticket}: {e}")
    
    def _close_losing_positions(self, positions_to_close: List[PositionToClose]):
        """平亏损持仓"""
        losing_positions = sorted(
            [p for p in positions_to_close if p.profit < 0],
            key=lambda p: p.profit  # 亏损最多的优先
        )
        
        if not losing_positions:
            logger.info("[CRISIS] No losing positions to close")
            return
        
        logger.warning(f"[CRISIS] Closing losing positions: {len(losing_positions)} position(s)")
        
        fh = file_handler
        for pos in losing_positions:
            try:
                close_order = {
                    "action": "close_position",
                    "ticket": pos.ticket,
                    "symbol": pos.symbol,
                    "volume": pos.volume,
                    "type": "SELL" if pos.type.upper() == "BUY" else "BUY",
                    "reason": "margin_crisis_losing_close",
                    "priority_score": pos.priority_score,
                    "profit": pos.profit
                }
                fh.write_json_to_file("close_order.json", close_order)
                logger.warning(
                    f"[CRISIS] Sent close order: ticket={pos.ticket} "
                    f"{pos.symbol} {pos.volume}lot loss=${pos.profit:.2f}"
                )
            except Exception as e:
                logger.error(f"[ERR] Failed to close position {pos.ticket}: {e}")
    
    def _close_all_positions(self, positions_to_close: List[PositionToClose]):
        """平所有持仓"""
        if not positions_to_close:
            logger.warning("[CRISIS] No positions to close (already flat)")
            return
        
        logger.warning(f"[CRISIS] CLOSING ALL POSITIONS: {len(positions_to_close)} position(s)")
        
        fh = file_handler
        for pos in positions_to_close:
            try:
                close_order = {
                    "action": "close_position",
                    "ticket": pos.ticket,
                    "symbol": pos.symbol,
                    "volume": pos.volume,
                    "type": "SELL" if pos.type.upper() == "BUY" else "BUY",
                    "reason": "margin_crisis_close_all",
                    "priority_score": pos.priority_score
                }
                fh.write_json_to_file("close_order.json", close_order)
                logger.warning(
                    f"[CRISIS] Sent CLOSE ALL order: ticket={pos.ticket} "
                    f"{pos.symbol} {pos.volume}lot"
                )
            except Exception as e:
                logger.error(f"[ERR] Failed to close all position {pos.ticket}: {e}")
    
    def _stop_all_trading(self):
        """停止所有交易活动"""
        logger.warning("[CRISIS] STOPPING ALL TRADING ACTIVITY")
        
        # 1. 设置全局停止标志
        self.in_crisis_mode = True
        
        # 2. 通知风险管理器进入紧急模式
        try:
            from core.risk_manager import get_risk_manager
            rm = get_risk_manager()
            rm.is_crisis_mode = True
            logger.warning("[CRISIS] Risk manager set to CRISIS MODE")
        except Exception as e:
            logger.error(f"[ERR] Failed to notify risk manager: {e}")
        
        # 3. 通过文件通信通知MQL5 EA停止交易
        try:
            fh = file_handler
            fh.write_json_to_file("crisis_stop.json", {
                "action": "stop_all_trading",
                "timestamp": datetime.now().isoformat(),
                "reason": "margin_crisis_critical"
            })
            logger.warning("[CRISIS] Stop-trading signal sent to MQL5 EA")
        except Exception as e:
            logger.error(f"[ERR] Failed to send stop signal: {e}")
    
    def _apply_risk_adjustments(self, adjustments: Dict[str, Any]):
        """应用风险调整到风险管理器"""
        logger.warning(f"[CRISIS] Applying risk adjustments: trading={adjustments.get('trading_enabled', 'N/A')}")
        
        try:
            from core.risk_manager import get_risk_manager
            rm = get_risk_manager()
            
            # 推送风险参数调整
            if adjustments.get("trading_enabled") is False:
                rm.is_crisis_mode = True
                logger.warning("[CRISIS] Trading DISABLED via risk adjustments")
            
            # 更新风险参数
            rm.crisis_risk_params = {
                "risk_per_trade": adjustments.get("risk_per_trade", 0.01),
                "max_position_size": adjustments.get("max_position_size", 0.05),
                "stop_loss_multiplier": adjustments.get("stop_loss_multiplier", 1.0),
                "take_profit_multiplier": adjustments.get("take_profit_multiplier", 1.0),
                "volatility_multiplier": adjustments.get("volatility_multiplier", 1.0),
                "trading_enabled": adjustments.get("trading_enabled", True),
                "applied_at": datetime.now().isoformat()
            }
            logger.warning(f"[CRISIS] Risk parameters adjusted: {rm.crisis_risk_params}")
            
        except Exception as e:
            logger.error(f"[ERR] Failed to apply risk adjustments: {e}")
    
    def _send_user_notifications(self, notifications: List[str]):
        """发送用户通知（日志 + 文件记录）"""
        for notification in notifications:
            logger.warning(f"[USER NOTIFICATION] {notification}")
        
        # 持久化通知记录
        try:
            fh = file_handler
            existing = []
            try:
                existing = fh.read_json_from_file("crisis_notifications.json") or []
            except Exception:
                pass
            
            existing.append({
                "timestamp": datetime.now().isoformat(),
                "notifications": notifications
            })
            # 保留最近50条
            if len(existing) > 50:
                existing = existing[-50:]
            
            fh.write_json_to_file("crisis_notifications.json", existing)
        except Exception as e:
            logger.error(f"[ERR] Failed to persist notifications: {e}")
    
    def get_crisis_report(self) -> Dict[str, Any]:
        """获取危机报告"""
        try:
            latest_plan = None
            if self.crisis_plans:
                latest_plan = self.crisis_plans[-1]
            
            return {
                "current_status": {
                    "in_crisis_mode": self.in_crisis_mode,
                    "last_check": self.last_crisis_check.isoformat()
                },
                "latest_plan": {
                    "severity": latest_plan.severity.value if latest_plan else "none",
                    "margin_level": latest_plan.margin_level if latest_plan else 0.0,
                    "crisis_score": latest_plan.crisis_score if latest_plan else 0.0,
                    "primary_action": latest_plan.primary_action.value if latest_plan else "none",
                    "estimated_time_to_margin_call": latest_plan.estimated_time_to_margin_call if latest_plan else 0.0
                },
                "history_count": len(self.crisis_plans),
                "thresholds": {k.value: v for k, v in self.crisis_thresholds.items()},
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"[ERR] 获取危机报告失败: {e}")
            
            return {
                "current_status": {
                    "in_crisis_mode": False,
                    "last_check": datetime.now().isoformat()
                },
                "latest_plan": None,
                "history_count": 0,
                "thresholds": {k.value: v for k, v in self.crisis_thresholds.items()},
                "timestamp": datetime.now().isoformat()
            }


# 全局危机处理器实例
_global_crisis_handler: Optional[MarginCrisisHandler] = None


def get_crisis_handler() -> MarginCrisisHandler:
    """获取全局危机处理器实例"""
    global _global_crisis_handler
    if not _global_crisis_handler:
        _global_crisis_handler = MarginCrisisHandler()
    return _global_crisis_handler


if __name__ == "__main__":
    print("="*70)
    print("[测试] 保证金危机处理系统")
    print("="*70)
    
    # 测试危机处理器
    crisis_handler = MarginCrisisHandler()
    
    # 创建模拟危机数据
    test_data = {
        "account_summary": {
            "balance": 15000.0,
            "equity": 12000.0,  # 亏损状态
            "margin_used": 11000.0,
            "margin_free": 1000.0,
            "margin_level": 109.1,  # 接近追缴线
            "floating_profit": -3000.0  # 大额亏损
        },
        "positions_summary": {
            "total_count": 5,
            "total_volume": 2.5,
            "total_profit": -2500.0,
            "by_symbol": {
                "EURUSD": {"total_volume": 1.0, "total_profit": -500.0, "position_count": 2},
                "GOLD": {"total_volume": 1.5, "total_profit": -2000.0, "position_count": 3}
            }
        }
    }
    
    # 测试危机状态检查
    print("\n[测试] 检查危机状态...")
    crisis_status = crisis_handler.check_crisis_status(test_data)
    
    print(f"严重程度: {crisis_status['severity'].value}")
    print(f"保证金水平: {crisis_status['margin_level']:.1f}%")
    print(f"危机分数: {crisis_status['crisis_score']:.2f}")
    print(f"追缴风险: {crisis_status['margin_call_risk']:.2f}")
    
    # 测试危机计划生成
    print("\n[测试] 生成危机处理计划...")
    crisis_plan = crisis_handler.generate_crisis_plan(crisis_status)
    
    print(f"主要动作: {crisis_plan.primary_action.value}")
    print(f"次要动作: {[a.value for a in crisis_plan.secondary_actions]}")
    print(f"风险调整: {crisis_plan.risk_adjustments}")
    print(f"预计到追缴时间: {crisis_plan.estimated_time_to_margin_call:.1f}小时")
    
    print("恢复计划:")
    for step in crisis_plan.recovery_plan:
        print(f"  - {step}")
    
    print("\n用户通知:")
    for notification in crisis_plan.user_notifications:
        print(f"  - {notification}")
    
    print("\n[OK] 保证金危机处理系统测试完成！")