#!/usr/bin/env python3
"""
检查核心组件协调性
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

print("检查核心组件协调性...")

# 1. 检查配置系统
try:
    from core.config import config
    print("[OK] 配置系统导入成功")
    print(f"  关键配置:")
    print(f"    SOCKET_PORT: {getattr(config, 'SOCKET_PORT', '未定义')}")
    print(f"    WEBSOCKET_PORT: {getattr(config, 'WEBSOCKET_PORT', '未定义')}")
    print(f"    HTTP_PORT: {getattr(config, 'HTTP_PORT', '未定义')}")
    print(f"    MQL5_DATA_PORT: {getattr(config, 'MQL5_DATA_PORT', '未定义')}")
except Exception as e:
    print(f"[FAIL] 配置系统导入失败: {e}")

# 2. 检查异步优化器
try:
    from core.async_optimizer import AsyncRateLimiter, AsyncOptimizer
    print("[OK] 异步优化器模块导入成功")
    
    rate_limiter = AsyncRateLimiter(operations_per_second=15.0)
    print(f"[OK] 速率限制器初始化成功: {rate_limiter.get_stats().get('target_rate_per_second', 0)} ops/sec")
    
    optimizer = AsyncOptimizer(max_http_connections=5, max_ws_connections=10, rate_limit_per_client=50, enable_monitoring=True)
    print("[OK] 异步优化器初始化成功")
    
except Exception as e:
    print(f"[FAIL] 异步优化器检查失败: {e}")

# 3. 检查WebSocket处理器
try:
    from core.websocket_handler_enhanced import EnhancedWebSocketHandler, HAS_WEBSOCKETS
    print("[OK] WebSocket处理器模块导入成功")
    
    if HAS_WEBSOCKETS:
        handler = EnhancedWebSocketHandler(host="127.0.0.1", port=8081, process_request_func=None, max_connections=100, max_connections_per_ip=10, rate_limit_per_client=50)
        print(f"[OK] WebSocket处理器初始化成功 (port={handler.port})")
    else:
        print("[WARN] websockets库未安装")
        
except Exception as e:
    print(f"[FAIL] WebSocket处理器检查失败: {e}")

# 4. 检查MQL5数据管理器
try:
    from core.mql5_data import get_mql5_data_manager
    manager = get_mql5_data_manager()
    print("[OK] MQL5数据管理器导入成功")
except Exception as e:
    print(f"[FAIL] MQL5数据管理器检查失败: {e}")

# 5. 检查AI分析引擎
try:
    from core.ai_engine import AIAnalyzer
    analyzer = AIAnalyzer()
    print("[OK] AI分析器导入成功")
except Exception as e:
    print(f"[FAIL] AI分析器检查失败: {e}")

# 6. 检查风险管理系统
try:
    from core.risk_manager import get_risk_manager
    risk_manager = get_risk_manager()
    print("[OK] 风险管理系统导入成功")
except Exception as e:
    print(f"[FAIL] 风险管理系统检查失败: {e}")

# 7. 检查缓存系统
try:
    from core.cache import global_cache, tiered_cache
    print("[OK] 缓存系统导入成功")
except Exception as e:
    print(f"[FAIL] 缓存系统检查失败: {e}")

# 8. 检查AI服务
try:
    from mt5_ai_service import get_ai_service
    service = get_ai_service()
    print("[OK] AI服务实例化成功")
    
    # 检查关键属性
    components = [
        ("AI分析器", "ai_analyzer"),
        ("数据验证器", "validator"),
        ("指标分析器", "indicator_analyzer"),
        ("权重优化器", "weight_optimizer")
    ]
    
    for name, attr in components:
        if hasattr(service, attr) and getattr(service, attr):
            print(f"  [OK] {name}已集成到服务")
        else:
            print(f"  [WARN] {name}未集成或未初始化")
            
except Exception as e:
    print(f"[FAIL] 异步AI服务检查失败: {e}")

print("\n核心组件检查完成！")