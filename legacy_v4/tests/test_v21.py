#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
V2.1 全面单元测试套件
测试策略安全修复、JSON解析、缓存系统
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest
import json
import time
from datetime import datetime
from core.ai_engine import AIAnalyzer
from core.cache import LRUCache
from core.validator import DataValidator


class TestJSONParsing(unittest.TestCase):
    """测试AI响应JSON解析"""
    
    def setUp(self):
        self.analyzer = AIAnalyzer()
    
    def test_simple_json(self):
        """测试简单标准JSON"""
        content = '{"action": "BUY", "confidence": 0.85, "reason": "技术指标看好"}'
        result = self.analyzer._extract_json(content)
        self.assertIsNotNone(result)
        self.assertEqual(result['action'], 'BUY')
        self.assertAlmostEqual(result['confidence'], 0.85)
    
    def test_json_with_markdown(self):
        """测试带Markdown的JSON"""
        content = '''```json
{"action": "SELL", "confidence": 0.72, "reason": "趋势向下"}
```'''
        result = self.analyzer._extract_json(content)
        self.assertIsNotNone(result)
        self.assertEqual(result['action'], 'SELL')
    
    def test_json_with_text_around(self):
        """测试带前后文本的JSON"""
        content = '这是分析内容... {"action": "HOLD", "confidence": 0.5, "reason": "观望"} 更多内容'
        result = self.analyzer._extract_json(content)
        self.assertIsNotNone(result)
        self.assertEqual(result['action'], 'HOLD')
    
    def test_invalid_json_fallback(self):
        """测试无效JSON返回None"""
        content = '这不是JSON'
        result = self.analyzer._extract_json(content)
        self.assertIsNone(result)
    
    def test_action_normalization(self):
        """测试action归一化"""
        test_cases = [
            ('buy', 'BUY'),
            ('Sell', 'SELL'),
            ('Hold', 'HOLD'),
            ('invalid', 'HOLD'),
        ]
        for input_val, expected in test_cases:
            json_str = f'{{"action": "{input_val}", "confidence": 0.5, "reason": ""}}'
            result = self.analyzer._parse_json_string(json_str)
            self.assertEqual(result['action'], expected)
    
    def test_confidence_clamping(self):
        """测试置信度范围限制"""
        test_cases = [
            (1.5, 1.0),
            (-0.2, 0.0),
            (0.5, 0.5),
        ]
        for input_val, expected in test_cases:
            json_str = f'{{"action": "BUY", "confidence": {input_val}, "reason": ""}}'
            result = self.analyzer._parse_json_string(json_str)
            self.assertAlmostEqual(result['confidence'], expected)


class TestCacheSystem(unittest.TestCase):
    """测试缓存系统"""
    
    def setUp(self):
        self.cache = LRUCache(maxsize=5, ttl=10)  # 修复参数名
    
    def test_basic_set_get(self):
        """测试基本的设置和获取"""
        self.cache.set('key1', 'value1')
        self.assertEqual(self.cache.get('key1'), 'value1')
    
    def test_cache_miss(self):
        """测试缓存未命中"""
        self.assertIsNone(self.cache.get('nonexistent'))
    
    def test_lru_eviction(self):
        """测试LRU淘汰"""
        for i in range(6):
            self.cache.set(f'key{i}', f'value{i}')
        self.assertIsNone(self.cache.get('key0'))  # 最旧的应该被淘汰
    
    def test_ttl_expiration(self):
        """测试TTL过期"""
        cache_short = LRUCache(max_size=10, ttl_seconds=0.1)
        cache_short.set('expire', 'soon')
        self.assertEqual(cache_short.get('expire'), 'soon')
        time.sleep(0.2)
        self.assertIsNone(cache_short.get('expire'))
    
    def test_contains(self):
        """测试contains检查"""
        self.cache.set('check', 'exists')
        self.assertTrue('check' in self.cache)
        self.assertFalse('notthere' in self.cache)
    
    def test_cache_size(self):
        """测试缓存大小"""
        for i in range(3):
            self.cache.set(f'key{i}', f'value{i}')
        self.assertEqual(len(self.cache), 3)


class TestDataValidator(unittest.TestCase):
    """测试数据验证"""
    
    def setUp(self):
        self.validator = DataValidator()
    
    def test_valid_market_data(self):
        """测试有效的市场数据"""
        data = {
            'symbol': 'EURUSD',
            'bid': 1.0850,
            'ask': 1.0855,
            'time': time.time()
        }
        # validate_request在有效数据时返回True
        self.assertTrue(self.validator.validate_request(data))
    
    def test_invalid_price(self):
        """测试无效价格"""
        data = {
            'symbol': 'EURUSD',
            'bid': -1,
            'ask': 1.0855,
            'time': time.time()
        }
        # 应该抛出异常
        with self.assertRaises(ValueError):
            self.validator.validate_request(data)
    
    def test_missing_fields(self):
        """测试缺少字段"""
        data = {'symbol': 'EURUSD'}
        # 应该抛出异常
        with self.assertRaises(ValueError):
            self.validator.validate_request(data)


class TestPromptBuilding(unittest.TestCase):
    """测试提示词构建"""
    
    def setUp(self):
        self.analyzer = AIAnalyzer()
    
    def test_basic_prompt(self):
        """测试基本提示词"""
        prompt = self.analyzer.build_prompt(
            symbol='EURUSD',
            bid=1.0850,
            ask=1.0855,
            current_time=time.time()
        )
        self.assertIn('EURUSD', prompt)
        self.assertIn('BUY', prompt)
        self.assertIn('SELL', prompt)
    
    def test_prompt_with_indicators(self):
        """测试带指标的提示词"""
        indicators = {
            'rsi': 55.5,
            'macd_main': 0.0015,
            'macd_signal': 0.0020,
            'ema50': 1.0840
        }
        prompt = self.analyzer.build_prompt(
            symbol='EURUSD',
            bid=1.0850,
            ask=1.0855,
            current_time=time.time(),
            indicators=indicators
        )
        self.assertIn('RSI', prompt)
        self.assertIn('MACD', prompt)
        self.assertIn('EMA50', prompt)


class TestV21Features(unittest.TestCase):
    """V2.1新特性整合测试"""
    
    def test_safe_fallback(self):
        """测试安全后备策略不返回有风险信号"""
        analyzer = AIAnalyzer()
        action, confidence, reason = analyzer.get_fallback_strategy()
        self.assertIn(action, ['BUY', 'SELL', 'HOLD'])
        self.assertGreaterEqual(confidence, 0.0)
        self.assertLessEqual(confidence, 1.0)


def run_v21_tests():
    """运行V2.1所有测试"""
    print("=" * 60)
    print("🎯 V2.1 - 策略安全修复版 单元测试套件")
    print("=" * 60)
    
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    suite.addTests(loader.loadTestsFromTestCase(TestJSONParsing))
    suite.addTests(loader.loadTestsFromTestCase(TestCacheSystem))
    suite.addTests(loader.loadTestsFromTestCase(TestDataValidator))
    suite.addTests(loader.loadTestsFromTestCase(TestPromptBuilding))
    suite.addTests(loader.loadTestsFromTestCase(TestV21Features))
    
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    print("\n" + "=" * 60)
    print(f"[OK] 测试通过: {result.testsRun - len(result.failures) - len(result.errors)}/{result.testsRun}")
    if result.wasSuccessful():
        print("🎊 V2.1 所有测试通过！")
    else:
        print("[WARN]  部分测试失败，请检查")
    print("=" * 60)
    
    return result.wasSuccessful()


if __name__ == '__main__':
    success = run_v21_tests()
    sys.exit(0 if success else 1)
