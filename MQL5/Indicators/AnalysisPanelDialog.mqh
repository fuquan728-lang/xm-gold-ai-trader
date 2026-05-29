//+------------------------------------------------------------------+
//|                                          AnalysisPanelDialog.mqh |
//|                        技术分析面板 - 对话框类                    |
//|                                                                  |
//+------------------------------------------------------------------+
#include <Controls\Dialog.mqh>
#include <Controls\Label.mqh>
#include <Controls\Button.mqh>

#define INDENT_LEFT         (10)
#define INDENT_TOP          (10)
#define INDENT_RIGHT        (10)
#define INDENT_BOTTOM       (10)
#define CONTROLS_GAP_Y      (8)
#define LABEL_HEIGHT        (18)
#define PANEL_WIDTH         (280)
#define PANEL_HEIGHT        (420)

/**
 * 技术分析面板对话框类
 * 显示市场情绪、价格变化、技术评分、支撑阻力等信息
 */
class CAnalysisPanelDialog : public CAppDialog
{
private:
   CLabel            m_label_title;
   CLabel            m_label_sentiment_title;
   CLabel            m_label_sentiment_buy;
   CLabel            m_label_sentiment_sell;
   CLabel            m_label_price_title;
   CLabel            m_label_price_change;
   CLabel            m_label_open;
   CLabel            m_label_current;
   CLabel            m_label_low;
   CLabel            m_label_high;
   CLabel            m_label_tech_title;
   CLabel            m_label_tech_short;
   CLabel            m_label_tech_medium;
   CLabel            m_label_tech_long;
   CLabel            m_label_sr_title;
   CLabel            m_label_support;
   CLabel            m_label_resistance;
   CButton           m_button_close;

   CSymbolInfo       m_symbol;
   datetime          m_last_update;

public:
   /**
    * 构造函数
    */
                     CAnalysisPanelDialog(void);
   
   /**
    * 析构函数
    */
                    ~CAnalysisPanelDialog(void);
   
   /**
    * 创建对话框
    */
   virtual bool      Create(const long chart,const string name,const int subwin,const int x1,const int y1,const int x2,const int y2);
   
   /**
    * 事件处理
    */
   virtual bool      OnEvent(const int id,const long &lparam,const double &dparam,const string &sparam);
   
   /**
    * 更新面板数据
    */
   void              UpdateData(void);

protected:
   /**
    * 创建所有控件
    */
   bool              CreateControls(void);
   
   /**
    * 创建标题标签
    */
   bool              CreateTitleLabel(void);
   
   /**
    * 创建市场情绪标签
    */
   bool              CreateSentimentLabels(void);
   
   /**
    * 创建价格信息标签
    */
   bool              CreatePriceLabels(void);
   
   /**
    * 创建技术评分标签
    */
   bool              CreateTechLabels(void);
   
   /**
    * 创建支撑阻力标签
    */
   bool              CreateSRLabels(void);
   
   /**
    * 创建关闭按钮
    */
   bool              CreateCloseButton(void);
   
   /**
    * 计算市场情绪
    */
   void              CalculateSentiment(int &buy_percent, int &sell_percent);
   
   /**
    * 计算价格变化
    */
   double            CalculatePriceChange(void);
   
   /**
    * 计算技术评分
    */
   void              CalculateTechScores(int &short_score, int &medium_score, int &long_score);
   
   /**
    * 计算支撑阻力位
    */
   void              CalculateSupportResistance(double &support, double &resistance);
   
   /**
    * 关闭按钮点击事件
    */
   void              OnClickClose(void);
};

EVENT_MAP_BEGIN(CAnalysisPanelDialog)
   ON_EVENT(ON_CLICK,m_button_close,OnClickClose)
EVENT_MAP_END(CAppDialog)

/**
 * 构造函数实现
 */
CAnalysisPanelDialog::CAnalysisPanelDialog(void) : m_last_update(0)
{
}

/**
 * 析构函数实现
 */
CAnalysisPanelDialog::~CAnalysisPanelDialog(void)
{
}

/**
 * 创建对话框实现
 */
bool CAnalysisPanelDialog::Create(const long chart,const string name,const int subwin,const int x1,const int y1,const int x2,const int y2)
{
   if(!CAppDialog::Create(chart,name,subwin,x1,y1,x2,y2))
      return false;

   m_symbol.Name(Symbol());

   if(!CreateControls())
      return false;

   UpdateData();

   return true;
}

/**
 * 创建所有控件实现
 */
bool CAnalysisPanelDialog::CreateControls(void)
{
   if(!CreateTitleLabel())
      return false;
   if(!CreateSentimentLabels())
      return false;
   if(!CreatePriceLabels())
      return false;
   if(!CreateTechLabels())
      return false;
   if(!CreateSRLabels())
      return false;
   if(!CreateCloseButton())
      return false;
   return true;
}

/**
 * 创建标题标签实现
 */
bool CAnalysisPanelDialog::CreateTitleLabel(void)
{
   int x1 = INDENT_LEFT;
   int y1 = INDENT_TOP;
   int x2 = ClientAreaWidth() - INDENT_RIGHT;
   int y2 = y1 + LABEL_HEIGHT + 10;

   if(!m_label_title.Create(m_chart_id,m_name+"_Title",m_subwin,x1,y1,x2,y2))
      return false;
   m_label_title.Text("分析");
   m_label_title.FontSize(14);
   m_label_title.FontWeight(FW_BOLD);
   m_label_title.Color(clrBlack);
   if(!Add(m_label_title))
      return false;
   return true;
}

/**
 * 创建市场情绪标签实现
 */
bool CAnalysisPanelDialog::CreateSentimentLabels(void)
{
   int y = INDENT_TOP + LABEL_HEIGHT + 20;

   int x1 = INDENT_LEFT;
   int y1 = y;
   int x2 = ClientAreaWidth() - INDENT_RIGHT;
   int y2 = y1 + LABEL_HEIGHT;

   if(!m_label_sentiment_title.Create(m_chart_id,m_name+"_SentTitle",m_subwin,x1,y1,x2,y2))
      return false;
   m_label_sentiment_title.Text("市场脉动");
   m_label_sentiment_title.FontSize(10);
   m_label_sentiment_title.Color(clrDarkGray);
   if(!Add(m_label_sentiment_title))
      return false;

   y += LABEL_HEIGHT + CONTROLS_GAP_Y;
   y1 = y;
   y2 = y1 + LABEL_HEIGHT;

   if(!m_label_sentiment_buy.Create(m_chart_id,m_name+"_SentBuy",m_subwin,x1,y1,x2/2,y2))
      return false;
   m_label_sentiment_buy.Text("59% 买进");
   m_label_sentiment_buy.FontSize(11);
   m_label_sentiment_buy.Color(clrLime);
   if(!Add(m_label_sentiment_buy))
      return false;

   x1 = x2/2 + 10;
   if(!m_label_sentiment_sell.Create(m_chart_id,m_name+"_SentSell",m_subwin,x1,y1,x2,y2))
      return false;
   m_label_sentiment_sell.Text("41% 卖出");
   m_label_sentiment_sell.FontSize(11);
   m_label_sentiment_sell.Color(clrRed);
   m_label_sentiment_sell.Alignment(WND_ALIGN_RIGHT);
   if(!Add(m_label_sentiment_sell))
      return false;

   return true;
}

/**
 * 创建价格信息标签实现
 */
bool CAnalysisPanelDialog::CreatePriceLabels(void)
{
   int y = INDENT_TOP + LABEL_HEIGHT * 3 + 40;

   int x1 = INDENT_LEFT;
   int y1 = y;
   int x2 = ClientAreaWidth() - INDENT_RIGHT;
   int y2 = y1 + LABEL_HEIGHT;

   if(!m_label_price_title.Create(m_chart_id,m_name+"_PriceTitle",m_subwin,x1,y1,x2,y2))
      return false;
   m_label_price_title.Text("每日价格变化");
   m_label_price_title.FontSize(10);
   m_label_price_title.Color(clrDarkGray);
   if(!Add(m_label_price_title))
      return false;

   y += LABEL_HEIGHT + CONTROLS_GAP_Y;
   y1 = y;
   y2 = y1 + LABEL_HEIGHT;

   if(!m_label_price_change.Create(m_chart_id,m_name+"_PriceChange",m_subwin,x1,y1,x2,y2))
      return false;
   m_label_price_change.Text("↓ -0.28%");
   m_label_price_change.FontSize(11);
   m_label_price_change.Color(clrRed);
   if(!Add(m_label_price_change))
      return false;

   y += LABEL_HEIGHT + CONTROLS_GAP_Y + 5;
   y1 = y;
   y2 = y1 + LABEL_HEIGHT;

   if(!m_label_open.Create(m_chart_id,m_name+"_Open",m_subwin,x1,y1,x2,y2))
      return false;
   m_label_open.Text("开仓     4,865.96");
   m_label_open.FontSize(10);
   m_label_open.Color(clrDarkGray);
   if(!Add(m_label_open))
      return false;

   y += LABEL_HEIGHT + CONTROLS_GAP_Y;
   y1 = y;
   y2 = y1 + LABEL_HEIGHT + 5;

   if(!m_label_current.Create(m_chart_id,m_name+"_Current",m_subwin,x1,y1,x2,y2))
      return false;
   m_label_current.Text("当前     4,863.43");
   m_label_current.FontSize(12);
   m_label_current.FontWeight(FW_BOLD);
   m_label_current.Color(clrBlack);
   if(!Add(m_label_current))
      return false;

   y += LABEL_HEIGHT + CONTROLS_GAP_Y + 5;
   y1 = y;
   y2 = y1 + LABEL_HEIGHT;

   if(!m_label_low.Create(m_chart_id,m_name+"_Low",m_subwin,x1,y1,x2/2,y2))
      return false;
   m_label_low.Text("最低价     4,854.10");
   m_label_low.FontSize(10);
   m_label_low.Color(clrDarkGray);
   if(!Add(m_label_low))
      return false;

   x1 = x2/2 + 10;
   if(!m_label_high.Create(m_chart_id,m_name+"_High",m_subwin,x1,y1,x2,y2))
      return false;
   m_label_high.Text("最高价     4,884.24");
   m_label_high.FontSize(10);
   m_label_high.Color(clrDarkSlateBlue);
   m_label_high.Alignment(WND_ALIGN_RIGHT);
   if(!Add(m_label_high))
      return false;

   return true;
}

/**
 * 创建技术评分标签实现
 */
bool CAnalysisPanelDialog::CreateTechLabels(void)
{
   int y = INDENT_TOP + LABEL_HEIGHT * 8 + 90;

   int x1 = INDENT_LEFT;
   int y1 = y;
   int x2 = ClientAreaWidth() - INDENT_RIGHT;
   int y2 = y1 + LABEL_HEIGHT;

   if(!m_label_tech_title.Create(m_chart_id,m_name+"_TechTitle",m_subwin,x1,y1,x2,y2))
      return false;
   m_label_tech_title.Text("技术评分");
   m_label_tech_title.FontSize(10);
   m_label_tech_title.Color(clrDarkGray);
   if(!Add(m_label_tech_title))
      return false;

   y += LABEL_HEIGHT + CONTROLS_GAP_Y;
   y1 = y;
   y2 = y1 + LABEL_HEIGHT;

   if(!m_label_tech_short.Create(m_chart_id,m_name+"_TechShort",m_subwin,x1,y1,x2,y2))
      return false;
   m_label_tech_short.Text("↓ Short-term");
   m_label_tech_short.FontSize(10);
   m_label_tech_short.Color(clrRed);
   if(!Add(m_label_tech_short))
      return false;

   y += LABEL_HEIGHT + CONTROLS_GAP_Y;
   y1 = y;
   y2 = y1 + LABEL_HEIGHT;

   if(!m_label_tech_medium.Create(m_chart_id,m_name+"_TechMedium",m_subwin,x1,y1,x2,y2))
      return false;
   m_label_tech_medium.Text("↓ Intermediate");
   m_label_tech_medium.FontSize(10);
   m_label_tech_medium.Color(clrRed);
   if(!Add(m_label_tech_medium))
      return false;

   y += LABEL_HEIGHT + CONTROLS_GAP_Y;
   y1 = y;
   y2 = y1 + LABEL_HEIGHT;

   if(!m_label_tech_long.Create(m_chart_id,m_name+"_TechLong",m_subwin,x1,y1,x2,y2))
      return false;
   m_label_tech_long.Text("○ Long-term");
   m_label_tech_long.FontSize(10);
   m_label_tech_long.Color(clrDarkGray);
   if(!Add(m_label_tech_long))
      return false;

   return true;
}

/**
 * 创建支撑阻力标签实现
 */
bool CAnalysisPanelDialog::CreateSRLabels(void)
{
   int y = INDENT_TOP + LABEL_HEIGHT * 12 + 120;

   int x1 = INDENT_LEFT;
   int y1 = y;
   int x2 = ClientAreaWidth() - INDENT_RIGHT;
   int y2 = y1 + LABEL_HEIGHT;

   if(!m_label_sr_title.Create(m_chart_id,m_name+"_SRTitle",m_subwin,x1,y1,x2,y2))
      return false;
   m_label_sr_title.Text("支撑/阻力");
   m_label_sr_title.FontSize(10);
   m_label_sr_title.Color(clrDarkGray);
   if(!Add(m_label_sr_title))
      return false;

   y += LABEL_HEIGHT + CONTROLS_GAP_Y;
   y1 = y;
   y2 = y1 + LABEL_HEIGHT;

   if(!m_label_support.Create(m_chart_id,m_name+"_Support",m_subwin,x1,y1,x2/2,y2))
      return false;
   m_label_support.Text("4,215.25  Support");
   m_label_support.FontSize(11);
   m_label_support.Color(clrLime);
   if(!Add(m_label_support))
      return false;

   x1 = x2/2 + 10;
   if(!m_label_resistance.Create(m_chart_id,m_name+"_Resistance",m_subwin,x1,y1,x2,y2))
      return false;
   m_label_resistance.Text("5,082.22  Resistance");
   m_label_resistance.FontSize(11);
   m_label_resistance.Color(clrRed);
   m_label_resistance.Alignment(WND_ALIGN_RIGHT);
   if(!Add(m_label_resistance))
      return false;

   return true;
}

/**
 * 创建关闭按钮实现
 */
bool CAnalysisPanelDialog::CreateCloseButton(void)
{
   int btn_width = 60;
   int btn_height = 22;
   int x1 = ClientAreaWidth() - INDENT_RIGHT - btn_width;
   int y1 = ClientAreaHeight() - INDENT_BOTTOM - btn_height;
   int x2 = x1 + btn_width;
   int y2 = y1 + btn_height;

   if(!m_button_close.Create(m_chart_id,m_name+"_Close",m_subwin,x1,y1,x2,y2))
      return false;
   m_button_close.Text("关闭");
   m_button_close.FontSize(9);
   if(!Add(m_button_close))
      return false;
   m_button_close.Alignment(WND_ALIGN_RIGHT|WND_ALIGN_BOTTOM,0,0,INDENT_RIGHT,INDENT_BOTTOM);

   return true;
}

/**
 * 更新面板数据实现
 */
void CAnalysisPanelDialog::UpdateData(void)
{
   datetime now = TimeCurrent();
   if(now - m_last_update < 1)
      return;
   m_last_update = now;

   if(!m_symbol.RefreshRates())
      return;

   int buy_percent, sell_percent;
   CalculateSentiment(buy_percent, sell_percent);
   m_label_sentiment_buy.Text(IntegerToString(buy_percent) + "% 买进");
   m_label_sentiment_sell.Text(IntegerToString(sell_percent) + "% 卖出");

   double change = CalculatePriceChange();
   string change_text = (change >= 0 ? "↑ " : "↓ ") + DoubleToString(change, 2) + "%";
   m_label_price_change.Text(change_text);
   m_label_price_change.Color(change >= 0 ? clrLime : clrRed);

   double open = iOpen(_Symbol, PERIOD_D1, 1);
   double current = m_symbol.Bid();
   double low = iLow(_Symbol, PERIOD_D1, 0);
   double high = iHigh(_Symbol, PERIOD_D1, 0);

   m_label_open.Text("开仓     " + DoubleToString(open, m_symbol.Digits()));
   m_label_current.Text("当前     " + DoubleToString(current, m_symbol.Digits()));
   m_label_low.Text("最低价     " + DoubleToString(low, m_symbol.Digits()));
   m_label_high.Text("最高价     " + DoubleToString(high, m_symbol.Digits()));

   int short_score, medium_score, long_score;
   CalculateTechScores(short_score, medium_score, long_score);

   string short_text = (short_score > 0 ? "↑ " : (short_score < 0 ? "↓ " : "○ ")) + "Short-term";
   string medium_text = (medium_score > 0 ? "↑ " : (medium_score < 0 ? "↓ " : "○ ")) + "Intermediate";
   string long_text = (long_score > 0 ? "↑ " : (long_score < 0 ? "↓ " : "○ ")) + "Long-term";

   m_label_tech_short.Text(short_text);
   m_label_tech_short.Color(short_score > 0 ? clrLime : (short_score < 0 ? clrRed : clrDarkGray));
   m_label_tech_medium.Text(medium_text);
   m_label_tech_medium.Color(medium_score > 0 ? clrLime : (medium_score < 0 ? clrRed : clrDarkGray));
   m_label_tech_long.Text(long_text);
   m_label_tech_long.Color(long_score > 0 ? clrLime : (long_score < 0 ? clrRed : clrDarkGray));

   double support, resistance;
   CalculateSupportResistance(support, resistance);
   m_label_support.Text(DoubleToString(support, m_symbol.Digits()) + "  Support");
   m_label_resistance.Text(DoubleToString(resistance, m_symbol.Digits()) + "  Resistance");
}

/**
 * 计算市场情绪实现
 */
void CAnalysisPanelDialog::CalculateSentiment(int &buy_percent, int &sell_percent)
{
   double rsi = iRSI(_Symbol, PERIOD_H1, 14, PRICE_CLOSE, 0);
   buy_percent = (int)MathRound(50 + (50 - rsi));
   sell_percent = 100 - buy_percent;
   buy_percent = MathMax(10, MathMin(90, buy_percent));
   sell_percent = 100 - buy_percent;
}

/**
 * 计算价格变化实现
 */
double CAnalysisPanelDialog::CalculatePriceChange(void)
{
   double open = iOpen(_Symbol, PERIOD_D1, 1);
   double current = m_symbol.Bid();
   if(open == 0) return 0;
   return (current - open) / open * 100;
}

/**
 * 计算技术评分实现
 */
void CAnalysisPanelDialog::CalculateTechScores(int &short_score, int &medium_score, int &long_score)
{
   double macd_main = iMACD(_Symbol, PERIOD_H1, 12, 26, 9, PRICE_CLOSE, MODE_MAIN, 0);
   double macd_signal = iMACD(_Symbol, PERIOD_H1, 12, 26, 9, PRICE_CLOSE, MODE_SIGNAL, 0);
   double rsi = iRSI(_Symbol, PERIOD_H1, 14, PRICE_CLOSE, 0);
   double ma_fast = iMA(_Symbol, PERIOD_H1, 20, 0, MODE_SMA, PRICE_CLOSE, 0);
   double ma_slow = iMA(_Symbol, PERIOD_H1, 50, 0, MODE_SMA, PRICE_CLOSE, 0);

   short_score = 0;
   if(macd_main > macd_signal) short_score++; else short_score--;
   if(rsi < 30) short_score++; else if(rsi > 70) short_score--;
   if(ma_fast > ma_slow) short_score++; else short_score--;

   macd_main = iMACD(_Symbol, PERIOD_H4, 12, 26, 9, PRICE_CLOSE, MODE_MAIN, 0);
   macd_signal = iMACD(_Symbol, PERIOD_H4, 12, 26, 9, PRICE_CLOSE, MODE_SIGNAL, 0);
   rsi = iRSI(_Symbol, PERIOD_H4, 14, PRICE_CLOSE, 0);
   ma_fast = iMA(_Symbol, PERIOD_H4, 20, 0, MODE_SMA, PRICE_CLOSE, 0);
   ma_slow = iMA(_Symbol, PERIOD_H4, 50, 0, MODE_SMA, PRICE_CLOSE, 0);

   medium_score = 0;
   if(macd_main > macd_signal) medium_score++; else medium_score--;
   if(rsi < 30) medium_score++; else if(rsi > 70) medium_score--;
   if(ma_fast > ma_slow) medium_score++; else medium_score--;

   macd_main = iMACD(_Symbol, PERIOD_D1, 12, 26, 9, PRICE_CLOSE, MODE_MAIN, 0);
   macd_signal = iMACD(_Symbol, PERIOD_D1, 12, 26, 9, PRICE_CLOSE, MODE_SIGNAL, 0);
   rsi = iRSI(_Symbol, PERIOD_D1, 14, PRICE_CLOSE, 0);
   ma_fast = iMA(_Symbol, PERIOD_D1, 20, 0, MODE_SMA, PRICE_CLOSE, 0);
   ma_slow = iMA(_Symbol, PERIOD_D1, 50, 0, MODE_SMA, PRICE_CLOSE, 0);

   long_score = 0;
   if(macd_main > macd_signal) long_score++; else long_score--;
   if(rsi < 30) long_score++; else if(rsi > 70) long_score--;
   if(ma_fast > ma_slow) long_score++; else long_score--;
}

/**
 * 计算支撑阻力位实现
 */
void CAnalysisPanelDialog::CalculateSupportResistance(double &support, double &resistance)
{
   int period = 50;
   double lowest = DBL_MAX;
   double highest = 0;

   for(int i = 1; i <= period; i++)
   {
      double low = iLow(_Symbol, PERIOD_D1, i);
      double high = iHigh(_Symbol, PERIOD_D1, i);
      if(low < lowest) lowest = low;
      if(high > highest) highest = high;
   }

   double current = m_symbol.Bid();
   support = lowest + (current - lowest) * 0.3;
   resistance = highest - (highest - current) * 0.3;
}

/**
 * 关闭按钮点击事件实现
 */
void CAnalysisPanelDialog::OnClickClose(void)
{
   ChartIndicatorDelete(m_chart_id, m_subwin, m_name);
}

/**
 * 事件处理实现
 */
bool CAnalysisPanelDialog::OnEvent(const int id,const long &lparam,const double &dparam,const string &sparam)
{
   if(!CAppDialog::OnEvent(id,lparam,dparam,sparam))
      return false;
   return true;
}
