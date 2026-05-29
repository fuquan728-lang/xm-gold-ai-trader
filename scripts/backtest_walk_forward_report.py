from __future__ import annotations

import argparse
import itertools
import json
import math
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.backtest_baseline_report import (
    BacktestConfig,
    REASON_NO_BACKTEST_DATA,
    load_backtest_inputs,
    run_backtest_report,
)
from src.broker.mt5_client import MT5ClientError
from src.logging_config import configure_logging
from src.strategy.baseline_signal import BaselineSignalConfig
from src.strategy.risk_manager import RiskConfig


PROJECT = "xm-gold-ai-trader"
MODE = "backtest_walk_forward_report"

REASON_NO_WALK_FORWARD_FOLDS = "NO_WALK_FORWARD_FOLDS"
REASON_MIN_TRADES_PER_FOLD_FAILED = "MIN_TRADES_PER_FOLD_FAILED"
REASON_SINGLE_FOLD_PROFIT_DOMINANCE = "SINGLE_FOLD_PROFIT_DOMINANCE"
REASON_STRESS_PROFIT_FACTOR_FAILED = "STRESS_PROFIT_FACTOR_FAILED"
REASON_MAX_DRAWDOWN_FAILED = "MAX_DRAWDOWN_FAILED"


@dataclass(frozen=True, slots=True)
class WalkForwardFold:
    fold_id: int
    train_start: int
    train_end: int
    validation_start: int
    validation_end: int
    test_start: int
    test_end: int


@dataclass(frozen=True, slots=True)
class GateConfig:
    min_trades_per_fold: int = 5
    max_single_fold_profit_share: float = 0.75
    min_stress_profit_factor: float = 0.75
    max_drawdown_pct: float = 0.10


def main() -> int:
    args = parse_args()
    logger = configure_logging(logger_name="backtest_walk_forward_report")

    try:
        import pandas as pd
    except ImportError as exc:
        raise RuntimeError("pandas is required for walk-forward backtesting. Install requirements.txt.") from exc

    json_path = Path(args.output_json)
    summary_path = Path(args.output_summary)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        bars, symbol_info, data_source = load_backtest_inputs(args, pd)
    except MT5ClientError as exc:
        logger.error("%s", exc)
        print(str(exc), file=sys.stderr)
        return 1

    report = run_walk_forward_report(
        bars=bars,
        symbol=args.symbol,
        timeframe=args.timeframe,
        symbol_info=symbol_info,
        data_source=data_source,
        train_bars=args.train_bars,
        validation_bars=args.validation_bars,
        test_bars=args.test_bars,
        step_bars=args.step_bars,
        initial_balance=args.initial_balance,
        risk_config=RiskConfig(
            risk_per_trade_pct=args.risk_per_trade_pct,
            max_daily_loss_pct=args.max_daily_loss_pct,
            max_spread_points=args.max_spread_points,
            one_position_only=True,
            max_lot_per_trade=args.max_lot_per_trade,
        ),
        default_signal_config=BaselineSignalConfig(
            fast_sma=args.default_fast_sma,
            slow_sma=args.default_slow_sma,
            atr_period=args.atr_period,
            atr_stop_multiplier=args.default_atr_stop_multiplier,
            reward_risk_ratio=args.default_reward_risk_ratio,
        ),
        parameter_grid=build_parameter_grid(
            fast_values=parse_int_list(args.fast_sma_values),
            slow_values=parse_int_list(args.slow_sma_values),
            atr_stop_values=parse_float_list(args.atr_stop_multipliers),
            reward_risk_values=parse_float_list(args.reward_risk_ratios),
            atr_period=args.atr_period,
        ),
        spread_multipliers=parse_float_list(args.spread_multipliers),
        slippage_points=parse_float_list(args.slippage_points),
        gates=GateConfig(
            min_trades_per_fold=args.min_trades_per_fold,
            max_single_fold_profit_share=args.max_single_fold_profit_share,
            min_stress_profit_factor=args.min_stress_profit_factor,
            max_drawdown_pct=args.max_drawdown_pct,
        ),
    )
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True, default=str), encoding="utf-8")
    summary_path.write_text(report["markdown_summary"], encoding="utf-8")
    logger.info("Wrote walk-forward JSON report to %s", json_path)
    logger.info("Wrote walk-forward summary to %s", summary_path)

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True, default=str))
    else:
        print(report["markdown_summary"])
        print(f"\nJSON report: {json_path}")
        print(f"Markdown summary: {summary_path}")
    return 0


def run_walk_forward_report(
    *,
    bars: Any,
    symbol: str,
    timeframe: str,
    symbol_info: dict[str, Any],
    data_source: dict[str, Any] | None,
    train_bars: int,
    validation_bars: int,
    test_bars: int,
    step_bars: int,
    initial_balance: float,
    risk_config: RiskConfig,
    default_signal_config: BaselineSignalConfig,
    parameter_grid: list[BaselineSignalConfig],
    spread_multipliers: list[float],
    slippage_points: list[float],
    gates: GateConfig,
) -> dict[str, Any]:
    report = {
        "project": PROJECT,
        "mode": MODE,
        "orders_sent": 0,
        "symbol": symbol,
        "timeframe": timeframe,
        "status": "PASS",
        "reason_codes": [],
        "data_source": data_source or {},
        "fold_config": {
            "train_bars": train_bars,
            "validation_bars": validation_bars,
            "test_bars": test_bars,
            "step_bars": step_bars,
            "selection_source": "validation_window_only",
        },
        "strategy_constraints": {
            "ai_model_trading": False,
            "martingale": False,
            "grid": False,
            "lot_increase_after_loss": False,
            "orders_sent": 0,
        },
        "gates": {"config": asdict(gates), "passed": True, "failures": []},
        "folds": [],
        "robustness_matrix": [],
        "parameter_sensitivity": [],
        "markdown_summary": "",
    }

    if len(bars) == 0:
        report["status"] = "NO_DATA"
        report["reason_codes"] = [REASON_NO_BACKTEST_DATA]
        report["markdown_summary"] = format_markdown_summary(report)
        return report

    folds = make_walk_forward_folds(
        total_bars=len(bars),
        train_bars=train_bars,
        validation_bars=validation_bars,
        test_bars=test_bars,
        step_bars=step_bars,
    )
    if not folds:
        report["status"] = "FAIL"
        report["reason_codes"] = [REASON_NO_WALK_FORWARD_FOLDS]
        report["markdown_summary"] = format_markdown_summary(report)
        return report

    for fold in folds:
        report["folds"].append(
            evaluate_fold(
                bars=bars,
                fold=fold,
                symbol=symbol,
                timeframe=timeframe,
                symbol_info=symbol_info,
                initial_balance=initial_balance,
                risk_config=risk_config,
                default_signal_config=default_signal_config,
                parameter_grid=parameter_grid,
            )
        )

    report["robustness_matrix"] = run_robustness_matrix(
        bars=bars,
        symbol=symbol,
        timeframe=timeframe,
        symbol_info=symbol_info,
        initial_balance=initial_balance,
        risk_config=risk_config,
        signal_config=default_signal_config,
        spread_multipliers=spread_multipliers,
        slippage_points=slippage_points,
    )
    report["parameter_sensitivity"] = run_parameter_sensitivity(
        bars=bars,
        symbol=symbol,
        timeframe=timeframe,
        symbol_info=symbol_info,
        initial_balance=initial_balance,
        risk_config=risk_config,
        parameter_grid=parameter_grid,
    )
    report["gates"] = evaluate_gates(
        folds=report["folds"],
        robustness_matrix=report["robustness_matrix"],
        gates=gates,
    )
    if not report["gates"]["passed"]:
        report["status"] = "FAIL"
        report["reason_codes"] = [failure["reason_code"] for failure in report["gates"]["failures"]]
    report["markdown_summary"] = format_markdown_summary(report)
    return report


def make_walk_forward_folds(
    *,
    total_bars: int,
    train_bars: int,
    validation_bars: int,
    test_bars: int,
    step_bars: int,
) -> list[WalkForwardFold]:
    if min(train_bars, validation_bars, test_bars, step_bars) <= 0:
        raise ValueError("walk-forward window sizes must be positive")
    folds: list[WalkForwardFold] = []
    start = 0
    fold_id = 1
    total_window = train_bars + validation_bars + test_bars
    while start + total_window <= total_bars:
        train_start = start
        train_end = train_start + train_bars
        validation_start = train_end
        validation_end = validation_start + validation_bars
        test_start = validation_end
        test_end = test_start + test_bars
        folds.append(
            WalkForwardFold(
                fold_id=fold_id,
                train_start=train_start,
                train_end=train_end,
                validation_start=validation_start,
                validation_end=validation_end,
                test_start=test_start,
                test_end=test_end,
            )
        )
        fold_id += 1
        start += step_bars
    return folds


def evaluate_fold(
    *,
    bars: Any,
    fold: WalkForwardFold,
    symbol: str,
    timeframe: str,
    symbol_info: dict[str, Any],
    initial_balance: float,
    risk_config: RiskConfig,
    default_signal_config: BaselineSignalConfig,
    parameter_grid: list[BaselineSignalConfig],
) -> dict[str, Any]:
    train = bars.iloc[fold.train_start : fold.train_end].copy()
    validation = bars.iloc[fold.validation_start : fold.validation_end].copy()
    test = bars.iloc[fold.test_start : fold.test_end].copy()
    selected_config, validation_report = select_parameters_on_validation(
        validation=validation,
        symbol=symbol,
        timeframe=timeframe,
        symbol_info=symbol_info,
        initial_balance=initial_balance,
        risk_config=risk_config,
        parameter_grid=parameter_grid or [default_signal_config],
    )
    train_report = run_single_backtest(
        bars=train,
        symbol=symbol,
        timeframe=timeframe,
        symbol_info=symbol_info,
        initial_balance=initial_balance,
        risk_config=risk_config,
        signal_config=selected_config,
        data_source={"kind": "walk_forward_train", "fold_id": fold.fold_id},
    )
    test_report = run_single_backtest(
        bars=test,
        symbol=symbol,
        timeframe=timeframe,
        symbol_info=symbol_info,
        initial_balance=initial_balance,
        risk_config=risk_config,
        signal_config=selected_config,
        data_source={"kind": "walk_forward_test", "fold_id": fold.fold_id},
    )
    metrics = compact_metrics(test_report["metrics"])
    return {
        "fold_id": fold.fold_id,
        "date_range": {
            "train": window_range(train, fold.train_start, fold.train_end),
            "validation": window_range(validation, fold.validation_start, fold.validation_end),
            "test": window_range(test, fold.test_start, fold.test_end),
        },
        "selected_parameters": asdict(selected_config),
        "train_metrics": compact_metrics(train_report["metrics"]),
        "validation_metrics": compact_metrics(validation_report["metrics"]),
        "test_metrics": metrics,
        **metrics,
    }


def select_parameters_on_validation(
    *,
    validation: Any,
    symbol: str,
    timeframe: str,
    symbol_info: dict[str, Any],
    initial_balance: float,
    risk_config: RiskConfig,
    parameter_grid: list[BaselineSignalConfig],
) -> tuple[BaselineSignalConfig, dict[str, Any]]:
    best_config = parameter_grid[0]
    best_report: dict[str, Any] | None = None
    best_score: tuple[float, float, float] | None = None
    for signal_config in parameter_grid:
        report = run_single_backtest(
            bars=validation,
            symbol=symbol,
            timeframe=timeframe,
            symbol_info=symbol_info,
            initial_balance=initial_balance,
            risk_config=risk_config,
            signal_config=signal_config,
            data_source={"kind": "walk_forward_validation"},
        )
        metrics = report["metrics"]
        score = (
            float(metrics["net_profit"]),
            profit_factor_score(metrics.get("profit_factor")),
            float(metrics["total_trades"]),
        )
        if best_score is None or score > best_score:
            best_score = score
            best_config = signal_config
            best_report = report
    return best_config, best_report or {}


def run_robustness_matrix(
    *,
    bars: Any,
    symbol: str,
    timeframe: str,
    symbol_info: dict[str, Any],
    initial_balance: float,
    risk_config: RiskConfig,
    signal_config: BaselineSignalConfig,
    spread_multipliers: list[float],
    slippage_points: list[float],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for multiplier, slippage in itertools.product(spread_multipliers, slippage_points):
        stressed = apply_spread_slippage(
            bars=bars,
            symbol_info=symbol_info,
            spread_multiplier=multiplier,
            slippage_points=slippage,
        )
        report = run_single_backtest(
            bars=stressed,
            symbol=symbol,
            timeframe=timeframe,
            symbol_info=symbol_info,
            initial_balance=initial_balance,
            risk_config=risk_config,
            signal_config=signal_config,
            data_source={"kind": "robustness_matrix"},
        )
        rows.append(
            {
                "spread_multiplier": multiplier,
                "slippage_points": slippage,
                **compact_metrics(report["metrics"]),
            }
        )
    return rows


def apply_spread_slippage(
    *,
    bars: Any,
    symbol_info: Mapping[str, Any],
    spread_multiplier: float,
    slippage_points: float,
) -> Any:
    stressed = bars.copy()
    if "spread" in stressed.columns:
        base_spread = stressed["spread"].astype(float)
    else:
        base_spread = float(symbol_info.get("spread", 0.0) or 0.0)
    stressed["spread"] = (base_spread * spread_multiplier) + slippage_points
    return stressed


def run_parameter_sensitivity(
    *,
    bars: Any,
    symbol: str,
    timeframe: str,
    symbol_info: dict[str, Any],
    initial_balance: float,
    risk_config: RiskConfig,
    parameter_grid: list[BaselineSignalConfig],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for signal_config in parameter_grid:
        report = run_single_backtest(
            bars=bars,
            symbol=symbol,
            timeframe=timeframe,
            symbol_info=symbol_info,
            initial_balance=initial_balance,
            risk_config=risk_config,
            signal_config=signal_config,
            data_source={"kind": "parameter_sensitivity"},
        )
        rows.append({"parameters": asdict(signal_config), **compact_metrics(report["metrics"])})
    return sorted(rows, key=lambda row: (float(row["net_profit"]), float(row["total_trades"])), reverse=True)


def run_single_backtest(
    *,
    bars: Any,
    symbol: str,
    timeframe: str,
    symbol_info: dict[str, Any],
    initial_balance: float,
    risk_config: RiskConfig,
    signal_config: BaselineSignalConfig,
    data_source: dict[str, Any],
) -> dict[str, Any]:
    return run_backtest_report(
        bars=bars.reset_index(drop=True),
        symbol=symbol,
        timeframe=timeframe,
        symbol_info=symbol_info,
        config=BacktestConfig(
            signal=signal_config,
            risk=risk_config,
            initial_balance=initial_balance,
            spread_points=None,
        ),
        data_source=data_source,
    )


def evaluate_gates(
    *,
    folds: list[dict[str, Any]],
    robustness_matrix: list[dict[str, Any]],
    gates: GateConfig,
) -> dict[str, Any]:
    failures: list[dict[str, Any]] = []
    weak_folds = [fold["fold_id"] for fold in folds if int(fold["total_trades"]) < gates.min_trades_per_fold]
    if weak_folds:
        failures.append(
            {
                "reason_code": REASON_MIN_TRADES_PER_FOLD_FAILED,
                "message": f"folds below minimum trades per fold {gates.min_trades_per_fold}: {weak_folds}",
                "fold_ids": weak_folds,
            }
        )

    positive_profits = [max(0.0, float(fold["net_profit"])) for fold in folds]
    total_positive_profit = sum(positive_profits)
    if total_positive_profit > 0:
        max_share = max(positive_profits) / total_positive_profit
        if max_share > gates.max_single_fold_profit_share:
            failures.append(
                {
                    "reason_code": REASON_SINGLE_FOLD_PROFIT_DOMINANCE,
                    "message": (
                        f"single fold profit share {max_share:.3f} exceeds "
                        f"{gates.max_single_fold_profit_share:.3f}"
                    ),
                    "max_share": max_share,
                }
            )

    weak_stress = [
        row
        for row in robustness_matrix
        if int(row["total_trades"]) == 0
        or profit_factor_score(row.get("profit_factor"), none_when_no_loss_is_infinite=False) < gates.min_stress_profit_factor
    ]
    if weak_stress:
        failures.append(
            {
                "reason_code": REASON_STRESS_PROFIT_FACTOR_FAILED,
                "message": f"{len(weak_stress)} robustness cases below profit factor threshold",
                "threshold": gates.min_stress_profit_factor,
            }
        )

    worst_drawdown_pct = max(
        [float(fold["max_drawdown_pct"]) for fold in folds]
        + [float(row["max_drawdown_pct"]) for row in robustness_matrix],
        default=0.0,
    )
    if worst_drawdown_pct > gates.max_drawdown_pct:
        failures.append(
            {
                "reason_code": REASON_MAX_DRAWDOWN_FAILED,
                "message": f"max drawdown pct {worst_drawdown_pct:.4f} exceeds {gates.max_drawdown_pct:.4f}",
                "max_drawdown_pct": worst_drawdown_pct,
            }
        )

    return {"config": asdict(gates), "passed": not failures, "failures": failures}


def build_parameter_grid(
    *,
    fast_values: list[int],
    slow_values: list[int],
    atr_stop_values: list[float],
    reward_risk_values: list[float],
    atr_period: int,
) -> list[BaselineSignalConfig]:
    configs: list[BaselineSignalConfig] = []
    for fast, slow, atr_stop, reward_risk in itertools.product(
        fast_values,
        slow_values,
        atr_stop_values,
        reward_risk_values,
    ):
        if slow <= fast:
            continue
        configs.append(
            BaselineSignalConfig(
                fast_sma=fast,
                slow_sma=slow,
                atr_period=atr_period,
                atr_stop_multiplier=atr_stop,
                reward_risk_ratio=reward_risk,
            )
        )
    if not configs:
        raise ValueError("parameter grid is empty after filtering slow_sma > fast_sma")
    return configs


def compact_metrics(metrics: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "total_trades": int(metrics["total_trades"]),
        "win_rate": float(metrics["win_rate"]),
        "net_profit": float(metrics["net_profit"]),
        "profit_factor": metrics.get("profit_factor"),
        "max_drawdown": float(metrics["max_drawdown"]),
        "max_drawdown_pct": float(metrics["max_drawdown_pct"]),
        "average_r": float(metrics["average_r"]),
        "max_consecutive_losses": int(metrics["max_consecutive_losses"]),
    }


def window_range(window: Any, start: int, end: int) -> dict[str, Any]:
    if len(window) == 0:
        return {"start_index": start, "end_index_exclusive": end, "start_time": None, "end_time": None}
    return {
        "start_index": start,
        "end_index_exclusive": end,
        "start_time": str(window.iloc[0]["time"]),
        "end_time": str(window.iloc[-1]["time"]),
    }


def profit_factor_score(value: Any, *, none_when_no_loss_is_infinite: bool = True) -> float:
    if value is None:
        return math.inf if none_when_no_loss_is_infinite else 0.0
    return float(value)


def format_markdown_summary(report: Mapping[str, Any]) -> str:
    lines = [
        "# Walk-Forward Baseline Report",
        "",
        f"- Project: `{report['project']}`",
        f"- Symbol/timeframe: `{report['symbol']} {report['timeframe']}`",
        f"- Status: `{report['status']}`",
        f"- Orders sent: `{report['orders_sent']}`",
        f"- Gate result: `{'PASS' if report['gates']['passed'] else 'FAIL'}`",
        "",
        "## Fold Results",
        "",
        "| Fold | Test Range | Trades | Win Rate | Net Profit | Profit Factor | Max DD | Avg R | Max Losses |",
        "|---:|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for fold in report.get("folds", []):
        pf = fold["profit_factor"]
        pf_text = "n/a" if pf is None else f"{float(pf):.2f}"
        test_range = fold["date_range"]["test"]
        lines.append(
            "| {fold_id} | {start} to {end} | {trades} | {win:.2f}% | {net:.2f} | {pf} | {dd:.2f} | {avg_r:.3f} | {losses} |".format(
                fold_id=fold["fold_id"],
                start=test_range["start_time"],
                end=test_range["end_time"],
                trades=fold["total_trades"],
                win=fold["win_rate"] * 100,
                net=fold["net_profit"],
                pf=pf_text,
                dd=fold["max_drawdown"],
                avg_r=fold["average_r"],
                losses=fold["max_consecutive_losses"],
            )
        )
    lines.extend(["", "## Gate Failures", ""])
    failures = report["gates"].get("failures", [])
    if not failures:
        lines.append("- None")
    else:
        for failure in failures:
            lines.append(f"- `{failure['reason_code']}`: {failure['message']}")
    lines.extend(["", "## Robustness Matrix", ""])
    lines.append("| Spread x | Slippage Points | Trades | Net Profit | Profit Factor | Max DD |")
    lines.append("|---:|---:|---:|---:|---:|---:|")
    for row in report.get("robustness_matrix", []):
        pf = row["profit_factor"]
        pf_text = "n/a" if pf is None else f"{float(pf):.2f}"
        lines.append(
            f"| {row['spread_multiplier']:.2f} | {row['slippage_points']:.1f} | "
            f"{row['total_trades']} | {row['net_profit']:.2f} | {pf_text} | {row['max_drawdown']:.2f} |"
        )
    return "\n".join(lines) + "\n"


def parse_int_list(value: str) -> list[int]:
    return [int(part.strip()) for part in value.split(",") if part.strip()]


def parse_float_list(value: str) -> list[float]:
    return [float(part.strip()) for part in value.split(",") if part.strip()]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run baseline walk-forward and robustness validation without orders.")
    parser.add_argument("--symbol", default=os.getenv("XM_GOLD_SYMBOL", "GOLD_"))
    parser.add_argument("--timeframe", default="M15", choices=("M1", "M5", "M15", "M30", "H1", "H4", "D1"))
    parser.add_argument("--input", default="data/gold_m15.csv")
    parser.add_argument("--bars", type=int, default=5_000)
    parser.add_argument("--output-json", default="reports/backtests/walk_forward_report.json")
    parser.add_argument("--output-summary", default="reports/backtests/walk_forward_summary.md")
    parser.add_argument("--train-bars", type=int, default=1_500)
    parser.add_argument("--validation-bars", type=int, default=750)
    parser.add_argument("--test-bars", type=int, default=750)
    parser.add_argument("--step-bars", type=int, default=750)
    parser.add_argument("--initial-balance", type=float, default=10_000.0)
    parser.add_argument("--risk-per-trade-pct", type=float, default=0.25)
    parser.add_argument("--max-daily-loss-pct", type=float, default=1.0)
    parser.add_argument("--max-spread-points", type=float, default=1_000.0)
    parser.add_argument("--max-lot-per-trade", type=float, default=None)
    parser.add_argument("--default-fast-sma", type=int, default=20)
    parser.add_argument("--default-slow-sma", type=int, default=50)
    parser.add_argument("--default-atr-stop-multiplier", type=float, default=1.5)
    parser.add_argument("--default-reward-risk-ratio", type=float, default=1.5)
    parser.add_argument("--atr-period", type=int, default=14)
    parser.add_argument("--fast-sma-values", default="10,20")
    parser.add_argument("--slow-sma-values", default="40,50")
    parser.add_argument("--atr-stop-multipliers", default="1.0,1.5")
    parser.add_argument("--reward-risk-ratios", default="1.0,1.5")
    parser.add_argument("--spread-multipliers", default="1.0,1.25,1.5,2.0")
    parser.add_argument("--slippage-points", default="0,5,10,20")
    parser.add_argument("--min-trades-per-fold", type=int, default=5)
    parser.add_argument("--max-single-fold-profit-share", type=float, default=0.75)
    parser.add_argument("--min-stress-profit-factor", type=float, default=0.75)
    parser.add_argument("--max-drawdown-pct", type=float, default=0.10)
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
