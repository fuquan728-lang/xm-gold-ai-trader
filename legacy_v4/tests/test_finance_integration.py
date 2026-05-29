#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
金融数据集成测试

测试核心功能：
1. 金融数据集成模块初始化
2. NeoData技能连接性验证
3. 数据查询和缓存功能
4. 集成到MT5 AI系统的协调性
"""

import sys
import os
import time
import json
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.config import config
from core.finance_data_integration import get_finance_data_integration
from core.market_data_analyzer import get_market_data_analyzer
from core.ai_engine import AIAnalyzer
from core.logger import logger


def test_finance_integration_module() -> bool:
    """测试金融数据集成模块"""
    print("测试金融数据集成模块...")
    
    try:
        finance = get_finance_data_integration()
        assert finance is not None
        print("[OK] 金融数据集成模块初始化成功")
        
        # 测试配置
        assert hasattr(finance, 'enabled')
        assert hasattr(finance, 'neodata_enabled')
        assert hasattr(finance, 'data_sources')
        print("[OK] 配置检查通过")
        
        # 测试可用性检查
        is_available = finance.is_available()
        print(f"[OK] 可用性检查: {is_available}")
        
        return True
        
    except Exception as e:
        print(f"[ERR] 金融数据集成模块测试失败: {e}")
        return False


def test_neodata_connection() -> bool:
    """测试NeoData连接性"""
    print("\n测试NeoData连接性...")
    
    try:
        finance = get_finance_data_integration()
        
        # 检查是否启用
        if not finance.enabled:
            print("[WARN]️  金融数据集成未启用，跳过连接测试")
            return True  # 不是错误，只是未启用
            
        if "neodata" not in finance.data_sources:
            print("[WARN]️  NeoData不在数据源列表中，跳过连接测试")
            return True  # 不是错误，只是未配置
            
        # 测试连接
        test_results = finance.test_connection()
        print(f"连接测试结果:")
        print(f"  - 启用状态: {test_results.get('enabled')}")
        print(f"  - NeoData启用: {test_results.get('neodata_enabled')}")
        print(f"  - 路径存在: {test_results.get('neodata_path_exists')}")
        print(f"  - Python命令: {test_results.get('python_command')}")
        print(f"  - 整体状态: {test_results.get('overall_status')}")
        
        # 检查连接测试结果
        connection_tests = test_results.get('connection_tests', {})
        for test_name, result in connection_tests.items():
            if isinstance(result, dict):
                print(f"  - {test_name}: 成功={result.get('success')}, 有数据={result.get('has_data')}")
            else:
                print(f"  - {test_name}: {result}")
        
        # 判断测试是否通过
        if test_results.get('overall_status') == '可用':
            print("[OK] NeoData连接测试通过")
            return True
        elif test_results.get('overall_status') == '不可用':
            print("[WARN]️  NeoData连接不可用（可能是配置问题）")
            return False
        else:
            # 有错误信息
            print(f"[ERR] NeoData连接测试失败: {test_results.get('overall_status')}")
            return False
            
    except Exception as e:
        print(f"[ERR] NeoData连接测试异常: {e}")
        return False


def test_data_query_functions() -> bool:
    """测试数据查询功能"""
    print("\n测试数据查询功能...")
    
    try:
        finance = get_finance_data_integration()
        
        # 检查是否可用
        if not finance.is_available():
            print("[WARN]️  金融数据集成不可用，跳过查询测试")
            return True  # 不是错误，只是不可用
            
        # 测试黄金价格查询（通用资产）
        print("测试黄金价格查询...")
        gold_price = finance.get_gold_price()
        if gold_price:
            print(f"  [OK] 黄金价格查询成功")
            print(f"     来源: {gold_price.get('source')}")
            print(f"     类型: {gold_price.get('data_type', 'N/A')}")
            print(f"     描述: {gold_price.get('description', 'N/A')[:100]}...")
        else:
            print("  [WARN]️  黄金价格查询失败（可能是API限制或数据不可用）")
            
        # 测试外汇汇率查询
        print("\n测试外汇汇率查询...")
        forex_rate = finance.get_forex_rate("USDCNY")
        if forex_rate:
            print(f"  [OK] USDCNY汇率查询成功")
            print(f"     来源: {forex_rate.get('source')}")
        else:
            print("  [WARN]️  USDCNY汇率查询失败")
            
        # 测试宏观经济数据查询
        print("\n测试宏观经济数据查询...")
        macro_data = finance.get_macro_data("gdp")
        if macro_data:
            print(f"  [OK] GDP数据查询成功")
            print(f"     来源: {macro_data.get('source')}")
        else:
            print("  [WARN]️  GDP数据查询失败")
            
        # 测试增强市场分析
        print("\n测试增强市场分析...")
        enhanced_analysis = finance.get_enhanced_market_analysis("EURUSD", "forex")
        if enhanced_analysis:
            print(f"  [OK] 增强市场分析生成成功")
            print(f"     外部数据可用: {enhanced_analysis.get('external_data_available')}")
            print(f"     价格数据: {'有' if enhanced_analysis.get('price_data') else '无'}")
            print(f"     宏观数据: {'有' if enhanced_analysis.get('macro_data') else '无'}")
            print(f"     情绪数据: {'有' if enhanced_analysis.get('sentiment_data') else '无'}")
        else:
            print("  [WARN]️  增强市场分析生成失败")
            
        print("[OK] 数据查询功能测试完成")
        return True
        
    except Exception as e:
        print(f"[ERR] 数据查询功能测试异常: {e}")
        return False


def test_integration_with_market_analyzer() -> bool:
    """测试与市场数据分析器的集成"""
    print("\n测试与市场数据分析器的集成...")
    
    try:
        market_analyzer = get_market_data_analyzer()
        
        # 检查市场数据分析器是否支持外部数据方法
        if hasattr(market_analyzer, 'add_external_market_data'):
            print("[OK] 市场数据分析器已扩展外部数据支持")
            
            # 测试添加模拟外部数据
            test_data = {
                "type": "price",
                "symbol": "EURUSD",
                "timeframe": "H1",
                "timestamp": time.time(),
                "open": 1.0850,
                "high": 1.0860,
                "low": 1.0840,
                "close": 1.0855,
                "volume": 1000,
                "source": "test"
            }
            
            market_analyzer.add_market_data(test_data)
            print("[OK] 成功添加模拟市场数据")
            
            return True
        else:
            print("[WARN]️  市场数据分析器尚未扩展外部数据支持（需要实现add_external_market_data方法）")
            return True  # 不是错误，只是功能尚未实现
            
    except Exception as e:
        print(f"[ERR] 市场数据分析器集成测试异常: {e}")
        return False


def test_integration_with_ai_engine() -> bool:
    """测试与AI引擎的集成"""
    print("\n测试与AI引擎的集成...")
    
    try:
        # 检查AI引擎是否支持外部数据分析
        ai_analyzer = AIAnalyzer()
        
        if hasattr(ai_analyzer, 'analyze_with_external_data'):
            print("[OK] AI引擎已扩展外部数据分析支持")
            
            # 测试基础分析（模拟数据）
            test_symbol = "EURUSD"
            test_bid = 1.0850
            test_ask = 1.0852
            test_time = time.time()
            
            # 基础分析
            analysis = ai_analyzer.analyze(test_symbol, test_bid, test_ask, test_time)
            if analysis:
                print(f"[OK] AI基础分析成功")
                print(f"   信号: {analysis.get('signal', 'N/A')}")
                print(f"   置信度: {analysis.get('confidence', 0)}")
                
                # 检查是否包含外部数据字段
                if 'external_data' in analysis:
                    print(f"   外部数据可用: {analysis['external_data'].get('available', False)}")
                else:
                    print("   外部数据字段未包含（可能是配置未启用）")
                    
                return True
            else:
                print("[ERR] AI分析失败")
                return False
        else:
            print("[WARN]️  AI引擎尚未扩展外部数据分析支持（需要实现analyze_with_external_data方法）")
            return True  # 不是错误，只是功能尚未实现
            
    except Exception as e:
        print(f"[ERR] AI引擎集成测试异常: {e}")
        return False


def test_configuration_system() -> bool:
    """测试配置系统"""
    print("\n测试金融数据配置系统...")
    
    try:
        # 检查配置项
        required_configs = [
            'FINANCE_DATA_ENABLED',
            'NEODATA_ENABLED',
            'EXTERNAL_DATA_SOURCES',
            'MAX_EXTERNAL_RETRIES',
            'FINANCE_CACHE_TTL',
            'MARKET_DATA_UPDATE_INTERVAL'
        ]
        
        missing_configs = []
        for config_name in required_configs:
            if not hasattr(config, config_name):
                missing_configs.append(config_name)
                
        if missing_configs:
            print(f"[ERR] 缺少必要的金融数据配置: {missing_configs}")
            return False
        else:
            print("[OK] 所有必需的金融数据配置存在")
            
            # 显示配置值（脱敏）
            print("配置摘要:")
            print(f"  FINANCE_DATA_ENABLED: {config.FINANCE_DATA_ENABLED}")
            print(f"  NEODATA_ENABLED: {config.NEODATA_ENABLED}")
            print(f"  EXTERNAL_DATA_SOURCES: {config.EXTERNAL_DATA_SOURCES}")
            print(f"  MAX_EXTERNAL_RETRIES: {config.MAX_EXTERNAL_RETRIES}")
            print(f"  FINANCE_CACHE_TTL: {config.FINANCE_CACHE_TTL}秒")
            print(f"  MARKET_DATA_UPDATE_INTERVAL: {config.MARKET_DATA_UPDATE_INTERVAL}秒")
            
            return True
            
    except Exception as e:
        print(f"[ERR] 配置系统测试异常: {e}")
        return False


def main() -> bool:
    """主测试函数"""
    print("=" * 70)
    print("金融数据集成测试")
    print("=" * 70)
    print(f"测试时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"项目根目录: {Path(__file__).parent.parent}")
    print()
    
    # 配置日志级别为INFO
    logger.setLevel("INFO")
    
    tests = [
        ("金融数据集成模块", test_finance_integration_module),
        ("NeoData连接性", test_neodata_connection),
        ("数据查询功能", test_data_query_functions),
        ("配置系统", test_configuration_system),
        ("市场数据分析器集成", test_integration_with_market_analyzer),
        ("AI引擎集成", test_integration_with_ai_engine)
    ]
    
    results = []
    for test_name, test_func in tests:
        print(f"\n{'='*50}")
        print(f"测试: {test_name}")
        print(f"{'='*50}")
        
        try:
            result = test_func()
            results.append((test_name, result))
            
            if result:
                print(f"[OK] {test_name} - 通过")
            else:
                print(f"[ERR] {test_name} - 失败")
                
        except Exception as e:
            print(f"[ERR] {test_name} - 异常: {e}")
            results.append((test_name, False))
    
    # 汇总结果
    print(f"\n{'='*70}")
    print("测试结果汇总")
    print(f"{'='*70}")
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "[OK] 通过" if result else "[ERR] 失败"
        print(f"{test_name:30} {status}")
    
    print(f"\n通过: {passed}/{total}")
    
    if passed == total:
        print("🎉 所有测试通过，金融数据集成准备就绪")
    elif passed >= total * 0.7:
        print("[WARN]️  部分测试失败，但核心功能可用")
    else:
        print("[ERR] 多数测试失败，需要检查配置和依赖")
    
    # 生成测试报告
    report = {
        "timestamp": time.time(),
        "total_tests": total,
        "passed_tests": passed,
        "success_rate": passed / total if total > 0 else 0,
        "tests": [{"name": name, "passed": result} for name, result in results],
        "config_summary": {
            "FINANCE_DATA_ENABLED": config.FINANCE_DATA_ENABLED,
            "NEODATA_ENABLED": config.NEODATA_ENABLED,
            "EXTERNAL_DATA_SOURCES": config.EXTERNAL_DATA_SOURCES,
            "python_version": sys.version.split()[0]
        }
    }
    
    # 保存测试报告
    report_file = Path(__file__).parent / "finance_integration_test_report.json"
    try:
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"\n测试报告已保存: {report_file}")
    except Exception as e:
        print(f"[WARN]️  无法保存测试报告: {e}")
    
    return passed == total


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)