# MT5AITradingService God Class 拆分 — 实施记录

**设计日期**: 2026-07-04 | **状态**: ✅ 已完成 | **最终行数**: 472 行（原 1574 行，-70%）

---

## 实施概览

原 `MT5AITradingService` 拆分为 `mt5_ai_service.py`（472行）主入口 + 5 个 `core/service/` 子模块（共 1669 行）：

| 模块 | 行数 | 职责 |
|------|------|------|
| `core/service/ai_coordinator.py` | 435 | AI分析委托 + SL/TP动态计算 |
| `core/service/communication.py` | 500 | File/Socket/WebSocket 三种通信模式 |
| `core/service/monitor.py` | 301 | 心跳 + 账户监控 + 交易统计 |
| `core/service/request_processor.py` | 293 | 请求管道处理 |
| `core/service/utils.py` | 129 | 公共工具函数 |
| **总计** | **1658** | |
| `mt5_ai_service.py` (主入口) | 472 | 生命周期 + 依赖注入 + 委托分发 |

## 1. 现状分析（已完成）

`mt5_ai_service.py` 中 `MT5AITradingService` 类共 **1574行**，承载了4类职责，违反单一职责原则：

| 职责域 | 方法数 | 行数 | 耦合度 |
|--------|--------|------|--------|
| 请求处理管道 | 4 | ~600 | 高 |
| 通信层 (File/Socket/WS) | 4 | ~260 | 高 |
| 监控与统计 | 4 | ~180 | 中 |
| 生命周期管理 | 5 | ~200 | 中 |

## 2. 目标架构

```
mt5_ai_service.py (主入口, ~50行)
    |
    ├── core/service/request_processor.py    (~350行)
    │   └── RequestProcessor
    │       ├── process_request()
    │       ├── _validate_and_prepare()
    │       └── _build_response()
    │
    ├── core/service/ai_coordinator.py       (~300行)
    │   └── AIServiceCoordinator
    │       ├── analyze()
    │       ├── _calculate_dynamic_sl_tp()
    │       └── _get_blocking_risk_reason()
    │
    ├── core/service/communication.py         (~300行)
    │   ├── FileModeRunner
    │   │   └── _run_file_mode()
    │   ├── SocketModeRunner
    │   │   ├── _start_socket_mode()
    │   │   └── _run_socket_server()
    │   └── WebSocketModeRunner
    │       └── _start_websocket_mode()
    │
    └── core/service/monitor.py              (~200行)
        └── ServiceMonitor
            ├── _heartbeat_loop()
            ├── _monitor_account_data()
            ├── _update_trade_stats()
            └── get_trade_stats()
```

## 3. 拆分步骤（按风险递增）

### Phase 1: ServiceMonitor (低风险, 0.5天)

**抽出的方法**: `_heartbeat_loop`, `_monitor_account_data`, `_update_trade_stats`, `get_trade_stats`, `_print_status`

```python
# core/service/monitor.py
class ServiceMonitor:
    def __init__(self, service_registry, local_instance, observation_journal):
        self._service_registry = service_registry
        self._local_instance = local_instance
        self._observation_journal = observation_journal
        self._stats = { ... }  # 迁移 __init__ 中的统计字典
    
    def start_heartbeat(self) -> threading.Thread:
        """启动心跳线程"""
    
    def get_trade_stats(self) -> dict:
        """获取交易统计"""
    
    def _update_trade_stats(self, trade_history: list):
        """更新交易统计"""
```

**MT5AITradingService 改动**: 委托调用 → `self.monitor.get_trade_stats()`

### Phase 2: Communication (中风险, 1天)

**抽出的方法**: `_run_file_mode`, `_start_socket_mode`, `_run_socket_server`, `_start_websocket_mode`

```python
# core/service/communication.py
class FileModeRunner:
    def __init__(self, request_processor, config):
        self.request_processor = request_processor
    
    def run(self, service_id: str):
        """File模式主循环"""

class SocketModeRunner:
    def __init__(self, request_processor, host, port):
        ...
    
    def start(self) -> threading.Thread:
        """启动Socket服务器"""
```

**MT5AITradingService 改动**: `run()` 中委托到对应 Runner

### Phase 3: RequestProcessor + AICoordinator (高风险, 1.5天)

**抽出的方法**: `process_request`, `analyze`, `_calculate_dynamic_sl_tp`, `_get_blocking_risk_reason`

```python
# core/service/ai_coordinator.py
class AIServiceCoordinator:
    def __init__(self, ai_analyzer, risk_manager, weight_optimizer, trading_recorder):
        ...
    
    def analyze(self, symbol, bid, ask, ...) -> dict:
        """核心AI分析委托"""
    
    def calculate_sl_tp(self, symbol, action, confidence, current_price) -> tuple:
        """动态SL/TP计算"""

# core/service/request_processor.py  
class RequestProcessor:
    def __init__(self, ai_coordinator, validator, indicator_analyzer):
        ...
    
    def process(self, request_data: dict) -> dict:
        """处理完整的请求管道"""
```

**MT5AITradingService 改动**:
```python
def process_request(self, request_data):
    return self.request_processor.process(request_data, self.monitor)
```

## 4. `mt5_ai_service.py` 最终形态

```python
class MT5AITradingService:
    """MT5 AI交易服务 - V3.0 企业级增强版"""
    
    def __init__(self):
        # 保留初始化顺序
        self.ai_analyzer = AIAnalyzer()
        self.validator = DataValidator()
        self.indicator_analyzer = IndicatorAnalyzer()
        
        # 新建组合对象
        self.coordinator = AIServiceCoordinator(self.ai_analyzer, ...)
        self.request_processor = RequestProcessor(self.coordinator, ...)
        self.monitor = ServiceMonitor(...)
        self.file_runner = FileModeRunner(self.request_processor, ...)
        self.socket_runner = SocketModeRunner(self.request_processor, ...)
        self.ws_runner = WebSocketModeRunner(self.request_processor, ...)
        
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        self.running = False
    
    def _cleanup(self):
        self.monitor.stop()
        self.file_runner.stop()
        ...
    
    def process_request(self, request_data):
        return self.request_processor.process(request_data)
    
    def run(self, mode="auto"):
        self.running = True
        if mode == "file":
            self.file_runner.run()
        elif mode == "socket":
            self.socket_runner.start()
        ...
```

**最终行数估算**: `mt5_ai_service.py` ~150行, 各子模块 ~300行/个

## 5. 风险控制

| 风险 | 缓解措施 |
|------|---------|
| 循环依赖 | 所有子模块通过 `__init__` 注入，不通过 import 直接引用 |
| 状态不一致 | 保留 `MT5AITradingService` 作为状态持有者，子模块无状态 |
| 测试覆盖 | Phase 1 → Phase 2 → Phase 3 逐个阶段验证现有测试 |
| 回滚 | 每个 Phase 提交到 git，保留 rollback 能力 |

## 6. 实施检查清单

- [x] Phase 1: ServiceMonitor 提取 + 测试通过（→ `core/service/monitor.py` 301行）
- [x] Phase 2: Communication 提取 + 3种模式各自可独立启动（→ `core/service/communication.py` 500行）
- [x] Phase 3: AICoordinator 提取 + 完整管道测试（→ `core/service/ai_coordinator.py` 435行）
- [x] Phase 4: RequestProcessor 提取 + 端到端集成测试（→ `core/service/request_processor.py` 293行）
- [x] Phase 5: 清理 `mt5_ai_service.py` 冗余代码（1574→472行）
