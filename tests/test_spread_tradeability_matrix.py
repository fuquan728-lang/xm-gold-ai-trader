from pathlib import Path

from scripts.spread_tradeability_matrix import (
    CsvSpec,
    build_tradeability_matrix,
    load_csv_bars,
)


def write_csv(path: Path, rows: list[tuple[str, float, float, float, float, int]]) -> None:
    lines = ["time,open,high,low,close,tick_volume,spread,real_volume"]
    for timestamp, open_price, high, low, close, spread in rows:
        lines.append(f"{timestamp},{open_price},{high},{low},{close},100,{spread},0")
    path.write_text("\n".join(lines), encoding="utf-8")


def test_zero_spread_csv_is_not_treated_as_low_cost(tmp_path):
    csv_path = tmp_path / "eurusd_m15.csv"
    write_csv(
        csv_path,
        [
            ("2026-03-10 04:00:00+00:00", 1.1000, 1.1010, 1.0990, 1.1005, 0),
            ("2026-03-10 04:15:00+00:00", 1.1005, 1.1015, 1.0995, 1.1010, 0),
        ],
    )

    report = build_tradeability_matrix(
        [CsvSpec(path=csv_path, symbol="EURUSD")],
        timeframes=["M15"],
        min_bars=2,
    )

    row = report["matrix"][0]
    assert row["status"] == "MISSING_SPREAD_DATA"
    assert row["spread_data_quality"] == "MISSING_OR_ZERO_SPREAD"
    assert row["absolute_spread_gate_pass"] is None
    assert report["status"] == "NEEDS_REAL_SPREAD_DATA"


def test_longer_timeframe_can_reduce_spread_cost_ratio(tmp_path):
    csv_path = tmp_path / "gold_m15.csv"
    rows = []
    for index in range(8):
        hour = 4 + (index // 4)
        minute = (index % 4) * 15
        base = 5000 + (index * 1.0)
        rows.append(
            (
                f"2026-03-10 {hour:02d}:{minute:02d}:00+00:00",
                base,
                base + 0.5,
                base - 0.5,
                base + 0.1,
                50,
            )
        )
    write_csv(csv_path, rows)

    report = build_tradeability_matrix(
        [CsvSpec(path=csv_path, symbol="GOLD_", point=0.01)],
        timeframes=["M15", "H1"],
        min_bars=2,
    )

    m15 = next(row for row in report["matrix"] if row["timeframe"] == "M15")
    h1 = next(row for row in report["matrix"] if row["timeframe"] == "H1")
    assert m15["status"] == "BLOCKED_BY_SPREAD_COST"
    assert h1["status"] == "LONGER_TIMEFRAME_RESEARCH_CANDIDATE"
    assert h1["spread_to_range_pct"]["p50"] < m15["spread_to_range_pct"]["p50"]
    assert report["status"] == "LONGER_TIMEFRAME_RESEARCH_CANDIDATES"


def test_lower_spread_account_override_can_be_modeled(tmp_path):
    csv_path = tmp_path / "gold_m15.csv"
    write_csv(
        csv_path,
        [
            ("2026-03-10 04:00:00+00:00", 5000, 5005, 4995, 5001, 0),
            ("2026-03-10 04:15:00+00:00", 5001, 5006, 4996, 5002, 0),
        ],
    )

    bars = load_csv_bars(CsvSpec(path=csv_path, symbol="GOLD_", point=0.01, spread_override_pips=1.0))
    report = build_tradeability_matrix(
        [CsvSpec(path=csv_path, symbol="GOLD_", point=0.01, spread_override_pips=1.0)],
        timeframes=["M15"],
        min_bars=2,
    )

    row = report["matrix"][0]
    assert bars[0]["spread_pips"] == 1.0
    assert row["spread_data_quality"] == "SPREAD_OVERRIDE"
    assert row["status"] == "SPREAD_AND_COST_CANDIDATE"
    assert row["absolute_spread_gate_pass"] is True
