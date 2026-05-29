//+------------------------------------------------------------------+
//|                                  AI_Trader_V3.2_Integrated.mq5        |
//|                   AI智能交易 - V3.2 集成版（实时账户数据推送）       |
//| 【核心功能】AI智能交易 + 实时账户数据推送                           |
//| 【安全特性】持仓检查、止损验证、反向平仓逻辑                         |
//| 【性能优化】非阻塞异步、纳秒级精度控制                               |
//+------------------------------------------------------------------+
#property copyright   "AI Trader V3.2 - Integrated Edition"
#property link        "https://www.mql5.com"
#property version     "3.20"
#property description "AI智能交易 - V3.2 集成版（内置实时账户数据推送功能）"
#property strict

#include <Trade\Trade.mqh>
#include <Trade\SymbolInfo.mqh>
#include <Trade\PositionInfo.mqh>
#include <Trade\OrderInfo.mqh>
#include <ChartObjects\ChartObjectsTxtControls.mqh>
#include <ChartObjects\ChartObjectsLines.mqh>
#include <ChartObjects\ChartObjectsShapes.mqh>

// ==================== 输入参数 ====================
input string InpDataPath        = "";       // 数据文件路径
input int    InpRequestInterval = 300;      // 请求间隔（秒）- 5分钟
input double InpLotSize         = 0.01;     // 交易手数
input double InpMinConfidence   = 0.65;     // 最小置信度才交易
input bool   InpShowPanel       = true;     // 显示技术分析面板
input int    InpStopLoss        = 30;       // 止损点数（0=关闭）
input int    InpTakeProfit      = 60;       // 止盈点数（0=关闭）
input bool   InpShowLines       = true;     // 显示支撑阻力线
input int    InpTrailingStop    = 30;       // 追踪止损点数（0=关闭）

// ==================== 实时账户数据推送配置 ====================
input bool   InpPushAccountData = true;     // 启用账户数据推送
input int    InpAccountDataInterval = 60;   // 账户数据推送间隔（秒）
input string InpAccountDataHost = "127.0.0.1"; // 账户数据推送服务器IP
input int    InpAccountDataPort = 8080;     // 账户数据推送服务器端口

// ==================== 安全参数（新增） ====================
input bool   InpReversePosition = true;     // 反向信号时平仓反转
input double InpMaxDailyLoss    = 0.0;      // 每日最大亏损（0=禁用）
input bool   InpEnableRiskCheck = true;     // 启用风险检查

// ==================== 性能优化参数 ====================
input int    InpPanelUpdateInt  = 1;        // 面板更新间隔（秒）
input int    InpSRUpdateInt     = 5;        // 支撑阻力更新间隔（秒）
input int    InpIndicatorCache  = 1;        // 指标缓存周期（根K线）
input bool   InpEnablePerfStats = true;     // 启用性能统计

// ==================== 全局变量 ====================
CTrade         m_trade;
CSymbolInfo    m_symbol;
CPositionInfo  m_position;
COrderInfo     m_order;
datetime       m_last_request_time;
int            m_rsi_handle;
int            m_macd_handle;
int            m_ema_handle;

// 图表对象
CChartObjectLabel m_labels[20];
CChartObjectHLine m_support_line;
CChartObjectHLine m_resistance_line;
string panel_name = "AI_Trader_Panel";

// 状态变量
string m_last_action = "HOLD";
double m_last_confidence = 0.0;
string m_last_reason = "";
double m_support_price = 0;
double m_resistance_price = 0;

// 动态止损止盈（从AI响应中解析，优先于输入参数）
int g_dynamic_sl_pips = 0;
int g_dynamic_tp_pips = 0;

// 更新时间跟踪
datetime m_last_panel_update = 0;
datetime m_last_sr_update = 0;
datetime m_last_indicator_update = 0;

// 性能统计
struct PerfStats {
   ulong  total_ticks;
   ulong  panel_updates;
   ulong  sr_updates;
   ulong  indicator_calculations;
   ulong  trade_executions;
   double avg_tick_time;
   double max_tick_time;
   datetime last_stats_print;
};
PerfStats m_perf_stats;

// 指标缓存
struct IndicatorCache {
   double rsi;
   double macd_main;
   double macd_signal;
   double ema50;
   datetime last_update;
};
IndicatorCache m_indicator_cache;

bool m_panel_created = false;

// ==================== 异步状态机（新增） ====================
enum RequestState {
   STATE_IDLE,              // 空闲
   STATE_REQUEST_WRITTEN,   // 请求已写
   STATE_WAITING_RESPONSE,  // 等待响应
   STATE_RESPONSE_RECEIVED, // 响应已收
   STATE_PROCESSING         // 处理中
};
RequestState m_request_state = STATE_IDLE;
datetime m_request_start_time = 0;

// ==================== 风险统计（新增） ====================
double m_daily_profit = 0.0;
datetime m_last_reset_day = 0;

// ==================== 实时账户数据推送状态 ====================
datetime m_last_account_data_push = 0;
bool m_account_data_enabled = false;
int m_account_data_socket = -1;

// ==================== 常量定义 ====================
const int PANEL_WIDTH = 380;
const int PANEL_HEIGHT = 490;
const int LINE_HEIGHT = 22;
const int COL1_X_OFFSET = 0;
const int COL2_X_OFFSET = 175;
const int MAX_REASON_LENGTH = 120;
const int REASON_LINE1_MAX = 70;

//+------------------------------------------------------------------+
//| 【安全修复】验证输入参数                                         |
//+------------------------------------------------------------------+
bool ValidateInputParameters() {
   bool valid = true;
   
   if(InpLotSize <= 0) {
      Print("错误: 手数必须大于0");
      valid = false;
   }
   
   if(InpMinConfidence < 0 || InpMinConfidence > 1) {
      Print("错误: 置信度必须在0-1之间");
      valid = false;
   }
   
   if(InpStopLoss < 0) {
      Print("错误: 止损点数不能为负");
      valid = false;
   }
   
   if(InpTakeProfit < 0) {
      Print("错误: 止盈点数不能为负");
      valid = false;
   }
   
   double min_lot = m_symbol.LotsMin();
   if(InpLotSize < min_lot) {
      Print("错误: 手数 ", InpLotSize, " 小于最小允许 ", min_lot);
      valid = false;
   }
   
   double max_lot = m_symbol.LotsMax();
   if(InpLotSize > max_lot) {
      Print("错误: 手数 ", InpLotSize, " 大于最大允许 ", max_lot);
      valid = false;
   }
   
   double lot_step = m_symbol.LotsStep();
   if(MathMod(InpLotSize, lot_step) > lot_step / 2) {
      Print("警告: 手数 ", InpLotSize, " 不符合步长 ", lot_step);
   }
   
   return valid;
}

//+------------------------------------------------------------------+
//| 【安全修复】检查并重置每日统计                                   |
//+------------------------------------------------------------------+
void CheckDailyReset() {
   MqlDateTime now;
   TimeToStruct(TimeCurrent(), now);
   
   MqlDateTime last;
   TimeToStruct(m_last_reset_day, last);
   
   if(m_last_reset_day == 0 || now.day != last.day || now.mon != last.mon || now.year != last.year) {
      m_daily_profit = 0.0;
      m_last_reset_day = TimeCurrent();
      Print("新交易日开始，每日盈亏已重置");
   }
}

//+------------------------------------------------------------------+
//| 【安全修复】检查每日亏损限制                                     |
//+------------------------------------------------------------------+
bool IsDailyLossLimitReached() {
   if(InpMaxDailyLoss <= 0) return false;
   
   double total_profit = 0.0;
   for(int i = PositionsTotal() - 1; i >= 0; i--) {
      if(m_position.SelectByIndex(i)) {
         if(m_position.Symbol() == _Symbol) {
            total_profit += m_position.Profit();
         }
      }
   }
   
   if(m_daily_profit + total_profit <= -InpMaxDailyLoss) {
      Print("警告: 已达每日最大亏损限制！停止交易");
      return true;
   }
   
   return false;
}

//+------------------------------------------------------------------+
//| 【实时账户数据推送】初始化账户数据推送连接                        |
//+------------------------------------------------------------------+
bool InitAccountDataConnection() {
   if(m_account_data_socket != -1) {
      SocketClose(m_account_data_socket);
      m_account_data_socket = -1;
   }
   
   // 创建Socket
   m_account_data_socket = SocketCreate();
   if(m_account_data_socket == INVALID_HANDLE) {
      Print("账户数据推送Socket创建失败");
      return false;
   }
   
   // 连接服务器
   if(!SocketConnect(m_account_data_socket, InpAccountDataHost, InpAccountDataPort, 5000)) {
      Print("账户数据推送连接失败: ", InpAccountDataHost, ":", InpAccountDataPort);
      SocketClose(m_account_data_socket);
      m_account_data_socket = -1;
      return false;
   }
   
   Print("账户数据推送连接成功: ", InpAccountDataHost, ":", InpAccountDataPort);
   return true;
}

//+------------------------------------------------------------------+
//| 【实时账户数据推送】构建账户数据JSON                             |
//+------------------------------------------------------------------+
string BuildAccountDataJson() {
   string json = "{";
   json += "\"type\":\"mql5_data\",";
   
   // 账户信息
   json += "\"account\":{";
   json += "\"balance\":" + DoubleToString(AccountInfoDouble(ACCOUNT_BALANCE), 2) + ",";
   json += "\"equity\":" + DoubleToString(AccountInfoDouble(ACCOUNT_EQUITY), 2) + ",";
   json += "\"margin\":" + DoubleToString(AccountInfoDouble(ACCOUNT_MARGIN), 2) + ",";
   json += "\"margin_free\":" + DoubleToString(AccountInfoDouble(ACCOUNT_MARGIN_FREE), 2) + ",";
   json += "\"margin_level\":" + DoubleToString(AccountInfoDouble(ACCOUNT_MARGIN_LEVEL), 2) + ",";
   json += "\"profit\":" + DoubleToString(AccountInfoDouble(ACCOUNT_PROFIT), 2) + ",";
   json += "\"currency\":\"" + AccountInfoString(ACCOUNT_CURRENCY) + "\",";
   json += "\"leverage\":" + IntegerToString(AccountInfoInteger(ACCOUNT_LEVERAGE)) + ",";
   json += "\"account\":" + IntegerToString(AccountInfoInteger(ACCOUNT_LOGIN)) + ",";
   json += "\"server\":\"" + AccountInfoString(ACCOUNT_SERVER) + "\"";
   json += "},";
   
   // 持仓信息
   json += "\"positions\":[";
   int pos_count = PositionsTotal();
   for(int i = 0; i < pos_count; i++) {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0)
         continue;
         
      if(!PositionSelectByTicket(ticket))
         continue;
         
      if(i > 0) json += ",";
      
      json += "{";
      json += "\"ticket\":" + IntegerToString((ulong)ticket) + ",";
      json += "\"symbol\":\"" + PositionGetString(POSITION_SYMBOL) + "\",";
      json += "\"type\":\"" + (PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY ? "BUY" : "SELL") + "\",";
      json += "\"volume\":" + DoubleToString(PositionGetDouble(POSITION_VOLUME), 2) + ",";
      json += "\"open_time\":\"" + TimeToString((datetime)PositionGetInteger(POSITION_TIME), TIME_DATE|TIME_SECONDS) + "\",";
      json += "\"open_price\":" + DoubleToString(PositionGetDouble(POSITION_PRICE_OPEN), (int)Digits()) + ",";
      json += "\"sl\":" + DoubleToString(PositionGetDouble(POSITION_SL), (int)Digits()) + ",";
      json += "\"tp\":" + DoubleToString(PositionGetDouble(POSITION_TP), (int)Digits()) + ",";
      json += "\"current_price\":" + DoubleToString(PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY ? SymbolInfoDouble(PositionGetString(POSITION_SYMBOL), SYMBOL_BID) : SymbolInfoDouble(PositionGetString(POSITION_SYMBOL), SYMBOL_ASK), (int)Digits()) + ",";
      json += "\"profit\":" + DoubleToString(PositionGetDouble(POSITION_PROFIT), 2) + ",";
      json += "\"swap\":" + DoubleToString(PositionGetDouble(POSITION_SWAP), 2) + ",";
      json += "\"comment\":\"" + PositionGetString(POSITION_COMMENT) + "\"";
      json += "}";
   }
   json += "],";
   
   // 历史交易（最近20笔）
   json += "\"history\":[";
   // 这里可以添加历史交易获取逻辑，为简化起见留空
   json += "]";
   
   json += "}";
   
   return json;
}

//+------------------------------------------------------------------+
//| 【实时账户数据推送】推送账户数据到服务器                          |
//+------------------------------------------------------------------+
void PushAccountDataToServer() {
   datetime now = TimeCurrent();
   if(now - m_last_account_data_push < InpAccountDataInterval)
      return;
      
   m_last_account_data_push = now;
   
   // 检查连接状态
   if(m_account_data_socket == -1 || !SocketIsConnected(m_account_data_socket)) {
      if(!InitAccountDataConnection())
         return;
   }
   
   string json_data = BuildAccountDataJson();
   string send_data = json_data + "\n";
   uchar data[];
   int len = StringToCharArray(send_data, data);
   
   int sent = SocketSend(m_account_data_socket, data, (uint)len);
   if(sent <= 0) {
      Print("账户数据推送失败");
      SocketClose(m_account_data_socket);
      m_account_data_socket = -1;
   }
   else {
      Print("账户数据推送成功 (", sent, " bytes)");
   }
}

//+------------------------------------------------------------------+
//| 性能监控初始化                                                   |
//+------------------------------------------------------------------+
void PerfInit() {
   ZeroMemory(m_perf_stats);
   m_perf_stats.last_stats_print = TimeCurrent();
}

//+------------------------------------------------------------------+
//| 性能监控开始记录                                                 |
//+------------------------------------------------------------------+
void PerfTickStart(ulong &start_time) {
   start_time = GetMicrosecondCount();
   m_perf_stats.total_ticks++;
}

//+------------------------------------------------------------------+
//| 性能监控结束记录                                                 |
//+------------------------------------------------------------------+
void PerfTickEnd(ulong start_time) {
   ulong end_time = GetMicrosecondCount();
   double tick_time = (end_time - start_time) / 1000.0;
   
   m_perf_stats.avg_tick_time = (m_perf_stats.avg_tick_time * (m_perf_stats.total_ticks - 1) + tick_time) / m_perf_stats.total_ticks;
   if(tick_time > m_perf_stats.max_tick_time)
      m_perf_stats.max_tick_time = tick_time;
}

//+------------------------------------------------------------------+
//| 打印性能统计                                                     |
//+------------------------------------------------------------------+
void PerfPrintStats() {
   datetime now = TimeCurrent();
   if(now - m_perf_stats.last_stats_print < 300)  // 每5分钟打印一次
      return;
   
   m_perf_stats.last_stats_print = now;
   
   Print("=== 性能统计 ===");
   Print("总Tick数: ", m_perf_stats.total_ticks);
   Print("面板更新次数: ", m_perf_stats.panel_updates);
   Print("支撑阻力更新次数: ", m_perf_stats.sr_updates);
   Print("指标计算次数: ", m_perf_stats.indicator_calculations);
   Print("交易执行次数: ", m_perf_stats.trade_executions);
   Print("平均Tick时间: ", DoubleToString(m_perf_stats.avg_tick_time, 3), "ms");
   Print("最大Tick时间: ", DoubleToString(m_perf_stats.max_tick_time, 3), "ms");
   Print("=================");
}

//+------------------------------------------------------------------+
//| 指标初始化                                                       |
//+------------------------------------------------------------------+
void InitIndicators() {
   m_rsi_handle = iRSI(_Symbol, PERIOD_CURRENT, 14, PRICE_CLOSE);
   m_macd_handle = iMACD(_Symbol, PERIOD_CURRENT, 12, 26, 9, PRICE_CLOSE);
   m_ema_handle = iMA(_Symbol, PERIOD_CURRENT, 50, 0, MODE_EMA, PRICE_CLOSE);
   
   if(m_rsi_handle == INVALID_HANDLE)
      Print("RSI指标初始化失败");
   if(m_macd_handle == INVALID_HANDLE)
      Print("MACD指标初始化失败");
   if(m_ema_handle == INVALID_HANDLE)
      Print("EMA指标初始化失败");
   
   m_indicator_cache.last_update = 0;
}

//+------------------------------------------------------------------+
//| 获取指标值（带缓存）                                             |
//+------------------------------------------------------------------+
void UpdateIndicatorCache() {
   datetime now = TimeCurrent();
   if(now - m_indicator_cache.last_update < 60)  // 每60秒更新一次
      return;
   
   m_indicator_cache.last_update = now;
   m_perf_stats.indicator_calculations++;
   
   double rsi_buffer[2];
   ArraySetAsSeries(rsi_buffer, true);
   if(CopyBuffer(m_rsi_handle, 0, 0, 2, rsi_buffer) > 0)
      m_indicator_cache.rsi = rsi_buffer[0];
   
   double macd_main_buffer[2];
   ArraySetAsSeries(macd_main_buffer, true);
   double macd_signal_buffer[2];
   ArraySetAsSeries(macd_signal_buffer, true);
   if(CopyBuffer(m_macd_handle, 0, 0, 2, macd_main_buffer) > 0 && CopyBuffer(m_macd_handle, 1, 0, 2, macd_signal_buffer) > 0) {
      m_indicator_cache.macd_main = macd_main_buffer[0];
      m_indicator_cache.macd_signal = macd_signal_buffer[0];
   }
   
   double ema_buffer[2];
   ArraySetAsSeries(ema_buffer, true);
   if(CopyBuffer(m_ema_handle, 0, 0, 2, ema_buffer) > 0)
      m_indicator_cache.ema50 = ema_buffer[0];
}

//+------------------------------------------------------------------+
//| 构建市场数据                                                     |
//+------------------------------------------------------------------+
string BuildMarketData() {
   UpdateIndicatorCache();
   
   string data = "{";
   data += "\"symbol\":\"" + _Symbol + "\",";
   data += "\"timestamp\":\"" + TimeToString(TimeCurrent(), TIME_DATE|TIME_SECONDS) + "\",";
   data += "\"bid\":" + DoubleToString(m_symbol.Bid(), (int)Digits()) + ",";
   data += "\"ask\":" + DoubleToString(m_symbol.Ask(), (int)Digits()) + ",";
   data += "\"spread\":" + IntegerToString((int)((m_symbol.Ask() - m_symbol.Bid()) / m_symbol.Point())) + ",";
   data += "\"rsi\":" + DoubleToString(m_indicator_cache.rsi, 2) + ",";
   data += "\"macd_main\":" + DoubleToString(m_indicator_cache.macd_main, 5) + ",";
   data += "\"macd_signal\":" + DoubleToString(m_indicator_cache.macd_signal, 5) + ",";
   data += "\"ema50\":" + DoubleToString(m_indicator_cache.ema50, (int)Digits()) + ",";
   data += "\"volume\":" + DoubleToString(m_symbol.Volume()) + ",";
   data += "\"last_action\":\"" + m_last_action + "\",";
   data += "\"last_confidence\":" + DoubleToString(m_last_confidence, 2) + ",";
   data += "\"support\":" + DoubleToString(m_support_price, (int)Digits()) + ",";
   data += "\"resistance\":" + DoubleToString(m_resistance_price, (int)Digits());
   data += "}";
   
   return data;
}

//+------------------------------------------------------------------+
//| 写入请求文件                                                     |
//+------------------------------------------------------------------+
bool WriteRequestFile(string data) {
   string filename = "ai_request.json";
   if(InpDataPath != "")
      filename = InpDataPath + "\\" + filename;
   
   int handle = FileOpen(filename, FILE_WRITE | FILE_TXT | FILE_ANSI);
   if(handle == INVALID_HANDLE) {
      Print("无法打开请求文件: ", filename);
      return false;
   }
   
   FileWriteString(handle, data);
   FileClose(handle);
   return true;
}

//+------------------------------------------------------------------+
//| 读取响应文件                                                     |
//+------------------------------------------------------------------+
bool ReadResponseFile(string &response) {
   string filename = "ai_response.json";
   if(InpDataPath != "")
      filename = InpDataPath + "\\" + filename;
   
   if(!FileIsExist(filename))
      return false;
   
   int handle = FileOpen(filename, FILE_READ | FILE_TXT | FILE_ANSI);
   if(handle == INVALID_HANDLE)
      return false;
   
   response = FileReadString(handle);
   FileClose(handle);
   FileDelete(filename);
   
   return true;
}

//+------------------------------------------------------------------+
//| 解析AI响应                                                       |
//+------------------------------------------------------------------+
bool ParseAIResponse(string json, string &action, double &confidence, string &reason) {
   // 重置动态值
   g_dynamic_sl_pips = 0;
   g_dynamic_tp_pips = 0;
   
   int start_pos = StringFind(json, "\"action\":\"");
   if(start_pos == -1) return false;
   start_pos += 10;
   int end_pos = StringFind(json, "\"", start_pos);
   if(end_pos == -1) return false;
   action = StringSubstr(json, start_pos, end_pos - start_pos);
   
   start_pos = StringFind(json, "\"confidence\":");
   if(start_pos == -1) return false;
   start_pos += 13;
   end_pos = StringFind(json, ",", start_pos);
   if(end_pos == -1) end_pos = StringFind(json, "}", start_pos);
   if(end_pos == -1) return false;
   confidence = StringToDouble(StringSubstr(json, start_pos, end_pos - start_pos));
   
   start_pos = StringFind(json, "\"reason\":\"");
   if(start_pos == -1) return false;
   start_pos += 10;
   end_pos = StringFind(json, "\"", start_pos);
   if(end_pos == -1) return false;
   reason = StringSubstr(json, start_pos, end_pos - start_pos);
   
   // 解析动态止损
   int sl_pos = StringFind(json, "\"stop_loss_pips\":");
   if(sl_pos >= 0) {
      sl_pos += 17;
      int sl_end = StringFind(json, ",", sl_pos);
      if(sl_end == -1) sl_end = StringFind(json, "}", sl_pos);
      if(sl_end > sl_pos) {
         g_dynamic_sl_pips = (int)StringToDouble(StringSubstr(json, sl_pos, sl_end - sl_pos));
         if(g_dynamic_sl_pips > 0)
            Print("解析到动态止损: ", g_dynamic_sl_pips, "点");
      }
   }
   
   // 解析动态止盈
   int tp_pos = StringFind(json, "\"take_profit_pips\":");
   if(tp_pos >= 0) {
      tp_pos += 19;
      int tp_end = StringFind(json, ",", tp_pos);
      if(tp_end == -1) tp_end = StringFind(json, "}", tp_pos);
      if(tp_end > tp_pos) {
         g_dynamic_tp_pips = (int)StringToDouble(StringSubstr(json, tp_pos, tp_end - tp_pos));
         if(g_dynamic_tp_pips > 0)
            Print("解析到动态止盈: ", g_dynamic_tp_pips, "点");
      }
   }
   
   return true;
}

//+------------------------------------------------------------------+
//| 【安全修复】检查持仓状态                                         |
//+------------------------------------------------------------------+
bool HasExistingPosition() {
   for(int i = PositionsTotal() - 1; i >= 0; i--) {
      if(m_position.SelectByIndex(i)) {
         if(m_position.Symbol() == _Symbol && m_position.Magic() == 987656) {
            return true;
         }
      }
   }
   return false;
}

//+------------------------------------------------------------------+
//| 【安全修复】执行交易                                             |
//+------------------------------------------------------------------+
void ExecuteTrade(string action, double confidence) {
   if(IsDailyLossLimitReached()) {
      Print("已达到每日亏损限制，停止交易");
      return;
   }
   
   if(confidence < InpMinConfidence) {
      Print("置信度过低 (", DoubleToString(confidence, 2), " < ", DoubleToString(InpMinConfidence, 2), ")，不执行交易");
      return;
   }
   
   bool has_position = HasExistingPosition();
   
   if(action == "BUY") {
      if(has_position) {
         if(InpReversePosition) {
            Print("发现现有持仓，执行反转交易");
            m_trade.PositionClose(_Symbol);
            Sleep(50);
         } else {
            Print("已有持仓，跳过买入信号");
            return;
         }
      }
      
      double sl_price = 0, tp_price = 0;
      int use_sl = (g_dynamic_sl_pips > 0) ? g_dynamic_sl_pips : InpStopLoss;
      int use_tp = (g_dynamic_tp_pips > 0) ? g_dynamic_tp_pips : InpTakeProfit;
      
      if(use_sl > 0)
         sl_price = m_symbol.Bid() - use_sl * m_symbol.Point();
      if(use_tp > 0)
         tp_price = m_symbol.Bid() + use_tp * m_symbol.Point();
      
      Print("BUY: SL=", use_sl, "点", (g_dynamic_sl_pips > 0 ? "(动态)" : "(固定)"),
            " TP=", use_tp, "点", (g_dynamic_tp_pips > 0 ? "(动态)" : "(固定)"));
      
      // 保证金检查
      double margin_buy;
      if(OrderCalcMargin(ORDER_TYPE_BUY, _Symbol, InpLotSize, m_symbol.Ask(), margin_buy))
      {
         if(AccountInfoDouble(ACCOUNT_FREEMARGIN) < margin_buy * 1.1)
         {
            Print("BUY保证金不足: 需要=", DoubleToString(margin_buy, 2),
                  " 可用=", DoubleToString(AccountInfoDouble(ACCOUNT_FREEMARGIN), 2));
            return;
         }
      }
      
      if(m_trade.Buy(InpLotSize, _Symbol, m_symbol.Ask(), sl_price, tp_price)) {
         m_perf_stats.trade_executions++;
         Print("买入订单执行成功");
      } else {
         Print("买入订单执行失败，错误码: ", m_trade.ResultRetcode());
      }
      
   } else if(action == "SELL") {
      if(has_position) {
         if(InpReversePosition) {
            Print("发现现有持仓，执行反转交易");
            m_trade.PositionClose(_Symbol);
            Sleep(50);
         } else {
            Print("已有持仓，跳过卖出信号");
            return;
         }
      }
      
      double sl_price = 0, tp_price = 0;
      int use_sl_s = (g_dynamic_sl_pips > 0) ? g_dynamic_sl_pips : InpStopLoss;
      int use_tp_s = (g_dynamic_tp_pips > 0) ? g_dynamic_tp_pips : InpTakeProfit;
      
      if(use_sl_s > 0)
         sl_price = m_symbol.Ask() + use_sl_s * m_symbol.Point();
      if(use_tp_s > 0)
         tp_price = m_symbol.Bid() - use_tp_s * m_symbol.Point();
      
      Print("SELL: SL=", use_sl_s, "点", (g_dynamic_sl_pips > 0 ? "(动态)" : "(固定)"),
            " TP=", use_tp_s, "点", (g_dynamic_tp_pips > 0 ? "(动态)" : "(固定)"));
      
      // 保证金检查
      double margin_sell;
      if(OrderCalcMargin(ORDER_TYPE_SELL, _Symbol, InpLotSize, m_symbol.Bid(), margin_sell))
      {
         if(AccountInfoDouble(ACCOUNT_FREEMARGIN) < margin_sell * 1.1)
         {
            Print("SELL保证金不足: 需要=", DoubleToString(margin_sell, 2),
                  " 可用=", DoubleToString(AccountInfoDouble(ACCOUNT_FREEMARGIN), 2));
            return;
         }
      }
      
      if(m_trade.Sell(InpLotSize, _Symbol, m_symbol.Bid(), sl_price, tp_price)) {
         m_perf_stats.trade_executions++;
         Print("卖出订单执行成功");
      } else {
         Print("卖出订单执行失败，错误码: ", m_trade.ResultRetcode());
      }
      
   } else if(action == "HOLD") {
      Print("AI建议持仓，不执行交易");
   }
}

//+------------------------------------------------------------------+
//| 【安全修复】管理追踪止损                                         |
//+------------------------------------------------------------------+
void ManageTrailingStop() {
   if(InpTrailingStop <= 0) return;
   
   for(int i = PositionsTotal() - 1; i >= 0; i--) {
      if(m_position.SelectByIndex(i)) {
         if(m_position.Symbol() == _Symbol && m_position.Magic() == 987656) {
            double current_price = (m_position.PositionType() == POSITION_TYPE_BUY) ? m_symbol.Bid() : m_symbol.Ask();
            double new_sl = 0;
            
            if(m_position.PositionType() == POSITION_TYPE_BUY) {
               new_sl = current_price - InpTrailingStop * m_symbol.Point();
               if(new_sl > m_position.StopLoss() && new_sl > m_position.PriceOpen()) {
                  m_trade.PositionModify(m_position.Ticket(), new_sl, m_position.TakeProfit());
               }
            } else if(m_position.PositionType() == POSITION_TYPE_SELL) {
               new_sl = current_price + InpTrailingStop * m_symbol.Point();
               if(new_sl < m_position.StopLoss() && new_sl < m_position.PriceOpen()) {
                  m_trade.PositionModify(m_position.Ticket(), new_sl, m_position.TakeProfit());
               }
            }
         }
      }
   }
}

//+------------------------------------------------------------------+
//| 更新支撑阻力线                                                   |
//+------------------------------------------------------------------+
void UpdateSupportResistanceLines() {
   datetime now = TimeCurrent();
   if(now - m_last_sr_update < InpSRUpdateInt)
      return;
   
   m_last_sr_update = now;
   m_perf_stats.sr_updates++;
   
   double high = iHigh(_Symbol, PERIOD_H1, 1);
   double low = iLow(_Symbol, PERIOD_H1, 1);
   
   m_support_price = low - (high - low) * 0.5;
   m_resistance_price = high + (high - low) * 0.5;
   
   if(InpShowLines) {
      if(ObjectFind(0, panel_name + "_support_line") < 0) {
         m_support_line.Create(0, panel_name + "_support_line", 0, m_support_price);
         m_support_line.Color(clrBlue);
         m_support_line.Style(STYLE_DASH);
         m_support_line.Width(1);
      } else {
         m_support_line.Price(m_support_price);
      }
      
      if(ObjectFind(0, panel_name + "_resistance_line") < 0) {
         m_resistance_line.Create(0, panel_name + "_resistance_line", 0, m_resistance_price);
         m_resistance_line.Color(clrRed);
         m_resistance_line.Style(STYLE_DASH);
         m_resistance_line.Width(1);
      } else {
         m_resistance_line.Price(m_resistance_price);
      }
   }
}

//+------------------------------------------------------------------+
//| 更新技术分析面板                                                 |
//+------------------------------------------------------------------+
void UpdatePanel() {
   datetime now = TimeCurrent();
   if(now - m_last_panel_update < InpPanelUpdateInt)
      return;
   
   m_last_panel_update = now;
   m_perf_stats.panel_updates++;
   
   if(!InpShowPanel) return;
   
   int x = 10;
   int y = 20;
   color bg_color = clrWhiteSmoke;
   color text_color = clrBlack;
   color value_color = clrBlue;
   
   if(!m_panel_created) {
      // 创建背景
      ObjectCreate(0, panel_name + "_bg", OBJ_RECTANGLE_LABEL, 0, 0, 0);
      ObjectSetInteger(0, panel_name + "_bg", OBJPROP_XDISTANCE, x);
      ObjectSetInteger(0, panel_name + "_bg", OBJPROP_YDISTANCE, y);
      ObjectSetInteger(0, panel_name + "_bg", OBJPROP_XSIZE, PANEL_WIDTH);
      ObjectSetInteger(0, panel_name + "_bg", OBJPROP_YSIZE, PANEL_HEIGHT);
      ObjectSetInteger(0, panel_name + "_bg", OBJPROP_BGCOLOR, bg_color);
      ObjectSetInteger(0, panel_name + "_bg", OBJPROP_BORDER_TYPE, BORDER_FLAT);
      ObjectSetInteger(0, panel_name + "_bg", OBJPROP_CORNER, CORNER_LEFT_UPPER);
      
      m_panel_created = true;
   }
   
   // 标题
   UpdateLabel(0, "=== AI智能交易系统 V3.2 ===", x + PANEL_WIDTH/2, y + 5, text_color, 10, true);
   
   // 交易状态
   UpdateLabel(1, "当前状态:", x + 10, y + 30, text_color);
   UpdateLabel(2, m_last_action, x + 100, y + 30, value_color);
   
   UpdateLabel(3, "置信度:", x + 10, y + 55, text_color);
   UpdateLabel(4, DoubleToString(m_last_confidence, 2), x + 100, y + 55, value_color);
   
   // 市场数据
   UpdateLabel(5, "市场数据:", x + 10, y + 80, text_color);
   UpdateLabel(6, _Symbol, x + 100, y + 80, value_color);
   
   UpdateLabel(7, "买价:", x + 10, y + 105, text_color);
   UpdateLabel(8, DoubleToString(m_symbol.Bid(), (int)Digits()), x + 100, y + 105, value_color);
   
   UpdateLabel(9, "卖价:", x + 10, y + 130, text_color);
   UpdateLabel(10, DoubleToString(m_symbol.Ask(), (int)Digits()), x + 100, y + 130, value_color);
   
   UpdateLabel(11, "点差:", x + 10, y + 155, text_color);
   UpdateLabel(12, IntegerToString((int)((m_symbol.Ask() - m_symbol.Bid()) / m_symbol.Point())), x + 100, y + 155, value_color);
   
   // 指标数据
   UpdateLabel(13, "技术指标:", x + 10, y + 180, text_color);
   UpdateLabel(14, "RSI: " + DoubleToString(m_indicator_cache.rsi, 1), x + 100, y + 180, value_color);
   
   UpdateLabel(15, "MACD主值: " + DoubleToString(m_indicator_cache.macd_main, 3), x + 100, y + 205, value_color);
   UpdateLabel(16, "EMA50: " + DoubleToString(m_indicator_cache.ema50, (int)Digits()), x + 100, y + 230, value_color);
   
   // 支撑阻力
   UpdateLabel(17, "支撑位:", x + 10, y + 255, text_color);
   UpdateLabel(18, DoubleToString(m_support_price, (int)Digits()), x + 100, y + 255, value_color);
   
   UpdateLabel(19, "阻力位:", x + 10, y + 280, text_color);
   UpdateLabel(20, DoubleToString(m_resistance_price, (int)Digits()), x + 100, y + 280, value_color);
   
   // 账户数据推送状态
   UpdateLabel(21, "数据推送:", x + 10, y + 305, text_color);
   UpdateLabel(22, m_account_data_enabled ? "启用" : "禁用", x + 100, y + 305, value_color);
   
   if(m_account_data_enabled) {
      UpdateLabel(23, "下次推送:", x + 10, y + 330, text_color);
      int seconds_left = InpAccountDataInterval - (int)(now - m_last_account_data_push);
      if(seconds_left < 0) seconds_left = 0;
      UpdateLabel(24, IntegerToString(seconds_left) + "秒", x + 100, y + 330, value_color);
   }
   
   // 分析原因
   UpdateLabel(25, "分析原因:", x + 10, y + 355, text_color);
   if(StringLen(m_last_reason) > REASON_LINE1_MAX) {
      UpdateLabel(26, StringSubstr(m_last_reason, 0, REASON_LINE1_MAX), x + 100, y + 355, value_color, 9);
      UpdateLabel(27, StringSubstr(m_last_reason, REASON_LINE1_MAX, StringLen(m_last_reason) - REASON_LINE1_MAX), x + 100, y + 380, value_color, 9);
   } else {
      UpdateLabel(26, m_last_reason, x + 100, y + 355, value_color, 9);
   }
   
   // 性能统计
   if(InpEnablePerfStats) {
      UpdateLabel(28, "Tick时间:", x + 10, y + 415, text_color);
      UpdateLabel(29, DoubleToString(m_perf_stats.avg_tick_time, 2) + "ms", x + 100, y + 415, value_color, 9);
   }
   
   // 版本信息
   UpdateLabel(30, "版本: V3.2 (集成版)", x + PANEL_WIDTH/2, y + PANEL_HEIGHT - 20, clrGray, 9, true);
}

//+------------------------------------------------------------------+
//| 更新标签辅助函数                                                 |
//+------------------------------------------------------------------+
void UpdateLabel(int index, string text, int x, int y, color clr, int font_size = 9, bool center = false) {
   string name = panel_name + "_" + IntegerToString(index);
   
   if(ObjectFind(0, name) < 0) {
      ObjectCreate(0, name, OBJ_LABEL, 0, 0, 0);
      ObjectSetInteger(0, name, OBJPROP_CORNER, CORNER_LEFT_UPPER);
      ObjectSetInteger(0, name, OBJPROP_FONTSIZE, font_size);
   }
   
   ObjectSetInteger(0, name, OBJPROP_XDISTANCE, x);
   ObjectSetInteger(0, name, OBJPROP_YDISTANCE, y);
   ObjectSetString(0, name, OBJPROP_TEXT, text);
   ObjectSetInteger(0, name, OBJPROP_COLOR, clr);
   
   if(center) {
      ObjectSetInteger(0, name, OBJPROP_ANCHOR, ANCHOR_CENTER);
   } else {
      ObjectSetInteger(0, name, OBJPROP_ANCHOR, ANCHOR_LEFT_UPPER);
   }
}

//+------------------------------------------------------------------+
//| EA初始化函数                                                     |
//+------------------------------------------------------------------+
int OnInit() {
   m_symbol.Name(_Symbol);
   m_trade.SetExpertMagicNumber(987656);
   m_trade.SetMarginMode();
   m_trade.SetTypeFillingBySymbol(_Symbol);
   
   if(!ValidateInputParameters()) {
      Print("参数验证失败！请检查输入参数");
      return INIT_FAILED;
   }
   
   InitIndicators();
   PerfInit();
   CheckDailyReset();
   
   m_last_request_time = 0;
   m_last_action = "HOLD";
   m_last_confidence = 0.0;
   m_last_reason = "";
   m_request_state = STATE_IDLE;
   
   // 初始化账户数据推送
   if(InpPushAccountData) {
      m_account_data_enabled = true;
      if(!InitAccountDataConnection()) {
         Print("账户数据推送连接初始化失败");
      }
   }
   
   UpdateSupportResistanceLines();
   UpdatePanel();
   
   Print("=== AI交易EA V3.2 - 集成版已初始化 ===");
   Print("版本: 3.20");
   Print("核心特性: AI智能交易 + 实时账户数据推送");
   Print("安全特性: 持仓检查/反转、止损验证、每日亏损限制");
   if(InpTrailingStop > 0)
      Print("追踪止损: ", IntegerToString(InpTrailingStop), "点");
   if(InpStopLoss > 0)
      Print("止损: ", IntegerToString(InpStopLoss), "点");
   if(InpTakeProfit > 0)
      Print("止盈: ", IntegerToString(InpTakeProfit), "点");
   if(InpMaxDailyLoss > 0)
      Print("每日亏损限制: ", DoubleToString(InpMaxDailyLoss, 2));
   Print("面板更新间隔: ", InpPanelUpdateInt, "秒");
   Print("指标缓存周期: ", InpIndicatorCache, "根K线");
   Print("性能监控: ", InpEnablePerfStats ? "开启" : "关闭");
   Print("账户数据推送: ", InpPushAccountData ? "启用" : "禁用");
   Print("账户数据推送间隔: ", InpAccountDataInterval, "秒");
   Print("账户数据服务器: ", InpAccountDataHost, ":", InpAccountDataPort);
   Print("=========================================");
   
   return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
//| EA反初始化函数                                                   |
//+------------------------------------------------------------------+
void OnDeinit(const int reason) {
   if(m_rsi_handle != INVALID_HANDLE)
      IndicatorRelease(m_rsi_handle);
   if(m_macd_handle != INVALID_HANDLE)
      IndicatorRelease(m_macd_handle);
   if(m_ema_handle != INVALID_HANDLE)
      IndicatorRelease(m_ema_handle);
   
   // 关闭账户数据推送连接
   if(m_account_data_socket != -1) {
      SocketClose(m_account_data_socket);
      m_account_data_socket = -1;
      Print("账户数据推送连接已关闭");
   }
   
   if(InpShowPanel && m_panel_created) {
      for(int i = 0; i < 20; i++) {
         string name = panel_name + "_" + IntegerToString(i);
         if(ObjectFind(0, name) >= 0)
            ObjectDelete(0, name);
      }
      if(ObjectFind(0, panel_name + "_bg") >= 0)
         ObjectDelete(0, panel_name + "_bg");
   }
   
   if(ObjectFind(0, panel_name + "_support_line") >= 0)
      ObjectDelete(0, panel_name + "_support_line");
   if(ObjectFind(0, panel_name + "_resistance_line") >= 0)
      ObjectDelete(0, panel_name + "_resistance_line");
   
   m_panel_created = false;
   Print("AI交易EA V3.2已停止");
   PerfPrintStats();
}

//+------------------------------------------------------------------+
//| 【性能优化】EA主循环（非阻塞异步）                               |
//+------------------------------------------------------------------+
void OnTick() {
   ulong tick_start_time = 0;
   if(InpEnablePerfStats)
      PerfTickStart(tick_start_time);
   
   datetime now = TimeCurrent();
   
   UpdateSupportResistanceLines();
   UpdatePanel();
   ManageTrailingStop();
   CheckDailyReset();
   
   // 推送账户数据（如果启用）
   if(m_account_data_enabled) {
      PushAccountDataToServer();
   }
   
   switch(m_request_state) {
      case STATE_IDLE:
         if(now - m_last_request_time >= InpRequestInterval) {
            if(!m_symbol.RefreshRates())
               break;
            
            m_last_request_time = now;
            
            string filename = "ai_response.json";
            if(FileIsExist(filename))
               FileDelete(filename);
            
            string market_data = BuildMarketData();
            
            Print("写入请求文件...");
            if(WriteRequestFile(market_data)) {
               m_request_state = STATE_REQUEST_WRITTEN;
               m_request_start_time = now;
               Print("等待AI响应...");
            }
         }
         break;
         
      case STATE_REQUEST_WRITTEN:
      case STATE_WAITING_RESPONSE:
         {
         m_request_state = STATE_WAITING_RESPONSE;
         
         string response;
         if(ReadResponseFile(response)) {
            m_request_state = STATE_RESPONSE_RECEIVED;
            
            if(response != "") {
               Print("收到AI响应");
               
               string action;
               double confidence;
               string reason;
               
               if(ParseAIResponse(response, action, confidence, reason)) {
                  m_last_action = action;
                  m_last_confidence = confidence;
                  m_last_reason = reason;
                  
                  Print("AI建议: ", action, " 置信度: ", DoubleToString(confidence, 2));
                  Print("分析原因: ", reason);
                  ExecuteTrade(action, confidence);
                  UpdatePanel();
               }
            } else {
               Print("未收到AI响应内容");
            }
            m_request_state = STATE_IDLE;
         } else if(now - m_request_start_time > 10) {
            Print("等待响应超时，重置状态");
            m_request_state = STATE_IDLE;
         }
         break;
         }
   }
   
   if(InpEnablePerfStats) {
      PerfTickEnd(tick_start_time);
      PerfPrintStats();
   }
}

//+------------------------------------------------------------------+