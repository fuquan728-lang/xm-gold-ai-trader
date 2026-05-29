from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, time, timezone
from types import TracebackType
from typing import Any, Iterable

try:
    import MetaTrader5 as mt5  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - exercised on machines without MT5 Python package.
    mt5 = None  # type: ignore[assignment]


class MT5ClientError(RuntimeError):
    """Raised when MetaTrader5 cannot satisfy a broker request."""


@dataclass(frozen=True, slots=True)
class MT5ConnectionConfig:
    symbol: str = "GOLD_"
    terminal_path: str | None = None
    login: int | None = None
    password: str | None = None
    server: str | None = None
    timeout_ms: int = 60_000
    portable: bool = True
    validate_symbol_on_connect: bool = True


@dataclass(frozen=True, slots=True)
class SymbolSnapshot:
    name: str
    digits: int
    point: float
    trade_tick_size: float
    trade_tick_value: float
    trade_contract_size: float
    volume_min: float
    volume_max: float
    volume_step: float
    trade_stops_level: int
    trade_freeze_level: int
    spread: int
    spread_float: bool
    currency_base: str
    currency_profit: str
    currency_margin: str
    trade_mode: int
    filling_mode: int
    order_mode: int
    visible: bool
    raw: dict[str, Any]


@dataclass(frozen=True, slots=True)
class TickSnapshot:
    bid: float
    ask: float
    last: float
    volume: float
    time: int
    raw: dict[str, Any]


@dataclass(frozen=True, slots=True)
class AccountSnapshot:
    login: int
    trade_mode: int
    trade_allowed: bool
    trade_expert: bool
    balance: float
    equity: float
    margin: float
    margin_free: float
    currency: str
    server: str
    raw: dict[str, Any]


class MT5Client:
    """Thin MT5 wrapper that reads live broker metadata on every request."""

    def __init__(
        self,
        config: MT5ConnectionConfig | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self.config = config or MT5ConnectionConfig()
        self.logger = logger or logging.getLogger(__name__)
        self._connected = False

    def __enter__(self) -> "MT5Client":
        self.connect()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.shutdown()

    def connect(self) -> None:
        module = _require_mt5()
        kwargs: dict[str, Any] = {
            "timeout": self.config.timeout_ms,
            "portable": self.config.portable,
        }
        if self.config.terminal_path:
            kwargs["path"] = self.config.terminal_path
        if self.config.login is not None:
            kwargs["login"] = self.config.login
        if self.config.password:
            kwargs["password"] = self.config.password
        if self.config.server:
            kwargs["server"] = self.config.server

        if not module.initialize(**kwargs):
            raise MT5ClientError(f"MetaTrader5.initialize failed: {module.last_error()}")

        self._connected = True
        self.logger.info("Connected to MetaTrader5 terminal")
        if self.config.validate_symbol_on_connect:
            self.ensure_symbol(self.config.symbol)

    def shutdown(self) -> None:
        if mt5 is not None and self._connected:
            mt5.shutdown()
            self._connected = False
            self.logger.info("Disconnected from MetaTrader5 terminal")

    def ensure_symbol(self, symbol: str | None = None) -> SymbolSnapshot:
        module = _require_mt5()
        name = symbol or self.config.symbol
        info = module.symbol_info(name)
        if info is None:
            raise MT5ClientError(self.symbol_unavailable_message(name))
        if not bool(getattr(info, "visible", False)):
            if not module.symbol_select(name, True):
                raise MT5ClientError(f"symbol_select({name!r}, True) failed: {module.last_error()}")
        return self.get_symbol_info(name)

    def discover_symbols(self, patterns: Iterable[str] | None = None, limit: int = 50) -> list[dict[str, Any]]:
        module = _require_mt5()
        search_patterns = tuple(patterns or ("*Gold*", "*GOLD*", "*gold*", "*XAU*", "*xau*"))
        seen: set[str] = set()
        matches: list[dict[str, Any]] = []
        for pattern in search_patterns:
            symbols = module.symbols_get(pattern)
            if symbols is None:
                continue
            for symbol in symbols:
                data = _namedtuple_to_dict(symbol)
                name = str(data.get("name", ""))
                if not name or name in seen:
                    continue
                seen.add(name)
                matches.append(
                    {
                        "name": name,
                        "description": data.get("description"),
                        "path": data.get("path"),
                        "visible": bool(data.get("visible", False)),
                        "trade_mode": data.get("trade_mode"),
                        "currency_profit": data.get("currency_profit"),
                        "currency_margin": data.get("currency_margin"),
                        "spread": data.get("spread"),
                    }
                )
                if len(matches) >= limit:
                    return matches
        return matches

    def symbol_unavailable_message(self, symbol: str) -> str:
        module = _require_mt5()
        total = module.symbols_total()
        account = module.account_info()
        account_text = ""
        if account is not None:
            account_data = _namedtuple_to_dict(account)
            account_text = (
                f" account={account_data.get('login')} server={account_data.get('server')!r}"
                f" trade_mode={account_data.get('trade_mode')}"
            )
        candidates = self.discover_symbols(limit=12)
        if candidates:
            candidate_text = ", ".join(str(candidate["name"]) for candidate in candidates)
            hint = f" Gold/XAU candidates: {candidate_text}."
        else:
            hint = " No Gold/XAU candidates were returned by symbols_get()."
        return (
            f"symbol_info({symbol!r}) returned None; symbol is not available on this MT5 server."
            f"{account_text} symbols_total={total}. Last error: {module.last_error()}."
            f"{hint} Run: python scripts\\inspect_symbol.py --discover"
        )

    def get_symbol_info(self, symbol: str | None = None) -> SymbolSnapshot:
        """Read MetaTrader5.symbol_info(symbol) now; never use cached contract specs."""

        module = _require_mt5()
        name = symbol or self.config.symbol
        info = module.symbol_info(name)
        if info is None:
            raise MT5ClientError(f"symbol_info({name!r}) returned None: {module.last_error()}")
        data = _namedtuple_to_dict(info)
        return SymbolSnapshot(
            name=str(data["name"]),
            digits=int(data["digits"]),
            point=float(data["point"]),
            trade_tick_size=float(data["trade_tick_size"]),
            trade_tick_value=float(data["trade_tick_value"]),
            trade_contract_size=float(data["trade_contract_size"]),
            volume_min=float(data["volume_min"]),
            volume_max=float(data["volume_max"]),
            volume_step=float(data["volume_step"]),
            trade_stops_level=int(data.get("trade_stops_level", 0) or 0),
            trade_freeze_level=int(data.get("trade_freeze_level", 0) or 0),
            spread=int(data.get("spread", 0) or 0),
            spread_float=bool(data.get("spread_float", False)),
            currency_base=str(data.get("currency_base", "")),
            currency_profit=str(data.get("currency_profit", "")),
            currency_margin=str(data.get("currency_margin", "")),
            trade_mode=int(data.get("trade_mode", 0) or 0),
            filling_mode=int(data.get("filling_mode", 0) or 0),
            order_mode=int(data.get("order_mode", 0) or 0),
            visible=bool(data.get("visible", False)),
            raw=data,
        )

    def get_symbol_tick(self, symbol: str | None = None) -> TickSnapshot:
        module = _require_mt5()
        name = symbol or self.config.symbol
        tick = module.symbol_info_tick(name)
        if tick is None:
            raise MT5ClientError(f"symbol_info_tick({name!r}) returned None: {module.last_error()}")
        data = _namedtuple_to_dict(tick)
        return TickSnapshot(
            bid=float(data.get("bid", 0.0)),
            ask=float(data.get("ask", 0.0)),
            last=float(data.get("last", 0.0)),
            volume=float(data.get("volume", 0.0)),
            time=int(data.get("time", 0)),
            raw=data,
        )

    def get_account_info(self) -> AccountSnapshot:
        module = _require_mt5()
        account = module.account_info()
        if account is None:
            raise MT5ClientError(f"account_info() returned None: {module.last_error()}")
        data = _namedtuple_to_dict(account)
        return AccountSnapshot(
            login=int(data["login"]),
            trade_mode=int(data["trade_mode"]),
            trade_allowed=bool(data.get("trade_allowed", False)),
            trade_expert=bool(data.get("trade_expert", False)),
            balance=float(data["balance"]),
            equity=float(data["equity"]),
            margin=float(data["margin"]),
            margin_free=float(data["margin_free"]),
            currency=str(data.get("currency", "")),
            server=str(data.get("server", "")),
            raw=data,
        )

    def get_open_positions(self, symbol: str | None = None) -> list[Any]:
        module = _require_mt5()
        if symbol:
            positions = module.positions_get(symbol=symbol)
        else:
            positions = module.positions_get()
        if positions is None:
            raise MT5ClientError(f"positions_get failed: {module.last_error()}")
        return list(positions)

    def get_daily_realized_pnl(self, symbol: str | None = None, now_utc: datetime | None = None) -> float:
        module = _require_mt5()
        now = now_utc or datetime.now(timezone.utc)
        start = datetime.combine(now.date(), time.min, tzinfo=timezone.utc)
        deals = module.history_deals_get(start, now)
        if deals is None:
            raise MT5ClientError(f"history_deals_get failed: {module.last_error()}")

        pnl = 0.0
        for deal in deals:
            data = _namedtuple_to_dict(deal)
            if symbol and data.get("symbol") != symbol:
                continue
            pnl += float(data.get("profit", 0.0) or 0.0)
            pnl += float(data.get("swap", 0.0) or 0.0)
            pnl += float(data.get("commission", 0.0) or 0.0)
            pnl += float(data.get("fee", 0.0) or 0.0)
        return pnl

    def get_daily_order_count(
        self,
        symbol: str | None = None,
        magic_number: int | None = None,
        now_utc: datetime | None = None,
    ) -> int:
        module = _require_mt5()
        now = now_utc or datetime.now(timezone.utc)
        start = datetime.combine(now.date(), time.min, tzinfo=timezone.utc)
        deals = module.history_deals_get(start, now)
        if deals is None:
            raise MT5ClientError(f"history_deals_get failed: {module.last_error()}")

        count = 0
        for deal in deals:
            data = _namedtuple_to_dict(deal)
            if symbol and data.get("symbol") != symbol:
                continue
            if magic_number is not None and int(data.get("magic", 0) or 0) != magic_number:
                continue
            count += 1
        return count

    def get_history_orders(self, date_from: datetime, date_to: datetime) -> list[Any]:
        module = _require_mt5()
        orders = module.history_orders_get(date_from, date_to)
        if orders is None:
            raise MT5ClientError(f"history_orders_get failed: {module.last_error()}")
        return list(orders)

    def get_history_deals(self, date_from: datetime, date_to: datetime) -> list[Any]:
        module = _require_mt5()
        deals = module.history_deals_get(date_from, date_to)
        if deals is None:
            raise MT5ClientError(f"history_deals_get failed: {module.last_error()}")
        return list(deals)

    def copy_rates_from_pos(self, symbol: str, timeframe: str, count: int, start_pos: int = 0) -> Any:
        module = _require_mt5()
        if count <= 0:
            raise ValueError("count must be positive")
        self.ensure_symbol(symbol)
        rates = module.copy_rates_from_pos(symbol, timeframe_value(timeframe), start_pos, count)
        if rates is None:
            raise MT5ClientError(f"copy_rates_from_pos failed: {module.last_error()}")
        return rates

    def build_market_order_request(
        self,
        *,
        symbol: str,
        side: str,
        volume: float,
        stop_loss: float,
        take_profit: float | None,
        deviation_points: int,
        magic_number: int,
        comment: str,
    ) -> dict[str, Any]:
        module = _require_mt5()
        symbol_info = self.get_symbol_info(symbol)
        tick = self.get_symbol_tick(symbol)
        order_side = side.upper()
        if order_side not in {"BUY", "SELL"}:
            raise ValueError("side must be BUY or SELL")
        order_type = module.ORDER_TYPE_BUY if order_side == "BUY" else module.ORDER_TYPE_SELL
        price = tick.ask if order_side == "BUY" else tick.bid
        request: dict[str, Any] = {
            "action": module.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": order_type,
            "price": price,
            "sl": stop_loss,
            "deviation": deviation_points,
            "magic": magic_number,
            "comment": comment,
            "type_time": module.ORDER_TIME_GTC,
            "type_filling": select_order_filling(symbol_info.filling_mode),
        }
        if take_profit is not None:
            request["tp"] = take_profit

        return request

    def build_close_position_request(
        self,
        *,
        position: Any,
        deviation_points: int,
        magic_number: int,
        comment: str,
    ) -> dict[str, Any]:
        module = _require_mt5()
        symbol = str(getattr(position, "symbol"))
        tick = self.get_symbol_tick(symbol)
        symbol_info = self.get_symbol_info(symbol)
        position_type = int(getattr(position, "type"))
        if position_type == int(module.POSITION_TYPE_BUY):
            order_type = module.ORDER_TYPE_SELL
            price = tick.bid
        else:
            order_type = module.ORDER_TYPE_BUY
            price = tick.ask
        return {
            "action": module.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": float(getattr(position, "volume")),
            "type": order_type,
            "position": int(getattr(position, "ticket")),
            "price": price,
            "deviation": deviation_points,
            "magic": magic_number,
            "comment": comment,
            "type_time": module.ORDER_TIME_GTC,
            "type_filling": select_order_filling(symbol_info.filling_mode),
        }

    def order_check(self, request: dict[str, Any]) -> Any:
        module = _require_mt5()
        result = module.order_check(request)
        if result is None:
            raise MT5ClientError(f"order_check returned None: {module.last_error()}")
        return result

    def order_send_checked(self, request: dict[str, Any], order_check_result: Any) -> Any:
        from src.broker.execution_safety import order_check_passed

        if not order_check_passed(order_check_result):
            raise MT5ClientError("order_send blocked because order_check did not pass")
        module = _require_mt5()
        result = module.order_send(request)
        if result is None:
            raise MT5ClientError(f"order_send returned None: {module.last_error()}")
        return result

    def place_market_order(
        self,
        *,
        symbol: str,
        side: str,
        volume: float,
        stop_loss: float,
        take_profit: float | None,
        deviation_points: int,
        magic_number: int,
        comment: str,
    ) -> Any:
        request = self.build_market_order_request(
            symbol=symbol,
            side=side,
            volume=volume,
            stop_loss=stop_loss,
            take_profit=take_profit,
            deviation_points=deviation_points,
            magic_number=magic_number,
            comment=comment,
        )
        check_result = self.order_check(request)
        return self.order_send_checked(request, check_result)


def timeframe_value(timeframe: str) -> int:
    module = _require_mt5()
    normalized = timeframe.upper()
    names = {
        "M1": "TIMEFRAME_M1",
        "M5": "TIMEFRAME_M5",
        "M15": "TIMEFRAME_M15",
        "M30": "TIMEFRAME_M30",
        "H1": "TIMEFRAME_H1",
        "H4": "TIMEFRAME_H4",
        "D1": "TIMEFRAME_D1",
    }
    if normalized not in names:
        raise ValueError(f"unsupported timeframe: {timeframe}")
    return int(getattr(module, names[normalized]))


def select_order_filling(symbol_filling_mode: int) -> int:
    module = _require_mt5()
    numeric_fallbacks: Iterable[tuple[int, str]] = (
        (1, "ORDER_FILLING_FOK"),
        (2, "ORDER_FILLING_IOC"),
        (4, "ORDER_FILLING_BOC"),
    )
    choices: Iterable[tuple[str, str]] = (
        ("SYMBOL_FILLING_FOK", "ORDER_FILLING_FOK"),
        ("SYMBOL_FILLING_IOC", "ORDER_FILLING_IOC"),
        ("SYMBOL_FILLING_BOC", "ORDER_FILLING_BOC"),
    )
    for symbol_constant, order_constant in choices:
        if hasattr(module, symbol_constant) and hasattr(module, order_constant):
            if symbol_filling_mode & int(getattr(module, symbol_constant)):
                return int(getattr(module, order_constant))
    for symbol_flag, order_constant in numeric_fallbacks:
        if symbol_filling_mode & symbol_flag and hasattr(module, order_constant):
            return int(getattr(module, order_constant))
    return int(getattr(module, "ORDER_FILLING_RETURN"))


def _require_mt5() -> Any:
    if mt5 is None:
        raise MT5ClientError(
            "MetaTrader5 Python package is not installed. Install requirements on the Windows "
            "machine running the XM MT5 terminal."
        )
    return mt5


def _namedtuple_to_dict(value: Any) -> dict[str, Any]:
    if hasattr(value, "_asdict"):
        return dict(value._asdict())
    raise MT5ClientError(f"expected MetaTrader5 namedtuple, got {type(value)!r}")
