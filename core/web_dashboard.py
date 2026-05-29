#!/usr/bin/env python3
"""
MT5 AI Trading System - Enhanced Web Dashboard Module (V3.1)
Flask-based web monitoring dashboard with charts and statistics
"""

import os
import json
import threading
import time
from datetime import datetime
from typing import Dict, List, Any, Optional
from flask import Flask, render_template_string, jsonify, request
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.logger import logger
from core.mql5_data import get_mql5_data_manager

class WebDashboard:
    """Enhanced Flask-based web dashboard"""
    
    def __init__(self, host: str = "127.0.0.1", port: int = 8000):
        self.host = host
        self.port = port
        self.app = Flask(__name__)
        self.server = None
        self.thread = None
        self.running = False
        
        self.stats = {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "start_time": datetime.now().isoformat(),
            "uptime": 0,
            "total_pnl": 0.0,
            "total_trades": 0,
            "winning_trades": 0,
            "losing_trades": 0,
            "win_rate": 0.0,
            "avg_pnl": 0.0
        }
        
        # 交易统计（来自MQL5）
        self.trade_stats = {
            "total_trades": 0,
            "win_trades": 0,
            "loss_trades": 0,
            "win_rate": 0.0,
            "total_profit": 0.0,
            "total_loss": 0.0,
            "profit_factor": 0.0,
            "avg_win": 0.0,
            "avg_loss": 0.0,
            "buy_trades": 0,
            "sell_trades": 0,
            "sl_hits": 0,
            "tp_hits": 0
        }
        
        self.recent_signals: List[Dict[str, Any]] = []
        self.recent_trades: List[Dict[str, Any]] = []
        self.pnl_history: List[Dict[str, Any]] = []
        self.max_signals = 50
        self.max_trades = 20
        self.max_pnl_points = 100
        
        self.mql5_manager = get_mql5_data_manager()
        
        self.system_status = {
            "websocket": "disconnected",
            "socket": "disconnected",
            "file_mode": "disconnected",
            "ai_engine": "idle",
            "database": "connected"
        }
        
        self._setup_routes()
        
        logger.info(f"Web Dashboard initialized (host={host}, port={port})")
    
    def _setup_routes(self):
        """Setup Flask routes"""
        
        @self.app.route('/')
        def index():
            """Enhanced main dashboard page"""
            html_template = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>MT5 AI交易系统 - V3.1 仪表盘</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: 'Segoe UI', Arial, sans-serif; background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); color: white; padding: 20px; }
        .container { max-width: 1600px; margin: 0 auto; }
        h1 { text-align: center; margin-bottom: 30px; color: #00ff88; font-size: 2.5rem; }
        h2 { color: #00ccff; margin-bottom: 15px; border-bottom: 2px solid #333; padding-bottom: 10px; font-size: 1.4rem; }
        
        .status-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin-bottom: 30px; }
        .status-card { background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1); border-radius: 12px; padding: 20px; text-align: center; transition: transform 0.2s ease; }
        .status-card:hover { transform: translateY(-3px); border-color: rgba(0,255,136,0.3); }
        .status-card h3 { font-size: 0.9rem; opacity: 0.8; margin-bottom: 8px; text-transform: uppercase; letter-spacing: 1px; }
        .status-card .value { font-size: 2.2rem; font-weight: bold; color: #00ff88; }
        .status-card .value.warning { color: #ffaa00; }
        .status-card .value.danger { color: #ff4444; }
        .status-card .value.positive { color: #00ff88; }
        .status-card .value.negative { color: #ff4444; }
        .status-card .sub-value { font-size: 0.85rem; opacity: 0.6; margin-top: 5px; }
        
        .two-column { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 30px; }
        @media (max-width: 900px) { .two-column { grid-template-columns: 1fr; } }
        
        .section { background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.1); border-radius: 12px; padding: 25px; margin-bottom: 30px; }
        .chart-container { height: 300px; position: relative; }
        
        .signals-section { background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.1); border-radius: 12px; padding: 25px; margin-bottom: 30px; }
        .signal-item { background: rgba(255,255,255,0.03); border-left: 4px solid #00ff88; padding: 15px; margin-bottom: 12px; border-radius: 8px; display: flex; justify-content: space-between; align-items: center; }
        .signal-item.sell { border-left-color: #ff4444; }
        .signal-item.hold { border-left-color: #ffaa00; }
        .signal-info { flex: 1; }
        .signal-symbol { font-weight: bold; font-size: 1.1rem; }
        .signal-meta { font-size: 0.85rem; opacity: 0.7; margin-top: 5px; }
        .signal-action { font-weight: bold; font-size: 1.1rem; padding: 8px 16px; border-radius: 8px; }
        .signal-action.buy { background: #00ff88; color: #001; }
        .signal-action.sell { background: #ff4444; color: white; }
        .signal-action.hold { background: #ffaa00; color: #001; }
        
        table { width: 100%; border-collapse: collapse; }
        th, td { padding: 12px 15px; text-align: left; border-bottom: 1px solid rgba(255,255,255,0.1); }
        th { background: rgba(255,255,255,0.05); font-weight: 600; color: #00ccff; }
        tr:hover { background: rgba(255,255,255,0.02); }
        .trade-buy { color: #00ff88; }
        .trade-sell { color: #ff4444; }
        .positive { color: #00ff88; }
        .negative { color: #ff4444; }
        
        .status-badge { display: inline-block; padding: 4px 10px; border-radius: 5px; font-size: 0.85rem; }
        .status-online { background: rgba(0,255,136,0.2); color: #00ff88; }
        .status-offline { background: rgba(255,68,68,0.2); color: #ff4444; }
        .status-idle { background: rgba(255,170,0,0.2); color: #ffaa00; }
        
        .empty-state { text-align: center; padding: 50px; opacity: 0.5; }
        
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }
        .online-indicator { width: 12px; height: 12px; background: #00ff88; border-radius: 50%; display: inline-block; margin-right: 8px; animation: pulse 1.5s infinite; }
        
        .footer { text-align: center; margin-top: 50px; opacity: 0.6; padding: 20px; font-size: 0.9rem; }
    </style>
</head>
<body>
    <div class="container">
        <h1><span class="online-indicator"></span>MT5 AI交易系统 - V3.1 仪表盘</h1>
        
        <div class="status-grid">
            <div class="status-card">
                <h3>总请求数</h3>
                <div class="value" id="totalRequests">0</div>
            </div>
            <div class="status-card">
                <h3>成功请求</h3>
                <div class="value" id="successfulRequests">0</div>
            </div>
            <div class="status-card">
                <h3>总交易数</h3>
                <div class="value" id="totalTrades">0</div>
            </div>
            <div class="status-card">
                <h3>总盈亏</h3>
                <div class="value" id="totalPnl">0</div>
            </div>
            <div class="status-card">
                <h3>胜率</h3>
                <div class="value" id="winRate">0%</div>
            </div>
            <div class="status-card">
                <h3>运行时间</h3>
                <div class="value" id="uptime">0s</div>
            </div>
        </div>
        
        <div class="section">
            <h2>系统状态</h2>
            <div class="status-grid" style="grid-template-columns: repeat(5, 1fr);">
                <div class="status-card">
                    <h3>WebSocket</h3>
                    <div class="status-badge status-offline" id="wsStatus">未连接</div>
                </div>
                <div class="status-card">
                    <h3>Socket</h3>
                    <div class="status-badge status-offline" id="socketStatus">未连接</div>
                </div>
                <div class="status-card">
                    <h3>文件模式</h3>
                    <div class="status-badge status-offline" id="fileStatus">未连接</div>
                </div>
                <div class="status-card">
                    <h3>AI引擎</h3>
                    <div class="status-badge status-idle" id="aiStatus">待机</div>
                </div>
                <div class="status-card">
                    <h3>数据库</h3>
                    <div class="status-badge status-online" id="dbStatus">已连接</div>
                </div>
            </div>
        </div>
        
        <div class="section">
            <h2>账户信息</h2>
            <div class="status-grid" style="grid-template-columns: repeat(4, 1fr);">
                <div class="status-card">
                    <h3>账户余额</h3>
                    <div class="value" id="accountBalance">0.00</div>
                    <div class="sub-value" id="accountCurrency">USD</div>
                </div>
                <div class="status-card">
                    <h3>账户净值</h3>
                    <div class="value" id="accountEquity">0.00</div>
                </div>
                <div class="status-card">
                    <h3>浮动盈亏</h3>
                    <div class="value" id="accountProfit">0.00</div>
                </div>
                <div class="status-card">
                    <h3>可用保证金</h3>
                    <div class="value" id="accountMarginFree">0.00</div>
                </div>
            </div>
            <div style="margin-top: 15px; opacity: 0.7;">
                <span>账号: <span id="accountNumber">-</span></span>
                <span style="margin-left: 20px;">服务器: <span id="accountServer">-</span></span>
                <span style="margin-left: 20px;">杠杆: <span id="accountLeverage">-</span></span>
                <span style="margin-left: 20px;">更新时间: <span id="mql5LastUpdate">-</span></span>
            </div>
        </div>
        
        <div class="section">
            <h2>当前持仓</h2>
            <table>
                <thead>
                    <tr>
                        <th>订单号</th>
                        <th>品种</th>
                        <th>方向</th>
                        <th>手数</th>
                        <th>开仓时间</th>
                        <th>开仓价</th>
                        <th>当前价</th>
                        <th>盈亏</th>
                    </tr>
                </thead>
                <tbody id="positionsTable">
                    <tr><td colspan="8" class="empty-state">暂无持仓</td></tr>
                </tbody>
            </table>
        </div>
        
        <div class="two-column">
            <div class="section">
                <h2>盈亏历史</h2>
                <div class="chart-container">
                    <canvas id="pnlChart"></canvas>
                </div>
            </div>
            <div class="section">
                <h2>信号分布</h2>
                <div class="chart-container">
                    <canvas id="signalChart"></canvas>
                </div>
            </div>
        </div>
        
        <div class="section">
            <h2>最近交易</h2>
            <table>
                <thead>
                    <tr>
                        <th>时间</th>
                        <th>品种</th>
                        <th>方向</th>
                        <th>入场</th>
                        <th>出场</th>
                        <th>盈亏</th>
                        <th>状态</th>
                    </tr>
                </thead>
                <tbody id="tradesTable">
                    <tr><td colspan="7" class="empty-state">暂无交易</td></tr>
                </tbody>
            </table>
        </div>
        
        <div class="signals-section">
            <h2>最近信号</h2>
            <div id="signalsList">
                <div class="empty-state">等待信号...</div>
            </div>
        </div>
        
        <div class="footer">
            <p>WebSocket: ws://127.0.0.1:8081 | Socket: 127.0.0.1:8080 | 文件模式</p>
            <p>MT5 AI交易系统 - 企业版 V3.1</p>
        </div>
    </div>
    
    <script>
        let pnlChart, signalChart;
        
        async function fetchStats() {
            try {
                const response = await fetch('/api/stats');
                const data = await response.json();
                document.getElementById('totalRequests').textContent = data.total_requests;
                document.getElementById('successfulRequests').textContent = data.successful_requests;
                document.getElementById('totalTrades').textContent = data.total_trades;
                document.getElementById('winRate').textContent = (data.win_rate * 100).toFixed(1) + '%';
                document.getElementById('uptime').textContent = data.uptime;
                
                const pnlEl = document.getElementById('totalPnl');
                const pnl = data.total_pnl;
                pnlEl.textContent = pnl.toFixed(2);
                pnlEl.className = 'value ' + (pnl >= 0 ? 'positive' : 'negative');
            } catch(e) {
                console.error('Error fetching stats:', e);
            }
        }
        
        async function fetchSignals() {
            try {
                const response = await fetch('/api/signals');
                const data = await response.json();
                const container = document.getElementById('signalsList');
                
                if(data.signals.length === 0) {
                    container.innerHTML = '<div class="empty-state">等待信号...</div>';
                } else {
                    container.innerHTML = data.signals.map(signal => {
                        let actionText = signal.action;
                        if(actionText === 'BUY') actionText = '买入';
                        if(actionText === 'SELL') actionText = '卖出';
                        if(actionText === 'HOLD') actionText = '观望';
                        
                        return `
                        <div class="signal-item ${signal.action.toLowerCase()}">
                            <div class="signal-info">
                                <div class="signal-symbol">${signal.symbol}</div>
                                <div class="signal-meta">${signal.time} | 置信度: ${signal.confidence}</div>
                            </div>
                            <div class="signal-action ${signal.action.toLowerCase()}">${actionText}</div>
                        </div>
                        `;
                    }).join('');
                }
            } catch(e) {
                console.error('Error fetching signals:', e);
            }
        }
        
        async function fetchTrades() {
            try {
                const response = await fetch('/api/trades');
                const data = await response.json();
                const container = document.getElementById('tradesTable');
                
                if(data.trades.length === 0) {
                    container.innerHTML = '<tr><td colspan="7" class="empty-state">暂无交易</td></tr>';
                } else {
                    container.innerHTML = data.trades.map(trade => {
                        const actionClass = trade.action.toLowerCase() === 'buy' ? 'trade-buy' : 'trade-sell';
                        const pnlClass = trade.pnl >= 0 ? 'positive' : 'negative';
                        
                        let actionText = trade.action;
                        if(actionText === 'BUY') actionText = '买入';
                        if(actionText === 'SELL') actionText = '卖出';
                        
                        let statusText = trade.status;
                        if(statusText === 'open') statusText = '持仓中';
                        if(statusText === 'closed') statusText = '已平仓';
                        
                        return `
                            <tr>
                                <td>${trade.time}</td>
                                <td class="${actionClass}">${trade.symbol}</td>
                                <td class="${actionClass}">${actionText}</td>
                                <td>${trade.entry_price}</td>
                                <td>${trade.exit_price}</td>
                                <td class="${pnlClass}">${trade.pnl.toFixed(2)}</td>
                                <td>${statusText}</td>
                            </tr>
                        `;
                    }).join('');
                }
            } catch(e) {
                console.error('Error fetching trades:', e);
            }
        }
        
        async function fetchCharts() {
            try {
                const response = await fetch('/api/chart-data');
                const data = await response.json();
                updateCharts(data);
            } catch(e) {
                console.error('Error fetching chart data:', e);
            }
        }
        
        function updateCharts(data) {
            const pnlCtx = document.getElementById('pnlChart').getContext('2d');
            if(pnlChart) pnlChart.destroy();
            
            pnlChart = new Chart(pnlCtx, {
                type: 'line',
                data: {
                    labels: data.pnl_labels,
                    datasets: [{
                        label: '累计盈亏',
                        data: data.pnl_data,
                        borderColor: '#00ff88',
                        backgroundColor: 'rgba(0,255,136,0.1)',
                        fill: true,
                        tension: 0.4
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { labels: { color: 'white' } }
                    },
                    scales: {
                        x: { ticks: { color: 'rgba(255,255,255,0.7)' }, grid: { color: 'rgba(255,255,255,0.1)' } },
                        y: { ticks: { color: 'rgba(255,255,255,0.7)' }, grid: { color: 'rgba(255,255,255,0.1)' } }
                    }
                }
            });
            
            const signalCtx = document.getElementById('signalChart').getContext('2d');
            if(signalChart) signalChart.destroy();
            
            signalChart = new Chart(signalCtx, {
                type: 'doughnut',
                data: {
                    labels: ['买入', '卖出', '观望'],
                    datasets: [{
                        data: [data.buy_count, data.sell_count, data.hold_count],
                        backgroundColor: ['#00ff88', '#ff4444', '#ffaa00']
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { labels: { color: 'white' } }
                    }
                }
            });
        }
        
        async function fetchMql5Data() {
            try {
                const response = await fetch('/api/mql5');
                const data = await response.json();
                
                document.getElementById('accountBalance').textContent = data.account.balance.toFixed(2);
                document.getElementById('accountEquity').textContent = data.account.equity.toFixed(2);
                
                const profitEl = document.getElementById('accountProfit');
                profitEl.textContent = data.account.profit.toFixed(2);
                profitEl.className = 'value ' + (data.account.profit >= 0 ? 'positive' : 'negative');
                
                document.getElementById('accountMarginFree').textContent = data.account.margin_free.toFixed(2);
                document.getElementById('accountCurrency').textContent = data.account.currency;
                document.getElementById('accountNumber').textContent = data.account.account || '-';
                document.getElementById('accountServer').textContent = data.account.server || '-';
                document.getElementById('accountLeverage').textContent = '1:' + data.account.leverage;
                document.getElementById('mql5LastUpdate').textContent = data.last_update;
                
                const posTable = document.getElementById('positionsTable');
                if(data.positions && data.positions.length > 0) {
                    posTable.innerHTML = data.positions.map(pos => {
                        const dirClass = pos.type.toLowerCase() === 'buy' ? 'trade-buy' : 'trade-sell';
                        const dirText = pos.type === 'BUY' ? '买入' : pos.type === 'SELL' ? '卖出' : pos.type;
                        const pnlClass = pos.profit >= 0 ? 'positive' : 'negative';
                        
                        return `
                            <tr>
                                <td>${pos.ticket}</td>
                                <td class="${dirClass}">${pos.symbol}</td>
                                <td class="${dirClass}">${dirText}</td>
                                <td>${pos.volume.toFixed(2)}</td>
                                <td>${pos.open_time}</td>
                                <td>${pos.open_price}</td>
                                <td>${pos.current_price}</td>
                                <td class="${pnlClass}">${pos.profit.toFixed(2)}</td>
                            </tr>
                        `;
                    }).join('');
                } else {
                    posTable.innerHTML = '<tr><td colspan="8" class="empty-state">暂无持仓</td></tr>';
                }
            } catch(e) {
                console.error('获取 MQL5 数据失败:', e);
            }
        }
        
        fetchStats();
        fetchSignals();
        fetchTrades();
        fetchCharts();
        fetchMql5Data();
        
        setInterval(fetchStats, 3000);
        setInterval(fetchSignals, 3000);
        setInterval(fetchTrades, 5000);
        setInterval(fetchCharts, 5000);
        setInterval(fetchMql5Data, 2000);
    </script>
</body>
</html>
"""
            return render_template_string(html_template)
        
        @self.app.route('/api/stats')
        def get_stats():
            """Get enhanced system stats"""
            uptime = int(time.time() - datetime.fromisoformat(self.stats["start_time"]).timestamp())
            mins, secs = divmod(uptime, 60)
            hours, mins = divmod(mins, 60)
            uptime_str = f"{hours}小时 {mins}分钟 {secs}秒" if hours > 0 else f"{mins}分钟 {secs}秒"
            
            return jsonify({
                "total_requests": self.stats["total_requests"],
                "successful_requests": self.stats["successful_requests"],
                "failed_requests": self.stats["failed_requests"],
                "total_trades": self.stats["total_trades"],
                "total_pnl": self.stats["total_pnl"],
                "win_rate": self.stats["win_rate"],
                "uptime": uptime_str,
                "trade_stats": self.trade_stats
            })
        
        @self.app.route('/api/trade-stats')
        def get_trade_stats():
            """Get detailed trading statistics"""
            return jsonify(self.trade_stats)
        
        @self.app.route('/api/signals')
        def get_signals():
            """Get recent trading signals"""
            return jsonify({"signals": self.recent_signals})
        
        @self.app.route('/api/trades')
        def get_trades():
            """Get recent trades"""
            return jsonify({"trades": self.recent_trades})
        
        @self.app.route('/api/chart-data')
        def get_chart_data():
            """Get chart data"""
            buy_count = sum(1 for s in self.recent_signals if s.get('action') == 'BUY')
            sell_count = sum(1 for s in self.recent_signals if s.get('action') == 'SELL')
            hold_count = sum(1 for s in self.recent_signals if s.get('action') == 'HOLD')
            
            pnl_labels = [p.get('time', '') for p in self.pnl_history[-20:]]
            pnl_data = [p.get('pnl', 0) for p in self.pnl_history[-20:]]
            
            return jsonify({
                "buy_count": buy_count,
                "sell_count": sell_count,
                "hold_count": hold_count,
                "pnl_labels": pnl_labels,
                "pnl_data": pnl_data
            })
        
        @self.app.route('/api/mql5')
        def get_mql5_data():
            """获取 MQL5 账户和持仓数据"""
            try:
                data = self.mql5_manager.get_dashboard_data()
                return jsonify(data)
            except Exception as e:
                logger.error(f"获取 MQL5 数据失败: {e}")
                return jsonify({"error": str(e)}), 500
        
        @self.app.route('/api/health')
        def health_check():
            """Health check endpoint"""
            return jsonify({"status": "ok", "version": "V3.1"})
    
    def add_signal(self, signal_data: Dict[str, Any]):
        """Add a new trading signal to dashboard"""
        signal = {
            "symbol": signal_data.get("symbol", "N/A"),
            "action": signal_data.get("action", "HOLD"),
            "confidence": signal_data.get("confidence", 0),
            "reason": signal_data.get("reason", ""),
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        self.recent_signals.insert(0, signal)
        
        if len(self.recent_signals) > self.max_signals:
            self.recent_signals = self.recent_signals[:self.max_signals]
    
    def add_trade(self, trade_data: Dict[str, Any]):
        """Add a new trade to dashboard"""
        pnl_value = trade_data.get("pnl", 0)
        trade = {
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "symbol": trade_data.get("symbol", "N/A"),
            "action": trade_data.get("action", "HOLD"),
            "entry_price": trade_data.get("entry_price", 0),
            "exit_price": trade_data.get("exit_price", 0),
            "pnl": pnl_value if pnl_value is not None else 0,
            "status": trade_data.get("status", "open")
        }
        self.recent_trades.insert(0, trade)
        
        if len(self.recent_trades) > self.max_trades:
            self.recent_trades = self.recent_trades[:self.max_trades]
        
        # 只有当pnl不为None时才更新胜率和总盈利
        if pnl_value is not None:
            self.stats["total_trades"] += 1
            if pnl_value > 0:
                self.stats["winning_trades"] += 1
            elif pnl_value < 0:
                self.stats["losing_trades"] += 1
            
            total = self.stats["winning_trades"] + self.stats["losing_trades"]
            self.stats["win_rate"] = self.stats["winning_trades"] / total if total > 0 else 0
            self.stats["total_pnl"] += pnl_value
            
            self.pnl_history.append({
                "time": trade["time"],
                "pnl": self.stats["total_pnl"]
            })
        
        if len(self.pnl_history) > self.max_pnl_points:
            self.pnl_history = self.pnl_history[-self.max_pnl_points:]
    
    def record_request(self, success: bool = True):
        """Record a request"""
        self.stats["total_requests"] += 1
        if success:
            self.stats["successful_requests"] += 1
        else:
            self.stats["failed_requests"] += 1
    
    def update_system_status(self, status: Dict[str, str]):
        """Update system status"""
        self.system_status.update(status)
    
    def start(self):
        """Start the Flask web server in background thread"""
        if self.running:
            logger.warning("Web Dashboard already running!")
            return
        
        self.running = True
        
        def run_server():
            try:
                self.server = self.app.run(
                    host=self.host,
                    port=self.port,
                    debug=False,
                    use_reloader=False
                )
            except Exception as e:
                logger.error(f"Web Dashboard error: {e}")
                self.running = False
        
        self.thread = threading.Thread(target=run_server, daemon=True)
        self.thread.start()
        
        logger.info(f"Starting Web Dashboard at http://{self.host}:{self.port}")
        time.sleep(1)
        logger.info(f"Web Dashboard running at http://{self.host}:{self.port}")
    
    def stop(self):
        """Stop the web server"""
        self.running = False
        if self.server:
            try:
                self.server.shutdown()
            except Exception:
                pass
        logger.info("Web Dashboard stopped")
