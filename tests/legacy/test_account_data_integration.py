#!/usr/bin/env python3
"""
MT5 AI Trading System - 账户数据推送集成测试
测试新创建的AI_Trader_V3.2_Integrated.mq5 EA的功能集成性
"""

import os
import sys
import json
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_ea_file_integrity():
    """测试EA文件的完整性"""
    print("=" * 60)
    print("账户数据推送集成测试")
    print("=" * 60)
    
    # 检查EA文件是否存在
    ea_file = "MQL5/Experts/AI_Trader_V3.2_Integrated.mq5"
    if not os.path.exists(ea_file):
        print(f"[ERROR] EA文件不存在: {ea_file}")
        return False
    
    print(f"[OK] EA文件存在: {ea_file}")
    
    # 读取文件内容
    with open(ea_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 检查关键功能部分
    checks = [
        ("账户数据推送输入参数", "input bool   InpPushAccountData"),
        ("账户数据推送间隔", "input int    InpAccountDataInterval"),
        ("账户数据推送主机", "input string InpAccountDataHost"),
        ("账户数据推送端口", "input int    InpAccountDataPort"),
        ("账户数据推送连接函数", "bool InitAccountDataConnection()"),
        ("账户数据推送JSON构建", "string BuildAccountDataJson()"),
        ("账户数据推送执行", "void PushAccountDataToServer()"),
        ("账户状态变量", "bool m_account_data_enabled"),
        ("Socket句柄", "int m_account_data_socket"),
        ("最后推送时间", "datetime m_last_account_data_push"),
        ("初始化调用", "if(!InitAccountDataConnection())"),
        ("OnTick推送调用", "PushAccountDataToServer()"),
        ("OnDeinit清理", "SocketClose(m_account_data_socket)"),
        ("安全特性参数", "input bool   InpReversePosition"),
        ("每日亏损限制", "input double InpMaxDailyLoss"),
        ("风险检查", "input bool   InpEnableRiskCheck"),
        ("异步状态机", "enum RequestState"),
        ("指标缓存", "struct IndicatorCache"),
        ("性能统计", "struct PerfStats"),
    ]
    
    passed = 0
    failed = 0
    
    for check_name, check_string in checks:
        if check_string in content:
            print(f"[OK] {check_name}: [PASS]")
            passed += 1
        else:
            print(f"[ERROR] {check_name}: [FAIL] (未找到: {check_string})")
            failed += 1
    
    print("\n" + "=" * 60)
    print("完整性检查结果:")
    print(f"  通过: {passed}")
    print(f"  失败: {failed}")
    print(f"  总计: {passed + failed}")
    print(f"  通过率: {passed/(passed+failed)*100:.1f}%")
    
    return failed == 0

def test_mql5_data_manager():
    """测试MQL5数据管理器"""
    print("\n" + "=" * 60)
    print("MQL5数据管理器测试")
    print("=" * 60)
    
    try:
        from core.mql5_data import MQL5DataManager, AccountInfo, Position, TradeHistory
        
        # 测试数据类
        account = AccountInfo(
            balance=10000.0,
            equity=10500.0,
            margin=500.0,
            margin_free=9500.0,
            margin_level=2100.0,
            profit=500.0,
            currency="USD",
            leverage=100,
            account=123456,
            server="XMGlobal-Demo"
        )
        
        position = Position(
            ticket=1234567,
            symbol="EURUSD",
            type="BUY",
            volume=0.01,
            open_time="2026-04-22 10:30:00",
            open_price=1.0850,
            sl=1.0820,
            tp=1.0900,
            current_price=1.0865,
            profit=15.0,
            swap=0.0,
            comment="AI trade"
        )
        
        history = TradeHistory(
            ticket=1234566,
            symbol="EURUSD",
            type="SELL",
            volume=0.01,
            open_time="2026-04-22 09:15:00",
            open_price=1.0860,
            close_time="2026-04-22 10:15:00",
            close_price=1.0850,
            profit=-10.0,
            swap=0.0,
            commission=0.0,
            comment="Previous trade"
        )
        
        print("[OK] 数据类定义完整")
        print(f"     AccountInfo: {account}")
        print(f"     Position: {position}")
        print(f"     TradeHistory: {history}")
        
        # 测试数据管理器
        manager = MQL5DataManager()
        print("[OK] MQL5数据管理器初始化成功")
        
        # 模拟JSON数据
        test_data = {
            "type": "mql5_data",
            "account": {
                "balance": 10000.0,
                "equity": 10500.0,
                "margin": 500.0,
                "margin_free": 9500.0,
                "margin_level": 2100.0,
                "profit": 500.0,
                "currency": "USD",
                "leverage": 100,
                "account": 123456,
                "server": "XMGlobal-Demo"
            },
            "positions": [
                {
                    "ticket": 1234567,
                    "symbol": "EURUSD",
                    "type": "BUY",
                    "volume": 0.01,
                    "open_time": "2026-04-22 10:30:00",
                    "open_price": 1.0850,
                    "sl": 1.0820,
                    "tp": 1.0900,
                    "current_price": 1.0865,
                    "profit": 15.0,
                    "swap": 0.0,
                    "comment": "AI trade"
                }
            ],
            "history": [
                {
                    "ticket": 1234566,
                    "symbol": "EURUSD",
                    "type": "SELL",
                    "volume": 0.01,
                    "open_time": "2026-04-22 09:15:00",
                    "open_price": 1.0860,
                    "close_time": "2026-04-22 10:15:00",
                    "close_price": 1.0850,
                    "profit": -10.0,
                    "swap": 0.0,
                    "commission": 0.0,
                    "comment": "Previous trade"
                }
            ]
        }
        
        # 测试更新功能
        success = manager.update_from_json(test_data)
        if success:
            print("[OK] JSON数据更新成功")
            print(f"     账户余额: {manager.account_info.balance}")
            print(f"     持仓数量: {len(manager.positions)}")
            print(f"     历史交易数量: {len(manager.trade_history)}")
            print(f"     最后更新时间: {manager.last_update}")
        else:
            print("[ERROR] JSON数据更新失败")
            return False
        
        return True
        
    except ImportError as e:
        print(f"[ERROR] 导入模块失败: {e}")
        return False
    except Exception as e:
        print(f"[ERROR] 测试过程中发生错误: {e}")
        return False

def test_json_format():
    """测试JSON数据格式"""
    print("\n" + "=" * 60)
    print("JSON数据格式测试")
    print("=" * 60)
    
    # 构建与EA相同的JSON结构
    json_data = {
        "type": "mql5_data",
        "account": {
            "balance": 10000.0,
            "equity": 10500.0,
            "margin": 500.0,
            "margin_free": 9500.0,
            "margin_level": 2100.0,
            "profit": 500.0,
            "currency": "USD",
            "leverage": 100,
            "account": 123456,
            "server": "XMGlobal-Demo"
        },
        "positions": [
            {
                "ticket": 1234567,
                "symbol": "EURUSD",
                "type": "BUY",
                "volume": 0.01,
                "open_time": "2026-04-22 10:30:00",
                "open_price": 1.0850,
                "sl": 1.0820,
                "tp": 1.0900,
                "current_price": 1.0865,
                "profit": 15.0,
                "swap": 0.0,
                "comment": "AI trade"
            }
        ],
        "history": []
    }
    
    try:
        # 序列化和反序列化测试
        json_str = json.dumps(json_data)
        print(f"[OK] JSON序列化成功，长度: {len(json_str)} 字节")
        
        parsed = json.loads(json_str)
        print(f"[OK] JSON反序列化成功")
        
        # 验证数据结构
        assert parsed["type"] == "mql5_data"
        assert parsed["account"]["balance"] == 10000.0
        assert parsed["account"]["currency"] == "USD"
        assert len(parsed["positions"]) == 1
        assert parsed["positions"][0]["symbol"] == "EURUSD"
        assert parsed["positions"][0]["type"] == "BUY"
        
        print("[OK] 数据结构验证通过")
        
        # 输出示例JSON（用于EA调试）
        print("\n[INFO] 示例JSON数据:")
        print(json.dumps(json_data, indent=2))
        
        return True
        
    except json.JSONDecodeError as e:
        print(f"[ERROR] JSON解析错误: {e}")
        return False
    except AssertionError as e:
        print(f"[ERROR] 数据验证失败: {e}")
        return False
    except Exception as e:
        print(f"[ERROR] 测试过程中发生错误: {e}")
        return False

def test_configuration():
    """测试配置系统"""
    print("\n" + "=" * 60)
    print("配置系统测试")
    print("=" * 60)
    
    try:
        from core.config import config
        
        # 检查关键配置项
        required_configs = [
            "SOCKET_HOST",
            "SOCKET_PORT", 
            "WEBSOCKET_HOST",
            "WEBSOCKET_PORT",
            "HTTP_PORT",
            "MQL5_DATA_PORT",
            "MQL5_DATA_HOST",
            "MAX_CONNECTIONS",
            "RATE_LIMIT_PER_SECOND",
            "REQUEST_TIMEOUT"
        ]
        
        missing = []
        for config_name in required_configs:
            if hasattr(config, config_name):
                value = getattr(config, config_name)
                print(f"[OK] {config_name}: {value}")
            else:
                print(f"[ERROR] {config_name}: 未定义")
                missing.append(config_name)
        
        if missing:
            print(f"\n[WARN] 缺失配置项: {len(missing)} 个")
            for m in missing:
                print(f"       - {m}")
            return False
        
        print("\n[OK] 所有必需配置项都存在")
        
        # 检查端口配置
        ports = {
            "SOCKET_PORT": config.SOCKET_PORT,
            "WEBSOCKET_PORT": config.WEBSOCKET_PORT,
            "HTTP_PORT": config.HTTP_PORT,
            "MQL5_DATA_PORT": config.MQL5_DATA_PORT
        }
        
        # 确保端口不冲突
        port_values = list(ports.values())
        if len(port_values) != len(set(port_values)):
            print("[ERROR] 端口配置冲突！")
            for name, port in ports.items():
                print(f"       {name}: {port}")
            return False
        
        print("[OK] 端口配置无冲突")
        
        return True
        
    except ImportError as e:
        print(f"[ERROR] 导入配置模块失败: {e}")
        return False
    except Exception as e:
        print(f"[ERROR] 配置测试过程中发生错误: {e}")
        return False

def generate_installation_guide():
    """生成安装和配置指南"""
    print("\n" + "=" * 60)
    print("AI_Trader_V3.2_Integrated 安装和配置指南")
    print("=" * 60)
    
    guide = """
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
"""
    
    print(guide)
    
    # 保存指南到文件
    guide_file = "AI_Trader_V3.2_Integrated_安装指南.md"
    with open(guide_file, 'w', encoding='utf-8') as f:
        f.write(guide)
    
    print(f"\n[INFO] 安装指南已保存到: {guide_file}")
    return True

def main():
    """主测试函数"""
    print("MT5 AI Trading System - 账户数据推送集成测试")
    print(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    
    results = []
    
    # 运行测试
    results.append(("EA文件完整性测试", test_ea_file_integrity()))
    results.append(("MQL5数据管理器测试", test_mql5_data_manager()))
    results.append(("JSON数据格式测试", test_json_format()))
    results.append(("配置系统测试", test_configuration()))
    
    # 生成安装指南
    generate_installation_guide()
    
    # 汇总结果
    print("\n" + "=" * 80)
    print("测试结果汇总")
    print("=" * 80)
    
    passed = 0
    total = len(results)
    
    for test_name, success in results:
        status = "[PASS]" if success else "[FAIL]"
        print(f"{status} {test_name}")
        if success:
            passed += 1
    
    print("\n" + "=" * 80)
    print(f"总测试数: {total}")
    print(f"通过数: {passed}")
    print(f"失败数: {total - passed}")
    print(f"通过率: {passed/total*100:.1f}%")
    
    if passed == total:
        print("\n[SUCCESS] 所有测试通过！AI_Trader_V3.2_Integrated 已成功集成账户数据推送功能。")
        print("   请按照安装指南编译和配置EA。")
        return 0
    else:
        print("\n[WARNING] 部分测试失败，请检查相关问题。")
        return 1

if __name__ == "__main__":
    sys.exit(main())