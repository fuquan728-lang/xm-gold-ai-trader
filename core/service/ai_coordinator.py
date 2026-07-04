# -*- coding: utf-8 -*-
"""
AIServiceCoordinator - AI分析协调器 (Phase 3)
负责核心AI分析、动态SL/TP计算、风险评估

从 MT5AITradingService.analyze() 拆分而来 (2026-07-04)
"""

import time
from datetime import datetime
from typing import Dict, Any, Optional, Tuple

from core.logger import logger, monitor
from core.cache import global_cache
from core.validator import get_cache_key, get_fuzzy_cache_key, get_cache_keys_for_lookup
from core import config
from core.service.utils import (
    build_indicator_fingerprint,
    append_local_reason,
    BLOCKING_RISK_KEYWORDS,
)


class AIServiceCoordinator:
    """AI分析协调器
    封装 AI 调用、指标校验、动态 SL/TP、风险评估的完整分析管道。
    """

    def __init__(self, ai_analyzer, risk_manager=None, indicator_analyzer=None):
        self._ai_analyzer = ai_analyzer
        self._risk_manager = risk_manager
        self._indicator_analyzer = indicator_analyzer

    # ==================== 阻断性风险检查 ====================

    @staticmethod
    def get_blocking_risk_reason(assessment) -> Optional[str]:
        """返回阻断交易的风险原因；无阻断风险则返回None。"""
        warnings = getattr(assessment, "warning_messages", None) or []

        for warning in warnings:
            warning_text = str(warning)
            if any(
                keyword.lower() in warning_text.lower()
                for keyword in BLOCKING_RISK_KEYWORDS
            ):
                return warning_text

        position_size = getattr(assessment, "recommended_position_size", None)
        if position_size is not None and position_size <= 0:
            return "推荐仓位为0，禁止开仓"

        risk_reward_ratio = getattr(assessment, "risk_reward_ratio", None)
        if risk_reward_ratio is not None and risk_reward_ratio <= 0:
            return f"风险回报比{risk_reward_ratio:.2f}无效，禁止开仓"

        return None

    # ==================== 动态 SL/TP ====================

    def calculate_sl_tp(
        self,
        symbol: str,
        action: str,
        confidence: float,
        bid: float,
        ask: float,
        indicators: Optional[dict],
    ) -> Tuple[int, int]:
        """
        动态计算止损止盈 pips 数

        ★ 单位约定（与EA端保持一致）：
            1 pip = 10 * _Point（MT5 黄金 _Point=0.01）
            即 1 pip = 0.10 美元
            30 pip = 3.00 美元，60 pip = 6.00 美元

        MT5 stops_level 通常 100-200 points = 10-20 pips
        → 止损最小值设 25 pips (2.50$)，避免 [invalid stops]

        返回: (stop_loss_pips, take_profit_pips)
        """
        base_sl = 30  # 外汇默认 30 pips
        base_tp = 60

        # 黄金/贵金属特殊处理
        sym_upper = symbol.upper()
        is_gold = (
            sym_upper.startswith("XAU")
            or "GOLD" in sym_upper
            or sym_upper.endswith("_")
        )
        if is_gold:
            base_sl = 40
            base_tp = 80
            logger.debug(
                f"[SL/TP] 黄金品种({symbol})，使用宽止损: "
                f"SL={base_sl}pips(${base_sl * 0.1:.1f}), TP={base_tp}pips(${base_tp * 0.1:.1f})"
            )

        # 从指标计算波动率
        volatility_multiplier = 1.0
        if indicators:
            rsi = indicators.get("rsi", 50)
            if rsi > 70 or rsi < 30:
                volatility_multiplier = 1.3

            history = indicators.get("recent_history", [])
            if len(history) >= 5:
                highs = [h.get("high", 0) for h in history]
                lows = [h.get("low", 0) for h in history]
                closes = [h.get("close", 0) for h in history]

                true_ranges = []
                for i in range(1, len(closes)):
                    tr = max(
                        highs[i] - lows[i],
                        abs(highs[i] - closes[i - 1]),
                        abs(lows[i] - closes[i - 1]),
                    )
                    true_ranges.append(tr)

                if true_ranges:
                    avg_atr = sum(true_ranges) / len(true_ranges)
                    if avg_atr > 5.0:
                        volatility_multiplier = 1.3
                    elif avg_atr < 2.0:
                        volatility_multiplier = 0.85

        # 置信度调整
        if confidence < 0.65:
            sl_multiplier = 0.75
            tp_multiplier = 0.85
        elif confidence < 0.70:
            sl_multiplier = 0.85
            tp_multiplier = 0.90
        elif confidence > 0.85:
            sl_multiplier = 1.0
            tp_multiplier = 1.2
        else:
            sl_multiplier = 1.0
            tp_multiplier = 1.0

        # 风险管理器调整
        risk_adjustment = 1.0
        if self._risk_manager:
            try:
                risk_level = self._risk_manager.risk_params.risk_level
                if hasattr(risk_level, "value"):
                    if "high" in risk_level.value.lower():
                        risk_adjustment = 0.7
                        logger.debug(f"[SL/TP] 高风险状态，止损收紧 x{risk_adjustment}")
                    elif "low" in risk_level.value.lower():
                        risk_adjustment = 1.1
                        logger.debug(f"[SL/TP] 低风险状态，止损放宽 x{risk_adjustment}")
            except Exception as e:
                logger.debug(f"[SL/TP] 风险等级读取失败，使用默认倍数: {e}")

        final_sl_multiplier = volatility_multiplier * sl_multiplier * risk_adjustment
        final_tp_multiplier = volatility_multiplier * tp_multiplier * risk_adjustment

        stop_loss_pips = int(base_sl * final_sl_multiplier)
        take_profit_pips = int(base_tp * final_tp_multiplier)

        if take_profit_pips < stop_loss_pips * 1.5:
            take_profit_pips = int(stop_loss_pips * 1.5)

        stop_loss_pips = max(25, min(150, stop_loss_pips))
        take_profit_pips = max(40, min(300, take_profit_pips))

        logger.debug(
            f"[SL/TP] 最终计算: SL={stop_loss_pips}pips(${stop_loss_pips * 0.1:.1f}) "
            f"TP={take_profit_pips}pips(${take_profit_pips * 0.1:.1f}) "
            f"SL乘数={final_sl_multiplier:.2f}, TP乘数={final_tp_multiplier:.2f}"
        )

        return stop_loss_pips, take_profit_pips

    # ==================== 核心 AI 分析 ====================

    def analyze(
        self,
        symbol: str,
        bid: float,
        ask: float,
        current_time: float,
        history: Optional[list] = None,
        indicators: Optional[dict] = None,
        multi_timeframe: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """核心 AI 分析管道"""

        start_time = time.time()
        allow_fallback_trading = bool(getattr(config, "ALLOW_FALLBACK_TRADING", False))
        indicator_fingerprint = build_indicator_fingerprint(indicators)

        def unavailable_ai_hold(reason: str) -> Dict[str, Any]:
            monitor.record_request(True, time.time() - start_time)
            return {
                "action": "HOLD",
                "confidence": 0.75,
                "reason": reason,
                "symbol": symbol,
                "analysis_time": datetime.now().isoformat(),
                "use_deepseek": False,
                "cached": False,
            }

        # ---- 缓存查找 ----
        cache_keys = get_cache_keys_for_lookup(symbol, bid, ask)
        cached_result = None
        used_cache_key = None

        for cache_key in cache_keys:
            cached = global_cache.get(cache_key)
            if cached:
                if not isinstance(cached, dict):
                    logger.info(f"[CACHE] Skipping invalid cached result type: {type(cached).__name__}")
                    continue
                cached_action = cached.get("action") if isinstance(cached, dict) else None
                if not allow_fallback_trading and cached_action in ("BUY", "SELL"):
                    logger.info(f"[CACHE] Safe mode skips cached trade signal {cached_action}: {cache_key}")
                    continue
                cached_fingerprint = cached.get("indicator_fingerprint") if isinstance(cached, dict) else None
                if indicator_fingerprint and cached_fingerprint != indicator_fingerprint:
                    logger.info(f"[CACHE] 指标快照变化，跳过缓存结果: {cache_key}")
                    continue
                cached_result = cached
                used_cache_key = cache_key
                break

        if cached_result:
            is_exact_match = used_cache_key == cache_keys[0]
            logger.info(f"CACHE 使用{'精确' if is_exact_match else '模糊'}缓存结果 (键: {used_cache_key})")
            monitor.record_cache_hit()
            if (
                not allow_fallback_trading
                and not self._ai_analyzer.is_deepseek_available()
                and cached_result.get("action") in ("BUY", "SELL")
            ):
                return unavailable_ai_hold("AI不可用且后备交易未启用，缓存交易信号降级为HOLD")
            return cached_result

        monitor.record_cache_miss()

        # ---- AI 分析 ----
        action = "HOLD"
        confidence = 0.5
        reason = ""
        stop_loss_pips = None
        take_profit_pips = None
        deepseek_used = False

        if self._ai_analyzer.is_deepseek_available():
            prompt = self._ai_analyzer.build_prompt(
                symbol, bid, ask, current_time, history, indicators, multi_timeframe
            )
            ai_result = self._ai_analyzer.call_api(prompt)

            if ai_result:
                deepseek_used = True
                action = ai_result["action"]
                confidence = ai_result["confidence"]
                reason = ai_result["reason"]
                stop_loss_pips = ai_result.get("stop_loss_pips")
                take_profit_pips = ai_result.get("take_profit_pips")
                monitor.record_request(True, time.time() - start_time)
            else:
                if not allow_fallback_trading:
                    logger.warning("[SAFE] AI分析失败，后备交易未启用，返回HOLD")
                    return unavailable_ai_hold("AI分析失败，后备交易未启用")
                logger.warning("[WARN] AI分析失败，使用后备策略")
                action, confidence, reason = self._ai_analyzer.get_fallback_strategy(
                    symbol, bid, ask, indicators, multi_timeframe
                )
                monitor.record_request(True, time.time() - start_time)
        else:
            if not allow_fallback_trading:
                if self._ai_analyzer.use_deepseek:
                    logger.warning("[SAFE] DeepSeek不可用，后备交易未启用，返回HOLD")
                    return unavailable_ai_hold("DeepSeek不可用，后备交易未启用")
                logger.info("[SAFE] DeepSeek已禁用，后备交易未启用，返回HOLD")
                return unavailable_ai_hold("DeepSeek已禁用，后备交易未启用")
            action, confidence, reason = self._ai_analyzer.get_fallback_strategy(
                symbol, bid, ask, indicators, multi_timeframe
            )
            monitor.record_request(True, time.time() - start_time)

        # ---- 指标校验 ----
        if self._indicator_analyzer:
            indicator_validation = self._indicator_analyzer.evaluate_signal(
                action, confidence, indicators, symbol, bid, ask
            )
            action = indicator_validation["action"]
            confidence = indicator_validation["confidence"]
            reason = append_local_reason(reason, indicator_validation.get("reason", ""))
        else:
            indicator_validation = {"action": action, "confidence": confidence}

        # ---- RL 模型后备 ----
        if (
            action == "HOLD"
            and indicators
            and isinstance(indicators, dict)
            and getattr(config, "ENABLE_RL_MODEL", False)
        ):
            try:
                from core.rl_inference import get_rl_signal

                rl_action, rl_conf, rl_reason = get_rl_signal(indicators, bid, ask)
                if rl_action != "HOLD" and rl_conf > 0.55:
                    logger.info(f"[RL] RL后备信号: {rl_action} conf={rl_conf:.2f}")
                    reason = reason + " | RL备选: " + rl_reason[:60]
            except Exception as e:
                logger.debug(f"[RL] RL后备检查跳过: {e}")

        if action == "HOLD":
            stop_loss_pips = None
            take_profit_pips = None

        # ---- 动态 SL/TP ----
        if action in ("BUY", "SELL") and (stop_loss_pips is None or take_profit_pips is None):
            sl, tp = self.calculate_sl_tp(symbol, action, confidence, bid, ask, indicators)
            if stop_loss_pips is None:
                stop_loss_pips = sl
            if take_profit_pips is None:
                take_profit_pips = tp

        result = {
            "action": action,
            "confidence": confidence,
            "reason": reason,
            "symbol": symbol,
            "analysis_time": datetime.now().isoformat(),
            "use_deepseek": deepseek_used,
            "cached": False,
            "indicator_validation": indicator_validation,
            "indicator_fingerprint": indicator_fingerprint,
        }

        if action in ("BUY", "SELL"):
            if stop_loss_pips is not None:
                result["stop_loss_pips"] = stop_loss_pips
            if take_profit_pips is not None:
                result["take_profit_pips"] = take_profit_pips
            logger.info(f"动态止损止盈: SL={stop_loss_pips}点, TP={take_profit_pips}点")

        # ---- 风险评估 ----
        def downgrade_to_hold(downgrade_reason: str):
            result["original_action"] = result.get("action")
            result["original_confidence"] = result.get("confidence")
            result["original_reason"] = result.get("reason")
            result["action"] = "HOLD"
            result["confidence"] = 0.0
            result["reason"] = f"风险拦截: {downgrade_reason}"
            result["risk_downgrade_reason"] = downgrade_reason
            result.pop("stop_loss_pips", None)
            result.pop("take_profit_pips", None)

        if action in ("BUY", "SELL"):
            if not self._risk_manager:
                logger.warning("[RM] 风险管理器不可用，信号降级为HOLD")
                downgrade_to_hold("风险管理器不可用")
            else:
                try:
                    current_price = (bid + ask) / 2 if bid > 0 and ask > 0 else 0
                    if current_price <= 0:
                        logger.warning("[RM] 当前价格无效，信号降级为HOLD")
                        downgrade_to_hold("当前价格无效")
                    else:
                        spread = ask - bid if bid > 0 and ask > 0 else 0
                        spread_pct = (spread / current_price * 10000) if current_price > 0 else 0

                        if spread_pct > 50:
                            logger.warning(f"[RM] 点差异常({spread_pct:.1f}点)，流动性不足，信号降级为HOLD")
                            downgrade_to_hold(f"点差异常: {spread_pct:.1f}点，流动性不足")
                        else:
                            assessment = self._risk_manager.assess_trade_risk(
                                symbol=symbol,
                                action=action,
                                confidence=confidence,
                                current_price=current_price,
                            )
                            result["risk_assessment"] = {
                                "risk_score": assessment.risk_score,
                                "risk_level": assessment.risk_level.value,
                                "recommended_position_size": assessment.recommended_position_size,
                                "recommended_stop_loss": assessment.recommended_stop_loss,
                                "recommended_take_profit": assessment.recommended_take_profit,
                                "risk_reward_ratio": assessment.risk_reward_ratio,
                                "warnings": assessment.warning_messages,
                            }

                            risk_reasons = []
                            blocking_risk_reason = self.get_blocking_risk_reason(assessment)

                            if assessment.risk_score >= 0.8:
                                risk_reasons.append(f"风险评分{assessment.risk_score:.2f}超过阈值0.8")
                            if assessment.risk_reward_ratio < 1.0:
                                risk_reasons.append(f"风险回报比{assessment.risk_reward_ratio:.2f}低于1:1")
                            if confidence < 0.6 and assessment.risk_score > 0.5:
                                risk_reasons.append(f"低置信度({confidence:.2f})+高风险({assessment.risk_score:.2f})")

                            if blocking_risk_reason:
                                logger.warning(f"[RM] 阻断性风险触发({blocking_risk_reason})，信号降级为HOLD")
                                downgrade_to_hold(f"阻断性风险: {blocking_risk_reason}")
                            elif len(risk_reasons) >= 2:
                                logger.warning(f"[RM] 多维度风险触发(原因: {'; '.join(risk_reasons)})，信号降级为HOLD")
                                downgrade_to_hold(f"多维度风险: {'; '.join(risk_reasons)}")
                            elif assessment.risk_score >= 0.8:
                                logger.warning(f"[RM] 风险评分过高({assessment.risk_score:.2f})，信号降级为HOLD")
                                downgrade_to_hold(f"风险评分{assessment.risk_score:.2f}超过阈值0.8")
                            elif assessment.risk_score > 0.6:
                                logger.warning(f"[WARN] 风险评分偏高({assessment.risk_score:.2f})，保留信号但添加警告")
                                result["risk_warnings"] = risk_reasons
                except Exception as e:
                    logger.error(f"[RM] 风险评估异常，信号降级为HOLD: {e}")
                    downgrade_to_hold(f"风险评估异常: {str(e)[:120]}")

        # ---- 缓存存储 ----
        primary_cache_key = get_cache_key(symbol, bid, ask)
        global_cache.set(primary_cache_key, result)

        fuzzy_cache_key = get_fuzzy_cache_key(symbol, bid, ask, tolerance_pips=0.5)
        if fuzzy_cache_key != primary_cache_key:
            global_cache.set(fuzzy_cache_key, result)

        logger.info(
            f"[AI] AI建议: {result.get('action', action)} | "
            f"置信度: {result.get('confidence', confidence):.2f}"
        )
        if reason:
            logger.info(f"分析原因: {reason[:80]}{'...' if len(reason) > 80 else ''}")

        return result
