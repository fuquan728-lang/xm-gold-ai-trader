//+------------------------------------------------------------------+
//|                                           AnalysisPanel_Simple.mq5 |
//|                        技术分析面板 - 简化版本                    |
//|                                                                  |
//+------------------------------------------------------------------+
#property copyright   "Analysis Panel"
#property link        "https://www.mql5.com"
#property version     "1.00"
#property description "技术分析面板 - 显示市场情绪、价格变化、支撑阻力位"
#property indicator_chart_window
#property indicator_plots   0
#property indicator_buffers 0

#include <Trade\SymbolInfo.mqh>

input int    InpPanelX          = 20;       // 面板X坐标
input int    InpPanelY          = 20;       // 面板Y坐标
input color  InpBgColor         = clrWhite; // 面板背景色
input color  InpTextColor       = clrBlack; // 文字颜色
input color  InpBuyColor        = clrLime;  // 买进颜色
input color  InpSellColor       = clrRed;   // 卖出颜色
input int    InpFontSize        = 9;        // 字体大小

string panel_name = "AnalysisPanel";
CSymbolInfo symbol_info;

/**
 * 创建文本对象
 * @param name 对象名称
 * @param x X坐标
 * @param y Y坐标
 * @param text 文本内容
 * @param color 文字颜色
 * @param font_size 字体大小
 * @param bold 是否加粗
 */
void CreateTextObject(string name, int x, int y, string text, color color, int font_size, bool bold = false)
{
   if(ObjectFind(0, name) >= 0)
      ObjectDelete(0, name);
   
   ObjectCreate(0, name, OBJ_LABEL, 0, 0, 0);
   ObjectSetInteger(0, name, OBJPROP_XDISTANCE, x);
   ObjectSetInteger(0, name, OBJPROP_YDISTANCE, y);
   ObjectSetString(0, name, OBJPROP_TEXT, text);
   ObjectSetInteger(0, name, OBJPROP_COLOR, color);
   ObjectSetInteger(0, name, OBJPROP_FONTSIZE, font_size);
   ObjectSetString(0, name, OBJPROP_FONT, "Arial");
   if(bold)
      ObjectSetString(0, name, OBJPROP_FONT, "Arial Bold");
}

/**
 * 创建矩形背景
 * @param name 对象名称
 * @param x1 左X坐标
 * @param y1 上Y坐标
 * @param x2 右X坐标
 * @param y2 下Y坐标
 * @param color 背景颜色
 */
void CreateRectangle(string name, int x1, int y1, int x2, int y2, color color)
{
   if(ObjectFind(0, name) >= 0)
      ObjectDelete(0, name);
   
   ObjectCreate(0, name, OBJ_RECTANGLE_LABEL, 0, 0, 0);
   ObjectSetInteger(0, name, OBJPROP_XDISTANCE, x1);
   ObjectSetInteger(0, name, OBJPROP_YDISTANCE, y1);
   ObjectSetInteger(0, name, OBJPROP_XSIZE, x2 - x1);
   ObjectSetInteger(0, name, OBJPROP_YSIZE, y2 - y1);
   ObjectSetInteger(0, name, OBJPROP_COLOR, clrGray);
   ObjectSetInteger(0, name, OBJPROP_BACK, true);
   ObjectSetInteger(0, name, OBJPROP_FILL, true);
   ObjectSetInteger(0, name, OBJPROP_BGCOLOR, color);
   ObjectSetInteger(0, name, OBJPROP_ZORDER, 0);
}

/**
 * 计算市场情绪
 * @param buy_percent [输出] 买进百分比
 * @param sell_percent [输出] 卖出百分比
 */
void CalculateSentiment(int &buy_percent, int &sell_percent)
{
   double rsi = iRSI(_Symbol, PERIOD_H1, 14, PRICE_CLOSE, 0);
   if(rsi == 0) rsi = 50;
   buy_percent = (int)MathRound(50 + (50 - rsi));
   buy_percent = MathMax(10, MathMin(90, buy_percent));
   sell_percent = 100 - buy_percent;
}

/**
 * 计算价格变化百分比
 * @return double 价格变化百分比
 */
double CalculatePriceChange()
{
   double open = iOpen(_Symbol, PERIOD_D1, 1);
   double current = symbol_info.Bid();
   if(open == 0) return 0;
   return (current - open) / open * 100;
}

/**
 * 计算技术评分
 * @param short_score [输出] 短期评分
 * @param medium_score [输出] 中期评分
 * @param long_score [输出] 长期评分
 */
void CalculateTechScores(int &short_score, int &medium_score, int &long_score)
{
   short_score = 0;
   medium_score = 0;
   long_score = 0;
   
   double rsi_h1 = iRSI(_Symbol, PERIOD_H1, 14, PRICE_CLOSE, 0);
   double rsi_h4 = iRSI(_Symbol, PERIOD_H4, 14, PRICE_CLOSE, 0);
   double rsi_d1 = iRSI(_Symbol, PERIOD_D1, 14, PRICE_CLOSE, 0);
   
   if(rsi_h1 < 30) short_score = 1;
   else if(rsi_h1 > 70) short_score = -1;
   
   if(rsi_h4 < 30) medium_score = 1;
   else if(rsi_h4 > 70) medium_score = -1;
   
   if(rsi_d1 < 30) long_score = 1;
   else if(rsi_d1 > 70) long_score = -1;
}

/**
 * 计算支撑阻力位
 * @param support [输出] 支撑位
 * @param resistance [输出] 阻力位
 */
void CalculateSupportResistance(double &support, double &resistance)
{
   int period = 50;
   double lowest = DBL_MAX;
   double highest = 0;
   
   for(int i = 1; i <= period; i++)
   {
      double low = iLow(_Symbol, PERIOD_D1, i);
      double high = iHigh(_Symbol, PERIOD_D1, i);
      if(low != 0 && low < lowest) lowest = low;
      if(high != 0 && high > highest) highest = high;
   }
   
   double current = symbol_info.Bid();
   if(lowest == DBL_MAX) lowest = current * 0.95;
   if(highest == 0) highest = current * 1.05;
   
   support = lowest + (current - lowest) * 0.3;
   resistance = highest - (highest - current) * 0.3;
}

/**
 * 更新面板显示
 */
void UpdatePanel()
{
   int x = InpPanelX;
   int y = InpPanelY;
   int line_height = 18;
   int panel_width = 220;
   int panel_height = 280;
   
   CreateRectangle(panel_name + "_bg", x, y, x + panel_width, y + panel_height, InpBgColor);
   
   y += 10;
   CreateTextObject(panel_name + "_title", x + 10, y, "分析", InpTextColor, InpFontSize + 3, true);
   
   y += line_height + 10;
   CreateTextObject(panel_name + "_sent_title", x + 10, y, "市场脉动", clrDarkGray, InpFontSize - 1);
   
   y += line_height;
   int buy_percent, sell_percent;
   CalculateSentiment(buy_percent, sell_percent);
   CreateTextObject(panel_name + "_sent_buy", x + 10, y, IntegerToString(buy_percent) + "% 买进", InpBuyColor, InpFontSize);
   CreateTextObject(panel_name + "_sent_sell", x + 120, y, IntegerToString(sell_percent) + "% 卖出", InpSellColor, InpFontSize);
   
   y += line_height + 10;
   CreateTextObject(panel_name + "_price_title", x + 10, y, "每日价格变化", clrDarkGray, InpFontSize - 1);
   
   y += line_height;
   double change = CalculatePriceChange();
   string change_text = (change >= 0 ? "↑ " : "↓ ") + DoubleToString(change, 2) + "%";
   color change_color = change >= 0 ? InpBuyColor : InpSellColor;
   CreateTextObject(panel_name + "_price_change", x + 10, y, change_text, change_color, InpFontSize);
   
   y += line_height + 5;
   double open = iOpen(_Symbol, PERIOD_D1, 1);
   double current = symbol_info.Bid();
   double low = iLow(_Symbol, PERIOD_D1, 0);
   double high = iHigh(_Symbol, PERIOD_D1, 0);
   
   CreateTextObject(panel_name + "_open", x + 10, y, "开仓     " + DoubleToString(open, symbol_info.Digits()), clrDarkGray, InpFontSize - 1);
   
   y += line_height;
   CreateTextObject(panel_name + "_current", x + 10, y, "当前     " + DoubleToString(current, symbol_info.Digits()), InpTextColor, InpFontSize + 1, true);
   
   y += line_height;
   CreateTextObject(panel_name + "_low", x + 10, y, "最低价     " + DoubleToString(low, symbol_info.Digits()), clrDarkGray, InpFontSize - 1);
   CreateTextObject(panel_name + "_high", x + 110, y, "最高价     " + DoubleToString(high, symbol_info.Digits()), clrDarkSlateBlue, InpFontSize - 1);
   
   y += line_height + 10;
   CreateTextObject(panel_name + "_tech_title", x + 10, y, "技术评分", clrDarkGray, InpFontSize - 1);
   
   y += line_height;
   int short_score, medium_score, long_score;
   CalculateTechScores(short_score, medium_score, long_score);
   
   string short_text = (short_score > 0 ? "↑ " : (short_score < 0 ? "↓ " : "○ ")) + "Short-term";
   color short_color = short_score > 0 ? InpBuyColor : (short_score < 0 ? InpSellColor : clrDarkGray);
   CreateTextObject(panel_name + "_tech_short", x + 10, y, short_text, short_color, InpFontSize - 1);
   
   y += line_height;
   string medium_text = (medium_score > 0 ? "↑ " : (medium_score < 0 ? "↓ " : "○ ")) + "Intermediate";
   color medium_color = medium_score > 0 ? InpBuyColor : (medium_score < 0 ? InpSellColor : clrDarkGray);
   CreateTextObject(panel_name + "_tech_medium", x + 10, y, medium_text, medium_color, InpFontSize - 1);
   
   y += line_height;
   string long_text = (long_score > 0 ? "↑ " : (long_score < 0 ? "↓ " : "○ ")) + "Long-term";
   color long_color = long_score > 0 ? InpBuyColor : (long_score < 0 ? InpSellColor : clrDarkGray);
   CreateTextObject(panel_name + "_tech_long", x + 10, y, long_text, long_color, InpFontSize - 1);
   
   y += line_height + 10;
   CreateTextObject(panel_name + "_sr_title", x + 10, y, "支撑/阻力", clrDarkGray, InpFontSize - 1);
   
   y += line_height;
   double support, resistance;
   CalculateSupportResistance(support, resistance);
   CreateTextObject(panel_name + "_support", x + 10, y, DoubleToString(support, symbol_info.Digits()) + "  Support", InpBuyColor, InpFontSize);
   CreateTextObject(panel_name + "_resistance", x + 110, y, DoubleToString(resistance, symbol_info.Digits()) + "  Resistance", InpSellColor, InpFontSize);
}

/**
 * 删除所有面板对象
 */
void DeletePanelObjects()
{
   long total = ObjectsTotal(0, 0, -1);
   for(int i = total - 1; i >= 0; i--)
   {
      string name = ObjectName(0, i, 0, -1);
      if(StringFind(name, panel_name) == 0)
         ObjectDelete(0, name);
   }
}

/**
 * 指标初始化函数
 */
int OnInit()
{
   symbol_info.Name(_Symbol);
   return INIT_SUCCEEDED;
}

/**
 * 指标反初始化函数
 */
void OnDeinit(const int reason)
{
   DeletePanelObjects();
}

/**
 * 指标计算函数
 */
int OnCalculate(const int rates_total,
                const int prev_calculated,
                const int begin,
                const double &price[])
{
   static datetime last_update = 0;
   datetime now = TimeCurrent();
   
   if(now - last_update >= 1 || prev_calculated == 0)
   {
      symbol_info.RefreshRates();
      UpdatePanel();
      last_update = now;
   }
   
   return rates_total;
}
