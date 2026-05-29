#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
兼容桥接模块 - 从 websocket_handler_enhanced 重新导出
此文件仅用于向后兼容，所有实际实现已迁移至 websocket_handler_enhanced.py

注意: 此文件会在改动 websocket_handler_enhanced 后自动生效
"""
from core.websocket_handler_enhanced import (
    EnhancedWebSocketHandler as WebSocketHandler,
    ConnectionPool,
    ConnectionStatus,
    ClientInfo,
    HAS_WEBSOCKETS,
)

__all__ = ['WebSocketHandler', 'ConnectionPool', 'ConnectionStatus', 'ClientInfo', 'HAS_WEBSOCKETS']
