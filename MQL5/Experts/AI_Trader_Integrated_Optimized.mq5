//+------------------------------------------------------------------+
//|                                     AI_Trader_Integrated_Optimized.mq5 |
//|                   AI智能交易 + 技术分析面板 - 优化版             |
//| 性能优化: 减少重绘、优化指标计算、添加性能监控                  |
//+------------------------------------------------------------------+
#property copyright   "AI Trader Integrated - Optimized"
#property link        "https://www.mql5.com"
#property version     "3.10"
#property description "AI智能交易 + 技术分析面板 - 优化版"
#property strict

#include <Trade\Trade.mqh>
#include <Trade\SymbolInfo.mqh>
#include <Trade\PositionInfo.mqh>
#include <ChartObjects\ChartObjectsTxtControls.mqh>
#include <ChartObjects\ChartObjectsLines.mqh>
#include <ChartObjects\ChartObjectsShapes.mqh>

// ==================== 输入参数 ====================
input string InpDataPath        = "";       // 数据文件路径
input int    InpRequestInterval = 300;      // 请求间隔（秒）
input double InpLotSize         = 0.01;     // 交易手数
input double InpMinConfidence   = 0.75;     // 最小置信度才交易
input bool   InpShowPanel       = true;      // 显示技术分析面板
input int    InpStopLoss        = 30;       // 止损点数
input bool   InpShowLines       = true;      // 显示支撑阻力线
input int    InpTrailingStop    = 30;       // 追踪止损点数

// ==================== 性能优化参数 ====================
input int    InpPanelUpdateInt  = 1;        // 面板更新间隔（秒）
input int    InpSRUpdateInt     = 5;        // 支撑阻力更新间隔（秒）
input int    InpIndicatorCache  = 1;        // 指标缓存周期（根K线）
input bool   InpEnablePerfStats = true;      // 启用性能统计

// ==================== 全局变量 ====================
CTrade         m_trade;
CSymbolInfo    m_symbol;
CPositionInfo  m_position;
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

// ==================== 常量定义 ====================
const int PANEL_WIDTH = 380;
const int PANEL_HEIGHT = 460;
const int LINE_HEIGHT = 22;
const int COL1_X_OFFSET = 0;
const int COL2_X_OFFSET = 175;
const int MAX_REASON_LENGTH = 120;
const int REASON_LINE1_MAX = 70;

//+------------------------------------------------------------------+
//| 性能监控函数                                                     |
//+------------------------------------------------------------------+
void PerfInit() {
   ZeroMemory(m_perf_stats);
   m_perf_stats.last_stats_print = TimeCurrent();
}

void PerfTickStart(ulong &start_time) {
   start_time = GetMicrosecondCount();
}

void PerfTickEnd(ulong start_time) {
   ulong elapsed = GetMicrosecondCount() - start_time;
   double elapsed_sec = (double)elapsed / 1000000.0;
   
   m_perf_stats.total_ticks++;
   m_perf_stats.avg_tick_time = (m_perf_stats.avg_tick_time * (m_perf_stats.total_ticks - 1) + elapsed_sec) / m_perf_stats.total_ticks;
   if(elapsed_sec > m_perf_stats.max_tick_time)
      m_perf_stats.max_tick_time = elapsed_sec;
}

void PerfPrintStats() {
   if(!InpEnablePerfStats) return;
   
   datetime now = TimeCurrent();
   if(now - m_perf_stats.last_stats_print < 60) return;
   
   m_perf_stats.last_stats_print = now;
   
   Print("=== 性能统计 ===");
   Print("总Tick数: ", m_perf_stats.total_ticks);
   Print("面板更新: ", m_perf_stats.panel_updates);
   Print("支撑阻力更新: ", m_perf_stats.sr_updates);
   Print("指标计算: ", m_perf_stats.indicator_calculations);
   Print("平均Tick时间: ", DoubleToString(m_perf_stats.avg_tick_time * 1000, 2), "ms");
   Print("最大Tick时间: ", DoubleToString(m_perf_stats.max_tick_time * 1000, 2), "ms");
   Print("================");
}

//+------------------------------------------------------------------+
//| 初始化技术指标                                                   |
//+------------------------------------------------------------------+
void InitIndicators() {
   m_rsi_handle = iRSI(_Symbol, _Period, 14, PRICE_CLOSE);
   m_macd_handle = iMACD(_Symbol, _Period, 12, 26, 9, PRICE_CLOSE);
   m_ema_handle = iMA(_Symbol, _Period, 50, 0, MODE_EMA, PRICE_CLOSE);
   ZeroMemory(m_indicator_cache);
}

//+------------------------------------------------------------------+
//| 获取指标值（带缓存）                                             |
//+------------------------------------------------------------------+
bool GetCachedIndicators(double &rsi, double &macd_main, double &macd_signal, double &ema50) {
   datetime now = TimeCurrent();
   
   if(now - m_indicator_cache.last_update < InpIndicatorCache) {
      rsi = m_indicator_cache.rsi;
      macd_main = m_indicator_cache.macd_main;
      macd_signal = m_indicator_cache.macd_signal;
      ema50 = m_indicator_cache.ema50;
      return true;
   }
   
   bool success = true;
   
   if(m_rsi_handle != INVALID_HANDLE) {
      double rsi_buffer[];
      if(CopyBuffer(m_rsi_handle, 0, 0, 1, rsi_buffer) > 0)
         rsi = rsi_buffer[0];
      else
         success = false;
   } else {
      success = false;
   }
   
   if(m_macd_handle != INVALID_HANDLE) {
      double macd_main_buffer[], macd_signal_buffer[];
      if(CopyBuffer(m_macd_handle, 0, 0, 1, macd_main_buffer) > 0)
         macd_main = macd_main_buffer[0];
      else
         success = false;
      if(CopyBuffer(m_macd_handle, 1, 0, 1, macd_signal_buffer) > 0)
         macd_signal = macd_signal_buffer[0];
      else
         success = false;
   } else {
      success = false;
   }
   
   if(m_ema_handle != INVALID_HANDLE) {
      double ema_buffer[];
      if(CopyBuffer(m_ema_handle, 0, 0, 1, ema_buffer) > 0)
         ema50 = ema_buffer[0];
      else
         success = false;
   } else {
      success = false;
   }
   
   if(success) {
      m_indicator_cache.rsi = rsi;
      m_indicator_cache.macd_main = macd_main;
      m_indicator_cache.macd_signal = macd_signal;
      m_indicator_cache.ema50 = ema50;
      m_indicator_cache.last_update = now;
      m_perf_stats.indicator_calculations++;
   }
   
   return success;
}

//+------------------------------------------------------------------+
//| 计算支撑阻力位（优化版）                                         |
//+------------------------------------------------------------------+
void CalculateSupportResistance() {
   int bars = MathMin(20, Bars(_Symbol, _Period));
   if(bars < 5) return;
   
   double highest = 0;
   double lowest = 999999;
   
   double high_buffer[], low_buffer[];
   ArraySetAsSeries(high_buffer, true);
   ArraySetAsSeries(low_buffer, true);
   
   if(CopyHigh(_Symbol, _Period, 1, bars, high_buffer) > 0 && 
      CopyLow(_Symbol, _Period, 1, bars, low_buffer) > 0) {
      for(int i = 0; i < bars; i++) {
         if(high_buffer[i] > highest) highest = high_buffer[i];
         if(low_buffer[i] < lowest) lowest = low_buffer[i];
      }
      m_support_price = lowest;
      m_resistance_price = highest;
   }
}

//+------------------------------------------------------------------+
//| 更新支撑阻力线（优化版）                                         |
//+------------------------------------------------------------------+
void UpdateSupportResistanceLines() {
   if(!InpShowLines) return;
   
   datetime now = TimeCurrent();
   if(now - m_last_sr_update < InpSRUpdateInt) return;
   
   m_last_sr_update = now;
   m_perf_stats.sr_updates++;
   
   CalculateSupportResistance();
   
   static double last_support = 0;
   static double last_resistance = 0;
   
   if(m_support_price > 0 && MathAbs(m_support_price - last_support) > m_symbol.Point() * 10) {
      last_support = m_support_price;
      
      if(ObjectFind(0, panel_name + "_support_line") >= 0) {
         ObjectDelete(0, panel_name + "_support_line");
      }
      m_support_line.Create(0, panel_name + "_support_line", 0, m_support_price);
      m_support_line.Color(clrLimeGreen);
      m_support_line.Style(STYLE_SOLID);
      m_support_line.Width(2);
      m_support_line.Description("Support");
   }
   
   if(m_resistance_price > 0 && MathAbs(m_resistance_price - last_resistance) > m_symbol.Point() * 10) {
      last_resistance = m_resistance_price;
      
      if(ObjectFind(0, panel_name + "_resistance_line") >= 0) {
         ObjectDelete(0, panel_name + "_resistance_line");
      }
      m_resistance_line.Create(0, panel_name + "_resistance_line", 0, m_resistance_price);
      m_resistance_line.Color(clrRed);
      m_resistance_line.Style(STYLE_SOLID);
      m_resistance_line.Width(2);
      m_resistance_line.Description("Resistance");
   }
}

//+------------------------------------------------------------------+
//| 创建/更新技术分析面板（优化版）                                  |
//+------------------------------------------------------------------+
void UpdatePanel() {
   if(!InpShowPanel) return;
   
   datetime now = TimeCurrent();
   if(now - m_last_panel_update < InpPanelUpdateInt && m_panel_created) return;
   
   m_last_panel_update = now;
   m_perf_stats.panel_updates++;
   
   if(!m_panel_created) {
      CreatePanelObjects();
      m_panel_created = true;
   }
   
   UpdatePanelContent();
}

//+------------------------------------------------------------------+
//| 创建面板对象（只调用一次）                                       |
//+------------------------------------------------------------------+
void CreatePanelObjects() {
   int chart_w = (int)ChartGetInteger(0, CHART_WIDTH_IN_PIXELS);
   int x = chart_w - PANEL_WIDTH - 10;
   int y = 15;
   int start_y = y;
   
   for(int i = 0; i < 20; i++) {
      string name = panel_name + "_" + IntegerToString(i);
      if(ObjectFind(0, name) >= 0)
         ObjectDelete(0, name);
   }
   if(ObjectFind(0, panel_name + "_bg") >= 0)
      ObjectDelete(0, panel_name + "_bg");
   
   ObjectCreate(0, panel_name + "_bg", OBJ_RECTANGLE_LABEL, 0, 0, 0);
   ObjectSetInteger(0, panel_name + "_bg", OBJPROP_XDISTANCE, 0);
   ObjectSetInteger(0, panel_name + "_bg", OBJPROP_YDISTANCE, start_y - 10);
   ObjectSetInteger(0, panel_name + "_bg", OBJPROP_XSIZE, PANEL_WIDTH);
   ObjectSetInteger(0, panel_name + "_bg", OBJPROP_YSIZE, PANEL_HEIGHT);
   ObjectSetInteger(0, panel_name + "_bg", OBJPROP_CORNER, CORNER_RIGHT_UPPER);
   ObjectSetInteger(0, panel_name + "_bg", OBJPROP_COLOR, clrLightGray);
   ObjectSetInteger(0, panel_name + "_bg", OBJPROP_STYLE, STYLE_SOLID);
   ObjectSetInteger(0, panel_name + "_bg", OBJPROP_WIDTH, 1);
   ObjectSetInteger(0, panel_name + "_bg", OBJPROP_BACK, true);
   ObjectSetInteger(0, panel_name + "_bg", OBJPROP_ZORDER, 0);
   ObjectSetInteger(0, panel_name + "_bg", OBJPROP_FILL, true);
   ObjectSetInteger(0, panel_name + "_bg", OBJPROP_BGCOLOR, clrWhite);
   
   CreateLabel(0, x, y, "【🤖 AI智能交易】", clrBlue, 16, "Arial Bold");
   y += LINE_HEIGHT + 4;
   
   CreateLabel(1, x, y, "━━━ AI建议 ━━━", clrDarkGray, 11, "Arial Bold");
   y += LINE_HEIGHT;
   
   CreateLabel(2, x, y, "等待中...", clrDarkGray, 14, "Arial Bold");
   CreateLabel(3, x + COL2_X_OFFSET, y, "置信: 0.00", clrDarkGray, 11, "Arial Bold");
   y += LINE_HEIGHT;
   
   CreateLabel(9, x, y, "分析: --", clrDarkSlateGray, 10, "Arial");
   y += LINE_HEIGHT;
   
   CreateLabel(15, x, y, "", clrDarkSlateGray, 10, "Arial");
   y += LINE_HEIGHT + 6;
   
   CreateLabel(4, x, y, "━━━ 市场数据 ━━━", clrDarkGray, 11, "Arial Bold");
   y += LINE_HEIGHT;
   
   CreateLabel(5, x, y, "现价: --", clrBlack, 12, "Arial Bold");
   CreateLabel(6, x + COL2_X_OFFSET, y, "点差: --", clrDarkOrange, 11, "Arial Bold");
   y += LINE_HEIGHT;
   
   CreateLabel(7, x, y, "RSI: --", clrDarkGreen, 11, "Arial Bold");
   CreateLabel(8, x + COL2_X_OFFSET, y, "EMA50: --", clrPurple, 11, "Arial Bold");
   y += LINE_HEIGHT + 6;
   
   CreateLabel(13, x, y, "━━━ 技术指标 ━━━", clrDarkGray, 11, "Arial Bold");
   y += LINE_HEIGHT;
   
   CreateLabel(14, x, y, "MACD: --", clrDarkViolet, 11, "Arial Bold");
   y += LINE_HEIGHT + 6;
   
   CreateLabel(10, x, y, "━━━ 支撑阻力 ━━━", clrDarkGray, 11, "Arial Bold");
   y += LINE_HEIGHT;
   
   CreateLabel(11, x, y, "支撑: --", clrLimeGreen, 11, "Arial Bold");
   CreateLabel(12, x + COL2_X_OFFSET, y, "阻力: --", clrRed, 11, "Arial Bold");
}

//+------------------------------------------------------------------+
//| 辅助函数：创建标签                                               |
//+------------------------------------------------------------------+
void CreateLabel(int index, int x, int y, string text, color clr, int font_size, string font) {
   m_labels[index].Create(0, panel_name + "_" + IntegerToString(index), 0, x, y);
   m_labels[index].Description(text);
   m_labels[index].Color(clr);
   m_labels[index].FontSize(font_size);
   m_labels[index].Font(font);
   m_labels[index].Anchor(ANCHOR_RIGHT_UPPER);
}

//+------------------------------------------------------------------+
//| 更新面板内容                                                     |
//+------------------------------------------------------------------+
void UpdatePanelContent() {
   color action_color = clrDarkGray;
   string action_text = "等待中...";
   if(m_last_action == "BUY") {
      action_color = clrLime;
      action_text = "【🟢 买入】";
   } else if(m_last_action == "SELL") {
      action_color = clrRed;
      action_text = "【🔴 卖出】";
   } else if(m_last_action == "HOLD") {
      action_text = "【⚪ 观望】";
   }
   
   m_labels[2].Description(action_text);
   m_labels[2].Color(action_color);
   m_labels[3].Description("置信: " + DoubleToString(m_last_confidence, 2));
   
   string reason_line1 = "";
   string reason_line2 = "";
   if(StringLen(m_last_reason) > 0) {
      if(StringLen(m_last_reason) > REASON_LINE1_MAX) {
         int mid = REASON_LINE1_MAX;
         while(mid > 40 && StringGetCharacter(m_last_reason, mid) != ' ')
            mid--;
         if(mid < 40) mid = REASON_LINE1_MAX;
         
         reason_line1 = "分析: " + StringSubstr(m_last_reason, 0, mid);
         reason_line2 = StringSubstr(m_last_reason, mid);
      } else {
         reason_line1 = "分析: " + m_last_reason;
         reason_line2 = "";
      }
   } else {
      reason_line1 = "分析: --";
      reason_line2 = "";
   }
   
   m_labels[9].Description(reason_line1);
   m_labels[15].Description(reason_line2);
   
   m_labels[5].Description("现价: " + DoubleToString((m_symbol.Bid() + m_symbol.Ask()) / 2, m_symbol.Digits()));
   
   int point_value = (int)MathPow(10, m_symbol.Digits());
   double spread_points = (m_symbol.Ask() - m_symbol.Bid()) * point_value;
   m_labels[6].Description("点差: " + DoubleToString(spread_points, 0) + "点");
   
   double rsi, macd_main, macd_signal, ema50;
   if(GetCachedIndicators(rsi, macd_main, macd_signal, ema50)) {
      m_labels[7].Description("RSI: " + DoubleToString(rsi, 2));
      m_labels[7].Color(rsi > 70 ? clrRed : (rsi < 30 ? clrLime : clrDarkGreen));
      
      m_labels[8].Description("EMA50: " + DoubleToString(ema50, m_symbol.Digits()));
      
      m_labels[14].Description("MACD: " + DoubleToString(macd_main, 5));
      m_labels[14].Color(macd_main > 0 ? clrLimeGreen : (macd_main < 0 ? clrRed : clrDarkViolet));
   }
   
   if(m_support_price > 0)
      m_labels[11].Description("支撑: " + DoubleToString(m_support_price, m_symbol.Digits()));
   if(m_resistance_price > 0)
      m_labels[12].Description("阻力: " + DoubleToString(m_resistance_price, m_symbol.Digits()));
   
   ChartRedraw();
}

//+------------------------------------------------------------------+
//| 获取历史K线数据（优化版）                                       |
//+------------------------------------------------------------------+
string GetHistoryData(int count) {
   string json = "[";
   int actual_count = MathMin(count, Bars(_Symbol, _Period));
   
   double open_buffer[], high_buffer[], low_buffer[], close_buffer[];
   long volume_buffer[];
   datetime time_buffer[];
   
   ArraySetAsSeries(open_buffer, true);
   ArraySetAsSeries(high_buffer, true);
   ArraySetAsSeries(low_buffer, true);
   ArraySetAsSeries(close_buffer, true);
   ArraySetAsSeries(volume_buffer, true);
   ArraySetAsSeries(time_buffer, true);
   
   bool has_data = (CopyOpen(_Symbol, _Period, 0, actual_count, open_buffer) > 0 &&
                   CopyHigh(_Symbol, _Period, 0, actual_count, high_buffer) > 0 &&
                   CopyLow(_Symbol, _Period, 0, actual_count, low_buffer) > 0 &&
                   CopyClose(_Symbol, _Period, 0, actual_count, close_buffer) > 0 &&
                   CopyTime(_Symbol, _Period, 0, actual_count, time_buffer) > 0 &&
                   CopyTickVolume(_Symbol, _Period, 0, actual_count, volume_buffer) > 0);
   
   if(has_data) {
      for(int i = 0; i < actual_count; i++) {
         if(i > 0) json += ",";
         json += "{";
         json += "\"time\":" + IntegerToString((int)time_buffer[i]) + ",";
         json += "\"open\":" + DoubleToString(open_buffer[i], m_symbol.Digits()) + ",";
         json += "\"high\":" + DoubleToString(high_buffer[i], m_symbol.Digits()) + ",";
         json += "\"low\":" + DoubleToString(low_buffer[i], m_symbol.Digits()) + ",";
         json += "\"close\":" + DoubleToString(close_buffer[i], m_symbol.Digits()) + ",";
         json += "\"volume\":" + IntegerToString((int)volume_buffer[i]);
         json += "}";
      }
   }
   
   json += "]";
   return json;
}

//+------------------------------------------------------------------+
//| 获取技术指标数据（优化版）                                       |
//+------------------------------------------------------------------+
string GetIndicatorsData() {
   double rsi, macd_main, macd_signal, ema50;
   GetCachedIndicators(rsi, macd_main, macd_signal, ema50);
   
   string json = "{";
   json += "\"rsi\":" + DoubleToString(rsi, 2) + ",";
   json += "\"macd_main\":" + DoubleToString(macd_main, 5) + ",";
   json += "\"macd_signal\":" + DoubleToString(macd_signal, 5) + ",";
   json += "\"ema50\":" + DoubleToString(ema50, m_symbol.Digits());
   json += "}";
   
   return json;
}

//+------------------------------------------------------------------+
//| 构建市场数据JSON                                                 |
//+------------------------------------------------------------------+
string BuildMarketData() {
   string json = "{";
   json += "\"symbol\":\"" + _Symbol + "\",";
   json += "\"bid\":" + DoubleToString(m_symbol.Bid(), m_symbol.Digits()) + ",";
   json += "\"ask\":" + DoubleToString(m_symbol.Ask(), m_symbol.Digits()) + ",";
   json += "\"time\":" + IntegerToString((int)TimeCurrent()) + ",";
   json += "\"history\":" + GetHistoryData(30) + ",";
   json += "\"indicators\":" + GetIndicatorsData();
   json += "}";
   return json;
}

//+------------------------------------------------------------------+
//| 写入请求文件                                                     |
//+------------------------------------------------------------------+
bool WriteRequestFile(string data) {
   string filename = "ai_request.json";
   int file_handle = FileOpen(filename, FILE_WRITE|FILE_TXT|FILE_ANSI);
   
   if(file_handle == INVALID_HANDLE) {
      Print("无法打开请求文件: ", filename);
      return false;
   }
   
   FileWrite(file_handle, data);
   FileClose(file_handle);
   return true;
}

//+------------------------------------------------------------------+
//| 读取响应文件                                                     |
//+------------------------------------------------------------------+
bool ReadResponseFile(string &response) {
   string filename = "ai_response.json";
   
   if(!FileIsExist(filename))
      return false;
   
   int file_handle = FileOpen(filename, FILE_READ|FILE_TXT|FILE_UNICODE);
   
   if(file_handle == INVALID_HANDLE)
      return false;
   
   response = "";
   while(!FileIsEnding(file_handle)) {
      response += FileReadString(file_handle);
   }
   
   FileClose(file_handle);
   FileDelete(filename);
   return true;
}

//+------------------------------------------------------------------+
//| 解析AI响应                                                       |
//+------------------------------------------------------------------+
bool ParseAIResponse(string response, string &action, double &confidence, string &reason) {
   action = "HOLD";
   confidence = 0.0;
   reason = "";
   
   int buy_pos = StringFind(response, "\"action\":\"BUY\"");
   int buy_pos2 = StringFind(response, "\"action\": \"BUY\"");
   int sell_pos = StringFind(response, "\"action\":\"SELL\"");
   int sell_pos2 = StringFind(response, "\"action\": \"SELL\"");
   
   if(buy_pos >= 0 || buy_pos2 >= 0)
      action = "BUY";
   else if(sell_pos >= 0 || sell_pos2 >= 0)
      action = "SELL";
   
   int conf_pos = StringFind(response, "\"confidence\":");
   if(conf_pos >= 0) {
      int start = conf_pos + 14;
      int end = StringFind(response, ",", start);
      if(end < 0)
         end = StringFind(response, "}", start);
      if(end > start) {
         string conf_str = StringSubstr(response, start, end - start);
         confidence = StringToDouble(conf_str);
      }
   }
   
   int reason_pos = StringFind(response, "\"reason\":");
   if(reason_pos >= 0) {
      int start = reason_pos + 9;
      while(start < StringLen(response) && StringGetCharacter(response, start) != '"')
         start++;
      start++;
      
      int end = start;
      int quote_count = 1;
      while(end < StringLen(response)) {
         if(StringGetCharacter(response, end) == '"') {
            if(end > 0 && StringGetCharacter(response, end - 1) != '\\') {
               quote_count++;
               if(quote_count == 2)
                  break;
            }
         }
         end++;
      }
      
      if(end > start) {
         reason = StringSubstr(response, start, end - start);
         if(StringLen(reason) > 100)
            reason = StringSubstr(reason, 0, 97) + "...";
      }
   }
   
   return true;
}

//+------------------------------------------------------------------+
//| 点数转价格                                                       |
//+------------------------------------------------------------------+
double PointsToPrice(int points) {
   double point = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
   return (double)points * point;
}

//+------------------------------------------------------------------+
//| 执行AI建议的交易                                                 |
//+------------------------------------------------------------------+
void ExecuteTrade(string action, double confidence) {
   if(confidence < InpMinConfidence) {
      Print("置信度 ", DoubleToString(confidence, 2), " 低于阈值 ", DoubleToString(InpMinConfidence, 2), "，不交易");
      return;
   }
   
   m_perf_stats.trade_executions++;
   double sl_price = 0;
   
   if(action == "BUY") {
      if(InpStopLoss > 0)
         sl_price = m_symbol.Ask() - PointsToPrice(InpStopLoss);
      
      if(m_trade.PositionOpen(_Symbol, ORDER_TYPE_BUY, InpLotSize, m_symbol.Ask(), sl_price, 0.0)) {
         Print("AI建议: 开多单成功 (止损:", DoubleToString(sl_price, m_symbol.Digits()), ")");
      } else {
         Print("开多单失败: ", m_trade.ResultComment());
      }
   } else if(action == "SELL") {
      if(InpStopLoss > 0)
         sl_price = m_symbol.Bid() + PointsToPrice(InpStopLoss);
      
      if(m_trade.PositionOpen(_Symbol, ORDER_TYPE_SELL, InpLotSize, m_symbol.Bid(), sl_price, 0.0)) {
         Print("AI建议: 开空单成功 (止损:", DoubleToString(sl_price, m_symbol.Digits()), ")");
      } else {
         Print("开空单失败: ", m_trade.ResultComment());
      }
   }
}

//+------------------------------------------------------------------+
//| 管理追踪止损                                                     |
//+------------------------------------------------------------------+
void ManageTrailingStop() {
   if(InpTrailingStop <= 0)
      return;
   
   for(int i = PositionsTotal() - 1; i >= 0; i--) {
      if(!m_position.SelectByIndex(i))
         continue;
      
      string pos_symbol = PositionGetString(POSITION_SYMBOL);
      if(pos_symbol != _Symbol)
         continue;
      
      ulong pos_ticket = PositionGetInteger(POSITION_TICKET);
      double pos_open_price = PositionGetDouble(POSITION_PRICE_OPEN);
      ENUM_POSITION_TYPE pos_type = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
      double pos_sl = PositionGetDouble(POSITION_SL);
      
      double trailing_distance = PointsToPrice(InpTrailingStop);
      double new_sl = 0;
      
      if(pos_type == POSITION_TYPE_BUY) {
         double profit_level = m_symbol.Bid() - trailing_distance;
         if(profit_level > pos_open_price) {
            if(pos_sl == 0 || profit_level > pos_sl) {
               new_sl = profit_level;
            }
         }
      } else if(pos_type == POSITION_TYPE_SELL) {
         double profit_level = m_symbol.Ask() + trailing_distance;
         if(profit_level < pos_open_price) {
            if(pos_sl == 0 || profit_level < pos_sl) {
               new_sl = profit_level;
            }
         }
      }
      
      if((pos_sl == 0 || new_sl > 0) && new_sl != pos_sl) {
         if(m_trade.PositionModify(pos_ticket, new_sl, 0.0)) {
            Print("追踪止损更新: 新止损=", DoubleToString(new_sl, m_symbol.Digits()));
         } else {
            Print("追踪止损更新失败: ", m_trade.ResultComment());
         }
      }
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
   
   InitIndicators();
   PerfInit();
   
   m_last_request_time = 0;
   m_last_action = "HOLD";
   m_last_confidence = 0.0;
   m_last_reason = "";
   
   UpdateSupportResistanceLines();
   UpdatePanel();
   
   Print("AI交易EA(优化版)已初始化");
   if(InpTrailingStop > 0)
      Print("追踪止损: ", IntegerToString(InpTrailingStop), "点");
   if(InpStopLoss > 0)
      Print("止损: ", IntegerToString(InpStopLoss), "点");
   Print("面板更新间隔: ", InpPanelUpdateInt, "秒");
   Print("指标缓存周期: ", InpIndicatorCache, "根K线");
   Print("性能监控: ", InpEnablePerfStats ? "开启" : "关闭");
   
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
   Print("AI交易EA(优化版)已停止");
   PerfPrintStats();
}

//+------------------------------------------------------------------+
//| EA主循环函数（优化版）                                          |
//+------------------------------------------------------------------+
void OnTick() {
   ulong tick_start_time = 0;
   if(InpEnablePerfStats)
      PerfTickStart(tick_start_time);
   
   datetime now = TimeCurrent();
   
   UpdateSupportResistanceLines();
   UpdatePanel();
   ManageTrailingStop();
   
   if(now - m_last_request_time < InpRequestInterval) {
      if(InpEnablePerfStats)
         PerfTickEnd(tick_start_time);
      return;
   }
   
   if(!m_symbol.RefreshRates()) {
      if(InpEnablePerfStats)
         PerfTickEnd(tick_start_time);
      return;
   }
   
   m_last_request_time = now;
   
   string filename = "ai_response.json";
   if(FileIsExist(filename))
      FileDelete(filename);
   
   string market_data = BuildMarketData();
   string response;
   
   Print("写入请求文件...");
   
   if(WriteRequestFile(market_data)) {
      Print("等待AI响应...");
      
      int wait_count = 0;
      while(wait_count < 100) {
         Sleep(100);
         if(ReadResponseFile(response))
            break;
         wait_count++;
      }
      
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
         Print("未收到AI响应");
      }
   }
   
   if(InpEnablePerfStats) {
      PerfTickEnd(tick_start_time);
      PerfPrintStats();
   }
}
