from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.backtest_baseline_report import load_backtest_inputs
from scripts.dry_run_campaign_report import session_name
from scripts.live_dry_run_signal_journal import DEFAULT_PARAMETER_REPORT, REASON_NO_ACTIONABLE_SIGNAL, selected_signal_config
from src.broker.mt5_client import MT5ClientError
from src.logging_config import configure_logging
from src.strategy.baseline_signal import BaselineSignalConfig, BaselineSignalGenerator, TradeSignal


PROJECT = "xm-gold-ai-trader"
MODE = "historical_signal_replay"
DEFAULT_JOURNAL_DIR = Path("logs/historical_signal_replay")

REASON_NO_HISTORICAL_DATA = "NO_HISTORICAL_DATA"
REASON_SIGNAL_SCARCITY = "SIGNAL_SCARCITY"


def main() -> int:
    args = parse_args()
    logger = configure_logging(logger_name="historical_signal_replay")

    try:
        import pandas as pd
    except ImportError as exc:
        raise RuntimeError("pandas is required for historical signal replay. Install requirements.txt.") from exc

    try:
        bars, symbol_info, data_source = load_backtest_inputs(args, pd)
    except MT5ClientError as exc:
        logger.error("%s", exc)
        print(str(exc), file=sys.stderr)
        return 1

    if args.bars and len(bars) > args.bars:
        bars = bars.tail(args.bars).reset_index(drop=True)
        data_source = {**data_source, "bars_replayed_from_tail": int(args.bars)}

    signal_config, parameter_source = selected_signal_config(args)
    report = run_historical_signal_replay(
        bars=bars,
        symbol=args.symbol,
        timeframe=args.timeframe,
        symbol_info=symbol_info,
        signal_config=signal_config,
        selected_parameters_source=parameter_source,
        data_source=data_source,
        include_observations=args.include_observations,
    )

    if args.write_journal:
        journal_report = report
        if "observations" not in journal_report:
            journal_report = {
                **report,
                "observations": replay_observations(
                    bars=bars,
                    symbol=args.symbol,
                    timeframe=args.timeframe,
                    signal_config=signal_config,
                    symbol_info=symbol_info,
                ),
            }
        report["journal_path"] = write_replay_journal(Path(args.journal_dir), journal_report)

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True, default=str))
    else:
        print_summary(report)
    return 0


def run_historical_signal_replay(
    *,
    bars: Any,
    symbol: str,
    timeframe: str,
    symbol_info: Mapping[str, Any],
    signal_config: BaselineSignalConfig,
    selected_parameters_source: str,
    data_source: Mapping[str, Any] | None = None,
    include_observations: bool = False,
) -> dict[str, Any]:
    report: dict[str, Any] = {
        "project": PROJECT,
        "mode": MODE,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "symbol": symbol,
        "timeframe": timeframe,
        "status": "OK",
        "reason_codes": [],
        "selected_parameters": asdict(signal_config),
        "selected_parameters_source": selected_parameters_source,
        "data_source": dict(data_source or {}),
        "total_bars_replayed": int(len(bars)),
        "total_observations": 0,
        "signal_count": 0,
        "block_count": 0,
        "actionable_signal_rate": 0.0,
        "buy_signal_count": 0,
        "sell_signal_count": 0,
        "no_actionable_signal_count": 0,
        "spread_assumptions": spread_assumptions(bars, symbol_info),
        "orders_sent": 0,
        "order_check_called": False,
        "order_send_called": False,
        "diagnostics": empty_diagnostics(),
        "hard_safety": {
            "ai_model_trading": False,
            "order_check": False,
            "order_send": False,
            "martingale": False,
            "grid": False,
            "lot_increase_after_loss": False,
        },
    }
    if len(bars) == 0:
        report["status"] = "NO_DATA"
        report["reason_codes"] = [REASON_NO_HISTORICAL_DATA]
        if include_observations:
            report["observations"] = []
        return report

    observations = replay_observations(
        bars=bars,
        symbol=symbol,
        timeframe=timeframe,
        signal_config=signal_config,
        symbol_info=symbol_info,
    )
    metrics = summarize_observations(observations, signal_config)
    report.update(metrics)
    if include_observations:
        report["observations"] = observations
    return report


def replay_observations(
    *,
    bars: Any,
    symbol: str,
    timeframe: str,
    signal_config: BaselineSignalConfig,
    symbol_info: Mapping[str, Any],
    signal_generator: Any | None = None,
) -> list[dict[str, Any]]:
    generator = signal_generator or BaselineSignalGenerator(signal_config)
    atr_values = average_true_range(bars, signal_config.atr_period)
    regime_thresholds = volatility_thresholds(atr_values)
    observations: list[dict[str, Any]] = []
    for bar_index in range(len(bars)):
        visible_bars = bars.iloc[: bar_index + 1].copy()
        latest_bar = bars.iloc[bar_index]
        signal = generator.generate(visible_bars, symbol)
        signal_payload = signal_to_dict(signal)
        is_actionable = signal.is_actionable
        spread_points = spread_points_for_bar(latest_bar, symbol_info)
        volatility_regime = classify_volatility(atr_values.iloc[bar_index], regime_thresholds)
        observations.append(
            {
                "bar_index": bar_index,
                "bars_visible": int(len(visible_bars)),
                "latest_closed_bar_time": str(latest_bar["time"]),
                "timeframe": timeframe,
                "symbol": symbol,
                "final_decision": "SIGNAL" if is_actionable else "BLOCK",
                "reason_codes": [] if is_actionable else [REASON_NO_ACTIONABLE_SIGNAL],
                "reasons": [] if is_actionable else [f"{REASON_NO_ACTIONABLE_SIGNAL}: {signal.reason}"],
                "signal": signal_payload,
                "spread_points": spread_points,
                "session": session_name(latest_bar["time"]),
                "volatility_regime": volatility_regime,
                "atr": none_if_nan(atr_values.iloc[bar_index]),
                "orders_sent": 0,
                "order_check_called": False,
                "order_send_called": False,
            }
        )
    return observations


def summarize_observations(observations: list[dict[str, Any]], signal_config: BaselineSignalConfig) -> dict[str, Any]:
    total = len(observations)
    signals = [obs for obs in observations if obs["final_decision"] == "SIGNAL"]
    buy_count = sum(1 for obs in signals if obs["signal"]["side"] == "BUY")
    sell_count = sum(1 for obs in signals if obs["signal"]["side"] == "SELL")
    no_actionable_count = sum(1 for obs in observations if REASON_NO_ACTIONABLE_SIGNAL in obs["reason_codes"])
    reason_counts: dict[str, int] = {}
    for obs in observations:
        for code in obs["reason_codes"]:
            reason_counts[code] = reason_counts.get(code, 0) + 1

    signal_indices = [int(obs["bar_index"]) for obs in signals]
    average_gap = average_bars_between(signal_indices)
    longest_streak = longest_no_signal_streak(observations)
    signal_scarcity = total >= (max(signal_config.slow_sma, signal_config.atr_period) + 2) and len(signals) == 0
    reason_codes = [REASON_SIGNAL_SCARCITY] if signal_scarcity else []
    if signal_scarcity:
        reason_counts[REASON_SIGNAL_SCARCITY] = 1

    return {
        "status": "OK",
        "reason_codes": reason_codes,
        "total_observations": total,
        "signal_count": len(signals),
        "block_count": total - len(signals),
        "actionable_signal_rate": len(signals) / total if total else 0.0,
        "buy_signal_count": buy_count,
        "sell_signal_count": sell_count,
        "BUY_count": buy_count,
        "SELL_count": sell_count,
        "no_actionable_signal_count": no_actionable_count,
        "NO_ACTIONABLE_SIGNAL_count": no_actionable_count,
        "reason_code_counts": dict(sorted(reason_counts.items())),
        "diagnostics": {
            "average_bars_between_signals": average_gap,
            "longest_no_signal_streak": longest_streak,
            "signal_scarcity_detected": signal_scarcity,
            "signals_by_session": signals_by_group(observations, "session"),
            "signals_by_volatility_regime": signals_by_group(observations, "volatility_regime"),
            "observations_by_volatility_regime": observations_by_group(observations, "volatility_regime"),
        },
    }


def average_true_range(bars: Any, period: int) -> Any:
    previous_close = bars["close"].shift(1)
    true_range = bars[["high", "low"]].assign(
        high_close=(bars["high"] - previous_close).abs(),
        low_close=(bars["low"] - previous_close).abs(),
        high_low=bars["high"] - bars["low"],
    )[["high_close", "low_close", "high_low"]].max(axis=1)
    return true_range.rolling(period).mean()


def volatility_thresholds(atr_values: Any) -> dict[str, float | None]:
    clean = atr_values.dropna()
    if len(clean) == 0:
        return {"low_max": None, "medium_max": None}
    return {
        "low_max": float(clean.quantile(1 / 3)),
        "medium_max": float(clean.quantile(2 / 3)),
    }


def classify_volatility(value: Any, thresholds: Mapping[str, float | None]) -> str:
    if value != value:
        return "unknown"
    low_max = thresholds.get("low_max")
    medium_max = thresholds.get("medium_max")
    if low_max is None or medium_max is None:
        return "unknown"
    numeric = float(value)
    if numeric <= low_max:
        return "low"
    if numeric <= medium_max:
        return "medium"
    return "high"


def spread_assumptions(bars: Any, symbol_info: Mapping[str, Any]) -> dict[str, Any]:
    if len(bars) == 0:
        return {"source": "none", "average_spread_points": None, "max_spread_points": None}
    if "spread" in bars.columns:
        spreads = [float(value) for value in bars["spread"].dropna()]
        source = "bar_spread_column"
    else:
        spreads = [float(symbol_info.get("spread", 0.0) or 0.0)] * len(bars)
        source = "symbol_info_spread"
    return {
        "source": source,
        "average_spread_points": sum(spreads) / len(spreads) if spreads else None,
        "max_spread_points": max(spreads) if spreads else None,
        "min_spread_points": min(spreads) if spreads else None,
    }


def spread_points_for_bar(bar: Any, symbol_info: Mapping[str, Any]) -> float:
    if "spread" in bar and bar["spread"] == bar["spread"]:
        return float(bar["spread"])
    return float(symbol_info.get("spread", 0.0) or 0.0)


def average_bars_between(signal_indices: list[int]) -> float | None:
    if len(signal_indices) < 2:
        return None
    gaps = [current - previous for previous, current in zip(signal_indices, signal_indices[1:])]
    return sum(gaps) / len(gaps)


def longest_no_signal_streak(observations: list[dict[str, Any]]) -> int:
    longest = 0
    current = 0
    for obs in observations:
        if obs["final_decision"] == "SIGNAL":
            longest = max(longest, current)
            current = 0
        else:
            current += 1
    return max(longest, current)


def signals_by_group(observations: list[dict[str, Any]], key: str) -> dict[str, dict[str, int]]:
    groups = {name: empty_signal_group() for name in group_names(key)}
    for obs in observations:
        group = str(obs.get(key, "unknown"))
        groups.setdefault(group, empty_signal_group())
        if obs["final_decision"] != "SIGNAL":
            continue
        side = obs["signal"]["side"]
        groups[group]["total"] += 1
        if side == "BUY":
            groups[group]["BUY"] += 1
        if side == "SELL":
            groups[group]["SELL"] += 1
    return groups


def observations_by_group(observations: list[dict[str, Any]], key: str) -> dict[str, int]:
    groups = {name: 0 for name in group_names(key)}
    for obs in observations:
        group = str(obs.get(key, "unknown"))
        groups[group] = groups.get(group, 0) + 1
    return groups


def group_names(key: str) -> tuple[str, ...]:
    if key == "session":
        return ("Asia", "London", "NewYork", "OffHours")
    if key == "volatility_regime":
        return ("low", "medium", "high", "unknown")
    return ("unknown",)


def empty_signal_group() -> dict[str, int]:
    return {"total": 0, "BUY": 0, "SELL": 0}


def empty_diagnostics() -> dict[str, Any]:
    return {
        "average_bars_between_signals": None,
        "longest_no_signal_streak": 0,
        "signal_scarcity_detected": False,
        "signals_by_session": signals_by_group([], "session"),
        "signals_by_volatility_regime": signals_by_group([], "volatility_regime"),
        "observations_by_volatility_regime": observations_by_group([], "volatility_regime"),
    }


def signal_to_dict(signal: TradeSignal) -> dict[str, Any]:
    return {
        "symbol": signal.symbol,
        "side": signal.side,
        "confidence": signal.confidence,
        "entry_price": signal.entry_price,
        "stop_loss_price": signal.stop_loss_price,
        "take_profit_price": signal.take_profit_price,
        "reason": signal.reason,
    }


def none_if_nan(value: Any) -> float | None:
    if value != value:
        return None
    return float(value)


def write_replay_journal(journal_dir: Path, report: Mapping[str, Any]) -> str:
    journal_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    path = journal_dir / f"historical_signal_replay_{timestamp}.json"
    path.write_text(json.dumps(report, indent=2, sort_keys=True, default=str), encoding="utf-8")
    return str(path)


def print_summary(report: Mapping[str, Any]) -> None:
    print("xm-gold-ai-trader historical signal replay")
    print(f"symbol/timeframe: {report['symbol']} {report['timeframe']}")
    print(f"status: {report['status']}")
    print(f"bars replayed: {report['total_bars_replayed']}")
    print(f"observations: {report['total_observations']}")
    print(f"signals: {report['signal_count']}")
    print(f"BUY/SELL: {report['buy_signal_count']}/{report['sell_signal_count']}")
    print(f"actionable signal rate: {report['actionable_signal_rate']:.4f}")
    print(f"longest no-signal streak: {report['diagnostics']['longest_no_signal_streak']}")
    print("orders_sent: 0")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Replay historical GOLD_ M15 bars as dry-run signal observations.")
    parser.add_argument("--symbol", default=os.getenv("XM_GOLD_SYMBOL", "GOLD_"))
    parser.add_argument("--timeframe", default="M15", choices=("M1", "M5", "M15", "M30", "H1", "H4", "D1"))
    parser.add_argument("--input", default="data/gold_m15.csv")
    parser.add_argument("--bars", type=int, default=5_000)
    parser.add_argument("--parameter-report", default=str(DEFAULT_PARAMETER_REPORT))
    parser.add_argument("--fallback-fast-sma", type=int, default=10)
    parser.add_argument("--fallback-slow-sma", type=int, default=40)
    parser.add_argument("--atr-period", type=int, default=14)
    parser.add_argument("--fallback-atr-stop-multiplier", type=float, default=1.5)
    parser.add_argument("--fallback-reward-risk-ratio", type=float, default=1.5)
    parser.add_argument("--write-journal", action="store_true")
    parser.add_argument("--journal-dir", default=str(DEFAULT_JOURNAL_DIR))
    parser.add_argument("--include-observations", action="store_true")
    parser.add_argument("--terminal-path", default=os.getenv("XM_MT5_TERMINAL_PATH"))
    parser.add_argument("--login", type=int, default=_optional_int(os.getenv("XM_MT5_LOGIN")))
    parser.add_argument("--password", default=os.getenv("XM_MT5_PASSWORD"))
    parser.add_argument("--server", default=os.getenv("XM_MT5_SERVER"))
    parser.add_argument("--timeout-ms", type=int, default=60_000)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def _optional_int(value: str | None) -> int | None:
    return int(value) if value else None


if __name__ == "__main__":
    raise SystemExit(main())
