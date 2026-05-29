# ⚙️ 配置说明

> 系统配置详解和优化建议

## 配置文件概述

MT5 AI交易系统使用多级配置系统：

1. **环境变量** (`.env`文件) - 核心服务配置
2. **EA参数** (MT5界面) - 客户端运行时配置
3. **Python配置** (`config.py`) - 程序内部配置
4. **数据库配置** - 数据存储和缓存配置

## 环境变量配置 (`.env`)

### AI服务配置
```env
# ==================== DeepSeek AI配置 ====================
USE_DEEPSEEK=true                    # 启用AI功能（true/false）
DEEPSEEK_API_KEY=sk-您的密钥         # DeepSeek API密钥（必需）
DEEPSEEK_API_URL=https://api.deepseek.com/v1/chat/completions  # API地址
DEEPSEEK_MODEL=deepseek-chat         # 使用的模型
DEEPSEEK_MAX_TOKENS=1000             # 最大响应长度
DEEPSEEK_TEMPERATURE=0.7             # 响应随机性（0-1）

# ==================== 服务网络配置 ====================
SOCKET_HOST=127.0.0.1                # Socket服务监听地址
SOCKET_PORT=8080                     # Socket服务端口
WEBSOCKET_PORT=8081                  # WebSocket服务端口
HTTP_PORT=8000                       # Web仪表盘端口
SERVICE_ID=ai_trading_系统自动生成     # 服务唯一标识

# ==================== 性能配置 ====================
CACHE_SIZE=100                       # LRU缓存大小（条数）
CONFIDENCE_THRESHOLD=0.65            # 置信度阈值（0-1）
REQUEST_TIMEOUT=30                   # 请求超时时间（秒）
MAX_RETRIES=3                        # 最大重试次数
CONNECTION_POOL_SIZE=10              # HTTP连接池大小

# ==================== 安全配置 ====================
MAX_DAILY_LOSS=1000                  # 每日最大亏损（USD）
MAX_POSITIONS=5                      # 最大同时持仓数
ENABLE_SAFETY_CHECKS=true            # 启用安全检查
ALLOW_REVERSE_CLOSE=true             # 允许反向平仓
VALIDATE_STOP_LEVELS=true            # 验证止损止盈水平

# ==================== 日志配置 ====================
LOG_LEVEL=INFO                       # 日志级别（DEBUG/INFO/WARNING/ERROR）
LOG_FILE=service.log                 # 日志文件路径
LOG_FORMAT=detailed                  # 日志格式（simple/detailed/json）
```

### 配置说明

#### DeepSeek AI配置
- **USE_DEEPSEEK**: 必须设置为`true`才能使用AI功能
- **DEEPSEEK_API_KEY**: 从DeepSeek官网获取的有效API密钥
- **DEEPSEEK_TEMPERATURE**: 值越高AI响应越随机，推荐0.7-0.8

#### 网络配置
- **SOCKET_HOST**: 通常为127.0.0.1（本地），如需远程访问可设为0.0.0.0
- **端口分配**:
  - 8080: Socket服务（TCP）
  - 8081: WebSocket服务（V3.0）
  - 8000: HTTP Web仪表盘

#### 性能配置
- **CACHE_SIZE**: 根据内存调整，每条缓存约2KB，100条约200KB
- **CONFIDENCE_THRESHOLD**: 置信度低于此值的建议将被过滤
- **REQUEST_TIMEOUT**: 包含AI API调用的总超时时间

## EA参数配置

### 通信设置
| 参数 | 类型 | 默认值 | 范围 | 说明 |
|------|------|--------|------|------|
| **InpCommMode** | ENUM | MODE_AUTO | MODE_AUTO/MODE_SOCKET/MODE_FILE/MODE_WEBSOCKET | 通信模式 |
| **InpSocketHost** | string | "127.0.0.1" | 任意IP或主机名 | Socket服务地址 |
| **InpSocketPort** | int | 8080 | 1-65535 | Socket服务端口 |
| **InpWebSocketURL** | string | "ws://127.0.0.1:8081" | 有效的WebSocket URL | WebSocket服务地址 |

### 连接设置
| 参数 | 类型 | 默认值 | 范围 | 说明 |
|------|------|--------|------|------|
| **InpConnectTimeout** | int | 3000 | 100-10000 | 连接超时(ms) |
| **InpReceiveTimeout** | int | 5000 | 1000-30000 | 接收超时(ms) |
| **InpMaxRetries** | int | 3 | 0-10 | 最大重试次数 |
| **InpFailoverThreshold** | int | 3 | 1-10 | 故障转移阈值 |

### 交易设置
| 参数 | 类型 | 默认值 | 范围 | 说明 |
|------|------|--------|------|------|
| **InpLotSize** | double | 0.1 | 0.01-100 | 交易手数 |
| **InpStopLoss** | int | 200 | 10-1000 | 止损点数 |
| **InpTakeProfit** | int | 400 | 20-2000 | 止盈点数 |
| **InpMaxDailyLoss** | double | 1000 | 0-10000 | 每日最大亏损 |

### 显示设置
| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| **InpShowPanel** | bool | true | 显示信息面板 |
| **InpShowLines** | bool | true | 显示支撑阻力线 |
| **InpPanelCorner** | ENUM | CORNER_LEFT_UPPER | 面板位置 |
| **InpPanelX** | int | 10 | 面板X坐标 |
| **InpPanelY** | int | 20 | 面板Y坐标 |

## Python配置 (`config.py`)

### 核心配置类
```python
class Config:
    # 从环境变量加载配置
    USE_DEEPSEEK = os.getenv("USE_DEEPSEEK", "true").lower() == "true"
    DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
    
    # 服务配置
    SOCKET_HOST = os.getenv("SOCKET_HOST", "127.0.0.1")
    SOCKET_PORT = int(os.getenv("SOCKET_PORT", "8080"))
    WEBSOCKET_PORT = int(os.getenv("WEBSOCKET_PORT", "8081"))
    HTTP_PORT = int(os.getenv("HTTP_PORT", "8000"))
    
    # 性能配置
    CACHE_SIZE = int(os.getenv("CACHE_SIZE", "100"))
    CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "0.65"))
    REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "30"))
```

### 配置验证
系统启动时会自动验证配置：
- API密钥是否有效
- 端口是否可用
- 必要目录是否存在
- 数据库连接是否正常

## 数据库配置

### SQLite配置
```python
# 数据库路径
DB_PATH = "data/trading.db"

# 连接配置
DB_POOL_SIZE = 5
DB_MAX_OVERFLOW = 10
DB_POOL_RECYCLE = 3600  # 连接回收时间(秒)

# 表结构自动迁移
ENABLE_AUTO_MIGRATE = True
```

### 数据保留策略
```python
# 交易记录保留
TRADE_HISTORY_DAYS = 90      # 交易记录保留90天
PERF_METRICS_DAYS = 30       # 性能指标保留30天
LOG_ENTRIES_DAYS = 7         # 日志条目保留7天

# 缓存清理策略
CACHE_CLEAN_INTERVAL = 3600  # 缓存清理间隔(秒)
MAX_CACHE_AGE = 86400        # 缓存最大存活时间(秒)
```

## 优化配置建议

### 小型账户配置
```env
# 风险控制更严格
MAX_DAILY_LOSS=500
MAX_POSITIONS=3
CONFIDENCE_THRESHOLD=0.7

# 性能优化
CACHE_SIZE=50
REQUEST_TIMEOUT=20
```

### 大型账户配置
```env
# 提高限制
MAX_DAILY_LOSS=5000
MAX_POSITIONS=10
CONFIDENCE_THRESHOLD=0.6

# 性能最大化
CACHE_SIZE=200
CONNECTION_POOL_SIZE=20
```

### 高频交易配置
```env
# 低延迟配置
REQUEST_TIMEOUT=10
CONNECTION_POOL_SIZE=30
CACHE_SIZE=300

# 网络优化
SOCKET_HOST=0.0.0.0  # 允许远程连接
```

## 配置验证和测试

### 配置验证脚本
```powershell
# 验证环境变量配置
python tools/validate_config.py

# 测试网络连接
python tools/test_socket_connection.py --host 127.0.0.1 --port 8080

# 测试AI服务
python tools/test_deepseek.py --api-key $env:DEEPSEEK_API_KEY
```

### 配置问题诊断

#### 问题1：AI服务不可用
```powershell
# 检查API密钥
echo $env:DEEPSEEK_API_KEY

# 测试API连接
python tools/test_deepseek.py --verbose
```

#### 问题2：Socket连接失败
```powershell
# 检查端口占用
netstat -ano | findstr :8080

# 测试Socket服务
python tools/test_socket_connection.py --timeout 5000
```

#### 问题3：性能问题
```powershell
# 监控系统资源
python tools/monitor_performance.py --interval 5

# 分析缓存命中率
python tools/analyze_cache.py --log-file service.log
```

## 动态配置更新

### 运行时配置更新
部分配置支持热更新：
```python
# 通过Web仪表盘更新配置
# 访问 http://127.0.0.1:8000/config
# 可动态调整：
# - 缓存大小
# - 置信度阈值
# - 日志级别
```

### 配置版本管理
建议使用配置版本控制：
```powershell
# 备份当前配置
copy .env .env.backup.$(Get-Date -Format "yyyyMMdd")

# 恢复配置
copy .env.backup.20240421 .env
```

## 安全配置建议

### 生产环境安全配置
```env
# 使用环境变量而非文件存储密钥
# 在系统环境变量中设置：
# DEEPSEEK_API_KEY=sk-...

# 限制服务访问
SOCKET_HOST=127.0.0.1  # 仅本地访问
# 或使用防火墙规则限制IP

# 启用所有安全检查
ENABLE_SAFETY_CHECKS=true
VALIDATE_STOP_LEVELS=true
ALLOW_REVERSE_CLOSE=true

# 定期轮换密钥
# 建议每月更新API密钥
```

---

> **重要**：修改配置后需要重启服务才能生效（部分配置支持热更新）。