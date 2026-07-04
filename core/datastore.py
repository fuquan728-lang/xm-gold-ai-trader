#!/usr/bin/env python3
"""
V3.0 - 数据存储与交易记录系统
为PPO强化学习准备完整数据结构
"""

import sqlite3
import json
import time
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path
from enum import Enum

from core.logger import logger


class ActionType(Enum):
    """交易动作类型"""
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class TradeStatus(Enum):
    """交易状态"""
    OPEN = "open"
    CLOSED = "closed"
    CANCELLED = "cancelled"


class DataStore:
    """数据存储管理器 - SQLite数据库"""
    
    def __init__(self, db_path: str = "data/trading.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(exist_ok=True)
        self._init_database()
    
    def _get_connection(self):
        """获取数据库连接"""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn
    
    def _init_database(self):
        """初始化数据库表"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            try:
                # AI分析记录表
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS ai_analysis (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp REAL NOT NULL,
                        symbol TEXT NOT NULL,
                        bid REAL NOT NULL,
                        ask REAL NOT NULL,
                        action TEXT NOT NULL,
                        confidence REAL NOT NULL,
                        reason TEXT,
                        use_deepseek INTEGER DEFAULT 0,
                        cached INTEGER DEFAULT 0,
                        indicators TEXT,
                        history TEXT,
                        response_time REAL
                    )
                ''')
                
                # 交易记录表
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS trades (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp REAL NOT NULL,
                        symbol TEXT NOT NULL,
                        action TEXT NOT NULL,
                        entry_price REAL NOT NULL,
                        exit_price REAL,
                        position_size REAL DEFAULT 0,
                        stop_loss REAL,
                        take_profit REAL,
                        status TEXT DEFAULT 'open',
                        pnl REAL,
                        pnl_percent REAL,
                        hold_time REAL,
                        ai_analysis_id INTEGER
                    )
                ''')
                
                # 市场状态表 - 为PPO强化学习准备
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS market_states (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp REAL NOT NULL,
                        symbol TEXT NOT NULL,
                        bid REAL NOT NULL,
                        ask REAL NOT NULL,
                        indicators TEXT,
                        position_open INTEGER DEFAULT 0,
                        position_action TEXT,
                        position_entry_price REAL,
                        account_balance REAL,
                        equity REAL
                    )
                ''')
                
                # PPO强化学习经验回放表
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS ppo_experiences (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp REAL NOT NULL,
                        symbol TEXT NOT NULL,
                        state TEXT NOT NULL,
                        action TEXT NOT NULL,
                        action_prob REAL,
                        reward REAL,
                        next_state TEXT,
                        done INTEGER DEFAULT 0,
                        value REAL,
                        advantage REAL
                    )
                ''')
                
                # 市场行情数据表
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS market_prices (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp REAL NOT NULL,
                        symbol TEXT NOT NULL,
                        timeframe TEXT NOT NULL,
                        open REAL NOT NULL,
                        high REAL NOT NULL,
                        low REAL NOT NULL,
                        close REAL NOT NULL,
                        volume REAL,
                        tick_volume REAL,
                        spread INTEGER,
                        real_volume REAL,
                        UNIQUE(symbol, timeframe, timestamp)
                    )
                ''')
                
                # 技术指标表
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS technical_indicators (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp REAL NOT NULL,
                        symbol TEXT NOT NULL,
                        timeframe TEXT NOT NULL,
                        ma5 REAL,
                        ma10 REAL,
                        ma20 REAL,
                        ma50 REAL,
                        ma100 REAL,
                        ma200 REAL,
                        rsi REAL,
                        macd REAL,
                        macd_signal REAL,
                        macd_hist REAL,
                        bollinger_upper REAL,
                        bollinger_middle REAL,
                        bollinger_lower REAL,
                        atr REAL,
                        stoch_k REAL,
                        stoch_d REAL,
                        cci REAL,
                        adx REAL,
                        obv REAL,
                        volume_ratio REAL,
                        UNIQUE(symbol, timeframe, timestamp)
                    )
                ''')
                
                # 宏观经济指标表
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS economic_indicators (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp REAL NOT NULL,
                        country TEXT NOT NULL,
                        indicator_name TEXT NOT NULL,
                        indicator_code TEXT NOT NULL,
                        value REAL NOT NULL,
                        unit TEXT,
                        period TEXT,
                        previous_value REAL,
                        forecast_value REAL,
                        source TEXT,
                        UNIQUE(country, indicator_code, timestamp)
                    )
                ''')
                
                # 市场情绪数据表
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS market_sentiment (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp REAL NOT NULL,
                        symbol TEXT NOT NULL,
                        sentiment_score REAL,
                        bullish_percent REAL,
                        bearish_percent REAL,
                        neutral_percent REAL,
                        news_sentiment REAL,
                        social_sentiment REAL,
                        fear_greed_index REAL,
                        volatility_index REAL,
                        put_call_ratio REAL,
                        source TEXT,
                        UNIQUE(symbol, timestamp)
                    )
                ''')
                
                conn.commit()
                logger.info(f"[OK] 数据库初始化完成: {self.db_path}")
            except Exception as e:
                logger.error(f"[ERR] 数据库初始化失败: {e}")
                raise
    
    def record_ai_analysis(
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
        history: Optional[List] = None,
        response_time: Optional[float] = None
    ) -> int:
        """记录一次AI分析"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO ai_analysis 
                (timestamp, symbol, bid, ask, action, confidence, reason, 
                 use_deepseek, cached, indicators, history, response_time)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                time.time(),
                symbol,
                bid,
                ask,
                action,
                confidence,
                reason,
                1 if use_deepseek else 0,
                1 if cached else 0,
                json.dumps(indicators) if indicators else None,
                json.dumps(history) if history else None,
                response_time
            ))
            
            conn.commit()
            analysis_id = cursor.lastrowid
            logger.debug(f"[LOG] AI分析已记录 [ID: {analysis_id}]: {action} ({confidence:.2f})")
            return analysis_id
    
    def record_trade(
        self,
        symbol: str,
        action: str,
        entry_price: float,
        position_size: float = 0,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        ai_analysis_id: Optional[int] = None
    ) -> int:
        """记录新开交易"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO trades 
                (timestamp, symbol, action, entry_price, position_size, 
                 stop_loss, take_profit, status, ai_analysis_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                time.time(),
                symbol,
                action,
                entry_price,
                position_size,
                stop_loss,
                take_profit,
                TradeStatus.OPEN.value,
                ai_analysis_id
            ))
            
            conn.commit()
            trade_id = cursor.lastrowid
            logger.info(f"[LOG] 交易已记录 [ID: {trade_id}]: {action} @ {entry_price}")
            return trade_id
    
    def close_trade(
        self,
        trade_id: int,
        exit_price: float,
        pnl: Optional[float] = None,
        pnl_percent: Optional[float] = None
    ):
        """平仓并更新交易记录"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # 查询开仓时间戳，计算实际持仓时长
            cursor.execute('SELECT timestamp FROM trades WHERE id = ?', (trade_id,))
            row = cursor.fetchone()
            close_time = time.time()
            if row and row[0]:
                hold_time_seconds = close_time - row[0]
            else:
                hold_time_seconds = 0.0
                logger.warning(f"[WARN] 未找到交易 {trade_id} 的开仓时间戳，hold_time 设为 0")
            
            cursor.execute('''
                UPDATE trades 
                SET exit_price = ?, pnl = ?, pnl_percent = ?, 
                    status = ?, hold_time = ?
                WHERE id = ?
            ''', (
                exit_price,
                pnl,
                pnl_percent,
                TradeStatus.CLOSED.value,
                hold_time_seconds,
                trade_id
            ))
            
            conn.commit()
            logger.info(f"[OK] 交易已平仓 [ID: {trade_id}]: PnL={pnl}, 持仓{hold_time_seconds/60:.1f}分钟")
    
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
        """记录市场状态 - 为PPO强化学习准备"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO market_states 
                (timestamp, symbol, bid, ask, indicators, 
                 position_open, position_action, position_entry_price,
                 account_balance, equity)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                time.time(),
                symbol,
                bid,
                ask,
                json.dumps(indicators) if indicators else None,
                1 if position_open else 0,
                position_action,
                position_entry_price,
                account_balance,
                equity
            ))
            
            conn.commit()
            state_id = cursor.lastrowid
            return state_id
    
    def record_ppo_experience(
        self,
        symbol: str,
        state: Dict[str, Any],
        action: str,
        reward: float,
        next_state: Optional[Dict[str, Any]] = None,
        done: bool = False,
        action_prob: Optional[float] = None,
        value: Optional[float] = None,
        advantage: Optional[float] = None
    ) -> int:
        """记录PPO强化学习经验"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO ppo_experiences 
                (timestamp, symbol, state, action, action_prob, reward,
                 next_state, done, value, advantage)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                time.time(),
                symbol,
                json.dumps(state),
                action,
                action_prob,
                reward,
                json.dumps(next_state) if next_state else None,
                1 if done else 0,
                value,
                advantage
            ))
            
            conn.commit()
            exp_id = cursor.lastrowid
            logger.debug(f"[AI] PPO经验已记录 [ID: {exp_id}]: reward={reward:.4f}")
            return exp_id
    
    def get_ai_analyses(
        self,
        symbol: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict]:
        """获取AI分析历史"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            query = "SELECT * FROM ai_analysis"
            params = []
            
            if symbol:
                query += " WHERE symbol = ?"
                params.append(symbol)
            
            query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            return [dict(row) for row in rows]
    
    def get_trades(
        self,
        symbol: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict]:
        """获取交易历史"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            query = "SELECT * FROM trades"
            params = []
            conditions = []
            
            if symbol:
                conditions.append("symbol = ?")
                params.append(symbol)
            if status:
                conditions.append("status = ?")
                params.append(status)
            
            if conditions:
                query += " WHERE " + " AND ".join(conditions)
            
            query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            return [dict(row) for row in rows]
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            stats = {}
            
            cursor.execute("SELECT COUNT(*) as cnt FROM ai_analysis")
            stats['total_analyses'] = cursor.fetchone()['cnt']
            
            cursor.execute("SELECT COUNT(*) as cnt FROM trades")
            stats['total_trades'] = cursor.fetchone()['cnt']
            
            cursor.execute("SELECT COUNT(*) as cnt FROM trades WHERE status = 'closed'")
            stats['closed_trades'] = cursor.fetchone()['cnt']
            
            cursor.execute("SELECT AVG(pnl) as avg_pnl FROM trades WHERE status = 'closed' AND pnl IS NOT NULL")
            stats['avg_pnl'] = cursor.fetchone()['avg_pnl']
            
            cursor.execute("SELECT SUM(pnl) as total_pnl FROM trades WHERE status = 'closed' AND pnl IS NOT NULL")
            stats['total_pnl'] = cursor.fetchone()['total_pnl']
            
            cursor.execute("SELECT COUNT(*) as cnt FROM ppo_experiences")
            stats['ppo_experiences'] = cursor.fetchone()['cnt']
            
            return stats
    
    def record_market_price(
        self,
        symbol: str,
        timeframe: str,
        open_price: float,
        high: float,
        low: float,
        close: float,
        volume: Optional[float] = None,
        tick_volume: Optional[float] = None,
        spread: Optional[int] = None,
        real_volume: Optional[float] = None
    ) -> int:
        """记录市场行情数据"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT OR REPLACE INTO market_prices
                (timestamp, symbol, timeframe, open, high, low, close,
                 volume, tick_volume, spread, real_volume)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                time.time(),
                symbol,
                timeframe,
                open_price,
                high,
                low,
                close,
                volume,
                tick_volume,
                spread,
                real_volume
            ))
            
            conn.commit()
            price_id = cursor.lastrowid
            logger.debug(f"[DATA] 市场行情记录 [ID: {price_id}]: {symbol} {timeframe} {close}")
            return price_id
    
    def record_technical_indicators(
        self,
        symbol: str,
        timeframe: str,
        ma5: Optional[float] = None,
        ma10: Optional[float] = None,
        ma20: Optional[float] = None,
        ma50: Optional[float] = None,
        ma100: Optional[float] = None,
        ma200: Optional[float] = None,
        rsi: Optional[float] = None,
        macd: Optional[float] = None,
        macd_signal: Optional[float] = None,
        macd_hist: Optional[float] = None,
        bollinger_upper: Optional[float] = None,
        bollinger_middle: Optional[float] = None,
        bollinger_lower: Optional[float] = None,
        atr: Optional[float] = None,
        stoch_k: Optional[float] = None,
        stoch_d: Optional[float] = None,
        cci: Optional[float] = None,
        adx: Optional[float] = None,
        obv: Optional[float] = None,
        volume_ratio: Optional[float] = None
    ) -> int:
        """记录技术指标"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT OR REPLACE INTO technical_indicators
                (timestamp, symbol, timeframe, ma5, ma10, ma20, ma50, ma100, ma200,
                 rsi, macd, macd_signal, macd_hist, bollinger_upper, bollinger_middle,
                 bollinger_lower, atr, stoch_k, stoch_d, cci, adx, obv, volume_ratio)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                time.time(),
                symbol,
                timeframe,
                ma5,
                ma10,
                ma20,
                ma50,
                ma100,
                ma200,
                rsi,
                macd,
                macd_signal,
                macd_hist,
                bollinger_upper,
                bollinger_middle,
                bollinger_lower,
                atr,
                stoch_k,
                stoch_d,
                cci,
                adx,
                obv,
                volume_ratio
            ))
            
            conn.commit()
            indicator_id = cursor.lastrowid
            logger.debug(f"[UP] 技术指标记录 [ID: {indicator_id}]: {symbol} {timeframe}")
            return indicator_id
    
    def record_economic_indicator(
        self,
        country: str,
        indicator_name: str,
        indicator_code: str,
        value: float,
        unit: str,
        period: str,
        previous_value: Optional[float] = None,
        forecast_value: Optional[float] = None,
        source: str = "unknown"
    ) -> int:
        """记录宏观经济指标"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT OR REPLACE INTO economic_indicators
                (timestamp, country, indicator_name, indicator_code, value,
                 unit, period, previous_value, forecast_value, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                time.time(),
                country,
                indicator_name,
                indicator_code,
                value,
                unit,
                period,
                previous_value,
                forecast_value,
                source
            ))
            
            conn.commit()
            econ_id = cursor.lastrowid
            logger.debug(f"🌍 经济指标记录 [ID: {econ_id}]: {country} {indicator_code}")
            return econ_id
    
    def record_market_sentiment(
        self,
        symbol: str,
        sentiment_score: Optional[float] = None,
        bullish_percent: Optional[float] = None,
        bearish_percent: Optional[float] = None,
        neutral_percent: Optional[float] = None,
        news_sentiment: Optional[float] = None,
        social_sentiment: Optional[float] = None,
        fear_greed_index: Optional[float] = None,
        volatility_index: Optional[float] = None,
        put_call_ratio: Optional[float] = None,
        source: str = "unknown"
    ) -> int:
        """记录市场情绪数据"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT OR REPLACE INTO market_sentiment
                (timestamp, symbol, sentiment_score, bullish_percent, bearish_percent,
                 neutral_percent, news_sentiment, social_sentiment, fear_greed_index,
                 volatility_index, put_call_ratio, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                time.time(),
                symbol,
                sentiment_score,
                bullish_percent,
                bearish_percent,
                neutral_percent,
                news_sentiment,
                social_sentiment,
                fear_greed_index,
                volatility_index,
                put_call_ratio,
                source
            ))
            
            conn.commit()
            sentiment_id = cursor.lastrowid
            logger.debug(f"😊 市场情绪记录 [ID: {sentiment_id}]: {symbol}")
            return sentiment_id


# 全局数据存储实例
_global_datastore: Optional[DataStore] = None


def get_datastore(db_path: str = "data/trading.db") -> DataStore:
    """获取全局数据存储实例"""
    global _global_datastore
    if not _global_datastore:
        _global_datastore = DataStore(db_path)
    return _global_datastore


if __name__ == "__main__":
    # 测试数据存储
    print("="*70)
    print("[TOOL] 测试数据存储系统")
    print("="*70)
    
    store = get_datastore(":memory:")  # 使用内存数据库测试
    
    # 测试AI分析记录
    print("\n[LOG] 测试AI分析记录...")
    analysis_id = store.record_ai_analysis(
        symbol="EURUSD",
        bid=1.0850,
        ask=1.0852,
        action="BUY",
        confidence=0.75,
        reason="RSI超卖+MACD金叉",
        use_deepseek=True
    )
    print(f"[OK] AI分析记录ID: {analysis_id}")
    
    # 测试交易记录
    print("\n[LOG] 测试交易记录...")
    trade_id = store.record_trade(
        symbol="EURUSD",
        action="BUY",
        entry_price=1.0851,
        position_size=0.1,
        stop_loss=1.0800,
        take_profit=1.0900,
        ai_analysis_id=analysis_id
    )
    print(f"[OK] 交易记录ID: {trade_id}")
    
    # 测试平仓
    print("\n[LOG] 测试平仓...")
    store.close_trade(
        trade_id=trade_id,
        exit_price=1.0875,
        pnl=24.0,
        pnl_percent=0.22
    )
    
    # 测试市场状态记录（PPO准备）
    print("\n[AI] 测试市场状态记录...")
    state_id = store.record_market_state(
        symbol="EURUSD",
        bid=1.0850,
        ask=1.0852,
        indicators={"RSI": 35, "MACD": 0.001},
        position_open=False
    )
    print(f"[OK] 市场状态记录ID: {state_id}")
    
    # 测试PPO经验记录
    print("\n[AI] 测试PPO经验记录...")
    exp_id = store.record_ppo_experience(
        symbol="EURUSD",
        state={"price": 1.0850, "rsi": 35},
        action="BUY",
        reward=0.01,
        done=False
    )
    print(f"[OK] PPO经验记录ID: {exp_id}")
    
    # 获取统计
    print("\n[DATA] 统计信息:")
    stats = store.get_statistics()
    print(json.dumps(stats, indent=2, ensure_ascii=False))
    
    print("\n[OK] 测试完成！数据存储系统工作正常！")