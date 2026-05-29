from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.broker.mt5_client import MT5Client, MT5ClientError, MT5ConnectionConfig
from src.broker.order_executor import TradingConfig, load_trading_config
from src.cli_contract import EXIT_CONTROLLED, event_exit_code
from src.logging_config import configure_logging
from src.runtime.lock import DEFAULT_EMERGENCY_STOP_PATH, emergency_stop_file_decision
from src.strategy.baseline_signal import BaselineSignalConfig, BaselineSignalGenerator, TradeSignal
from src.strategy.risk_manager import (
    AccountState,
    REASON_LOT_BELOW_VOLUME_MIN,
    REASON_MAX_SPREAD_EXCEEDED,
    RiskDecision,
    RiskManager,
    TradeRiskRequest,
    spread_points_from_prices,
)


PROJECT = "xm-gold-ai-trader"
MODE = "live_dry_run_signal_journal"
JOURNAL_SCHEMA_VERSION = 1
DEFAULT_JOURNAL_DIR = Path("logs/dry_run_signals")
DEFAULT_PARAMETER_REPORT = Path("reports/backtests/parameter_stability_report.json")

REASON_MT5_CONNECTION_FAILED = "MT5_CONNECTION_FAILED"
REASON_NO_ACTIONABLE_SIGNAL = "NO_ACTIONABLE_SIGNAL"
REASON_NO_RECENT_BARS = "NO_RECENT_BARS"
REASON_RISK_NOT_EVALUATED = "RISK_NOT_EVALUATED"
REASON_SKIP_DUPLICATE_BAR = "SKIP_DUPLICATE_BAR"


def main() -> int:
    args = parse_args()
    logger = configure_logging(logger_name="live_dry_run_signal_journal")

    try:
        if args.loop:
            payload = run_loop(args)
        else:
            payload = observe_once(args)
    except Exception as exc:  # pragma: no cover - defensive CLI guard.
        logger.exception("live dry-run signal journal failed")
        print(str(exc), file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True, default=str))
    elif payload.get("mode") == MODE:
        print_summary(payload)
    else:
        print_loop_summary(payload)

    if payload.get("mode") == MODE:
        return event_exit_code(payload)
    return EXIT_CONTROLLED


def run_loop(
    args: argparse.Namespace,
    *,
    client_factory: Callable[[MT5ConnectionConfig], Any] = MT5Client,
    sleep: Callable[[float], None] = time.sleep,
    journal_dir: Path | None = None,
    emergency_stop_path: Path | None = None,
) -> dict[str, Any]:
    max_iterations = args.max_iterations
    if max_iterations is not None and max_iterations <= 0:
        raise ValueError("--max-iterations must be positive when provided")

    observations: list[dict[str, Any]] = []
    iteration = 0
    while True:
        iteration += 1
        observations.append(
            observe_once(
                args,
                client_factory=client_factory,
                journal_dir=journal_dir,
                emergency_stop_path=emergency_stop_path,
            )
        )
        if max_iterations is not None and iteration >= max_iterations:
            break
        sleep(float(args.interval_seconds))

    signal_count = sum(1 for event in observations if event.get("final_decision") == "SIGNAL")
    block_count = sum(1 for event in observations if event.get("final_decision") == "BLOCK")
    skip_count = sum(1 for event in observations if event.get("final_decision") == "SKIP")
    return {
        "project": PROJECT,
        "mode": f"{MODE}_loop",
        "campaign_id": getattr(args, "campaign_id", None),
        "orders_sent": 0,
        "iterations": len(observations),
        "signal_count": signal_count,
        "block_count": block_count,
        "skip_count": skip_count,
        "journal_paths": [event.get("journal_path") for event in observations if event.get("journal_path")],
        "observations": observations,
    }


def observe_once(
    args: argparse.Namespace,
    *,
    client_factory: Callable[[MT5ConnectionConfig], Any] = MT5Client,
    journal_dir: Path | None = None,
    emergency_stop_path: Path | None = None,
) -> dict[str, Any]:
    try:
        import pandas as pd
    except ImportError as exc:
        raise RuntimeError("pandas is required for live dry-run signal journaling. Install requirements.txt.") from exc

    config = load_or_default_config(args.config)
    symbol = args.symbol or config.symbol
    if args.symbol:
        config = replace(config, symbol=symbol, execution=replace(config.execution, require_symbol=symbol))

    signal_config, parameter_source = selected_signal_config(args)
    stop_path = emergency_stop_path or DEFAULT_EMERGENCY_STOP_PATH
    emergency_decision = emergency_stop_file_decision(stop_path)
    pre_reason_codes = list(emergency_decision.reason_codes)
    pre_reasons = list(emergency_decision.reasons)

    try:
        with client_factory(build_connection_config(args, symbol)) as client:
            if hasattr(client, "ensure_symbol"):
                client.ensure_symbol(symbol)
            account = client.get_account_info()
            symbol_info = client.get_symbol_info(symbol)
            tick = client.get_symbol_tick(symbol)
            rates = client.copy_rates_from_pos(symbol, args.timeframe, args.bars, start_pos=args.start_pos)
            bars = normalize_rates(rates, pd)
            if bars.empty:
                event = build_event(
                    args=args,
                    config=config,
                    signal_config=signal_config,
                    parameter_source=parameter_source,
                    final_decision="BLOCK",
                    reason_codes=append_unique(pre_reason_codes, REASON_NO_RECENT_BARS),
                    reasons=pre_reasons + [f"{REASON_NO_RECENT_BARS}: MT5 returned no recent bars"],
                    account=result_to_dict(account),
                    symbol_info=result_to_dict(symbol_info),
                    tick=result_to_dict(tick),
                    bars=bars,
                    signal=None,
                    risk_decision=None,
                    current_spread=None,
                    open_positions_count=None,
                )
                return write_journal(journal_dir or Path(args.journal_dir), event)

            latest_closed_bar_time = str(bars.iloc[-1]["time"])
            if getattr(args, "bar_close_only", False):
                previous = most_recent_closed_bar_journal(
                    journal_dir=journal_dir or Path(args.journal_dir),
                    symbol=symbol,
                    timeframe=args.timeframe,
                    campaign_id=getattr(args, "campaign_id", None),
                )
                if previous is not None and not is_newer_closed_bar(latest_closed_bar_time, previous):
                    return build_event(
                        args=args,
                        config=config,
                        signal_config=signal_config,
                        parameter_source=parameter_source,
                        final_decision="SKIP",
                        reason_codes=[REASON_SKIP_DUPLICATE_BAR],
                        reasons=[
                            f"{REASON_SKIP_DUPLICATE_BAR}: latest closed bar {latest_closed_bar_time} "
                            f"is not newer than previous journal {previous}"
                        ],
                        account=account.raw,
                        symbol_info=symbol_info.raw,
                        tick=tick.raw,
                        bars=bars,
                        signal=None,
                        risk_decision=None,
                        current_spread=spread_points_from_prices(tick.bid, tick.ask, symbol_info.point),
                        open_positions_count=None,
                    )

            signal = BaselineSignalGenerator(signal_config).generate(bars, symbol)
            current_spread = spread_points_from_prices(tick.bid, tick.ask, symbol_info.point)
            positions = client.get_open_positions(symbol)
            daily_pnl = client.get_daily_realized_pnl(symbol)
            risk_decision = assess_signal(
                config=config,
                signal=signal,
                symbol_info=symbol_info.raw,
                account=account.raw,
                daily_pnl=daily_pnl,
                current_spread=current_spread,
                positions=positions,
            )
            final_decision, reason_codes, reasons = final_signal_decision(
                signal=signal,
                risk_decision=risk_decision,
                pre_reason_codes=pre_reason_codes,
                pre_reasons=pre_reasons,
                current_spread=current_spread,
                max_spread_points=config.risk.max_spread_points,
            )
            event = build_event(
                args=args,
                config=config,
                signal_config=signal_config,
                parameter_source=parameter_source,
                final_decision=final_decision,
                reason_codes=reason_codes,
                reasons=reasons,
                account=account.raw,
                symbol_info=symbol_info.raw,
                tick=tick.raw,
                bars=bars,
                signal=signal,
                risk_decision=risk_decision,
                current_spread=current_spread,
                open_positions_count=len(positions),
            )
            return write_journal(journal_dir or Path(args.journal_dir), event)
    except MT5ClientError as exc:
        event = build_event(
            args=args,
            config=config,
            signal_config=signal_config,
            parameter_source=parameter_source,
            final_decision="BLOCK",
            reason_codes=append_unique(pre_reason_codes, REASON_MT5_CONNECTION_FAILED),
            reasons=pre_reasons + [f"{REASON_MT5_CONNECTION_FAILED}: {exc}"],
            account=None,
            symbol_info=None,
            tick=None,
            bars=None,
            signal=None,
            risk_decision=None,
            current_spread=None,
            open_positions_count=None,
        )
        return write_journal(journal_dir or Path(args.journal_dir), event)


def normalize_rates(rates: Any, pd: Any) -> Any:
    bars = pd.DataFrame(rates)
    if bars.empty:
        return bars
    bars.columns = [str(column).lower() for column in bars.columns]
    if "time" not in bars.columns:
        raise MT5ClientError("copy_rates_from_pos returned bars without time")
    if pd.api.types.is_numeric_dtype(bars["time"]):
        bars["time"] = pd.to_datetime(bars["time"], unit="s", utc=True)
    else:
        bars["time"] = pd.to_datetime(bars["time"], utc=True)
    for column in ("open", "high", "low", "close"):
        if column not in bars.columns:
            raise MT5ClientError(f"copy_rates_from_pos returned bars without {column}")
        bars[column] = bars[column].astype(float)
    if "spread" in bars.columns:
        bars["spread"] = bars["spread"].astype(float)
    return bars.sort_values("time").reset_index(drop=True)


def assess_signal(
    *,
    config: TradingConfig,
    signal: TradeSignal,
    symbol_info: dict[str, Any],
    account: dict[str, Any],
    daily_pnl: float,
    current_spread: float,
    positions: list[Any],
) -> RiskDecision | None:
    if not signal.is_actionable:
        return None
    return RiskManager(config.risk).assess_trade(
        TradeRiskRequest(
            symbol_info=symbol_info,
            account=AccountState(
                balance=float(account["balance"]),
                equity=float(account["equity"]),
                daily_realized_pnl=daily_pnl,
            ),
            side=signal.side,
            entry_price=float(signal.entry_price),
            stop_loss_price=float(signal.stop_loss_price),
            take_profit_price=signal.take_profit_price,
            current_spread_points=current_spread,
            open_positions=positions,
        )
    )


def final_signal_decision(
    *,
    signal: TradeSignal,
    risk_decision: RiskDecision | None,
    pre_reason_codes: list[str],
    pre_reasons: list[str],
    current_spread: float,
    max_spread_points: float,
) -> tuple[str, list[str], list[str]]:
    reason_codes = list(pre_reason_codes)
    reasons = list(pre_reasons)

    if current_spread > max_spread_points:
        add_reason(
            reason_codes,
            reasons,
            REASON_MAX_SPREAD_EXCEEDED,
            f"spread too wide: {current_spread:.1f} > {max_spread_points:.1f} points",
        )

    if not signal.is_actionable:
        add_reason(reason_codes, reasons, REASON_NO_ACTIONABLE_SIGNAL, signal.reason or "baseline signal is HOLD")
    elif risk_decision is None:
        add_reason(reason_codes, reasons, REASON_RISK_NOT_EVALUATED, "no risk preview was produced")
    elif not risk_decision.allowed:
        for code, reason in zip(risk_decision.reason_codes, risk_decision.reasons):
            add_reason(reason_codes, reasons, code, reason.removeprefix(f"{code}: "))

    if reason_codes:
        return "BLOCK", reason_codes, reasons
    return "SIGNAL", [], []


def build_event(
    *,
    args: argparse.Namespace,
    config: TradingConfig,
    signal_config: BaselineSignalConfig,
    parameter_source: str,
    final_decision: str,
    reason_codes: list[str],
    reasons: list[str],
    account: dict[str, Any] | None,
    symbol_info: dict[str, Any] | None,
    tick: dict[str, Any] | None,
    bars: Any | None,
    signal: TradeSignal | None,
    risk_decision: RiskDecision | None,
    current_spread: float | None,
    open_positions_count: int | None,
) -> dict[str, Any]:
    latest_closed_bar_time = None
    if bars is not None and len(bars) > 0:
        latest_closed_bar_time = str(bars.iloc[-1]["time"])
    return {
        "journal_schema_version": JOURNAL_SCHEMA_VERSION,
        "project": PROJECT,
        "mode": MODE,
        "campaign_id": getattr(args, "campaign_id", None),
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "account": compact_account(account),
        "symbol": compact_symbol(symbol_info) if symbol_info is not None else None,
        "tick": compact_tick(tick),
        "timeframe": args.timeframe,
        "bars_used": int(len(bars)) if bars is not None else 0,
        "latest_closed_bar_time": latest_closed_bar_time,
        "selected_parameters": asdict(signal_config),
        "selected_parameters_source": parameter_source,
        "signal": asdict(signal) if signal is not None else None,
        "risk_preview": risk_preview_payload(risk_decision, current_spread, config.risk.max_spread_points),
        "current_spread_points": current_spread,
        "open_positions_count": open_positions_count,
        "config": {
            "symbol": config.symbol,
            "magic_number": config.magic_number,
            "execution": asdict(config.execution),
            "risk": asdict(config.risk),
        },
        "final_decision": final_decision,
        "reason_codes": reason_codes,
        "reasons": reasons,
        "orders_sent": 0,
        "order_check_called": False,
        "order_send_called": False,
        "journal_path": None,
    }


def risk_preview_payload(
    decision: RiskDecision | None,
    current_spread: float | None,
    max_spread_points: float,
) -> dict[str, Any]:
    spread_allowed = None if current_spread is None else current_spread <= max_spread_points
    payload: dict[str, Any] = {
        "evaluated": decision is not None,
        "allowed": decision.allowed if decision is not None else False,
        "volume": decision.volume if decision is not None else 0.0,
        "reason_codes": list(decision.reason_codes) if decision is not None else [],
        "reasons": list(decision.reasons) if decision is not None else [],
        "risk_amount": decision.risk_amount if decision is not None else 0.0,
        "risk_per_lot": decision.risk_per_lot if decision is not None else 0.0,
        "stop_distance_points": decision.stop_distance_points if decision is not None else None,
        "take_profit_distance_points": decision.take_profit_distance_points if decision is not None else None,
        "spread_filter": {
            "current_spread_points": current_spread,
            "max_spread_points": max_spread_points,
            "allowed": spread_allowed,
        },
    }
    if REASON_LOT_BELOW_VOLUME_MIN in payload["reason_codes"]:
        payload["lot_below_minimum"] = True
    else:
        payload["lot_below_minimum"] = False
    return payload


def selected_signal_config(args: argparse.Namespace) -> tuple[BaselineSignalConfig, str]:
    report_path = Path(args.parameter_report)
    if report_path.exists():
        try:
            payload = json.loads(report_path.read_text(encoding="utf-8"))
            parameters = payload.get("diagnostics", {}).get("best_parameters")
            if not isinstance(parameters, dict):
                results = payload.get("parameter_results") or []
                if results and isinstance(results[0], dict):
                    parameters = results[0].get("parameters")
            if isinstance(parameters, dict):
                return (
                    BaselineSignalConfig(
                        fast_sma=int(parameters["fast_sma"]),
                        slow_sma=int(parameters["slow_sma"]),
                        atr_period=int(parameters.get("atr_period", args.atr_period)),
                        atr_stop_multiplier=float(parameters["atr_stop_multiplier"]),
                        reward_risk_ratio=float(parameters["reward_risk_ratio"]),
                    ),
                    str(report_path),
                )
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
            pass
    return (
        BaselineSignalConfig(
            fast_sma=args.fallback_fast_sma,
            slow_sma=args.fallback_slow_sma,
            atr_period=args.atr_period,
            atr_stop_multiplier=args.fallback_atr_stop_multiplier,
            reward_risk_ratio=args.fallback_reward_risk_ratio,
        ),
        "cli_fallback",
    )


def write_journal(journal_dir: Path, event: dict[str, Any]) -> dict[str, Any]:
    journal_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    path = journal_dir / f"live_dry_run_signal_{timestamp}.json"
    event["journal_path"] = str(path)
    path.write_text(json.dumps(event, indent=2, sort_keys=True, default=str), encoding="utf-8")
    return event


def most_recent_closed_bar_journal(
    *,
    journal_dir: Path,
    symbol: str,
    timeframe: str,
    campaign_id: str | None,
) -> str | None:
    if not journal_dir.exists():
        return None
    latest: str | None = None
    latest_dt: datetime | None = None
    for path in sorted(journal_dir.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        if payload.get("timeframe") != timeframe:
            continue
        if payload.get("campaign_id") != campaign_id:
            continue
        payload_symbol = payload.get("symbol")
        payload_symbol_name = payload_symbol.get("name") if isinstance(payload_symbol, dict) else None
        payload_config = payload.get("config")
        payload_config_symbol = payload_config.get("symbol") if isinstance(payload_config, dict) else None
        if symbol not in {payload_symbol_name, payload_config_symbol}:
            continue
        closed_bar_time = payload.get("latest_closed_bar_time")
        parsed = parse_bar_time(closed_bar_time)
        if parsed is None:
            continue
        if latest_dt is None or parsed > latest_dt:
            latest_dt = parsed
            latest = str(closed_bar_time)
    return latest


def is_newer_closed_bar(candidate: str, previous: str) -> bool:
    candidate_dt = parse_bar_time(candidate)
    previous_dt = parse_bar_time(previous)
    if candidate_dt is None or previous_dt is None:
        return candidate != previous
    return candidate_dt > previous_dt


def parse_bar_time(value: Any) -> datetime | None:
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def append_unique(codes: list[str], code: str) -> list[str]:
    output = list(codes)
    if code not in output:
        output.append(code)
    return output


def add_reason(codes: list[str], reasons: list[str], code: str, reason: str) -> None:
    if code not in codes:
        codes.append(code)
        reasons.append(f"{code}: {reason}")


def compact_account(account: dict[str, Any] | None) -> dict[str, Any]:
    if account is None:
        return {"login": None, "server": None, "balance": None, "equity": None, "currency": None, "trade_mode": None}
    return {
        "login": account.get("login"),
        "server": account.get("server"),
        "balance": account.get("balance"),
        "equity": account.get("equity"),
        "currency": account.get("currency"),
        "trade_mode": account.get("trade_mode"),
    }


def compact_symbol(symbol: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "name",
        "description",
        "path",
        "point",
        "spread",
        "digits",
        "trade_tick_size",
        "trade_tick_value",
        "trade_contract_size",
        "volume_min",
        "volume_max",
        "volume_step",
        "trade_stops_level",
        "trade_mode",
    )
    return {key: symbol.get(key) for key in keys}


def compact_tick(tick: dict[str, Any] | None) -> dict[str, Any]:
    if tick is None:
        return {"bid": None, "ask": None, "last": None, "time": None}
    return {"bid": tick.get("bid"), "ask": tick.get("ask"), "last": tick.get("last"), "time": tick.get("time")}


def result_to_dict(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    raw = getattr(value, "raw", None)
    if isinstance(raw, dict):
        return raw
    if hasattr(value, "_asdict"):
        return dict(value._asdict())
    return dict(vars(value))


def load_or_default_config(path: str) -> TradingConfig:
    config_path = Path(path)
    if config_path.exists():
        return load_trading_config(config_path)
    return TradingConfig()


def build_connection_config(args: argparse.Namespace, symbol: str) -> MT5ConnectionConfig:
    return MT5ConnectionConfig(
        symbol=symbol,
        terminal_path=args.terminal_path,
        login=args.login,
        password=args.password,
        server=args.server,
        timeout_ms=args.timeout_ms,
    )


def print_summary(payload: dict[str, Any]) -> None:
    print("xm-gold-ai-trader live dry-run signal journal")
    print(f"final decision: {payload['final_decision']}")
    if payload["reason_codes"]:
        print(f"reason codes: {', '.join(payload['reason_codes'])}")
    print(f"symbol: {payload['config']['symbol']} | timeframe: {payload['timeframe']}")
    print(f"latest closed bar: {payload['latest_closed_bar_time']}")
    print(f"spread points: {payload['current_spread_points']}")
    signal = payload.get("signal") or {}
    print(f"signal: {signal.get('side')} | {signal.get('reason')}")
    print(f"journal: {payload['journal_path']}")
    print("orders_sent: 0")


def print_loop_summary(payload: dict[str, Any]) -> None:
    print("xm-gold-ai-trader live dry-run signal journal loop")
    print(f"iterations: {payload['iterations']}")
    print(f"signals: {payload['signal_count']}")
    print(f"blocks: {payload['block_count']}")
    print(f"skips: {payload['skip_count']}")
    print("orders_sent: 0")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Observe live GOLD_ baseline signals and write dry-run journals.")
    parser.add_argument("--config", default="configs/xm_gold_ai_trader.demo.yaml")
    parser.add_argument("--symbol", default=os.getenv("XM_GOLD_SYMBOL"))
    parser.add_argument("--timeframe", default="M15", choices=("M1", "M5", "M15", "M30", "H1", "H4", "D1"))
    parser.add_argument("--bars", type=int, default=250)
    parser.add_argument("--start-pos", type=int, default=1, help="MT5 bar offset; 1 uses the latest closed bar.")
    parser.add_argument("--parameter-report", default=str(DEFAULT_PARAMETER_REPORT))
    parser.add_argument("--journal-dir", default=str(DEFAULT_JOURNAL_DIR))
    parser.add_argument("--campaign-id", default=None)
    parser.add_argument("--bar-close-only", action="store_true")
    parser.add_argument("--fallback-fast-sma", type=int, default=10)
    parser.add_argument("--fallback-slow-sma", type=int, default=40)
    parser.add_argument("--atr-period", type=int, default=14)
    parser.add_argument("--fallback-atr-stop-multiplier", type=float, default=1.5)
    parser.add_argument("--fallback-reward-risk-ratio", type=float, default=1.5)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--once", action="store_true", help="Run one observation and exit.")
    mode.add_argument("--loop", action="store_true", help="Poll repeatedly without sending orders.")
    parser.add_argument("--interval-seconds", type=float, default=60.0)
    parser.add_argument("--max-iterations", type=int, default=None)
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
