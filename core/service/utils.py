# -*- coding: utf-8 -*-
"""
core/service/utils.py - God Class 拆分共享工具函数 (Phase 3)

从 mt5_ai_service.py 模块级函数迁移而来，供 AICoordinator / RequestProcessor 复用。
"""

from datetime import datetime
from typing import Dict, Any, Optional


# ---- 指标指纹 ----

_INDICATOR_FINGERPRINT_KEYS = ("rsi", "macd_main", "macd_signal", "ema50", "atr")


def build_indicator_fingerprint(indicators: Optional[Dict[str, Any]]) -> Optional[str]:
    """Build a compact fingerprint so cached signals cannot cross indicator states."""
    if not indicators:
        return None

    parts = []
    for key in _INDICATOR_FINGERPRINT_KEYS:
        if key not in indicators:
            continue
        try:
            parts.append(f"{key}:{float(indicators[key]):.4f}")
        except (TypeError, ValueError):
            parts.append(f"{key}:{indicators[key]}")
    return "|".join(parts) if parts else None


# ---- AI / 本地 reason 拼接 ----

def append_local_reason(ai_reason: str, local_reason: str) -> str:
    """拼接 AI 原因和本地指标校验原因，截断至 240 字符"""
    if not local_reason:
        return ai_reason
    if not ai_reason:
        return f"本地指标校验: {local_reason}"
    combined = f"{ai_reason} | 本地指标校验: {local_reason}"
    return combined[:240]


# ---- 阻断性风险关键词 ----

BLOCKING_RISK_KEYWORDS = (
    "保证金不足",
    "无法开仓",
    "保证金追缴",
    "立即平仓",
    "账户不允许",
    "交易被禁用",
    "风险评估失败",
    "margin insufficient",
    "not enough margin",
)


# ---- 时间工具 ----

def utc_now_iso() -> str:
    return datetime.now().isoformat()


def latency_ms(start_iso: Optional[str], end_iso: Optional[str] = None) -> Optional[int]:
    """计算 ISO 时间戳之间的毫秒差"""
    if not start_iso:
        return None
    try:
        start = datetime.fromisoformat(str(start_iso))
        end = datetime.fromisoformat(str(end_iso)) if end_iso else datetime.now()
        return max(0, int((end - start).total_seconds() * 1000))
    except Exception:
        return None


def total_latency_ms(
    request_created_at: Optional[str],
    request_read_at: Optional[str],
    end_iso: str,
) -> Optional[int]:
    """计算从创建到处理完成的总延迟"""
    read_latency = latency_ms(request_read_at, end_iso)
    created_latency = latency_ms(request_created_at, end_iso)
    if read_latency is None:
        return created_latency
    if created_latency is None:
        return read_latency
    if created_latency > read_latency + 300_000:  # >5min 视为异常
        return read_latency
    return created_latency


# ---- 被阻断原因推导 ----

def derive_blocked_by(result: Dict[str, Any], config) -> list:
    """从处理结果推导被阻断的原因列表"""
    blocked = []
    if not isinstance(result, dict):
        return blocked

    if result.get("action") != "HOLD":
        return blocked

    blocked.append("ACTION_HOLD")
    reason = str(result.get("reason", ""))
    validation = result.get("indicator_validation")
    if isinstance(validation, dict):
        blocks = validation.get("blocks") or []
        if any("pips>" in str(block) for block in blocks):
            blocked.append("SPREAD_TOO_HIGH")
        if validation.get("original_action") in ("BUY", "SELL") and validation.get("adjusted"):
            blocked.append("INDICATOR_QUALITY_GATE")

    confidence = result.get("original_confidence", result.get("confidence", 0.0))
    try:
        if float(confidence) < float(getattr(config, "MIN_CONFIDENCE", 0.5)):
            blocked.append("LOW_CONFIDENCE")
    except Exception:
        pass

    if "DeepSeek" in reason or "AI" in reason:
        if "不可用" in reason or "失败" in reason or "disabled" in reason.lower():
            blocked.append("AI_UNAVAILABLE")
    if result.get("risk_downgrade_reason"):
        blocked.append("RISK_DOWNGRADE")

    return list(dict.fromkeys(blocked))
