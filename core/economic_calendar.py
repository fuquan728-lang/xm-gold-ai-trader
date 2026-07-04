#!/usr/bin/env python3
"""
经济日历与黄金基本面数据模块

为AI决策管道提供实时经济事件、黄金ETF持仓、DXY关联等基本面数据，
解决LLM无法感知实时市场的盲区问题。

数据覆盖:
1. 经济日历事件（FOMC/NFP/CPI/GDP等）
2. 黄金ETF持仓变化（GLD/IAU）
3. 美元指数(DXY)与美债收益率
4. 市场时段效应（亚洲/欧洲/美洲盘）
"""

import json
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum

from core.logger import logger


class EventImpact(Enum):
    """经济事件影响等级"""
    LOW = 1       # 低影响
    MEDIUM = 2    # 中等影响
    HIGH = 3      # 高影响
    CRITICAL = 4  # 极端影响（FOMC/NFP级别）


class GoldBias(Enum):
    """事件对黄金的偏向"""
    BULLISH = "bullish"        # 利好黄金（避险/宽松/弱美元）
    BEARISH = "bearish"        # 利空黄金（风险偏好/紧缩/强美元）
    NEUTRAL = "neutral"        # 中性
    VOLATILE = "volatile"      # 高波动但方向不确定


@dataclass
class EconomicEvent:
    """经济事件"""
    name: str                    # 事件名称
    date: str                    # 日期 YYYY-MM-DD
    time: str                    # 时间 HH:MM (UTC+8)
    country: str                 # 国家
    impact: EventImpact          # 影响等级
    gold_bias: GoldBias          # 对黄金的偏向
    previous: Optional[str] = None   # 前值
    forecast: Optional[str] = None   # 预期值
    actual: Optional[str] = None     # 实际值
    notes: str = ""              # 备注

    def is_upcoming(self, hours_ahead: int = 72) -> bool:
        """判断事件是否在未来hours_ahead小时内"""
        try:
            dt_str = f"{self.date} {self.time}"
            event_dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M")
            now = datetime.now()
            delta = event_dt - now
            return timedelta(0) <= delta <= timedelta(hours=hours_ahead)
        except Exception:
            return False

    def happened_recently(self, hours_past: int = 24) -> bool:
        """判断事件是否在过去hours_past小时内发生"""
        try:
            dt_str = f"{self.date} {self.time}"
            event_dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M")
            now = datetime.now()
            delta = now - event_dt
            return timedelta(0) <= delta <= timedelta(hours=hours_past)
        except Exception:
            return False


# ==================== 2026年关键经济事件日历 ====================
# 黄金交易者最关注的美国经济事件
# 实际数据请定期更新

GOLD_CRITICAL_EVENTS_2026: List[EconomicEvent] = [
    # FOMC利率决议 (8次/年)
    EconomicEvent("FOMC利率决议", "2026-01-28", "03:00", "US", EventImpact.CRITICAL, GoldBias.VOLATILE, "4.25-4.50%", "4.25-4.50%", notes="点阵图+经济预测"),
    EconomicEvent("FOMC利率决议", "2026-03-18", "02:00", "US", EventImpact.CRITICAL, GoldBias.VOLATILE, "4.25-4.50%", "4.25-4.50%", notes="点阵图+经济预测"),
    EconomicEvent("FOMC利率决议", "2026-05-06", "02:00", "US", EventImpact.CRITICAL, GoldBias.VOLATILE, notes="点阵图+经济预测"),
    EconomicEvent("FOMC利率决议", "2026-06-17", "02:00", "US", EventImpact.CRITICAL, GoldBias.VOLATILE, notes="点阵图+经济预测"),
    EconomicEvent("FOMC利率决议", "2026-07-29", "02:00", "US", EventImpact.CRITICAL, GoldBias.VOLATILE, notes="点阵图+经济预测"),
    EconomicEvent("FOMC利率决议", "2026-09-16", "02:00", "US", EventImpact.CRITICAL, GoldBias.VOLATILE, notes="点阵图+经济预测"),
    EconomicEvent("FOMC利率决议", "2026-11-04", "03:00", "US", EventImpact.CRITICAL, GoldBias.VOLATILE, notes="点阵图+经济预测"),
    EconomicEvent("FOMC利率决议", "2026-12-16", "03:00", "US", EventImpact.CRITICAL, GoldBias.VOLATILE, notes="点阵图+经济预测"),

    # 非农就业报告 (每月第一个周五)
    EconomicEvent("非农就业报告", "2026-01-09", "21:30", "US", EventImpact.CRITICAL, GoldBias.VOLATILE),
    EconomicEvent("非农就业报告", "2026-02-06", "21:30", "US", EventImpact.CRITICAL, GoldBias.VOLATILE),
    EconomicEvent("非农就业报告", "2026-03-06", "21:30", "US", EventImpact.CRITICAL, GoldBias.VOLATILE),
    EconomicEvent("非农就业报告", "2026-04-03", "20:30", "US", EventImpact.CRITICAL, GoldBias.VOLATILE),
    EconomicEvent("非农就业报告", "2026-05-01", "20:30", "US", EventImpact.CRITICAL, GoldBias.VOLATILE),
    EconomicEvent("非农就业报告", "2026-06-05", "20:30", "US", EventImpact.CRITICAL, GoldBias.VOLATILE),
    EconomicEvent("非农就业报告", "2026-07-03", "20:30", "US", EventImpact.CRITICAL, GoldBias.VOLATILE),
    EconomicEvent("非农就业报告", "2026-08-07", "20:30", "US", EventImpact.CRITICAL, GoldBias.VOLATILE),
    EconomicEvent("非农就业报告", "2026-09-04", "20:30", "US", EventImpact.CRITICAL, GoldBias.VOLATILE),
    EconomicEvent("非农就业报告", "2026-10-02", "20:30", "US", EventImpact.CRITICAL, GoldBias.VOLATILE),
    EconomicEvent("非农就业报告", "2026-11-06", "21:30", "US", EventImpact.CRITICAL, GoldBias.VOLATILE),
    EconomicEvent("非农就业报告", "2026-12-04", "21:30", "US", EventImpact.CRITICAL, GoldBias.VOLATILE),

    # CPI通胀数据 (每月中旬)
    EconomicEvent("CPI通胀数据", "2026-01-14", "21:30", "US", EventImpact.HIGH, GoldBias.BULLISH, notes="高CPI利空美元利好黄金"),
    EconomicEvent("CPI通胀数据", "2026-02-12", "21:30", "US", EventImpact.HIGH, GoldBias.BULLISH),
    EconomicEvent("CPI通胀数据", "2026-03-11", "20:30", "US", EventImpact.HIGH, GoldBias.BULLISH),
    EconomicEvent("CPI通胀数据", "2026-04-14", "20:30", "US", EventImpact.HIGH, GoldBias.BULLISH),
    EconomicEvent("CPI通胀数据", "2026-05-13", "20:30", "US", EventImpact.HIGH, GoldBias.BULLISH),
    EconomicEvent("CPI通胀数据", "2026-06-10", "20:30", "US", EventImpact.HIGH, GoldBias.BULLISH),
    EconomicEvent("CPI通胀数据", "2026-07-15", "20:30", "US", EventImpact.HIGH, GoldBias.BULLISH),
    EconomicEvent("CPI通胀数据", "2026-08-12", "20:30", "US", EventImpact.HIGH, GoldBias.BULLISH),
    EconomicEvent("CPI通胀数据", "2026-09-15", "20:30", "US", EventImpact.HIGH, GoldBias.BULLISH),
    EconomicEvent("CPI通胀数据", "2026-10-14", "20:30", "US", EventImpact.HIGH, GoldBias.BULLISH),
    EconomicEvent("CPI通胀数据", "2026-11-12", "21:30", "US", EventImpact.HIGH, GoldBias.BULLISH),
    EconomicEvent("CPI通胀数据", "2026-12-11", "21:30", "US", EventImpact.HIGH, GoldBias.BULLISH),

    # GDP数据
    EconomicEvent("GDP季率初值", "2026-01-29", "21:30", "US", EventImpact.HIGH, GoldBias.NEUTRAL),
    EconomicEvent("GDP季率初值", "2026-04-30", "20:30", "US", EventImpact.HIGH, GoldBias.NEUTRAL),
    EconomicEvent("GDP季率初值", "2026-07-30", "20:30", "US", EventImpact.HIGH, GoldBias.NEUTRAL),
    EconomicEvent("GDP季率初值", "2026-10-29", "20:30", "US", EventImpact.HIGH, GoldBias.NEUTRAL),
]


# ==================== 经济日历管理器 ====================

class EconomicCalendar:
    """经济日历管理器"""

    def __init__(self):
        self.events = list(GOLD_CRITICAL_EVENTS_2026)
        logger.info(f"[ECAL] Economic calendar initialized: {len(self.events)} critical events loaded")

    def get_upcoming_events(self, hours_ahead: int = 72) -> List[EconomicEvent]:
        """获取即将发生的经济事件"""
        upcoming = [e for e in self.events if e.is_upcoming(hours_ahead)]
        upcoming.sort(key=lambda e: f"{e.date}{e.time}")
        return upcoming

    def get_recent_events(self, hours_past: int = 24) -> List[EconomicEvent]:
        """获取近期已发生的经济事件"""
        recent = [e for e in self.events if e.happened_recently(hours_past)]
        recent.sort(key=lambda e: f"{e.date}{e.time}", reverse=True)
        return recent

    def get_events_near_date(self, target_date: str, window_days: int = 3) -> List[EconomicEvent]:
        """获取指定日期附近的事件"""
        try:
            target = datetime.strptime(target_date, "%Y-%m-%d")
            result = []
            for event in self.events:
                try:
                    event_date = datetime.strptime(event.date, "%Y-%m-%d")
                    if abs((event_date - target).days) <= window_days:
                        result.append(event)
                except ValueError:
                    continue
            return result
        except ValueError:
            return []

    def get_critical_events_today(self) -> List[EconomicEvent]:
        """获取今天的重大事件"""
        today = datetime.now().strftime("%Y-%m-%d")
        return [e for e in self.events if e.date == today and e.impact.value >= EventImpact.HIGH.value]

    def get_risk_advisory(self) -> Dict[str, Any]:
        """
        生成当前的风险建议
        
        基于即将发生的事件评估风险级别：
        - 如果有FOMC/NFP在24h内 → 高风险，建议减仓或观望
        - 如果有CPI/GDP在24h内 → 中高风险
        - 如果有重要事件在72h内 → 提示注意
        """
        advisory = {
            "risk_level": "normal",
            "advisory_text": "无重大事件，正常交易",
            "events_24h": [],
            "events_72h": [],
            "recommendation": "trade_as_normal"
        }

        events_24h = self.get_upcoming_events(24)
        events_72h = self.get_upcoming_events(72)

        advisory["events_24h"] = [{"name": e.name, "time": f"{e.date} {e.time}",
                                    "impact": e.impact.name} for e in events_24h]
        advisory["events_72h"] = [{"name": e.name, "time": f"{e.date} {e.time}",
                                    "impact": e.impact.name} for e in events_72h]

        if events_24h:
            critical_in_24h = [e for e in events_24h if e.impact == EventImpact.CRITICAL]
            if critical_in_24h:
                advisory["risk_level"] = "high"
                advisory["advisory_text"] = f"CRITICAL event in 24h: {critical_in_24h[0].name}"
                advisory["recommendation"] = "reduce_exposure_or_hold"
            else:
                high_in_24h = [e for e in events_24h if e.impact >= EventImpact.HIGH]
                if high_in_24h:
                    advisory["risk_level"] = "elevated"
                    advisory["advisory_text"] = f"High-impact event in 24h: {high_in_24h[0].name}"
                    advisory["recommendation"] = "trade_with_caution"
        elif events_72h:
            critical_in_72h = [e for e in events_72h if e.impact == EventImpact.CRITICAL]
            if critical_in_72h:
                advisory["risk_level"] = "elevated"
                advisory["advisory_text"] = f"CRITICAL event upcoming: {critical_in_72h[0].name} ({critical_in_72h[0].date})"
                advisory["recommendation"] = "plan_position_management"

        return advisory


# ==================== 市场时段分析 ====================

class MarketSessionAnalyzer:
    """市场时段分析器"""

    # 时段定义 (UTC+8 北京时间)
    SESSIONS = {
        "asia": {"name": "亚洲盘", "start_hour": 7, "end_hour": 15, "volatility": "low",
                 "character": "区间震荡为主，流动性偏低"},
        "europe": {"name": "欧洲盘", "start_hour": 15, "end_hour": 23, "volatility": "medium",
                   "character": "趋势启动，突破行情常见"},
        "america": {"name": "美洲盘", "start_hour": 20, "end_hour": 4, "volatility": "high",
                    "character": "高波动，数据行情集中"},
        "overlap_asia_eu": {"name": "亚欧重叠", "start_hour": 14, "end_hour": 16, "volatility": "medium",
                           "character": "波动上升期"},
        "overlap_eu_us": {"name": "欧美重叠", "start_hour": 20, "end_hour": 23, "volatility": "high",
                         "character": "最大波动时段，流动性最强"},
        "low_liquidity": {"name": "低流动性", "start_hour": 4, "end_hour": 7, "volatility": "low",
                          "character": "亚洲盘前，点差可能扩大"}
    }

    @classmethod
    def get_current_session(cls) -> Dict[str, str]:
        """获取当前市场时段"""
        now = datetime.now()
        current_hour = now.hour

        for session_key, session_data in cls.SESSIONS.items():
            start = session_data["start_hour"]
            end = session_data["end_hour"]
            if start < end:
                if start <= current_hour < end:
                    return {"key": session_key, **session_data}
            else:  # 跨午夜时段
                if current_hour >= start or current_hour < end:
                    return {"key": session_key, **session_data}

        return {"key": "unknown", "name": "未知时段", "volatility": "unknown", "character": ""}

    @classmethod
    def get_volatility_multiplier(cls) -> float:
        """获取当前时段波动率乘数（用于调整止损止盈）"""
        session = cls.get_current_session()
        vol = session.get("volatility", "medium")
        multiplier = {"low": 0.85, "medium": 1.0, "high": 1.25}
        return multiplier.get(vol, 1.0)


# ==================== AI提示词上下文构建器 ====================

class AIPromptContextBuilder:
    """
    AI提示词基本面上下文构建器
    
    将所有经济/市场数据编译为简洁的提示词片段，
    注入到AI引擎的决策提示词中。
    """

    def __init__(self):
        self.calendar = EconomicCalendar()
        self.session_analyzer = MarketSessionAnalyzer()

    def build_economic_context(self) -> str:
        """构建经济基本面上下文"""
        parts = []

        # 1. 市场时段
        session = self.session_analyzer.get_current_session()
        parts.append(f"[市场时段] {session['name']} ({session['character']})")

        # 2. 即将发生的关键事件
        upcoming_24h = self.calendar.get_upcoming_events(24)
        if upcoming_24h:
            events_text = "; ".join(
                f"{e.name}({e.date} {e.time}, {e.impact.name})"
                for e in upcoming_24h[:3]
            )
            parts.append(f"[预警] 24h内关键事件: {events_text}")
            parts.append("  → 建议: 控制仓位，关注事件结果")

        upcoming_72h = self.calendar.get_upcoming_events(72)
        if upcoming_72h:
            far_events = [e for e in upcoming_72h if e not in upcoming_24h]
            if far_events:
                parts.append(f"[关注] 72h内事件: {far_events[0].name}({far_events[0].date})")

        # 3. 刚发生的事件
        recent = self.calendar.get_recent_events(8)
        if recent:
            parts.append(f"[最近事件] {recent[0].name}于{recent[0].date}已公布")

        # 4. 风险顾问
        advisory = self.calendar.get_risk_advisory()
        if advisory["risk_level"] != "normal":
            parts.append(f"[风险提示] {advisory['advisory_text']}")

        # 5. 黄金基本面因素框架
        parts.append(
            "[黄金基本面] 核心因子: (1)美联储利率预期→与实际利率负相关 "
            "(2)美元指数(DXY)→负相关 (3)地缘政治→避险需求 "
            "(4)实际通胀→保值需求 (5)央行购金→需求支撑"
        )

        return "\n".join(parts)

    def build_full_context(self, include_details: bool = False) -> Dict[str, Any]:
        """构建完整的基本面分析上下文"""
        session = self.session_analyzer.get_current_session()
        advisory = self.calendar.get_risk_advisory()
        upcoming = self.calendar.get_upcoming_events(72)

        context = {
            "session": {
                "name": session["name"],
                "volatility": session["volatility"],
                "volatility_multiplier": self.session_analyzer.get_volatility_multiplier()
            },
            "risk_advisory": advisory,
            "upcoming_events_count": len(upcoming),
            "critical_events_today": len(self.calendar.get_critical_events_today()),
            "prompt_context": self.build_economic_context()
        }

        if include_details:
            context["upcoming_events"] = [
                {"name": e.name, "datetime": f"{e.date} {e.time}",
                 "impact": e.impact.name, "gold_bias": e.gold_bias.value}
                for e in upcoming[:5]
            ]

        return context


# ==================== 黄金ETF/DXY数据模拟接口 ====================
# 未来可集成实时API: Alpha Vantage, Yahoo Finance, Investing.com

class GoldMacroDataProvider:
    """
    黄金宏观数据提供者
    
    当前为静态参考数据模式，未来可接入:
    - Alpha Vantage API (DXY, US10Y)
    - 黄金ETF持仓数据 (GLD holdings)
    - CFTC持仓报告 (COT report)
    """

    # DXY关键水平
    DXY_SUPPORT = [100.0, 102.0, 104.0]
    DXY_RESISTANCE = [106.0, 108.0, 110.0]

    # 美债收益率关键水平
    US10Y_SUPPORT = [3.80, 4.00]
    US10Y_RESISTANCE = [4.50, 4.80]

    @classmethod
    def get_gold_macro_summary(cls) -> Dict[str, Any]:
        """
        获取黄金宏观环境总结
        
        Returns:
            包含DXY、美债、ETF、央行等维度的总结
        """
        return {
            "factors": [
                {
                    "factor": "美联储政策",
                    "status": "data_dependent",
                    "gold_impact": "hawkish→bearish, dovish→bullish",
                    "weight": 0.35
                },
                {
                    "factor": "美元指数(DXY)",
                    "status": "monitor",
                    "gold_impact": "inverse correlation (-0.6 to -0.8)",
                    "key_levels": {"support": cls.DXY_SUPPORT, "resistance": cls.DXY_RESISTANCE},
                    "weight": 0.25
                },
                {
                    "factor": "美债收益率(US10Y)",
                    "status": "monitor",
                    "gold_impact": "inverse correlation (-0.3 to -0.5)",
                    "key_levels": {"support": cls.US10Y_SUPPORT, "resistance": cls.US10Y_RESISTANCE},
                    "weight": 0.20
                },
                {
                    "factor": "央行购金",
                    "status": "structural_support",
                    "gold_impact": "中国/印度/土耳其央行持续购金，长期利好",
                    "weight": 0.10
                },
                {
                    "factor": "地缘政治",
                    "status": "variable",
                    "gold_impact": "避险情绪→短期利好黄金",
                    "weight": 0.10
                }
            ],
            "summary": (
                "黄金在2026年宏观环境中受多重因素影响。"
                "美联储降息周期 → 利空美元利好黄金。"
                "央行持续购金提供结构性支撑。"
                "关注FOMC会议和非农数据对短期走势的影响。"
            )
        }

    @classmethod
    def build_prompt_section(cls) -> str:
        """构建AI提示词的黄金宏观部分"""
        summary = cls.get_gold_macro_summary()
        lines = ["[黄金宏观环境]"]
        for f in summary["factors"]:
            lines.append(f"  {f['factor']}(权重{f['weight']:.0%}): {f['gold_impact']}")
        lines.append(f"  {summary['summary']}")
        return "\n".join(lines)


# ==================== 全局实例 ====================

_economic_calendar: Optional[EconomicCalendar] = None
_prompt_builder: Optional[AIPromptContextBuilder] = None


def get_economic_calendar() -> EconomicCalendar:
    global _economic_calendar
    if _economic_calendar is None:
        _economic_calendar = EconomicCalendar()
    return _economic_calendar


def get_prompt_context_builder() -> AIPromptContextBuilder:
    global _prompt_builder
    if _prompt_builder is None:
        _prompt_builder = AIPromptContextBuilder()
    return _prompt_builder


def get_economic_context_for_ai() -> str:
    """快捷函数：获取AI提示词用的经济上下文"""
    builder = get_prompt_context_builder()
    economic = builder.build_economic_context()
    macro = GoldMacroDataProvider.build_prompt_section()
    return f"{economic}\n\n{macro}"
