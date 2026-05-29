//+------------------------------------------------------------------+
//|                                          AI_Trader_Integrated.mq5 |
//|                   AI智能交易 + 技术分析面板 - 集成版             |
//+------------------------------------------------------------------+
#property copyright   "AI Trader Integrated"
#property link        "https://www.mql5.com"
#property version     "3.10"
#property description "AI智能交易 + 技术分析面板 - 集成版 (带止盈功能)"
#property strict

#include <Trade\Trade.mqh>
#include <Trade\SymbolInfo.mqh>
#include <Trade\PositionInfo.mqh>
#include <ChartObjects\ChartObjectsTxtControls.mqh>
#include <ChartObjects\ChartObjectsLines.mqh>
#include <ChartObjects\ChartObjectsShapes.mqh>

// 自定义字符串修剪函数（MQL5没有内置StringTrim）
string StringTrim(const string str)
{
   string result = str;
   // 去除左侧空白
   while(StringGetCharacter(result, 0) == ' ' || StringGetCharacter(result, 0) == '\t' || StringGetCharacter(result, 0) == '\n' || StringGetCharacter(result, 0) == '\r')
      result = StringSubstr(result, 1);
   
   // 去除右侧空白
   int len = StringLen(result);
   while(len > 0 && (StringGetCharacter(result, len-1) == ' ' || StringGetCharacter(result, len-1) == '\t' || StringGetCharacter(result, len-1) == '\n' || StringGetCharacter(result, len-1) == '\r'))
   {
      result = StringSubstr(result, 0, len-1);
      len = StringLen(result);
   }
   
   return result;
}

input string InpDataPath        = "";       // 数据文件路径（留空使用标准MQL5\Files目录）
input int    InpRequestInterval = 300;      // 请求间隔（秒）- 5分钟
input double InpLotSize         = 0.01;     // 交易手数
input double InpMinConfidence   = 0.65;     // 最小置信度才交易
input bool   InpShowPanel       = true;      // 显示技术分析面板
input int    InpStopLoss        = 30;       // 止损点数（0=关闭）
input int    InpTakeProfit      = 60;       // 止盈点数（0=关闭）
input bool   InpShowLines       = true;      // 显示支撑阻力线
input int    InpTrailingStop    = 30;       // 追踪止损点数（0=关闭）
input bool   InpEnableRiskCheck = true;     // 启用风险检查
input double InpMaxDailyLoss    = 0.0;      // 每日最大亏损（0=关闭，单位：账户货币）

CTrade         m_trade;
double         m_daily_start_balance = 0.0;
CSymbolInfo    m_symbol;
CPositionInfo  m_position;
datetime       m_last_request_time;
int            m_rsi_handle;
int            m_macd_handle;
int            m_ema_handle;
int            m_ema20_handle;
int            m_ema100_handle;
int            m_atr_handle;
int            m_stoch_handle;

CChartObjectLabel m_labels[20];
CChartObjectHLine m_support_line;
CChartObjectHLine m_resistance_line;
string panel_name = "AI_Trader_Panel";
string m_last_action = "HOLD";
double m_last_confidence = 0.0;
string m_last_reason = "";
double m_support_price = 0;
double m_resistance_price = 0;

// 动态止损止盈（从AI响应中解析，优先于输入参数）
int g_dynamic_sl_pips = 0;   // 0表示使用默认值InpStopLoss
int g_dynamic_tp_pips = 0;   // 0表示使用默认值InpTakeProfit

datetime m_last_panel_update = 0;
datetime m_last_sr_update = 0;

const int PANEL_WIDTH = 380;
const int PANEL_HEIGHT = 460;
const int PANEL_UPDATE_INTERVAL = 1;
const int SR_UPDATE_INTERVAL = 5;
const int LINE_HEIGHT = 22;
const int COL1_X_OFFSET = 0;
const int COL2_X_OFFSET = 175;
const int MAX_REASON_LENGTH = 120;
const int REASON_LINE1_MAX = 70;

/**
 * 初始化技术指标
 */
void InitIndicators()
{
   m_rsi_handle = iRSI(_Symbol, _Period, 14, PRICE_CLOSE);
   m_macd_handle = iMACD(_Symbol, _Period, 12, 26, 9, PRICE_CLOSE);
   m_ema_handle = iMA(_Symbol, _Period, 50, 0, MODE_EMA, PRICE_CLOSE);
   m_ema20_handle = iMA(_Symbol, _Period, 20, 0, MODE_EMA, PRICE_CLOSE);
   m_ema100_handle = iMA(_Symbol, _Period, 100, 0, MODE_EMA, PRICE_CLOSE);
   m_atr_handle = iATR(_Symbol, _Period, 14);
   m_stoch_handle = iStochastic(_Symbol, _Period, 14, 3, 3, MODE_SMA, STO_LOWHIGH);
}

/**
 * 计算支撑阻力位（最近20根K线）
 */
void CalculateSupportResistance()
{
   int bars = MathMin(20, Bars(_Symbol, _Period));
   if(bars < 5)
      return;
   
   double highest = 0;
   double lowest = 999999;
   
   for(int i = 1; i < bars; i++)
   {
      double high = iHigh(_Symbol, _Period, i);
      double low = iLow(_Symbol, _Period, i);
      
      if(high > highest)
         highest = high;
      if(low < lowest)
         lowest = low;
   }
   
   m_support_price = lowest;
   m_resistance_price = highest;
}

/**
 * 更新支撑阻力线
 */
void UpdateSupportResistanceLines()
{
   if(!InpShowLines)
      return;
   
   datetime now = TimeCurrent();
   if(now - m_last_sr_update < SR_UPDATE_INTERVAL)
      return;
   
   m_last_sr_update = now;
   CalculateSupportResistance();
   
   if(m_support_price > 0)
   {
      if(ObjectFind(0, panel_name + "_support_line") >= 0)
         ObjectDelete(0, panel_name + "_support_line");
      
      m_support_line.Create(0, panel_name + "_support_line", 0, m_support_price);
      m_support_line.Color(clrLimeGreen);
      m_support_line.Style(STYLE_SOLID);
      m_support_line.Width(2);
      m_support_line.Description("Support");
   }
   
   if(m_resistance_price > 0)
   {
      if(ObjectFind(0, panel_name + "_resistance_line") >= 0)
         ObjectDelete(0, panel_name + "_resistance_line");
      
      m_resistance_line.Create(0, panel_name + "_resistance_line", 0, m_resistance_price);
      m_resistance_line.Color(clrRed);
      m_resistance_line.Style(STYLE_SOLID);
      m_resistance_line.Width(2);
      m_resistance_line.Description("Resistance");
   }
}

bool m_panel_created = false;

/**
 * 创建/更新技术分析面板
 */
void UpdatePanel()
{
   if(!InpShowPanel)
      return;
   
   datetime now = TimeCurrent();
   if(now - m_last_panel_update < PANEL_UPDATE_INTERVAL && m_panel_created)
      return;
   
   m_last_panel_update = now;
   
   int chart_w = (int)ChartGetInteger(0, CHART_WIDTH_IN_PIXELS);
   int x = chart_w - PANEL_WIDTH - 10;
   int y = 15;
   int start_y = y;
   
   if(!m_panel_created)
   {
      for(int i = 0; i < 20; i++)
      {
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
      
      m_labels[0].Create(0, panel_name + "_0", 0, x, y);
      m_labels[0].Description("【🤖 AI智能交易】");
      m_labels[0].Color(clrBlue);
      m_labels[0].FontSize(16);
      m_labels[0].Font("Arial Bold");
      m_labels[0].Anchor(ANCHOR_RIGHT_UPPER);
      
      y += LINE_HEIGHT + 4;
      
      m_labels[1].Create(0, panel_name + "_1", 0, x, y);
      m_labels[1].Description("━━━ AI建议 ━━━");
      m_labels[1].Color(clrDarkGray);
      m_labels[1].FontSize(11);
      m_labels[1].Font("Arial Bold");
      m_labels[1].Anchor(ANCHOR_RIGHT_UPPER);
      
      y += LINE_HEIGHT;
      
      m_labels[2].Create(0, panel_name + "_2", 0, x, y);
      m_labels[2].Description("等待中...");
      m_labels[2].Color(clrDarkGray);
      m_labels[2].FontSize(14);
      m_labels[2].Font("Arial Bold");
      m_labels[2].Anchor(ANCHOR_RIGHT_UPPER);
      
      m_labels[3].Create(0, panel_name + "_3", 0, x + COL2_X_OFFSET, y);
      m_labels[3].Description("置信: 0.00");
      m_labels[3].Color(clrDarkGray);
      m_labels[3].FontSize(11);
      m_labels[3].Font("Arial Bold");
      m_labels[3].Anchor(ANCHOR_RIGHT_UPPER);
      
      y += LINE_HEIGHT;
      
      m_labels[9].Create(0, panel_name + "_9", 0, x, y);
      m_labels[9].Description("分析: --");
      m_labels[9].Color(clrDarkSlateGray);
      m_labels[9].FontSize(10);
      m_labels[9].Font("Arial");
      m_labels[9].Anchor(ANCHOR_RIGHT_UPPER);
      
      y += LINE_HEIGHT;
      
      m_labels[15].Create(0, panel_name + "_15", 0, x, y);
      m_labels[15].Description("");
      m_labels[15].Color(clrDarkSlateGray);
      m_labels[15].FontSize(10);
      m_labels[15].Font("Arial");
      m_labels[15].Anchor(ANCHOR_RIGHT_UPPER);
      
      y += LINE_HEIGHT + 6;
      
      m_labels[4].Create(0, panel_name + "_4", 0, x, y);
      m_labels[4].Description("━━━ 市场数据 ━━━");
      m_labels[4].Color(clrDarkGray);
      m_labels[4].FontSize(11);
      m_labels[4].Font("Arial Bold");
      m_labels[4].Anchor(ANCHOR_RIGHT_UPPER);
      
      y += LINE_HEIGHT;
      
      m_labels[5].Create(0, panel_name + "_5", 0, x, y);
      m_labels[5].Description("现价: --");
      m_labels[5].Color(clrBlack);
      m_labels[5].FontSize(12);
      m_labels[5].Font("Arial Bold");
      m_labels[5].Anchor(ANCHOR_RIGHT_UPPER);
      
      m_labels[6].Create(0, panel_name + "_6", 0, x + COL2_X_OFFSET, y);
      m_labels[6].Description("点差: --");
      m_labels[6].Color(clrDarkOrange);
      m_labels[6].FontSize(11);
      m_labels[6].Font("Arial Bold");
      m_labels[6].Anchor(ANCHOR_RIGHT_UPPER);
      
      y += LINE_HEIGHT;
      
      m_labels[7].Create(0, panel_name + "_7", 0, x, y);
      m_labels[7].Description("RSI: --");
      m_labels[7].Color(clrDarkGreen);
      m_labels[7].FontSize(11);
      m_labels[7].Font("Arial Bold");
      m_labels[7].Anchor(ANCHOR_RIGHT_UPPER);
      
      m_labels[8].Create(0, panel_name + "_8", 0, x + COL2_X_OFFSET, y);
      m_labels[8].Description("EMA50: --");
      m_labels[8].Color(clrPurple);
      m_labels[8].FontSize(11);
      m_labels[8].Font("Arial Bold");
      m_labels[8].Anchor(ANCHOR_RIGHT_UPPER);
      
      y += LINE_HEIGHT + 6;
      
      m_labels[13].Create(0, panel_name + "_13", 0, x, y);
      m_labels[13].Description("━━━ 技术指标 ━━━");
      m_labels[13].Color(clrDarkGray);
      m_labels[13].FontSize(11);
      m_labels[13].Font("Arial Bold");
      m_labels[13].Anchor(ANCHOR_RIGHT_UPPER);
      
      y += LINE_HEIGHT;
      
      m_labels[14].Create(0, panel_name + "_14", 0, x, y);
      m_labels[14].Description("MACD: --");
      m_labels[14].Color(clrDarkViolet);
      m_labels[14].FontSize(11);
      m_labels[14].Font("Arial Bold");
      m_labels[14].Anchor(ANCHOR_RIGHT_UPPER);
      
      y += LINE_HEIGHT + 6;
      
      m_labels[10].Create(0, panel_name + "_10", 0, x, y);
      m_labels[10].Description("━━━ 支撑阻力 ━━━");
      m_labels[10].Color(clrDarkGray);
      m_labels[10].FontSize(11);
      m_labels[10].Font("Arial Bold");
      m_labels[10].Anchor(ANCHOR_RIGHT_UPPER);
      
      y += LINE_HEIGHT;
      
      m_labels[11].Create(0, panel_name + "_11", 0, x, y);
      m_labels[11].Description("支撑: --");
      m_labels[11].Color(clrLimeGreen);
      m_labels[11].FontSize(11);
      m_labels[11].Font("Arial Bold");
      m_labels[11].Anchor(ANCHOR_RIGHT_UPPER);
      
      m_labels[12].Create(0, panel_name + "_12", 0, x + COL2_X_OFFSET, y);
      m_labels[12].Description("阻力: --");
      m_labels[12].Color(clrRed);
      m_labels[12].FontSize(11);
      m_labels[12].Font("Arial Bold");
      m_labels[12].Anchor(ANCHOR_RIGHT_UPPER);
      
      m_panel_created = true;
   }
   
   
   
   color action_color = clrDarkGray;
   string action_text = "等待中...";
   if(m_last_action == "BUY")
   {
      action_color = clrLime;
      action_text = "【🟢 买入】";
   }
   else if(m_last_action == "SELL")
   {
      action_color = clrRed;
      action_text = "【🔴 卖出】";
   }
   else if(m_last_action == "HOLD")
   {
      action_text = "【⚪ 观望】";
   }
   
   m_labels[2].Description(action_text);
   m_labels[2].Color(action_color);
   m_labels[3].Description("置信: " + DoubleToString(m_last_confidence, 2));
   
   string reason_line1 = "";
   string reason_line2 = "";
   if(StringLen(m_last_reason) > 0)
   {
      if(StringLen(m_last_reason) > REASON_LINE1_MAX)
      {
         int mid = REASON_LINE1_MAX;
         while(mid > 40 && StringGetCharacter(m_last_reason, mid) != ' ')
            mid--;
         if(mid < 40) mid = REASON_LINE1_MAX;
         
         reason_line1 = "分析: " + StringSubstr(m_last_reason, 0, mid);
         reason_line2 = StringSubstr(m_last_reason, mid);
      }
      else
      {
         reason_line1 = "分析: " + m_last_reason;
         reason_line2 = "";
      }
   }
   else
   {
      reason_line1 = "分析: --";
      reason_line2 = "";
   }
   
   m_labels[9].Description(reason_line1);
   m_labels[15].Description(reason_line2);
   
   m_labels[5].Description("现价: " + DoubleToString((m_symbol.Bid() + m_symbol.Ask()) / 2, m_symbol.Digits()));
   
   int point_value = (int)MathPow(10, m_symbol.Digits());
   double spread_points = (m_symbol.Ask() - m_symbol.Bid()) * point_value;
   m_labels[6].Description("点差: " + DoubleToString(spread_points, 0) + "点");
   
   double rsi = 0;
   if(m_rsi_handle != INVALID_HANDLE)
   {
      double rsi_buffer[];
      if(CopyBuffer(m_rsi_handle, 0, 0, 1, rsi_buffer) > 0)
         rsi = rsi_buffer[0];
   }
   
   m_labels[7].Description("RSI: " + DoubleToString(rsi, 2));
   m_labels[7].Color(rsi > 70 ? clrRed : (rsi < 30 ? clrLime : clrDarkGreen));
   
   double ema50 = 0;
   if(m_ema_handle != INVALID_HANDLE)
   {
      double ema_buffer[];
      if(CopyBuffer(m_ema_handle, 0, 0, 1, ema_buffer) > 0)
         ema50 = ema_buffer[0];
   }
   
   m_labels[8].Description("EMA50: " + DoubleToString(ema50, m_symbol.Digits()));
   
   double macd_main = 0;
   if(m_macd_handle != INVALID_HANDLE)
   {
      double macd_buffer[];
      if(CopyBuffer(m_macd_handle, 0, 0, 1, macd_buffer) > 0)
         macd_main = macd_buffer[0];
   }
   
   m_labels[14].Description("MACD: " + DoubleToString(macd_main, 5));
   m_labels[14].Color(macd_main > 0 ? clrLimeGreen : (macd_main < 0 ? clrRed : clrDarkViolet));
   
   if(m_support_price > 0)
      m_labels[11].Description("支撑: " + DoubleToString(m_support_price, m_symbol.Digits()));
   if(m_resistance_price > 0)
      m_labels[12].Description("阻力: " + DoubleToString(m_resistance_price, m_symbol.Digits()));
   
   ChartRedraw();
   ChartSetInteger(0, CHART_EVENT_MOUSE_MOVE, true);
}

/**
 * 获取历史K线数据
 */
string GetHistoryData(int count)
{
   string json = "[";
   
   for(int i = 0; i < count && i < Bars(_Symbol, _Period); i++)
   {
      datetime time = iTime(_Symbol, _Period, i);
      double open = iOpen(_Symbol, _Period, i);
      double high = iHigh(_Symbol, _Period, i);
      double low = iLow(_Symbol, _Period, i);
      double close = iClose(_Symbol, _Period, i);
      long volume = iVolume(_Symbol, _Period, i);
      
      if(i > 0)
         json += ",";
      
      json += "{";
      json += "\"time\":" + IntegerToString((int)time) + ",";
      json += "\"open\":" + DoubleToString(open, m_symbol.Digits()) + ",";
      json += "\"high\":" + DoubleToString(high, m_symbol.Digits()) + ",";
      json += "\"low\":" + DoubleToString(low, m_symbol.Digits()) + ",";
      json += "\"close\":" + DoubleToString(close, m_symbol.Digits()) + ",";
      json += "\"volume\":" + IntegerToString((int)volume);
      json += "}";
   }
   
   json += "]";
   return json;
}

/**
 * 获取技术指标数据
 */
string GetIndicatorsData()
{
   string json = "{";
   
   double rsi = 0;
   if(m_rsi_handle != INVALID_HANDLE)
   {
      double rsi_buffer[];
      if(CopyBuffer(m_rsi_handle, 0, 0, 1, rsi_buffer) > 0)
         rsi = rsi_buffer[0];
   }
   
   double macd_main = 0, macd_signal = 0;
   if(m_macd_handle != INVALID_HANDLE)
   {
      double macd_main_buffer[], macd_signal_buffer[];
      if(CopyBuffer(m_macd_handle, 0, 0, 1, macd_main_buffer) > 0)
         macd_main = macd_main_buffer[0];
      if(CopyBuffer(m_macd_handle, 1, 0, 1, macd_signal_buffer) > 0)
         macd_signal = macd_signal_buffer[0];
   }
   
   double ema50 = 0;
   if(m_ema_handle != INVALID_HANDLE)
   {
      double ema_buffer[];
      if(CopyBuffer(m_ema_handle, 0, 0, 1, ema_buffer) > 0)
         ema50 = ema_buffer[0];
   }
   
   double ema20 = 0;
   if(m_ema20_handle != INVALID_HANDLE)
   {
      double ema20_buffer[];
      if(CopyBuffer(m_ema20_handle, 0, 0, 1, ema20_buffer) > 0)
         ema20 = ema20_buffer[0];
   }
   
   double ema100 = 0;
   if(m_ema100_handle != INVALID_HANDLE)
   {
      double ema100_buffer[];
      if(CopyBuffer(m_ema100_handle, 0, 0, 1, ema100_buffer) > 0)
         ema100 = ema100_buffer[0];
   }
   
   double atr = 0;
   if(m_atr_handle != INVALID_HANDLE)
   {
      double atr_buffer[];
      if(CopyBuffer(m_atr_handle, 0, 0, 1, atr_buffer) > 0)
         atr = atr_buffer[0];
   }
   
   double stoch_k = 0, stoch_d = 0;
   if(m_stoch_handle != INVALID_HANDLE)
   {
      double stoch_k_buffer[], stoch_d_buffer[];
      if(CopyBuffer(m_stoch_handle, 0, 0, 1, stoch_k_buffer) > 0)
         stoch_k = stoch_k_buffer[0];
      if(CopyBuffer(m_stoch_handle, 1, 0, 1, stoch_d_buffer) > 0)
         stoch_d = stoch_d_buffer[0];
   }
   
   double macd_histogram = macd_main - macd_signal;
   
   json += "\"rsi\":" + DoubleToString(rsi, 2) + ",";
   json += "\"macd_main\":" + DoubleToString(macd_main, 5) + ",";
   json += "\"macd_signal\":" + DoubleToString(macd_signal, 5) + ",";
   json += "\"macd_histogram\":" + DoubleToString(macd_histogram, 5) + ",";
   json += "\"ema20\":" + DoubleToString(ema20, m_symbol.Digits()) + ",";
   json += "\"ema50\":" + DoubleToString(ema50, m_symbol.Digits()) + ",";
   json += "\"ema100\":" + DoubleToString(ema100, m_symbol.Digits()) + ",";
   json += "\"atr\":" + DoubleToString(atr, m_symbol.Digits()) + ",";
   json += "\"stoch_k\":" + DoubleToString(stoch_k, 2) + ",";
   json += "\"stoch_d\":" + DoubleToString(stoch_d, 2);
   json += "}";
   
   return json;
}

/**
 * 获取账户数据JSON
 * 使用MQL5 AccountInfo API直接把账户资金/保证金传给Python风控。
 */
string GetAccountDataJson()
{
   double balance = AccountInfoDouble(ACCOUNT_BALANCE);
   double equity = AccountInfoDouble(ACCOUNT_EQUITY);
   double margin = AccountInfoDouble(ACCOUNT_MARGIN);
   double margin_free = AccountInfoDouble(ACCOUNT_MARGIN_FREE);
   double margin_level = AccountInfoDouble(ACCOUNT_MARGIN_LEVEL);
   double profit = AccountInfoDouble(ACCOUNT_PROFIT);
   
   // MT5在没有持仓/没有保证金占用时常返回0，这代表未使用保证金，不是保证金危机。
   if(margin <= 0.0 && (margin_free > 0.0 || equity > 0.0))
      margin_level = 1000.0;
   
   string json = "{";
   json += "\"balance\":" + DoubleToString(balance, 2) + ",";
   json += "\"equity\":" + DoubleToString(equity, 2) + ",";
   json += "\"margin_free\":" + DoubleToString(margin_free, 2) + ",";
   json += "\"margin\":" + DoubleToString(margin, 2) + ",";
   json += "\"margin_level\":" + DoubleToString(margin_level, 2) + ",";
   json += "\"profit\":" + DoubleToString(profit, 2) + ",";
   json += "\"leverage\":" + IntegerToString((int)AccountInfoInteger(ACCOUNT_LEVERAGE));
   json += "}";
   
   return json;
}

/**
 * 构建市场数据JSON
 */
string BuildMarketData()
{
   string json = "{";
   json += "\"symbol\":\"" + _Symbol + "\",";
   json += "\"bid\":" + DoubleToString(m_symbol.Bid(), m_symbol.Digits()) + ",";
   json += "\"ask\":" + DoubleToString(m_symbol.Ask(), m_symbol.Digits()) + ",";
   json += "\"spread\":" + DoubleToString(m_symbol.Ask() - m_symbol.Bid(), m_symbol.Digits()) + ",";
   json += "\"time\":" + IntegerToString((int)TimeCurrent()) + ",";
   json += "\"history\":" + GetHistoryData(30) + ",";
   json += "\"indicators\":" + GetIndicatorsData() + ",";
   json += "\"account_data\":" + GetAccountDataJson();
   json += "}";
   return json;
}

/**
 * 写入请求文件
 */
bool WriteRequestFile(string data)
{
   string filename = "ai_request.json";
   int file_handle = FileOpen(filename, FILE_WRITE|FILE_TXT|FILE_ANSI);
   
   if(file_handle == INVALID_HANDLE)
   {
      Print("无法打开请求文件: ", filename);
      return false;
   }
   
   FileWrite(file_handle, data);
   FileClose(file_handle);
   return true;
}

/**
 * 读取响应文件
 */
bool ReadResponseFile(string &response)
{
   string filename = "ai_response.json";
   
   if(!FileIsExist(filename))
      return false;
   
   int file_handle = FileOpen(filename, FILE_READ|FILE_TXT|FILE_UNICODE);
   
   if(file_handle == INVALID_HANDLE)
      return false;
   
   response = "";
   while(!FileIsEnding(file_handle))
   {
      response += FileReadString(file_handle);
   }
   
   FileClose(file_handle);
   
   // 调试：显示读取的内容
   string debug_content = response;
   if(StringLen(debug_content) > 200)
      debug_content = StringSubstr(debug_content, 0, 197) + "...";
   Print("📄 读取的文件内容: ", debug_content);
   
   FileDelete(filename);
   return true;
}

/**
 * 解析AI响应 - 更健壮的版本
 */
bool ParseAIResponse(string response, string &action, double &confidence, string &reason)
{
   action = "HOLD";
   confidence = 0.0;
   reason = "";
   
   // 重置动态止损止盈（每次新响应重新解析）
   g_dynamic_sl_pips = 0;
   g_dynamic_tp_pips = 0;
   
   // 调试：打印原始响应（前200字符）
   string debug_response = response;
   if(StringLen(debug_response) > 200)
      debug_response = StringSubstr(debug_response, 0, 197) + "...";
   Print("原始响应: ", debug_response);
   
   // 清理响应：去除可能的```json标记和代码块标记
   string clean_response = response;
   // 去除```json和```标记
   int backtick_pos = StringFind(clean_response, "```json");
   if(backtick_pos >= 0)
   {
      clean_response = StringSubstr(clean_response, backtick_pos + 7); // 跳过```json
   }
   
   backtick_pos = StringFind(clean_response, "```");
   if(backtick_pos >= 0)
   {
      clean_response = StringSubstr(clean_response, 0, backtick_pos);
   }
   
   // 去除开头和结尾的空白
   clean_response = StringTrim(clean_response);
   
   Print("清理后的响应: ", (StringLen(clean_response) > 200 ? StringSubstr(clean_response, 0, 197) + "..." : clean_response));
   
   // 方法1：健壮的JSON解析（支持嵌套引号和转义）
   // 查找整个JSON对象
   int json_start = StringFind(clean_response, "{");
   int json_end = StringFind(clean_response, "}", json_start);
   
   if(json_start < 0 || json_end <= json_start)
   {
      Print("❌ 未找到有效的JSON对象，尝试回退解析");
      return ParseAIResponseFallback(clean_response, action, confidence, reason);
   }
   
   // 提取JSON字符串（包含可能的嵌套对象，但我们的响应很简单）
   string json_str = StringSubstr(clean_response, json_start, json_end - json_start + 1);
   Print("提取的JSON: ", json_str);
   
   // 解析action字段
   string action_value = ExtractJSONValue(json_str, "action");
   if(action_value != "")
   {
      action_value = StringTrim(action_value);
      Print("🔍 ParseAIResponse: action_value='", action_value, "' 长度=", StringLen(action_value));
      if(action_value == "BUY" || action_value == "SELL" || action_value == "HOLD")
      {
         action = action_value;
         Print("✅ 解析到action: ", action);
      }
      else
      {
         Print("⚠️ 无效的action值: ", action_value, "，使用HOLD");
         action = "HOLD";
      }
   }
   else
   {
      Print("⚠️ 未找到action字段，尝试回退解析");
      return ParseAIResponseFallback(clean_response, action, confidence, reason);
   }
   
   // 解析confidence字段
   string confidence_str = ExtractJSONValue(json_str, "confidence");
   if(confidence_str != "")
   {
      confidence_str = StringTrim(confidence_str);
      confidence = StringToDouble(confidence_str);
      
      // 验证置信度范围
      if(confidence < 0.0)
      {
         Print("⚠️ 置信度小于0: ", confidence, "，调整为0");
         confidence = 0.0;
      }
      else if(confidence > 1.0)
      {
         Print("⚠️ 置信度大于1: ", confidence, "，调整为1.0");
         confidence = 1.0;
      }
      
      Print("✅ 解析到confidence: ", DoubleToString(confidence, 3));
   }
   else
   {
      Print("⚠️ 未找到confidence字段，使用0.0");
      confidence = 0.0;
   }
   
   // 解析reason字段
   string reason_value = ExtractJSONValue(json_str, "reason");
   if(reason_value != "")
   {
      Print("🔍 ParseAIResponse: reason_value='", reason_value, "' 长度=", StringLen(reason_value));
      reason = reason_value;
      // 限制reason长度
      if(StringLen(reason) > MAX_REASON_LENGTH)
         reason = StringSubstr(reason, 0, MAX_REASON_LENGTH - 3) + "...";
      Print("✅ 解析到reason: ", reason);
   }
   else
   {
      Print("⚠️ 未找到reason字段，使用空字符串");
   }
   
   // 解析动态止损止盈 (Python AI响应的stop_loss_pips / take_profit_pips)
   string sl_str = ExtractJSONValue(json_str, "stop_loss_pips");
   if(sl_str != "")
   {
      g_dynamic_sl_pips = (int)StringToDouble(StringTrim(sl_str));
      if(g_dynamic_sl_pips > 0)
         Print("✅ 解析到动态止损: ", g_dynamic_sl_pips, "点");
   }
   string tp_str = ExtractJSONValue(json_str, "take_profit_pips");
   if(tp_str != "")
   {
      g_dynamic_tp_pips = (int)StringToDouble(StringTrim(tp_str));
      if(g_dynamic_tp_pips > 0)
         Print("✅ 解析到动态止盈: ", g_dynamic_tp_pips, "点");
   }
   
   // HOLD信号保留AI返回的真实置信度（如0.55），不再强制清零
   // 只有确实未解析到confidence时才保持初始值0.0
   
   Print("✅ 最终解析结果: action=", action, 
         " confidence=", DoubleToString(confidence, 3), 
         " reason=", (StringLen(reason) > 30 ? StringSubstr(reason, 0, 27) + "..." : reason));
   return true;
}

// 辅助函数：从JSON字符串中提取字符串值（带引号）
string ExtractJSONStringValue(string json_str, string key)
{
   // 查找key的模式
   string key_pattern = "\"" + key + "\":";
   int key_pos = StringFind(json_str, key_pattern);
   if(key_pos < 0)
      return "";
   
   // 跳过key和冒号
   int value_start = key_pos + StringLen(key_pattern);
   
   // 跳过空白
   while(value_start < StringLen(json_str) && (StringGetCharacter(json_str, value_start) == ' ' || StringGetCharacter(json_str, value_start) == '\t' || StringGetCharacter(json_str, value_start) == '\n'))
      value_start++;
   
   // 检查开始引号
   if(value_start >= StringLen(json_str) || StringGetCharacter(json_str, value_start) != '"')
      return "";
   
   // 跳过开始引号
   value_start++;
   
   // 查找结束引号（跳过转义引号）
   int value_end = value_start;
   bool escaped = false;
   while(value_end < StringLen(json_str))
   {
      if(StringGetCharacter(json_str, value_end) == '\\')
      {
         escaped = !escaped;
      }
      else if(StringGetCharacter(json_str, value_end) == '"')
      {
         if(!escaped)
            break;
         escaped = false;
      }
      else
      {
         escaped = false;
      }
      value_end++;
   }
   
   if(value_end >= StringLen(json_str))
      return "";
   
   // 提取值
   string value = StringSubstr(json_str, value_start, value_end - value_start);
   
   // 直接返回原始值（AI返回的JSON应该是有效的，无需转义处理）
   // StringReplace在处理中文字符时有问题，会破坏字符串
   return value;
}

// 辅助函数：从JSON字符串中提取值（可以是数字或字符串）
string ExtractJSONValue(string json_str, string key)
{
   // 简单直接的JSON解析 - 查找 "key": 模式
   string key_pattern = "\"" + key + "\":";
   int key_pos = StringFind(json_str, key_pattern);
   if(key_pos < 0)
   {
      Print("🔍 ExtractJSONValue: 未找到key: ", key);
      return "";
   }
   
   Print("🔍 ExtractJSONValue: 找到key '", key, "' 在位置 ", key_pos);
   
   // 跳过key和冒号
   int value_start = key_pos + StringLen(key_pattern);
   
   // 跳过空白
   while(value_start < StringLen(json_str) && (StringGetCharacter(json_str, value_start) == ' ' || StringGetCharacter(json_str, value_start) == '\t' || StringGetCharacter(json_str, value_start) == '\n'))
      value_start++;
   
   if(value_start >= StringLen(json_str))
   {
      Print("🔍 ExtractJSONValue: value_start超出范围");
      return "";
   }
   
   Print("🔍 ExtractJSONValue: value_start=", value_start, " 字符='", StringSubstr(json_str, value_start, 1), "'");
   
   // 检查是否是字符串值（以双引号开始）
   if(StringGetCharacter(json_str, value_start) == '"')
   {
      Print("🔍 ExtractJSONValue: 字符串值");
      
      // 字符串值 - 查找结束引号（跳过转义引号）
      value_start++; // 跳过开始引号
      int value_end = value_start;
      bool escaped = false;
      
      while(value_end < StringLen(json_str))
      {
         ushort ch = StringGetCharacter(json_str, value_end);
         if(ch == '\\')
         {
            escaped = !escaped;
         }
         else if(ch == '"')
         {
            if(!escaped)
               break;
            escaped = false;
         }
         else
         {
            escaped = false;
         }
         value_end++;
      }
      
      if(value_end >= StringLen(json_str))
      {
         Print("🔍 ExtractJSONValue: 未找到结束引号");
         return "";
      }
      
      // 提取字符串值
      string value = StringSubstr(json_str, value_start, value_end - value_start);
      Print("🔍 ExtractJSONValue: 提取的原始值='", value, "' 长度=", StringLen(value));
      
      // 直接返回原始值（AI返回的JSON应该是有效的，无需转义处理）
      // StringReplace在处理中文字符时有问题，会破坏字符串
      Print("🔍 ExtractJSONValue: 返回值='", value, "'");
      return value;
   }
   else
   {
      Print("🔍 ExtractJSONValue: 非字符串值");
      
      // 非字符串值（数字、布尔值等）
      int value_end = value_start;
      
      // 查找值的结束位置（逗号、右大括号或空白）
      while(value_end < StringLen(json_str))
      {
         ushort ch = StringGetCharacter(json_str, value_end);
         if(ch == ',' || ch == '}' || ch == ' ' || ch == '\t' || ch == '\n')
            break;
         value_end++;
      }
      
      if(value_end <= value_start)
      {
         Print("🔍 ExtractJSONValue: 值结束位置无效");
         return "";
      }
      
      // 提取值
      string value = StringSubstr(json_str, value_start, value_end - value_start);
      Print("🔍 ExtractJSONValue: 提取的非字符串值='", value, "'");
      return value;
   }
}


// 回退解析方法（兼容旧格式）
bool ParseAIResponseFallback(string response, string &action, double &confidence, string &reason)
{
   action = "HOLD";
   confidence = 0.0;
   reason = "";
   
   Print("🔄 使用回退解析方法");
   
   // 简单搜索BUY/SELL/HOLD
   if(StringFind(response, "\"action\":\"BUY\"") >= 0 || StringFind(response, "'action':'BUY'") >= 0 || StringFind(response, "action\":\"BUY") >= 0)
      action = "BUY";
   else if(StringFind(response, "\"action\":\"SELL\"") >= 0 || StringFind(response, "'action':'SELL'") >= 0 || StringFind(response, "action\":\"SELL") >= 0)
      action = "SELL";
   else if(StringFind(response, "\"action\":\"HOLD\"") >= 0 || StringFind(response, "'action':'HOLD'") >= 0 || StringFind(response, "action\":\"HOLD") >= 0)
      action = "HOLD";
   
   // 搜索confidence
   int conf_start = StringFind(response, "\"confidence\":");
   if(conf_start < 0) conf_start = StringFind(response, "'confidence':");
   if(conf_start < 0) conf_start = StringFind(response, "confidence\":");
   
   if(conf_start >= 0)
   {
      int colon_pos = StringFind(response, ":", conf_start);
      if(colon_pos >= 0)
      {
         int start = colon_pos + 1;
         // 跳过空白
         while(start < StringLen(response) && (StringGetCharacter(response, start) == ' ' || StringGetCharacter(response, start) == '\t' || StringGetCharacter(response, start) == '\n'))
            start++;
         
         int end = start;
         while(end < StringLen(response) && StringGetCharacter(response, end) != ',' && StringGetCharacter(response, end) != '}')
            end++;
         
         if(end > start)
         {
            string conf_str = StringSubstr(response, start, end - start);
            conf_str = StringTrim(conf_str);
            confidence = StringToDouble(conf_str);
            
            // 验证范围
            if(confidence < 0.0) confidence = 0.0;
            if(confidence > 1.0) confidence = 1.0;
         }
      }
   }
   
   // 搜索reason
   int reason_start = StringFind(response, "\"reason\":\"");
   if(reason_start < 0) reason_start = StringFind(response, "'reason':'");
   if(reason_start < 0) reason_start = StringFind(response, "reason\":\"");
   
   if(reason_start >= 0)
   {
      int quote_pos = StringFind(response, "\"", reason_start + 9);
      if(quote_pos < 0) quote_pos = StringFind(response, "'", reason_start + 9);
      
      if(quote_pos >= 0)
      {
         int start = quote_pos + 1;
         int end = start;
         int quote_count = 0;
         
         while(end < StringLen(response))
         {
            if(StringGetCharacter(response, end) == '"' || StringGetCharacter(response, end) == '\'')
            {
               if(end > 0 && StringGetCharacter(response, end - 1) != '\\')
               {
                  quote_count++;
                  if(quote_count == 1)
                     break;
               }
            }
            end++;
         }
         
         if(end > start)
         {
            reason = StringSubstr(response, start, end - start);
            if(StringLen(reason) > MAX_REASON_LENGTH)
               reason = StringSubstr(reason, 0, MAX_REASON_LENGTH - 3) + "...";
         }
      }
   }
   
   // 如果明确是HOLD响应，不要因为reason/original_action里出现BUY/SELL而改写动作
   if(StringFind(response, "\"action\":\"HOLD\"") >= 0 ||
      StringFind(response, "\"action\": \"HOLD\"") >= 0 ||
      StringFind(response, "'action':'HOLD'") >= 0 ||
      StringFind(response, "'action': 'HOLD'") >= 0 ||
      StringFind(response, "action\":\"HOLD") >= 0)
   {
      action = "HOLD";
      confidence = 0.0;
      Print("🔄 回退解析确认HOLD响应");
      return true;
   }
   
   // 如果什么都没找到，尝试最后的简单搜索
   if(action == "HOLD" && confidence == 0.0)
   {
      if(StringFind(response, "BUY") >= 0)
         action = "BUY";
      else if(StringFind(response, "SELL") >= 0)
         action = "SELL";
      
      // 尝试提取数字作为置信度
      string numbers = "0123456789.";
      int num_start = -1;
      for(int i = 0; i < StringLen(response); i++)
      {
         string ch = StringSubstr(response, i, 1);
         if(StringFind(numbers, ch) >= 0)
         {
            if(num_start < 0) num_start = i;
         }
         else if(num_start >= 0)
         {
            string num_str = StringSubstr(response, num_start, i - num_start);
            double num = StringToDouble(num_str);
            if(num >= 0.0 && num <= 1.0)
            {
               confidence = num;
               break;
            }
            num_start = -1;
         }
      }
   }
   
   Print("🔄 回退解析结果: action=", action, " confidence=", DoubleToString(confidence, 3));
   return true;
}

double PointsToPrice(int points)
{
   double point = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
   return (double)points * point;
}

//+------------------------------------------------------------------+
//| 每日亏损限制检查                                                  |
//+------------------------------------------------------------------+
bool IsDailyLossLimitReached()
{
   if(InpMaxDailyLoss <= 0)
      return false;
   
   // 初始化当日起始余额（首次调用）
   if(m_daily_start_balance <= 0)
      m_daily_start_balance = AccountInfoDouble(ACCOUNT_BALANCE);
   
   // 检查是否为新的一天（重置基准）
   static datetime last_check_date = 0;
   MqlDateTime dt;
   TimeCurrent(dt);
   if(last_check_date > 0 && dt.day != last_check_date)
   {
      m_daily_start_balance = AccountInfoDouble(ACCOUNT_BALANCE);
   }
   last_check_date = dt.day;
   
   double current_equity = AccountInfoDouble(ACCOUNT_EQUITY);
   double daily_loss = m_daily_start_balance - current_equity;
   
   if(daily_loss >= InpMaxDailyLoss)
   {
      Print("警告: 已达每日最大亏损限制! 亏损=", DoubleToString(daily_loss, 2),
            " 限制=", DoubleToString(InpMaxDailyLoss, 2), " 停止交易");
      return true;
   }
   
   return false;
}

/**
 * 执行AI建议的交易（带止盈止损）
 */
void ExecuteTrade(string action, double confidence)
{
   if(confidence < InpMinConfidence)
   {
      Print("置信度 ", DoubleToString(confidence, 2), " 低于阈值 ", DoubleToString(InpMinConfidence, 2), "，不交易");
      return;
   }
   
   if(InpEnableRiskCheck && IsDailyLossLimitReached())
   {
      return;
   }
   
   bool has_position = false;
   ENUM_POSITION_TYPE current_type = POSITION_TYPE_BUY;
   
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      if(m_position.SelectByIndex(i))
      {
         if(m_position.Symbol() == _Symbol && m_position.Magic() == 987656)
         {
            has_position = true;
            current_type = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
            break;
         }
      }
   }
   
   if(has_position)
   {
      if(action == "BUY" && current_type == POSITION_TYPE_BUY)
      {
         Print("已有多头持仓，跳过开仓");
         return;
      }
      else if(action == "SELL" && current_type == POSITION_TYPE_SELL)
      {
         Print("已有空头持仓，跳过开仓");
         return;
      }
      else if(action == "BUY" && current_type == POSITION_TYPE_SELL)
      {
         Print("检测到相反持仓，正在平仓...");
         if(!m_trade.PositionClose(_Symbol))
         {
            Print("平仓失败，无法开新仓: ", m_trade.ResultComment());
            return;
         }
         has_position = false;
      }
      else if(action == "SELL" && current_type == POSITION_TYPE_BUY)
      {
         Print("检测到相反持仓，正在平仓...");
         if(!m_trade.PositionClose(_Symbol))
         {
            Print("平仓失败，无法开新仓: ", m_trade.ResultComment());
            return;
         }
         has_position = false;
      }
   }
   
   double sl_price = 0.0;
   double tp_price = 0.0;
   
   // 优先使用动态止损止盈（从AI响应中解析的），否则使用输入参数
   int use_sl = (g_dynamic_sl_pips > 0) ? g_dynamic_sl_pips : InpStopLoss;
   int use_tp = (g_dynamic_tp_pips > 0) ? g_dynamic_tp_pips : InpTakeProfit;
   
   // STOPS_LEVEL 检查：确保止损止盈距离满足券商最低要求
   int stops_level = (int)SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL);
   double min_sl_distance = (stops_level + 5) * m_symbol.Point();
   
   if(action == "BUY")
   {
      // BUY: 以Ask入场，止损以Bid为基准计算（避免止损高于买价Invalid stops）
      double bid = m_symbol.Bid();
      double ask = m_symbol.Ask();
      
      if(use_sl > 0)
      {
         double sl_distance = PointsToPrice(use_sl);
         if(sl_distance < min_sl_distance) sl_distance = min_sl_distance;
         sl_price = NormalizeDouble(bid - sl_distance, m_symbol.Digits());
      }
      
      if(use_tp > 0)
      {
         double tp_distance = PointsToPrice(use_tp);
         if(tp_distance < min_sl_distance) tp_distance = min_sl_distance;
         tp_price = NormalizeDouble(ask + tp_distance, m_symbol.Digits());
      }
      
      Print("BUY: Ask=", DoubleToString(ask, m_symbol.Digits()),
            " Bid=", DoubleToString(bid, m_symbol.Digits()),
            " SL=", DoubleToString(sl_price, m_symbol.Digits()),
            "(", use_sl, "点", (g_dynamic_sl_pips > 0 ? "动态" : "固定"), ")",
            " TP=", DoubleToString(tp_price, m_symbol.Digits()),
            "(", use_tp, "点", (g_dynamic_tp_pips > 0 ? "动态" : "固定"), ")",
            " stops_level=", stops_level);
      
      // 保证金检查
      double margin;
      if(OrderCalcMargin(ORDER_TYPE_BUY, _Symbol, InpLotSize, ask, margin))
      {
         if(AccountInfoDouble(ACCOUNT_FREEMARGIN) < margin * 1.1)
         {
            Print("BUY保证金不足: 需要=", DoubleToString(margin, 2),
                  " 可用=", DoubleToString(AccountInfoDouble(ACCOUNT_FREEMARGIN), 2));
            return;
         }
      }
      
      if(m_trade.PositionOpen(_Symbol, ORDER_TYPE_BUY, InpLotSize, ask, sl_price, tp_price))
      {
         string log_msg = "AI建议: 开多单成功";
         if(sl_price > 0) log_msg += StringFormat(" (止损: %s)", DoubleToString(sl_price, m_symbol.Digits()));
         if(tp_price > 0) log_msg += StringFormat(" (止盈: %s)", DoubleToString(tp_price, m_symbol.Digits()));
         Print(log_msg);
      }
      else
      {
         Print("开多单失败: ", m_trade.ResultComment());
      }
   }
   else if(action == "SELL")
   {
      // SELL: 以Bid入场，止损以Ask为基准计算（避免止损低于卖价Invalid stops）
      double bid = m_symbol.Bid();
      double ask = m_symbol.Ask();
      
      if(use_sl > 0)
      {
         double sl_distance = PointsToPrice(use_sl);
         if(sl_distance < min_sl_distance) sl_distance = min_sl_distance;
         sl_price = NormalizeDouble(ask + sl_distance, m_symbol.Digits());
      }
      
      if(use_tp > 0)
      {
         double tp_distance = PointsToPrice(use_tp);
         if(tp_distance < min_sl_distance) tp_distance = min_sl_distance;
         tp_price = NormalizeDouble(bid - tp_distance, m_symbol.Digits());
      }
      
      Print("SELL: Bid=", DoubleToString(bid, m_symbol.Digits()),
            " Ask=", DoubleToString(ask, m_symbol.Digits()),
            " SL=", DoubleToString(sl_price, m_symbol.Digits()),
            "(", use_sl, "点", (g_dynamic_sl_pips > 0 ? "动态" : "固定"), ")",
            " TP=", DoubleToString(tp_price, m_symbol.Digits()),
            "(", use_tp, "点", (g_dynamic_tp_pips > 0 ? "动态" : "固定"), ")",
            " stops_level=", stops_level);
      
      // 保证金检查
      double margin_sell;
      if(OrderCalcMargin(ORDER_TYPE_SELL, _Symbol, InpLotSize, bid, margin_sell))
      {
         if(AccountInfoDouble(ACCOUNT_FREEMARGIN) < margin_sell * 1.1)
         {
            Print("SELL保证金不足: 需要=", DoubleToString(margin_sell, 2),
                  " 可用=", DoubleToString(AccountInfoDouble(ACCOUNT_FREEMARGIN), 2));
            return;
         }
      }
      
      if(m_trade.PositionOpen(_Symbol, ORDER_TYPE_SELL, InpLotSize, bid, sl_price, tp_price))
      {
         string log_msg = "AI建议: 开空单成功";
         if(sl_price > 0) log_msg += StringFormat(" (止损: %s)", DoubleToString(sl_price, m_symbol.Digits()));
         if(tp_price > 0) log_msg += StringFormat(" (止盈: %s)", DoubleToString(tp_price, m_symbol.Digits()));
         Print(log_msg);
      }
      else
      {
         Print("开空单失败: ", m_trade.ResultComment());
      }
   }
   
   // 交易执行后清除动态止损止盈
   g_dynamic_sl_pips = 0;
   g_dynamic_tp_pips = 0;
}

/**
 * 管理追踪止损
 */
void ManageTrailingStop()
{
   if(InpTrailingStop <= 0)
      return;
   
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
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
      
      if(pos_type == POSITION_TYPE_BUY)
      {
         double profit_level = m_symbol.Bid() - trailing_distance;
         if(profit_level > pos_open_price)
         {
            if(pos_sl == 0 || profit_level > pos_sl)
            {
               new_sl = profit_level;
            }
         }
      }
      else if(pos_type == POSITION_TYPE_SELL)
      {
         double profit_level = m_symbol.Ask() + trailing_distance;
         if(profit_level < pos_open_price)
         {
            if(pos_sl == 0 || profit_level < pos_sl)
            {
               new_sl = profit_level;
            }
         }
      }
      
      if((pos_sl == 0 || new_sl > 0) && new_sl != pos_sl)
      {
         if(m_trade.PositionModify(pos_ticket, new_sl, 0.0))
         {
            Print("追踪止损更新: 新止损=", DoubleToString(new_sl, m_symbol.Digits()));
         }
         else
         {
            Print("追踪止损更新失败: ", m_trade.ResultComment());
         }
      }
   }
}

/**
 * EA初始化函数
 */
int OnInit()
{
   m_symbol.Name(_Symbol);
   m_trade.SetExpertMagicNumber(987656);
   m_trade.SetMarginMode();
   m_trade.SetTypeFillingBySymbol(_Symbol);
   
   InitIndicators();
   
   m_last_request_time = 0;
   m_last_action = "HOLD";
   m_last_confidence = 0.0;
   m_last_reason = "";
   
   UpdateSupportResistanceLines();
   UpdatePanel();
   
   Print("AI交易EA(集成版 v3.10)已初始化");
   if(InpTrailingStop > 0)
      Print("追踪止损: ", IntegerToString(InpTrailingStop), "点");
   if(InpStopLoss > 0)
      Print("止损: ", IntegerToString(InpStopLoss), "点");
   if(InpTakeProfit > 0)
      Print("止盈: ", IntegerToString(InpTakeProfit), "点");
   Print("最小交易置信度: ", DoubleToString(InpMinConfidence, 2));
   Print("请求间隔: ", IntegerToString(InpRequestInterval), "秒");
   
   return INIT_SUCCEEDED;
}

/**
 * EA反初始化函数
 */
void OnDeinit(const int reason)
{
   if(m_rsi_handle != INVALID_HANDLE)
      IndicatorRelease(m_rsi_handle);
   if(m_macd_handle != INVALID_HANDLE)
      IndicatorRelease(m_macd_handle);
   if(m_ema_handle != INVALID_HANDLE)
      IndicatorRelease(m_ema_handle);
   if(m_ema20_handle != INVALID_HANDLE)
      IndicatorRelease(m_ema20_handle);
   if(m_ema100_handle != INVALID_HANDLE)
      IndicatorRelease(m_ema100_handle);
   if(m_atr_handle != INVALID_HANDLE)
      IndicatorRelease(m_atr_handle);
   if(m_stoch_handle != INVALID_HANDLE)
      IndicatorRelease(m_stoch_handle);
   
   if(InpShowPanel && m_panel_created)
   {
      for(int i = 0; i < 20; i++)
      {
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
   Print("AI交易EA(集成版)已停止");
}

/**
 * EA主循环函数
 */
void OnTick()
{
   datetime now = TimeCurrent();
   
   UpdateSupportResistanceLines();
   UpdatePanel();
   ManageTrailingStop();
   
   if(now - m_last_request_time < InpRequestInterval)
      return;
   
   if(!m_symbol.RefreshRates())
      return;
   
   m_last_request_time = now;
   
   string filename = "ai_response.json";
   if(FileIsExist(filename))
      FileDelete(filename);
   
   string market_data = BuildMarketData();
   string response;
   
   Print("写入请求文件...");
   
   if(WriteRequestFile(market_data))
   {
      Print("等待AI响应...");
      
      int wait_count = 0;
      while(wait_count < 100)
      {
         Sleep(100);
         if(ReadResponseFile(response))
            break;
         wait_count++;
      }
      
      if(response != "")
      {
         Print("收到AI响应");
         
         string action;
         double confidence;
         string reason;
         
         if(ParseAIResponse(response, action, confidence, reason))
         {
            m_last_action = action;
            m_last_confidence = confidence;
            m_last_reason = reason;
            
            Print("AI建议: ", action, " 置信度: ", DoubleToString(confidence, 2));
            Print("分析原因: ", reason);
            ExecuteTrade(action, confidence);
            UpdatePanel();
         }
      }
      else
      {
         Print("未收到AI响应");
      }
   }
}
