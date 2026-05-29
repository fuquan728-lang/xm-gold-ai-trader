# 📚 术语表

> MT5 AI交易系统相关术语和概念解释

## A

### AI引擎 (AI Engine)
系统的核心组件，负责调用DeepSeek API进行市场分析，生成交易建议。

### Auto模式 (Auto Mode)
智能通信模式，自动检测最优通信方式（Socket/WebSocket/File）并在故障时自动切换。

### API密钥 (API Key)
用于访问DeepSeek API的认证密钥，格式为`sk-`开头的字符串。

## B

### 布林带 (Bollinger Bands)
由约翰·布林格开发的技术指标，由中间移动平均线和上下标准差带组成，用于衡量市场波动性。

### 买价 (Bid Price)
交易者可以卖出货币对的价格，通常低于卖价。

## C

### 缓存 (Cache)
临时存储AI分析结果的内存区域，用于提高系统性能和减少API调用次数。

### 置信度 (Confidence)
AI对交易建议的自信程度，范围0-1，用于过滤低质量信号。

### 通信模式 (Communication Mode)
系统与MT5 EA之间的通信方式，包括Socket、WebSocket、文件和自动模式。

## D

### DeepSeek
本系统集成的AI服务提供商，提供市场分析和交易建议生成能力。

### 数据库 (Database)
存储交易记录、系统状态和性能指标的持久化存储，默认使用SQLite。

## E

### EA (Expert Advisor)
MT5平台上的自动交易程序，本系统的客户端组件。

### EMA (Exponential Moving Average)
指数移动平均线，给予近期价格更高权重的技术指标。

### 企业级增强版 (Enterprise Enhancement)
V3.0版本的核心特性，包括高可用架构、实时监控和性能优化。

## F

### 文件模式 (File Mode)
基于文件系统的通信模式，通过JSON文件在MT5和Python服务之间交换数据。

### 故障转移 (Failover)
当主通信模式失败时，自动切换到备用模式的能力。

## G

### 黄金交叉 (Golden Cross)
技术分析术语，指短期移动平均线上穿长期移动平均线，通常被视为看涨信号。

## H

### 高频交易 (High-Frequency Trading)
在极短时间内执行大量交易策略的交易方式。

### 历史数据 (Historical Data)
过去一段时间内的市场价格和交易量数据，用于技术分析和AI训练。

## I

### 集成版 (Integrated Version)
指V2.2及之后的版本，集成了多种通信模式和完整的安全策略。

## J

### JSON (JavaScript Object Notation)
轻量级数据交换格式，用于系统内部和外部API的数据传输。

## K

### K线 (Candlestick)
显示特定时间段内开盘价、收盘价、最高价和最低价的技术图表。

## L

### LRU缓存 (Least Recently Used Cache)
缓存淘汰策略，优先淘汰最久未使用的缓存条目。

### 止损 (Stop Loss)
为限制潜在亏损而设定的自动平仓价格。

## M

### MT5 (MetaTrader 5)
广泛使用的外汇和差价合约交易平台，本系统的客户端运行环境。

### MACD (Moving Average Convergence Divergence)
移动平均收敛发散指标，用于识别趋势变化和动量。

### MQL5 (MetaQuotes Language 5)
MT5平台的编程语言，用于开发EA和指标。

## N

### 非阻塞架构 (Non-blocking Architecture)
系统设计模式，允许同时处理多个请求而不互相阻塞。

## O

### 卖价 (Ask Price)
交易者可以买入货币对的价格，通常高于买价。

## P

### 面板 (Panel)
在MT5图表上显示的图形用户界面，展示系统状态和交易信息。

### 平仓 (Position Close)
关闭现有持仓的交易操作。

## Q

### 趋势线 (Trend Line)
连接价格高点或低点的直线，用于识别市场趋势方向。

## R

### RSI (Relative Strength Index)
相对强弱指数，衡量价格变动速度和幅度的动量指标。

### 风险管理 (Risk Management)
控制交易风险的一系列策略和规则，包括止损、仓位大小控制等。

## S

### Socket模式 (Socket Mode)
基于TCP Socket的通信模式，提供高性能的网络通信。

### 支撑位 (Support Level)
价格下跌时可能遇到买盘支撑，从而反弹的价格水平。

### 死叉 (Death Cross)
技术分析术语，指短期移动平均线下穿长期移动平均线，通常被视为看跌信号。

## T

### 技术分析 (Technical Analysis)
通过研究历史价格和交易量数据来预测未来价格走势的分析方法。

### 交易手数 (Trade Lot Size)
交易的基本单位，标准手为100,000单位基础货币。

## U

### UI (User Interface)
用户界面，包括MT5图表上的信息面板和Web监控仪表盘。

## V

### V2.1策略安全修复版
专注于修复核心安全问题的版本，包括持仓检查、反向平仓等功能。

### V2.2终极集成版
集成了三模式通信和完整监控系统的版本。

### V3.0企业级增强版
当前最新版本，增加了WebSocket通信、高可用架构和实时监控。

## W

### WebSocket模式
V3.0新增的双向实时通信模式，提供最低延迟的通信体验。

### Web监控仪表盘
基于Web的系统监控界面，可通过浏览器访问。

## X

### XM Global
项目名称中的经纪商名称，表示系统针对XM Global的MT5平台优化。

## Y

### 盈亏 (Profit and Loss)
交易产生的盈利或亏损。

## Z

### 阻力位 (Resistance Level)
价格上涨时可能遇到卖盘阻力，从而回落的价格水平。

### 自动交易 (Automated Trading)
由计算机程序自动执行交易决策和订单管理的交易方式。

---

## 技术缩写

### API - Application Programming Interface
应用程序编程接口

### DB - Database
数据库

### EA - Expert Advisor
专家顾问（MT5自动交易程序）

### HTTP - Hypertext Transfer Protocol
超文本传输协议

### JSON - JavaScript Object Notation
JavaScript对象表示法

### LRU - Least Recently Used
最近最少使用

### MACD - Moving Average Convergence Divergence
移动平均收敛发散

### MT5 - MetaTrader 5
第五代MetaTrader交易平台

### MQL5 - MetaQuotes Language 5
第五代MetaQuotes语言

### RSI - Relative Strength Index
相对强弱指数

### SQL - Structured Query Language
结构化查询语言

### TCP - Transmission Control Protocol
传输控制协议

### UI - User Interface
用户界面

### URL - Uniform Resource Locator
统一资源定位符

### WebSocket - Web Socket Protocol
WebSocket协议

## 交易术语

### 点 (Pip)
价格变动的最小单位，通常为0.0001（日元货币对为0.01）。

### 点差 (Spread)
买价和卖价之间的差额。

### 杠杆 (Leverage)
借入资金进行交易的能力，放大盈利和亏损。

### 保证金 (Margin)
开仓所需的资金。

### 滑点 (Slippage)
订单请求价格与实际成交价格之间的差异。

### 市价单 (Market Order)
按当前市场价格立即执行的订单。

### 挂单 (Pending Order)
在特定价格执行的未来订单。

## 系统状态术语

### 运行中 (Running)
系统正常工作的状态。

### 连接正常 (Connected)
EA与Python服务成功建立连接的状态。

### 服务可用 (Service Available)
Python服务正常运行并可处理请求的状态。

### 故障转移中 (Failover in Progress)
系统正在从一种通信模式切换到另一种模式的状态。

### 维护中 (Under Maintenance)
系统正在进行维护，暂停服务的状态。

---

> **注意**: 本术语表会随着系统发展而更新，建议定期查看最新版本。