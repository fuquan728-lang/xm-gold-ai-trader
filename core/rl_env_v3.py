#!/usr/bin/env python3
"""
RL交易环境 V3 — Sparse Reward + Episodic

改进:
1. 稀疏奖励: 只在交易平仓时给reward (该笔交易的profit)
2. Episode: 200 bars/轮, 随机起始点
3. 每步Hold有微小cost (-0.05 per bar in position)
4. 观测增加: bars_held, price_since_entry
"""

import numpy as np
from typing import Dict, List, Optional, Any, Tuple

from core.logger import logger


# 动作: 0=HOLD, 1=BUY, 2=SELL
N_ACTIONS = 3


class TradingEnvV3:
    """V3 奖励型: 仅在仓位平仓时给reward"""

    def __init__(self, bars: List, episode_len: int = 200,
                 initial_balance: float = 10000.0, lot_size: float = 0.1,
                 sl_pips: float = 30, tp_pips: float = 60,
                 pip_size: float = 0.10, pip_value: float = 10.0):
        self.bars = bars
        self.episode_len = episode_len
        self.initial_balance = initial_balance
        self.lot_size = lot_size
        self.sl_pips = sl_pips
        self.tp_pips = tp_pips
        self.pip_size = pip_size
        self.pip_value = pip_value

        # 预计算所有bar的features以提高速度
        self._obs_cache = {}
        self._precompute = False  # lazy

        self.observation_space_dim = 24  # 22 + bars_held + entry_distance

        self.reset()

    def reset(self, seed: int = None) -> np.ndarray:
        """随机选择一个起始bar开始新episode"""
        if seed is not None:
            np.random.seed(seed)
        max_start = max(0, len(self.bars) - self.episode_len - 50)
        self._start_idx = np.random.randint(0, max_start + 1) if max_start > 0 else 0
        self._idx = self._start_idx
        self._bars_in_ep = 0

        self._balance = self.initial_balance
        self._equity = self.initial_balance
        self._peak_equity = self.initial_balance

        self._position_side = 0
        self._entry_price = 0.0
        self._entry_bar = 0
        self._floating_pnl = 0.0
        self._drawdown_pct = 0.0
        self._trades_count = 0
        self._done = False

        return self._get_obs()

    def step(self, action: int) -> Tuple[np.ndarray, float, bool, bool, Dict]:
        bar = self.bars[self._idx]
        prev_equity = self._equity
        reward = 0.0

        # ── 仓位管理 ──
        if self._position_side != 0:
            bars_held = self._bars_in_ep - self._entry_bar

            # 检查 SL/TP
            exit_price = self._check_stop(bar, self._position_side, self._entry_price)
            if exit_price:
                pips = (exit_price - self._entry_price) * self._position_side / self.pip_size
                profit = pips * self.pip_value * self.lot_size
                self._balance += profit
                self._trades_count += 1

                # ★ 稀疏Reward: 该笔交易的全部盈亏
                reward = profit
                self._position_side = 0
                self._entry_price = 0.0

            # 持仓成本 (鼓励尽快平仓)
            elif bars_held > 20:
                reward -= 0.02  # 持有超过20 bars开始扣分

        # ── 开仓 ──
        if self._position_side == 0 and action != 0:
            if action == 1:
                self._position_side = 1
            elif action == 2:
                self._position_side = -1
            self._entry_price = bar.close
            self._entry_bar = self._bars_in_ep

        # ── 更新权益 ──
        if self._position_side != 0:
            pips = (bar.close - self._entry_price) * self._position_side / self.pip_size
            self._floating_pnl = pips * self.pip_value * self.lot_size
            self._equity = self._balance + self._floating_pnl
        else:
            self._floating_pnl = 0.0
            self._equity = self._balance

        self._peak_equity = max(self._peak_equity, self._equity)
        self._drawdown_pct = (self._peak_equity - self._equity) / self._peak_equity if self._peak_equity > 0 else 0

        # ── 过度交易惩罚 ──
        if action != 0 and self._trades_count > self.episode_len * 0.02:
            reward -= 1.0

        # ── 推进 ──
        self._idx += 1
        self._bars_in_ep += 1

        # ── 终止 ──
        done = False
        if self._bars_in_ep >= self.episode_len or self._idx >= len(self.bars):
            # 强制平仓
            if self._position_side != 0:
                last_bar = self.bars[min(self._idx, len(self.bars) - 1)]
                pips = (last_bar.close - self._entry_price) * self._position_side / self.pip_size
                profit = pips * self.pip_value * self.lot_size
                self._balance += profit
                reward = profit  # 最后平仓的reward
                self._position_side = 0
            done = True

        # 爆仓
        if self._equity <= self.initial_balance * 0.3:
            done = True
            reward -= 50.0

        obs = self._get_obs() if not done else np.zeros(self.observation_space_dim, dtype=np.float32)
        info = {"equity": self._equity, "trades": self._trades_count,
                "drawdown": self._drawdown_pct, "idx": self._idx}

        return obs, reward, done, False, info

    def _check_stop(self, bar, side, entry) -> Optional[float]:
        sl = entry - self.sl_pips * self.pip_size * side
        tp = entry + self.tp_pips * self.pip_size * side
        if side == 1:
            if bar.low <= sl: return sl
            if bar.high >= tp: return tp
        else:
            if bar.high >= sl: return sl
            if bar.low <= tp: return tp
        return None

    def _get_obs(self) -> np.ndarray:
        """22基础特征 + 2额外 = 24维"""
        idx = self._idx
        bars = self.bars
        recent = bars[max(0, idx - 49):idx + 1]

        if len(recent) < 2:
            return np.zeros(24, dtype=np.float32)

        c = np.array([b.close for b in recent], dtype=np.float32)
        o = np.array([b.open for b in recent], dtype=np.float32)
        h = np.array([b.high for b in recent], dtype=np.float32)
        l = np.array([b.low for b in recent], dtype=np.float32)
        v = np.array([b.tick_volume for b in recent], dtype=np.float32)
        norm = c[-1] if c[-1] > 0 else 1.0

        f = np.zeros(24, dtype=np.float32)

        # 价格特征 (0-9)
        f[0] = c[-1] / norm - 1
        f[1] = o[-1] / norm - 1
        f[2] = h[-1] / norm - 1
        f[3] = l[-1] / norm - 1
        if len(c) >= 2:  f[4] = (c[-1] / c[-2] - 1) * 100
        if len(c) >= 5:  f[5] = (c[-1] / c[-5] - 1) * 100
        if len(c) >= 20: f[6] = (c[-1] / c[-20] - 1) * 100
        if len(c) >= 3:  f[7] = (c[-1] / c[-3] - 1) * 100
        f[8] = (h[-1] - l[-1]) / norm * 100
        f[9] = (c[-1] - l[-1]) / (h[-1] - l[-1] + 1e-8)

        # Volume (10-11)
        f[10] = np.log1p(v[-1]) / 10
        f[11] = v[-1] / (np.mean(v[-5:]) + 1) if len(v) >= 5 else 1.0

        # Spread (12)
        spread = bars[idx].spread / (norm + 1e-8) * 100
        f[12] = min(spread / 10, 1.0)

        # Indicators (13-17)
        f[13] = self._rsi(c, 14)
        macd, macd_s = self._macd(c)
        f[14] = macd / (norm * 0.01 + 1e-8)
        f[15] = (macd - macd_s) / (norm * 0.005 + 1e-8)
        f[16] = self._bb(c, 20)
        f[17] = self._atr(recent, 14) / (norm * 0.01 + 1e-8)

        # Account (18-20)
        f[18] = self._position_side
        f[19] = np.clip(self._floating_pnl / 100, -10, 10)
        f[20] = np.clip(self._drawdown_pct * 100, -50, 0)

        # 扩展特征 V3 (21-23)
        f[21] = 0.0  # reserved
        f[22] = min(self._bars_in_ep / 200, 1.0)  # episode进度
        f[23] = 0.0  # price distance since entry (0 if no position)

        return f

    @staticmethod
    def _rsi(c, n=14):
        if len(c) < n + 1: return 0.0
        d = np.diff(c[-n - 1:])
        g = np.mean(np.maximum(d, 0))
        l_ = np.mean(np.maximum(-d, 0))
        if l_ == 0: return 50.0
        return 50.0 - 50 / (1 + g / l_) if g > 0 else 0.0

    @staticmethod
    def _macd(c, fast=12, slow=26, sig=9):
        if len(c) < slow: return 0.0, 0.0
        a_f, a_s = 2 / (fast + 1), 2 / (slow + 1)
        ema_f = c[0]
        ema_s = c[0]
        macd_vals = [0.0]
        for x in c[1:]:
            ema_f = a_f * x + (1 - a_f) * ema_f
            ema_s = a_s * x + (1 - a_s) * ema_s
            macd_vals.append(ema_f - ema_s)
        macd_arr = np.array(macd_vals)
        # signal
        a_sig = 2 / (sig + 1)
        sig_ema = macd_arr[0]
        for v in macd_arr[1:]:
            sig_ema = a_sig * v + (1 - a_sig) * sig_ema
        return macd_arr[-1], sig_ema

    @staticmethod
    def _bb(c, n=20):
        if len(c) < n: return 0.0
        ma = np.mean(c[-n:])
        sd = np.std(c[-n:])
        if sd == 0: return 0.0
        return (c[-1] - ma) / (2 * sd)

    @staticmethod
    def _atr(bars, n=14):
        if len(bars) < 2: return 0.0
        trs = []
        for i in range(1, len(bars)):
            hh, ll, pc = bars[i].high, bars[i].low, bars[i - 1].close
            trs.append(max(hh - ll, abs(hh - pc), abs(ll - pc)))
        return np.mean(trs[-n:]) if trs else 0.0


# ==================== 评估函数 ====================

def evaluate_v3(env: TradingEnvV3, get_action_fn, n_episodes: int = 10) -> Dict:
    """V3评估 — 运行多个episode计算平均绩效"""
    total_trades = 0
    total_profit = 0.0
    episodes_done = 0
    all_daily_returns = []

    for _ in range(n_episodes):
        obs = env.reset()
        done = False
        ep_profit = 0.0
        ep_trades = 0
        equity_start = env._equity

        while not done:
            action = get_action_fn(obs)
            obs, reward, done, _, info = env.step(action)
            ep_profit += reward
            ep_trades = info['trades']

        episodes_done += 1
        if env._equity > 0:
            all_daily_returns.append((env._equity - equity_start) / equity_start)

        total_trades += ep_trades
        total_profit += (env._equity - equity_start)

    avg_return = np.mean(all_daily_returns) * 100 if all_daily_returns else 0
    avg_trades = total_trades / n_episodes if n_episodes > 0 else 0

    # Sharpe approximation
    returns_arr = np.array(all_daily_returns)
    sharpe = np.mean(returns_arr) / (np.std(returns_arr) + 1e-8) * np.sqrt(252 * 200 / 1440) if len(returns_arr) > 1 else 0

    return {
        "avg_return_pct": avg_return,
        "avg_trades": avg_trades,
        "sharpe": sharpe,
        "total_profit": total_profit,
        "episodes": n_episodes
    }
