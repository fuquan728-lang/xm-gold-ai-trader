from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.preflight_order_check import (
    build_connection_config,
    get_orders_today,
    load_or_default_config,
    result_to_dict,
    risk_decision_to_dict,
)
from src.broker.execution_safety import (
    evaluate_execution_safety,
    order_check_failure_decision,
    order_check_passed,
)
from src.broker.mt5_client import MT5Client, MT5ClientError
from src.broker.order_executor import TradingConfig
from src.cli_contract import EXIT_RUNTIME_FAILURE, event_exit_code
from src.logging_config import configure_logging
from src.strategy.risk_manager import (
    AccountState,
    RiskConfig,
    RiskManager,
    TradeRiskRequest,
    spread_points_from_prices,
)


REASON_RISK_PCT_EXCEEDS_CONFIG_LIMIT = "RISK_PCT_EXCEEDS_CONFIG_LIMIT"
DEFAULT_TP_RR = 1.5
ATR_PERIOD = 14
ATR_STOP_MULTIPLIER = 1.5
ATR_TIMEFRAME = "M15"
ATR_BARS = 64
SAFE_FALLBACK_STOP_POINTS = 100.0


def main() -> int:
    args = parse_args()
    logger = configure_logging(logger_name="manual_preflight_order_check")

    try:
        config = load_or_default_config(args.config)
        if args.symbol:
            config = replace(config, symbol=args.symbol, execution=replace(config.execution, require_symbol=args.symbol))
        tp_rr = args.tp_rr if args.tp_rr is not None else configured_tp_rr(args.config)

        with MT5Client(build_connection_config(args, config.symbol)) as client:
            client.ensure_symbol(config.symbol)
            event = manual_preflight_order_check(
                client=client,
                config=config,
                side=args.side,
                risk_pct_override=args.risk_pct,
                stop_points=args.stop_points,
                tp_rr=tp_rr,
            )
    except MT5ClientError as exc:
        logger.error("%s", exc)
        print(str(exc), file=sys.stderr)
        return EXIT_RUNTIME_FAILURE

    print(json.dumps(event, indent=2, sort_keys=True, default=str))
    return event_exit_code(event)


def manual_preflight_order_check(
    *,
    client: Any,
    config: TradingConfig,
    side: str,
    risk_pct_override: float | None = None,
    stop_points: float | None = None,
    tp_rr: float = DEFAULT_TP_RR,
) -> dict[str, Any]:
    symbol_info = client.get_symbol_info(config.symbol)
    account = client.get_account_info()
    tick = client.get_symbol_tick(config.symbol)
    positions = client.get_open_positions(config.symbol)
    daily_pnl = client.get_daily_realized_pnl(config.symbol)
    orders_today = get_orders_today(client, config)
    current_spread = spread_points_from_prices(tick.bid, tick.ask, symbol_info.point)
    resolved_stop_points, stop_source = resolve_stop_points(
        client=client,
        symbol=config.symbol,
        symbol_info=symbol_info,
        explicit_stop_points=stop_points,
        risk_config=config.risk,
    )
    entry_price, stop_loss, take_profit = price_levels(
        side=side,
        tick=tick,
        symbol_info=symbol_info,
        stop_points=resolved_stop_points,
        tp_rr=tp_rr,
    )
    event = base_event(
        config=config,
        side=side,
        account=account,
        symbol_info=symbol_info,
        tick=tick,
        current_spread=current_spread,
        orders_today=orders_today,
        positions_count=len(positions),
        candidate_order={
            "symbol": config.symbol,
            "side": side,
            "entry_price": entry_price,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "stop_points": resolved_stop_points,
            "stop_source": stop_source,
            "tp_rr": tp_rr,
            "risk_pct": risk_pct_override if risk_pct_override is not None else config.risk.risk_per_trade_pct,
            "volume": None,
            "mt5_request": None,
        },
    )

    execution_decision = evaluate_execution_safety(
        config=config.execution,
        account_info=account.raw if account is not None else None,
        symbol=config.symbol,
        open_positions=positions,
        orders_today=orders_today,
        project_magic=config.magic_number,
        require_order_send_permission=False,
    )
    event["execution_decision"] = {
        "allowed": execution_decision.allowed,
        "reason_codes": list(execution_decision.reason_codes),
        "reasons": list(execution_decision.reasons),
    }
    if not execution_decision.allowed:
        return block_event(event, execution_decision.reason_codes, execution_decision.reasons)

    risk_config, override_block = risk_config_with_override(config.risk, risk_pct_override)
    if override_block is not None:
        event["local_risk_decision"] = override_block
        return block_event(event, tuple(override_block["reason_codes"]), tuple(override_block["reasons"]))

    risk_decision = RiskManager(risk_config).assess_trade(
        TradeRiskRequest(
            symbol_info=symbol_info.raw,
            account=AccountState(balance=account.balance, equity=account.equity, daily_realized_pnl=daily_pnl),
            side=side,
            entry_price=entry_price,
            stop_loss_price=stop_loss,
            take_profit_price=take_profit,
            current_spread_points=current_spread,
            open_positions=positions,
        )
    )
    event["local_risk_decision"] = risk_decision_to_dict(risk_decision)
    event["candidate_order"]["volume"] = risk_decision.volume
    if not risk_decision.allowed:
        return block_event(event, risk_decision.reason_codes, risk_decision.reasons)

    request = client.build_market_order_request(
        symbol=config.symbol,
        side=side,
        volume=risk_decision.volume,
        stop_loss=stop_loss,
        take_profit=take_profit,
        deviation_points=config.deviation_points,
        magic_number=config.magic_number,
        comment=manual_preflight_comment(config.order_comment),
    )
    event["candidate_order"]["mt5_request"] = request
    order_check_result = client.order_check(request)
    event["order_check_result"] = result_to_dict(order_check_result)
    if not order_check_passed(order_check_result):
        decision = order_check_failure_decision(order_check_result)
        return block_event(event, decision.reason_codes, decision.reasons)

    event["final_decision"] = "ALLOW"
    return event


def base_event(
    *,
    config: TradingConfig,
    side: str,
    account: Any,
    symbol_info: Any,
    tick: Any,
    current_spread: float,
    orders_today: int,
    positions_count: int,
    candidate_order: dict[str, Any],
) -> dict[str, Any]:
    return {
        "project": "xm-gold-ai-trader",
        "mode": "manual_preflight_order_check",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "orders_sent": 0,
        "final_decision": "BLOCK",
        "reason_codes": [],
        "reasons": [],
        "config": {"symbol": config.symbol, "execution": asdict(config.execution), "risk": asdict(config.risk)},
        "account": compact_account(account),
        "symbol": compact_symbol(symbol_info),
        "tick": result_to_dict(tick),
        "side": side,
        "orders_today": orders_today,
        "open_positions_count": positions_count,
        "current_spread_points": current_spread,
        "candidate_order": candidate_order,
        "execution_decision": None,
        "local_risk_decision": None,
        "order_check_result": None,
    }


def block_event(event: dict[str, Any], codes: tuple[str, ...], reasons: tuple[str, ...]) -> dict[str, Any]:
    event["final_decision"] = "BLOCK"
    event["reason_codes"] = list(codes)
    event["reasons"] = list(reasons)
    return event


def manual_preflight_comment(base_comment: str) -> str:
    return f"{base_comment}-preflt"[:31]


def risk_config_with_override(
    config: RiskConfig,
    risk_pct_override: float | None,
) -> tuple[RiskConfig, dict[str, Any] | None]:
    if risk_pct_override is None:
        return config, None
    if risk_pct_override > config.risk_per_trade_pct:
        reason = (
            f"{REASON_RISK_PCT_EXCEEDS_CONFIG_LIMIT}: requested risk_pct {risk_pct_override:.4f} "
            f"exceeds configured limit {config.risk_per_trade_pct:.4f}"
        )
        return config, {
            "allowed": False,
            "volume": 0.0,
            "reason_codes": [REASON_RISK_PCT_EXCEEDS_CONFIG_LIMIT],
            "reasons": [reason],
            "risk_amount": 0.0,
            "risk_per_lot": 0.0,
            "stop_distance_points": 0.0,
            "take_profit_distance_points": None,
        }
    return replace(config, risk_per_trade_pct=risk_pct_override), None


def price_levels(*, side: str, tick: Any, symbol_info: Any, stop_points: float, tp_rr: float) -> tuple[float, float, float]:
    point = float(symbol_info.point)
    distance = stop_points * point
    digits = int(_field(symbol_info, "digits", default=5))
    entry = float(tick.ask if side == "BUY" else tick.bid)
    if side == "BUY":
        return (
            _round_price(entry, digits),
            _round_price(entry - distance, digits),
            _round_price(entry + (distance * tp_rr), digits),
        )
    return (
        _round_price(entry, digits),
        _round_price(entry + distance, digits),
        _round_price(entry - (distance * tp_rr), digits),
    )


def resolve_stop_points(
    *,
    client: Any,
    symbol: str,
    symbol_info: Any,
    explicit_stop_points: float | None,
    risk_config: RiskConfig,
) -> tuple[float, str]:
    fallback = safe_fallback_stop_points(symbol_info, risk_config)
    if explicit_stop_points is not None:
        return explicit_stop_points, "cli"

    atr_points = atr_stop_points(client, symbol, symbol_info)
    if atr_points is None:
        return fallback, "safe_fallback"
    if atr_points < fallback:
        return fallback, "atr_fallback_floor"
    return atr_points, "atr"


def atr_stop_points(client: Any, symbol: str, symbol_info: Any) -> float | None:
    if not hasattr(client, "copy_rates_from_pos"):
        return None
    try:
        rates = client.copy_rates_from_pos(symbol, ATR_TIMEFRAME, ATR_BARS, start_pos=1)
    except Exception:
        return None
    if rates is None:
        return None
    rows = list(rates)
    if len(rows) <= ATR_PERIOD:
        return None
    ranges: list[float] = []
    previous_close = float(_bar_field(rows[0], "close"))
    for row in rows[1:]:
        high = float(_bar_field(row, "high"))
        low = float(_bar_field(row, "low"))
        true_range = max(high - low, abs(high - previous_close), abs(low - previous_close))
        ranges.append(true_range)
        previous_close = float(_bar_field(row, "close"))
    if len(ranges) < ATR_PERIOD:
        return None
    atr = sum(ranges[-ATR_PERIOD:]) / ATR_PERIOD
    point = float(symbol_info.point)
    if atr <= 0 or point <= 0:
        return None
    return (atr * ATR_STOP_MULTIPLIER) / point


def safe_fallback_stop_points(symbol_info: Any, risk_config: RiskConfig) -> float:
    raw = result_to_dict(symbol_info) or {}
    spread = float(raw.get("spread", 0.0) or 0.0)
    stops_level = float(raw.get("trade_stops_level", 0.0) or 0.0)
    return max(SAFE_FALLBACK_STOP_POINTS, risk_config.min_stop_distance_points, stops_level, spread * 2.0)


def compact_account(account: Any) -> dict[str, Any] | None:
    data = result_to_dict(account)
    if data is None:
        return None
    keys = ("login", "server", "trade_mode", "trade_allowed", "trade_expert", "balance", "equity", "currency")
    return {key: data.get(key) for key in keys}


def compact_symbol(symbol_info: Any) -> dict[str, Any]:
    data = result_to_dict(symbol_info) or {}
    keys = (
        "name",
        "description",
        "path",
        "digits",
        "point",
        "spread",
        "trade_tick_size",
        "trade_tick_value",
        "volume_min",
        "volume_max",
        "volume_step",
        "trade_stops_level",
        "trade_freeze_level",
        "trade_mode",
    )
    return {key: data.get(key) for key in keys}


def configured_tp_rr(path: str) -> float:
    config_path = Path(path)
    if not config_path.exists():
        return DEFAULT_TP_RR
    data = _read_config_mapping(config_path)
    candidates = [
        data.get("tp_rr"),
        data.get("reward_risk_ratio"),
        _mapping_value(data, "strategy", "tp_rr"),
        _mapping_value(data, "strategy", "reward_risk_ratio"),
        _mapping_value(data, "baseline", "reward_risk_ratio"),
    ]
    for value in candidates:
        if value is None:
            continue
        parsed = float(value)
        if parsed <= 0:
            raise ValueError("configured tp/reward-risk ratio must be positive")
        return parsed
    return DEFAULT_TP_RR


def _read_config_mapping(path: Path) -> Mapping[str, Any]:
    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
    elif path.suffix.lower() in {".yaml", ".yml"}:
        import yaml  # type: ignore[import-not-found]

        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    else:
        return {}
    if not isinstance(data, Mapping):
        raise ValueError("trading config must be a mapping")
    return data


def _mapping_value(data: Mapping[str, Any], section: str, key: str) -> Any:
    value = data.get(section, {})
    if not isinstance(value, Mapping):
        return None
    return value.get(key)


def _positive_float(value: str) -> float:
    parsed = float(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be positive")
    return parsed


def _optional_int(value: str | None) -> int | None:
    return int(value) if value else None


def _field(source: Any, name: str, default: Any = None) -> Any:
    if isinstance(source, Mapping):
        return source.get(name, default)
    if hasattr(source, name):
        return getattr(source, name)
    raw = getattr(source, "raw", None)
    if isinstance(raw, Mapping):
        return raw.get(name, default)
    return default


def _bar_field(row: Any, name: str) -> Any:
    if isinstance(row, Mapping):
        return row[name]
    try:
        return row[name]
    except (KeyError, TypeError, IndexError):
        return getattr(row, name)


def _round_price(value: float, digits: int) -> float:
    return round(value, digits)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a manual BUY/SELL order_check preflight only; never order_send.")
    parser.add_argument("--side", required=True, choices=("BUY", "SELL"))
    parser.add_argument("--config", default="configs/xm_gold_ai_trader.demo.yaml")
    parser.add_argument("--symbol", default=None, help="Optional override; defaults to the configured symbol.")
    parser.add_argument("--risk-pct", type=_positive_float, default=None)
    parser.add_argument("--stop-points", type=_positive_float, default=None)
    parser.add_argument("--tp-rr", type=_positive_float, default=None)
    parser.add_argument("--terminal-path", default=os.getenv("XM_MT5_TERMINAL_PATH"))
    parser.add_argument("--login", type=int, default=_optional_int(os.getenv("XM_MT5_LOGIN")))
    parser.add_argument("--password", default=os.getenv("XM_MT5_PASSWORD"))
    parser.add_argument("--server", default=os.getenv("XM_MT5_SERVER"))
    parser.add_argument("--timeout-ms", type=int, default=60_000)
    parser.add_argument("--json", action="store_true", help="Accepted for compatibility; output is always JSON.")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
