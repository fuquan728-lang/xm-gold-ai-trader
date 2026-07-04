import json

import pytest

from mt5_ai_service import parse_socket_payload


def test_exact_test_payload_is_health_probe() -> None:
    payload_type, payload = parse_socket_payload("TEST\n")

    assert payload_type == "test"
    assert payload is None


def test_mql5_data_payload_with_test_text_stays_json() -> None:
    message = {
        "type": "mql5_data",
        "account": {
            "balance": 1000.0,
            "equity": 1000.0,
            "server": "DemoTestServer",
        },
        "positions": [],
        "history": [],
    }

    payload_type, payload = parse_socket_payload(json.dumps(message) + "\n")

    assert payload_type == "json"
    assert payload is not None
    assert payload["type"] == "mql5_data"
    assert payload["account"]["server"] == "DemoTestServer"


def test_invalid_json_payload_raises_decode_error() -> None:
    with pytest.raises(json.JSONDecodeError):
        parse_socket_payload("{bad-json}\n")
