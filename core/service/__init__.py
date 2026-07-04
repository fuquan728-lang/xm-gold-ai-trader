# -*- coding: utf-8 -*-
"""
core/service - God Class拆分子模块包
Phase 1: ServiceMonitor
Phase 2: Communication (FileModeRunner / SocketModeRunner / WebSocketModeRunner)
Phase 3: AICoordinator / RequestProcessor
"""

from core.service.monitor import ServiceMonitor

__all__ = ["ServiceMonitor"]
