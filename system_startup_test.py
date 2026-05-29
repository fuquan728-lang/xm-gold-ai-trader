#!/usr/bin/env python3
"""
MT5 AI交易系统 - 系统启动与组件协调测试
一键测试系统启动、核心组件协调、通信验证
"""

import sys
import os
import time
import threading
import subprocess
import json
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

print("=" * 70)
print("MT5 AI交易系统 V4.0 - 系统启动与协调测试")
print("测试时间:", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
print("=" * 70)

test_results = []

def record_test(phase, name, success, message=""):
    """记录测试结果"""
    status = "[PASS]" if success else "[FAIL]"
    print(f"{status} [{phase}] {name}: {message}")
    test_results.append({
        "phase": phase,
        "name": name,
        "success": success,
        "message": message,
        "timestamp": datetime.now().isoformat()
    })
    return success

def test_config_system():
    """测试配置系统"""
    print("\n[阶段1] 配置系统检查...")
    try:
        from core.config import config
        record_test("配置", "配置系统导入", True, "成功导入核心配置")
        
        # 检查关键配置
        key_configs = [
            ("SOCKET_HOST", "127.0.0.1"),
            ("SOCKET_PORT", 8080),
            ("WEBSOCKET_PORT", 8081),
            ("HTTP_PORT", 8000),
            ("MQL5_DATA_PORT", 8083),
            ("MAX_CONCURRENT_CONNECTIONS", 10),
            ("CONNECTION_POOL_SIZE", 5)
        ]
        
        all_pass = True
        for key, expected in key_configs:
            if hasattr(config, key):
                actual = getattr(config, key)
                if str(actual) == str(expected):
                    record_test("配置", f"配置项 {key}", True, f"值正确: {actual}")
                else:
                    record_test("配置", f"配置项 {key}", False, f"值不匹配: 期望={expected}, 实际={actual}")
                    all_pass = False
            else:
                record_test("配置", f"配置项 {key}", False, "配置项不存在")
                all_pass = False
        
        # 检查端口冲突
        ports = [config.SOCKET_PORT, config.WEBSOCKET_PORT, config.HTTP_PORT, config.MQL5_DATA_PORT]
        if len(set(ports)) == len(ports):
            record_test("配置", "端口冲突检查", True, f"端口无冲突: {ports}")
        else:
            record_test("配置", "端口冲突检查", False, f"端口冲突: {ports}")
            all_pass = False
        
        return all_pass
        
    except Exception as e:
        record_test("配置", "配置系统检查", False, f"异常: {str(e)}")
        return False

def test_core_components():
    """测试核心组件"""
    print("\n[阶段2] 核心组件检查...")
    
    components_to_test = [
        ("异步优化器", "from core.async_optimizer import AsyncRateLimiter, AsyncOptimizer"),
        ("WebSocket处理器", "from core.websocket_handler_enhanced import EnhancedWebSocketHandler"),
        ("MQL5数据管理器", "from core.mql5_data import get_mql5_data_manager"),
        ("AI分析器", "from core.ai_engine import AIAnalyzer"),
        ("风险管理系统", "from core.risk_manager import get_risk_manager"),
        ("缓存系统", "from core.cache import global_cache, tiered_cache"),
        ("文件处理器", "from core.file_handler import file_handler"),
        ("HTTP仪表板", "from core.web_dashboard import WebDashboard"),
    ]
    
    all_pass = True
    for name, import_stmt in components_to_test:
        try:
            exec(import_stmt)
            record_test("组件", f"{name}导入", True, "模块导入成功")
        except Exception as e:
            record_test("组件", f"{name}导入", False, f"导入失败: {str(e)}")
            all_pass = False
    
    return all_pass

def test_service_integration():
    """测试服务集成"""
    print("\n[阶段3] 服务层集成检查...")
    
    try:
        from mt5_ai_service_optimized import get_async_ai_service
        
        service = get_async_ai_service()
        record_test("服务", "异步AI服务实例化", True, "服务实例化成功")
        
        # 检查核心组件集成
        integration_checks = [
            ("AI分析器", "ai_analyzer"),
            ("异步优化器", "async_optimizer"),
            ("MQL5数据管理器", "mql5_data_manager"),
            ("风险管理系统", "risk_manager"),
            ("缓存系统", "cache"),
        ]
        
        integrated_components = 0
        total_components = len(integration_checks)
        
        for name, attr in integration_checks:
            if hasattr(service, attr):
                instance = getattr(service, attr)
                if instance:
                    record_test("服务", f"{name}集成", True, f"{name}已集成并初始化")
                    integrated_components += 1
                else:
                    record_test("服务", f"{name}集成", False, f"{name}已定义但未初始化")
            else:
                record_test("服务", f"{name}集成", False, f"{name}属性不存在")
        
        integration_rate = (integrated_components / total_components * 100) if total_components > 0 else 0
        record_test("服务", "组件集成率", integration_rate >= 80, f"{integrated_components}/{total_components} 组件集成 ({integration_rate:.1f}%)")
        
        return integration_rate >= 80
        
    except Exception as e:
        record_test("服务", "服务集成检查", False, f"异常: {str(e)}")
        return False

def test_communication_modes():
    """测试通信模式"""
    print("\n[阶段4] 通信模式检查...")
    
    modes_to_test = [
        ("文件模式", "检查文件通信路径"),
        ("Socket模式", "检查Socket服务器配置"),
        ("WebSocket模式", "检查WebSocket服务器配置"),
        ("HTTP监控", "检查HTTP仪表板配置"),
    ]
    
    all_pass = True
    
    # 检查文件模式路径
    try:
        from core.file_handler import file_handler
        from core.config import config
        # 检查可能的文件路径
        possible_paths = config.get_possible_paths() if hasattr(config, 'get_possible_paths') else []
        if possible_paths and len(possible_paths) > 0:
            record_test("通信", "文件模式路径", True, f"发现 {len(possible_paths)} 个可能的文件路径")
        else:
            record_test("通信", "文件模式路径", False, "未找到可能的文件路径")
            all_pass = False
    except Exception as e:
        record_test("通信", "文件模式检查", False, f"异常: {str(e)}")
        all_pass = False
    
    # 检查Socket配置
    try:
        from core.config import config
        if config.SOCKET_PORT and 1024 <= config.SOCKET_PORT <= 65535:
            record_test("通信", "Socket端口配置", True, f"端口有效: {config.SOCKET_PORT}")
        else:
            record_test("通信", "Socket端口配置", False, f"端口无效: {config.SOCKET_PORT}")
            all_pass = False
    except Exception as e:
        record_test("通信", "Socket配置检查", False, f"异常: {str(e)}")
        all_pass = False
    
    # 检查WebSocket配置
    try:
        if config.WEBSOCKET_PORT and 1024 <= config.WEBSOCKET_PORT <= 65535:
            record_test("通信", "WebSocket端口配置", True, f"端口有效: {config.WEBSOCKET_PORT}")
        else:
            record_test("通信", "WebSocket端口配置", False, f"端口无效: {config.WEBSOCKET_PORT}")
            all_pass = False
    except Exception as e:
        record_test("通信", "WebSocket配置检查", False, f"异常: {str(e)}")
        all_pass = False
    
    # 检查HTTP监控
    try:
        if config.HTTP_PORT and 1024 <= config.HTTP_PORT <= 65535:
            record_test("通信", "HTTP监控端口", True, f"端口有效: {config.HTTP_PORT}")
        else:
            record_test("通信", "HTTP监控端口", False, f"端口无效: {config.HTTP_PORT}")
            all_pass = False
    except Exception as e:
        record_test("通信", "HTTP监控检查", False, f"异常: {str(e)}")
        all_pass = False
    
    return all_pass

def test_data_flow():
    """测试数据流"""
    print("\n[阶段5] 数据流模拟测试...")
    
    try:
        # 模拟MQL5数据 - 使用正确的数据结构
        test_mql5_data = {
        "account": {
            "balance": 15000.0,
            "equity": 15088.22,
            "margin": 507.72,
            "margin_free": 14380.50,
            "margin_level": 1791.8,
            "profit": 88.22,
            "currency": "USD",
            "leverage": 100,
            "account": 123456,
            "server": "XMGlobal-Demo"
        },
        "positions": [
            {"symbol": "EURUSD", "volume": 0.10, "type": "BUY", "open_price": 1.0850, "current_price": 1.0855, "profit": 5.0},
            {"symbol": "GOLD_", "volume": 0.05, "type": "SELL", "open_price": 2380.0, "current_price": 2385.5, "profit": -27.5}
        ],
        "timestamp": datetime.now().isoformat()
    }
        
        # 更新MQL5数据
        from core.mql5_data import get_mql5_data_manager
        mql5_manager = get_mql5_data_manager()
        # 使用正确的update_from_json方法
        mql5_manager.update_from_json(test_mql5_data)
        
        account_data = mql5_manager.get_dashboard_data()
        if account_data and "account_balance" in account_data:
            record_test("数据流", "MQL5数据更新", True, f"数据更新成功 (余额: ${account_data.get('account_balance', 0):.2f})")
        else:
            record_test("数据流", "MQL5数据更新", False, "数据更新失败")
            return False
        
        # 模拟市场数据
        test_market_data = {
            "symbol": "GOLD_",
            "bid": 2385.50,
            "ask": 2386.00,
            "spread": 0.50,
            "timestamp": datetime.now().isoformat(),
            "indicators": {
                "ema_50": 2390.20,
                "ema_200": 2375.80,
                "rsi": 48.5,
                "macd": {"value": -2.5, "signal": -1.8, "histogram": -0.7}
            }
        }
        
        # AI分析
        from core.ai_engine import AIAnalyzer
        analyzer = AIAnalyzer()
        analysis_result = analyzer.analyze_market_data(test_market_data)
        
        if analysis_result and "action" in analysis_result:
            record_test("数据流", "AI分析", True, f"分析完成: {analysis_result.get('action', '未知')}")
        else:
            record_test("数据流", "AI分析", False, "AI分析失败")
            return False
        
        # 增强分析（含账户上下文）
        enhanced_result = analyzer.analyze_market_data_enhanced(test_market_data)
        if enhanced_result and "action" in enhanced_result:
            prompt = enhanced_result.get("prompt", "")
            if "账户" in prompt or "持仓" in prompt or "balance" in prompt.lower():
                record_test("数据流", "账户上下文集成", True, "账户上下文成功集成")
            else:
                record_test("数据流", "账户上下文集成", False, "账户上下文未找到")
        else:
            record_test("数据流", "增强分析", False, "增强分析失败")
            return False
        
        # 风险评估
        from core.risk_manager import get_risk_manager
        risk_manager = get_risk_manager()
        
        test_trade = {
            "symbol": "GOLD_",
            "action": "SELL",
            "lot_size": 0.01,
            "stop_loss": 2400.0,
            "take_profit": 2350.0,
            "confidence": 0.65,
            "risk_per_trade_percent": 1.5
        }
        
        risk_assessment = risk_manager.assess_trade_risk(test_trade)
        if risk_assessment and hasattr(risk_assessment, 'status'):
            record_test("数据流", "风险评估", True, f"风险评估: {risk_assessment.status}")
        else:
            record_test("数据流", "风险评估", False, "风险评估失败")
            return False
        
        return True
        
    except Exception as e:
        record_test("数据流", "数据流测试", False, f"异常: {str(e)}")
        return False

def main():
    """主测试函数"""
    print("开始系统启动与协调测试...")
    print("-" * 70)
    
    # 运行所有测试阶段
    phases = [
        ("配置系统", test_config_system),
        ("核心组件", test_core_components),
        ("服务集成", test_service_integration),
        ("通信模式", test_communication_modes),
        ("数据流", test_data_flow),
    ]
    
    phase_results = []
    
    for phase_name, test_func in phases:
        print(f"\n>>> 开始测试阶段: {phase_name}")
        try:
            success = test_func()
            phase_results.append((phase_name, success))
            print(f"<<< {phase_name}测试: {'通过' if success else '失败'}")
        except Exception as e:
            print(f"<<< {phase_name}测试异常: {str(e)}")
            phase_results.append((phase_name, False))
    
    # 汇总结果
    print("\n" + "=" * 70)
    print("测试结果汇总")
    print("=" * 70)
    
    total_phases = len(phase_results)
    passed_phases = sum(1 for _, success in phase_results if success)
    failed_phases = total_phases - passed_phases
    
    total_tests = len(test_results)
    passed_tests = sum(1 for r in test_results if r["success"])
    failed_tests = total_tests - passed_tests
    
    print(f"测试阶段: {passed_phases}/{total_phases} 通过")
    print(f"详细测试: {passed_tests}/{total_tests} 通过")
    
    print("\n各阶段结果:")
    for phase_name, success in phase_results:
        status = "[PASS]" if success else "[FAIL]"
        print(f"  {status} {phase_name}")
    
    print("\n" + "=" * 70)
    if failed_phases == 0:
        print("[SUCCESS] 所有测试阶段通过！系统组件协调工作正常。")
        print("          系统已准备好一键启动和部署。")
        return True
    elif passed_phases >= 3:
        print("[WARN] 大多数测试通过，系统基本可用。")
        print("       建议修复少量问题后再部署。")
        return True
    else:
        print("[ERROR] 多个测试阶段失败，需要修复后再部署。")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)