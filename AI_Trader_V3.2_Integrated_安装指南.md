
## 安装步骤

### 1. 编译EA
1. 打开MetaTrader 5平台
2. 打开MetaEditor (F4)
3. 文件 → 打开 → 浏览到 `MQL5/Experts/AI_Trader_V3.2_Integrated.mq5`
4. 点击"编译"按钮 (F7)
5. 确认无编译错误

### 2. 配置EA参数
在图表上加载EA时，配置以下关键参数：

#### 基本交易参数：
- `InpLotSize`: 交易手数 (默认: 0.01)
- `InpMinConfidence`: 最小置信度 (默认: 0.65)
- `InpRequestInterval`: AI请求间隔秒数 (默认: 300, 5分钟)
- `InpStopLoss`: 止损点数 (默认: 30)
- `InpTakeProfit`: 止盈点数 (默认: 60)

#### 安全参数：
- `InpReversePosition`: 反向信号时平仓反转 (默认: true)
- `InpMaxDailyLoss`: 每日最大亏损 (默认: 0.0 = 禁用)
- `InpEnableRiskCheck`: 启用风险检查 (默认: true)

#### 实时账户数据推送：
- `InpPushAccountData`: 启用账户数据推送 (默认: true)
- `InpAccountDataInterval`: 推送间隔秒数 (默认: 60)
- `InpAccountDataHost`: 推送服务器IP (默认: 127.0.0.1)
- `InpAccountDataPort`: 推送服务器端口 (默认: 8080)

#### 性能优化：
- `InpPanelUpdateInt`: 面板更新间隔秒数 (默认: 1)
- `InpSRUpdateInt`: 支撑阻力更新间隔秒数 (默认: 5)
- `InpEnablePerfStats`: 启用性能统计 (默认: true)

### 3. 启动Python服务
确保以下服务在EA之前启动：

```bash
# 启动AI交易服务（支持MQL5数据）
python mt5_ai_service_optimized.py --mode auto

# 或使用异步优化版
python mt5_ai_service_optimized.py
```

### 4. 验证连接
1. EA加载后检查日志输出：
   - "账户数据推送连接成功: 127.0.0.1:8080"
   - "AI交易EA V3.2 - 集成版已初始化"
2. 检查Python服务日志：
   - "MQL5 数据管理器初始化完成"
   - 收到账户数据推送

## 功能验证

### 账户数据推送验证：
1. EA每60秒推送一次账户数据
2. Python服务接收并处理数据
3. 数据通过MQL5DataManager更新到AI引擎和风险管理系统

### 安全特性验证：
1. 反向信号时自动平仓反转
2. 每日亏损限制监控
3. 持仓检查和止损验证

### 性能监控：
1. 面板显示实时性能统计
2. 指标缓存减少计算负载
3. 异步状态机避免阻塞

## 故障排除

### 账户数据推送失败：
1. 检查Python服务是否运行在8080端口
2. 确认防火墙允许MT5出站连接
3. 验证EA参数中的主机和端口配置

### 编译错误：
1. 确保MT5版本支持Socket功能
2. 检查MQL5标准库路径
3. 验证所有include文件存在

### 连接问题：
1. 重启MT5和Python服务
2. 检查网络连接状态
3. 验证服务配置一致性
