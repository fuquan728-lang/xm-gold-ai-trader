from __future__ import annotations

import argparse
import json
import math
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import median
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.backtest_baseline_report import (
    BacktestConfig,
    REASON_NO_BACKTEST_DATA,
    load_backtest_inputs,
    run_backtest_report,
)
from scripts.backtest_walk_forward_report import (
    apply_spread_slippage,
    build_parameter_grid,
    compact_metrics,
    parse_float_list,
    parse_int_list,
)
from src.broker.mt5_client import MT5ClientError
from src.logging_config import configure_logging
from src.strategy.baseline_signal import BaselineSignalConfig
from src.strategy.risk_manager import RiskConfig


PROJECT = "xm-gold-ai-trader"
MODE = "backtest_parameter_stability_report"

WARNING_BEST_PARAM_ISOLATED = "BEST_PARAM_ISOLATED"
WARNING_MEDIAN_PARAM_WEAK = "MEDIAN_PARAM_WEAK"
WARNING_TOO_FEW_PROFITABLE_PARAMS = "TOO_FEW_PROFITABLE_PARAMS"
WARNING_STRESS_TEST_FRAGILE = "STRESS_TEST_FRAGILE"
WARNING_PROFIT_CONCENTRATED_IN_FEW_TRADES = "PROFIT_CONCENTRATED_IN_FEW_TRADES"

PARAMETER_NAMES = ("fast_sma", "slow_sma", "atr_stop_multiplier", "reward_risk_ratio")


@dataclass(frozen=True, slots=True)
class StabilityThresholds:
    min_median_profit_factor: float = 1.0
    min_profitable_parameter_pct: float = 0.35
    min_stress_survival_pct: float = 0.50
    min_stress_profit_factor: float = 1.0
    neighbor_net_profit_ratio: float = 0.35
    top_trade_profit_share_max: float = 0.50
    concentration_top_trade_count: int = 3


def main() -> int:
    args = parse_args()
    logger = configure_logging(logger_name="backtest_parameter_stability_report")

    try:
        import pandas as pd
    except ImportError as exc:
        raise RuntimeError("pandas is required for parameter stability backtesting. Install requirements.txt.") from exc

    json_path = Path(args.output_json)
    summary_path = Path(args.output_summary)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        bars, symbol_info, data_source = load_backtest_inputs(args, pd)
        parameter_values = {
            "fast_sma": parse_int_list(args.fast_sma_values),
            "slow_sma": parse_int_list(args.slow_sma_values),
            "atr_stop_multiplier": parse_float_list(args.atr_stop_multipliers),
            "reward_risk_ratio": parse_float_list(args.reward_risk_ratios),
        }
        parameter_grid = build_parameter_grid(
            fast_values=parameter_values["fast_sma"],
            slow_values=parameter_values["slow_sma"],
            atr_stop_values=parameter_values["atr_stop_multiplier"],
            reward_risk_values=parameter_values["reward_risk_ratio"],
            atr_period=args.atr_period,
        )
    except (MT5ClientError, ValueError) as exc:
        logger.error("%s", exc)
        print(str(exc), file=sys.stderr)
        return 1

    report = run_parameter_stability_report(
        bars=bars,
        symbol=args.symbol,
        timeframe=args.timeframe,
        symbol_info=symbol_info,
        data_source=data_source,
        initial_balance=args.initial_balance,
        risk_config=RiskConfig(
            risk_per_trade_pct=args.risk_per_trade_pct,
            max_daily_loss_pct=args.max_daily_loss_pct,
            max_spread_points=args.max_spread_points,
            one_position_only=True,
            max_lot_per_trade=args.max_lot_per_trade,
        ),
        parameter_grid=parameter_grid,
        parameter_values=parameter_values,
        spread_multipliers=parse_float_list(args.spread_multipliers),
        slippage_points=parse_float_list(args.slippage_points),
        thresholds=StabilityThresholds(
            min_median_profit_factor=args.min_median_profit_factor,
            min_profitable_parameter_pct=args.min_profitable_parameter_pct,
            min_stress_survival_pct=args.min_stress_survival_pct,
            min_stress_profit_factor=args.min_stress_profit_factor,
            neighbor_net_profit_ratio=args.neighbor_net_profit_ratio,
            top_trade_profit_share_max=args.top_trade_profit_share_max,
            concentration_top_trade_count=args.concentration_top_trade_count,
        ),
    )
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True, default=str), encoding="utf-8")
    summary_path.write_text(report["markdown_summary"], encoding="utf-8")
    logger.info("Wrote parameter stability JSON report to %s", json_path)
    logger.info("Wrote parameter stability summary to %s", summary_path)

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True, default=str))
    else:
        print(report["markdown_summary"])
        print(f"\nJSON report: {json_path}")
        print(f"Markdown summary: {summary_path}")
    return 0


def run_parameter_stability_report(
    *,
    bars: Any,
    symbol: str,
    timeframe: str,
    symbol_info: dict[str, Any],
    data_source: dict[str, Any] | None,
    initial_balance: float,
    risk_config: RiskConfig,
    parameter_grid: list[BaselineSignalConfig],
    parameter_values: Mapping[str, list[Any]],
    spread_multipliers: list[float],
    slippage_points: list[float],
    thresholds: StabilityThresholds,
) -> dict[str, Any]:
    report: dict[str, Any] = {
        "project": PROJECT,
        "mode": MODE,
        "orders_sent": 0,
        "symbol": symbol,
        "timeframe": timeframe,
        "status": "PASS",
        "reason_codes": [],
        "warning_flags": [],
        "data_source": data_source or {},
        "strategy_constraints": {
            "ai_model_trading": False,
            "martingale": False,
            "grid": False,
            "lot_increase_after_loss": False,
            "orders_sent": 0,
        },
        "parameter_grid": {
            "fast_sma": list(parameter_values.get("fast_sma", [])),
            "slow_sma": list(parameter_values.get("slow_sma", [])),
            "atr_stop_multiplier": list(parameter_values.get("atr_stop_multiplier", [])),
            "reward_risk_ratio": list(parameter_values.get("reward_risk_ratio", [])),
            "evaluated_parameter_sets": len(parameter_grid),
        },
        "stress_config": {
            "spread_multipliers": spread_multipliers,
            "slippage_points": slippage_points,
        },
        "thresholds": asdict(thresholds),
        "parameter_results": [],
        "diagnostics": {},
        "markdown_summary": "",
    }

    if len(bars) == 0:
        report["status"] = "NO_DATA"
        report["reason_codes"] = [REASON_NO_BACKTEST_DATA]
        report["diagnostics"] = empty_diagnostics()
        report["markdown_summary"] = format_markdown_summary(report)
        return report

    rows: list[dict[str, Any]] = []
    for signal_config in parameter_grid:
        rows.append(
            evaluate_parameter_set(
                bars=bars,
                symbol=symbol,
                timeframe=timeframe,
                symbol_info=symbol_info,
                initial_balance=initial_balance,
                risk_config=risk_config,
                signal_config=signal_config,
                spread_multipliers=spread_multipliers,
                slippage_points=slippage_points,
                thresholds=thresholds,
            )
        )

    rows = sorted(
        rows,
        key=lambda row: (
            float(row["robustness_score"]),
            float(row["net_profit"]),
            float(row["total_trades"]),
        ),
        reverse=True,
    )
    diagnostics = build_stability_diagnostics(
        rows=rows,
        parameter_values=parameter_values,
        thresholds=thresholds,
    )
    warning_flags = list(diagnostics["warning_flags"])
    report["parameter_results"] = rows
    report["diagnostics"] = diagnostics
    report["warning_flags"] = warning_flags
    report["reason_codes"] = warning_flags
    if warning_flags:
        report["status"] = "WARN"
    report["markdown_summary"] = format_markdown_summary(report)
    return report


def evaluate_parameter_set(
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
    thresholds: StabilityThresholds,
) -> dict[str, Any]:
    base_report = run_single_backtest(
        bars=bars,
        symbol=symbol,
        timeframe=timeframe,
        symbol_info=symbol_info,
        initial_balance=initial_balance,
        risk_config=risk_config,
        signal_config=signal_config,
        data_source={"kind": "parameter_stability_base"},
    )
    metrics = compact_metrics(base_report["metrics"])
    stress_results = evaluate_stress_cases(
        bars=bars,
        symbol=symbol,
        timeframe=timeframe,
        symbol_info=symbol_info,
        initial_balance=initial_balance,
        risk_config=risk_config,
        signal_config=signal_config,
        spread_multipliers=spread_multipliers,
        slippage_points=slippage_points,
        thresholds=thresholds,
    )
    survived_count = sum(1 for row in stress_results if row["stress_survived"])
    stress_survival_rate = survived_count / len(stress_results) if stress_results else 0.0
    concentration = calculate_profit_concentration(
        base_report["trades"],
        top_trade_count=thresholds.concentration_top_trade_count,
    )
    robustness_score = calculate_robustness_score(
        metrics=metrics,
        stress_survival_rate=stress_survival_rate,
        initial_balance=initial_balance,
    )
    return {
        "parameters": asdict(signal_config),
        **metrics,
        "robustness_score": robustness_score,
        "stress_survived": bool(stress_results and survived_count == len(stress_results)),
        "stress_survival_rate": stress_survival_rate,
        "stress_results": stress_results,
        "profit_concentration": concentration,
        "orders_sent": 0,
    }


def evaluate_stress_cases(
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
    thresholds: StabilityThresholds,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for spread_multiplier in spread_multipliers:
        for slippage_points_value in slippage_points:
            stressed = apply_spread_slippage(
                bars=bars,
                symbol_info=symbol_info,
                spread_multiplier=spread_multiplier,
                slippage_points=slippage_points_value,
            )
            report = run_single_backtest(
                bars=stressed,
                symbol=symbol,
                timeframe=timeframe,
                symbol_info=symbol_info,
                initial_balance=initial_balance,
                risk_config=risk_config,
                signal_config=signal_config,
                data_source={"kind": "parameter_stability_stress"},
            )
            metrics = compact_metrics(report["metrics"])
            row = {
                "spread_multiplier": spread_multiplier,
                "slippage_points": slippage_points_value,
                **metrics,
            }
            row["stress_survived"] = stress_case_survived(row, thresholds)
            rows.append(row)
    return rows


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


def build_stability_diagnostics(
    *,
    rows: list[dict[str, Any]],
    parameter_values: Mapping[str, list[Any]],
    thresholds: StabilityThresholds,
) -> dict[str, Any]:
    if not rows:
        return empty_diagnostics()

    best_row = rows[0]
    net_profits = [float(row["net_profit"]) for row in rows]
    pf_scores = [row_profit_factor_score(row) for row in rows]
    median_net_profit = float(median(net_profits))
    median_profit_factor = float(median(pf_scores))
    profitable_pct = ratio(sum(1 for value in net_profits if value > 0), len(rows))
    pf_gt_110_pct = ratio(sum(1 for score in pf_scores if score > 1.10), len(rows))
    stress_survival_pct = ratio(sum(1 for row in rows if row["stress_survived"]), len(rows))
    neighbors = find_neighbor_rows(best_row, rows, parameter_values)
    neighbor_net_profits = [float(row["net_profit"]) for row in neighbors]
    neighbor_scores = [float(row["robustness_score"]) for row in neighbors]
    best_net_profit = float(best_row["net_profit"])
    performance_gap = best_net_profit - median_net_profit
    diagnostics = {
        "best_parameters": best_row["parameters"],
        "best_metrics": metrics_without_stress(best_row),
        "top_parameter_clusters": build_top_parameter_clusters(rows, parameter_values),
        "neighboring_parameter_performance": {
            "neighbor_count": len(neighbors),
            "average_neighbor_net_profit": average(neighbor_net_profits),
            "average_neighbor_robustness_score": average(neighbor_scores),
            "best_to_neighbor_net_profit_ratio": (
                best_net_profit / average(neighbor_net_profits)
                if average(neighbor_net_profits) and average(neighbor_net_profits) != 0
                else None
            ),
            "neighbors": [
                {
                    "parameters": row["parameters"],
                    "net_profit": row["net_profit"],
                    "profit_factor": row["profit_factor"],
                    "robustness_score": row["robustness_score"],
                }
                for row in neighbors
            ],
        },
        "best_vs_median_performance_gap": {
            "best_net_profit": best_net_profit,
            "median_net_profit": median_net_profit,
            "absolute_gap": performance_gap,
            "ratio_to_abs_median": performance_gap / max(abs(median_net_profit), 1.0),
        },
        "median_metrics": {
            "net_profit": median_net_profit,
            "profit_factor_score": median_profit_factor,
        },
        "percent_profitable_parameter_sets": profitable_pct,
        "percent_profit_factor_gt_1_10": pf_gt_110_pct,
        "percent_stress_survived": stress_survival_pct,
        "evaluated_parameter_sets": len(rows),
    }
    diagnostics["warning_flags"] = detect_overfit_warning_flags(
        diagnostics=diagnostics,
        best_row=best_row,
        thresholds=thresholds,
    )
    return diagnostics


def detect_overfit_warning_flags(
    *,
    diagnostics: Mapping[str, Any],
    best_row: Mapping[str, Any],
    thresholds: StabilityThresholds,
) -> list[str]:
    flags: list[str] = []
    best_net_profit = float(best_row["net_profit"])
    neighbor = diagnostics["neighboring_parameter_performance"]
    neighbor_count = int(neighbor["neighbor_count"])
    average_neighbor_net_profit = neighbor["average_neighbor_net_profit"]
    if best_net_profit > 0:
        if neighbor_count == 0 or average_neighbor_net_profit is None:
            flags.append(WARNING_BEST_PARAM_ISOLATED)
        elif float(average_neighbor_net_profit) < best_net_profit * thresholds.neighbor_net_profit_ratio:
            flags.append(WARNING_BEST_PARAM_ISOLATED)

    median_metrics = diagnostics["median_metrics"]
    if (
        float(median_metrics["net_profit"]) <= 0
        or float(median_metrics["profit_factor_score"]) < thresholds.min_median_profit_factor
    ):
        flags.append(WARNING_MEDIAN_PARAM_WEAK)

    if float(diagnostics["percent_profitable_parameter_sets"]) < thresholds.min_profitable_parameter_pct:
        flags.append(WARNING_TOO_FEW_PROFITABLE_PARAMS)

    if float(diagnostics["percent_stress_survived"]) < thresholds.min_stress_survival_pct:
        flags.append(WARNING_STRESS_TEST_FRAGILE)

    concentration = best_row.get("profit_concentration", {})
    if float(concentration.get("top_trade_profit_share", 0.0)) > thresholds.top_trade_profit_share_max:
        flags.append(WARNING_PROFIT_CONCENTRATED_IN_FEW_TRADES)

    return flags


def build_top_parameter_clusters(
    rows: list[dict[str, Any]],
    parameter_values: Mapping[str, list[Any]],
) -> list[dict[str, Any]]:
    top_count = min(len(rows), max(1, math.ceil(len(rows) * 0.20)))
    top_rows = rows[:top_count]
    clusters: list[list[dict[str, Any]]] = []
    visited: set[int] = set()
    for index, row in enumerate(top_rows):
        if index in visited:
            continue
        stack = [index]
        cluster: list[dict[str, Any]] = []
        visited.add(index)
        while stack:
            current_index = stack.pop()
            current = top_rows[current_index]
            cluster.append(current)
            for other_index, other in enumerate(top_rows):
                if other_index in visited:
                    continue
                distance = parameter_distance(current, other, parameter_values)
                if distance is not None and distance <= 1:
                    visited.add(other_index)
                    stack.append(other_index)
        clusters.append(cluster)

    summaries: list[dict[str, Any]] = []
    for cluster_id, cluster in enumerate(clusters, start=1):
        summaries.append(
            {
                "cluster_id": cluster_id,
                "size": len(cluster),
                "average_net_profit": average([float(row["net_profit"]) for row in cluster]),
                "average_robustness_score": average([float(row["robustness_score"]) for row in cluster]),
                "parameter_ranges": parameter_ranges(cluster),
                "members": [row["parameters"] for row in cluster],
            }
        )
    return sorted(summaries, key=lambda item: (item["size"], item["average_robustness_score"]), reverse=True)


def find_neighbor_rows(
    best_row: Mapping[str, Any],
    rows: list[dict[str, Any]],
    parameter_values: Mapping[str, list[Any]],
) -> list[dict[str, Any]]:
    neighbors: list[dict[str, Any]] = []
    for row in rows:
        if row is best_row:
            continue
        distance = parameter_distance(best_row, row, parameter_values)
        if distance == 1:
            neighbors.append(row)
    return sorted(neighbors, key=lambda row: float(row["robustness_score"]), reverse=True)


def parameter_distance(
    left: Mapping[str, Any],
    right: Mapping[str, Any],
    parameter_values: Mapping[str, list[Any]],
) -> int | None:
    distance = 0
    left_parameters = left["parameters"]
    right_parameters = right["parameters"]
    for name in PARAMETER_NAMES:
        values = list(parameter_values.get(name, []))
        left_index = parameter_value_index(values, left_parameters[name])
        right_index = parameter_value_index(values, right_parameters[name])
        if left_index is None or right_index is None:
            return None
        distance += abs(left_index - right_index)
    return distance


def parameter_value_index(values: list[Any], value: Any) -> int | None:
    for index, candidate in enumerate(values):
        if float(candidate) == float(value):
            return index
    return None


def parameter_ranges(cluster: list[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    ranges: dict[str, dict[str, Any]] = {}
    for name in PARAMETER_NAMES:
        values = [row["parameters"][name] for row in cluster]
        ranges[name] = {"min": min(values), "max": max(values)}
    return ranges


def calculate_robustness_score(
    *,
    metrics: Mapping[str, Any],
    stress_survival_rate: float,
    initial_balance: float,
) -> float:
    net_profit = float(metrics["net_profit"])
    profit_score = clamp(net_profit / max(initial_balance * 0.02, 1.0), 0.0, 1.0)
    pf_score = row_profit_factor_score(metrics)
    pf_component = clamp((pf_score - 0.75) / 0.75, 0.0, 1.0)
    drawdown_component = 1.0 - clamp(float(metrics["max_drawdown_pct"]) / 0.10, 0.0, 1.0)
    trade_component = clamp(float(metrics["total_trades"]) / 30.0, 0.0, 1.0)
    average_r_component = clamp((float(metrics["average_r"]) + 0.25) / 0.75, 0.0, 1.0)
    score = (
        0.25 * profit_score
        + 0.25 * pf_component
        + 0.20 * stress_survival_rate
        + 0.15 * drawdown_component
        + 0.10 * trade_component
        + 0.05 * average_r_component
    )
    return round(score, 4)


def stress_case_survived(row: Mapping[str, Any], thresholds: StabilityThresholds) -> bool:
    return (
        int(row["total_trades"]) > 0
        and float(row["net_profit"]) > 0
        and row_profit_factor_score(row) >= thresholds.min_stress_profit_factor
    )


def calculate_profit_concentration(trades: list[Mapping[str, Any]], *, top_trade_count: int) -> dict[str, Any]:
    positive_pnls = sorted([float(trade["pnl"]) for trade in trades if float(trade["pnl"]) > 0], reverse=True)
    gross_profit = sum(positive_pnls)
    top_profit = sum(positive_pnls[:top_trade_count])
    return {
        "top_trade_count": top_trade_count,
        "gross_profit": gross_profit,
        "top_trade_profit": top_profit,
        "top_trade_profit_share": top_profit / gross_profit if gross_profit > 0 else 0.0,
    }


def metrics_without_stress(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "total_trades": row["total_trades"],
        "win_rate": row["win_rate"],
        "net_profit": row["net_profit"],
        "profit_factor": row["profit_factor"],
        "max_drawdown": row["max_drawdown"],
        "average_r": row["average_r"],
        "max_consecutive_losses": row["max_consecutive_losses"],
        "robustness_score": row["robustness_score"],
        "stress_survival_rate": row["stress_survival_rate"],
        "profit_concentration": row["profit_concentration"],
    }


def empty_diagnostics() -> dict[str, Any]:
    return {
        "best_parameters": None,
        "best_metrics": None,
        "top_parameter_clusters": [],
        "neighboring_parameter_performance": {
            "neighbor_count": 0,
            "average_neighbor_net_profit": None,
            "average_neighbor_robustness_score": None,
            "best_to_neighbor_net_profit_ratio": None,
            "neighbors": [],
        },
        "best_vs_median_performance_gap": {
            "best_net_profit": 0.0,
            "median_net_profit": 0.0,
            "absolute_gap": 0.0,
            "ratio_to_abs_median": 0.0,
        },
        "median_metrics": {"net_profit": 0.0, "profit_factor_score": 0.0},
        "percent_profitable_parameter_sets": 0.0,
        "percent_profit_factor_gt_1_10": 0.0,
        "percent_stress_survived": 0.0,
        "evaluated_parameter_sets": 0,
        "warning_flags": [],
    }


def row_profit_factor_score(row: Mapping[str, Any]) -> float:
    value = row.get("profit_factor")
    if value is None:
        return 2.0 if int(row.get("total_trades", 0)) > 0 and float(row.get("net_profit", 0.0)) > 0 else 0.0
    return float(value)


def ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def average(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def format_markdown_summary(report: Mapping[str, Any]) -> str:
    diagnostics = report["diagnostics"]
    lines = [
        "# Parameter Stability Report",
        "",
        f"- Project: `{report['project']}`",
        f"- Symbol/timeframe: `{report['symbol']} {report['timeframe']}`",
        f"- Status: `{report['status']}`",
        f"- Orders sent: `{report['orders_sent']}`",
        f"- Evaluated parameter sets: `{report['parameter_grid']['evaluated_parameter_sets']}`",
        "",
        "## Overfit Warnings",
        "",
    ]
    if report["warning_flags"]:
        for flag in report["warning_flags"]:
            lines.append(f"- `{flag}`")
    else:
        lines.append("- None")

    lines.extend(
        [
            "",
            "## Stability Diagnostics",
            "",
            f"- Profitable parameter sets: `{diagnostics['percent_profitable_parameter_sets'] * 100:.2f}%`",
            f"- Profit factor > 1.10: `{diagnostics['percent_profit_factor_gt_1_10'] * 100:.2f}%`",
            f"- Stress survival: `{diagnostics['percent_stress_survived'] * 100:.2f}%`",
            "",
            "## Top Parameter Sets",
            "",
            "| Rank | Fast | Slow | ATR Stop | RR | Trades | Net Profit | Profit Factor | Max DD | Avg R | Robustness |",
            "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for rank, row in enumerate(report.get("parameter_results", [])[:10], start=1):
        params = row["parameters"]
        pf = row["profit_factor"]
        pf_text = "n/a" if pf is None else f"{float(pf):.2f}"
        lines.append(
            "| {rank} | {fast} | {slow} | {atr:.2f} | {rr:.2f} | {trades} | {net:.2f} | {pf} | {dd:.2f} | {avg_r:.3f} | {score:.4f} |".format(
                rank=rank,
                fast=params["fast_sma"],
                slow=params["slow_sma"],
                atr=params["atr_stop_multiplier"],
                rr=params["reward_risk_ratio"],
                trades=row["total_trades"],
                net=row["net_profit"],
                pf=pf_text,
                dd=row["max_drawdown"],
                avg_r=row["average_r"],
                score=row["robustness_score"],
            )
        )
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run baseline parameter stability and overfit diagnostics without sending orders."
    )
    parser.add_argument("--symbol", default=os.getenv("XM_GOLD_SYMBOL", "GOLD_"))
    parser.add_argument("--timeframe", default="M15", choices=("M1", "M5", "M15", "M30", "H1", "H4", "D1"))
    parser.add_argument("--input", default="data/gold_m15.csv")
    parser.add_argument("--bars", type=int, default=5_000)
    parser.add_argument("--output-json", default="reports/backtests/parameter_stability_report.json")
    parser.add_argument("--output-summary", default="reports/backtests/parameter_stability_summary.md")
    parser.add_argument("--initial-balance", type=float, default=10_000.0)
    parser.add_argument("--risk-per-trade-pct", type=float, default=0.25)
    parser.add_argument("--max-daily-loss-pct", type=float, default=1.0)
    parser.add_argument("--max-spread-points", type=float, default=1_000.0)
    parser.add_argument("--max-lot-per-trade", type=float, default=None)
    parser.add_argument("--atr-period", type=int, default=14)
    parser.add_argument("--fast-sma-values", default="10,20")
    parser.add_argument("--slow-sma-values", default="40,50")
    parser.add_argument("--atr-stop-multipliers", default="1.0,1.5")
    parser.add_argument("--reward-risk-ratios", default="1.0,1.5")
    parser.add_argument("--spread-multipliers", default="1.0,1.5,2.0")
    parser.add_argument("--slippage-points", default="0,10,20")
    parser.add_argument("--min-median-profit-factor", type=float, default=1.0)
    parser.add_argument("--min-profitable-parameter-pct", type=float, default=0.35)
    parser.add_argument("--min-stress-survival-pct", type=float, default=0.50)
    parser.add_argument("--min-stress-profit-factor", type=float, default=1.0)
    parser.add_argument("--neighbor-net-profit-ratio", type=float, default=0.35)
    parser.add_argument("--top-trade-profit-share-max", type=float, default=0.50)
    parser.add_argument("--concentration-top-trade-count", type=int, default=3)
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
