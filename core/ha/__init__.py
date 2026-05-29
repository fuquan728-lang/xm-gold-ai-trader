"""
V3.0 - 高可用架构包
"""

from .service_registry import (
    ServiceRegistry,
    ServiceInstance,
    ServiceStatus,
    get_service_registry,
    create_local_service_instance
)

__all__ = [
    "ServiceRegistry",
    "ServiceInstance",
    "ServiceStatus",
    "get_service_registry",
    "create_local_service_instance"
]