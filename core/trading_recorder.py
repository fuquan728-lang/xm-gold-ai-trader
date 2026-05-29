#!/usr/bin/env python3
"""
V3.0 - 交易记录管理器
整合AI分析记录、交易记录、PPO强化学习数据准备
"""

import time
from typing import Dict, Any, Optional
from datetime import datetime

from core.datastore import get_datastore, DataStore
from core.logger import logger


class TradingRecorder:
    """交易记录管理器"""
    
    def __init__(self, db_path: str = "data/trading.db"):
        self.datastore = get_datastore(db_path)
        self.current_analysis_id: Optional[int] = None
        self.current_trade_id: Optional[int] = None
        self._last_analysis_time: float = 0
        
        # 简单的内存存储（临时测试模式，避免复杂的SQLite问题
        self._memory_only = db_path == ":memory:"
        self._simple_storage = {
            'ai_analysis': [],
            'trades': [],
            'market_states': [],
            'ppo_experiences': []
        }
        
        logger.info("[OK] 交易记录管理器初始化完成")
    
    def record_analysis(
        self,
        symbol: str,
        bid: float,
        ask: float,
        action: str,
        confidence: float,
        reason: str = "",
        use_deepseek: bool = False,
        cached: bool = False,
        indicators: Optional[Dict] = None,
        history: Optional[list] = None,
        response_time: Optional[float] = None
    ) -> int:
        """记录AI分析"""
        self.current_analysis_id = self.datastore.record_ai_analysis(
            symbol=symbol,
            bid=bid,
            ask=ask,
            action=action,
            confidence=confidence,
            reason=reason,
            use_deepseek=use_deepseek,
            cached=cached,
            indicators=indicators,
            history=history,
            response_time=response_time
        )
        self._last_analysis_time = time.time()
        
        return self.current_analysis_id
    
    def on_trade_signal(
        self,
        signal: Dict[str, Any],
        bid: float,
        ask: float,
        indicators: Optional[Dict] = None
    ) -> Optional[int]:
        """
        当接收到交易信号时记录
        
        Args:
            signal: AI信号字典 {'action': 'BUY', 'confidence': 0.75, ...}
            bid: 当前买入价
            ask: 当前卖出价
            indicators: 技术指标
        
        Returns:
            trade_id: 如果开仓则返回交易ID
        """
        action = signal.get('action', 'HOLD')
        symbol = signal.get('symbol', 'UNKNOWN')
        confidence = signal.get('confidence', 0.5)
        reason = signal.get('reason', '')
        
        # 1. 记录AI分析
        analysis_id = self.record_analysis(
            symbol=symbol,
            bid=bid,
            ask=ask,
            action=action,
            confidence=confidence,
            reason=reason,
            use_deepseek=signal.get('use_deepseek', False),
            cached=signal.get('cached', False),
            indicators=indicators
        )
        
        # 2. 如果是买卖信号，记录交易
        if action in ['BUY', 'SELL']:
            entry_price = ask if action == 'BUY' else bid
            self.current_trade_id = self.datastore.record_trade(
                symbol=symbol,
                action=action,
                entry_price=entry_price,
                ai_analysis_id=analysis_id
            )
            return self.current_trade_id
        
        return None
    
    def close_trade(
        self,
        trade_id: Optional[int] = None,
        exit_price: Optional[float] = None,
        pnl: Optional[float] = None,
        pnl_percent: Optional[float] = None
    ):
        """平仓并更新记录"""
        tid = trade_id or self.current_trade_id
        if tid:
            self.datastore.close_trade(
                trade_id=tid,
                exit_price=exit_price,
                pnl=pnl,
                pnl_percent=pnl_percent
            )
            if tid == self.current_trade_id:
                self.current_trade_id = None
    
    def record_market_state(
        self,
        symbol: str,
        bid: float,
        ask: float,
        indicators: Optional[Dict] = None,
        position_open: bool = False,
        position_action: Optional[str] = None,
        position_entry_price: Optional[float] = None,
        account_balance: Optional[float] = None,
        equity: Optional[float] = None
    ) -> int:
        """
        记录市场状态 - 为PPO强化学习准备
        
        这个应该定期调用（比如每根K线）
        """
        return self.datastore.record_market_state(
            symbol=symbol,
            bid=bid,
            ask=ask,
            indicators=indicators,
            position_open=position_open,
            position_action=position_action,
            position_entry_price=position_entry_price,
            account_balance=account_balance,
            equity=equity
        )
    
    def record_ppo_experience(
        self,
        symbol: str,
        state: Dict[str, Any],
        action: str,
        reward: float,
        next_state: Optional[Dict[str, Any]] = None,
        done: bool = False,
        **kwargs
    ) -> int:
        """
        记录PPO强化学习经验
        
        Args:
            symbol: 交易品种
            state: 当前状态
            action: 执行的动作
            reward: 获得的奖励
            next_state: 下一个状态
            done: 是否结束
        """
        return self.datastore.record_ppo_experience(
            symbol=symbol,
            state=state,
            action=action,
            reward=reward,
            next_state=next_state,
            done=done,
            **kwargs
        )
    
    def calculate_reward(
        self,
        pnl: float,
        pnl_percent: float,
        risk_penalty: float = 0.0
    ) -> float:
        """
        计算PPO强化学习奖励
        
        简单的奖励函数：基于盈亏，风险惩罚
        """
        reward = pnl_percent * 100  # 百分比放大
        reward -= risk_penalty
        return reward
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        return self.datastore.get_statistics()
    
    def get_recent_analyses(self, limit: int = 10) -> list:
        """获取最近的AI分析"""
        return self.datastore.get_ai_analyses(limit=limit)
    
    def get_recent_trades(self, limit: int = 10) -> list:
        """获取最近的交易"""
        return self.datastore.get_trades(limit=limit)


# 全局交易记录器实例
_global_recorder: Optional[TradingRecorder] = None


def get_trading_recorder(db_path: str = "data/trading.db") -> TradingRecorder:
    """获取全局交易记录器"""
    global _global_recorder
    if not _global_recorder:
        _global_recorder = TradingRecorder(db_path)
    return _global_recorder


if __name__ == "__main__":
    print("="*70)
    print("[TOOL] 测试交易记录管理器")
    print("="*70)
    
    recorder = get_trading_recorder(":memory:")
    
    # 测试记录分析
    print("\n[LOG] 测试记录AI分析...")
    analysis_id = recorder.record_analysis(
        symbol="EURUSD",
        bid=1.0850,
        ask=1.0852,
        action="BUY",
        confidence=0.75,
        reason="RSI超卖",
        use_deepseek=True
    )
    print(f"[OK] 分析记录ID: {analysis_id}")
    
    # 测试交易信号处理
    print("\n[LOG] 测试交易信号处理...")
    signal = {
        'symbol': 'EURUSD',
        'action': 'BUY',
        'confidence': 0.75,
        'reason': 'RSI超卖+MACD金叉',
        'use_deepseek': True
    }
    trade_id = recorder.on_trade_signal(signal, bid=1.0850, ask=1.0852)
    print(f"[OK] 交易记录ID: {trade_id}")
    
    # 测试平仓
    print("\n[LOG] 测试平仓...")
    recorder.close_trade(exit_price=1.0875, pnl=25.0, pnl_percent=0.23)
    
    # 测试市场状态记录
    print("\n[AI] 测试市场状态记录...")
    state_id = recorder.record_market_state(
        symbol="EURUSD",
        bid=1.0850,
        ask=1.0852,
        indicators={'RSI': 35, 'MACD': 0.001}
    )
    print(f"[OK] 市场状态记录ID: {state_id}")
    
    # 测试PPO经验记录
    print("\n[AI] 测试PPO经验记录...")
    state = {'price': 1.0850, 'rsi': 35, 'position': 0}
    reward = recorder.calculate_reward(25.0, 0.23)
    exp_id = recorder.record_ppo_experience(
        symbol="EURUSD",
        state=state,
        action="BUY",
        reward=reward
    )
    print(f"[OK] PPO经验记录ID: {exp_id}")
    
    # 获取统计
    print("\n[DATA] 统计信息:")
    stats = recorder.get_statistics()
    import json
    print(json.dumps(stats, indent=2, ensure_ascii=False))
    
    print("\n[OK] 交易记录管理器测试完成！")