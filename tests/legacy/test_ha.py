#!/usr/bin/env python3
"""
V3.0 - 高可用架构测试脚本
"""

import sys
import time
import json

# 添加项目路径
sys.path.insert(0, str(__import__('pathlib').Path(__file__).parent))

from core.ha import get_service_registry, create_local_service_instance, ServiceStatus
from core.logger import setup_logger, logger


def test_service_registry():
    """测试服务注册中心"""
    print("="*70)
    print("[TOOL] 测试1: 服务注册中心")
    print("="*70)
    
    registry = get_service_registry()
    registry.start()
    
    # 注册实例
    print("\n[LOG] 注册服务实例...")
    instance1 = create_local_service_instance(port=8000)
    instance2 = create_local_service_instance(port=8001)
    
    registry.register(instance1)
    registry.register(instance2)
    
    print(f"[OK] 已注册 {len(registry.get_all_instances())} 个实例")
    
    # 选择实例
    print("\n🎯 选择健康实例...")
    selected = registry.select_healthy_instance()
    if selected:
        print(f"[OK] 选中实例: {selected.service_id} (端口: {selected.port})")
    
    # 心跳
    print("\n💓 发送心跳...")
    for i in range(3):
        registry.heartbeat(instance1.service_id)
        registry.heartbeat(instance2.service_id)
        print(f"  心跳 {i+1}")
        time.sleep(0.5)
    
    # 状态报告
    print("\n[DATA] 状态报告:")
    report = registry.get_status_report()
    print(json.dumps(report, indent=2, ensure_ascii=False))
    
    # 注销实例
    print("\n👋 注销实例...")
    registry.unregister(instance2.service_id)
    print(f"[OK] 剩余实例: {len(registry.get_all_instances())}")
    
    registry.stop()
    print("\n[OK] 测试1完成！")
    return True


def test_load_balancing():
    """测试负载均衡"""
    print("\n" + "="*70)
    print("[TOOL] 测试2: 负载均衡")
    print("="*70)
    
    registry = get_service_registry()
    registry.start()
    
    # 注册3个实例
    print("\n[LOG] 注册3个服务实例...")
    instances = []
    for i in range(3):
        instance = create_local_service_instance(port=8000 + i)
        instance.status = ServiceStatus.HEALTHY
        instances.append(instance)
        registry.register(instance)
        print(f"  注册: {instance.service_id}")
    
    # 测试轮询
    print("\n[REFRESH] 测试轮询选择...")
    selected_ids = []
    for i in range(10):
        selected = registry.select_healthy_instance()
        if selected:
            selected_ids.append(selected.service_id)
            print(f"  选择 {i+1}: {selected.service_id}")
    
    # 统计
    from collections import Counter
    print("\n[DATA] 选择统计:")
    count = Counter(selected_ids)
    for sid, cnt in count.items():
        print(f"  {sid}: {cnt} 次")
    
    registry.stop()
    print("\n[OK] 测试2完成！")
    return True


def test_health_check():
    """测试健康检查"""
    print("\n" + "="*70)
    print("[TOOL] 测试3: 健康检查")
    print("="*70)
    
    # 临时修改健康检查间隔
    registry = get_service_registry()
    registry.health_check_interval = 1
    registry.health_check_timeout = 3
    registry.start()
    
    print("\n[LOG] 注册服务实例...")
    instance = create_local_service_instance(port=8000)
    registry.register(instance)
    
    # 手动设为健康
    instance.status = ServiceStatus.HEALTHY
    
    # 监控状态变化
    print("\n[TIME]  监控健康状态 (超时3秒)...")
    start_time = time.time()
    last_status = instance.status
    
    for i in range(5):
        report = registry.get_status_report()
        current = report['instances'][0]['status'] if report['instances'] else 'UNKNOWN'
        
        if current != last_status:
            print(f"  [{i+1}s] 状态变化: {last_status.value if hasattr(last_status, 'value') else last_status} -> {current}")
            last_status = current
        else:
            print(f"  [{i+1}s] 状态: {current}")
        
        time.sleep(1)
    
    # 发送心跳恢复
    print("\n💓 发送心跳恢复健康...")
    registry.heartbeat(instance.service_id)
    instance.status = ServiceStatus.HEALTHY
    
    time.sleep(0.5)
    report = registry.get_status_report()
    print(f"  恢复后状态: {report['instances'][0]['status']}")
    
    registry.stop()
    print("\n[OK] 测试3完成！")
    return True


def main():
    """主测试函数"""
    logger = setup_logger(level=20)  # INFO
    
    print("\n" + "="*70)
    print("🎯 V3.0 高可用架构测试")
    print("="*70)
    
    tests = [
        ("服务注册中心", test_service_registry),
        ("负载均衡", test_load_balancing),
        ("健康检查", test_health_check)
    ]
    
    results = []
    for name, test_func in tests:
        try:
            ok = test_func()
            results.append((name, ok))
        except Exception as e:
            print(f"\n[ERR] 测试 '{name}' 失败: {e}")
            import traceback
            print(traceback.format_exc())
            results.append((name, False))
    
    print("\n" + "="*70)
    print("[CLIP] 测试结果汇总")
    print("="*70)
    for name, ok in results:
        status = "[OK] 通过" if ok else "[ERR] 失败"
        print(f"  {name}: {status}")
    
    passed = sum(1 for _, ok in results if ok)
    print(f"\n[DATA] 总计: {passed}/{len(results)} 测试通过")
    
    if passed == len(results):
        print("\n[DONE] 所有测试通过！")
        return 0
    else:
        print(f"\n[WARN]  有 {len(results) - passed} 个测试失败")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)