#!/usr/bin/env python3
"""
V3.1 - Enhanced Dashboard Test
"""
import sys
import time
import random

sys.path.insert(0, str(__import__('pathlib').Path(__file__).parent))

from core.web_dashboard import WebDashboard
from core.logger import setup_logger, logger

def test_dashboard():
    print("=" * 70)
    print("Testing Enhanced Web Dashboard")
    print("=" * 70)
    
    dashboard = WebDashboard()
    dashboard.start()
    
    print("\nGenerating test signals and trades...")
    
    symbols = ['EURUSD', 'GBPUSD', 'USDJPY', 'XAUUSD']
    actions = ['BUY', 'SELL', 'HOLD']
    
    for i in range(10):
        symbol = random.choice(symbols)
        action = random.choice(actions)
        confidence = 0.5 + random.random() * 0.4
        bid = 1.08 + random.random() * 0.02
        ask = bid + 0.0002
        
        # Add signal
        signal = {
            'symbol': symbol,
            'action': action,
            'confidence': confidence,
            'reason': f'Market analysis {i+1}'
        }
        dashboard.add_signal(signal)
        
        # If trade signal, add trade
        if action in ['BUY', 'SELL'] and confidence > 0.5:
            entry_price = ask if action == 'BUY' else bid
            pnl = (random.random() - 0.5) * 10
            
            trade = {
                'symbol': symbol,
                'action': action,
                'entry_price': entry_price,
                'exit_price': entry_price + pnl/1000,
                'pnl': pnl,
                'status': 'closed'
            }
            dashboard.add_trade(trade)
        
        dashboard.record_request(True)
        print(f"Added signal {i+1}: {symbol} - {action}")
        time.sleep(0.5)
    
    print("\n" + "=" * 70)
    print("Dashboard test data generated!")
    print("Please visit: http://127.0.0.1:8000")
    print("=" * 70)
    print("\nPress Ctrl+C to stop...")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        dashboard.stop()
        print("\nStopped")

if __name__ == "__main__":
    logger = setup_logger(level=20)
    test_dashboard()
