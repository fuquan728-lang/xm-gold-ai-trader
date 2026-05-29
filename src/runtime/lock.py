from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


DEFAULT_RUNTIME_DIR = Path(".runtime")
DEFAULT_LOCK_PATH = DEFAULT_RUNTIME_DIR / "xm_gold_ai_trader.lock"
DEFAULT_EMERGENCY_STOP_PATH = DEFAULT_RUNTIME_DIR / "EMERGENCY_STOP"
DEFAULT_LOCK_STALE_AFTER_SECONDS = 15 * 60

REASON_RUNTIME_LOCK_EXISTS = "RUNTIME_LOCK_EXISTS"
REASON_STALE_RUNTIME_LOCK_RECOVERED = "STALE_RUNTIME_LOCK_RECOVERED"
REASON_EMERGENCY_STOP_FILE_PRESENT = "EMERGENCY_STOP_FILE_PRESENT"


@dataclass(frozen=True, slots=True)
class RuntimeLockResult:
    acquired: bool
    reason_codes: tuple[str, ...] = ()
    reasons: tuple[str, ...] = ()
    stale_recovered: bool = False


class RuntimeLock:
    def __init__(
        self,
        path: Path | str = DEFAULT_LOCK_PATH,
        *,
        stale_after_seconds: int = DEFAULT_LOCK_STALE_AFTER_SECONDS,
    ) -> None:
        self.path = Path(path)
        self.stale_after_seconds = stale_after_seconds
        self.token = str(uuid4())
        self.acquired = False

    def acquire(self, now_utc: datetime | None = None) -> RuntimeLockResult:
        now = now_utc or datetime.now(timezone.utc)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        stale_recovered = False

        if self.path.exists():
            age_seconds = max(0.0, (now - lock_timestamp(self.path)).total_seconds())
            if age_seconds < self.stale_after_seconds:
                return RuntimeLockResult(
                    acquired=False,
                    reason_codes=(REASON_RUNTIME_LOCK_EXISTS,),
                    reasons=(
                        f"{REASON_RUNTIME_LOCK_EXISTS}: runtime lock exists at {self.path} "
                        f"and age {age_seconds:.1f}s is below stale timeout {self.stale_after_seconds}s",
                    ),
                )
            self.path.unlink(missing_ok=True)
            stale_recovered = True

        payload = {
            "project": "xm-gold-ai-trader",
            "pid": os.getpid(),
            "token": self.token,
            "acquired_at_utc": now.isoformat(),
        }
        try:
            with self.path.open("x", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2, sort_keys=True)
        except FileExistsError:
            return RuntimeLockResult(
                acquired=False,
                reason_codes=(REASON_RUNTIME_LOCK_EXISTS,),
                reasons=(f"{REASON_RUNTIME_LOCK_EXISTS}: runtime lock already exists at {self.path}",),
            )

        self.acquired = True
        if stale_recovered:
            return RuntimeLockResult(
                acquired=True,
                reason_codes=(REASON_STALE_RUNTIME_LOCK_RECOVERED,),
                reasons=(f"{REASON_STALE_RUNTIME_LOCK_RECOVERED}: recovered stale runtime lock at {self.path}",),
                stale_recovered=True,
            )
        return RuntimeLockResult(acquired=True)

    def release(self) -> None:
        if not self.acquired or not self.path.exists():
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            payload = {}
        if payload.get("token") == self.token:
            self.path.unlink(missing_ok=True)
        self.acquired = False

    def __enter__(self) -> "RuntimeLock":
        result = self.acquire()
        if not result.acquired:
            raise RuntimeError("; ".join(result.reasons))
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self.release()


def lock_timestamp(path: Path) -> datetime:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        acquired = payload.get("acquired_at_utc")
        if acquired:
            parsed = datetime.fromisoformat(str(acquired).replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
    except (OSError, json.JSONDecodeError, ValueError):
        pass
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)


def emergency_stop_file_decision(path: Path | str = DEFAULT_EMERGENCY_STOP_PATH) -> RuntimeLockResult:
    stop_path = Path(path)
    if not stop_path.exists():
        return RuntimeLockResult(acquired=True)
    return RuntimeLockResult(
        acquired=False,
        reason_codes=(REASON_EMERGENCY_STOP_FILE_PRESENT,),
        reasons=(f"{REASON_EMERGENCY_STOP_FILE_PRESENT}: emergency stop file exists at {stop_path}",),
    )
