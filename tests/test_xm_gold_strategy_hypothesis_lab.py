from __future__ import annotations

import pandas as pd

from scripts.strategy_hypothesis_lab import (
    MODE,
    PROJECT,
    REASON_NO_HISTORICAL_DATA,
    REASON_SYMBOL_INFO_UNAVAILABLE,
    HypothesisDefinition,
    risk_normalized_hypothesis_ranking,
    run_strategy_hypothesis_lab,
)
from src.broker.order_executor import TradingConfig
from src.strategy.baseline_signal import BaselineSignalConfig
from src.strategy.risk_manager import REASON_LOT_BELOW_VOLUME_MIN, RiskConfig


SYMBOL_INFO = {
    "name": "GOLD_",
    "point": 0.01,
    "trade_tick_size": 0.01,
    "trade_tick_value": 1.0,
    "volume_min": 0.01,
    "volume_step": 0.01,
    "volume_max": 50.0,
    "trade_stops_level": 0,
    "spread": 55,
}


def test_hypothesis_lab_is_read_only_and_reports_required_fields():
    report = run_strategy_hypothesis_lab(
        bars=oscillating_bars(),
        symbol="GOLD_",
        timeframe="M15",
        symbol_info=SYMBOL_INFO,
        trading_config=TradingConfig(risk=RiskConfig(max_spread_points=350)),
        hypotheses=[risk_gated_crossover("risk_gated")],
        account_equity=10.0,
        data_source={"kind": "unit_test"},
    )

    assert report["project"] == PROJECT
    assert report["mode"] == MODE
    assert report["orders_sent"] == 0
    assert report["order_check_called"] is False
    assert report["order_send_called"] is False
    assert report["hypothetical_only"] is True
    assert report["production_strategy_unchanged"] is True
    assert report["ai_annotation_read_only"] is True
    row = report["hypotheses"][0]
    assert row["candidate_signal_count"] > 0
    assert row["final_theoretical_signal_count"] == 0
    assert row["estimated_min_lot_feasibility_issues"] > 0


def test_candidate_only_diagnostic_does_not_apply_risk_gate_to_final_count():
    report = run_strategy_hypothesis_lab(
        bars=oscillating_bars(),
        symbol="GOLD_",
        timeframe="M15",
        symbol_info=SYMBOL_INFO,
        trading_config=TradingConfig(risk=RiskConfig(max_spread_points=350)),
        hypotheses=[
            risk_gated_crossover("risk_gated"),
            candidate_only_crossover("candidate_only"),
        ],
        account_equity=10.0,
        data_source={"kind": "unit_test"},
    )

    risk_gated, candidate_only = report["hypotheses"]

    assert risk_gated["candidate_signal_count"] == candidate_only["candidate_signal_count"]
    assert risk_gated["final_theoretical_signal_count"] == 0
    assert candidate_only["final_theoretical_signal_count"] == candidate_only["candidate_signal_count"]
    assert REASON_LOT_BELOW_VOLUME_MIN in risk_gated["block_reason_counts"]
    assert candidate_only["estimated_min_lot_feasibility_issues"] == risk_gated["estimated_min_lot_feasibility_issues"]


def test_minimum_lot_feasibility_study_reports_distributions_and_required_budget():
    report = run_strategy_hypothesis_lab(
        bars=oscillating_bars(),
        symbol="GOLD_",
        timeframe="M15",
        symbol_info=SYMBOL_INFO,
        trading_config=TradingConfig(risk=RiskConfig(max_spread_points=350)),
        hypotheses=[risk_gated_crossover("risk_gated")],
        account_equity=10.0,
        data_source={"kind": "unit_test"},
    )

    row = report["hypotheses"][0]
    study = row["minimum_lot_feasibility"]

    assert report["minimum_lot_feasibility_study"] == study
    assert study["hypothetical_only"] is True
    assert study["not_production_settings"] is True
    assert study["candidate_count"] == row["candidate_signal_count"]
    assert study["volume_min"] == 0.01
    assert study["volume_step"] == 0.01
    assert study["lot_below_volume_min_count"] == row["candidate_signal_count"]
    assert study["computed_lot_distribution"]["count"] == row["candidate_signal_count"]
    assert study["computed_lot_distribution"]["max"] < study["volume_min"]
    assert study["normalized_lot_distribution"]["max"] == 0.0
    assert study["risk_per_lot_distribution"]["min"] > 0
    assert study["stop_distance_points_distribution"]["min"] > 0
    assert study["atr_price_distribution"]["min"] > 0
    assert study["risk_shortfall_to_min_lot_distribution"]["min"] > 0
    assert study["account_balance_required_at_current_risk_pct_distribution"]["min"] > 10.0
    assert study["risk_pct_required_at_account_equity_distribution"]["min"] > 0.25

    scenarios = {scenario["name"]: scenario for scenario in study["hypothetical_risk_budget_scenarios"]}
    assert scenarios["current_config"]["feasible_candidate_count"] == 0
    assert scenarios["all_candidates_requirement"]["feasible_candidate_count"] == row["candidate_signal_count"]


def test_minimum_lot_feasibility_scenarios_can_be_feasible_without_order_paths():
    report = run_strategy_hypothesis_lab(
        bars=oscillating_bars(),
        symbol="GOLD_",
        timeframe="M15",
        symbol_info=SYMBOL_INFO,
        trading_config=TradingConfig(risk=RiskConfig(max_spread_points=350)),
        hypotheses=[risk_gated_crossover("risk_gated")],
        account_equity=100_000.0,
        data_source={"kind": "unit_test"},
    )

    row = report["hypotheses"][0]
    study = row["minimum_lot_feasibility"]
    scenarios = {scenario["name"]: scenario for scenario in study["hypothetical_risk_budget_scenarios"]}

    assert row["candidate_signal_count"] > 0
    assert row["final_theoretical_signal_count"] == row["candidate_signal_count"]
    assert study["lot_below_volume_min_count"] == 0
    assert study["normalized_lot_distribution"]["max"] >= study["volume_min"]
    assert scenarios["current_config"]["hypothetical_only"] is True
    assert scenarios["current_config"]["feasible_candidate_count"] == row["candidate_signal_count"]
    assert report["orders_sent"] == 0
    assert report["order_check_called"] is False
    assert report["order_send_called"] is False


def test_risk_budget_frontier_reports_account_and_fixed_budget_scenarios():
    report = run_strategy_hypothesis_lab(
        bars=oscillating_bars(),
        symbol="GOLD_",
        timeframe="M15",
        symbol_info=SYMBOL_INFO,
        trading_config=TradingConfig(risk=RiskConfig(max_spread_points=350)),
        hypotheses=[risk_gated_crossover("risk_gated")],
        account_equity=10.0,
        data_source={"kind": "unit_test"},
    )

    frontier = report["minimum_lot_feasibility_study"]["risk_budget_frontier"]
    matrix = frontier["account_balance_risk_pct_matrix"]
    fixed = frontier["fixed_risk_budget_scenarios"]

    assert frontier["hypothetical_only"] is True
    assert frontier["not_production_settings"] is True
    assert frontier["account_balances_tested"] == [500.0, 1000.0, 2500.0, 5000.0, 6000.0, 10000.0]
    assert frontier["risk_percentages_tested"] == [0.25, 0.5, 1.0]
    assert frontier["fixed_risk_budgets_tested"] == [2.5, 5.0, 10.0, 15.0, 25.0]
    assert len(matrix) == 18
    assert len(fixed) == 5

    low_budget = scenario_by_matrix_key(matrix, account_balance=500.0, risk_pct=0.25)
    higher_budget = scenario_by_matrix_key(matrix, account_balance=500.0, risk_pct=1.0)

    assert low_budget["risk_amount"] == 1.25
    assert low_budget["feasible_candidate_count"] == 0
    assert low_budget["infeasible_candidate_count"] == low_budget["candidate_count"]
    assert low_budget["median_normalized_lot"] == 0.0
    assert low_budget["median_risk_shortfall"] > 0
    assert low_budget["minimum_required_balance_estimate"] > 0
    assert higher_budget["risk_amount"] == 5.0
    assert higher_budget["feasible_candidate_count"] == higher_budget["candidate_count"]
    assert higher_budget["median_normalized_lot"] >= frontier["broker_volume_min"]


def test_fixed_risk_budget_frontier_keeps_scenarios_hypothetical():
    report = run_strategy_hypothesis_lab(
        bars=oscillating_bars(),
        symbol="GOLD_",
        timeframe="M15",
        symbol_info=SYMBOL_INFO,
        trading_config=TradingConfig(risk=RiskConfig(max_spread_points=350)),
        hypotheses=[risk_gated_crossover("risk_gated")],
        account_equity=10.0,
        data_source={"kind": "unit_test"},
    )

    fixed = report["minimum_lot_feasibility_study"]["risk_budget_frontier"]["fixed_risk_budget_scenarios"]
    by_budget = {row["fixed_risk_budget"]: row for row in fixed}

    assert by_budget[2.5]["hypothetical_only"] is True
    assert by_budget[2.5]["not_production_settings"] is True
    assert by_budget[2.5]["scenario_type"] == "fixed_risk_budget"
    assert by_budget[2.5]["risk_pct_for_required_balance_estimate"] == 0.25
    assert by_budget[25.0]["feasible_candidate_count"] >= by_budget[2.5]["feasible_candidate_count"]
    assert report["orders_sent"] == 0
    assert report["order_check_called"] is False
    assert report["order_send_called"] is False


def test_risk_normalized_ranking_output_exists_and_is_read_only():
    report = run_strategy_hypothesis_lab(
        bars=oscillating_bars(),
        symbol="GOLD_",
        timeframe="M15",
        symbol_info=SYMBOL_INFO,
        trading_config=TradingConfig(risk=RiskConfig(max_spread_points=350)),
        hypotheses=[
            risk_gated_crossover("risk_gated"),
            candidate_only_crossover("candidate_only"),
        ],
        account_equity=10.0,
        data_source={"kind": "unit_test"},
    )

    ranking = report["risk_normalized_hypothesis_ranking"]
    first_budget = ranking["rankings_by_fixed_risk_budget"][0]
    first_row = first_budget["rankings"][0]

    assert ranking["hypothetical_only"] is True
    assert ranking["not_production_selection"] is True
    assert ranking["orders_sent"] == 0
    assert ranking["order_check_called"] is False
    assert ranking["order_send_called"] is False
    assert ranking["risk_budgets"] == [2.5, 5.0, 10.0, 15.0, 25.0]
    assert first_row["rank"] == 1
    assert first_row["total_candidates"] > 0
    assert "normalized_ranking_score" in first_row
    assert "score_components" in first_row
    assert first_row["orders_sent"] == 0
    assert first_row["order_check_called"] is False
    assert first_row["order_send_called"] is False


def test_risk_normalized_rankings_are_deterministic():
    kwargs = {
        "bars": oscillating_bars(),
        "symbol": "GOLD_",
        "timeframe": "M15",
        "symbol_info": SYMBOL_INFO,
        "trading_config": TradingConfig(risk=RiskConfig(max_spread_points=350)),
        "hypotheses": [
            risk_gated_crossover("risk_gated"),
            candidate_only_crossover("candidate_only"),
        ],
        "account_equity": 10.0,
        "data_source": {"kind": "unit_test"},
    }

    first = run_strategy_hypothesis_lab(**kwargs)["risk_normalized_hypothesis_ranking"]
    second = run_strategy_hypothesis_lab(**kwargs)["risk_normalized_hypothesis_ranking"]

    assert first == second


def test_risk_normalized_ranking_does_not_reward_raw_signal_spam_when_feasibility_is_poor():
    ranking = risk_normalized_hypothesis_ranking(
        [
            fake_ranking_row(
                name="balanced_feasible",
                total_candidates=20,
                feasible_candidates=18,
                feasible_buy=9,
                feasible_sell=9,
                median_risk_shortfall=0.0,
                median_stop_distance_points=1_000.0,
            ),
            fake_ranking_row(
                name="spammy_poor_feasibility",
                total_candidates=1_000,
                feasible_candidates=50,
                feasible_buy=45,
                feasible_sell=5,
                median_risk_shortfall=20.0,
                median_stop_distance_points=7_500.0,
            ),
        ]
    )

    for group in ranking["rankings_by_fixed_risk_budget"]:
        assert group["rankings"][0]["hypothesis_name"] == "balanced_feasible"
        spammy = next(row for row in group["rankings"] if row["hypothesis_name"] == "spammy_poor_feasibility")
        balanced = next(row for row in group["rankings"] if row["hypothesis_name"] == "balanced_feasible")
        assert spammy["total_candidates"] > balanced["total_candidates"]
        assert spammy["normalized_ranking_score"] < balanced["normalized_ranking_score"]


def test_hypothesis_selection_evidence_pack_exists_and_disables_production_recommendation():
    report = run_strategy_hypothesis_lab(
        bars=oscillating_bars(),
        symbol="GOLD_",
        timeframe="M15",
        symbol_info=SYMBOL_INFO,
        trading_config=TradingConfig(risk=RiskConfig(max_spread_points=350)),
        hypotheses=[
            risk_gated_crossover("risk_gated"),
            candidate_only_crossover("candidate_only"),
        ],
        account_equity=10.0,
        data_source={"kind": "unit_test"},
    )

    pack = report["hypothesis_selection_evidence_pack"]
    decision = pack["production_decision"]

    assert pack["hypothetical_only"] is True
    assert pack["read_only_offline_research"] is True
    assert pack["not_production_selection"] is True
    assert pack["selected_offline_hypothesis"] == "risk_gated"
    assert pack["baseline_candidate_feasibility"]["candidate_signal_count"] > 0
    assert pack["minimum_lot_feasibility_bottleneck"]["lot_below_volume_min_count"] > 0
    assert pack["risk_budget_frontier_summary"]
    assert pack["normalized_ranking_summary"]["ranking_is_production_selector"] is False
    assert decision["production_ready"] is False
    assert decision["production_strategy_change_recommended"] is False
    assert decision["live_order_enablement_recommended"] is False
    assert decision["ai_trading_behavior_introduced"] is False
    assert "NO_PRODUCTION_STRATEGY_CHANGE_RECOMMENDED" in decision["reason_codes"]
    assert pack["next_evidence_required"]
    assert pack["orders_sent"] == 0
    assert pack["order_check_called"] is False
    assert pack["order_send_called"] is False


def test_hypothesis_selection_evidence_pack_selected_hypothesis_is_deterministic():
    kwargs = {
        "bars": oscillating_bars(),
        "symbol": "GOLD_",
        "timeframe": "M15",
        "symbol_info": SYMBOL_INFO,
        "trading_config": TradingConfig(risk=RiskConfig(max_spread_points=350)),
        "hypotheses": [
            risk_gated_crossover("risk_gated"),
            candidate_only_crossover("candidate_only"),
        ],
        "account_equity": 10.0,
        "data_source": {"kind": "unit_test"},
    }

    first = run_strategy_hypothesis_lab(**kwargs)["hypothesis_selection_evidence_pack"]
    second = run_strategy_hypothesis_lab(**kwargs)["hypothesis_selection_evidence_pack"]

    assert first == second
    assert first["selected_offline_hypothesis"] == second["selected_offline_hypothesis"]


def test_evidence_pack_explains_close_sma_contender_when_available():
    report = run_strategy_hypothesis_lab(
        bars=oscillating_bars(),
        symbol="GOLD_",
        timeframe="M15",
        symbol_info=SYMBOL_INFO,
        trading_config=TradingConfig(risk=RiskConfig(max_spread_points=350)),
        hypotheses=[
            risk_gated_crossover("risk_gated"),
            HypothesisDefinition(
                name="sma_10_30_risk_gated",
                family="sma_parameter_variant",
                description="Unit-test contender.",
                signal_mode="sma_crossover",
                signal_config=BaselineSignalConfig(fast_sma=2, slow_sma=4, atr_period=2),
                risk_gated=True,
            ),
        ],
        account_equity=10.0,
        data_source={"kind": "unit_test"},
    )

    contender = report["hypothesis_selection_evidence_pack"]["why_sma_10_30_not_selected_yet"]

    assert contender["contender"] == "sma_10_30_risk_gated"
    assert contender["contender_present"] is True
    assert contender["budget_25_contender"] is not None
    assert any("candidate" in reason for reason in contender["reasons"])


def test_forward_evidence_plan_defines_v06_gates_without_production_enablement():
    report = run_strategy_hypothesis_lab(
        bars=oscillating_bars(),
        symbol="GOLD_",
        timeframe="M15",
        symbol_info=SYMBOL_INFO,
        trading_config=TradingConfig(risk=RiskConfig(max_spread_points=350)),
        hypotheses=[risk_gated_crossover("risk_gated")],
        account_equity=10.0,
        data_source={"kind": "unit_test"},
    )

    plan = report["forward_evidence_plan"]

    assert plan["hypothetical_only"] is True
    assert plan["read_only_research_plan"] is True
    assert plan["production_strategy_change_recommended"] is False
    assert plan["live_order_enablement_recommended"] is False
    assert plan["ai_trading_behavior_introduced"] is False
    assert plan["forward_enriched_live_dry_run_requirement"]["minimum_enriched_closed_bars"] == 500
    assert plan["forward_enriched_live_dry_run_requirement"]["minimum_final_signal_count"] == 5
    assert plan["forward_enriched_live_dry_run_requirement"]["minimum_diagnostics_coverage_pct"] == 0.95
    assert plan["out_of_sample_historical_split"]["no_parameter_selection_on_test_split"] is True
    assert "volume_min" in plan["risk_and_execution_feasibility"]["required_constraints"]
    assert "spread_points" in plan["market_condition_sensitivity"]["required_distributions"]
    assert plan["trade_quality_diagnostics"]["raw_candidate_spam_penalty_required"] is True
    assert plan["decision_gates"]["explicit_no_live_order_recommendation"] is True
    assert plan["decision_gates"]["production_ready"] is False
    assert plan["orders_sent"] == 0
    assert plan["order_check_called"] is False
    assert plan["order_send_called"] is False


def test_forward_sample_collection_plan_exists_and_defines_tracking_fields():
    report = run_strategy_hypothesis_lab(
        bars=oscillating_bars(),
        symbol="GOLD_",
        timeframe="M15",
        symbol_info=SYMBOL_INFO,
        trading_config=TradingConfig(risk=RiskConfig(max_spread_points=350)),
        hypotheses=[risk_gated_crossover("risk_gated")],
        account_equity=10.0,
        data_source={"kind": "unit_test"},
    )

    plan = report["forward_sample_collection_plan"]

    assert plan["hypothetical_only"] is True
    assert plan["read_only_research_plan"] is True
    assert plan["production_strategy_change_recommended"] is False
    assert plan["live_order_enablement_recommended"] is False
    assert plan["ai_trading_behavior_introduced"] is False

    progress = plan["progress"]
    bars = progress["enriched_closed_bars"]
    signals = progress["final_dry_run_signals"]
    coverage = progress["diagnostics_coverage"]

    assert bars["current"] == 0
    assert bars["required"] == 500
    assert bars["remaining"] == 500
    assert bars["met"] is False

    assert signals["current"] == 0
    assert signals["required"] == 5
    assert signals["remaining"] == 5
    assert signals["met"] is False

    assert coverage["current_pct"] == 0.0
    assert coverage["required_pct"] == 95.0
    assert coverage["met"] is False

    summary = progress["summary"]
    assert summary["all_gates_met"] is False
    assert summary["ready_for_v06_research"] is False
    assert summary["offline_research_only"] is True

    assert plan["forward_evidence_gates_met"] is False

    sampling = plan["sampling_command"]
    assert "run_dry_observation_campaign.py" in sampling["command"]
    assert "--bar-close-only" in sampling["command"]
    assert "--json" in sampling["command"]
    assert sampling["parameters"]["bar_close_only"] is True

    cadence = plan["sampling_cadence"]
    assert any("allow_order_send" in rule for rule in cadence["rules"])
    assert len(cadence["recommended_review_points"]) >= 2

    gates = plan["what_gates_met_unlocks"]
    assert gates["allows_v06_parameter_candidate_research"] is False
    assert gates["does_not_allow_production_strategy_changes"] is True
    assert gates["does_not_allow_live_order_enablement"] is True

    assert plan["orders_sent"] == 0
    assert plan["order_check_called"] is False
    assert plan["order_send_called"] is False
    assert len(plan["next_steps_after_gates_met"]) >= 3


def test_trend_continuation_hypothesis_generates_candidates_without_changing_baseline():
    report = run_strategy_hypothesis_lab(
        bars=trending_bars(),
        symbol="GOLD_",
        timeframe="M15",
        symbol_info=SYMBOL_INFO,
        trading_config=TradingConfig(risk=RiskConfig(max_spread_points=350)),
        hypotheses=[
            candidate_only_crossover("crossover"),
            HypothesisDefinition(
                name="trend_continuation",
                family="trend_continuation",
                description="Unit-test trend continuation diagnostic.",
                signal_mode="trend_continuation",
                signal_config=BaselineSignalConfig(fast_sma=2, slow_sma=5, atr_period=2),
                risk_gated=False,
            ),
        ],
        account_equity=100_000.0,
        data_source={"kind": "unit_test"},
    )

    crossover, trend = report["hypotheses"]

    assert crossover["candidate_signal_count"] == 0
    assert trend["candidate_signal_count"] > 0
    assert trend["final_theoretical_signal_count"] == trend["candidate_signal_count"]
    assert report["production_strategy_unchanged"] is True


def test_empty_data_returns_warn_without_order_boundaries():
    report = run_strategy_hypothesis_lab(
        bars=pd.DataFrame(columns=["time", "open", "high", "low", "close", "spread"]),
        symbol="GOLD_",
        timeframe="M15",
        symbol_info=SYMBOL_INFO,
        trading_config=TradingConfig(),
        hypotheses=[risk_gated_crossover("risk_gated")],
    )

    assert report["final_decision"] == "WARN"
    assert report["reason_codes"] == [REASON_NO_HISTORICAL_DATA]
    assert report["orders_sent"] == 0
    assert report["order_check_called"] is False
    assert report["order_send_called"] is False


def test_missing_symbol_info_returns_warn_without_order_boundaries():
    report = run_strategy_hypothesis_lab(
        bars=oscillating_bars(),
        symbol="GOLD_",
        timeframe="M15",
        symbol_info=None,
        trading_config=TradingConfig(),
        hypotheses=[risk_gated_crossover("risk_gated")],
    )

    assert report["final_decision"] == "WARN"
    assert report["reason_codes"] == [REASON_SYMBOL_INFO_UNAVAILABLE]
    assert report["orders_sent"] == 0
    assert report["order_check_called"] is False
    assert report["order_send_called"] is False


def risk_gated_crossover(name: str) -> HypothesisDefinition:
    return HypothesisDefinition(
        name=name,
        family="unit_test",
        description="Unit-test risk-gated SMA crossover.",
        signal_mode="sma_crossover",
        signal_config=BaselineSignalConfig(fast_sma=2, slow_sma=3, atr_period=2),
        risk_gated=True,
    )


def candidate_only_crossover(name: str) -> HypothesisDefinition:
    return HypothesisDefinition(
        name=name,
        family="unit_test",
        description="Unit-test candidate-only SMA crossover.",
        signal_mode="sma_crossover",
        signal_config=BaselineSignalConfig(fast_sma=2, slow_sma=3, atr_period=2),
        risk_gated=False,
    )


def scenario_by_matrix_key(
    rows: list[dict],
    *,
    account_balance: float,
    risk_pct: float,
) -> dict:
    for row in rows:
        if row["account_balance"] == account_balance and row["risk_pct"] == risk_pct:
            return row
    raise AssertionError(f"scenario not found for account_balance={account_balance} risk_pct={risk_pct}")


def fake_ranking_row(
    *,
    name: str,
    total_candidates: int,
    feasible_candidates: int,
    feasible_buy: int,
    feasible_sell: int,
    median_risk_shortfall: float,
    median_stop_distance_points: float,
) -> dict:
    fixed_scenarios = [
        {
            "scenario_type": "fixed_risk_budget",
            "hypothetical_only": True,
            "not_production_settings": True,
            "fixed_risk_budget": budget,
            "risk_amount": budget,
            "candidate_count": total_candidates,
            "feasible_candidate_count": feasible_candidates,
            "infeasible_candidate_count": total_candidates - feasible_candidates,
            "feasible_percentage": feasible_candidates / total_candidates,
            "candidate_buy_count": total_candidates // 2,
            "candidate_sell_count": total_candidates - (total_candidates // 2),
            "feasible_buy_count": feasible_buy,
            "feasible_sell_count": feasible_sell,
            "buy_sell_distribution": {
                "candidate": {"BUY": total_candidates // 2, "SELL": total_candidates - (total_candidates // 2)},
                "feasible": {"BUY": feasible_buy, "SELL": feasible_sell},
            },
            "median_computed_lot": 0.02,
            "median_normalized_lot": 0.01 if feasible_candidates else 0.0,
            "median_stop_distance_points": median_stop_distance_points,
            "median_atr_points": median_stop_distance_points / 1.5,
            "median_risk_shortfall": median_risk_shortfall,
            "scenario_top_blockers": [{"reason": "LOT_BELOW_VOLUME_MIN", "count": total_candidates - feasible_candidates}],
        }
        for budget in [2.5, 5.0, 10.0, 15.0, 25.0]
    ]
    return {
        "name": name,
        "family": "unit_test",
        "risk_gated": True,
        "signal_mode": "unit_test",
        "candidate_signal_count": total_candidates,
        "candidate_buy_count": total_candidates // 2,
        "candidate_sell_count": total_candidates - (total_candidates // 2),
        "top_block_reasons": [{"reason": "LOT_BELOW_VOLUME_MIN", "count": total_candidates - feasible_candidates}],
        "minimum_lot_feasibility": {
            "stop_distance_points_distribution": {"median": median_stop_distance_points},
            "atr_points_distribution": {"median": median_stop_distance_points / 1.5},
            "risk_budget_frontier": {"fixed_risk_budget_scenarios": fixed_scenarios},
        },
    }


def oscillating_bars() -> pd.DataFrame:
    closes = [10, 9, 8, 9, 10, 11, 10, 9, 8, 9, 10, 11, 10, 9, 8, 9, 10, 11]
    return bars_from_closes(closes)


def trending_bars() -> pd.DataFrame:
    return bars_from_closes(list(range(10, 40)))


def bars_from_closes(closes: list[float]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "time": [f"2026-05-29T{i:02d}:00:00+00:00" for i in range(len(closes))],
            "open": closes,
            "high": [close + 0.3 for close in closes],
            "low": [close - 0.3 for close in closes],
            "close": closes,
            "spread": [55 for _ in closes],
        }
    )
