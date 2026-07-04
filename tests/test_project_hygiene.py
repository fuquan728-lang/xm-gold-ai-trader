from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_current_docs_do_not_point_to_legacy_ea_entrypoints():
    current_docs = [
        "README.md",
        "ACTIVE_PROJECT.md",
        "docs/01-项目概述/QUICK_START.md",
        "docs/01-项目概述/ARCHITECTURE.md",
        "docs/02-用户手册/INSTALLATION.md",
        "docs/02-用户手册/OPERATION.md",
        "docs/03-开发文档/MQL5_INTEGRATION.md",
        "docs/MQL5_EA_VERSION_INVENTORY.md",
    ]
    legacy_entrypoints = [
        "MQL5/Experts/AI_Trader_Integrated_Socket.mq5",
        "AI_Trader_Integrated_Socket.ex5",
        "socket_test.mq5",
    ]

    offenders = {
        path: [entry for entry in legacy_entrypoints if entry in read(path)]
        for path in current_docs
    }

    assert {path: entries for path, entries in offenders.items() if entries} == {}


def test_runtime_code_avoids_known_deprecated_apis():
    runtime_files = [
        "core/ai_engine.py",
        "core/websocket_handler_enhanced.py",
        "core/async_optimizer.py",
    ]
    forbidden = [
        "datetime.utcfromtimestamp",
        "from websockets.server import WebSocketServerProtocol",
    ]

    offenders = {
        path: [pattern for pattern in forbidden if pattern in read(path)]
        for path in runtime_files
    }

    assert {path: patterns for path, patterns in offenders.items() if patterns} == {}
