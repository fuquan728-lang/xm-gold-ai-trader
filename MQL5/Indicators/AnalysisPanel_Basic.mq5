//+------------------------------------------------------------------+
//|                                            AnalysisPanel_Basic.mq5 |
//|                        技术分析面板 - 最终版本                    |
//|                                                                  |
//+------------------------------------------------------------------+
#property copyright   "Analysis Panel"
#property link        "https://www.mql5.com"
#property version     "1.20"
#property description "技术分析面板"
#property indicator_chart_window
#property indicator_plots   0
#property indicator_buffers 0

#include <ChartObjects\ChartObjectsTxtControls.mqh>
#include <ChartObjects\ChartObjectsLines.mqh>

CChartObjectLabel m_labels[20];
CChartObjectHLine m_support_line;
CChartObjectHLine m_resistance_line;
string panel_name = "AnalysisPanel_Basic";

int OnInit()
{
   int panel_w = 260;
   int chart_w = (int)ChartGetInteger(0, CHART_WIDTH_IN_PIXELS);
   int x = chart_w - panel_w - 30;
   int y = 30;
   int line_h = 22;
   
   for(int i = 0; i < 20; i++)
   {
      string name = panel_name + "_" + IntegerToString(i);
      if(ObjectFind(0, name) >= 0)
         ObjectDelete(0, name);
   }
   
   m_labels[0].Create(0, panel_name + "_0", 0, x, y);
   m_labels[0].Description("分析");
   m_labels[0].Color(clrBlack);
   m_labels[0].FontSize(16);
   m_labels[0].Font("Arial Bold");
   
   y += line_h + 15;
   
   m_labels[1].Create(0, panel_name + "_1", 0, x, y);
   m_labels[1].Description("市场脉动");
   m_labels[1].Color(clrDimGray);
   m_labels[1].FontSize(10);
   m_labels[1].Font("Arial Bold");
   
   y += line_h;
   
   m_labels[2].Create(0, panel_name + "_2", 0, x, y);
   m_labels[2].Description("59% 买进");
   m_labels[2].Color(clrLimeGreen);
   m_labels[2].FontSize(12);
   m_labels[2].Font("Arial Bold");
   
   m_labels[3].Create(0, panel_name + "_3", 0, x + 130, y);
   m_labels[3].Description("41% 卖出");
   m_labels[3].Color(clrCrimson);
   m_labels[3].FontSize(12);
   m_labels[3].Font("Arial Bold");
   
   y += line_h + 15;
   
   m_labels[4].Create(0, panel_name + "_4", 0, x, y);
   m_labels[4].Description("每日价格变化");
   m_labels[4].Color(clrDimGray);
   m_labels[4].FontSize(10);
   m_labels[4].Font("Arial Bold");
   
   y += line_h;
   
   m_labels[5].Create(0, panel_name + "_5", 0, x, y);
   m_labels[5].Description("↓ -0.28%");
   m_labels[5].Color(clrCrimson);
   m_labels[5].FontSize(12);
   m_labels[5].Font("Arial Bold");
   
   y += line_h + 10;
   
   m_labels[6].Create(0, panel_name + "_6", 0, x, y);
   m_labels[6].Description("开仓     4865.96");
   m_labels[6].Color(clrDimGray);
   m_labels[6].FontSize(10);
   m_labels[6].Font("Arial Bold");
   
   y += line_h;
   
   m_labels[7].Create(0, panel_name + "_7", 0, x, y);
   m_labels[7].Description("当前     4863.43");
   m_labels[7].Color(clrBlack);
   m_labels[7].FontSize(14);
   m_labels[7].Font("Arial Bold");
   
   y += line_h;
   
   m_labels[8].Create(0, panel_name + "_8", 0, x, y);
   m_labels[8].Description("最低价     4854.10");
   m_labels[8].Color(clrDimGray);
   m_labels[8].FontSize(10);
   m_labels[8].Font("Arial Bold");
   
   m_labels[9].Create(0, panel_name + "_9", 0, x + 130, y);
   m_labels[9].Description("最高价     4884.24");
   m_labels[9].Color(clrDarkSlateBlue);
   m_labels[9].FontSize(10);
   m_labels[9].Font("Arial Bold");
   
   y += line_h + 15;
   
   m_labels[10].Create(0, panel_name + "_10", 0, x, y);
   m_labels[10].Description("技术评分");
   m_labels[10].Color(clrDimGray);
   m_labels[10].FontSize(10);
   m_labels[10].Font("Arial Bold");
   
   y += line_h;
   
   m_labels[11].Create(0, panel_name + "_11", 0, x, y);
   m_labels[11].Description("↓ Short-term");
   m_labels[11].Color(clrCrimson);
   m_labels[11].FontSize(10);
   m_labels[11].Font("Arial Bold");
   
   y += line_h;
   
   m_labels[12].Create(0, panel_name + "_12", 0, x, y);
   m_labels[12].Description("↓ Intermediate");
   m_labels[12].Color(clrCrimson);
   m_labels[12].FontSize(10);
   m_labels[12].Font("Arial Bold");
   
   y += line_h;
   
   m_labels[13].Create(0, panel_name + "_13", 0, x, y);
   m_labels[13].Description("○ Long-term");
   m_labels[13].Color(clrDimGray);
   m_labels[13].FontSize(10);
   m_labels[13].Font("Arial Bold");
   
   y += line_h + 15;
   
   m_labels[14].Create(0, panel_name + "_14", 0, x, y);
   m_labels[14].Description("支撑/阻力");
   m_labels[14].Color(clrDimGray);
   m_labels[14].FontSize(10);
   m_labels[14].Font("Arial Bold");
   
   y += line_h;
   
   m_labels[15].Create(0, panel_name + "_15", 0, x, y);
   m_labels[15].Description("4215.25  Support");
   m_labels[15].Color(clrLimeGreen);
   m_labels[15].FontSize(12);
   m_labels[15].Font("Arial Bold");
   
   m_labels[16].Create(0, panel_name + "_16", 0, x + 130, y);
   m_labels[16].Description("5082.22  Resistance");
   m_labels[16].Color(clrCrimson);
   m_labels[16].FontSize(12);
   m_labels[16].Font("Arial Bold");
   
   double support_price = 4215.25;
   double resistance_price = 5082.22;
   
   if(ObjectFind(0, panel_name + "_support_line") >= 0)
      ObjectDelete(0, panel_name + "_support_line");
   m_support_line.Create(0, panel_name + "_support_line", 0, support_price);
   m_support_line.Color(clrLimeGreen);
   m_support_line.Style(STYLE_SOLID);
   m_support_line.Width(2);
   m_support_line.Description("Support");
   
   if(ObjectFind(0, panel_name + "_resistance_line") >= 0)
      ObjectDelete(0, panel_name + "_resistance_line");
   m_resistance_line.Create(0, panel_name + "_resistance_line", 0, resistance_price);
   m_resistance_line.Color(clrCrimson);
   m_resistance_line.Style(STYLE_SOLID);
   m_resistance_line.Width(2);
   m_resistance_line.Description("Resistance");
   
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   for(int i = 0; i < 20; i++)
   {
      string name = panel_name + "_" + IntegerToString(i);
      if(ObjectFind(0, name) >= 0)
         ObjectDelete(0, name);
   }
   if(ObjectFind(0, panel_name + "_support_line") >= 0)
      ObjectDelete(0, panel_name + "_support_line");
   if(ObjectFind(0, panel_name + "_resistance_line") >= 0)
      ObjectDelete(0, panel_name + "_resistance_line");
}

int OnCalculate(const int rates_total,
                const int prev_calculated,
                const int begin,
                const double &price[])
{
   return rates_total;
}
