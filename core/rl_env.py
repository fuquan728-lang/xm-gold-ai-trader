#!/usr/bin/env python3
"""
强化学习交易环境 — Gymnasium兼容

观测空间: [OHLCV特征, 技术指标, 账户状态] → shape=(obs_dim,)
动作空间: Discrete(3) → 0=HOLD, 1=BUY, 2=SELL
奖励函数: 风险调整收益 (profit - drawdown_penalty - turnover_cost)

设计原则:
1. 严格无Look-ahead: 每步只使用当前Bar及之前的信息
2. 真实交易约束: 滑点/点差/最小止损距离
3. 风险惩罚: 大回撤时奖励降权, 鼓励稳健策略
"""

import math
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass

import numpy as np

from core.logger import logger


# ==================== 动作空间定义 ====================

# 0 = HOLD (不交易)
# 1 = BUY  (开多/平空)
# 2 = SELL (开空/平多)

ACTION_HOLD = 0
ACTION_BUY  = 1
ACTION_SELL = 2
N_ACTIONS   = 3


# ==================== 特征工程 ====================

@dataclass
class FeatureConfig:
    """特征配置"""
    lookback_window: int = 50      # 回看窗口(bar数)
    use_price_norm: bool = True    # 价格归一化
    use_volume: bool = True        # 使用成交量
    use_spread: bool = True        # 使用点差
    indicator_windows: List[int] = None  # 指标窗口列表

    def __post_init__(self):
        if self.indicator_windows is None:
            self.indicator_windows = [5, 10, 20, 50]


class FeatureEngineer:
    """特征工程 — 将原始Bar数据转换为观测向量"""

    def __init__(self, config: FeatureConfig = None):
        self.config = config or FeatureConfig()
        self._feature_dim = None

    @property
    def feature_dim(self) -> int:
        """计算观测维度"""
        if self._feature_dim is None:
            dim = 0
            # 价格特征: OHLC4 + returns(4) + HL比率(2) = 10
            dim += 10
            # 成交量特征 (2)
            if self.config.use_volume:
                dim += 2
            # 点差特征 (1)
            if self.config.use_spread:
                dim += 1
            # 技术指标: RSI(1) + MACD(2) + BB(2) + ATR(1) = 6
            dim += 6
            # 账户状态: position(1) + floating_pnl(1) + drawdown(1) = 3
            dim += 3
            self._feature_dim = dim
        return self._feature_dim

    def extract(self, bars: List, idx: int, 
                position_side: int, floating_pnl: float, 
                drawdown_pct: float) -> np.ndarray:
        """
        提取观测向量

        Args:
            bars: 历史Bar列表（当前索引的Bar已加入）
            idx: 当前Bar索引
            position_side: -1=空仓, 0=无, 1=多仓
            floating_pnl: 浮动盈亏
            drawdown_pct: 当前回撤百分比
        """
        features = []
        window = min(idx + 1, self.config.lookback_window)
        start = max(0, idx - window + 1)
        recent = bars[start:idx + 1]

        if len(recent) < 2:
            return np.zeros(self.feature_dim)

        closes = np.array([b.close for b in recent])
        opens = np.array([b.open for b in recent])
        highs = np.array([b.high for b in recent])
        lows = np.array([b.low for b in recent])
        volumes = np.array([b.tick_volume for b in recent])
        spreads = np.array([b.spread for b in recent])

        # 价格归一化（以当前收盘价为基准）
        current_close = closes[-1]
        norm_factor = current_close if current_close > 0 else 1.0

        # (1) 价格特征
        features.append(closes[-1] / norm_factor - 1)    # 收盘价
        features.append(opens[-1] / norm_factor - 1)      # 开盘价
        features.append(highs[-1] / norm_factor - 1)      # 最高价
        features.append(lows[-1] / norm_factor - 1)       # 最低价

        if len(recent) >= 2:
            ret1 = closes[-1] / closes[-2] - 1
            features.append(ret1 * 100)                    # 1期收益率(%)
        else:
            features.append(0.0)

        if len(recent) >= 5:
            ret5 = closes[-1] / closes[-5] - 1
            features.append(ret5 * 100)                    # 5期收益率(%)
        else:
            features.append(0.0)

        if len(recent) >= 20:
            ret20 = closes[-1] / closes[-20] - 1
            features.append(ret20 * 100)                   # 20期收益率(%)
        else:
            features.append(0.0)

        # 短期动量
        if len(recent) >= 3:
            mom3 = closes[-1] / closes[-3] - 1
            features.append(mom3 * 100)
        else:
            features.append(0.0)

        # HL比率
        hl_range = highs[-1] - lows[-1]
        features.append(hl_range / norm_factor * 100 if norm_factor > 0 else 0)
        if closes[-1] > 0:
            features.append((closes[-1] - lows[-1]) / (highs[-1] - lows[-1] + 1e-8))

        # (2) 成交量特征
        if self.config.use_volume:
            features.append(math.log1p(volumes[-1]) / 10)
            if len(volumes) >= 5:
                vol_ratio = volumes[-1] / (np.mean(volumes[-5:]) + 1)
                features.append(min(vol_ratio, 5.0))
            else:
                features.append(1.0)  # 数据不足时默认为1

        # (3) 点差特征
        if self.config.use_spread:
            spread_norm = spreads[-1] / norm_factor * 100 if len(spreads) > 0 and norm_factor > 0 else 0
            features.append(spread_norm)

        # (4) 技术指标 — 固定维度输出
        if len(closes) >= 14:
            rsi = self._calc_rsi(closes[-14:], 14)
            features.append((rsi - 50) / 50)
        else:
            features.append(0.0)  # 数据不足时补零

        if len(closes) >= 26:
            macd, signal = self._calc_macd(closes)
            features.append(macd / (norm_factor * 0.01))
            features.append((macd - signal) / (norm_factor * 0.005 + 1e-8))
        else:
            features.append(0.0)
            features.append(0.0)

        if len(closes) >= 20:
            bb_pos = self._calc_bb_position(closes[-20:])
            features.append(bb_pos)
        else:
            features.append(0.0)

        if len(recent) >= 14:
            atr = self._calc_atr(recent[-14:])
            features.append(atr / (norm_factor * 0.01 + 1e-8))
        else:
            features.append(0.0)

        # (5) 账户状态
        features.append(position_side)                     # -1/0/1
        features.append(np.clip(floating_pnl / 100.0, -10, 10))  # 浮动盈亏缩放
        features.append(np.clip(drawdown_pct * 100, -50, 0))     # 回撤

        # 确保固定维度输出
        result = np.array(features, dtype=np.float32)
        if len(result) < self.feature_dim:
            padded = np.zeros(self.feature_dim, dtype=np.float32)
            padded[:len(result)] = result
            return padded
        return result[:self.feature_dim]

    @staticmethod
    def _calc_rsi(closes: np.ndarray, period: int = 14) -> float:
        diffs = np.diff(closes)
        gains = np.where(diffs > 0, diffs, 0)
        losses = np.where(diffs < 0, -diffs, 0)
        avg_gain = np.mean(gains)
        avg_loss = np.mean(losses)
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100 - 100 / (1 + rs)

    @staticmethod
    def _calc_macd(closes: np.ndarray, fast: int = 12, slow: int = 26, sig: int = 9) -> Tuple[float, float]:
        ema_fast = FeatureEngineer._ema(closes, fast)
        ema_slow = FeatureEngineer._ema(closes, slow)
        macd_line = ema_fast - ema_slow

        macd_series = [0.0] * (slow - 1)
        for i in range(slow - 1, len(closes)):
            ema_f = FeatureEngineer._ema(closes[:i + 1], fast)
            ema_s = FeatureEngineer._ema(closes[:i + 1], slow)
            macd_series.append(ema_f - ema_s)
        macd_arr = np.array(macd_series)
        signal_line = FeatureEngineer._ema(macd_arr[-sig:] if len(macd_arr) >= sig else macd_arr, sig)

        return macd_line, signal_line

    @staticmethod
    def _ema(data: np.ndarray, period: int) -> float:
        if len(data) == 0:
            return 0.0
        alpha = 2 / (period + 1)
        ema = data[0]
        for x in data[1:]:
            ema = alpha * x + (1 - alpha) * ema
        return ema

    @staticmethod
    def _calc_bb_position(closes: np.ndarray, period: int = 20, std: float = 2.0) -> float:
        ma = np.mean(closes)
        sigma = np.std(closes)
        if sigma == 0:
            return 0.0
        return (closes[-1] - ma) / (std * sigma)

    @staticmethod
    def _calc_atr(bars_or_recents: list, period: int = 14) -> float:
        tr_values = []
        for i in range(1, len(bars_or_recents)):
            b = bars_or_recents[i]
            prev = bars_or_recents[i - 1]
            if hasattr(b, 'high'):
                h, l, pc = b.high, b.low, prev.close
            else:
                h, l, pc = b[1], b[2], prev[3] if isinstance(prev, (list, tuple)) else prev
            tr = max(h - l, abs(h - pc), abs(l - pc))
            tr_values.append(tr)
        return np.mean(tr_values) if tr_values else 0.0


# ==================== Gymnasium 交易环境 ====================

class TradingGymEnv:
    """
    交易强化学习环境 (Gymnasium-compatible)

    Observation: 特征工程提取的多维向量
    Action: Discrete(3) → HOLD/BUY/SELL
    Reward: 风险调整收益
    """

    metadata = {"render_modes": ["human"]}

    def __init__(self, bars: List, 
                 initial_balance: float = 10000.0,
                 lot_size: float = 0.1,
                 sl_pips: float = 30.0,
                 tp_pips: float = 60.0,
                 max_position: int = 1,
                 feature_config: FeatureConfig = None,
                 pip_size: float = 0.10,
                 pip_value: float = 10.0):
        """
        Args:
            bars: Bar列表
            initial_balance: 初始资金
            lot_size: 固定交易手数
            sl_pips: 止损pips
            tp_pips: 止盈pips
            max_position: 最大同时持仓数
            pip_size: 1 pip的价格距离
            pip_value: 每pip价值(标准手)
        """
        self.bars = bars
        self.initial_balance = initial_balance
        self.lot_size = lot_size
        self.sl_pips = sl_pips
        self.tp_pips = tp_pips
        self.max_position = max_position
        self.pip_size = pip_size
        self.pip_value = pip_value

        # 特征工程
        self.feature_engineer = FeatureEngineer(feature_config)
        self.observation_space_dim = self.feature_engineer.feature_dim

        # 状态
        self._idx = 0
        self._balance = initial_balance
        self._equity = initial_balance
        self._peak_equity = initial_balance
        self._position_side = 0      # -1/0/1
        self._entry_price = 0.0
        self._floating_pnl = 0.0
        self._drawdown_pct = 0.0
        self._trades_count = 0
        self._done = False

    @property
    def current_bar(self):
        return self.bars[self._idx] if self._idx < len(self.bars) else None

    def reset(self, seed: int = None) -> np.ndarray:
        """重置环境"""
        if seed is not None:
            np.random.seed(seed)

        self._idx = 0
        self._balance = self.initial_balance
        self._equity = self.initial_balance
        self._peak_equity = self.initial_balance
        self._position_side = 0
        self._entry_price = 0.0
        self._floating_pnl = 0.0
        self._drawdown_pct = 0.0
        self._trades_count = 0
        self._done = False

        return self._get_obs()

    def step(self, action: int) -> Tuple[np.ndarray, float, bool, bool, Dict]:
        """
        执行一步

        Args:
            action: 0=HOLD, 1=BUY, 2=SELL

        Returns:
            observation, reward, terminated, truncated, info
        """
        bar = self.current_bar
        prev_equity = self._equity

        # ==== 平仓检查 ====
        if self._position_side != 0:
            exit_price = None
            exit_reason = ""

            if self._position_side == 1:  # BUY
                sl_price = self._entry_price - self.sl_pips * self.pip_size
                tp_price = self._entry_price + self.tp_pips * self.pip_size
                if bar.low <= sl_price:
                    exit_price = sl_price
                    exit_reason = "sl"
                elif bar.high >= tp_price:
                    exit_price = tp_price
                    exit_reason = "tp"
            else:  # SELL (-1)
                sl_price = self._entry_price + self.sl_pips * self.pip_size
                tp_price = self._entry_price - self.tp_pips * self.pip_size
                if bar.high >= sl_price:
                    exit_price = sl_price
                    exit_reason = "sl"
                elif bar.low <= tp_price:
                    exit_price = tp_price
                    exit_reason = "tp"

            if exit_price:
                pips = (exit_price - self._entry_price) * self._position_side / self.pip_size
                profit = pips * self.pip_value * self.lot_size
                self._balance += profit
                self._trades_count += 1
                self._position_side = 0
                self._entry_price = 0.0

        # ==== 开仓逻辑 ====
        if self._position_side == 0 and action != ACTION_HOLD:
            if action == ACTION_BUY:
                self._position_side = 1
            elif action == ACTION_SELL:
                self._position_side = -1
            self._entry_price = bar.close

        # ==== 更新浮动盈亏 ====
        if self._position_side != 0:
            pips = (bar.close - self._entry_price) * self._position_side / self.pip_size
            self._floating_pnl = pips * self.pip_value * self.lot_size
            self._equity = self._balance + self._floating_pnl
        else:
            self._floating_pnl = 0.0
            self._equity = self._balance

        # ==== 更新回撤 ====
        self._peak_equity = max(self._peak_equity, self._equity)
        self._drawdown_pct = (self._peak_equity - self._equity) / self._peak_equity if self._peak_equity > 0 else 0.0

        # ==== 奖励函数 ====
        equity_change = self._equity - prev_equity
        # 基础奖励: 权益变化（放大以提供有效梯度信号）
        reward = equity_change / 10.0

        # 回撤惩罚（重罚）
        if self._drawdown_pct > 0.03:
            reward -= self._drawdown_pct * 100.0

        # 持仓惩罚
        if self._position_side != 0:
            reward -= 0.01

        # 过度交易惩罚（严厉 — 允许最多 n_bars*0.005 次交易）
        max_reasonable_trades = max(10, int(len(self.bars) * 0.005))
        if action != ACTION_HOLD:
            # 匀速惩罚：超过阈值后每多一次交易罚1.0
            excess = max(0, self._trades_count - max_reasonable_trades)
            if excess > 0:
                reward -= 1.0 + excess * 0.1

        # 持仓平仓奖励/惩罚
        if self._position_side == 0 and action == ACTION_HOLD:
            reward += 0.001  # 空仓HOLD微奖励

        # ==== 推进时间 ====
        self._idx += 1

        # ==== 终止条件 ====
        terminated = False
        truncated = False

        if self._idx >= len(self.bars):
            # 强制平仓
            if self._position_side != 0:
                bar = self.bars[-1]
                pips = (bar.close - self._entry_price) * self._position_side / self.pip_size
                profit = pips * self.pip_value * self.lot_size
                self._balance += profit
                self._equity = self._balance
                self._position_side = 0
            terminated = True

        # 爆仓
        if self._equity <= self.initial_balance * 0.2:
            terminated = True
            reward -= 20.0  # 爆仓大幅惩罚

        # 获取观测
        obs = self._get_obs() if not terminated else np.zeros(self.observation_space_dim)

        info = {
            "equity": self._equity,
            "balance": self._balance,
            "drawdown": self._drawdown_pct,
            "position": self._position_side,
            "trades": self._trades_count,
            "idx": self._idx
        }

        return obs, reward, terminated, truncated, info

    def _get_obs(self) -> np.ndarray:
        """构建观测向量"""
        return self.feature_engineer.extract(
            self.bars, self._idx,
            self._position_side,
            self._floating_pnl,
            self._drawdown_pct
        )

    def render(self, mode: str = "human"):
        bar = self.current_bar
        print(f"[{self._idx}/{len(self.bars)}] "
              f"Equity=${self._equity:.0f} "
              f"Pos={self._position_side} "
              f"DD={self._drawdown_pct*100:.1f}% "
              f"Trades={self._trades_count}")


# ==================== 批量回测评估 ====================

def evaluate_agent(env: TradingGymEnv, get_action_func, 
                   n_episodes: int = 1, render: bool = False) -> Dict[str, float]:
    """
    评估Agent在环境中的表现

    Args:
        env: 交易环境
        get_action_func: (obs) → action 函数
        n_episodes: 评估episode数
        render: 是否渲染

    Returns:
        绩效字典 {sharpe, sortino, max_dd, total_return, win_rate, ...}
    """
    all_equity = []
    all_returns = []

    for ep in range(n_episodes):
        obs = env.reset()
        done = False
        episode_equity = [env.initial_balance]

        while not done:
            action = get_action_func(obs)
            obs, reward, terminated, truncated, info = env.step(action)
            done = terminated or truncated
            episode_equity.append(info["equity"])

            if render:
                env.render()

        all_equity.extend(episode_equity)

    # 计算绩效指标
    eq = np.array(all_equity)
    returns = np.diff(eq) / eq[:-1] + 1e-8

    sharpe = np.mean(returns) / np.std(returns) * np.sqrt(252) if np.std(returns) > 0 else 0
    neg_returns = returns[returns < 0]
    sortino = np.mean(returns) / np.std(neg_returns) * np.sqrt(252) if len(neg_returns) > 0 and np.std(neg_returns) > 0 else 0
    running_max = np.maximum.accumulate(eq)
    max_dd = np.max((running_max - eq) / running_max)
    total_return = (eq[-1] - eq[0]) / eq[0]

    return {
        "total_return_pct": total_return * 100,
        "final_equity": eq[-1],
        "sharpe_ratio": sharpe,
        "sortino_ratio": sortino,
        "max_drawdown_pct": max_dd * 100,
        "n_trades": env._trades_count if hasattr(env, '_trades_count') else 0
    }
