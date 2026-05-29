# MT5 AI交易系统 - 快速开始指南

## 🚀 5分钟快速部署

### 系统要求
- **操作系统**: Windows 10/11（推荐）或 Linux/macOS
- **Python**: 3.8+（推荐3.9+）
- **MetaTrader 5**: 最新版本
- **网络**: 可访问 DeepSeek API（需API密钥）

### 步骤1：安装依赖
```powershell
# 克隆项目（如果尚未克隆）
git clone <项目地址>
cd "XM Global MT5"

# 安装Python依赖
pip install -r requirements.txt
```

### 步骤2：配置环境
```powershell
# 复制环境变量模板
copy .env.example .env

# 编辑.env文件，设置您的DeepSeek API密钥
# 使用文本编辑器打开.env，修改以下内容：
# USE_DEEPSEEK=true
# DEEPSEEK_API_KEY=sk-您的真实API密钥
```

### 步骤3：启动AI服务
```powershell
# 方法1：使用自动模式启动（推荐）
python mt5_ai_service.py

# 方法2：指定通信模式启动
python mt5_ai_service.py --mode auto     # 自动模式（默认）
python mt5_ai_service.py --mode socket   # Socket模式
python mt5_ai_service.py --mode file     # 文件模式
python mt5_ai_service.py --mode websocket # WebSocket模式（V3.0）

# 方法3：带详细日志启动
python mt5_ai_service.py --log-file service.log --log-level DEBUG
```

### 步骤4：安装并配置MT5 EA
1. 将 `MQL5/Experts/AI_Trader_Integrated_Socket.mq5` 复制到MT5的 `MQL5/Experts/` 目录
2. 在MetaEditor中打开并编译（F7）
3. 在MT5图表上添加EA
4. 配置EA参数：
   - **通信模式**: AUTO（推荐）
   - **Socket地址**: 127.0.0.1:8080
   - **WebSocket地址**: ws://127.0.0.1:8081
   - **连接超时**: 3000ms
   - **最大重试次数**: 3
   - **故障转移阈值**: 3

### 步骤5：验证系统
1. **检查服务状态**: 访问 http://127.0.0.1:8000
2. **测试AI连接**: 运行 `python tools/test_deepseek.py`
3. **测试Socket连接**: 运行 `python tools/test_socket_connection.py`
4. **查看实时日志**: 服务控制台应显示成功启动信息

## ⚙️ 配置详解

### 核心配置（.env文件）
```env
# DeepSeek AI配置
USE_DEEPSEEK=true
DEEPSEEK_API_KEY=sk-您的密钥
DEEPSEEK_API_URL=https://api.deepseek.com/v1/chat/completions
DEEPSEEK_MODEL=deepseek-chat

# 服务配置
SOCKET_HOST=127.0.0.1
SOCKET_PORT=8080
WEBSOCKET_PORT=8081
HTTP_PORT=8000

# 性能配置
CACHE_SIZE=100
CONFIDENCE_THRESHOLD=0.65
REQUEST_TIMEOUT=30
MAX_RETRIES=3

# 安全配置
MAX_DAILY_LOSS=1000
MAX_POSITIONS=5
ENABLE_SAFETY_CHECKS=true
```

### EA参数配置
| 参数 | 默认值 | 说明 |
|------|--------|------|
| 通信模式 | AUTO | AUTO/SOCKET/FILE/WEBSOCKET |
| Socket地址 | 127.0.0.1 | 服务主机地址 |
| Socket端口 | 8080 | 服务端口 |
| WebSocket地址 | ws://127.0.0.1:8081 | WebSocket服务地址 |
| 连接超时 | 3000ms | Socket连接超时时间 |
| 接收超时 | 5000ms | 响应接收超时时间 |
| 最大重试次数 | 3 | 连接失败重试次数 |
| 故障转移阈值 | 3 | 连续失败后切换模式 |
| 显示面板 | true | 在图表显示信息面板 |
| 显示支撑阻力线 | true | 显示技术分析线 |

## 🔍 验证安装

### 验证1：服务启动状态
成功启动后应看到类似输出：
```
======================================================================
 🎯  MT5 AI交易系统 - V3.0 企业级增强版
 ======================================================================
 📊 配置信息:
   - 通信模式: AUTO
   - DeepSeek: ✅ 启用
   - 缓存大小: 100
   - 置信度阈值: 0.65
   - 请求超时: 30s
   - 服务ID: ai_trading_xxxxxxx
   - WebSocket地址: ws://127.0.0.1:8081
   - Socket地址: 127.0.0.1:8080
   - Web Dashboard: http://127.0.0.1:8000
```

### 验证2：Web监控仪表盘
访问 http://127.0.0.1:8000，应看到：
- 实时系统状态
- 通信模式信息
- 请求统计
- 性能指标

### 验证3：EA连接状态
MT5日志应显示：
```
✅ EA初始化完成
✅ 自动选择Socket模式（或文件模式）
📡 正在发送AI请求...
✅ 收到AI响应: BUY/SELL/HOLD
```

### 验证4：AI功能测试
运行测试脚本：
```powershell
python tools/test_deepseek.py
```
应看到AI成功响应市场分析。

## 🐛 故障排除

### 常见问题1：DeepSeek API连接失败
**症状**: 服务启动但AI调用失败
**解决方案**:
1. 检查 `.env` 文件中的 `DEEPSEEK_API_KEY`
2. 运行 `python tools/test_deepseek.py` 测试API
3. 确保网络可访问 `api.deepseek.com`
4. 检查API密钥余额和权限

### 常见问题2：Socket连接失败
**症状**: EA自动切换到文件模式
**解决方案**:
1. 确保Python服务正在运行：`python mt5_ai_service.py`
2. 检查防火墙是否阻止端口8080/8081
3. 验证EA参数中的主机和端口
4. 运行 `python tools/test_socket_connection.py`

### 常见问题3：EA不交易
**症状**: AI有建议但不执行交易
**解决方案**:
1. 检查MT5中的自动交易是否启用
2. 确认置信度阈值设置（默认0.65）
3. 检查账户是否有足够资金
4. 验证交易品种是否支持

### 常见问题4：Web仪表盘无法访问
**症状**: http://127.0.0.1:8000 无法打开
**解决方案**:
1. 确保服务已启动并显示Web Dashboard信息
2. 检查端口8000是否被其他程序占用
3. 尝试使用 `--http-port 8001` 更改端口

## 📈 下一步

### 基础使用
1. 观察AI交易建议
2. 监控Web仪表盘数据
3. 查看MT5日志中的交易记录

### 进阶配置
1. 调整AI提示词模板（`core/ai_engine.py`）
2. 修改技术指标参数
3. 自定义风险控制规则

### 性能优化
1. 根据硬件调整缓存大小
2. 优化通信模式配置
3. 设置自动重启和监控

---

> **提示**: 首次使用建议从**文件模式**开始，稳定后再切换到**自动模式**以获得最佳性能。