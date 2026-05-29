# 📡 API参考手册

> 系统API接口详细说明

## API概述

MT5 AI交易系统提供多种API接口，支持不同通信协议：

### 支持的协议
1. **Socket API** (TCP): 高性能二进制协议
2. **WebSocket API** (V3.0): 双向实时通信
3. **HTTP API**: Web仪表盘和管理接口
4. **文件API**: 基于文件系统的兼容接口

## Socket API

### 连接信息
- **协议**: TCP
- **地址**: `127.0.0.1:8080` (默认)
- **编码**: UTF-8 JSON
- **超时**: 连接3000ms，接收5000ms

### 请求格式
```json
{
  "request_id": "unique_request_id",
  "symbol": "EURUSD",
  "bid": 1.08542,
  "ask": 1.08547,
  "time": 1745260800,
  "history": [
    {
      "time": 1745251200,
      "open": 1.08321,
      "high": 1.08652,
      "low": 1.08294,
      "close": 1.08542,
      "volume": 15234
    }
    // 更多K线数据...
  ],
  "parameters": {
    "period": "H1",
    "indicators": ["RSI", "MACD", "EMA"],
    "cache_key": "optional_cache_key"
  }
}
```

### 响应格式
```json
{
  "request_id": "unique_request_id",
  "action": "BUY|SELL|HOLD",
  "confidence": 0.78,
  "reason": "详细分析原因...",
  "symbol": "EURUSD",
  "analysis_time": "2024-04-21T10:30:45Z",
  "indicators": {
    "rsi": 58.4,
    "macd": 0.0012,
    "ema_50": 1.08456
  },
  "recommendation": {
    "entry": 1.08547,
    "stop_loss": 1.08347,
    "take_profit": 1.08947,
    "lot_size": 0.1
  }
}
```

### 错误响应
```json
{
  "request_id": "unique_request_id",
  "error": true,
  "error_code": "API_ERROR",
  "error_message": "详细错误信息",
  "timestamp": "2024-04-21T10:30:45Z"
}
```

### 错误代码表
| 错误代码 | HTTP状态 | 说明 |
|----------|-----------|------|
| `INVALID_REQUEST` | 400 | 请求格式错误 |
| `API_KEY_INVALID` | 401 | API密钥无效 |
| `RATE_LIMITED` | 429 | 请求频率超限 |
| `AI_SERVICE_ERROR` | 503 | AI服务不可用 |
| `INTERNAL_ERROR` | 500 | 服务器内部错误 |

## WebSocket API (V3.0)

### 连接信息
- **协议**: WebSocket
- **地址**: `ws://127.0.0.1:8081` (默认)
- **编码**: UTF-8 JSON
- **心跳**: 每30秒自动发送ping

### 连接建立
```javascript
// 客户端连接示例
const ws = new WebSocket('ws://127.0.0.1:8081');

ws.onopen = function() {
  console.log('WebSocket连接已建立');
  
  // 发送认证消息（如果需要）
  ws.send(JSON.stringify({
    "type": "auth",
    "api_key": "your_api_key"
  }));
};
```

### 消息类型

#### 1. 交易请求消息
```json
{
  "type": "trade_request",
  "request_id": "req_001",
  "symbol": "GOLD",
  "bid": 4811.26,
  "ask": 4811.75,
  "timestamp": 1745260800
}
```

#### 2. 交易响应消息
```json
{
  "type": "trade_response",
  "request_id": "req_001",
  "action": "BUY",
  "confidence": 0.78,
  "timestamp": 1745260801
}
```

#### 3. 市场数据推送
```json
{
  "type": "market_update",
  "symbol": "EURUSD",
  "bid": 1.08542,
  "ask": 1.08547,
  "spread": 0.5,
  "timestamp": 1745260800
}
```

#### 4. 系统状态推送
```json
{
  "type": "system_status",
  "status": "running",
  "mode": "websocket",
  "requests_today": 1245,
  "success_rate": 0.98,
  "timestamp": 1745260800
}
```

### 事件订阅
```json
// 订阅市场数据
{
  "type": "subscribe",
  "channels": ["market_data", "system_status"]
}

// 取消订阅
{
  "type": "unsubscribe",
  "channels": ["market_data"]
}
```

## HTTP API

### Web仪表盘 API
- **地址**: `http://127.0.0.1:8000`
- **认证**: 无（本地访问）或基本认证

#### 端点列表

##### GET `/`
- **描述**: Web仪表盘主页面
- **响应**: HTML页面

##### GET `/api/status`
- **描述**: 获取系统状态
- **响应**:
```json
{
  "status": "running",
  "version": "3.0",
  "uptime": 86400,
  "requests_total": 1245,
  "requests_today": 89,
  "success_rate": 0.98
}
```

##### GET `/api/trades`
- **描述**: 获取交易记录
- **参数**:
  - `limit`: 返回数量 (默认: 50)
  - `offset`: 偏移量 (默认: 0)
  - `symbol`: 交易品种筛选
- **响应**:
```json
{
  "trades": [
    {
      "id": 1,
      "symbol": "EURUSD",
      "action": "BUY",
      "confidence": 0.78,
      "result": "profit",
      "profit": 15.2,
      "timestamp": "2024-04-21T10:30:45Z"
    }
  ],
  "total": 1245
}
```

##### GET `/api/performance`
- **描述**: 获取性能指标
- **参数**:
  - `period`: 时间周期 (day/week/month)
- **响应**:
```json
{
  "win_rate": 0.65,
  "profit_factor": 1.82,
  "total_trades": 1245,
  "total_profit": 1520.5,
  "max_drawdown": -320.4,
  "sharpe_ratio": 1.24
}
```

##### POST `/api/config`
- **描述**: 更新配置（部分支持热更新）
- **请求**:
```json
{
  "confidence_threshold": 0.7,
  "cache_size": 150,
  "log_level": "DEBUG"
}
```
- **响应**:
```json
{
  "success": true,
  "updated": ["confidence_threshold", "cache_size"],
  "requires_restart": ["log_level"]
}
```

### 管理 API

#### 健康检查端点
```
GET /health
```
- **响应**: `{"status": "healthy"}` 或 `{"status": "unhealthy", "details": "..."}`

#### 指标端点
```
GET /metrics
```
- **响应**: Prometheus格式的指标数据

## 文件API

### 文件位置
- **请求文件**: `MQL5/Files/ai_request.json`
- **响应文件**: `MQL5/Files/ai_response.json`

### 请求文件格式
```json
{
  "symbol": "GOLD",
  "bid": 4811.26,
  "ask": 4811.75,
  "time": 1745260800,
  "history": [...]
}
```

### 响应文件格式
```json
{
  "action": "HOLD",
  "confidence": 0.5,
  "reason": "指标信号矛盾...",
  "symbol": "GOLD",
  "analysis_time": "2024-04-21T10:30:45Z"
}
```

## Python SDK使用示例

### 安装SDK
```bash
pip install mt5-ai-sdk
```

### 基本使用
```python
from mt5_ai_sdk import MT5AIClient

# 创建客户端
client = MT5AIClient(
    host="127.0.0.1",
    socket_port=8080,
    websocket_port=8081,
    api_key="your_api_key"
)

# 发送交易请求
response = client.request_trade(
    symbol="EURUSD",
    bid=1.08542,
    ask=1.08547,
    history_data=history_data
)

print(f"Action: {response.action}")
print(f"Confidence: {response.confidence}")
print(f"Reason: {response.reason}")
```

### WebSocket客户端
```python
import asyncio
from mt5_ai_sdk import MT5AIWebSocketClient

async def main():
    client = MT5AIWebSocketClient("ws://127.0.0.1:8081")
    
    async with client.connect() as ws:
        # 订阅市场数据
        await ws.subscribe(["market_data", "system_status"])
        
        # 接收消息
        async for message in ws.listen():
            if message.type == "trade_response":
                print(f"Trade response: {message.action}")
            elif message.type == "market_update":
                print(f"Market update: {message.symbol} {message.bid}")

asyncio.run(main())
```

## MQL5集成示例

### Socket客户端
```mql5
// 创建Socket
int socket = SocketCreate();
if(socket == INVALID_HANDLE) {
    Print("Failed to create socket");
    return;
}

// 连接服务器
if(SocketConnect(socket, InpSocketHost, InpSocketPort, InpConnectTimeout)) {
    // 发送请求数据
    string request_json = "{\"symbol\":\"EURUSD\",\"bid\":1.08542}";
    uchar data[];
    StringToCharArray(request_json, data);
    SocketSend(socket, data);
    
    // 接收响应
    uchar response[1024];
    int received = SocketRead(socket, response, ArraySize(response), InpReceiveTimeout);
    
    if(received > 0) {
        string response_json = CharArrayToString(response, 0, received);
        // 解析响应...
    }
    
    SocketClose(socket);
}
```

### WebSocket客户端 (V3.0)
```mql5
// 使用WebSocket库
#include <WebSocket.mqh>

CWebSocket ws;

void OnInit() {
    if(ws.Connect("ws://127.0.0.1:8081")) {
        Print("WebSocket connected");
    }
}

void OnTick() {
    if(ws.IsConnected()) {
        // 发送请求
        string request = "{\"type\":\"trade_request\",\"symbol\":\"" + Symbol() + "\"}";
        ws.Send(request);
        
        // 检查响应
        string response = ws.Receive();
        if(response != "") {
            // 处理响应...
        }
    }
}
```

## 错误处理

### 重试机制
```python
import time
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=10)
)
def send_request_with_retry(client, request):
    try:
        return client.request_trade(**request)
    except ConnectionError as e:
        print(f"Connection error: {e}, retrying...")
        raise
```

### 断路器模式
```python
from pybreaker import CircuitBreaker

# 创建断路器
breaker = CircuitBreaker(fail_max=5, reset_timeout=60)

@breaker
def call_ai_service(request):
    return ai_service.process(request)

try:
    response = call_ai_service(request)
except CircuitBreakerError:
    # 断路器已打开，使用备用策略
    response = fallback_strategy(request)
```

## 性能优化

### 批量请求
```python
# 批量发送请求
batch_requests = [
    {"symbol": "EURUSD", "bid": 1.08542},
    {"symbol": "GBPUSD", "bid": 1.26532},
    {"symbol": "USDJPY", "bid": 154.23}
]

batch_responses = client.batch_request(batch_requests)
```

### 连接池
```python
from connection_pool import ConnectionPool

# 创建连接池
pool = ConnectionPool(
    factory=lambda: MT5AIClient(),
    max_size=10,
    idle_timeout=300
)

# 使用连接
with pool.get_connection() as client:
    response = client.request_trade(**request)
```

## 安全性

### API密钥认证
```python
# 在请求头中添加认证
headers = {
    "X-API-Key": "your_api_key",
    "Content-Type": "application/json"
}

response = requests.post(
    "http://127.0.0.1:8000/api/trade",
    json=request_data,
    headers=headers
)
```

### 请求签名
```python
import hmac
import hashlib
import time

def sign_request(api_key, api_secret, request_data):
    timestamp = str(int(time.time()))
    message = timestamp + json.dumps(request_data, sort_keys=True)
    signature = hmac.new(
        api_secret.encode(),
        message.encode(),
        hashlib.sha256
    ).hexdigest()
    
    return {
        "X-API-Key": api_key,
        "X-Timestamp": timestamp,
        "X-Signature": signature
    }
```

---

> **注意**: 所有API调用都应包含适当的错误处理和重试逻辑，以确保系统的可靠性。