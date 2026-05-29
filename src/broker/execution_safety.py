from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence


REASON_ACCOUNT_INFO_UNAVAILABLE = "ACCOUNT_INFO_UNAVAILABLE"
REASON_TRADE_NOT_ALLOWED = "TRADE_NOT_ALLOWED"
REASON_EXPERT_TRADING_DISABLED = "EXPERT_TRADING_DISABLED"
REASON_NON_DEMO_ACCOUNT = "NON_DEMO_ACCOUNT"
REASON_EMERGENCY_STOP = "EMERGENCY_STOP"
REASON_ALLOW_ORDER_SEND_FALSE = "ALLOW_ORDER_SEND_FALSE"
REASON_SYMBOL_NOT_REQUIRED = "SYMBOL_NOT_REQUIRED"
REASON_MAX_ORDERS_PER_DAY = "MAX_ORDERS_PER_DAY"
REASON_MAX_POSITIONS = "MAX_POSITIONS"
REASON_EXISTING_MAGIC_POSITION = "EXISTING_MAGIC_POSITION"
REASON_ORDER_CHECK_FAILED = "ORDER_CHECK_FAILED"
REASON_NO_MATCHING_POSITIONS = "NO_MATCHING_POSITIONS"
REASON_EMERGENCY_STOP_FILE_PRESENT = "EMERGENCY_STOP_FILE_PRESENT"
REASON_ONE_SHOT_ORDER_ALREADY_USED = "ONE_SHOT_ORDER_ALREADY_USED"
REASON_DAILY_LOSS_LIMIT_REACHED = "DAILY_LOSS_LIMIT_REACHED"

ACCOUNT_TRADE_MODE_DEMO = 0


@dataclass(frozen=True, slots=True)
class ExecutionConfig:
    allow_order_send: bool = False
    require_demo_account: bool = True
    require_symbol: str = "GOLD_"
    max_orders_per_day: int = 1
    max_positions: int = 1
    emergency_stop: bool = False
    one_shot_only: bool = False
    require_manual_confirmation: bool = True
    require_env_confirmation: bool = True

    def __post_init__(self) -> None:
        if self.max_orders_per_day < 0:
            raise ValueError("max_orders_per_day must be >= 0")
        if self.max_positions < 0:
            raise ValueError("max_positions must be >= 0")
        if not self.require_symbol:
            raise ValueError("require_symbol must not be empty")


@dataclass(frozen=True, slots=True)
class ExecutionSafetyDecision:
    allowed: bool
    reason_codes: tuple[str, ...] = ()
    reasons: tuple[str, ...] = ()


def evaluate_execution_safety(
    *,
    config: ExecutionConfig,
    account_info: Any,
    symbol: str,
    open_positions: Sequence[Any] = (),
    orders_today: int = 0,
    project_magic: int | None = None,
    require_order_send_permission: bool = False,
    check_existing_magic_position: bool = False,
    demo_trade_mode: int = ACCOUNT_TRADE_MODE_DEMO,
) -> ExecutionSafetyDecision:
    codes: list[str] = []
    reasons: list[str] = []

    if config.emergency_stop:
        _block(codes, reasons, REASON_EMERGENCY_STOP, "execution.emergency_stop is true")

    if require_order_send_permission and not config.allow_order_send:
        _block(codes, reasons, REASON_ALLOW_ORDER_SEND_FALSE, "execution.allow_order_send is false")

    if symbol != config.require_symbol:
        _block(
            codes,
            reasons,
            REASON_SYMBOL_NOT_REQUIRED,
            f"symbol {symbol!r} does not match execution.require_symbol {config.require_symbol!r}",
        )

    if account_info is None:
        _block(codes, reasons, REASON_ACCOUNT_INFO_UNAVAILABLE, "account_info() returned None")
    else:
        trade_allowed = _bool_field(account_info, "trade_allowed", default=False)
        trade_expert = _bool_field(account_info, "trade_expert", default=False)
        trade_mode = _int_field(account_info, "trade_mode", default=None)

        if not trade_allowed:
            _block(codes, reasons, REASON_TRADE_NOT_ALLOWED, "account trade_allowed is false")
        if not trade_expert:
            _block(codes, reasons, REASON_EXPERT_TRADING_DISABLED, "account trade_expert is false")
        if config.require_demo_account and trade_mode != demo_trade_mode:
            _block(
                codes,
                reasons,
                REASON_NON_DEMO_ACCOUNT,
                f"account trade_mode {trade_mode!r} is not demo mode {demo_trade_mode}",
            )

    matching_positions = [
        position
        for position in open_positions
        if position_matches(position, symbol=config.require_symbol, magic=project_magic)
    ]
    if config.max_positions and len(matching_positions) >= config.max_positions:
        _block(
            codes,
            reasons,
            REASON_MAX_POSITIONS,
            f"matching open positions {len(matching_positions)} >= max_positions {config.max_positions}",
        )
    if check_existing_magic_position and matching_positions:
        _block(
            codes,
            reasons,
            REASON_EXISTING_MAGIC_POSITION,
            f"existing {config.require_symbol} position with project magic {project_magic}",
        )

    if config.max_orders_per_day and orders_today >= config.max_orders_per_day:
        _block(
            codes,
            reasons,
            REASON_MAX_ORDERS_PER_DAY,
            f"orders today {orders_today} >= max_orders_per_day {config.max_orders_per_day}",
        )

    return ExecutionSafetyDecision(allowed=not codes, reason_codes=tuple(codes), reasons=tuple(reasons))


def position_matches(position: Any, *, symbol: str, magic: int | None = None) -> bool:
    if _field(position, "symbol", default=None) != symbol:
        return False
    if magic is None:
        return True
    return _int_field(position, "magic", default=None) == magic


def order_check_passed(order_check_result: Any) -> bool:
    if order_check_result is None:
        return False
    retcode = _int_field(order_check_result, "retcode", default=None)
    if retcode is None:
        return False
    return retcode in {0, 10008, 10009}


def order_check_failure_decision(order_check_result: Any) -> ExecutionSafetyDecision:
    retcode = _field(order_check_result, "retcode", default=None)
    comment = _field(order_check_result, "comment", default="")
    return ExecutionSafetyDecision(
        allowed=False,
        reason_codes=(REASON_ORDER_CHECK_FAILED,),
        reasons=(f"{REASON_ORDER_CHECK_FAILED}: order_check failed retcode={retcode!r} comment={comment!r}",),
    )


def _field(source: Any, name: str, default: Any = None) -> Any:
    if isinstance(source, Mapping):
        return source.get(name, default)
    return getattr(source, name, default)


def _bool_field(source: Any, name: str, default: bool) -> bool:
    return bool(_field(source, name, default))


def _int_field(source: Any, name: str, default: int | None) -> int | None:
    value = _field(source, name, default)
    return None if value is None else int(value)


def _block(codes: list[str], reasons: list[str], code: str, reason: str) -> None:
    codes.append(code)
    reasons.append(f"{code}: {reason}")
