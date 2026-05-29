# 🏆 最佳实践

> 系统使用、开发和维护的最佳实践指南

## 使用最佳实践

### 账户管理
1. **从模拟账户开始**
   - 在实盘交易前，至少在模拟账户上运行2-4周
   - 验证系统稳定性和策略有效性
   - 熟悉系统操作和监控方法

2. **资金管理**
   - 初始资金不超过总交易资金的10%
   - 单笔交易风险控制在账户资金的1-2%
   - 设置严格的每日亏损限额

3. **多品种分散**
   - 不要将所有资金投入单一品种
   - 选择相关性较低的交易品种
   - 根据市场时段选择活跃品种

### 风险管理
1. **止损设置**
   - 始终设置止损订单
   - 止损距离根据品种波动性调整
   - 避免移动止损过于频繁

2. **仓位控制**
   - 遵循最大持仓限制
   - 避免过度交易
   - 根据账户规模调整手数

3. **风险监控**
   - 每日检查风险指标
   - 监控最大回撤
   - 设置风险预警阈值

### 系统操作
1. **日常检查清单**
   ```powershell
   # 每日启动检查
   1. 检查Python服务运行状态
   2. 验证Web仪表盘可访问
   3. 确认MT5 EA连接正常
   4. 检查API密钥余额
   5. 查看昨日交易报告
   ```

2. **监控策略**
   - 每小时查看一次系统状态
   - 每日分析交易报告
   - 每周进行性能评估

3. **备份策略**
   - 每日备份交易数据
   - 每周备份配置文件
   - 每月完整系统备份

## 开发最佳实践

### 代码质量
1. **代码规范**
   ```python
   # 好的实践
   def analyze_market_data(symbol, bid, ask, history):
       """分析市场数据并返回交易建议"""
       # 清晰的函数文档
       if not validate_inputs(symbol, bid, ask):
           return create_error_response("输入验证失败")
       
       try:
           result = process_market_data(symbol, bid, ask, history)
           return format_response(result)
       except Exception as e:
           log_error(f"分析失败: {e}")
           return create_fallback_response()
   
   # 避免的做法
   def analyze(a,b,c,d):  # 参数名不清晰
       # 没有错误处理
       return process(a,b,c,d)
   ```

2. **错误处理**
   ```python
   # 全面的错误处理
   def process_request(request_data):
       try:
           validate_request(request_data)
           result = call_external_api(request_data)
           return {"success": True, "data": result}
           
       except ValidationError as e:
           log_warning(f"请求验证失败: {e}")
           return {"success": False, "error": "请求格式错误"}
           
       except APITimeoutError as e:
           log_error(f"API调用超时: {e}")
           return {"success": False, "error": "服务响应超时"}
           
       except Exception as e:
           log_critical(f"未预期错误: {e}")
           return {"success": False, "error": "系统内部错误"}
   ```

3. **测试驱动**
   ```python
   # 先写测试
   def test_trade_execution():
       """测试交易执行逻辑"""
       trader = TradeExecutor()
       
       # 测试买入
       result = trader.execute_trade(
           symbol="EURUSD",
           action="BUY",
           confidence=0.78,
           lot_size=0.1
       )
       
       assert result["success"] == True
       assert "order_id" in result
       assert result["action"] == "BUY"
   
   # 后实现功能
   class TradeExecutor:
       def execute_trade(self, symbol, action, confidence, lot_size):
           if confidence < CONFIDENCE_THRESHOLD:
               return {"success": False, "error": "置信度过低"}
           
           # 执行交易逻辑...
           return {"success": True, "order_id": order_id, "action": action}
   ```

### 性能优化
1. **缓存策略**
   ```python
   # 智能缓存
   class SmartCache:
       def __init__(self, size=100, ttl=300):
           self.cache = LRUCache(size)
           self.ttl = ttl  # 缓存生存时间（秒）
       
       def get_with_fallback(self, key, fallback_func, *args, **kwargs):
           """获取缓存，如果不存在则调用fallback函数"""
           cached = self.cache.get(key)
           
           if cached and time.time() - cached["timestamp"] < self.ttl:
               return cached["data"]
           
           # 调用fallback函数获取新数据
           fresh_data = fallback_func(*args, **kwargs)
           
           # 更新缓存
           self.cache.put(key, {
               "data": fresh_data,
               "timestamp": time.time()
           })
           
           return fresh_data
   ```

2. **连接管理**
   ```python
   # 连接池
   class ConnectionPool:
       def __init__(self, max_size=10, idle_timeout=300):
           self.pool = Queue(max_size)
           self.idle_timeout = idle_timeout
           self._init_pool(max_size)
       
       def get_connection(self):
           """从池中获取连接"""
           try:
               conn = self.pool.get_nowait()
               if self._is_connection_valid(conn):
                   return conn
           except QueueEmpty:
               pass
           
           # 创建新连接
           return self._create_connection()
       
       def return_connection(self, conn):
           """归还连接到池中"""
           if self._is_connection_valid(conn):
               self.pool.put_nowait(conn)
           else:
               conn.close()
   ```

3. **异步处理**
   ```python
   # 异步请求处理
   import asyncio
   from concurrent.futures import ThreadPoolExecutor
   
   class AsyncRequestHandler:
       def __init__(self, max_workers=5):
           self.executor = ThreadPoolExecutor(max_workers)
       
       async def process_batch_requests(self, requests):
           """批量处理请求"""
           loop = asyncio.get_event_loop()
           
           # 并发执行请求
           tasks = []
           for request in requests:
               task = loop.run_in_executor(
                   self.executor,
                   self._process_single_request,
                   request
               )
               tasks.append(task)
           
           # 等待所有任务完成
           results = await asyncio.gather(*tasks, return_exceptions=True)
           
           # 处理结果
           processed_results = []
           for result in results:
               if isinstance(result, Exception):
                   processed_results.append({"error": str(result)})
               else:
                   processed_results.append(result)
           
           return processed_results
   ```

### 安全实践
1. **API密钥管理**
   ```python
   # 安全的密钥管理
   from cryptography.fernet import Fernet
   import os
   
   class SecureKeyManager:
       def __init__(self, key_file=".encrypted_key"):
           self.key_file = key_file
           self._ensure_key_exists()
       
       def _ensure_key_exists(self):
           if not os.path.exists(self.key_file):
               # 从环境变量获取密钥
               raw_key = os.getenv("API_KEY", "")
               if raw_key:
                   self._encrypt_and_save(raw_key)
       
       def _encrypt_and_save(self, plaintext_key):
           # 生成加密密钥
           encryption_key = Fernet.generate_key()
           cipher = Fernet(encryption_key)
           
           # 加密API密钥
           encrypted_key = cipher.encrypt(plaintext_key.encode())
           
           # 保存加密后的密钥
           with open(self.key_file, "wb") as f:
               f.write(encrypted_key)
           
           # 将加密密钥保存在安全的地方
           # （实际使用中应使用密钥管理服务）
           print(f"加密密钥: {encryption_key.decode()}")
           print("请将此密钥保存在安全的地方")
       
       def get_decrypted_key(self, encryption_key):
           """使用加密密钥解密API密钥"""
           with open(self.key_file, "rb") as f:
               encrypted_key = f.read()
           
           cipher = Fernet(encryption_key.encode())
           return cipher.decrypt(encrypted_key).decode()
   ```

2. **输入验证**
   ```python
   # 全面的输入验证
   class InputValidator:
       @staticmethod
       def validate_trade_request(request):
           """验证交易请求"""
           required_fields = ["symbol", "bid", "ask", "time"]
           
           # 检查必需字段
           for field in required_fields:
               if field not in request:
                   raise ValidationError(f"缺少必需字段: {field}")
           
           # 验证数据类型
           if not isinstance(request["symbol"], str):
               raise ValidationError("symbol必须是字符串")
           
           if not isinstance(request["bid"], (int, float)):
               raise ValidationError("bid必须是数字")
           
           if request["bid"] <= 0:
               raise ValidationError("bid必须大于0")
           
           # 验证业务逻辑
           if request["ask"] <= request["bid"]:
               raise ValidationError("ask必须大于bid")
           
           # 验证时间戳
           current_time = int(time.time())
           if request["time"] > current_time + 3600:  # 未来1小时
               raise ValidationError("时间戳不能在未来")
           
           if request["time"] < current_time - 86400:  # 过去24小时
               raise ValidationError("时间戳过于久远")
           
           return True
   ```

3. **日志安全**
   ```python
   # 安全的日志记录
   import logging
   import re
   
   class SanitizedLogger:
       def __init__(self, name):
           self.logger = logging.getLogger(name)
       
       def sanitize_message(self, message):
           """清理敏感信息"""
           # 移除API密钥
           message = re.sub(r'sk-[a-zA-Z0-9]{20,}', '[API_KEY]', message)
           
           # 移除IP地址
           message = re.sub(r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}', '[IP]', message)
           
           # 移除邮箱地址
           message = re.sub(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', '[EMAIL]', message)
           
           return message
       
       def info(self, message, *args, **kwargs):
           sanitized = self.sanitize_message(message)
           self.logger.info(sanitized, *args, **kwargs)
       
       def error(self, message, *args, **kwargs):
           sanitized = self.sanitize_message(message)
           self.logger.error(sanitized, *args, **kwargs)
   ```

## 维护最佳实践

### 监控和维护
1. **健康检查**
   ```python
   # 定期健康检查
   import schedule
   import time
   
   def health_check():
       """系统健康检查"""
       checks = [
           check_service_status,
           check_database_connection,
           check_api_availability,
           check_disk_space,
           check_memory_usage
       ]
       
       results = []
       for check_func in checks:
           try:
               result = check_func()
               results.append((check_func.__name__, True, result))
           except Exception as e:
               results.append((check_func.__name__, False, str(e)))
       
       # 生成报告
       report = generate_health_report(results)
       
       # 如果有严重问题，发送告警
       if any(not success for _, success, _ in results):
           send_alert(report)
       
       return report
   
   # 每5分钟运行一次健康检查
   schedule.every(5).minutes.do(health_check)
   
   while True:
       schedule.run_pending()
       time.sleep(1)
   ```

2. **性能监控**
   ```python
   # 性能指标收集
   from prometheus_client import Counter, Gauge, Histogram, start_http_server
   
   # 定义指标
   REQUESTS_TOTAL = Counter('requests_total', 'Total requests')
   REQUEST_DURATION = Histogram('request_duration_seconds', 'Request duration')
   ACTIVE_CONNECTIONS = Gauge('active_connections', 'Active connections')
   CACHE_HIT_RATE = Gauge('cache_hit_rate', 'Cache hit rate')
   
   class PerformanceMonitor:
       def __init__(self, port=9090):
           start_http_server(port)
       
       @REQUEST_DURATION.time()
       def process_request(self, request):
           """处理请求并记录指标"""
           REQUESTS_TOTAL.inc()
           ACTIVE_CONNECTIONS.inc()
           
           try:
               result = self._do_process(request)
               return result
           finally:
               ACTIVE_CONNECTIONS.dec()
       
       def update_cache_metrics(self, hits, misses):
           """更新缓存指标"""
           total = hits + misses
           if total > 0:
               rate = hits / total
               CACHE_HIT_RATE.set(rate)
   ```

3. **日志管理**
   ```python
   # 结构化日志
   import json
   import logging
   from datetime import datetime
   
   class StructuredLogger:
       def __init__(self, name, log_file="app.log"):
           self.logger = logging.getLogger(name)
           self.logger.setLevel(logging.INFO)
           
           # 文件处理器
           file_handler = logging.FileHandler(log_file)
           file_handler.setLevel(logging.INFO)
           
           # JSON格式化器
           formatter = JSONFormatter()
           file_handler.setFormatter(formatter)
           
           self.logger.addHandler(file_handler)
       
       def log_event(self, event_type, data, level="info"):
           """记录结构化事件"""
           log_entry = {
               "timestamp": datetime.utcnow().isoformat(),
               "event_type": event_type,
               "level": level,
               "data": data,
               "service": "mt5_ai_trading"
           }
           
           if level == "info":
               self.logger.info(json.dumps(log_entry))
           elif level == "warning":
               self.logger.warning(json.dumps(log_entry))
           elif level == "error":
               self.logger.error(json.dumps(log_entry))
   
   class JSONFormatter(logging.Formatter):
       def format(self, record):
           try:
               # 尝试解析JSON消息
               message = json.loads(record.getMessage())
           except json.JSONDecodeError:
               # 如果不是JSON，创建基本结构
               message = {"raw_message": record.getMessage()}
           
           log_entry = {
               "timestamp": self.formatTime(record),
               "level": record.levelname,
               "logger": record.name,
               "message": message
           }
           
           return json.dumps(log_entry)
   ```

### 备份和恢复
1. **数据备份策略**
   ```python
   # 自动化备份
   import shutil
   import sqlite3
   from datetime import datetime
   import schedule
   
   class BackupManager:
       def __init__(self, backup_dir="backups", retention_days=30):
           self.backup_dir = backup_dir
           self.retention_days = retention_days
           os.makedirs(backup_dir, exist_ok=True)
       
       def perform_backup(self):
           """执行完整备份"""
           timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
           
           # 备份数据库
           db_backup = self._backup_database(timestamp)
           
           # 备份配置文件
           config_backup = self._backup_configs(timestamp)
           
           # 备份日志文件
           log_backup = self._backup_logs(timestamp)
           
           # 创建备份清单
           manifest = {
               "timestamp": timestamp,
               "backups": {
                   "database": db_backup,
                   "configs": config_backup,
                   "logs": log_backup
               },
               "system_info": self._get_system_info()
           }
           
           # 保存清单
           manifest_file = os.path.join(self.backup_dir, f"manifest_{timestamp}.json")
           with open(manifest_file, "w") as f:
               json.dump(manifest, f, indent=2)
           
           # 清理旧备份
           self._cleanup_old_backups()
           
           return manifest
       
       def _backup_database(self, timestamp):
           """备份SQLite数据库"""
           source_db = "data/trading.db"
           backup_db = os.path.join(self.backup_dir, f"db_{timestamp}.db")
           
           # 使用SQLite备份API
           source = sqlite3.connect(source_db)
           backup = sqlite3.connect(backup_db)
           
           with backup:
               source.backup(backup)
           
           source.close()
           backup.close()
           
           return backup_db
   ```

2. **灾难恢复**
   ```python
   # 灾难恢复计划
   class DisasterRecovery:
       def __init__(self, backup_dir="backups"):
           self.backup_dir = backup_dir
       
       def recover_from_backup(self, backup_timestamp=None):
           """从备份恢复系统"""
           if backup_timestamp is None:
               # 查找最新备份
               backups = self._list_backups()
               if not backups:
                   raise Exception("未找到可用备份")
               backup_timestamp = max(backups)
           
           # 读取备份清单
           manifest_file = os.path.join(
               self.backup_dir, 
               f"manifest_{backup_timestamp}.json"
           )
           
           with open(manifest_file, "r") as f:
               manifest = json.load(f)
           
           # 停止服务
           self._stop_services()
           
           try:
               # 恢复数据库
               self._restore_database(manifest["backups"]["database"])
               
               # 恢复配置文件
               self._restore_configs(manifest["backups"]["configs"])
               
               # 恢复日志（可选）
               self._restore_logs(manifest["backups"]["logs"])
               
               print(f"✅ 系统已从备份 {backup_timestamp} 恢复")
               
           except Exception as e:
               print(f"❌ 恢复失败: {e}")
               raise
           
           finally:
               # 重启服务
               self._start_services()
   ```

## 部署最佳实践

### 环境配置
1. **环境分离**
   ```
   # 目录结构
   project/
   ├── .env.development    # 开发环境配置
   ├── .env.staging       # 测试环境配置
   ├── .env.production    # 生产环境配置
   └── .env.example       # 配置模板
   
   # 根据环境加载配置
   ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
   env_file = f".env.{ENVIRONMENT}"
   load_dotenv(env_file)
   ```

2. **配置验证**
   ```python
   # 启动时配置验证
   def validate_configuration():
       """验证所有必需配置"""
       required_configs = [
           "DEEPSEEK_API_KEY",
           "SOCKET_HOST",
           "SOCKET_PORT"
       ]
       
       missing = []
       for config in required_configs:
           if not os.getenv(config):
               missing.append(config)
       
       if missing:
           raise ConfigurationError(
               f"缺少必需配置: {', '.join(missing)}"
           )
       
       # 验证端口可用性
       validate_port_availability()
       
       # 验证API密钥
       validate_api_key()
   ```

### 高可用部署
1. **负载均衡配置**
   ```nginx
   # nginx配置示例
   upstream mt5_ai_servers {
       server 127.0.0.1:8080;
       server 127.0.0.1:8082;
       server 127.0.0.1:8084;
   }
   
   server {
       listen 80;
       server_name mt5-ai.example.com;
       
       location / {
           proxy_pass http://mt5_ai_servers;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
           proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
       }
       
       # 健康检查端点
       location /health {
           access_log off;
           return 200 "healthy\n";
           add_header Content-Type text/plain;
       }
   }
   ```

2. **服务发现和注册**
   ```python
   # 服务注册和发现
   class ServiceRegistry:
       def __init__(self, consul_host="localhost", consul_port=8500):
           self.consul_client = consul.Consul(
               host=consul_host, 
               port=consul_port
           )
       
       def register_service(self, service_name, service_id, address, port):
           """注册服务"""
           self.consul_client.agent.service.register(
               name=service_name,
               service_id=service_id,
               address=address,
               port=port,
               check={
                   "HTTP": f"http://{address}:{port}/health",
                   "interval": "10s",
                   "timeout": "5s"
               }
           )
       
       def discover_services(self, service_name):
           """发现服务实例"""
           services = self.consul_client.health.service(service_name)[1]
           instances = []
           
           for service in services:
               instance = {
                   "address": service["Service"]["Address"],
                   "port": service["Service"]["Port"],
                   "status": service["Checks"][0]["Status"]
               }
               instances.append(instance)
           
           return instances
   ```

---

> **重要**: 最佳实践应随着系统发展和经验积累不断更新。定期审查和更新这些实践以确保其有效性。