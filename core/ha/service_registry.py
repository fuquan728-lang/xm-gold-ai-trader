#!/usr/bin/env python3
"""
V3.0 - 高可用架构模块
服务发现、健康检查、负载均衡、故障转移
"""

import time
import json
import threading
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Any, Set
from enum import Enum
import random

from core.logger import logger


class ServiceStatus(Enum):
    """服务状态枚举"""
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    STARTING = "starting"
    STOPPED = "stopped"


class ServiceInstance:
    """服务实例"""
    
    def __init__(
        self,
        service_id: str,
        host: str = "127.0.0.1",
        port: int = 8000,
        websocket_port: Optional[int] = None,
        socket_port: Optional[int] = None,
        service_type: str = "ai_trading"
    ):
        self.service_id = service_id
        self.host = host
        self.port = port
        self.websocket_port = websocket_port
        self.socket_port = socket_port
        self.service_type = service_type
        self.status = ServiceStatus.STARTING
        self.last_heartbeat = time.time()
        self.metadata: Dict[str, Any] = {
            "startup_time": datetime.now().isoformat(),
            "requests_processed": 0,
            "version": "V3.0"
        }
    
    def update_heartbeat(self):
        """更新心跳时间"""
        self.last_heartbeat = time.time()
    
    def is_alive(self, timeout_seconds: int = 30) -> bool:
        """检查服务是否还活着"""
        return (time.time() - self.last_heartbeat) < timeout_seconds
    
    def increment_requests(self):
        """请求计数器递增"""
        self.metadata["requests_processed"] = self.metadata.get("requests_processed", 0) + 1
    
    def to_dict(self) -> Dict[str, Any]:
        """转为字典"""
        return {
            "service_id": self.service_id,
            "host": self.host,
            "port": self.port,
            "websocket_port": self.websocket_port,
            "socket_port": self.socket_port,
            "service_type": self.service_type,
            "status": self.status.value,
            "last_heartbeat": self.last_heartbeat,
            "metadata": self.metadata
        }


class LoadBalancer:
    """简单的负载均衡器"""
    
    def __init__(self):
        self.strategy = "round_robin"  # 或 "least_connections"
        self.round_robin_index = 0
    
    def select_instance(self, instances: List[ServiceInstance]) -> Optional[ServiceInstance]:
        """选择一个服务实例"""
        healthy_instances = [i for i in instances if i.status == ServiceStatus.HEALTHY]
        if not healthy_instances:
            return None
        
        if self.strategy == "round_robin":
            self.round_robin_index = (self.round_robin_index + 1) % len(healthy_instances)
            return healthy_instances[self.round_robin_index]
        elif self.strategy == "least_connections":
            # 简单实现：选随机一个
            return random.choice(healthy_instances)
        else:
            return random.choice(healthy_instances)


class ServiceRegistry:
    """服务注册和发现中心"""
    
    def __init__(self):
        self.instances: Dict[str, ServiceInstance] = {}
        self.lock = threading.RLock()
        self.health_check_interval = 5.0
        self.health_check_timeout = 30
        self.load_balancer = LoadBalancer()
        self.running = False
        self.health_check_thread: Optional[threading.Thread] = None
        
        logger.info("[OK] ServiceRegistry 初始化")
    
    def register(self, instance: ServiceInstance) -> str:
        """注册服务"""
        with self.lock:
            self.instances[instance.service_id] = instance
            logger.info(f"[LOG] 服务注册成功: {instance.service_id}")
            return instance.service_id
    
    def unregister(self, service_id: str):
        """注销服务"""
        with self.lock:
            if service_id in self.instances:
                self.instances[service_id].status = ServiceStatus.STOPPED
                del self.instances[service_id]
                logger.info(f"👋 服务注销: {service_id}")
    
    def heartbeat(self, service_id: str):
        """服务心跳"""
        with self.lock:
            if service_id in self.instances:
                self.instances[service_id].update_heartbeat()
                # logger.debug(f"💓 服务心跳: {service_id}")
    
    def get_instance(self, service_id: str) -> Optional[ServiceInstance]:
        """获取服务实例"""
        with self.lock:
            return self.instances.get(service_id)
    
    def get_all_instances(self) -> List[ServiceInstance]:
        """获取所有服务实例"""
        with self.lock:
            return list(self.instances.values())
    
    def select_healthy_instance(self, service_type: str = "ai_trading") -> Optional[ServiceInstance]:
        """选择一个健康的服务实例"""
        with self.lock:
            matching_instances = [
                i for i in self.instances.values()
                if i.service_type == service_type and i.status == ServiceStatus.HEALTHY
            ]
            return self.load_balancer.select_instance(matching_instances)
    
    def _health_check_loop(self):
        """健康检查循环"""
        logger.info("[HOSPITAL] 健康检查线程启动")
        while self.running:
            try:
                self._perform_health_check()
                time.sleep(self.health_check_interval)
            except Exception as e:
                logger.error(f"[ERR] 健康检查异常: {e}")
                time.sleep(1)
    
    def _perform_health_check(self):
        """执行一次健康检查"""
        with self.lock:
            now = time.time()
            for service_id, instance in list(self.instances.items()):
                # 检查心跳超时
                if instance.status == ServiceStatus.HEALTHY:
                    if not instance.is_alive(self.health_check_timeout):
                        instance.status = ServiceStatus.UNHEALTHY
                        logger.warning(f"[WARN] 服务不健康: {service_id}")
                elif instance.status == ServiceStatus.STARTING:
                    # 给启动一个宽限期
                    if (now - instance.last_heartbeat) > 60:
                        instance.status = ServiceStatus.HEALTHY
                        logger.info(f"[OK] 服务启动完成: {service_id}")
    
    def start(self):
        """启动服务注册中心"""
        self.running = True
        self.health_check_thread = threading.Thread(target=self._health_check_loop, daemon=True)
        self.health_check_thread.start()
        logger.info("-> ServiceRegistry 启动成功")
    
    def stop(self):
        """停止服务注册中心"""
        self.running = False
        if self.health_check_thread:
            self.health_check_thread.join(timeout=2)
        logger.info("🛑 ServiceRegistry 已停止")
    
    def get_status_report(self) -> Dict[str, Any]:
        """获取状态报告"""
        with self.lock:
            total = len(self.instances)
            healthy = sum(1 for i in self.instances.values() if i.status == ServiceStatus.HEALTHY)
            unhealthy = sum(1 for i in self.instances.values() if i.status == ServiceStatus.UNHEALTHY)
            
            return {
                "total_instances": total,
                "healthy_instances": healthy,
                "unhealthy_instances": unhealthy,
                "instances": [i.to_dict() for i in self.instances.values()]
            }


# 全局服务注册中心
_global_registry: Optional[ServiceRegistry] = None


def get_service_registry() -> ServiceRegistry:
    """获取全局服务注册中心"""
    global _global_registry
    if not _global_registry:
        _global_registry = ServiceRegistry()
    return _global_registry


def create_local_service_instance(
    port: int = 8000,
    websocket_port: int = 8081,
    socket_port: int = 8080
) -> ServiceInstance:
    """创建本地服务实例"""
    service_id = f"ai_trading_{uuid.uuid4().hex[:8]}"
    return ServiceInstance(
        service_id=service_id,
        host="127.0.0.1",
        port=port,
        websocket_port=websocket_port,
        socket_port=socket_port
    )


if __name__ == "__main__":
    # 简单测试
    print("="*70)
    print("[TOOL] 测试服务注册中心")
    print("="*70)
    
    registry = get_service_registry()
    registry.start()
    
    # 注册2个测试实例
    instance1 = create_local_service_instance(port=8000)
    instance2 = create_local_service_instance(port=8001)
    
    registry.register(instance1)
    registry.register(instance2)
    
    # 选择实例
    selected = registry.select_healthy_instance()
    if selected:
        print(f"\n[OK] 选中的实例: {selected.service_id}")
    
    # 打印状态
    print("\n[DATA] 状态报告:")
    report = registry.get_status_report()
    print(json.dumps(report, indent=2, ensure_ascii=False))
    
    registry.stop()
    print("\n[OK] 测试完成！")