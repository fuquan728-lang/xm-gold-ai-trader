import json
from pathlib import Path

from core.file_handler import FileHandler
from core.validator import DataValidator
from mt5_ai_service import MT5AITradingService, PROTOCOL_VERSION, _total_latency_ms
from core.service.ai_coordinator import AIServiceCoordinator
from core.service.request_processor import RequestProcessor


class DummyInstance:
    def increment_requests(self):
        pass


class DummyRecorder:
    def record_analysis(self, **kwargs):
        pass


class DummyCoordinator:
    def analyze(self, *args, **kwargs):
        return {"action": "HOLD", "confidence": 0.62, "reason": "test"}


def make_service():
    service = MT5AITradingService.__new__(MT5AITradingService)
    service.local_instance = DummyInstance()
    service.validator = DataValidator()
    service.web_dashboard = None
    service.trading_recorder = DummyRecorder()
    service.request_processor = RequestProcessor(
        ai_coordinator=DummyCoordinator(),
        validator=DataValidator(),
        local_instance=DummyInstance(),
        trading_recorder=DummyRecorder(),
        web_dashboard=None,
        monitor_module=None,
    )
    return service


def test_missing_request_id_is_safe_hold():
    service = make_service()

    result = service.process_request(
        {"symbol": "GOLD_", "bid": 4052.9, "ask": 4053.1, "time": 1782820000}
    )

    assert result["action"] == "HOLD"
    assert result["protocol_version"] == PROTOCOL_VERSION
    assert result["request_id"] == ""
    assert list(result.keys())[:3] == ["protocol_version", "request_id", "action"]
    assert "MISSING_REQUEST_ID" in result["blocked_by"]
    assert result["response_matched"] is False


def test_request_id_is_echoed_with_latency_audit_fields(monkeypatch):
    service = make_service()

    def fake_analyze(*args, **kwargs):
        return {
            "action": "HOLD",
            "confidence": 0.62,
            "reason": "test hold",
            "use_deepseek": True,
            "cached": False,
        }

    service.analyze = fake_analyze

    result = service.process_request(
        {
            "request_id": "GOLD__M5_20260702_103753_828",
            "request_created_at": "2026-07-02T10:37:53",
            "_request_read_at": "2026-07-02T10:37:54",
            "ea_timeout_seconds": 45,
            "symbol": "GOLD_",
            "bid": 4052.9,
            "ask": 4053.1,
            "time": 1782820000,
        }
    )

    assert result["protocol_version"] == PROTOCOL_VERSION
    assert result["request_id"] == "GOLD__M5_20260702_103753_828"
    assert list(result.keys())[:3] == ["protocol_version", "request_id", "action"]
    assert result["response_matched"] is True
    assert result["stale_response"] is False
    assert result["stale_response_guard"] is True
    assert result["request_id_required"] is True
    assert "ACTION_HOLD" in result["blocked_by"]
    assert result["ea_timeout_seconds"] == 45
    assert isinstance(result["latency_ai_ms"], int)
    assert isinstance(result["latency_total_ms"], int)


def test_response_write_is_atomic_and_utf16(tmp_path: Path):
    handler = FileHandler()
    response = {
        "protocol_version": PROTOCOL_VERSION,
        "request_id": "rid-1",
        "action": "HOLD",
        "confidence": 0.75,
    }

    assert handler.write_response(response, str(tmp_path))

    response_file = tmp_path / "ai_response.json"
    assert response_file.exists()
    assert not (tmp_path / "ai_response.json.tmp").exists()
    raw = response_file.read_text(encoding="utf-16")
    assert raw.startswith('{"protocol_version":"v0.25.7","request_id":"rid-1","action":"HOLD"')
    assert json.loads(raw)["request_id"] == "rid-1"


def test_total_latency_prefers_request_read_time_when_ea_clock_differs():
    latency = _total_latency_ms(
        "2026-07-02T11:04:38",
        "2026-07-02T16:04:38.000000",
        "2026-07-02T16:04:41.000000",
    )

    assert latency == 3000


def test_ea_stale_response_keeps_waiting_for_current_request():
    ea_path = Path(__file__).resolve().parents[1] / "MQL5" / "Experts" / "AI_Trader_V3.2_Integrated.mq5"
    source = ea_path.read_text(encoding="utf-8")

    stale_start = source.index("if(response_request_id != m_current_request_id)")
    stale_end = source.index("[REQUEST_ID_MATCHED]", stale_start)
    stale_block = source[stale_start:stale_end]

    assert "[STALE_RESPONSE_WAIT_CONTINUE]" in stale_block
    assert "m_request_state = STATE_WAITING_RESPONSE;" in stale_block
    assert "m_request_state = STATE_IDLE;" not in stale_block


def test_ea_cleans_response_from_configured_data_path_before_new_request():
    ea_path = Path(__file__).resolve().parents[1] / "MQL5" / "Experts" / "AI_Trader_V3.2_Integrated.mq5"
    source = ea_path.read_text(encoding="utf-8")

    assert 'string response_filename = "ai_response.json";' in source
    assert 'if(InpDataPath != "")' in source
    assert 'response_filename = InpDataPath + "\\\\" + response_filename;' in source
    assert "FileDelete(response_filename);" in source
