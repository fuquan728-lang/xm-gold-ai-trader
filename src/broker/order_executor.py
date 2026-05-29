from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from src.broker.execution_safety import (
    ExecutionConfig,
    ExecutionSafetyDecision,
    REASON_ALLOW_ORDER_SEND_FALSE,
    evaluate_execution_safety,
    order_check_failure_decision,
    order_check_passed,
)
from src.broker.mt5_client import MT5Client
from src.strategy.baseline_signal import TradeSignal
from src.strategy.risk_manager import (
    AccountState,
    RiskConfig,
    RiskDecision,
    RiskManager,
    TradeRiskRequest,
    spread_points_from_prices,
)


REASON_HOLD_SIGNAL = "HOLD_SIGNAL"
REASON_SIGNAL_SYMBOL_MISMATCH = "SIGNAL_SYMBOL_MISMATCH"
REASON_INVALID_SIGNAL = "INVALID_SIGNAL"
REASON_ORDER_SEND_DISABLED = REASON_ALLOW_ORDER_SEND_FALSE


@dataclass(frozen=True, slots=True)
class TradingConfig:
    symbol: str = "GOLD_"
    deviation_points: int = 50
    magic_number: int = 26052601
    order_comment: str = "xm-gold-ai-trader"
    execution: ExecutionConfig = field(default_factory=ExecutionConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)

    @property
    def paper_mode(self) -> bool:
        return not self.execution.allow_order_send

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "TradingConfig":
        risk_data = data.get("risk", {})
        if risk_data is None:
            risk_data = {}
        if not isinstance(risk_data, Mapping):
            raise ValueError("risk config must be a mapping")
        execution_data = data.get("execution", {})
        if execution_data is None:
            execution_data = {}
        if not isinstance(execution_data, Mapping):
            raise ValueError("execution config must be a mapping")
        return cls(
            symbol=str(data.get("symbol", "GOLD_")),
            deviation_points=int(data.get("deviation_points", 50)),
            magic_number=int(data.get("magic_number", 26052601)),
            order_comment=str(data.get("order_comment", "xm-gold-ai-trader")),
            execution=ExecutionConfig(**dict(execution_data)),
            risk=RiskConfig(**dict(risk_data)),
        )


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    status: str
    symbol: str
    side: str
    volume: float
    paper_mode: bool
    risk_decision: RiskDecision | None = None
    execution_decision: ExecutionSafetyDecision | None = None
    order_check_result: Any = None
    reason_codes: tuple[str, ...] = ()
    order_result: Any = None
    message: str = ""


class OrderExecutor:
    """Applies risk gates, then either paper-logs or sends an MT5 order."""

    def __init__(
        self,
        mt5_client: MT5Client,
        config: TradingConfig | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self.mt5_client = mt5_client
        self.config = config or TradingConfig()
        self.risk_manager = RiskManager(self.config.risk)
        self.logger = logger or logging.getLogger(__name__)

    def execute_signal(self, signal: TradeSignal) -> ExecutionResult:
        if signal.side == "HOLD":
            return ExecutionResult(
                status="skipped",
                symbol=signal.symbol,
                side=signal.side,
                volume=0.0,
                paper_mode=self.config.paper_mode,
                reason_codes=(REASON_HOLD_SIGNAL,),
                message=signal.reason or "hold signal",
            )

        if signal.symbol != self.config.symbol:
            message = f"signal symbol {signal.symbol!r} does not match configured symbol {self.config.symbol!r}"
            self.logger.warning(message)
            return ExecutionResult(
                status="blocked",
                symbol=signal.symbol,
                side=signal.side,
                volume=0.0,
                paper_mode=self.config.paper_mode,
                reason_codes=(REASON_SIGNAL_SYMBOL_MISMATCH,),
                message=message,
            )

        if not signal.is_actionable:
            message = "actionable signal must include entry and stop-loss prices"
            self.logger.warning(message)
            return ExecutionResult(
                status="blocked",
                symbol=signal.symbol,
                side=signal.side,
                volume=0.0,
                paper_mode=self.config.paper_mode,
                reason_codes=(REASON_INVALID_SIGNAL,),
                message=message,
            )

        symbol_info = self.mt5_client.get_symbol_info(self.config.symbol)
        tick = self.mt5_client.get_symbol_tick(self.config.symbol)
        account = self.mt5_client.get_account_info()
        positions = self.mt5_client.get_open_positions(self.config.symbol)
        daily_pnl = self.mt5_client.get_daily_realized_pnl(self.config.symbol)
        entry_price = tick.ask if signal.side == "BUY" else tick.bid
        current_spread = spread_points_from_prices(tick.bid, tick.ask, symbol_info.point)

        execution_decision = evaluate_execution_safety(
            config=self.config.execution,
            account_info=account.raw if account is not None else None,
            symbol=self.config.symbol,
            open_positions=positions,
            project_magic=self.config.magic_number,
            require_order_send_permission=self.config.execution.allow_order_send,
        )
        if not execution_decision.allowed:
            message = "; ".join(execution_decision.reasons)
            self.logger.warning(
                "Trade blocked by execution safety: codes=%s reasons=%s",
                ",".join(execution_decision.reason_codes),
                message,
            )
            return ExecutionResult(
                status="blocked",
                symbol=self.config.symbol,
                side=signal.side,
                volume=0.0,
                paper_mode=self.config.paper_mode,
                execution_decision=execution_decision,
                reason_codes=execution_decision.reason_codes,
                message=message,
            )

        risk_decision = self.risk_manager.assess_trade(
            TradeRiskRequest(
                symbol_info=symbol_info.raw,
                account=AccountState(
                    balance=account.balance,
                    equity=account.equity,
                    daily_realized_pnl=daily_pnl,
                ),
                side=signal.side,
                entry_price=entry_price,
                stop_loss_price=float(signal.stop_loss_price),
                take_profit_price=signal.take_profit_price,
                current_spread_points=current_spread,
                open_positions=positions,
            )
        )
        if not risk_decision.allowed:
            message = "; ".join(risk_decision.reasons)
            self.logger.warning(
                "Trade blocked by risk manager: codes=%s reasons=%s",
                ",".join(risk_decision.reason_codes),
                message,
            )
            return ExecutionResult(
                status="blocked",
                symbol=self.config.symbol,
                side=signal.side,
                volume=0.0,
                paper_mode=self.config.paper_mode,
                risk_decision=risk_decision,
                reason_codes=risk_decision.reason_codes,
                message=message,
            )

        if self.config.paper_mode:
            self.logger.info(
                "Paper trade accepted: symbol=%s side=%s volume=%.4f entry=%.5f sl=%.5f tp=%s",
                self.config.symbol,
                signal.side,
                risk_decision.volume,
                entry_price,
                signal.stop_loss_price,
                signal.take_profit_price,
            )
            return ExecutionResult(
                status="paper",
                symbol=self.config.symbol,
                side=signal.side,
                volume=risk_decision.volume,
                paper_mode=True,
                risk_decision=risk_decision,
                execution_decision=execution_decision,
                reason_codes=(REASON_ORDER_SEND_DISABLED,),
                message="paper mode: live order was not sent",
            )

        order_request = self.mt5_client.build_market_order_request(
            symbol=self.config.symbol,
            side=signal.side,
            volume=risk_decision.volume,
            stop_loss=float(signal.stop_loss_price),
            take_profit=signal.take_profit_price,
            deviation_points=self.config.deviation_points,
            magic_number=self.config.magic_number,
            comment=self.config.order_comment,
        )
        order_check_result = self.mt5_client.order_check(order_request)
        if not order_check_passed(order_check_result):
            check_decision = order_check_failure_decision(order_check_result)
            return ExecutionResult(
                status="blocked",
                symbol=self.config.symbol,
                side=signal.side,
                volume=0.0,
                paper_mode=False,
                risk_decision=risk_decision,
                execution_decision=execution_decision,
                order_check_result=order_check_result,
                reason_codes=check_decision.reason_codes,
                message="; ".join(check_decision.reasons),
            )

        order_result = self.mt5_client.order_send_checked(order_request, order_check_result)
        self.logger.info("Live order sent: %s", order_result)
        return ExecutionResult(
            status="sent",
            symbol=self.config.symbol,
            side=signal.side,
            volume=risk_decision.volume,
            paper_mode=False,
            risk_decision=risk_decision,
            execution_decision=execution_decision,
            order_check_result=order_check_result,
            reason_codes=(),
            order_result=order_result,
            message="live order sent",
        )


def load_trading_config(path: str | Path) -> TradingConfig:
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(config_path)

    if config_path.suffix.lower() == ".json":
        data = json.loads(config_path.read_text(encoding="utf-8"))
    elif config_path.suffix.lower() in {".yaml", ".yml"}:
        try:
            import yaml  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError("PyYAML is required to read YAML configs. Install requirements.txt.") from exc
        data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    else:
        raise ValueError("config file must be .json, .yaml, or .yml")

    if not isinstance(data, Mapping):
        raise ValueError("trading config must be a mapping")
    return TradingConfig.from_mapping(data)


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "y", "on"}:
            return True
        if normalized in {"false", "0", "no", "n", "off", ""}:
            return False
    return bool(value)
