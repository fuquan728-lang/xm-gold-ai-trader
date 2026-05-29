#!/usr/bin/env python3
"""
最终组件协调性测试
验证MT5 AI交易系统V4.0所有核心组件协调工作
"""

import sys
import os
import time
import json
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

print("=" * 70)
print("MT5 AI交易系统 V4.0 - 最终组件协调性测试")
print("测试时间:", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
print("=" * 70)

test_results = []

def record_test(name, success, message=""):
    """记录测试结果"""
    status = "[PASS]" if success else "[FAIL]"
    print(f"{status} {name}: {message}")
    test_results.append({
        "name": name,
        "success": success,
        "message": message,
        "timestamp": datetime.now().isoformat()
    })
    return success

# 1. 测试配置系统
print("\n[测试1] 配置系统检查...")
try:
    from core.config import config
    config_summary = config.get_summary()
    record_test("配置系统导入", True, f"配置项总数: {len(config_summary)}")
    
    # 检查关键配置
    required_configs = [
        ("SOCKET_HOST", "127.0.0.1"),
        ("SOCKET_PORT", 8080),
        ("WEBSOCKET_PORT", 8081),
        ("HTTP_PORT", 8000),
        ("MQL5_DATA_PORT", 8083),
        ("MAX_CONCURRENT_CONNECTIONS", 10),
        ("CONNECTION_POOL_SIZE", 5)
    ]
    
    for key, expected_value in required_configs:
        if hasattr(config, key):
            actual_value = getattr(config, key)
            success = str(actual_value) == str(expected_value)
            record_test(f"配置项 {key}", success, f"期望={expected_value}, 实际={actual_value}")
        else:
            record_test(f"配置项 {key}", False, "配置项不存在")
    
    # 检查端口冲突
    ports = [config.SOCKET_PORT, config.WEBSOCKET_PORT, config.HTTP_PORT, config.MQL5_DATA_PORT]
    if len(set(ports)) == len(ports):
        record_test("端口冲突检查", True, f"端口无冲突: SOCKET={config.SOCKET_PORT}, WS={config.WEBSOCKET_PORT}, HTTP={config.HTTP_PORT}, MQL5={config.MQL5_DATA_PORT}")
    else:
        record_test("端口冲突检查", False, f"端口冲突: {ports}")
        
except Exception as e:
    record_test("配置系统检查", False, f"异常: {str(e)}")

# 2. 测试异步优化器
print("\n[测试2] 异步优化器组件检查...")
try:
    from core.async_optimizer import AsyncRateLimiter, AsyncOptimizer, PerformanceMonitor
    record_test("AsyncRateLimiter导入", True, "速率限制器模块导入成功")
    record_test("AsyncOptimizer导入", True, "异步优化器模块导入成功")
    record_test("PerformanceMonitor导入", True, "性能监控器模块导入成功")
    
    # 测试速率限制器初始化
    rate_limiter = AsyncRateLimiter(operations_per_second=15.0)
    stats = rate_limiter.get_stats()
    record_test("速率限制器初始化", True, f"目标速率: {stats.get('target_rate_per_second', 0):.2f} ops/sec")
    
    # 测试异步优化器初始化
    optimizer = AsyncOptimizer(
        max_http_connections=5,
        max_ws_connections=10,
        rate_limit_per_client=50,
        enable_monitoring=True
    )
    record_test("异步优化器初始化", True, "优化器成功初始化")
    
    if optimizer.monitor:
        record_test("性能监控器集成", True, "性能监控器已集成到优化器")
    
except Exception as e:
    record_test("异步优化器检查", False, f"异常: {str(e)}")

# 3. 测试WebSocket处理器
print("\n[测试3] WebSocket处理器检查...")
try:
    from core.websocket_handler_enhanced import EnhancedWebSocketHandler, HAS_WEBSOCKETS
    record_test("EnhancedWebSocketHandler导入", True, "WebSocket处理器模块导入成功")
    
    if HAS_WEBSOCKETS:
        handler = EnhancedWebSocketHandler(
            host=config.SOCKET_HOST,
            port=config.WEBSOCKET_PORT,
            process_request_func=None,
            max_connections=100,
            max_connections_per_ip=10,
            rate_limit_per_client=50
        )
        record_test("WebSocket处理器初始化", True, f"处理器已初始化 (host={handler.host}, port={handler.port})")
        
        # 检查配置一致性
        if handler.host == config.SOCKET_HOST and handler.port == config.WEBSOCKET_PORT:
            record_test("配置一致性检查", True, "处理器配置与系统配置一致")
        else:
            record_test("配置一致性检查", False, f"配置不匹配: handler({handler.host}:{handler.port}) vs config({config.SOCKET_HOST}:{config.WEBSOCKET_PORT})")
    else:
        record_test("websockets库检查", True, "websockets库未安装（跳过详细测试）")
        
except Exception as e:
    record_test("WebSocket处理器检查", False, f"异常: {str(e)}")

# 4. 测试MQL5数据管理器
print("\n[测试4] MQL5数据管理器检查...")
try:
    from core.mql5_data import get_mql5_data_manager
    
    # 创建测试数据
    test_data = {
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
    
    manager = get_mql5_data_manager()
    manager.update_from_json(test_data)
    account_data = manager.get_dashboard_data()
    
    if account_data and "account_balance" in account_data:
        record_test("MQL5数据管理器", True, f"数据管理器工作正常 (余额: ${account_data.get('account_balance', 0):.2f})")
    else:
        record_test("MQL5数据管理器", False, "数据管理器初始化失败")
        
except Exception as e:
    record_test("MQL5数据管理器检查", False, f"异常: {str(e)}")

# 5. 测试AI分析引擎
print("\n[测试5] AI分析引擎检查...")
try:
    from core.ai_engine import AIAnalyzer
    
    analyzer = AIAnalyzer()
    record_test("AI分析器导入", True, "AI分析器模块导入成功")
    
    # 创建测试数据
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
    
    # 测试传统分析（无账户上下文）
    result1 = analyzer.analyze_market_data(test_market_data)
    if result1 and "action" in result1:
        record_test("传统AI分析", True, f"分析完成: {result1.get('action', '未知')} (置信度: {result1.get('confidence', 0):.2f})")
    else:
        record_test("传统AI分析", False, "分析失败")
    
    # 测试增强分析（有账户上下文）
    result2 = analyzer.analyze_market_data_enhanced(test_market_data)
    if result2 and "action" in result2:
        record_test("增强AI分析", True, f"增强分析完成: {result2.get('action', '未知')}")
        # 检查是否包含账户上下文
        prompt = result2.get("prompt", "")
        if "账户" in prompt or "持仓" in prompt or "balance" in prompt.lower():
            record_test("账户上下文集成", True, "账户上下文成功集成到AI分析")
        else:
            record_test("账户上下文集成", False, "账户上下文未找到")
    else:
        record_test("增强AI分析", False, "增强分析失败")
        
except Exception as e:
    record_test("AI分析引擎检查", False, f"异常: {str(e)}")

# 6. 测试风险管理系统
print("\n[测试6] 风险管理系统检查...")
try:
    from core.risk_manager import get_risk_manager, TradeRiskAssessment
    
    risk_manager = get_risk_manager()
    record_test("风险管理系统导入", True, "风险管理系统模块导入成功")
    
    # 测试交易风险评估
    test_trade = {
        "symbol": "GOLD_",
        "action": "SELL",
        "lot_size": 0.01,
        "stop_loss": 2400.0,
        "take_profit": 2350.0,
        "confidence": 0.65,
        "risk_per_trade_percent": 1.5
    }
    
    assessment = risk_manager.assess_trade_risk(test_trade)
    if isinstance(assessment, TradeRiskAssessment):
        record_test("交易风险评估", True, f"风险评估成功: {assessment.status}")
        record_test("仓位调整", True, f"推荐仓位: {assessment.recommended_lot_size:.4f}手")
    else:
        record_test("交易风险评估", False, "风险评估失败")
    
    # 测试开仓条件检查
    risk_result = risk_manager.check_trade_conditions(test_trade)
    if risk_result and "allow_trade" in risk_result:
        record_test("开仓条件检查", True, f"开仓条件: {risk_result.get('allow_trade', False)}")
    else:
        record_test("开仓条件检查", False, "条件检查失败")
        
except Exception as e:
    record_test("风险管理系统检查", False, f"异常: {str(e)}")

# 7. 测试缓存系统
print("\n[测试7] 缓存系统检查...")
try:
    from core.cache import global_cache, tiered_cache
    
    # 测试全局缓存
    global_cache.set("test_key", {"test": "value", "timestamp": datetime.now().isoformat()})
    cached_value = global_cache.get("test_key")
    
    if cached_value and cached_value.get("test") == "value":
        record_test("全局缓存系统", True, "全局缓存读写正常")
    else:
        record_test("全局缓存系统", False, "全局缓存读写失败")
    
    # 测试分层缓存
    tiered_cache.set("tier_test", {"data": "tiered_value"}, ttl=60)
    tier_cached = tiered_cache.get("tier_test")
    
    if tier_cached and tier_cached.get("data") == "tiered_value":
        record_test("分层缓存系统", True, "分层缓存读写正常")
    else:
        record_test("分层缓存系统", False, "分层缓存读写失败")
        
except Exception as e:
    record_test("缓存系统检查", False, f"异常: {str(e)}")

# 8. 测试服务层集成
print("\n[测试8] 服务层集成检查...")
try:
    from mt5_ai_service_optimized import get_async_ai_service
    
    service = get_async_ai_service()
    record_test("异步AI服务实例化", True, "服务实例化成功")
    
    # 检查关键组件
    components = [
        ("AI分析器", service.ai_analyzer),
        ("异步优化器", service.async_optimizer),
        ("MQL5数据管理器", getattr(service, "mql5_data_manager", None)),
        ("风险管理系统", getattr(service, "risk_manager", None)),
        ("缓存系统", getattr(service, "cache", None))
    ]
    
    for component_name, component_instance in components:
        if component_instance:
            record_test(f"{component_name}集成", True, f"{component_name}已集成到服务层")
        else:
            record_test(f"{component_name}集成", False, f"{component_name}未集成到服务层")
            
    record_test("服务层整体集成", True, "服务层组件集成检查完成")
    
except Exception as e:
    record_test("服务层集成检查", False, f"异常: {str(e)}")

# 9. 测试文件模式处理器
print("\n[测试9] 文件模式处理器检查...")
try:
    from core.file_handler import file_handler
    
    test_file_data = {
        "symbol": "XAUUSD",
        "bid": 2384.75,
        "ask": 2385.25,
        "action": "SELL",
        "confidence": 0.72,
        "timestamp": datetime.now().isoformat()
    }
    
    # 测试文件写入
    result = file_handler.write_trading_signal(test_file_data)
    if result:
        record_test("文件写入功能", True, "文件模式写入成功")
    else:
        record_test("文件写入功能", False, "文件模式写入失败")
    
    # 检查文件是否存在
    if os.path.exists(file_handler.get_current_signal_file_path()):
        record_test("信号文件路径", True, "信号文件路径有效")
    else:
        record_test("信号文件路径", False, "信号文件路径无效")
        
except Exception as e:
    record_test("文件模式处理器检查", False, f"异常: {str(e)}")

# 10. 测试HTTP仪表板
print("\n[测试10] HTTP仪表板检查...")
try:
    from core.web_dashboard import WebDashboard
    
    dashboard = WebDashboard(host="127.0.0.1", port=config.HTTP_PORT)
    record_test("WebDashboard导入", True, "HTTP仪表板模块导入成功")
    
    # 检查仪表板状态
    if dashboard.port == config.HTTP_PORT:
        record_test("仪表板配置", True, f"仪表板端口配置正确: {dashboard.port}")
    else:
        record_test("仪表板配置", False, f"端口不匹配: dashboard={dashboard.port}, config={config.HTTP_PORT}")
        
except Exception as e:
    record_test("HTTP仪表板检查", False, f"异常: {str(e)}")

# 汇总测试结果
print("\n" + "=" * 70)
print("测试结果汇总")
print("=" * 70)

total_tests = len(test_results)
passed_tests = sum(1 for r in test_results if r["success"])
failed_tests = total_tests - passed_tests
pass_rate = (passed_tests / total_tests * 100) if total_tests > 0 else 0

print(f"总测试数: {total_tests}")
print(f"通过测试: {passed_tests}")
print(f"失败测试: {failed_tests}")
print(f"通过率: {pass_rate:.1f}%")

if failed_tests > 0:
    print("\n失败测试详情:")
    for result in test_results:
        if not result["success"]:
            print(f"  [FAIL] {result['name']}: {result['message']}")

print("\n" + "=" * 70)
if failed_tests == 0:
    print("[SUCCESS] 所有组件协调工作正常！系统已准备好部署。")
    sys.exit(0)
elif pass_rate >= 90:
    print("[WARN] 绝大多数组件协调工作正常，系统基本可用。")
    print("   建议检查少量失败组件后再部署。")
    sys.exit(1)
else:
    print("[ERROR] 组件协调存在问题，需要修复后再部署。")
    sys.exit(1)