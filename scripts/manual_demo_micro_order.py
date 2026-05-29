from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, replace
from datetime import datetime, time, timezone
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.manual_preflight_order_check import (
    DEFAULT_TP_RR,
    compact_account,
    compact_symbol,
    price_levels,
)
from scripts.preflight_order_check import build_connection_config, get_orders_today, load_or_default_config, result_to_dict
from scripts.demo_lifecycle_report import order_send_accepted
from scripts.reconcile_demo_journal import load_journal_entries
from src.broker.execution_safety import (
    REASON_DAILY_LOSS_LIMIT_REACHED,
    REASON_EMERGENCY_STOP_FILE_PRESENT,
    REASON_ONE_SHOT_ORDER_ALREADY_USED,
    REASON_ORDER_CHECK_FAILED,
    evaluate_execution_safety,
    order_check_failure_decision,
    order_check_passed,
    position_matches,
)
from src.broker.mt5_client import MT5Client, MT5ClientError
from src.broker.order_executor import TradingConfig
from src.cli_contract import EXIT_RUNTIME_FAILURE, event_exit_code
from src.logging_config import configure_logging
from src.runtime.lock import (
    DEFAULT_EMERGENCY_STOP_PATH,
    DEFAULT_LOCK_PATH,
    DEFAULT_LOCK_STALE_AFTER_SECONDS,
    REASON_RUNTIME_LOCK_EXISTS,
    REASON_STALE_RUNTIME_LOCK_RECOVERED,
    RuntimeLock,
    emergency_stop_file_decision,
)
from src.strategy.risk_manager import AccountState, RiskConfig, RiskManager, TradeRiskRequest, spread_points_from_prices
from src.strategy.risk_manager import max_daily_loss_amount


REASON_DEMO_ORDER_CONFIRMATION_MISSING = "DEMO_ORDER_CONFIRMATION_MISSING"
REASON_CAPPED_LOT_BELOW_VOLUME_MIN = "CAPPED_LOT_BELOW_VOLUME_MIN"
REASON_ORDER_SEND_RETCODE_NOT_OK = "ORDER_SEND_RETCODE_NOT_OK"
REASON_POSITION_VERIFICATION_FAILED = "POSITION_VERIFICATION_FAILED"

FIRST_DEMO_MAX_LOT = 0.01
DEFAULT_STOP_POINTS = 100.0
JOURNAL_DIR = Path("logs/demo_orders")


def main() -> int:
    args = parse_args()
    logger = configure_logging(logger_name="manual_demo_micro_order")

    try:
        config = load_or_default_config(args.config)
        if args.symbol:
            config = replace(config, symbol=args.symbol, execution=replace(config.execution, require_symbol=args.symbol))

        env_confirmed = os.getenv("XM_GOLD_CONFIRM_DEMO_ORDER") == "YES"
        emergency_decision = emergency_stop_file_decision(DEFAULT_EMERGENCY_STOP_PATH)
        if not emergency_decision.acquired:
            event = write_journal(
                JOURNAL_DIR,
                operational_block_event(
                    config=config,
                    side=args.side,
                    cli_confirmed=args.confirm_demo_order,
                    env_confirmed=env_confirmed,
                    block_stage="pre_mt5",
                    codes=emergency_decision.reason_codes,
                    reasons=emergency_decision.reasons,
                ),
            )
        elif (config.execution.require_manual_confirmation and not args.confirm_demo_order) or (
            config.execution.require_env_confirmation and not env_confirmed
        ):
            event = write_journal(
                JOURNAL_DIR,
                confirmation_block_event(
                    config=config,
                    side=args.side,
                    cli_confirmed=args.confirm_demo_order,
                    env_confirmed=env_confirmed,
                ),
            )
        else:
            with MT5Client(build_connection_config(args, config.symbol)) as client:
                client.ensure_symbol(config.symbol)
                event = manual_demo_micro_order(
                    client=client,
                    config=config,
                    side=args.side,
                    stop_points=args.stop_points,
                    tp_rr=args.tp_rr,
                    cli_confirmed=args.confirm_demo_order,
                    env_confirmed=env_confirmed,
                    journal_dir=JOURNAL_DIR,
                    lock_stale_after_seconds=args.lock_stale_after_seconds,
                )
    except (MT5ClientError, OSError, RuntimeError, ValueError) as exc:
        logger.error("%s", exc)
        print(str(exc), file=sys.stderr)
        return EXIT_RUNTIME_FAILURE

    print(json.dumps(event, indent=2, sort_keys=True, default=str))
    return event_exit_code(event)


def manual_demo_micro_order(
    *,
    client: Any,
    config: TradingConfig,
    side: str,
    stop_points: float = DEFAULT_STOP_POINTS,
    tp_rr: float = DEFAULT_TP_RR,
    cli_confirmed: bool,
    env_confirmed: bool,
    journal_dir: Path = JOURNAL_DIR,
    runtime_lock_path: Path = DEFAULT_LOCK_PATH,
    emergency_stop_path: Path = DEFAULT_EMERGENCY_STOP_PATH,
    lock_stale_after_seconds: int = DEFAULT_LOCK_STALE_AFTER_SECONDS,
) -> dict[str, Any]:
    emergency_decision = emergency_stop_file_decision(emergency_stop_path)
    if not emergency_decision.acquired:
        return write_journal(
            journal_dir,
            operational_block_event(
                config=config,
                side=side,
                cli_confirmed=cli_confirmed,
                env_confirmed=env_confirmed,
                block_stage="pre_mt5",
                codes=emergency_decision.reason_codes,
                reasons=emergency_decision.reasons,
            ),
        )

    if (config.execution.require_manual_confirmation and not cli_confirmed) or (
        config.execution.require_env_confirmation and not env_confirmed
    ):
        event = confirmation_block_event(
            config=config,
            side=side,
            cli_confirmed=cli_confirmed,
            env_confirmed=env_confirmed,
        )
        return write_journal(journal_dir, event)

    runtime_lock = RuntimeLock(runtime_lock_path, stale_after_seconds=lock_stale_after_seconds)
    lock_decision = runtime_lock.acquire()
    if not lock_decision.acquired:
        return write_journal(
            journal_dir,
            operational_block_event(
                config=config,
                side=side,
                cli_confirmed=cli_confirmed,
                env_confirmed=env_confirmed,
                block_stage="pre_mt5",
                codes=lock_decision.reason_codes,
                reasons=lock_decision.reasons,
            ),
        )

    try:
        return _manual_demo_micro_order_locked(
            client=client,
            config=config,
            side=side,
            stop_points=stop_points,
            tp_rr=tp_rr,
            cli_confirmed=cli_confirmed,
            env_confirmed=env_confirmed,
            journal_dir=journal_dir,
            lock_decision=lock_decision,
            runtime_lock_path=runtime_lock_path,
        )
    finally:
        runtime_lock.release()


def _manual_demo_micro_order_locked(
    *,
    client: Any,
    config: TradingConfig,
    side: str,
    stop_points: float,
    tp_rr: float,
    cli_confirmed: bool,
    env_confirmed: bool,
    journal_dir: Path,
    lock_decision: Any,
    runtime_lock_path: Path,
) -> dict[str, Any]:
    symbol_info = client.get_symbol_info(config.symbol)
    account = client.get_account_info()
    tick = client.get_symbol_tick(config.symbol)
    positions = client.get_open_positions(config.symbol)
    daily_pnl = project_daily_realized_pnl(client, config)
    orders_today = get_orders_today(client, config)
    current_spread = spread_points_from_prices(tick.bid, tick.ask, symbol_info.point)
    entry_price, stop_loss, take_profit = price_levels(
        side=side,
        tick=tick,
        symbol_info=symbol_info,
        stop_points=stop_points,
        tp_rr=tp_rr,
    )
    event = base_event(
        config=config,
        side=side,
        account=account,
        symbol_info=symbol_info,
        tick=tick,
        candidate_order={
            "symbol": config.symbol,
            "side": side,
            "entry_price": entry_price,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "stop_points": stop_points,
            "tp_rr": tp_rr,
            "risk_pct": config.risk.risk_per_trade_pct,
            "raw_risk_volume": None,
            "volume": None,
            "max_lot_cap": FIRST_DEMO_MAX_LOT,
            "mt5_request": None,
        },
        current_spread=current_spread,
        orders_today=orders_today,
        open_positions_count=len(positions),
        cli_confirmed=cli_confirmed,
        env_confirmed=env_confirmed,
        block_stage="post_mt5",
    )
    event["runtime_lock"] = {
        "path": str(runtime_lock_path),
        "acquired": True,
        "stale_recovered": bool(getattr(lock_decision, "stale_recovered", False)),
    }
    event["project_daily_realized_pnl"] = daily_pnl
    if getattr(lock_decision, "reason_codes", ()):
        event["warning_codes"] = list(lock_decision.reason_codes)
        event["warnings"] = list(lock_decision.reasons)

    one_shot_used = accepted_order_exists_today(client=client, config=config, journal_dir=journal_dir)
    event["one_shot"] = {"enabled": config.execution.one_shot_only, "already_used": one_shot_used}
    if config.execution.one_shot_only and one_shot_used:
        reasons = (
            f"{REASON_ONE_SHOT_ORDER_ALREADY_USED}: an accepted {config.symbol} demo order "
            "with the project magic already exists today",
        )
        return write_journal(journal_dir, block_event(event, (REASON_ONE_SHOT_ORDER_ALREADY_USED,), reasons))

    execution_decision = evaluate_execution_safety(
        config=config.execution,
        account_info=account.raw if account is not None else None,
        symbol=config.symbol,
        open_positions=positions,
        orders_today=orders_today,
        project_magic=config.magic_number,
        require_order_send_permission=True,
        check_existing_magic_position=True,
    )
    event["execution_decision"] = {
        "allowed": execution_decision.allowed,
        "reason_codes": list(execution_decision.reason_codes),
        "reasons": list(execution_decision.reasons),
    }
    if not execution_decision.allowed:
        return write_journal(journal_dir, block_event(event, execution_decision.reason_codes, execution_decision.reasons))

    daily_loss_limit = max_daily_loss_amount(account.balance, config.risk.max_daily_loss_pct)
    event["daily_loss_limit"] = daily_loss_limit
    if daily_pnl <= -daily_loss_limit:
        reasons = (
            f"{REASON_DAILY_LOSS_LIMIT_REACHED}: project realized PnL {daily_pnl:.2f} "
            f"<= -{daily_loss_limit:.2f}",
        )
        return write_journal(journal_dir, block_event(event, (REASON_DAILY_LOSS_LIMIT_REACHED,), reasons))

    risk_decision = RiskManager(config.risk).assess_trade(
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
    risk_payload = risk_decision_to_payload(risk_decision)
    event["local_risk_decision"] = risk_payload
    event["candidate_order"]["raw_risk_volume"] = risk_decision.volume
    if not risk_decision.allowed:
        return write_journal(journal_dir, block_event(event, risk_decision.reason_codes, risk_decision.reasons))

    capped_volume = min(risk_decision.volume, FIRST_DEMO_MAX_LOT)
    risk_payload["capped_volume"] = capped_volume
    event["candidate_order"]["volume"] = capped_volume
    minimum_volume = float(_field(symbol_info.raw, "volume_min", 0.0))
    if capped_volume < minimum_volume:
        reasons = (
            f"{REASON_CAPPED_LOT_BELOW_VOLUME_MIN}: capped volume {capped_volume:.2f} "
            f"is below broker volume_min {minimum_volume:.2f}",
        )
        return write_journal(journal_dir, block_event(event, (REASON_CAPPED_LOT_BELOW_VOLUME_MIN,), reasons))

    request = client.build_market_order_request(
        symbol=config.symbol,
        side=side,
        volume=capped_volume,
        stop_loss=stop_loss,
        take_profit=take_profit,
        deviation_points=config.deviation_points,
        magic_number=config.magic_number,
        comment=demo_order_comment(config.order_comment),
    )
    event["candidate_order"]["mt5_request"] = request

    order_check_result = client.order_check(request)
    event["order_check_result"] = result_to_dict(order_check_result)
    if not order_check_passed(order_check_result):
        event["block_stage"] = "post_order_check"
        decision = order_check_failure_decision(order_check_result)
        return write_journal(journal_dir, block_event(event, decision.reason_codes, decision.reasons))

    order_send_result = client.order_send_checked(request, order_check_result)
    event["order_send_attempts"] = 1
    event["order_send_result"] = result_to_dict(order_send_result)
    event["block_stage"] = "post_order_send"
    if not order_check_passed(order_send_result):
        reasons = (f"{REASON_ORDER_SEND_RETCODE_NOT_OK}: order_send retcode was not successful",)
        return write_journal(journal_dir, block_event(event, (REASON_ORDER_SEND_RETCODE_NOT_OK,), reasons))

    event["orders_sent"] = 1
    event["orders_accepted"] = 1
    verification = verify_matching_position(client, config)
    event["position_verification"] = verification
    if not verification["matched"]:
        reasons = (
            f"{REASON_POSITION_VERIFICATION_FAILED}: no matching {config.symbol} position "
            f"with magic {config.magic_number} was found after order_send",
        )
        return write_journal(journal_dir, block_event(event, (REASON_POSITION_VERIFICATION_FAILED,), reasons))

    event["final_decision"] = "SENT"
    return write_journal(journal_dir, event)


def confirmation_block_event(*, config: TradingConfig, side: str, cli_confirmed: bool, env_confirmed: bool) -> dict[str, Any]:
    event = base_event(
        config=config,
        side=side,
        account=None,
        symbol_info=None,
        tick=None,
        candidate_order=None,
        current_spread=None,
        orders_today=None,
        open_positions_count=None,
        cli_confirmed=cli_confirmed,
        env_confirmed=env_confirmed,
        block_stage="pre_confirmation",
    )
    return block_event(
        event,
        (REASON_DEMO_ORDER_CONFIRMATION_MISSING,),
        (
            f"{REASON_DEMO_ORDER_CONFIRMATION_MISSING}: --confirm-demo-order and "
            "XM_GOLD_CONFIRM_DEMO_ORDER=YES are both required",
        ),
    )


def operational_block_event(
    *,
    config: TradingConfig,
    side: str,
    cli_confirmed: bool,
    env_confirmed: bool,
    block_stage: str,
    codes: tuple[str, ...],
    reasons: tuple[str, ...],
) -> dict[str, Any]:
    event = base_event(
        config=config,
        side=side,
        account=None,
        symbol_info=None,
        tick=None,
        candidate_order=None,
        current_spread=None,
        orders_today=None,
        open_positions_count=None,
        cli_confirmed=cli_confirmed,
        env_confirmed=env_confirmed,
        block_stage=block_stage,
    )
    return block_event(event, codes, reasons)


def base_event(
    *,
    config: TradingConfig,
    side: str,
    account: Any,
    symbol_info: Any,
    tick: Any,
    candidate_order: dict[str, Any] | None,
    current_spread: float | None,
    orders_today: int | None,
    open_positions_count: int | None,
    cli_confirmed: bool,
    env_confirmed: bool,
    block_stage: str,
) -> dict[str, Any]:
    return {
        "project": "xm-gold-ai-trader",
        "mode": "manual_demo_micro_order",
        "journal_schema_version": 1,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "final_decision": "BLOCK",
        "reason_codes": [],
        "reasons": [],
        "orders_sent": 0,
        "orders_accepted": 0,
        "order_send_attempts": 0,
        "block_stage": block_stage,
        "config": {
            "symbol": config.symbol,
            "magic_number": config.magic_number,
            "deviation_points": config.deviation_points,
            "order_comment": config.order_comment,
            "execution": asdict(config.execution),
            "risk": asdict(config.risk),
        },
        "confirmations": {"cli_confirmed": cli_confirmed, "env_confirmed": env_confirmed},
        "account": compact_account(account),
        "symbol": compact_symbol(symbol_info) if symbol_info is not None else None,
        "tick": result_to_dict(tick),
        "side": side,
        "orders_today": orders_today,
        "open_positions_count": open_positions_count,
        "current_spread_points": current_spread,
        "candidate_order": candidate_order,
        "execution_decision": None,
        "local_risk_decision": None,
        "order_check_result": None,
        "order_send_result": None,
        "position_verification": {"checked": False, "matched": False, "matching_positions": []},
        "runtime_lock": None,
        "warning_codes": [],
        "warnings": [],
        "one_shot": None,
        "project_daily_realized_pnl": None,
        "daily_loss_limit": None,
        "journal_path": None,
    }


def block_event(event: dict[str, Any], codes: tuple[str, ...], reasons: tuple[str, ...]) -> dict[str, Any]:
    event["final_decision"] = "BLOCK"
    event["reason_codes"] = list(codes)
    event["reasons"] = list(reasons)
    return event


def risk_decision_to_payload(decision: Any) -> dict[str, Any]:
    return {
        "allowed": decision.allowed,
        "volume": decision.volume,
        "capped_volume": None,
        "reason_codes": list(decision.reason_codes),
        "reasons": list(decision.reasons),
        "risk_amount": decision.risk_amount,
        "risk_per_lot": decision.risk_per_lot,
        "stop_distance_points": decision.stop_distance_points,
        "take_profit_distance_points": decision.take_profit_distance_points,
    }


def verify_matching_position(client: Any, config: TradingConfig) -> dict[str, Any]:
    positions = client.get_open_positions(config.symbol)
    matches = [
        result_to_dict(position)
        for position in positions
        if position_matches(position, symbol=config.execution.require_symbol, magic=config.magic_number)
    ]
    return {"checked": True, "matched": bool(matches), "matching_positions": matches}


def write_journal(journal_dir: Path, event: dict[str, Any]) -> dict[str, Any]:
    journal_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = journal_dir / f"manual_demo_micro_order_{timestamp}.json"
    event["journal_path"] = str(path)
    path.write_text(json.dumps(event, indent=2, sort_keys=True, default=str), encoding="utf-8")
    return event


def demo_order_comment(base_comment: str) -> str:
    return f"{base_comment}-demo1"[:31]


def accepted_order_exists_today(
    *,
    client: Any,
    config: TradingConfig,
    journal_dir: Path,
    now_utc: datetime | None = None,
) -> bool:
    return accepted_order_in_journal_today(config=config, journal_dir=journal_dir, now_utc=now_utc) or (
        accepted_order_in_mt5_history_today(client=client, config=config, now_utc=now_utc)
    )


def accepted_order_in_journal_today(
    *,
    config: TradingConfig,
    journal_dir: Path,
    now_utc: datetime | None = None,
) -> bool:
    now = now_utc or datetime.now(timezone.utc)
    for entry in load_journal_entries(journal_dir):
        payload = entry.payload
        if not isinstance(payload, Mapping) or not order_send_accepted(payload):
            continue
        if payload_symbol(payload) != config.symbol:
            continue
        if payload_magic(payload) != config.magic_number:
            continue
        timestamp = parse_timestamp(payload.get("timestamp_utc"))
        if timestamp is not None and timestamp.date() == now.date():
            return True
    return False


def accepted_order_in_mt5_history_today(
    *,
    client: Any,
    config: TradingConfig,
    now_utc: datetime | None = None,
) -> bool:
    if not hasattr(client, "get_history_deals"):
        return False
    start, end = trading_day_window(now_utc)
    for deal in client.get_history_deals(start, end):
        data = result_to_dict(deal) or {}
        if data.get("symbol") != config.symbol:
            continue
        if _optional_int_value(data.get("magic")) != config.magic_number:
            continue
        if float(data.get("volume", 0.0) or 0.0) > 0:
            return True
    return False


def project_daily_realized_pnl(client: Any, config: TradingConfig, now_utc: datetime | None = None) -> float:
    if hasattr(client, "get_history_deals"):
        start, end = trading_day_window(now_utc)
        pnl = 0.0
        for deal in client.get_history_deals(start, end):
            data = result_to_dict(deal) or {}
            if data.get("symbol") != config.symbol:
                continue
            if _optional_int_value(data.get("magic")) != config.magic_number:
                continue
            pnl += float(data.get("profit", 0.0) or 0.0)
            pnl += float(data.get("swap", 0.0) or 0.0)
            pnl += float(data.get("commission", 0.0) or 0.0)
            pnl += float(data.get("fee", 0.0) or 0.0)
        return pnl
    return float(client.get_daily_realized_pnl(config.symbol))


def trading_day_window(now_utc: datetime | None = None) -> tuple[datetime, datetime]:
    now = now_utc or datetime.now(timezone.utc)
    start = datetime.combine(now.date(), time.min, tzinfo=timezone.utc)
    return start, now


def payload_symbol(payload: Mapping[str, Any]) -> str | None:
    return (
        _nested(payload, "candidate_order", "symbol")
        or _nested(payload, "symbol", "name")
        or _nested(payload, "config", "symbol")
    )


def payload_magic(payload: Mapping[str, Any]) -> int | None:
    return _optional_int_value(
        _nested(payload, "config", "magic_number")
        or _nested(payload, "candidate_order", "mt5_request", "magic")
    )


def parse_timestamp(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _nested(source: Mapping[str, Any], *path: str) -> Any:
    value: Any = source
    for key in path:
        if not isinstance(value, Mapping):
            return None
        value = value.get(key)
    return value


def _positive_float(value: str) -> float:
    parsed = float(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be positive")
    return parsed


def _optional_int(value: str | None) -> int | None:
    return int(value) if value else None


def _optional_int_value(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _field(source: Any, name: str, default: Any = None) -> Any:
    if isinstance(source, Mapping):
        return source.get(name, default)
    return getattr(source, name, default)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send one manually confirmed demo-only GOLD_ micro order.")
    parser.add_argument("--side", required=True, choices=("BUY", "SELL"))
    parser.add_argument("--stop-points", type=_positive_float, default=DEFAULT_STOP_POINTS)
    parser.add_argument("--tp-rr", type=_positive_float, default=DEFAULT_TP_RR)
    parser.add_argument("--config", required=True)
    parser.add_argument("--symbol", default=None, help="Optional override; defaults to the configured symbol.")
    parser.add_argument("--confirm-demo-order", action="store_true")
    parser.add_argument("--lock-stale-after-seconds", type=int, default=DEFAULT_LOCK_STALE_AFTER_SECONDS)
    parser.add_argument("--terminal-path", default=os.getenv("XM_MT5_TERMINAL_PATH"))
    parser.add_argument("--login", type=int, default=_optional_int(os.getenv("XM_MT5_LOGIN")))
    parser.add_argument("--password", default=os.getenv("XM_MT5_PASSWORD"))
    parser.add_argument("--server", default=os.getenv("XM_MT5_SERVER"))
    parser.add_argument("--timeout-ms", type=int, default=60_000)
    parser.add_argument("--json", action="store_true", help="Accepted for compatibility; output is always JSON.")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
