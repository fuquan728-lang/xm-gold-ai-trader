#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
多时间框架分析性能评估工具
对比有/无多时间框架分析的交易信号准确率
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import json
import random
import time
from datetime import datetime
from core.ai_engine import AIAnalyzer

class PerformanceEvaluator:
    """性能评估器"""
    
    def __init__(self):
        self.analyzer = AIAnalyzer()
        self.test_results = {
            'without_mtf': [],
            'with_mtf': []
        }
        
    def generate_test_data(self, num_samples=100):
        """生成模拟测试数据"""
        print(f"[DATA] 生成 {num_samples} 个测试样本...")
        
        test_cases = []
        symbols = ['EURUSD', 'GBPUSD', 'USDJPY', 'XAUUSD', 'GBPJPY']
        
        for i in range(num_samples):
            symbol = random.choice(symbols)
            
            if symbol == 'XAUUSD':
                base_price = 2300 + random.uniform(-50, 50)
            else:
                base_price = 1.0 + random.uniform(-0.2, 0.2)
                
            spread = 0.0002 + random.uniform(-0.00005, 0.00015)
            
            # 生成市场数据
            current_price = base_price
            bid = current_price
            ask = bid + spread
            
            # 生成历史数据
            history = self._generate_history(symbol, bid, ask, 50)
            
            # 生成指标数据
            indicators = self._generate_indicators(bid, ask)
            
            # 生成多时间框架数据
            multi_timeframe = self._generate_multi_timeframe(symbol, bid, ask)
            
            # 计算预期结果（基于趋势）
            expected = self._calculate_expected(history, indicators, multi_timeframe)
            
            test_cases.append({
                'id': i,
                'symbol': symbol,
                'bid': bid,
                'ask': ask,
                'current_time': time.time(),
                'history': history,
                'indicators': indicators,
                'multi_timeframe': multi_timeframe,
                'expected': expected
            })
            
        return test_cases
        
    def _generate_history(self, symbol, base_bid, base_ask, num_bars):
        """生成历史数据"""
        history = []
        current_time = int(time.time())
        time_step = 60 if 'XAUUSD' not in symbol else 300
        
        for i in range(num_bars):
            variation = random.uniform(-0.001, 0.001) if 'XAUUSD' not in symbol else random.uniform(-1, 1)
            open_p = base_bid + variation * (num_bars - i)
            high_p = open_p + abs(random.uniform(-0.0005, 0.001)) if 'XAUUSD' not in symbol else open_p + abs(random.uniform(-0.5, 1.5))
            low_p = open_p - abs(random.uniform(-0.0005, 0.001)) if 'XAUUSD' not in symbol else open_p - abs(random.uniform(-0.5, 1.5))
            close_p = open_p + random.uniform(-0.0005, 0.0005) if 'XAUUSD' not in symbol else open_p + random.uniform(-0.5, 0.5)
            
            history.append({
                'time': current_time - time_step * (num_bars - i),
                'open': open_p,
                'high': high_p,
                'low': low_p,
                'close': close_p,
                'volume': random.randint(500, 3000)
            })
            
        return history
        
    def _generate_indicators(self, bid, ask):
        """生成技术指标数据"""
        return {
            'rsi': random.uniform(20, 80),
            'macd_main': random.uniform(-0.005, 0.005),
            'macd_signal': random.uniform(-0.005, 0.005),
            'ema50': bid + random.uniform(-0.001, 0.001),
            'ema20': bid + random.uniform(-0.0008, 0.0008),
            'ema100': bid + random.uniform(-0.0012, 0.0012),
            'atr': abs(random.uniform(0.0005, 0.002)),
            'stoch_k': random.uniform(10, 90),
            'stoch_d': random.uniform(15, 85)
        }
        
    def _generate_multi_timeframe(self, symbol, base_bid, base_ask):
        """生成多时间框架数据"""
        mtf = {}
        
        for timeframe, period in [('h1', 30), ('h4', 20), ('d1', 15)]:
            timeframe_data = {
                'history': self._generate_history(symbol, base_bid, base_ask, period),
                'indicators': self._generate_indicators(base_bid, base_ask)
            }
            mtf[timeframe] = timeframe_data
            
        return mtf
        
    def _calculate_expected(self, history, indicators, multi_timeframe):
        """计算预期结果（基于技术分析规则）"""
        bullish_score = 0
        bearish_score = 0
        
        # RSI分析
        rsi = indicators.get('rsi', 50)
        if rsi < 35:
            bullish_score += 2
        elif rsi > 65:
            bearish_score += 2
        elif rsi < 45:
            bullish_score += 1
        elif rsi > 55:
            bearish_score += 1
            
        # MACD分析
        macd_main = indicators.get('macd_main', 0)
        macd_signal = indicators.get('macd_signal', 0)
        macd_histogram = macd_main - macd_signal
        if macd_histogram > 0.0001:
            bullish_score += 2
        elif macd_histogram < -0.0001:
            bearish_score += 2
            
        # EMA排列分析
        ema20 = indicators.get('ema20', 0)
        ema50 = indicators.get('ema50', 0)
        ema100 = indicators.get('ema100', 0)
        current_price = history[0]['close'] if history else 0
        if current_price > ema20 > ema50 > ema100:
            bullish_score += 3
        elif current_price < ema20 < ema50 < ema100:
            bearish_score += 3
            
        # 多时间框架一致性
        if multi_timeframe:
            mtf_bullish = 0
            mtf_bearish = 0
            for tf in ['h1', 'h4', 'd1']:
                if tf in multi_timeframe:
                    tf_indicators = multi_timeframe[tf]['indicators']
                    tf_macd_main = tf_indicators.get('macd_main', 0)
                    tf_macd_signal = tf_indicators.get('macd_signal', 0)
                    tf_histogram = tf_macd_main - tf_macd_signal
                    if tf_histogram > 0.0001:
                        mtf_bullish += 1
                    elif tf_histogram < -0.0001:
                        mtf_bearish += 1
            if mtf_bullish > mtf_bearish:
                bullish_score += 2
            elif mtf_bearish > mtf_bullish:
                bearish_score += 2
                
        # 确定预期结果
        if bullish_score > bearish_score:
            expected = {'action': 'BUY', 'strength': bullish_score}
        elif bearish_score > bullish_score:
            expected = {'action': 'SELL', 'strength': bearish_score}
        else:
            expected = {'action': 'HOLD', 'strength': 0}
            
        return expected
        
    def run_comparison_test(self, test_cases):
        """运行对比测试"""
        print("🎯 开始性能评估对比测试...")
        print("="*60)
        
        for i, case in enumerate(test_cases):
            if (i+1) % 10 == 0:
                print(f"    进度: {i+1}/{len(test_cases)} ({(i+1)*100/len(test_cases):.0f}%)")
                
            # 测试无多时间框架分析
            action1, conf1, reason1 = self.analyzer.get_fallback_strategy(
                case['symbol'], case['bid'], case['ask'], case['indicators'], None)
            result1 = {
                'case_id': case['id'],
                'action': action1,
                'confidence': conf1,
                'reason': reason1,
                'expected': case['expected']['action'],
                'correct': action1 == case['expected']['action']
            }
            self.test_results['without_mtf'].append(result1)
            
            # 测试有多时间框架分析
            action2, conf2, reason2 = self.analyzer.get_fallback_strategy(
                case['symbol'], case['bid'], case['ask'], case['indicators'], case['multi_timeframe'])
            result2 = {
                'case_id': case['id'],
                'action': action2,
                'confidence': conf2,
                'reason': reason2,
                'expected': case['expected']['action'],
                'correct': action2 == case['expected']['action']
            }
            self.test_results['with_mtf'].append(result2)
            
        print("[OK] 对比测试完成！")
        
    def analyze_results(self):
        """分析测试结果"""
        print("\n" + "="*60)
        print("[UP] 性能分析结果")
        print("="*60)
        
        # 无多时间框架分析结果
        without_mtf = self.test_results['without_mtf']
        without_mtf_correct = sum(1 for r in without_mtf if r['correct'])
        without_mtf_accuracy = without_mtf_correct / len(without_mtf) * 100
        
        # 有多时间框架分析结果
        with_mtf = self.test_results['with_mtf']
        with_mtf_correct = sum(1 for r in with_mtf if r['correct'])
        with_mtf_accuracy = with_mtf_correct / len(with_mtf) * 100
        
        improvement = with_mtf_accuracy - without_mtf_accuracy
        
        print("\n[DATA] 准确率对比:")
        print(f"    无多时间框架分析: {without_mtf_accuracy:.2f}% ({without_mtf_correct}/{len(without_mtf)})")
        print(f"    有多时间框架分析: {with_mtf_accuracy:.2f}% ({with_mtf_correct}/{len(with_mtf)})")
        print(f"    性能提升: {improvement:+.2f}%")
        
        # 详细分析各动作的正确性
        print("\n🎯 动作分类准确率:")
        for action_type in ['BUY', 'SELL', 'HOLD']:
            print(f"\n  {action_type}:")
            
            # 无MTF
            mtf_cases = [r for r in without_mtf if r['expected'] == action_type]
            if mtf_cases:
                mtf_correct = sum(1 for r in mtf_cases if r['correct'])
                mtf_acc = mtf_correct / len(mtf_cases) * 100
                print(f"    无MTF: {mtf_acc:.2f}% ({mtf_correct}/{len(mtf_cases)})")
                
            # 有MTF
            mtf_with_cases = [r for r in with_mtf if r['expected'] == action_type]
            if mtf_with_cases:
                mtf_with_correct = sum(1 for r in mtf_with_cases if r['correct'])
                mtf_with_acc = mtf_with_correct / len(mtf_with_cases) * 100
                print(f"    有MTF: {mtf_with_acc:.2f}% ({mtf_with_correct}/{len(mtf_with_cases)})")
                
        # 置信度分析
        print("\n[DOWN] 置信度统计:")
        without_mtf_conf_avg = sum(r['confidence'] for r in without_mtf) / len(without_mtf)
        with_mtf_conf_avg = sum(r['confidence'] for r in with_mtf) / len(with_mtf)
        print(f"    无MTF平均置信度: {without_mtf_conf_avg:.3f}")
        print(f"    有MTF平均置信度: {with_mtf_conf_avg:.3f}")
        
        return {
            'without_mtf_accuracy': without_mtf_accuracy,
            'with_mtf_accuracy': with_mtf_accuracy,
            'improvement': improvement
        }
        
    def save_results(self, filename='performance_results.json'):
        """保存结果到JSON"""
        results = {
            'timestamp': datetime.now().isoformat(),
            'test_results': self.test_results,
            'analysis': self.analyze_results()
        }
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
            
        print(f"\n[OK] 结果已保存到 {filename}")

def main():
    """主函数"""
    print("="*60)
    print("🧪 多时间框架分析性能评估工具")
    print("="*60)
    
    evaluator = PerformanceEvaluator()
    
    # 生成测试数据
    test_cases = evaluator.generate_test_data(100)
    
    # 运行对比测试
    evaluator.run_comparison_test(test_cases)
    
    # 分析结果
    results = evaluator.analyze_results()
    
    # 保存结果
    evaluator.save_results()
    
    print("\n" + "="*60)
    print("[DONE] 性能评估完成！")
    if results['improvement'] > 0:
        print(f"[OK] 多时间框架分析提升了准确率！")
    else:
        print(f"ℹ️  测试完成，查看详细结果")
    print("="*60)

if __name__ == '__main__':
    main()