# Legacy V4 Tests

These tests belong to the older V3/V4 integrated AI trading service stack.
They are **intentionally excluded from default pytest** (`legacy_v4` in
`pytest.ini` `testpaths_ignore`).

## Test Status

| File | Status | Notes |
|------|--------|-------|
| `final_component_coordination_test.py` | Legacy | V4.0 10-phase coordination test |
| `test_scientific_trading_system.py` | Legacy | V4.0 integration test |
| `test_socket_integration.py` | Legacy | Socket connection tests |
| `test_async_optimization.py` | Legacy | Async optimizer tests |
| `test_margin_optimization.py` | Legacy | Margin management tests |
| `ai_optimization_ab_test.py` | Legacy | AI optimization AB test |
| `run_ab_test_fixed.py` | Legacy | Duplicate of ai_optimization_ab_test.py |
| `simple_ab_test.py` | Legacy | Simplified predecessor |
| `test_v21.py` | Legacy | V2.1 unit tests |
| **`test_validation.py`** | **BROKEN** | Imports deleted `ai_file_server_optimized.py` |
| `test_config.py` | Legacy | Config tests |
| `test_finance_integration.py` | Legacy | Finance integration tests |
| `test_deepseek_config.py` | Migratable | Lightweight config test → `tests/` candidate |
| `test_mql5_account_data.py` | Migratable | MQL5 data manager test → `tests/` candidate |
| `test_risk_gate.py` | Migratable | Risk gate test → `tests/` candidate |

## ⚠️ Broken Test

`test_validation.py` imports from `ai_file_server_optimized.py` which was
deleted. This test will fail immediately if run directly.

## Migratable Tests

Three tests (`test_deepseek_config.py`, `test_mql5_account_data.py`,
`test_risk_gate.py`) use currently-existing modules and could be migrated to
`tests/`. See `docs/backlog/repository_integration_candidates.md`.

## Scope

These tests validated the V3/V4 AI trading service architecture. The current
`xm-gold-ai-trader` scaffold uses a different architecture (`src/` + `scripts/`).
Do not run these tests as part of the default verification pipeline.

Last reviewed: 2026-05-30 (v0.5.8)
