from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.dry_run_signal_report import (
    REASON_JOURNAL_JSON_INVALID,
    REASON_JOURNAL_NOT_OBJECT,
    load_dry_run_journals,
    missing_required_fields,
    numeric_or_none,
)
from scripts.live_dry_run_signal_journal import DEFAULT_JOURNAL_DIR, PROJECT
from src.logging_config import configure_logging


MODE = "annotate_dry_run_signals"
ANNOTATION_MODE = "ai_signal_annotation"
ANNOTATION_SCHEMA_VERSION = 1
DEFAULT_ANNOTATION_DIR = Path("logs/ai_annotations")

REASON_AI_PROVIDER_DISABLED = "AI_PROVIDER_DISABLED"
REASON_SOURCE_JOURNAL_MALFORMED = "SOURCE_JOURNAL_MALFORMED"
REASON_SOURCE_JOURNAL_REQUIRED_FIELD_MISSING = "SOURCE_JOURNAL_REQUIRED_FIELD_MISSING"
REASON_ANNOTATION_NOT_OBJECT = "ANNOTATION_NOT_OBJECT"
REASON_ANNOTATION_SCHEMA_FIELD_MISSING = "ANNOTATION_SCHEMA_FIELD_MISSING"
REASON_ANNOTATION_UNEXPECTED_FIELD = "ANNOTATION_UNEXPECTED_FIELD"
REASON_ANNOTATION_FORBIDDEN_FIELD = "ANNOTATION_FORBIDDEN_FIELD"

ALLOWED_ANNOTATION_KEYS = frozenset(
    {
        "market_regime",
        "trend_context",
        "volatility_context",
        "spread_context",
        "signal_quality_comment",
        "risk_notes",
        "do_not_trade_reason",
        "confidence_text",
    }
)
FORBIDDEN_TERMS = (
    "BUY",
    "SELL",
    "LONG",
    "SHORT",
    "lot",
    "volume",
    "SL",
    "TP",
    "stop_loss",
    "take_profit",
    "entry",
    "entry_price",
    "order_send",
)
FORBIDDEN_TEXT_TERMS = FORBIDDEN_TERMS + ("stop loss", "take profit")
FORBIDDEN_KEY_NORMALIZED = {term.lower() for term in FORBIDDEN_TERMS}


def main() -> int:
    args = parse_args()
    logger = configure_logging(logger_name="annotate_dry_run_signals")
    try:
        report = annotate_dry_run_signals(
            source_dir=Path(args.source_dir),
            output_dir=Path(args.output_dir),
            provider=args.provider,
            mock_ai=args.mock_ai,
        )
    except Exception as exc:  # pragma: no cover - defensive CLI guard.
        logger.exception("AI annotation failed")
        print(str(exc), file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True, default=str))
    else:
        print_summary(report)
    return 0


def annotate_dry_run_signals(
    *,
    source_dir: Path,
    output_dir: Path,
    provider: str = "mock",
    mock_ai: bool = True,
) -> dict[str, Any]:
    if provider != "mock" or not mock_ai:
        return {
            "project": PROJECT,
            "mode": MODE,
            "annotation_schema_version": ANNOTATION_SCHEMA_VERSION,
            "source_dir": str(source_dir),
            "output_dir": str(output_dir),
            "provider": provider,
            "mock_ai": mock_ai,
            "source_journals_total": 0,
            "annotations_written": 0,
            "rejected_annotations": 0,
            "malformed_source_journals": 0,
            "reason_codes": [REASON_AI_PROVIDER_DISABLED],
            "reasons": [f"{REASON_AI_PROVIDER_DISABLED}: only deterministic --mock-ai annotations are enabled"],
            "annotation_paths": [],
            "orders_sent": 0,
            "order_check_called": False,
            "order_send_called": False,
            "hard_safety": hard_safety(),
        }

    output_dir.mkdir(parents=True, exist_ok=True)
    existing_source_hashes = load_existing_accepted_source_hashes(output_dir)
    entries = load_dry_run_journals(source_dir)
    paths: list[str] = []
    reason_counter: Counter[str] = Counter()
    annotations_written = 0
    annotations_skipped_existing = 0
    rejected_annotations = 0
    malformed_source_journals = 0

    for entry in entries:
        source_path = Path(entry["path"])
        source_hash = sha256_file(source_path)
        if source_hash in existing_source_hashes:
            annotations_skipped_existing += 1
            continue
        payload = entry["payload"]
        if payload is None:
            malformed_source_journals += 1
            rejected_annotations += 1
            codes = [REASON_SOURCE_JOURNAL_MALFORMED, *(entry.get("reason_codes") or [])]
            journal = build_rejection_journal(
                source_path=source_path,
                source_hash=source_hash,
                reason_codes=dedupe(codes),
                reasons=[f"{REASON_SOURCE_JOURNAL_MALFORMED}: {entry.get('error') or 'source journal could not be parsed'}"],
                provider=provider,
                source_payload=None,
            )
            paths.append(write_annotation_journal(output_dir, journal))
            reason_counter.update(journal["reason_codes"])
            continue

        missing = missing_required_fields(payload)
        if missing:
            rejected_annotations += 1
            journal = build_rejection_journal(
                source_path=source_path,
                source_hash=source_hash,
                reason_codes=[REASON_SOURCE_JOURNAL_REQUIRED_FIELD_MISSING],
                reasons=[f"{REASON_SOURCE_JOURNAL_REQUIRED_FIELD_MISSING}: missing {', '.join(missing)}"],
                provider=provider,
                source_payload=payload,
            )
            paths.append(write_annotation_journal(output_dir, journal))
            reason_counter.update(journal["reason_codes"])
            continue

        annotation = build_mock_annotation(payload)
        validation = validate_annotation(annotation)
        if validation:
            rejected_annotations += 1
            journal = build_rejection_journal(
                source_path=source_path,
                source_hash=source_hash,
                reason_codes=dedupe([item["reason_code"] for item in validation]),
                reasons=[item["reason"] for item in validation],
                provider=provider,
                source_payload=payload,
                validation_violations=validation,
            )
            paths.append(write_annotation_journal(output_dir, journal))
            reason_counter.update(journal["reason_codes"])
            continue

        journal = build_annotation_journal(
            source_path=source_path,
            source_hash=source_hash,
            source_payload=payload,
            annotation=annotation,
            provider=provider,
        )
        paths.append(write_annotation_journal(output_dir, journal))
        annotations_written += 1
        existing_source_hashes.add(source_hash)

    return {
        "project": PROJECT,
        "mode": MODE,
        "annotation_schema_version": ANNOTATION_SCHEMA_VERSION,
        "source_dir": str(source_dir),
        "output_dir": str(output_dir),
        "provider": provider,
        "mock_ai": mock_ai,
        "source_journals_total": len(entries),
        "annotations_written": annotations_written,
        "annotations_skipped_existing": annotations_skipped_existing,
        "rejected_annotations": rejected_annotations,
        "malformed_source_journals": malformed_source_journals,
        "reason_codes": sorted(reason_counter),
        "reasons": [f"{code}: see annotation journals for details" for code in sorted(reason_counter)],
        "annotation_paths": paths,
        "orders_sent": 0,
        "order_check_called": False,
        "order_send_called": False,
        "hard_safety": hard_safety(),
    }


def load_existing_accepted_source_hashes(output_dir: Path) -> set[str]:
    hashes: set[str] = set()
    if not output_dir.exists():
        return hashes
    for path in output_dir.glob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, Mapping):
            continue
        if payload.get("annotation_status") != "ACCEPTED":
            continue
        source_hash = payload.get("source_journal_hash")
        if source_hash:
            hashes.add(str(source_hash))
    return hashes


def build_mock_annotation(source_payload: Mapping[str, Any]) -> dict[str, str]:
    final_decision = str(source_payload.get("final_decision") or "UNKNOWN")
    reason_codes = set(str(code) for code in (source_payload.get("reason_codes") or []))
    risk_codes = set(str(code) for code in ((source_payload.get("risk_preview") or {}).get("reason_codes") or []))
    all_codes = reason_codes | risk_codes
    spread = numeric_or_none(source_payload.get("current_spread_points"))

    if "EMERGENCY_STOP_FILE_PRESENT" in all_codes:
        market_regime = "safety_stop_observation"
    elif any("SPREAD" in code for code in all_codes):
        market_regime = "spread_constrained"
    elif final_decision == "SIGNAL":
        market_regime = "baseline_condition_present"
    elif final_decision == "SKIP":
        market_regime = "duplicate_bar_observation"
    else:
        market_regime = "neutral_or_unclear"

    spread_context = "Spread was unavailable in the source journal."
    if spread is not None:
        spread_context = f"Observed spread was {spread:.1f} points in the source journal."

    risk_notes = "Risk preview was not evaluated because the source observation had no actionable condition."
    if (source_payload.get("risk_preview") or {}).get("evaluated"):
        risk_notes = "Risk preview was reviewed for guardrail context only."
    if any("BELOW" in code for code in all_codes):
        risk_notes = "Risk preview indicated the computed size was below the broker minimum."

    return {
        "market_regime": market_regime,
        "trend_context": trend_context(final_decision),
        "volatility_context": "ATR-derived context is treated as descriptive observation only.",
        "spread_context": spread_context,
        "signal_quality_comment": f"Read-only comment; source final decision remains {final_decision}.",
        "risk_notes": risk_notes,
        "do_not_trade_reason": "This annotation never authorizes execution or changes the source decision.",
        "confidence_text": "Descriptive confidence only; not an execution confidence score.",
    }


def trend_context(final_decision: str) -> str:
    if final_decision == "SIGNAL":
        return "Baseline crossover condition was present on the latest closed bar."
    if final_decision == "SKIP":
        return "No new closed bar was available for a fresh observation."
    return "No actionable crossover condition was present on the latest closed bar."


def validate_annotation(annotation: Any) -> list[dict[str, str]]:
    violations: list[dict[str, str]] = []
    if not isinstance(annotation, Mapping):
        return [
            {
                "reason_code": REASON_ANNOTATION_NOT_OBJECT,
                "reason": f"{REASON_ANNOTATION_NOT_OBJECT}: annotation must be a JSON object",
                "path": "annotation",
            }
        ]

    missing = sorted(ALLOWED_ANNOTATION_KEYS.difference(annotation.keys()))
    if missing:
        violations.append(
            {
                "reason_code": REASON_ANNOTATION_SCHEMA_FIELD_MISSING,
                "reason": f"{REASON_ANNOTATION_SCHEMA_FIELD_MISSING}: missing {', '.join(missing)}",
                "path": "annotation",
            }
        )
    unexpected = sorted(set(annotation.keys()).difference(ALLOWED_ANNOTATION_KEYS))
    if unexpected:
        violations.append(
            {
                "reason_code": REASON_ANNOTATION_UNEXPECTED_FIELD,
                "reason": f"{REASON_ANNOTATION_UNEXPECTED_FIELD}: unexpected {', '.join(unexpected)}",
                "path": "annotation",
            }
        )

    for path, key, value in walk_annotation(annotation):
        if key is not None and is_forbidden_key(key):
            violations.append(
                {
                    "reason_code": REASON_ANNOTATION_FORBIDDEN_FIELD,
                    "reason": f"{REASON_ANNOTATION_FORBIDDEN_FIELD}: forbidden key {path}",
                    "path": path,
                }
            )
        if isinstance(value, str):
            term = first_forbidden_text_term(value)
            if term is not None:
                violations.append(
                    {
                        "reason_code": REASON_ANNOTATION_FORBIDDEN_FIELD,
                        "reason": f"{REASON_ANNOTATION_FORBIDDEN_FIELD}: forbidden term {term!r} at {path}",
                        "path": path,
                    }
                )
    return violations


def walk_annotation(value: Any, prefix: str = "annotation") -> list[tuple[str, str | None, Any]]:
    items: list[tuple[str, str | None, Any]] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            child_path = f"{prefix}.{key}"
            items.append((child_path, str(key), child))
            items.extend(walk_annotation(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            child_path = f"{prefix}[{index}]"
            items.append((child_path, None, child))
            items.extend(walk_annotation(child, child_path))
    return items


def is_forbidden_key(key: str) -> bool:
    return key.lower() in FORBIDDEN_KEY_NORMALIZED


def first_forbidden_text_term(value: str) -> str | None:
    for term in FORBIDDEN_TEXT_TERMS:
        if re.search(rf"(?<![A-Za-z0-9_]){re.escape(term)}(?![A-Za-z0-9_])", value, flags=re.IGNORECASE):
            return term
    return None


def build_annotation_journal(
    *,
    source_path: Path,
    source_hash: str,
    source_payload: Mapping[str, Any],
    annotation: Mapping[str, str],
    provider: str,
) -> dict[str, Any]:
    source_final_decision = source_payload.get("final_decision")
    return {
        "project": PROJECT,
        "mode": ANNOTATION_MODE,
        "annotation_schema_version": ANNOTATION_SCHEMA_VERSION,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "source_journal_path": str(source_path),
        "source_journal_hash": source_hash,
        "source_timestamp_utc": source_payload.get("timestamp_utc"),
        "source_final_decision": source_final_decision,
        "source_reason_codes": list(source_payload.get("reason_codes") or []),
        "final_decision": source_final_decision,
        "annotation_provider": provider,
        "annotation_status": "ACCEPTED",
        "annotation": dict(annotation),
        "validation_violations": [],
        "reason_codes": [],
        "reasons": [],
        "orders_sent": 0,
        "order_check_called": False,
        "order_send_called": False,
        "hard_safety": hard_safety(),
    }


def build_rejection_journal(
    *,
    source_path: Path,
    source_hash: str,
    reason_codes: list[str],
    reasons: list[str],
    provider: str,
    source_payload: Mapping[str, Any] | None,
    validation_violations: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    source_final_decision = source_payload.get("final_decision") if source_payload is not None else None
    return {
        "project": PROJECT,
        "mode": ANNOTATION_MODE,
        "annotation_schema_version": ANNOTATION_SCHEMA_VERSION,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "source_journal_path": str(source_path),
        "source_journal_hash": source_hash,
        "source_timestamp_utc": source_payload.get("timestamp_utc") if source_payload is not None else None,
        "source_final_decision": source_final_decision,
        "source_reason_codes": list(source_payload.get("reason_codes") or []) if source_payload is not None else [],
        "final_decision": source_final_decision if source_final_decision is not None else "BLOCK",
        "annotation_provider": provider,
        "annotation_status": "REJECTED",
        "annotation": None,
        "validation_violations": validation_violations or [],
        "reason_codes": reason_codes,
        "reasons": reasons,
        "orders_sent": 0,
        "order_check_called": False,
        "order_send_called": False,
        "hard_safety": hard_safety(),
    }


def write_annotation_journal(output_dir: Path, journal: Mapping[str, Any]) -> str:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    source_stem = Path(str(journal.get("source_journal_path") or "source")).stem
    path = output_dir / f"ai_annotation_{source_stem}_{timestamp}.json"
    path.write_text(json.dumps(journal, indent=2, sort_keys=True, default=str), encoding="utf-8")
    return str(path)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def hard_safety() -> dict[str, bool]:
    return {
        "ai_model_trading": False,
        "order_check": False,
        "order_send": False,
        "martingale": False,
        "grid": False,
        "lot_increase_after_loss": False,
    }


def dedupe(values: list[str]) -> list[str]:
    output: list[str] = []
    for value in values:
        if value not in output:
            output.append(value)
    return output


def print_summary(report: Mapping[str, Any]) -> None:
    print("xm-gold-ai-trader AI signal annotation")
    print(f"source journals: {report['source_journals_total']}")
    print(f"annotations written: {report['annotations_written']}")
    print(f"rejected annotations: {report['rejected_annotations']}")
    print(f"malformed source journals: {report['malformed_source_journals']}")
    print("orders_sent: 0")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create read-only AI-style annotations for dry-run signal journals.")
    parser.add_argument("--source-dir", default=str(DEFAULT_JOURNAL_DIR))
    parser.add_argument("--output-dir", default=str(DEFAULT_ANNOTATION_DIR))
    parser.add_argument("--mock-ai", action="store_true", default=True)
    parser.add_argument("--provider", default="mock", help="Reserved for later; only 'mock' is enabled.")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
