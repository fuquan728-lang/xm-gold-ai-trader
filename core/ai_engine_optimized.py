#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
兼容桥接模块 - ai_engine_optimized 已合并至 ai_engine

v3.1+: 多时间框架分析(MFT)等优化已集成到主引擎 ai_engine.AIAnalyzer
此文件仅用于向后兼容旧测试代码
"""
from core.ai_engine import AIAnalyzer as AIAnalyzerOptimized


def get_optimized_analyzer(**kwargs):
    """获取优化版分析器（已合并至主引擎）"""
    return AIAnalyzerOptimized(**kwargs)


__all__ = ['AIAnalyzerOptimized', 'get_optimized_analyzer']
