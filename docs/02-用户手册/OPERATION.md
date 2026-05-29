# 🎮 操作指南

> 日常操作、监控和维护指南

## 日常操作流程

### 标准启动流程
1. **启动AI服务**：
   ```powershell
   cd "D:\搬家文件夹\XM Global MT5"
   python mt5_ai_service.py
   ```

2. **验证服务状态**：
   - 检查控制台输出，确认V3.0启动成功
   - 访问Web仪表盘：http://127.0.0.1:8000
   - 确认所有服务模块显示正常

3. **启动MT5 EA**：
   - 打开MetaTrader 5
   - 在交易品种图表上添加 `AI_Trader_Integrated_Socket`
   - 确认EA初始化成功

4. **监控运行状态**：
   - 观察MT5图表上的信息面板
   - 查看Web仪表盘实时数据
   - 监控控制台日志（可选记录到文件）

### 标准关闭流程
1. **停止EA交易**：
   - 在MT5中从图表移除EA
   - 或禁用EA的自动交易功能

2. **停止AI服务**：
   - 在服务控制台按 `Ctrl+C`
   - 等待服务优雅关闭（约3-5秒）

3. **验证关闭**：
   - 确认所有进程已退出
   - 检查端口释放：8080、8081、8000
   - 备份重要日志和数据

## 实时监控

### Web监控仪表盘
访问 http://127.0.0.1:8000 查看：

#### 1. 系统状态面板
- **服务状态**: 运行时间、版本信息
- **通信模式**: 当前使用的通信方式
- **连接统计**: 活跃连接数、请求总数
- **资源使用**: CPU、内存、缓存命中率

#### 2. 交易监控面板
- **实时交易**: 最新交易建议和结果
- **持仓状态**: 当前持仓和盈亏情况
- **风险指标**: 每日亏损、最大回撤等
- **性能统计**: 胜率、平均盈亏比

#### 3. 性能监控面板
- **响应时间**: AI响应、通信延迟
- **缓存效率**: 命中率、缓存大小
- **错误统计**: 各类错误发生次数
- **趋势图表**: 关键指标随时间变化

### MT5信息面板
EA在图表上显示的信息面板：

#### 面板布局
```
┌─────────────────────────────────────┐
│   AI智能交易系统 - V3.0            │
│   通信模式: SOCKET                 │
│   服务状态: ✅ 连接正常            │
│   请求统计: 125次 (成功: 120)      │
│   最后响应: BUY | 置信度: 0.78     │
│   持仓状态: GOLD_ 0.1手 (盈: +$15) │
│   今日盈亏: +$45.20                │
└─────────────────────────────────────┘
```

#### 面板颜色编码
- **绿色**: 正常状态、盈利
- **黄色**: 警告状态、小幅度亏损
- **红色**: 错误状态、风险超限
- **蓝色**: 信息状态、中性

### 日志监控

#### 控制台日志级别
```powershell
# 不同详细程度的日志
python mt5_ai_service.py --log-level DEBUG    # 最详细
python mt5_ai_service.py --log-level INFO     # 默认
python mt5_ai_service.py --log-level WARNING  # 仅警告和错误
python mt5_ai_service.py --log-level ERROR    # 仅错误
```

#### 日志文件监控
```powershell
# 实时查看日志
Get-Content service.log -Wait

# 筛选关键信息
Select-String -Path service.log -Pattern "ERROR|WARNING"
Select-String -Path service.log -Pattern "交易|持仓|盈亏"

# 日志轮转配置
# 在.env中设置：
# LOG_MAX_SIZE=10485760  # 10MB
# LOG_BACKUP_COUNT=5     # 保留5个备份
```

## 交易管理

### 交易信号解读

#### AI建议类型
1. **BUY (买入)**:
   - 置信度 ≥ 阈值（默认0.65）
   - AI分析显示强烈上涨信号
   - 多重技术指标确认

2. **SELL (卖出)**:
   - 置信度 ≥ 阈值
   - AI分析显示强烈下跌信号
   - 多重技术指标确认

3. **HOLD (持有)**:
   - 置信度 < 阈值
   - 市场趋势不明确
   - 建议观望

#### 置信度说明
- **0.8-1.0**: 强烈信号，高概率成功
- **0.65-0.8**: 中等信号，值得考虑
- **0.5-0.65**: 弱信号，建议谨慎
- **<0.5**: 不建议交易

### 持仓管理

#### 自动持仓控制
系统自动管理：
- 同方向持仓合并
- 反向信号自动平仓
- 止损止盈自动执行
- 风险超限自动停止

#### 手动干预
```mql5
// 在MT5中手动操作：
// 1. 右键持仓 → 平仓
// 2. 修改EA参数实时生效
// 3. 禁用EA暂停自动交易
```

### 风险控制

#### 实时风险监控
1. **每日亏损限制**:
   - 达到限制自动停止新交易
   - 次日自动重置计数器
   - 可通过Web仪表盘调整

2. **最大持仓限制**:
   - 控制同时持仓数量
   - 防止过度交易
   - 根据账户规模调整

3. **单笔风险控制**:
   - 每笔交易最大风险比例
   - 基于账户余额动态计算
   - 防止单笔亏损过大

## 维护操作

### 日常维护

#### 每日检查清单
1. [ ] 服务运行状态正常
2. [ ] Web仪表盘可访问
3. [ ] EA连接正常
4. [ ] API密钥有效（余额充足）
5. [ ] 磁盘空间充足
6. [ ] 日志文件大小正常
7. [ ] 数据库连接正常

#### 每周维护任务
1. **日志清理**:
   ```powershell
   # 清理7天前的日志
   Get-ChildItem *.log | Where-Object {$_.LastWriteTime -lt (Get-Date).AddDays(-7)} | Remove-Item
   ```

2. **数据库维护**:
   ```powershell
   # 优化数据库
   python tools/db_maintenance.py --vacuum --analyze
   ```

3. **备份重要数据**:
   ```powershell
   # 备份交易记录
   python tools/backup_data.py --output backup_$(Get-Date -Format "yyyyMMdd").zip
   ```

### 性能优化

#### 监控性能指标
```powershell
# 查看关键性能指标
python tools/performance_monitor.py --metrics response_time,cache_hit_rate,error_rate

# 生成性能报告
python tools/performance_report.py --period daily --output report.html
```

#### 优化建议
1. **响应时间慢**:
   - 增加缓存大小
   - 优化网络连接
   - 升级API密钥套餐

2. **缓存命中率低**:
   - 调整缓存策略
   - 分析市场波动性
   - 考虑不同交易品种特性

3. **连接不稳定**:
   - 检查网络质量
   - 调整超时设置
   - 启用备用通信模式

### 故障处理

#### 常见故障恢复

##### 故障1：服务崩溃
**症状**: Python服务意外退出
**恢复步骤**:
1. 检查崩溃日志 `error.log`
2. 重启服务：`python mt5_ai_service.py`
3. 如频繁崩溃，降低负载或检查配置

##### 故障2：EA失去连接
**症状**: MT5显示"Socket服务器不可用"
**恢复步骤**:
1. 检查Python服务是否运行
2. 验证防火墙设置
3. 重启MT5 EA
4. 切换到文件模式临时使用

##### 故障3：AI响应失败
**症状**: 长时间无交易信号
**恢复步骤**:
1. 测试AI连接：`python tools/test_deepseek.py`
2. 检查API密钥余额
3. 查看DeepSeek服务状态
4. 临时禁用AI功能，使用规则交易

#### 紧急操作流程

##### 立即停止交易
1. **快速方法**: 在MT5中移除EA
2. **备用方法**: 停止Python服务
3. **最终方法**: 关闭MT5终端

##### 数据恢复
```powershell
# 从备份恢复
python tools/restore_backup.py --file backup_20240421.zip

# 检查数据完整性
python tools/verify_data.py --repair
```

## 高级操作

### 多账户管理

#### 同时运行多个EA
1. **不同交易品种**:
   - 每个品种使用独立图表和EA实例
   - 共享同一个Python服务

2. **不同账户**:
   - 每个账户需要独立的Python服务实例
   - 使用不同端口配置

#### 配置示例
```powershell
# 账户1服务
python mt5_ai_service.py --socket-port 8080 --websocket-port 8081 --http-port 8000

# 账户2服务
python mt5_ai_service.py --socket-port 8082 --websocket-port 8083 --http-port 8001
```

### 策略调整

#### 实时调整参数
通过Web仪表盘可调整：
- 置信度阈值
- 风险限制
- 交易手数
- 技术指标权重

#### 长期策略优化
1. **收集交易数据**
2. **分析策略表现**
3. **调整AI提示词**
4. **回测验证**
5. **实盘部署**

### 数据分析和报告

#### 生成交易报告
```powershell
# 日报
python tools/generate_report.py --period daily --format html

# 周报
python tools/generate_report.py --period weekly --format pdf

# 自定义报告
python tools/generate_report.py --start 2024-01-01 --end 2024-04-21 --metrics all
```

#### 性能分析
```powershell
# 分析胜率和盈亏比
python tools/analyze_performance.py --metric win_rate,profit_factor

# 找出最佳参数组合
python tools/optimize_parameters.py --parameter confidence_threshold --range 0.5,0.8
```

## 最佳实践

### 操作纪律
1. **定期监控**: 至少每小时查看一次状态
2. **及时响应**: 发现问题立即处理
3. **保持记录**: 记录所有操作和异常
4. **定期备份**: 每日备份重要数据
5. **持续学习**: 分析交易结果，优化策略

### 风险管理
1. **从小开始**: 先用模拟账户测试
2. **逐步增加**: 验证稳定后增加资金
3. **设置上限**: 严格遵守风险限制
4. **分散风险**: 不要全部资金投入
5. **准备预案**: 制定故障应对计划

### 技术维护
1. **定期更新**: 保持软件最新版本
2. **监控资源**: 关注系统性能指标
3. **清理维护**: 定期清理日志和临时文件
4. **安全加固**: 定期检查安全配置
5. **文档更新**: 保持操作文档同步

---

> **提示**: 成功的自动化交易 = 优秀的技术系统 + 严谨的风险管理 + 持续的策略优化