from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.backtest_baseline_report import load_symbol_metadata, normalize_bars, sha256_file
from scripts.dry_run_signal_report import load_dry_run_journals, numeric_or_none
from scripts.live_dry_run_signal_journal import DEFAULT_PARAMETER_REPORT
from src.broker.order_executor import TradingConfig, load_trading_config
from src.strategy.baseline_signal import BaselineSignalConfig
from src.strategy.risk_manager import (
    AccountState,
    REASON_LOT_BELOW_VOLUME_MIN,
    RiskConfig,
    RiskDecision,
    RiskManager,
    SymbolSpec,
    TradeRiskRequest,
)


PROJECT = "xm-gold-ai-trader"
MODE = "strategy_hypothesis_lab"
REASON_NO_HISTORICAL_DATA = "NO_HISTORICAL_DATA"
REASON_SYMBOL_INFO_UNAVAILABLE = "SYMBOL_INFO_UNAVAILABLE"
REASON_NO_ACTIONABLE_SIGNAL = "NO_ACTIONABLE_SIGNAL"


@dataclass(frozen=True, slots=True)
class HypothesisDefinition:
    name: str
    family: str
    description: str
    signal_mode: str
    signal_config: BaselineSignalConfig
    risk_gated: bool = True


@dataclass(frozen=True, slots=True)
class Candidate:
    side: str
    entry_price: float
    stop_loss_price: float
    take_profit_price: float
    signal_bar_index: int
    entry_bar_index: int
    signal_time: str
    reason: str
    stop_distance_points: float


def main() -> int:
    args = parse_args()
    try:
        import pandas as pd
    except ImportError as exc:
        raise RuntimeError("pandas is required for strategy hypothesis lab. Install requirements.txt.") from exc

    report = build_report_from_args(args, pd)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True, default=str))
    else:
        print_summary(report)
    return 0


def build_report_from_args(args: argparse.Namespace, pd: Any) -> dict[str, Any]:
    input_path = Path(args.input)
    bars = load_bars(input_path, pd)
    if args.bars and len(bars) > args.bars:
        bars = bars.tail(args.bars).reset_index(drop=True)

    journal_dir = Path(args.dry_run_journal_dir)
    symbol_info = load_symbol_info(
        input_path=input_path,
        explicit_path=Path(args.symbol_info) if args.symbol_info else None,
        journal_dir=journal_dir,
    )
    trading_config = load_or_default_trading_config(Path(args.config))
    selected_config, selected_source = selected_signal_config_from_report(
        Path(args.parameter_report),
        fallback=BaselineSignalConfig(
            fast_sma=args.fallback_fast_sma,
            slow_sma=args.fallback_slow_sma,
            atr_period=args.atr_period,
            atr_stop_multiplier=args.fallback_atr_stop_multiplier,
            reward_risk_ratio=args.fallback_reward_risk_ratio,
        ),
    )
    hypotheses = build_hypotheses(selected_config)
    return run_strategy_hypothesis_lab(
        bars=bars,
        symbol=args.symbol,
        timeframe=args.timeframe,
        symbol_info=symbol_info,
        trading_config=trading_config,
        hypotheses=hypotheses,
        account_equity=args.account_equity,
        selected_parameters_source=selected_source,
        data_source={
            "kind": "csv",
            "input": str(input_path),
            "input_sha256": sha256_file(input_path) if input_path.exists() else None,
            "bars_used": int(len(bars)),
            "dry_run_journal_dir": str(journal_dir),
        },
    )


def run_strategy_hypothesis_lab(
    *,
    bars: Any,
    symbol: str,
    timeframe: str,
    symbol_info: Mapping[str, Any] | None,
    trading_config: TradingConfig | None = None,
    hypotheses: list[HypothesisDefinition] | None = None,
    account_equity: float = 1_000.0,
    selected_parameters_source: str = "provided",
    data_source: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    config = trading_config or TradingConfig()
    report: dict[str, Any] = {
        "project": PROJECT,
        "mode": MODE,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "symbol": symbol,
        "timeframe": timeframe,
        "status": "OK",
        "final_decision": "PASS",
        "reason_codes": [],
        "reasons": [],
        "orders_sent": 0,
        "order_check_called": False,
        "order_send_called": False,
        "hypothetical_only": True,
        "production_strategy_unchanged": True,
        "ai_annotation_read_only": True,
        "selected_parameters_source": selected_parameters_source,
        "data_source": dict(data_source or {}),
        "account_equity_assumption": account_equity,
        "risk_config": asdict(config.risk),
        "execution_config": asdict(config.execution),
        "hypotheses": [],
        "comparison_against_current_baseline": [],
        "notes": [
            "Offline research only; results are hypothetical and are not used for trading.",
            "No order_check or order_send is called.",
            "Production strategy defaults, safety gates, and order routing are unchanged.",
            "No AI model trading is used.",
            "No martingale, grid, or automatic lot increase after loss is modeled.",
        ],
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
        report["final_decision"] = "WARN"
        report["reason_codes"] = [REASON_NO_HISTORICAL_DATA]
        report["reasons"] = [f"{REASON_NO_HISTORICAL_DATA}: no historical bars available"]
        return report
    if symbol_info is None:
        report["status"] = "NO_SYMBOL_INFO"
        report["final_decision"] = "WARN"
        report["reason_codes"] = [REASON_SYMBOL_INFO_UNAVAILABLE]
        report["reasons"] = [f"{REASON_SYMBOL_INFO_UNAVAILABLE}: no collected symbol_info metadata or dry-run journal symbol info found"]
        return report

    spec = SymbolSpec.from_mt5(symbol_info)
    spec.validate()
    rows = [
        evaluate_hypothesis(
            bars=bars,
            symbol=symbol,
            hypothesis=hypothesis,
            symbol_info=dict(symbol_info),
            risk_config=config.risk,
            account_equity=account_equity,
        )
        for hypothesis in (hypotheses or build_hypotheses(BaselineSignalConfig()))
    ]
    report["hypotheses"] = rows
    report["comparison_against_current_baseline"] = compare_against_baseline(rows)
    report["summary"] = {
        "hypothesis_count": len(rows),
        "best_by_final_theoretical_signal_count": compact_hypothesis_summary(
            max(
                rows,
                key=lambda row: int(row["final_theoretical_signal_count"]),
                default=None,
            )
        ),
        "best_by_candidate_signal_count": compact_hypothesis_summary(
            max(
                rows,
                key=lambda row: int(row["candidate_signal_count"]),
                default=None,
            )
        ),
        "current_baseline": compact_hypothesis_summary(rows[0] if rows else None),
    }
    return report


def evaluate_hypothesis(
    *,
    bars: Any,
    symbol: str,
    hypothesis: HypothesisDefinition,
    symbol_info: dict[str, Any],
    risk_config: RiskConfig,
    account_equity: float,
) -> dict[str, Any]:
    minimum_bars = max(hypothesis.signal_config.slow_sma, hypothesis.signal_config.atr_period) + 2
    frame = add_indicators(bars, hypothesis.signal_config)
    risk_manager = RiskManager(risk_config)
    observations = 0
    candidates: list[Candidate] = []
    final_signals: list[Candidate] = []
    reason_counter: Counter[str] = Counter()
    feasibility_counter: Counter[str] = Counter()
    lot_below_min_count = 0
    risk_preview_examples: list[dict[str, Any]] = []

    for entry_index in range(minimum_bars, len(frame)):
        observations += 1
        candidate = candidate_for_entry(
            frame=frame,
            entry_index=entry_index,
            symbol=symbol,
            hypothesis=hypothesis,
            symbol_info=symbol_info,
        )
        if candidate is None:
            reason_counter.update([REASON_NO_ACTIONABLE_SIGNAL])
            continue

        candidates.append(candidate)
        risk_decision = assess_candidate(
            candidate=candidate,
            symbol_info=symbol_info,
            risk_manager=risk_manager,
            account_equity=account_equity,
            spread_points=spread_points_for_bar(frame.iloc[entry_index], symbol_info),
        )
        if REASON_LOT_BELOW_VOLUME_MIN in risk_decision.reason_codes:
            lot_below_min_count += 1
        feasibility_counter.update(risk_decision.reason_codes)
        if len(risk_preview_examples) < 5:
            risk_preview_examples.append(risk_preview_payload(candidate, risk_decision))

        if hypothesis.risk_gated and not risk_decision.allowed:
            reason_counter.update(risk_decision.reason_codes)
            continue
        final_signals.append(candidate)

    candidate_side_counts = side_counts(candidates)
    final_side_counts = side_counts(final_signals)
    return {
        "name": hypothesis.name,
        "family": hypothesis.family,
        "description": hypothesis.description,
        "hypothetical_only": True,
        "risk_gated": hypothesis.risk_gated,
        "signal_mode": hypothesis.signal_mode,
        "parameters": asdict(hypothesis.signal_config),
        "total_observations": observations,
        "candidate_signal_count": len(candidates),
        "final_theoretical_signal_count": len(final_signals),
        "signal_rate": len(final_signals) / observations if observations else 0.0,
        "candidate_signal_rate": len(candidates) / observations if observations else 0.0,
        "candidate_buy_count": candidate_side_counts["BUY"],
        "candidate_sell_count": candidate_side_counts["SELL"],
        "final_buy_count": final_side_counts["BUY"],
        "final_sell_count": final_side_counts["SELL"],
        "buy_sell_distribution": {
            "candidate": candidate_side_counts,
            "final_theoretical": final_side_counts,
        },
        "top_block_reasons": counter_to_top(reason_counter),
        "block_reason_counts": dict(sorted(reason_counter.items())),
        "estimated_min_lot_feasibility_issues": lot_below_min_count,
        "estimated_feasibility_reason_counts": dict(sorted(feasibility_counter.items())),
        "risk_preview_examples": risk_preview_examples,
        "orders_sent": 0,
        "order_check_called": False,
        "order_send_called": False,
    }


def add_indicators(bars: Any, config: BaselineSignalConfig) -> Any:
    frame = bars.copy()
    frame["fast_sma"] = frame["close"].rolling(config.fast_sma).mean()
    frame["slow_sma"] = frame["close"].rolling(config.slow_sma).mean()
    previous_close = frame["close"].shift(1)
    true_range = frame[["high", "low"]].assign(
        high_close=(frame["high"] - previous_close).abs(),
        low_close=(frame["low"] - previous_close).abs(),
        high_low=frame["high"] - frame["low"],
    )[["high_close", "low_close", "high_low"]].max(axis=1)
    frame["atr"] = true_range.rolling(config.atr_period).mean()
    return frame


def candidate_for_entry(
    *,
    frame: Any,
    entry_index: int,
    symbol: str,
    hypothesis: HypothesisDefinition,
    symbol_info: Mapping[str, Any],
) -> Candidate | None:
    previous = frame.iloc[entry_index - 2]
    signal_bar = frame.iloc[entry_index - 1]
    if indicator_warmup(previous, signal_bar):
        return None

    side = side_for_mode(previous, signal_bar, hypothesis.signal_mode)
    if side is None:
        return None

    entry_bar = frame.iloc[entry_index]
    entry_price = float(entry_bar["open"])
    stop_distance = float(signal_bar["atr"]) * hypothesis.signal_config.atr_stop_multiplier
    if stop_distance <= 0:
        return None
    stop_loss = entry_price - stop_distance if side == "BUY" else entry_price + stop_distance
    take_profit = (
        entry_price + (stop_distance * hypothesis.signal_config.reward_risk_ratio)
        if side == "BUY"
        else entry_price - (stop_distance * hypothesis.signal_config.reward_risk_ratio)
    )
    point = float(symbol_info["point"])
    return Candidate(
        side=side,
        entry_price=entry_price,
        stop_loss_price=stop_loss,
        take_profit_price=take_profit,
        signal_bar_index=entry_index - 1,
        entry_bar_index=entry_index,
        signal_time=str(signal_bar["time"]),
        reason=f"{hypothesis.signal_mode} generated {side}",
        stop_distance_points=abs(entry_price - stop_loss) / point,
    )


def indicator_warmup(previous: Any, signal_bar: Any) -> bool:
    values = (
        previous["fast_sma"],
        previous["slow_sma"],
        signal_bar["fast_sma"],
        signal_bar["slow_sma"],
        signal_bar["atr"],
    )
    return any(value != value for value in values)


def side_for_mode(previous: Any, signal_bar: Any, mode: str) -> str | None:
    crossed_up = previous["fast_sma"] <= previous["slow_sma"] and signal_bar["fast_sma"] > signal_bar["slow_sma"]
    crossed_down = previous["fast_sma"] >= previous["slow_sma"] and signal_bar["fast_sma"] < signal_bar["slow_sma"]
    if mode == "sma_crossover":
        if crossed_up:
            return "BUY"
        if crossed_down:
            return "SELL"
        return None

    if mode == "trend_continuation":
        if not crossed_up and signal_bar["fast_sma"] > signal_bar["slow_sma"] and signal_bar["close"] > signal_bar["slow_sma"]:
            return "BUY"
        if not crossed_down and signal_bar["fast_sma"] < signal_bar["slow_sma"] and signal_bar["close"] < signal_bar["slow_sma"]:
            return "SELL"
        return None

    if mode == "relaxed_sma_slope":
        fast_slope = signal_bar["fast_sma"] - previous["fast_sma"]
        if fast_slope > 0 and signal_bar["close"] >= signal_bar["fast_sma"]:
            return "BUY"
        if fast_slope < 0 and signal_bar["close"] <= signal_bar["fast_sma"]:
            return "SELL"
        return None

    raise ValueError(f"unsupported signal_mode: {mode}")


def assess_candidate(
    *,
    candidate: Candidate,
    symbol_info: dict[str, Any],
    risk_manager: RiskManager,
    account_equity: float,
    spread_points: float,
) -> RiskDecision:
    return risk_manager.assess_trade(
        TradeRiskRequest(
            symbol_info=symbol_info,
            account=AccountState(balance=account_equity, equity=account_equity, daily_realized_pnl=0.0),
            side=candidate.side,
            entry_price=candidate.entry_price,
            stop_loss_price=candidate.stop_loss_price,
            take_profit_price=candidate.take_profit_price,
            current_spread_points=spread_points,
            open_positions=[],
        )
    )


def risk_preview_payload(candidate: Candidate, decision: RiskDecision) -> dict[str, Any]:
    computed_lot = decision.risk_amount / decision.risk_per_lot if decision.risk_per_lot > 0 else None
    return {
        "side": candidate.side,
        "signal_time": candidate.signal_time,
        "entry_bar_index": candidate.entry_bar_index,
        "stop_distance_points": candidate.stop_distance_points,
        "allowed": decision.allowed,
        "volume": decision.volume,
        "computed_lot": computed_lot,
        "risk_amount": decision.risk_amount,
        "risk_per_lot": decision.risk_per_lot,
        "reason_codes": list(decision.reason_codes),
    }


def build_hypotheses(selected_config: BaselineSignalConfig) -> list[HypothesisDefinition]:
    return [
        HypothesisDefinition(
            name="current_baseline_risk_gated",
            family="current_baseline",
            description="Current selected SMA crossover parameters with normal offline risk feasibility gates.",
            signal_mode="sma_crossover",
            signal_config=selected_config,
            risk_gated=True,
        ),
        HypothesisDefinition(
            name="current_baseline_candidate_only",
            family="crossover_only_baseline",
            description="Current selected SMA crossover parameters counted as candidates without applying feasibility gates to final theoretical count.",
            signal_mode="sma_crossover",
            signal_config=selected_config,
            risk_gated=False,
        ),
        HypothesisDefinition(
            name="sma_5_20_risk_gated",
            family="sma_parameter_variant",
            description="Faster SMA crossover hypothesis with normal offline risk feasibility gates.",
            signal_mode="sma_crossover",
            signal_config=copy_signal_config(selected_config, fast_sma=5, slow_sma=20),
            risk_gated=True,
        ),
        HypothesisDefinition(
            name="sma_8_21_risk_gated",
            family="sma_parameter_variant",
            description="Medium-fast SMA crossover hypothesis with normal offline risk feasibility gates.",
            signal_mode="sma_crossover",
            signal_config=copy_signal_config(selected_config, fast_sma=8, slow_sma=21),
            risk_gated=True,
        ),
        HypothesisDefinition(
            name="sma_10_30_risk_gated",
            family="sma_parameter_variant",
            description="Moderately relaxed SMA crossover hypothesis with normal offline risk feasibility gates.",
            signal_mode="sma_crossover",
            signal_config=copy_signal_config(selected_config, fast_sma=10, slow_sma=30),
            risk_gated=True,
        ),
        HypothesisDefinition(
            name="trend_continuation_risk_gated",
            family="trend_continuation",
            description="Trend-continuation hypothesis that does not require an immediate crossover, with normal offline risk feasibility gates.",
            signal_mode="trend_continuation",
            signal_config=selected_config,
            risk_gated=True,
        ),
        HypothesisDefinition(
            name="relaxed_candidate_only_sma_slope",
            family="relaxed_candidate_diagnostic",
            description="Relaxed candidate-only diagnostic using fast SMA slope; not production logic and not risk-gated for final theoretical count.",
            signal_mode="relaxed_sma_slope",
            signal_config=selected_config,
            risk_gated=False,
        ),
    ]


def copy_signal_config(config: BaselineSignalConfig, *, fast_sma: int, slow_sma: int) -> BaselineSignalConfig:
    return BaselineSignalConfig(
        fast_sma=fast_sma,
        slow_sma=slow_sma,
        atr_period=config.atr_period,
        atr_stop_multiplier=config.atr_stop_multiplier,
        reward_risk_ratio=config.reward_risk_ratio,
    )


def selected_signal_config_from_report(path: Path, fallback: BaselineSignalConfig) -> tuple[BaselineSignalConfig, str]:
    if not path.exists():
        return fallback, "cli_fallback"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        parameters = payload.get("diagnostics", {}).get("best_parameters")
        if not isinstance(parameters, Mapping):
            rows = payload.get("parameter_results") or []
            if rows and isinstance(rows[0], Mapping):
                parameters = rows[0].get("parameters")
        if isinstance(parameters, Mapping):
            return (
                BaselineSignalConfig(
                    fast_sma=int(parameters["fast_sma"]),
                    slow_sma=int(parameters["slow_sma"]),
                    atr_period=int(parameters.get("atr_period", fallback.atr_period)),
                    atr_stop_multiplier=float(parameters["atr_stop_multiplier"]),
                    reward_risk_ratio=float(parameters["reward_risk_ratio"]),
                ),
                str(path),
            )
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
        pass
    return fallback, "cli_fallback"


def load_bars(path: Path, pd: Any) -> Any:
    if not path.exists():
        return pd.DataFrame(columns=["time", "open", "high", "low", "close", "spread"])
    return normalize_bars(pd.read_csv(path), pd)


def load_symbol_info(*, input_path: Path, explicit_path: Path | None, journal_dir: Path) -> dict[str, Any] | None:
    metadata_path = explicit_path or input_path.with_suffix(input_path.suffix + ".symbol_info.json")
    metadata = load_symbol_metadata(metadata_path)
    if metadata is not None:
        return dict(metadata["symbol_info"])

    for entry in sorted(load_dry_run_journals(journal_dir), key=lambda item: str(item.get("path")), reverse=True):
        payload = entry.get("payload")
        if not isinstance(payload, Mapping):
            continue
        symbol = payload.get("symbol")
        if isinstance(symbol, Mapping) and symbol.get("point") is not None:
            return dict(symbol)
    return None


def load_or_default_trading_config(path: Path) -> TradingConfig:
    if path.exists():
        return load_trading_config(path)
    return TradingConfig()


def compare_against_baseline(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not rows:
        return []
    baseline = rows[0]
    baseline_candidates = int(baseline["candidate_signal_count"])
    baseline_final = int(baseline["final_theoretical_signal_count"])
    baseline_rate = float(baseline["signal_rate"])
    comparisons = []
    for row in rows:
        comparisons.append(
            {
                "name": row["name"],
                "candidate_signal_delta": int(row["candidate_signal_count"]) - baseline_candidates,
                "final_theoretical_signal_delta": int(row["final_theoretical_signal_count"]) - baseline_final,
                "signal_rate_delta": float(row["signal_rate"]) - baseline_rate,
                "estimated_min_lot_issue_delta": int(row["estimated_min_lot_feasibility_issues"])
                - int(baseline["estimated_min_lot_feasibility_issues"]),
            }
        )
    return comparisons


def compact_hypothesis_summary(row: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "name": row["name"],
        "family": row["family"],
        "risk_gated": row["risk_gated"],
        "candidate_signal_count": row["candidate_signal_count"],
        "final_theoretical_signal_count": row["final_theoretical_signal_count"],
        "signal_rate": row["signal_rate"],
        "candidate_signal_rate": row["candidate_signal_rate"],
        "estimated_min_lot_feasibility_issues": row["estimated_min_lot_feasibility_issues"],
        "top_block_reasons": row["top_block_reasons"],
    }


def side_counts(candidates: list[Candidate]) -> dict[str, int]:
    counter = Counter(candidate.side for candidate in candidates)
    return {"BUY": counter.get("BUY", 0), "SELL": counter.get("SELL", 0)}


def counter_to_top(counter: Counter[str], limit: int = 10) -> list[dict[str, Any]]:
    return [{"reason": reason, "count": count} for reason, count in counter.most_common(limit)]


def spread_points_for_bar(bar: Any, symbol_info: Mapping[str, Any]) -> float:
    spread = numeric_or_none(bar.get("spread") if hasattr(bar, "get") else None)
    if spread is not None:
        return spread
    return float(symbol_info.get("spread", 0.0) or 0.0)


def print_summary(report: Mapping[str, Any]) -> None:
    print("xm-gold-ai-trader strategy hypothesis lab")
    print(f"status: {report['status']}")
    print(f"hypotheses: {len(report.get('hypotheses', []))}")
    for row in report.get("hypotheses", []):
        print(
            f"{row['name']}: candidates={row['candidate_signal_count']} "
            f"final_theoretical={row['final_theoretical_signal_count']} "
            f"rate={row['signal_rate']:.4f}"
        )
    print("orders_sent: 0")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run read-only offline strategy hypothesis diagnostics.")
    parser.add_argument("--symbol", default=os.getenv("XM_GOLD_SYMBOL", "GOLD_"))
    parser.add_argument("--timeframe", default="M15", choices=("M1", "M5", "M15", "M30", "H1", "H4", "D1"))
    parser.add_argument("--input", default="data/gold_m15.csv")
    parser.add_argument("--symbol-info")
    parser.add_argument("--dry-run-journal-dir", default="logs/dry_run_signals")
    parser.add_argument("--config", default="configs/xm_gold_ai_trader.demo.yaml")
    parser.add_argument("--parameter-report", default=str(DEFAULT_PARAMETER_REPORT))
    parser.add_argument("--bars", type=int, default=5_000)
    parser.add_argument("--account-equity", type=float, default=1_000.0)
    parser.add_argument("--fallback-fast-sma", type=int, default=10)
    parser.add_argument("--fallback-slow-sma", type=int, default=40)
    parser.add_argument("--atr-period", type=int, default=14)
    parser.add_argument("--fallback-atr-stop-multiplier", type=float, default=1.5)
    parser.add_argument("--fallback-reward-risk-ratio", type=float, default=1.5)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
