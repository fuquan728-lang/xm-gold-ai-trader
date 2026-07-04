# 📥 安装指南

> 详细安装步骤和系统要求

## 系统要求

### 硬件要求
- **CPU**: 双核2.0GHz以上（推荐四核）
- **内存**: 4GB以上（推荐8GB）
- **硬盘**: 至少1GB可用空间
- **网络**: 稳定的互联网连接

### 软件要求
- **操作系统**: Windows 10/11（推荐），Linux/macOS也支持
- **Python**: 3.8或更高版本（推荐3.9+）
- **MetaTrader 5**: 最新版本（Build 4000+）
- **数据库**: SQLite（已包含在Python中）

## 安装步骤

### 1. 获取源代码
```powershell
# 方法1：克隆仓库（如果使用Git）
git clone <仓库地址>
cd "XM Global MT5"

# 方法2：下载ZIP包
# 解压到任意目录，例如 D:\XM Global MT5\
```

### 2. 安装Python依赖
```powershell
# 进入项目目录
cd "XM Global MT5"

# 安装所有依赖（推荐使用虚拟环境）
pip install -r requirements.txt

# 如果遇到权限问题，可以尝试：
pip install --user -r requirements.txt
```

### 3. 配置环境变量
```powershell
# 复制环境变量模板
copy .env.example .env

# 使用文本编辑器打开.env文件
# 主要配置项：
#   USE_DEEPSEEK=true                   # 启用AI功能
#   DEEPSEEK_API_KEY=<set-in-system-environment>  # 必须设置
#   SOCKET_HOST=127.0.0.1              # 服务监听地址
#   SOCKET_PORT=8080                   # Socket端口
#   WEBSOCKET_PORT=8081                # WebSocket端口
#   HTTP_PORT=8000                     # Web仪表盘端口
```

### 4. 安装MT5 EA
1. **找到MT5数据文件夹**：
   - 在MT5中：文件 → 打开数据文件夹
   - 路径通常为：`C:\Users\<用户名>\AppData\Roaming\MetaQuotes\Terminal\<终端ID>\`

2. **复制EA文件**：
   - 推荐先将 `MQL5/Experts/XM_Gold_AI_Trader_SafetyGuard.mq5` 复制到 `MQL5/Experts/` 目录，只读监控，不下单
   - 需要自动交易时，使用 `MQL5/Experts/AI_Trader_V3.2_Integrated.mq5`，并保持默认 `InpAllowLiveTrading=false`、`InpRequireDemoAccount=true`
   - 不要使用 `AI_Trader_V2.1_Safe.mq5` 作为自动交易入口；该 Legacy EA 默认 `InpAllowOrderExecution=false`
   - `AI_Trader_Integrated_Socket.mq5` 是 Legacy/Archive，不作为新安装入口
   - 将 `MQL5/Include/` 中的头文件复制到对应目录（如果需要）

3. **编译EA**：
   - 在MT5中打开MetaEditor（F4）
   - 优先导航到 `Experts/XM_Gold_AI_Trader_SafetyGuard.mq5`
   - 点击编译按钮（F7）
   - 确认无错误信息

### 5. 验证安装
```powershell
# 测试Python环境
python --version
pip list | findstr deepseek

# 测试DeepSeek连接
python tools/test_deepseek.py

# 测试Socket服务
python tools/test_socket_connection.py
```

## 安装后配置

### 配置EA参数
在MT5图表上添加EA时，配置以下参数：

| 参数组 | 参数 | 推荐值 | 说明 |
|--------|------|--------|------|
| **通信设置** | 通信模式 | AUTO | 自动选择最佳模式 |
| | Socket地址 | 127.0.0.1 | 服务运行的主机 |
| | Socket端口 | 8080 | 服务端口 |
| | WebSocket地址 | ws://127.0.0.1:8081 | WebSocket服务地址 |
| **连接设置** | 连接超时 | 3000 | 连接等待时间(ms) |
| | 接收超时 | 5000 | 接收响应超时(ms) |
| | 最大重试次数 | 3 | 连接失败重试次数 |
| | 故障转移阈值 | 3 | 切换模式的失败次数 |
| **显示设置** | 显示面板 | true | 在图表显示信息 |
| | 显示支撑阻力线 | true | 显示技术分析线 |

### 配置服务启动选项
创建启动脚本 `start_service.bat`：
```batch
@echo off
cd /d "D:\搬家文件夹\XM Global MT5"
python mt5_ai_service.py --mode auto --log-file service.log
pause
```

## 高级安装

### 使用虚拟环境（推荐）
```powershell
# 创建虚拟环境
python -m venv venv

# 激活虚拟环境
# Windows:
venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 退出虚拟环境
deactivate
```

### 服务化安装（Windows）
```powershell
# 使用nssm将服务注册为Windows服务
# 下载nssm：https://nssm.cc/download
nssm install MT5AIService "D:\搬家文件夹\XM Global MT5\venv\Scripts\python.exe" "mt5_ai_service.py"
nssm set MT5AIService AppDirectory "D:\搬家文件夹\XM Global MT5"
nssm set MT5AIService AppStdout "D:\搬家文件夹\XM Global MT5\service.log"
nssm set MT5AIService AppStderr "D:\搬家文件夹\XM Global MT5\error.log"

# 启动服务
nssm start MT5AIService
```

### 多实例部署
```powershell
# 实例1（端口8080）
python mt5_ai_service.py --socket-port 8080 --websocket-port 8081 --http-port 8000

# 实例2（端口8082）
python mt5_ai_service.py --socket-port 8082 --websocket-port 8083 --http-port 8001
```

## 安装验证

### 验证步骤
1. **服务启动验证**：
   ```powershell
   python mt5_ai_service.py
   ```
   应看到V3.0启动横幅和配置信息。

2. **Web仪表盘验证**：
   - 浏览器访问 http://127.0.0.1:8000
   - 应看到实时监控界面

3. **EA连接验证**：
   - 在MT5图表添加EA
   - 查看MT5日志，应显示"✅ EA初始化完成"
   - 通信模式应为Socket或文件模式

4. **AI功能验证**：
   ```powershell
   python tools/test_deepseek.py
   ```
   应看到AI成功响应市场分析。

### 常见安装问题

#### 问题1：Python依赖安装失败
**解决方案**：
```powershell
# 升级pip
python -m pip install --upgrade pip

# 使用国内镜像源（如在中国）
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 或使用conda环境
conda create -n mt5ai python=3.9
conda activate mt5ai
pip install -r requirements.txt
```

#### 问题2：MT5编译错误
**解决方案**：
1. 确保MT5为最新版本
2. 检查MQL5头文件是否完整
3. 在MetaEditor中查看具体错误信息
4. 可能需要安装Visual C++ Redistributable

#### 问题3：服务启动但无法连接
**解决方案**：
1. 检查防火墙设置，允许端口8080、8081、8000
2. 验证EA参数中的主机地址和端口
3. 使用文件模式测试连接
4. 运行 `python tools/test_socket_connection.py`

## 卸载

### 完全卸载步骤
1. **停止服务**：
   ```powershell
   # 如果注册为Windows服务
   nssm stop MT5AIService
   nssm remove MT5AIService confirm
   ```

2. **删除文件**：
   - 删除项目目录
   - 删除MT5中的EA文件
   - 删除数据库文件 `data/trading.db`

3. **清理环境**：
   ```powershell
   # 删除虚拟环境
   rmdir /s venv
   
   # 卸载Python包
   pip uninstall -r requirements.txt -y
   ```

---

> **提示**：首次安装建议从**文件模式**开始测试，稳定后再切换到**自动模式**。
