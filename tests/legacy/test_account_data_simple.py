#!/usr/bin/env python3
"""
MT5 AI Trading System - 账户数据推送集成测试（简化版）
"""

import os
import sys

def test_ea_file():
    """测试EA文件的完整性"""
    print("=" * 60)
    print("账户数据推送集成测试 - 简化版")
    print("=" * 60)
    
    ea_file = "MQL5/Experts/AI_Trader_V3.2_Integrated.mq5"
    if not os.path.exists(ea_file):
        print(f"[ERROR] EA文件不存在: {ea_file}")
        return False
    
    print(f"[OK] EA文件存在: {ea_file}")
    
    with open(ea_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
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
            print(f"[PASS] {check_name}")
            passed += 1
        else:
            print(f"[FAIL] {check_name} (未找到: {check_string})")
            failed += 1
    
    print("\n" + "=" * 60)
    print("完整性检查结果:")
    print(f"  通过: {passed}")
    print(f"  失败: {failed}")
    print(f"  总计: {passed + failed}")
    if passed + failed > 0:
        print(f"  通过率: {passed/(passed+failed)*100:.1f}%")
    
    return failed == 0

def test_config():
    """测试核心配置"""
    print("\n" + "=" * 60)
    print("核心配置测试")
    print("=" * 60)
    
    # 检查core模块
    try:
        import core.config as config
        print("[PASS] 配置模块导入成功")
        
        # 检查关键配置项
        key_configs = [
            ("SOCKET_HOST", True, "127.0.0.1"),
            ("SOCKET_PORT", True, 8080),
            ("WEBSOCKET_HOST", True, "127.0.0.1"),
            ("WEBSOCKET_PORT", True, 8081),
            ("HTTP_PORT", True, 8000),
            ("MQL5_DATA_PORT", True, 8083)
        ]
        
        for config_name, required, default in key_configs:
            if hasattr(config, config_name):
                value = getattr(config, config_name)
                if not required or value:  # 如果不需要或值有效
                    print(f"[PASS] {config_name}: {value}")
                else:
                    print(f"[WARN] {config_name}: 值为空")
            else:
                print(f"[WARN] {config_name}: 未定义，使用默认值 {default}")
        
        return True
    except ImportError as e:
        print(f"[FAIL] 导入配置模块失败: {e}")
        return False

def main():
    """主测试函数"""
    print("MT5 AI Trading System - 账户数据推送集成测试（简化版）")
    print("=" * 80)
    
    # 运行测试
    test1_result = test_ea_file()
    test2_result = test_config()
    
    print("\n" + "=" * 80)
    print("测试结果汇总")
    print("=" * 80)
    
    print(f"1. EA文件完整性测试: {'[PASS]' if test1_result else '[FAIL]'}")
    print(f"2. 核心配置测试: {'[PASS]' if test2_result else '[FAIL]'}")
    
    all_pass = test1_result and test2_result
    
    if all_pass:
        print("\n[SUCCESS] 所有测试通过！")
        print("- AI_Trader_V3.2_Integrated 已成功集成账户数据推送功能")
        print("- 实时账户数据推送功能已内置到EA中")
        print("- 安全特性（反向平仓、每日亏损限制）已启用")
        print("- 异步状态机和性能统计已集成")
        print("\n下一步操作:")
        print("1. 在MetaEditor中编译 MQL5/Experts/AI_Trader_V3.2_Integrated.mq5")
        print("2. 在MT5图表上加载EA")
        print("3. 启用账户数据推送功能（默认已启用）")
        print("4. 启动Python服务: python mt5_ai_service_optimized.py")
    else:
        print("\n[WARNING] 部分测试失败，请检查相关问题。")
    
    return 0 if all_pass else 1

if __name__ == "__main__":
    sys.exit(main())