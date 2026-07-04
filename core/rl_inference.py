#!/usr/bin/env python3
"""
RL模型推理接口 — 为AI服务提供RL决策后备

加载训练好的PPO模型，基于指标数据快速给出交易信号。
"""

import numpy as np
from typing import Dict, Optional, Any, Tuple

from core.logger import logger
from core import config


class RLInferenceEngine:
    """RL模型推理引擎"""

    def __init__(self, model_path: str = "models/ppo_gold_v2.pt"):
        self.model_path = model_path
        self.model = None
        self.obs_dim = None
        self.loaded = False
        self._try_load()

    def _try_load(self):
        """尝试加载模型"""
        if not getattr(config, "ENABLE_RL_MODEL", False):
            logger.info("[RL-INF] RL model disabled; fallback to rule/LLM decision")
            return
        try:
            import torch
            self.model = torch.load(self.model_path, map_location='cpu', weights_only=False)
            self.obs_dim = self.model.get('obs_dim')
            logger.info(f"[RL-INF] Model loaded: {self.model_path} (obs_dim={self.obs_dim})")
            self.loaded = True
        except FileNotFoundError:
            logger.debug(f"[RL-INF] Model not found: {self.model_path} (will create empty engine)")
        except Exception as e:
            logger.warning(f"[RL-INF] Failed to load model: {e}")

    def predict(self, indicators: Dict[str, float],
                bid: float, ask: float,
                position_side: int = 0,
                floating_pnl: float = 0.0,
                drawdown_pct: float = 0.0) -> Tuple[str, float, str]:
        """
        基于指标数据预测交易信号

        Args:
            indicators: {"rsi": 50.0, "macd_main": 0.1, "ema50": 4000, ...}
            bid/ask: 报价
            position_side: -1/0/1
            floating_pnl: 浮动盈亏($)
            drawdown_pct: 回撤比例

        Returns:
            (action, confidence, reason)
        """
        if not self.loaded or self.model is None:
            return "HOLD", 0.0, "RL模型未加载"

        try:
            import torch
            from core.rl_env import FeatureEngineer, ACTION_HOLD, ACTION_BUY, ACTION_SELL
            from core.rl_trainer import ActorCritic

            # 构建特征向量
            fe = FeatureEngineer()
            obs = self._build_observation(indicators, bid, ask, position_side,
                                          floating_pnl, drawdown_pct)

            # 加载网络
            model_state = self.model.get('model_state')
            if model_state is None:
                return "HOLD", 0.0, "RL模型数据损坏"

            # 创建网络并加载权重
            n_actions = self.model.get('n_actions', 3)
            net = ActorCritic(self.obs_dim, n_actions)
            net.load_state_dict(model_state)
            net.eval()

            # 推理
            obs_tensor = torch.FloatTensor(obs).unsqueeze(0)
            with torch.no_grad():
                logits, value = net(obs_tensor)
                probs = torch.nn.functional.softmax(logits, dim=-1)
                action_idx = torch.argmax(probs, dim=-1).item()
                confidence = probs[0, action_idx].item()

            action_map = {0: "HOLD", 1: "BUY", 2: "SELL"}
            action = action_map.get(action_idx, "HOLD")

            # 置信度阈值
            if confidence < 0.5:
                return "HOLD", confidence, f"RL置信度过低({confidence:.2f})"

            reason = f"RL模型决策: {action} (conf={confidence:.2f}, value={value.item():.2f})"
            return action, min(confidence, 0.8), reason

        except Exception as e:
            logger.error(f"[RL-INF] Prediction failed: {e}")
            return "HOLD", 0.0, f"RL推理失败: {str(e)[:40]}"

    def _build_observation(self, indicators, bid, ask,
                          position_side, floating_pnl, drawdown_pct) -> np.ndarray:
        """基于指标构建标准化观测向量"""
        obs = np.zeros(22, dtype=np.float32)

        # 价格特征
        mid = (bid + ask) / 2
        obs[0] = 0.0  # normalized close
        obs[1] = 0.0
        obs[2] = 0.0
        obs[3] = 0.0
        obs[4] = 0.0  # ret1
        obs[5] = 0.0  # ret5
        obs[6] = 0.0  # ret20
        obs[7] = 0.0  # mom3
        obs[8] = (ask - bid) / mid * 100 if mid > 0 else 0  # HL ratio
        obs[9] = 0.5  # close position in range

        # Volume
        obs[10] = 0.5
        obs[11] = 1.0

        # Spread
        spread_pips = (ask - bid) / 0.10 if mid > 0 else 0
        obs[12] = min(spread_pips / 10.0, 1.0)

        # Indicators
        rsi = indicators.get('rsi', 50)
        obs[13] = (rsi - 50) / 50  # RSI normalized

        macd = indicators.get('macd_main', 0)
        obs[14] = macd / (mid * 0.001 + 1e-8)  # MACD

        macd_signal = indicators.get('macd_signal', 0)
        obs[15] = (macd - macd_signal) / (mid * 0.0005 + 1e-8)

        ema50 = indicators.get('ema50', mid)
        bb_pos = (mid - ema50) / (mid * 0.02 + 1e-8) if ema50 > 0 else 0
        obs[16] = bb_pos  # BB position

        obs[17] = 0.5  # ATR default

        # Account state
        obs[18] = position_side
        obs[19] = np.clip(floating_pnl / 100.0, -10, 10)
        obs[20] = np.clip(drawdown_pct * 100, -50, 0)

        # Padding for extra feature
        obs[21] = 0.0

        return obs


# 全局单例
_rl_engine: Optional[RLInferenceEngine] = None


def get_rl_engine(model_path: str = "models/ppo_gold_v2.pt") -> RLInferenceEngine:
    """获取RL推理引擎单例"""
    global _rl_engine
    if _rl_engine is None:
        _rl_engine = RLInferenceEngine(model_path)
    return _rl_engine


def get_rl_signal(indicators: dict, bid: float, ask: float) -> Tuple[str, float, str]:
    """快捷函数：获取RL信号"""
    engine = get_rl_engine()
    return engine.predict(indicators, bid, ask)
