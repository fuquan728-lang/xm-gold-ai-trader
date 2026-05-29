# 🧪 测试指南

> 系统测试框架和测试指南

## 测试架构

### 测试层级
```
┌─────────────────────────────────────────┐
│           端到端集成测试                │
│   (MT5 EA + Python服务 + 数据库)        │
├─────────────────────────────────────────┤
│           集成测试                      │
│   (Python服务 + 外部API)                │
├─────────────────────────────────────────┤
│           单元测试                      │
│   (单个模块/函数)                       │
└─────────────────────────────────────────┘
```

### 测试工具栈
- **单元测试**: `pytest` + `unittest`
- **集成测试**: 自定义测试框架
- **性能测试**: `locust` + 自定义脚本
- **安全测试**: 静态分析 + 动态测试
- **端到端测试**: MT5测试脚本 + Python测试客户端

## 单元测试

### Python单元测试

#### 测试结构
```
tests/
├── unit/
│   ├── test_ai_engine.py      # AI引擎测试
│   ├── test_cache.py          # 缓存测试
│   ├── test_config.py         # 配置测试
│   ├── test_communication.py  # 通信测试
│   └── test_trading.py        # 交易逻辑测试
├── integration/
│   ├── test_socket_integration.py
│   ├── test_file_integration.py
│   └── test_websocket_integration.py
└── e2e/
    ├── test_full_workflow.py
    └── test_performance.py
```

#### 示例测试：AI引擎
```python
# tests/unit/test_ai_engine.py
import pytest
from core.ai_engine import AIEngine
from unittest.mock import Mock, patch

class TestAIEngine:
    @pytest.fixture
    def ai_engine(self):
        return AIEngine(api_key="test_key", cache_size=10)
    
    def test_analyze_market_data(self, ai_engine):
        """测试市场数据分析"""
        market_data = {
            "symbol": "EURUSD",
            "bid": 1.08542,
            "ask": 1.08547,
            "history": []
        }
        
        with patch.object(ai_engine, '_call_deepseek_api') as mock_api:
            mock_api.return_value = {
                "action": "BUY",
                "confidence": 0.78,
                "reason": "测试原因"
            }
            
            result = ai_engine.analyze_market_data(market_data)
            
            assert result["action"] in ["BUY", "SELL", "HOLD"]
            assert 0 <= result["confidence"] <= 1
            assert "reason" in result
    
    def test_cache_usage(self, ai_engine):
        """测试缓存功能"""
        market_data = {
            "symbol": "EURUSD",
            "bid": 1.08542,
            "ask": 1.08547
        }
        
        # 第一次调用应调用API
        with patch.object(ai_engine, '_call_deepseek_api') as mock_api:
            mock_api.return_value = {"action": "BUY", "confidence": 0.8}
            result1 = ai_engine.analyze_market_data(market_data)
            assert mock_api.call_count == 1
        
        # 第二次调用应使用缓存
        with patch.object(ai_engine, '_call_deepseek_api') as mock_api:
            result2 = ai_engine.analyze_market_data(market_data)
            assert mock_api.call_count == 0  # 不应再次调用API
            assert result2 == result1
    
    def test_error_handling(self, ai_engine):
        """测试错误处理"""
        market_data = {"symbol": "EURUSD"}
        
        with patch.object(ai_engine, '_call_deepseek_api') as mock_api:
            mock_api.side_effect = Exception("API调用失败")
            
            result = ai_engine.analyze_market_data(market_data)
            
            assert result["action"] == "HOLD"
            assert result["confidence"] == 0.0
            assert "error" in result["reason"]
```

#### 示例测试：缓存系统
```python
# tests/unit/test_cache.py
import pytest
from core.cache import LRUCache

class TestLRUCache:
    def test_basic_operations(self):
        """测试基本操作"""
        cache = LRUCache(capacity=3)
        
        # 测试添加和获取
        cache.put("key1", "value1")
        assert cache.get("key1") == "value1"
        
        # 测试容量限制
        cache.put("key2", "value2")
        cache.put("key3", "value3")
        cache.put("key4", "value4")  # 应淘汰key1
        
        assert cache.get("key1") is None
        assert cache.get("key4") == "value4"
    
    def test_lru_eviction(self):
        """测试LRU淘汰策略"""
        cache = LRUCache(capacity=3)
        
        cache.put("key1", "value1")
        cache.put("key2", "value2")
        cache.put("key3", "value3")
        
        # 访问key1，使其成为最近使用的
        cache.get("key1")
        
        # 添加新键，应淘汰key2（最久未使用）
        cache.put("key4", "value4")
        
        assert cache.get("key1") == "value1"
        assert cache.get("key2") is None
        assert cache.get("key3") == "value3"
        assert cache.get("key4") == "value4"
    
    def test_statistics(self):
        """测试统计信息"""
        cache = LRUCache(capacity=100)
        
        for i in range(10):
            cache.put(f"key{i}", f"value{i}")
        
        for i in range(5):
            cache.get(f"key{i}")
        
        stats = cache.get_stats()
        assert stats["hits"] == 5
        assert stats["misses"] == 0
        assert stats["size"] == 10
        assert stats["hit_rate"] == 1.0
```

### MQL5单元测试

#### 测试框架
```mql5
// tests/test_framework.mqh
#define TEST_ASSERT(condition, message) \
   if(!(condition)) { \
      Print("❌ 测试失败: ", message); \
      return false; \
   }

#define TEST_EQUAL(actual, expected, message) \
   TEST_ASSERT(actual == expected, StringFormat("%s (实际: %s, 期望: %s)", \
              message, actual, expected))

bool RunTestSuite() {
   bool all_passed = true;
   
   all_passed &= TestCommunicationModule();
   all_passed &= TestTradeModule();
   all_passed &= TestUIModule();
   all_passed &= TestUtilityFunctions();
   
   return all_passed;
}

// 示例测试：通信模块
bool TestCommunicationModule() {
   Print("=== 测试通信模块 ===");
   
   // 测试Socket创建
   int socket = SocketCreate();
   TEST_ASSERT(socket != INVALID_HANDLE, "Socket创建失败");
   
   // 测试连接（使用模拟服务器）
   bool connected = SocketConnect(socket, "127.0.0.1", 9999, 1000);
   TEST_ASSERT(!connected, "应连接失败（端口9999无服务）");
   
   SocketClose(socket);
   Print("✅ 通信模块测试通过");
   return true;
}
```

#### 测试脚本
```mql5
// tests/run_tests.mq5
#property script_show_inputs

input bool RUN_ALL_TESTS = true;
input bool TEST_COMMUNICATION = true;
input bool TEST_TRADING = false;  // 注意：交易测试可能执行真实交易

void OnStart() {
   Print("🚀 开始MT5 AI交易系统测试");
   Print("=========================================");
   
   if(RUN_ALL_TESTS || TEST_COMMUNICATION) {
      if(!TestCommunicationModule()) {
         Print("❌ 通信模块测试失败");
         return;
      }
   }
   
   if(RUN_ALL_TESTS || TEST_TRADING) {
      if(!TestTradeModule()) {
         Print("❌ 交易模块测试失败");
         return;
      }
   }
   
   // 运行其他测试...
   
   Print("=========================================");
   Print("✅ 所有测试通过！");
   Print("系统已准备好进行模拟账户测试");
}
```

## 集成测试

### Python服务集成测试

#### Socket通信测试
```python
# tests/integration/test_socket_integration.py
import socket
import json
import time
import pytest
from threading import Thread

class TestSocketIntegration:
    @pytest.fixture
    def start_test_server(self):
        """启动测试Socket服务器"""
        def server_thread():
            server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server.bind(('127.0.0.1', 9999))
            server.listen(1)
            server.settimeout(5)
            
            try:
                conn, addr = server.accept()
                data = conn.recv(1024)
                
                # 解析请求
                request = json.loads(data.decode('utf-8'))
                
                # 发送测试响应
                response = {
                    "action": "BUY",
                    "confidence": 0.78,
                    "reason": "测试响应"
                }
                conn.send(json.dumps(response).encode('utf-8'))
                conn.close()
            finally:
                server.close()
        
        thread = Thread(target=server_thread)
        thread.daemon = True
        thread.start()
        time.sleep(0.5)  # 等待服务器启动
        yield
        # 清理在测试完成后自动进行
    
    def test_socket_communication(self, start_test_server):
        """测试Socket通信"""
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client.settimeout(2)
        
        try:
            client.connect(('127.0.0.1', 9999))
            
            # 发送测试请求
            request = {
                "symbol": "TEST",
                "bid": 1.0,
                "ask": 1.0
            }
            client.send(json.dumps(request).encode('utf-8'))
            
            # 接收响应
            response_data = client.recv(1024)
            response = json.loads(response_data.decode('utf-8'))
            
            assert response["action"] == "BUY"
            assert response["confidence"] == 0.78
            assert "reason" in response
            
        finally:
            client.close()
```

#### 文件通信测试
```python
# tests/integration/test_file_integration.py
import json
import tempfile
import os
import time
import pytest

class TestFileIntegration:
    def test_file_communication(self):
        """测试文件通信"""
        with tempfile.TemporaryDirectory() as temp_dir:
            request_file = os.path.join(temp_dir, "ai_request.json")
            response_file = os.path.join(temp_dir, "ai_response.json")
            
            # 1. 写入请求文件
            request = {
                "symbol": "EURUSD",
                "bid": 1.08542,
                "ask": 1.08547
            }
            
            with open(request_file, 'w', encoding='utf-8') as f:
                json.dump(request, f)
            
            # 2. 模拟服务处理（读取请求，写入响应）
            with open(request_file, 'r', encoding='utf-8') as f:
                received_request = json.load(f)
            
            assert received_request["symbol"] == "EURUSD"
            
            # 3. 写入响应文件
            response = {
                "action": "HOLD",
                "confidence": 0.5,
                "reason": "测试响应"
            }
            
            with open(response_file, 'w', encoding='utf-8') as f:
                json.dump(response, f)
            
            # 4. 验证响应文件
            with open(response_file, 'r', encoding='utf-8') as f:
                received_response = json.load(f)
            
            assert received_response["action"] == "HOLD"
            assert received_response["confidence"] == 0.5
```

### MT5-Python集成测试

#### 端到端测试脚本
```python
# tests/e2e/test_full_workflow.py
import time
import json
import pytest
from mt5_ai_sdk import MT5AIClient
from unittest.mock import Mock, patch

class TestFullWorkflow:
    """端到端工作流测试"""
    
    @pytest.fixture
    def mock_mt5(self):
        """模拟MT5环境"""
        with patch('mt5_ai_sdk.mt5') as mock_mt5:
            # 模拟MT5连接
            mock_mt5.initialize.return_value = True
            mock_mt5.symbol_info.return_value = Mock(bid=1.08542, ask=1.08547)
            mock_mt5.positions_total.return_value = 0
            mock_mt5.terminal_info.return_value = Mock(connected=True)
            yield mock_mt5
    
    def test_complete_trading_cycle(self, mock_mt5):
        """测试完整的交易周期"""
        # 1. 初始化客户端
        client = MT5AIClient(host="127.0.0.1", socket_port=8080)
        
        # 2. 获取市场数据
        symbol = "EURUSD"
        bid = mock_mt5.symbol_info(symbol).bid
        ask = mock_mt5.symbol_info(symbol).ask
        
        # 3. 发送AI分析请求
        market_data = {
            "symbol": symbol,
            "bid": bid,
            "ask": ask,
            "time": int(time.time()),
            "history": self._generate_test_history()
        }
        
        # 模拟AI响应
        with patch.object(client, '_send_socket_request') as mock_request:
            mock_request.return_value = {
                "action": "BUY",
                "confidence": 0.78,
                "reason": "测试分析",
                "recommendation": {
                    "entry": ask,
                    "stop_loss": ask - 0.002,
                    "take_profit": ask + 0.004,
                    "lot_size": 0.1
                }
            }
            
            response = client.request_trade(market_data)
            
            assert response["action"] == "BUY"
            assert response["confidence"] >= 0.65
            
            # 4. 验证交易执行（模拟）
            if response["action"] in ["BUY", "SELL"]:
                # 检查是否有持仓限制
                positions = mock_mt5.positions_total()
                if positions < 5:  # 最大持仓限制
                    # 执行交易（在测试中只记录，不实际执行）
                    trade_request = {
                        "symbol": symbol,
                        "action": response["action"],
                        "entry": response["recommendation"]["entry"],
                        "stop_loss": response["recommendation"]["stop_loss"],
                        "take_profit": response["recommendation"]["take_profit"],
                        "lot_size": response["recommendation"]["lot_size"]
                    }
                    
                    # 验证交易请求格式
                    assert trade_request["lot_size"] > 0
                    assert trade_request["stop_loss"] < trade_request["entry"]  # 对于买入
                    
                    print(f"测试交易请求: {trade_request}")
    
    def _generate_test_history(self):
        """生成测试历史数据"""
        history = []
        base_price = 1.08000
        for i in range(50):
            time_offset = (50 - i) * 3600  # 每小时一个数据点
            open_price = base_price + i * 0.0001
            close_price = open_price + 0.0005
            high_price = close_price + 0.0002
            low_price = open_price - 0.0002
            
            history.append({
                "time": int(time.time()) - time_offset,
                "open": open_price,
                "high": high_price,
                "low": low_price,
                "close": close_price,
                "volume": 1000 + i * 10
            })
        
        return history
```

## 性能测试

### 负载测试
```python
# tests/performance/test_load.py
import time
import statistics
import concurrent.futures
import pytest
from mt5_ai_sdk import MT5AIClient

class TestLoadPerformance:
    """负载性能测试"""
    
    @pytest.fixture
    def client(self):
        return MT5AIClient(host="127.0.0.1", socket_port=8080)
    
    def test_single_request_latency(self, client):
        """测试单请求延迟"""
        start_time = time.time()
        
        market_data = {
            "symbol": "EURUSD",
            "bid": 1.08542,
            "ask": 1.08547,
            "time": int(time.time())
        }
        
        response = client.request_trade(market_data)
        
        end_time = time.time()
        latency = (end_time - start_time) * 1000  # 转换为毫秒
        
        assert latency < 5000  # 5秒超时
        print(f"单请求延迟: {latency:.2f}ms")
    
    def test_concurrent_requests(self, client):
        """测试并发请求"""
        num_requests = 10
        market_data_list = []
        
        for i in range(num_requests):
            market_data_list.append({
                "symbol": f"TEST{i}",
                "bid": 1.0 + i * 0.001,
                "ask": 1.0 + i * 0.001 + 0.00005,
                "time": int(time.time())
            })
        
        latencies = []
        
        def make_request(data):
            start = time.time()
            try:
                client.request_trade(data)
            except Exception as e:
                print(f"请求失败: {e}")
                return None
            finally:
                end = time.time()
                return (end - start) * 1000
        
        # 使用线程池并发执行
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(make_request, data) for data in market_data_list]
            
            for future in concurrent.futures.as_completed(futures):
                latency = future.result()
                if latency:
                    latencies.append(latency)
        
        if latencies:
            avg_latency = statistics.mean(latencies)
            max_latency = max(latencies)
            min_latency = min(latencies)
            
            print(f"并发测试结果:")
            print(f"  请求数量: {num_requests}")
            print(f"  平均延迟: {avg_latency:.2f}ms")
            print(f"  最大延迟: {max_latency:.2f}ms")
            print(f"  最小延迟: {min_latency:.2f}ms")
            
            assert avg_latency < 10000  # 平均延迟应小于10秒
```

### 压力测试
```python
# tests/performance/test_stress.py
import time
import threading
import queue
import pytest

class TestStressPerformance:
    """压力测试"""
    
    def test_high_frequency_requests(self):
        """测试高频请求"""
        request_queue = queue.Queue()
        response_queue = queue.Queue()
        stop_event = threading.Event()
        
        num_workers = 3
        requests_per_worker = 20
        total_requests = num_workers * requests_per_worker
        
        # 创建工作线程
        workers = []
        for i in range(num_workers):
            worker = threading.Thread(
                target=self._request_worker,
                args=(i, request_queue, response_queue, stop_event, requests_per_worker)
            )
            workers.append(worker)
        
        # 启动工作线程
        for worker in workers:
            worker.start()
        
        # 等待所有请求完成
        time.sleep(requests_per_worker * 0.5)  # 估计时间
        
        # 停止工作线程
        stop_event.set()
        for worker in workers:
            worker.join()
        
        # 收集结果
        results = []
        while not response_queue.empty():
            results.append(response_queue.get())
        
        print(f"压力测试完成")
        print(f"  总请求数: {total_requests}")
        print(f"  成功请求: {len([r for r in results if r['success']])}")
        print(f"  失败请求: {len([r for r in results if not r['success']])}")
        
        success_rate = len([r for r in results if r['success']]) / total_requests
        assert success_rate > 0.8  # 成功率应大于80%
    
    def _request_worker(self, worker_id, request_queue, response_queue, stop_event, max_requests):
        """工作线程函数"""
        client = MT5AIClient(host="127.0.0.1", socket_port=8080)
        request_count = 0
        
        while not stop_event.is_set() and request_count < max_requests:
            try:
                market_data = {
                    "symbol": f"STRESS{worker_id}",
                    "bid": 1.0 + worker_id * 0.01,
                    "ask": 1.0 + worker_id * 0.01 + 0.0005,
                    "time": int(time.time())
                }
                
                start_time = time.time()
                response = client.request_trade(market_data)
                end_time = time.time()
                
                response_queue.put({
                    "worker": worker_id,
                    "success": True,
                    "latency": (end_time - start_time) * 1000,
                    "action": response.get("action", "ERROR")
                })
                
            except Exception as e:
                response_queue.put({
                    "worker": worker_id,
                    "success": False,
                    "error": str(e)
                })
            
            request_count += 1
            time.sleep(0.1)  # 控制请求频率
```

## 安全测试

### 输入验证测试
```python
# tests/security/test_input_validation.py
import pytest
from core.ai_engine import AIEngine

class TestInputValidation:
    """输入验证测试"""
    
    @pytest.fixture
    def ai_engine(self):
        return AIEngine(api_key="test_key")
    
    def test_malformed_json(self, ai_engine):
        """测试畸形JSON输入"""
        # 测试无效JSON
        with pytest.raises(ValueError):
            ai_engine.analyze_market_data("not a json")
        
        # 测试缺少必需字段
        invalid_data = {"symbol": "EURUSD"}  # 缺少bid/ask
        result = ai_engine.analyze_market_data(invalid_data)
        assert result["action"] == "HOLD"
        assert "error" in result["reason"].lower()
    
    def test_extreme_values(self, ai_engine):
        """测试极端值输入"""
        # 测试极大值
        extreme_data = {
            "symbol": "EURUSD",
            "bid": 1e100,  # 极大值
            "ask": 1e100 + 0.00001,
            "time": 2**31 - 1  # 最大32位整数
        }
        
        result = ai_engine.analyze_market_data(extreme_data)
        # 系统应处理极端值而不崩溃
        assert result["action"] in ["BUY", "SELL", "HOLD"]
    
    def test_sql_injection(self, ai_engine):
        """测试SQL注入防护"""
        malicious_data = {
            "symbol": "EURUSD' OR '1'='1",  # SQL注入尝试
            "bid": 1.08542,
            "ask": 1.08547,
            "time": 1745260800
        }
        
        result = ai_engine.analyze_market_data(malicious_data)
        # 系统应正常处理，不应崩溃或执行恶意代码
        assert result["action"] in ["BUY", "SELL", "HOLD"]
```

## 测试运行和报告

### 运行所有测试
```bash
# 运行单元测试
pytest tests/unit/ -v

# 运行集成测试
pytest tests/integration/ -v

# 运行性能测试
pytest tests/performance/ -v --tb=short

# 运行安全测试
pytest tests/security/ -v

# 运行所有测试（除性能测试）
pytest tests/ -v --ignore=tests/performance/

# 生成HTML报告
pytest tests/ -v --html=test_report.html --self-contained-html
```

### 测试覆盖率
```bash
# 安装覆盖率工具
pip install pytest-cov

# 运行测试并计算覆盖率
pytest tests/ --cov=core --cov-report=html --cov-report=term

# 查看HTML覆盖率报告
open htmlcov/index.html
```

### 持续集成
```yaml
# .github/workflows/tests.yml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    
    steps:
    - uses: actions/checkout@v3
    
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.9'
    
    - name: Install dependencies
      run: |
        pip install -r requirements.txt
        pip install pytest pytest-cov
    
    - name: Run tests
      run: |
        pytest tests/ --cov=core --cov-report=xml --cov-report=html
    
    - name: Upload coverage
      uses: codecov/codecov-action@v3
      with:
        file: ./coverage.xml
```

## 测试最佳实践

### 测试策略
1. **测试金字塔**: 多写单元测试，适量集成测试，少量端到端测试
2. **测试隔离**: 每个测试独立，不依赖其他测试状态
3. **快速反馈**: 保持测试快速运行，便于频繁执行
4. **确定性测试**: 避免随机性和时序依赖

### 测试数据管理
1. **使用fixture**: 复用测试数据准备逻辑
2. **模拟外部依赖**: 使用mock隔离测试
3. **清理测试数据**: 测试后清理临时文件和数据库
4. **数据工厂**: 使用工厂模式生成测试数据

### 测试维护
1. **定期运行**: 集成到CI/CD流水线
2. **监控测试稳定性**: 跟踪flakey测试
3. **更新测试文档**: 保持测试文档同步
4. **测试重构**: 定期重构测试代码，保持可维护性

---

> **提示**: 良好的测试覆盖率是系统稳定性的重要保障。建议在每次代码变更后运行相关测试。