# MT5 AI交易系统 - 实时图表Socket模式测试指南

## 测试目标
验证在实时MT5图表上使用Socket通信模式的完整功能，解决策略测试器中的网络限制问题。

## 系统当前状态验证

### ✅ 已确认的服务状态
1. **Socket服务器**：端口8080正在监听 (127.0.0.1:8080)
2. **Web Dashboard**：运行在 http://127.0.0.1:8000
3. **AI核心服务**：支持Socket/WebSocket/File/AUTO模式
4. **异步优化**：已应用async-python-patterns技能，性能优化完成

### ⚠️ 已知问题
- EA在策略测试器中Socket连接失败（错误4014）
- 保证金水平警告持续出现（0.0%）
- 账户数据推送连接失败

## 实时图表测试准备

### 第一步：确认Python服务运行
```bash
# 检查Socket服务器是否运行
cd "d:\搬家文件夹\XM Global MT5"
python -c "import socket; s = socket.socket(); s.settimeout(2); result = s.connect_ex(('127.0.0.1', 8080)); print('Socket服务器状态:', '✅ 在线' if result == 0 else f'❌ 离线，错误:{result}'); s.close()"
```

**预期结果**：`Socket服务器状态: ✅ 在线`

### 第二步：准备MT5环境
1. **打开MetaTrader 5** 
2. **登录您的交易账户**
3. **打开一个图表窗口**（建议使用EURUSD或GOLD_）

### 第三步：配置EA参数
1. **导航到EA文件**：
   ```
   MQL5\Experts\AI_Trader_Integrated_Socket.mq5
   ```

2. **确保已编译**（`.ex5`文件存在）

3. **在实时图表上加载EA**：
   - 将EA拖放到图表上
   - 或使用"导航器" → "专家顾问" → 双击`AI_Trader_Integrated_Socket`

### 第四步：关键参数设置

#### 通信参数
```
Communication Mode: SOCKET        # 选择Socket模式
Socket Host: 127.0.0.1           # 本地主机
Socket Port: 8080                # Socket服务器端口
Timeout (seconds): 5             # 连接超时
```

#### 账户数据推送
```
Enable Account Data Push: true   # 启用账户数据推送
Push Interval (seconds): 10      # 推送间隔
Push Account Info: true          # 推送账户信息
Push Positions: true             # 推送持仓数据
Push Risk Metrics: true          # 推送风险指标
```

#### 交易参数
```
Symbol: AUTO                     # 自动选择品种
Timeframe: CURRENT               # 当前时间框架
Risk Percent (%): 1.5            # 每笔交易风险比例
Max Positions: 5                 # 最大持仓数量
Stop Loss (pips): 50             # 止损点数
Take Profit (pips): 100          # 止盈点数
```

#### 日志与调试
```
Enable Debug Logging: true       # 启用详细日志
Log Level: DEBUG                 # 日志级别
Save Logs to File: true          # 保存日志到文件
```

### 第五步：启动EA
1. **点击"确定"**应用参数
2. **确保"允许实时交易"**复选框已选中
3. **允许DLL导入**（如果需要）
4. **查看EA笑脸图标**出现在图表右上角

## 连接验证流程

### 实时监控方法

#### 1. 查看EA日志
- 打开MT5的"专家"标签
- 监控连接状态消息：
  ```
  ✅ Socket连接成功: 127.0.0.1:8080
  ✅ 账户数据推送已连接
  ✅ 接收到AI信号: [交易指令]
  ```

#### 2. 检查Web Dashboard
- 访问 http://127.0.0.1:8000
- 查看"实时连接"状态
- 验证Socket连接计数
- 监控账户数据流

#### 3. 查看Python服务日志
```
# 如果服务在终端运行，查看实时输出
[INFO]  新的Socket连接: 127.0.0.1:xxxxx
[INFO]  接收到EA心跳: MT5_Client_v1.0
[INFO]  处理交易请求: symbol=GOLD_, action=ANALYZE
[INFO]  AI分析完成: SELL GOLD_ (置信度: 0.68)
```

### 预期成功标志

#### ✅ 第一阶段：连接建立
1. EA日志显示Socket连接成功
2. Python服务显示新连接建立
3. Web Dashboard显示活跃Socket连接

#### ✅ 第二阶段：数据交换
1. 账户数据推送成功（Python服务收到账户信息）
2. AI生成交易信号并推送给EA
3. EA接收信号并在日志中显示

#### ✅ 第三阶段：交易执行
1. EA根据AI信号执行交易
2. MT5账户出现实际交易记录
3. 风险管理器正常运作

## 故障排除指南

### 常见问题与解决方案

#### ❌ 问题1：Socket连接失败（仍显示错误4014）
**可能原因**：
- Windows防火墙阻止连接
- MT5网络权限不足
- Python服务未在监听端口

**解决方案**：
1. **检查防火墙**：
   ```powershell
   netsh advfirewall firewall show rule name="MT5 Socket Connection"
   ```
   如果没有规则，添加：
   ```powershell
   netsh advfirewall firewall add rule name="MT5 Socket Connection" dir=in action=allow protocol=TCP localport=8080
   ```

2. **检查MT5权限**：
   - 以管理员身份运行MT5
   - 确保"工具" → "选项" → "EA交易"中允许WebRequest

3. **重启Python服务**：
   ```bash
   cd "d:\搬家文件夹\XM Global MT5"
   python mt5_ai_service.py --mode socket
   ```

#### ❌ 问题2：账户数据推送失败
**可能原因**：
- 账户数据格式错误
- 推送间隔太短
- Python端数据处理错误

**解决方案**：
1. **检查EA参数**：
   - `Push Interval`设置为10-30秒
   - 确保所有推送选项都启用

2. **查看Python日志**：
   ```
   [ERR]  处理账户数据失败: [具体错误]
   ```

#### ❌ 问题3：交易信号未执行
**可能原因**：
- 风险管理器阻止开仓
- 保证金不足
- 交易时间限制

**解决方案**：
1. **检查账户状态**：
   - 确保有足够保证金
   - 检查交易时段是否开放

2. **检查风险管理器日志**：
   ```
   [INFO]  交易风险评估: 风险评分=0.17, 允许开仓=YES
   ```

### 调试模式启用

#### EA端调试
```
# 在EA输入参数中设置
Enable Debug Logging: true
Log Level: DEBUG
Log File: logs/ea_debug.log
```

#### Python端调试
```bash
# 启动带详细日志的服务
cd "d:\搬家文件夹\XM Global MT5"
python mt5_ai_service.py --mode socket --verbose --debug
```

## 性能监控指标

### 实时监控指标
1. **连接延迟**：< 100ms（理想状态）
2. **信号处理时间**：< 2秒
3. **交易执行延迟**：< 500ms
4. **系统资源使用**：CPU < 30%，内存 < 500MB

### Web Dashboard监控面板
- **连接状态**：Socket/WebSocket/File连接数
- **性能指标**：响应时间、吞吐量、错误率
- **交易统计**：信号数、执行数、成功率
- **风险指标**：账户健康度、持仓集中度

## 测试验收标准

### 最低要求（必须全部满足）
- [ ] EA成功建立Socket连接
- [ ] 账户数据推送到Python服务
- [ ] AI生成至少一个交易信号
- [ ] Web Dashboard显示实时连接状态

### 推荐目标（建议满足）
- [ ] 成功执行至少一笔交易
- [ ] 风险管理器正常工作
- [ ] 异步优化功能生效
- [ ] 系统稳定运行30分钟以上

## 安全注意事项

### 风险管理
1. **初始资金限制**：使用小资金测试（建议$100-500）
2. **最大仓位限制**：设置保守的仓位大小
3. **止损设置**：确保止损参数合理
4. **监控频率**：前30分钟密切监控

### 紧急停止
1. **立即停止EA**：在图表上右键 → "删除专家顾问"
2. **停止Python服务**：Ctrl+C在终端中
3. **关闭MT5**：如出现异常情况

## 后续优化建议

### 成功测试后的下一步
1. **性能基准测试**：测量不同负载下的表现
2. **多品种测试**：扩展到多个交易品种
3. **长时间运行测试**：24小时稳定性测试
4. **压力测试**：模拟市场波动下的表现

### 故障收集与改进
1. **记录所有错误日志**到`logs/real_time_testing.log`
2. **收集性能数据**用于优化
3. **更新系统配置**基于测试结果

---

## 测试结果记录表

| 测试项目 | 状态 | 时间戳 | 备注 |
|---------|------|--------|------|
| Socket连接建立 | | | |
| 账户数据推送 | | | |
| AI信号生成 | | | |
| 风险管理评估 | | | |
| 交易执行 | | | |
| 系统稳定性 | | | |
| 性能指标 | | | |

**测试开始时间**：_______________
**测试结束时间**：_______________
**测试人员**：___________________

---

## 技术支持

### 问题反馈渠道
1. **日志文件位置**：
   - EA日志：`MQL5/Logs/`
   - Python日志：`logs/`
   - 系统日志：`logs/system.log`

2. **关键文件检查**：
   - `core/mql5_data.py` - MQL5数据管理器
   - `core/websocket_handler_enhanced.py` - WebSocket处理器
   - `core/async_optimizer.py` - 异步优化器

3. **联系支持**：
   - 提供完整的日志文件
   - 描述问题现象和复现步骤
   - 附上相关配置截图

**祝您测试顺利！** 🚀