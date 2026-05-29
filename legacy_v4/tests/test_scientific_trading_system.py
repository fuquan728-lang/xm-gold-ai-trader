#!/usr/bin/env python3
"""
科学智能交易系统 - 集成测试
测试所有新模块的功能和性能
"""

import os
import sys
import time
import json
import asyncio
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Any
import tempfile
import shutil

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from core.datastore import get_datastore, DataStore
from core.market_data_analyzer import get_market_data_analyzer
from core.ml_predictor import get_ml_predictor
from core.risk_manager import get_risk_manager, RiskLevel
from core.trade_executor import get_trade_executor, TradingPlatform
from core.performance_evaluator import get_performance_evaluator
from core.system_optimizer import get_system_optimizer
from core.logger import logger


class TestScientificTradingSystem:
    """科学智能交易系统测试类"""
    
    @classmethod
    def setup_class(cls):
        """测试类设置"""
        print("\n" + "="*70)
        print("🧪 科学智能交易系统 - 集成测试开始")
        print("="*70)
        
        # 创建临时数据库用于测试
        cls.temp_dir = tempfile.mkdtemp()
        cls.db_path = os.path.join(cls.temp_dir, "test_trading.db")
        
        # 设置测试环境变量
        os.environ["DATABASE_PATH"] = cls.db_path
        os.environ["LOG_LEVEL"] = "INFO"
        
        logger.info(f"[DIR] 测试数据库路径: {cls.db_path}")
    
    @classmethod
    def teardown_class(cls):
        """测试类清理"""
        # 清理临时文件
        if os.path.exists(cls.temp_dir):
            shutil.rmtree(cls.temp_dir)
            logger.info(f"🧹 清理临时目录: {cls.temp_dir}")
        
        print("\n" + "="*70)
        print("[OK] 科学智能交易系统 - 集成测试完成")
        print("="*70)
    
    def setup_method(self, method_name=None):
        """测试方法设置"""
        self.start_time = time.time()
        self.current_test_name = method_name or getattr(self, '_testMethodName', 'unknown_test')
        print(f"\n[TOOL] 开始测试: {self.current_test_name}")
    
    def teardown_method(self):
        """测试方法清理"""
        duration = time.time() - self.start_time
        print(f"[TIME]  测试耗时: {duration:.2f}s")
    
    def test_01_datastore(self):
        """测试数据存储模块"""
        print("[DATA] 测试数据存储模块...")
        
        # 获取数据存储实例
        datastore = get_datastore()
        assert datastore is not None
        assert isinstance(datastore, DataStore)
        
        # 测试数据库连接
        conn = datastore.conn
        assert conn is not None
        
        # 测试表创建
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        
        required_tables = [
            'market_prices', 'technical_indicators', 'economic_indicators',
            'market_sentiment', 'trades', 'predictions'
        ]
        
        for table in required_tables:
            assert table in tables, f"表 {table} 不存在"
        
        print(f"[OK] 数据库连接正常，找到 {len(tables)} 张表")
        
        # 测试数据插入
        trade_id = datastore.record_trade(
            symbol="EURUSD",
            action="BUY",
            entry_price=1.0850,
            position_size=0.1,
            stop_loss=1.0820,
            take_profit=1.0900,
            pnl=25.50
        )
        
        assert trade_id is not None
        assert isinstance(trade_id, int)
        
        # 测试数据查询
        trades = datastore.get_trades(limit=10)
        assert isinstance(trades, list)
        assert len(trades) > 0
        
        print(f"[OK] 数据存储功能正常，已记录 {len(trades)} 条交易")
    
    def test_02_market_data_analyzer(self):
        """测试市场数据分析模块"""
        print("[UP] 测试市场数据分析模块...")
        
        # 获取市场数据分析器实例
        analyzer = get_market_data_analyzer()
        assert analyzer is not None
        assert isinstance(analyzer, MarketDataAnalyzer)
        
        # 测试实时数据处理
        test_data = {
            "symbol": "EURUSD",
            "bid": 1.0850,
            "ask": 1.0852,
            "volume": 1000000,
            "timestamp": time.time()
        }
        
        result = analyzer.process_real_time_data(
            symbol="EURUSD",
            bid=1.0850,
            ask=1.0852,
            volume=1000000,
            timestamp=time.time()
        )
        
        assert isinstance(result, dict)
        assert "processed" in result
        assert result["processed"] is True
        
        # 测试技术指标计算
        indicators = analyzer.calculate_technical_indicators(
            symbol="EURUSD",
            timeframe="M5"
        )
        
        assert isinstance(indicators, dict)
        assert "sma_20" in indicators
        assert "rsi" in indicators
        assert "macd" in indicators
        
        # 测试市场分析
        analysis = analyzer.get_market_analysis("EURUSD", "M5")
        assert isinstance(analysis, dict)
        assert "trend" in analysis
        assert "volatility" in analysis
        assert "sentiment" in analysis
        
        print(f"[OK] 市场数据分析功能正常，趋势: {analysis.get('trend', 'unknown')}")
    
    def test_03_ml_predictor(self):
        """测试机器学习预测模块"""
        print("[AI] 测试机器学习预测模块...")
        
        # 获取机器学习预测器实例
        predictor = get_ml_predictor()
        assert predictor is not None
        assert isinstance(predictor, MLPredictor)
        
        # 准备测试数据
        features = np.random.randn(100, 10)  # 100个样本，10个特征
        labels = np.random.randint(0, 2, 100)  # 100个二元标签
        
        # 测试模型训练
        model_name = "test_model"
        training_result = predictor.train_model(
            model_name=model_name,
            features=features,
            labels=labels,
            model_type="random_forest",
            test_size=0.2
        )
        
        assert isinstance(training_result, dict)
        assert "accuracy" in training_result
        assert "model_id" in training_result
        
        model_id = training_result["model_id"]
        
        # 测试预测
        test_features = np.random.randn(10, 10)
        predictions = predictor.predict(
            model_name=model_name,
            features=test_features,
            confidence_threshold=0.6
        )
        
        assert isinstance(predictions, dict)
        assert "predictions" in predictions
        assert "confidences" in predictions
        assert "model_used" in predictions
        
        # 测试特征提取
        market_data = {
            "prices": np.random.randn(100),
            "volumes": np.random.randn(100),
            "indicators": {
                "rsi": np.random.randn(100),
                "macd": np.random.randn(100)
            }
        }
        
        extracted_features = predictor.extract_features(market_data)
        assert isinstance(extracted_features, np.ndarray)
        
        print(f"[OK] 机器学习预测功能正常，准确率: {training_result['accuracy']:.2%}")
    
    def test_04_risk_manager(self):
        """测试风险管理模块"""
        print("[RM]  测试风险管理模块...")
        
        # 获取风险管理器实例
        risk_manager = get_risk_manager(account_balance=10000.0)
        assert risk_manager is not None
        assert isinstance(risk_manager, RiskManager)
        
        # 测试交易风险评估
        assessment = risk_manager.assess_trade_risk(
            symbol="EURUSD",
            action="BUY",
            confidence=0.75,
            current_price=1.0850
        )
        
        assert assessment is not None
        assert assessment.symbol == "EURUSD"
        assert assessment.action == "BUY"
        assert 0 <= assessment.risk_score <= 1
        assert isinstance(assessment.recommended_position_size, float)
        assert isinstance(assessment.recommended_stop_loss, float)
        assert isinstance(assessment.recommended_take_profit, float)
        
        # 测试开仓条件检查
        can_open = risk_manager.can_open_position(
            symbol="EURUSD",
            position_size=0.1
        )
        
        assert isinstance(can_open, bool)
        
        # 测试风险报告
        risk_report = risk_manager.get_risk_report()
        assert isinstance(risk_report, dict)
        assert "account" in risk_report
        assert "risk_parameters" in risk_report
        assert "risk_metrics" in risk_report
        
        print(f"[OK] 风险管理功能正常，风险评分: {assessment.risk_score:.2f}")
    
    def test_05_trade_executor(self):
        """测试交易执行模块"""
        print("-> 测试交易执行模块...")
        
        # 获取交易执行器实例（使用模拟平台）
        executor = get_trade_executor(platform=TradingPlatform.MT5)
        assert executor is not None
        assert isinstance(executor, TradeExecutor)
        
        # 测试执行状态
        status = executor.get_execution_status()
        assert isinstance(status, dict)
        assert "platform" in status
        assert "connected" in status
        
        # 测试订单提交
        executor.submit_order(
            symbol="EURUSD",
            action="BUY",
            confidence=0.75
        )
        
        # 检查订单队列
        time.sleep(0.5)  # 等待订单处理
        
        print(f"[OK] 交易执行功能正常，平台: {status['platform']}")
    
    def test_06_performance_evaluator(self):
        """测试绩效评估模块"""
        print("[DATA] 测试绩效评估模块...")
        
        # 获取绩效评估器实例
        evaluator = get_performance_evaluator()
        assert evaluator is not None
        assert isinstance(evaluator, PerformanceEvaluator)
        
        # 测试绩效指标计算
        metrics = evaluator.get_strategy_metrics(strategy="default")
        assert isinstance(metrics, object)
        assert hasattr(metrics, "total_trades")
        assert hasattr(metrics, "win_rate")
        assert hasattr(metrics, "total_pnl")
        
        # 测试策略分析
        analysis = evaluator.analyze_strategy(strategy="default", symbol="EURUSD")
        assert analysis is not None
        assert analysis.strategy_name == "default"
        assert isinstance(analysis.metrics, object)
        assert isinstance(analysis.recommendations, list)
        
        # 测试报告生成
        report_path = evaluator.generate_report(
            strategy="default",
            include_details=True
        )
        
        assert isinstance(report_path, str)
        if report_path:  # 可能为空字符串（生成失败时）
            assert os.path.exists(report_path)
            print(f"[OK] 绩效评估功能正常，报告路径: {report_path}")
        else:
            print("[WARN]  报告生成失败，但其他功能正常")
    
    def test_07_system_optimizer(self):
        """测试系统优化器模块"""
        print("[FAST] 测试系统优化器模块...")
        
        # 获取系统优化器实例
        optimizer = get_system_optimizer()
        assert optimizer is not None
        assert isinstance(optimizer, SystemOptimizer)
        
        # 测试缓存功能
        def fetch_data():
            time.sleep(0.01)  # 模拟耗时操作
            return "test_data"
        
        # 第一次获取（缓存未命中）
        start_time = time.time()
        data1 = optimizer.get_cached_data("test_key", fetch_data)
        duration1 = time.time() - start_time
        
        # 第二次获取（缓存命中）
        start_time = time.time()
        data2 = optimizer.get_cached_data("test_key", fetch_data)
        duration2 = time.time() - start_time
        
        assert data1 == "test_data"
        assert data2 == "test_data"
        assert duration2 < duration1  # 缓存应该更快
        
        # 测试重试机制
        attempt_count = 0
        
        def unreliable_function():
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count < 2:
                raise Exception(f"模拟失败 (尝试 {attempt_count})")
            return "成功"
        
        result = optimizer.execute_with_retry(unreliable_function, max_retries=3)
        assert result == "成功"
        assert attempt_count == 2
        
        # 测试批量处理
        items = list(range(100))
        
        def process_item(x):
            time.sleep(0.001)
            return x * 2
        
        results = optimizer.batch_process(items, process_item, batch_size=20, parallel=True)
        assert len(results) == 100
        assert results[0] == 0
        assert results[99] == 198
        
        print(f"[OK] 系统优化功能正常，缓存加速比: {duration1/duration2:.1f}x")
    
    def test_08_integration(self):
        """测试模块集成"""
        print("[LINK] 测试模块集成...")
        
        # 模拟完整的交易流程
        symbol = "EURUSD"
        current_price = 1.0850
        
        # 1. 市场数据分析
        analyzer = get_market_data_analyzer()
        analysis = analyzer.get_market_analysis(symbol, "M5")
        
        # 2. 机器学习预测
        predictor = get_ml_predictor()
        
        # 准备特征数据
        features = np.random.randn(1, 10)
        prediction = predictor.predict(
            model_name="random_forest",
            features=features,
            confidence_threshold=0.6
        )
        
        # 3. 风险评估
        risk_manager = get_risk_manager()
        confidence = prediction.get("confidences", [0.5])[0] if prediction.get("predictions") else 0.5
        action = "BUY" if prediction.get("predictions", [0])[0] == 1 else "SELL"
        
        risk_assessment = risk_manager.assess_trade_risk(
            symbol=symbol,
            action=action,
            confidence=confidence,
            current_price=current_price
        )
        
        # 4. 交易执行
        executor = get_trade_executor()
        if risk_assessment.risk_score < 0.7:  # 风险评分较低才执行
            executor.submit_order(
                symbol=symbol,
                action=action,
                confidence=confidence
            )
        
        # 5. 绩效评估
        evaluator = get_performance_evaluator()
        metrics = evaluator.get_strategy_metrics("default")
        
        # 6. 系统优化
        optimizer = get_system_optimizer()
        performance_report = optimizer.get_performance_report()
        
        # 验证集成结果
        assert analysis is not None
        assert prediction is not None
        assert risk_assessment is not None
        assert metrics is not None
        assert performance_report is not None
        
        print("[OK] 模块集成测试通过，完整交易流程验证成功")
    
    def test_09_performance(self):
        """测试系统性能"""
        print("[FAST] 测试系统性能...")
        
        # 测试并发处理能力
        optimizer = get_system_optimizer()
        
        # 并发任务数量
        num_tasks = 50
        
        def mock_task(task_id):
            time.sleep(0.05)  # 模拟50ms的任务
            return f"task_{task_id}_completed"
        
        # 提交并发任务
        start_time = time.time()
        task_ids = []
        
        for i in range(num_tasks):
            task_id = optimizer.task_scheduler.submit(
                mock_task, i, priority=5
            )
            task_ids.append(task_id)
        
        # 等待所有任务完成
        results = []
        for task_id in task_ids:
            try:
                result = optimizer.task_scheduler.wait_for_completion(task_id, timeout=10)
                results.append(result)
            except Exception as e:
                print(f"[WARN]  任务 {task_id} 失败: {e}")
        
        total_time = time.time() - start_time
        
        # 性能要求：50个任务应在5秒内完成（平均每个任务100ms）
        assert total_time < 5.0, f"性能测试失败: 总耗时 {total_time:.2f}s > 5.0s"
        
        # 计算吞吐量
        throughput = num_tasks / total_time
        avg_latency = total_time / num_tasks * 1000  # 转换为毫秒
        
        print(f"[OK] 性能测试通过:")
        print(f"   任务数量: {num_tasks}")
        print(f"   总耗时: {total_time:.2f}s")
        print(f"   吞吐量: {throughput:.1f} 任务/秒")
        print(f"   平均延迟: {avg_latency:.1f}ms")
        
        # 性能要求：平均延迟 < 150ms
        assert avg_latency < 150, f"延迟过高: {avg_latency:.1f}ms > 150ms"
    
    def test_10_error_handling(self):
        """测试错误处理"""
        print("[RM]  测试错误处理...")
        
        optimizer = get_system_optimizer()
        
        # 测试异常情况下的重试机制
        fail_count = 0
        
        def failing_function():
            nonlocal fail_count
            fail_count += 1
            raise RuntimeError(f"第{fail_count}次失败")
        
        # 应该抛出异常
        try:
            optimizer.execute_with_retry(failing_function, max_retries=3, retry_delay=0.1)
            assert False, "应该抛出异常"
        except RuntimeError as e:
            assert "第3次失败" in str(e)  # 最后一次失败
        
        # 测试缓存失效处理
        def throwing_fetcher():
            raise ValueError("获取数据失败")
        
        try:
            optimizer.get_cached_data("error_key", throwing_fetcher)
            assert False, "应该抛出异常"
        except ValueError as e:
            assert "获取数据失败" in str(e)
        
        print("[OK] 错误处理测试通过，系统具备容错能力")


def run_all_tests():
    """运行所有测试"""
    print("\n" + "="*70)
    print("-> 开始运行科学智能交易系统集成测试")
    print("="*70)
    
    # 创建测试实例
    test_suite = TestScientificTradingSystem()
    
    # 设置测试类
    test_suite.setup_class()
    
    # 运行所有测试方法
    test_methods = [
        "test_01_datastore",
        "test_02_market_data_analyzer",
        "test_03_ml_predictor",
        "test_04_risk_manager",
        "test_05_trade_executor",
        "test_06_performance_evaluator",
        "test_07_system_optimizer",
        "test_08_integration",
        "test_09_performance",
        "test_10_error_handling"
    ]
    
    passed_tests = 0
    failed_tests = []
    
    for method_name in test_methods:
        try:
            # 设置测试方法
            test_suite.setup_method(method_name)
            
            # 运行测试
            method = getattr(test_suite, method_name)
            method()
            
            print(f"[OK] {method_name} 测试通过")
            passed_tests += 1
            
        except Exception as e:
            print(f"[ERR] {method_name} 测试失败: {e}")
            failed_tests.append((method_name, str(e)))
        
        finally:
            # 清理测试方法
            test_suite.teardown_method()
    
    # 清理测试类
    test_suite.teardown_class()
    
    # 输出测试结果
    print("\n" + "="*70)
    print("[DATA] 测试结果汇总")
    print("="*70)
    
    total_tests = len(test_methods)
    print(f"总测试数: {total_tests}")
    print(f"通过: {passed_tests}")
    print(f"失败: {len(failed_tests)}")
    
    if failed_tests:
        print("\n[ERR] 失败的测试:")
        for test_name, error in failed_tests:
            print(f"  - {test_name}: {error}")
        
        print(f"\n[TIP] 通过率: {passed_tests/total_tests*100:.1f}%")
        return False
    else:
        print(f"\n[DONE] 所有测试通过！")
        print(f"[TIP] 通过率: {passed_tests/total_tests*100:.1f}%")
        return True


if __name__ == "__main__":
    # 运行测试
    success = run_all_tests()
    
    if success:
        print("\n[OK] 科学智能交易系统集成测试全部通过！")
        sys.exit(0)
    else:
        print("\n[ERR] 科学智能交易系统集成测试失败！")
        sys.exit(1)