#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
运行所有单元测试
"""

import sys
import os
from pathlib import Path

def run_tests():
    """运行所有测试"""
    print("=" * 60)
    print("MT5 AI交易系统 - 单元测试套件")
    print("=" * 60)
    
    # 添加项目根目录到Python路径
    sys.path.insert(0, str(Path(__file__).parent))
    
    # 运行配置测试
    print("\n[TOOL] 运行配置模块测试...")
    try:
        from tests.test_config import test_config_defaults, test_get_possible_paths, test_config_validation
        test_config_defaults()
        test_get_possible_paths()
        test_config_validation()
        print("[OK] 配置模块测试完成")
    except Exception as e:
        print(f"[ERR] 配置模块测试失败: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    # 运行验证测试
    print("\n[TEST] 运行数据验证测试...")
    try:
        from tests.test_validation import (
            test_validate_request_data_valid,
            test_validate_request_data_missing_fields,
            test_validate_request_data_invalid_types,
            test_validate_request_data_optional_fields
        )
        test_validate_request_data_valid()
        test_validate_request_data_missing_fields()
        test_validate_request_data_invalid_types()
        test_validate_request_data_optional_fields()
        print("[OK] 数据验证测试完成")
    except Exception as e:
        print(f"[ERR] 数据验证测试失败: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    # 运行Socket集成测试
    print("\n🔌 运行Socket集成测试...")
    try:
        from tests.test_socket_integration import run_all_tests
        if not run_all_tests():
            print("[ERR] Socket集成测试失败")
            return 1
        print("[OK] Socket集成测试完成")
    except Exception as e:
        print(f"[ERR] Socket集成测试失败: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    print("\n" + "=" * 60)
    print("[DONE] 所有测试通过！")
    print("=" * 60)
    return 0

if __name__ == "__main__":
    sys.exit(run_tests())