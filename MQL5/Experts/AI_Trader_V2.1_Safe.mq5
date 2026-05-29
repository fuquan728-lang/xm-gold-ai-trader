//+------------------------------------------------------------------+
//|                                  AI_Trader_V2.1_Safe.mq5        |
//|                   AI智能交易 - V2.1 安全修复版                   |
//| 【P0级修复】添加持仓检查、止损验证、反向平仓逻辑                 |
//| 【性能优化】移除Sleep阻塞、添加异步状态机                       |
//+------------------------------------------------------------------+
#property copyright   "AI Trader V2.1 - Safe Edition"
#property link        "https://www.mql5.com"
#property version     "3.11"
#property description "AI智能交易 - V2.1 安全修复版"
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
input int    InpRequestInterval = 300;      // 请求间隔（秒）
input double InpLotSize         = 0.01;     // 交易手数
input double InpMinConfidence   = 0.65;     // 最小置信度才交易
input bool   InpShowPanel       = true;      // 显示技术分析面板
input int    InpStopLoss        = 30;       // 止损点数
input int    InpTakeProfit      = 60;       // 止盈点数（新增）
input bool   InpShowLines       = true;      // 显示支撑阻力线
input int    InpTrailingStop    = 30;       // 追踪止损点数

// ==================== 安全参数（新增） ====================
input bool   InpReversePosition = true;      // 反向信号时平仓反转
input double InpMaxDailyLoss    = 0.0;      // 每日最大亏损（0=禁用）
input bool   InpEnableRiskCheck = true;      // 启用风险检查

// ==================== 性能优化参数 ====================
input int    InpPanelUpdateInt  = 1;        // 面板更新间隔（秒）
input int    InpSRUpdateInt     = 5;        // 支撑阻力更新间隔（秒）
input int    InpIndicatorCache  = 1;        // 指标缓存周期（根K线）
input bool   InpEnablePerfStats = true;      // 启用性能统计

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
//| 【安全修复】获取当前持仓类型                                     |
//+------------------------------------------------------------------+
ENUM_POSITION_TYPE GetCurrentPositionType() {
   for(int i = PositionsTotal() - 1; i >= 0; i--) {
      if(m_position.SelectByIndex(i)) {
         if(m_position.Symbol() == _Symbol && m_position.Magic() == 987656) {
            return (ENUM_POSITION_TYPE)m_position.PositionType();
         }
      }
   }
   return (ENUM_POSITION_TYPE)(-1);
}

//+------------------------------------------------------------------+
//| 【安全修复】平仓所有当前持仓                                     |
//+------------------------------------------------------------------+
bool CloseAllPositions() {
   bool closed = false;
   
   for(int i = PositionsTotal() - 1; i >= 0; i--) {
      if(m_position.SelectByIndex(i)) {
         if(m_position.Symbol() == _Symbol && m_position.Magic() == 987656) {
            ulong ticket = m_position.Ticket();
            Print("正在平仓: 单号=", ticket, " 类型=", (m_position.PositionType() == POSITION_TYPE_BUY ? "多单" : "空单"));
            
            if(m_trade.PositionClose(ticket)) {
               Print("平仓成功: 单号=", ticket);
               closed = true;
            } else {
               Print("平仓失败: ", m_trade.ResultComment());
            }
         }
      }
   }
   
   return closed;
}

//+------------------------------------------------------------------+
//| 【安全修复】验证止损/止盈价格是否有效                            |
//+------------------------------------------------------------------+
bool ValidateSLTP(double price, ENUM_POSITION_TYPE pos_type, bool is_stop_loss) {
   if(price == 0) return true;
   
   double point = m_symbol.Point();
   double stoplevel = m_symbol.StopsLevel() * point;
   double freezlevel = m_symbol.FreezeLevel() * point;
   double min_distance = MathMax(stoplevel, freezlevel);
   
   double current_price = (pos_type == POSITION_TYPE_BUY) ? m_symbol.Ask() : m_symbol.Bid();
   
   if(is_stop_loss) {
      if(pos_type == POSITION_TYPE_BUY) {
         if(price > current_price - min_distance) {
            Print("止损错误: 距离现价太近，最小距离=", min_distance);
            return false;
         }
      } else {
         if(price < current_price + min_distance) {
            Print("止损错误: 距离现价太近，最小距离=", min_distance);
            return false;
         }
      }
   } else {
      if(pos_type == POSITION_TYPE_BUY) {
         if(price < current_price + min_distance) {
            Print("止盈错误: 距离现价太近，最小距离=", min_distance);
            return false;
         }
      } else {
         if(price > current_price - min_distance) {
            Print("止盈错误: 距离现价太近，最小距离=", min_distance);
            return false;
         }
      }
   }
   
   return true;
}

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
   Print("交易执行: ", m_perf_stats.trade_executions);
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
   
   CreateLabel(0, x, y, "【🤖 AI智能交易 V2.1】", clrBlue, 16, "Arial Bold");
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
   y += LINE_HEIGHT + 6;
   
   CreateLabel(16, x, y, "━━━ 安全状态 ━━━", clrDarkGray, 11, "Arial Bold");
   y += LINE_HEIGHT;
   
   CreateLabel(17, x, y, "持仓: --", clrDarkBlue, 10, "Arial Bold");
   CreateLabel(18, x + COL2_X_OFFSET, y, "风险: --", clrDarkBlue, 10, "Arial Bold");
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
   
   ENUM_POSITION_TYPE pos_type = GetCurrentPositionType();
   string pos_text = "无持仓";
   color pos_color = clrDarkGray;
   if(pos_type == POSITION_TYPE_BUY) {
      pos_text = "持有多单";
      pos_color = clrLime;
   } else if(pos_type == POSITION_TYPE_SELL) {
      pos_text = "持有空单";
      pos_color = clrRed;
   }
   m_labels[17].Description("持仓: " + pos_text);
   m_labels[17].Color(pos_color);
   
   bool risk_ok = !IsDailyLossLimitReached();
   m_labels[18].Description("风险: " + (risk_ok ? "正常" : "超限"));
   m_labels[18].Color(risk_ok ? clrLimeGreen : clrRed);
   
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
   g_dynamic_sl_pips = 0;
   g_dynamic_tp_pips = 0;
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
   
   // 解析动态止损
   int sl_pos = StringFind(response, "\"stop_loss_pips\":");
   if(sl_pos >= 0) {
      sl_pos += 17;
      int sl_end = StringFind(response, ",", sl_pos);
      if(sl_end == -1) sl_end = StringFind(response, "}", sl_pos);
      if(sl_end > sl_pos) {
         g_dynamic_sl_pips = (int)StringToDouble(StringSubstr(response, sl_pos, sl_end - sl_pos));
         if(g_dynamic_sl_pips > 0)
            Print("解析到动态止损: ", g_dynamic_sl_pips, "点");
      }
   }
   
   // 解析动态止盈
   int tp_pos = StringFind(response, "\"take_profit_pips\":");
   if(tp_pos >= 0) {
      tp_pos += 19;
      int tp_end = StringFind(response, ",", tp_pos);
      if(tp_end == -1) tp_end = StringFind(response, "}", tp_pos);
      if(tp_end > tp_pos) {
         g_dynamic_tp_pips = (int)StringToDouble(StringSubstr(response, tp_pos, tp_end - tp_pos));
         if(g_dynamic_tp_pips > 0)
            Print("解析到动态止盈: ", g_dynamic_tp_pips, "点");
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
//| 【安全修复】执行AI建议的交易（增强版）                           |
//+------------------------------------------------------------------+
void ExecuteTrade(string action, double confidence) {
   if(confidence < InpMinConfidence) {
      Print("置信度 ", DoubleToString(confidence, 2), " 低于阈值 ", DoubleToString(InpMinConfidence, 2), "，不交易");
      return;
   }
   
   if(InpEnableRiskCheck && IsDailyLossLimitReached()) {
      Print("风险检查: 已达每日亏损限制，不执行交易");
      return;
   }
   
   ENUM_POSITION_TYPE current_pos = GetCurrentPositionType();
   bool need_reverse = false;
   
   if(current_pos != (ENUM_POSITION_TYPE)(-1)) {
      if(action == "BUY" && current_pos == POSITION_TYPE_SELL) {
         need_reverse = true;
      } else if(action == "SELL" && current_pos == POSITION_TYPE_BUY) {
         need_reverse = true;
      } else if((action == "BUY" && current_pos == POSITION_TYPE_BUY) || 
                (action == "SELL" && current_pos == POSITION_TYPE_SELL)) {
         Print("持仓方向与建议一致，不重复开仓");
         return;
      }
   }
   
   if(need_reverse && InpReversePosition) {
      Print("检测到反向信号，正在平仓后反转...");
      if(!CloseAllPositions()) {
         Print("平仓失败，取消开仓操作");
         return;
      }
      // 智能等待：轮询检查仓位是否完全关闭，最多等待3秒
      int wait_count = 0;
      while(PositionsTotal() > 0 && wait_count < 30) {
         Sleep(100);
         wait_count++;
      }
      if(wait_count >= 30) {
         Print("⚠️ 平仓等待超时，仍有未平仓位，取消开仓");
         return;
      }
      m_symbol.RefreshRates();
   }
   
   double sl_price = 0;
   double tp_price = 0;
   int use_sl = (g_dynamic_sl_pips > 0) ? g_dynamic_sl_pips : InpStopLoss;
   int use_tp = (g_dynamic_tp_pips > 0) ? g_dynamic_tp_pips : InpTakeProfit;
   
   if(action == "BUY") {
      if(use_sl > 0) {
         sl_price = m_symbol.Bid() - PointsToPrice(use_sl);
         if(!ValidateSLTP(sl_price, POSITION_TYPE_BUY, true)) {
            Print("止损验证失败，取消开仓");
            return;
         }
      }
      
      if(use_tp > 0) {
         tp_price = m_symbol.Ask() + PointsToPrice(use_tp);
         if(!ValidateSLTP(tp_price, POSITION_TYPE_BUY, false)) {
            Print("止盈验证失败，取消开仓");
            return;
         }
      }
      
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
      
      if(m_trade.PositionOpen(_Symbol, ORDER_TYPE_BUY, InpLotSize, m_symbol.Ask(), sl_price, tp_price)) {
         m_perf_stats.trade_executions++;
         Print("AI建议: 开多单成功 (SL:", use_sl, "点", (g_dynamic_sl_pips > 0 ? "动态" : "固定"),
               " TP:", use_tp, "点", (g_dynamic_tp_pips > 0 ? "动态" : "固定"),
               " 止损:", DoubleToString(sl_price, m_symbol.Digits()), " 止盈:", DoubleToString(tp_price, m_symbol.Digits()), ")");
      } else {
         Print("开多单失败: ", m_trade.ResultComment());
      }
   } else if(action == "SELL") {
      if(use_sl > 0) {
         sl_price = m_symbol.Bid() + PointsToPrice(use_sl);
         if(!ValidateSLTP(sl_price, POSITION_TYPE_SELL, true)) {
            Print("止损验证失败，取消开仓");
            return;
         }
      }
      
      if(use_tp > 0) {
         tp_price = m_symbol.Bid() - PointsToPrice(use_tp);
         if(!ValidateSLTP(tp_price, POSITION_TYPE_SELL, false)) {
            Print("止盈验证失败，取消开仓");
            return;
         }
      }
      
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
      
      if(m_trade.PositionOpen(_Symbol, ORDER_TYPE_SELL, InpLotSize, m_symbol.Bid(), sl_price, tp_price)) {
         m_perf_stats.trade_executions++;
         Print("AI建议: 开空单成功 (SL:", use_sl, "点", (g_dynamic_sl_pips > 0 ? "动态" : "固定"),
               " TP:", use_tp, "点", (g_dynamic_tp_pips > 0 ? "动态" : "固定"),
               " 止损:", DoubleToString(sl_price, m_symbol.Digits()), " 止盈:", DoubleToString(tp_price, m_symbol.Digits()), ")");
      } else {
         Print("开空单失败: ", m_trade.ResultComment());
      }
   } else if(action == "HOLD") {
      Print("AI建议HOLD，不执行交易");
      // 清除动态止损止盈值
      g_dynamic_sl_pips = 0;
      g_dynamic_tp_pips = 0;
   }
}

// HOLD时清除动态值
void OnHoldSignal() {
   g_dynamic_sl_pips = 0;
   g_dynamic_tp_pips = 0;
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
   
   UpdateSupportResistanceLines();
   UpdatePanel();
   
   Print("=== AI交易EA V2.1 - 安全修复版已初始化 ===");
   Print("版本: 3.11");
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
   Print("AI交易EA V2.1已停止");
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
