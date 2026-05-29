//+------------------------------------------------------------------+
//|                                                AnalysisPanel.mq5 |
//|                        技术分析面板 - 主指标文件                  |
//|                                                                  |
//+------------------------------------------------------------------+
#property copyright   "Analysis Panel"
#property link        "https://www.mql5.com"
#property version     "1.00"
#property description "技术分析面板 - 显示市场情绪、价格变化、技术评分、支撑阻力位"
#property indicator_separate_window
#property indicator_plots               0
#property indicator_buffers             0
#property indicator_minimum             0.0
#property indicator_maximum             0.0

#include "AnalysisPanelDialog.mqh"

CAnalysisPanelDialog ExtDialog;

/**
 * 指标初始化函数
 * 创建并显示技术分析面板对话框
 * @return int 初始化结果
 */
int OnInit(void)
{
   if(!ExtDialog.Create(0,"技术分析面板",0,30,30,30 + 280,30 + 420))
      return INIT_FAILED;

   if(!ExtDialog.Run())
      return INIT_FAILED;

   return INIT_SUCCEEDED;
}

/**
 * 指标反初始化函数
 * 销毁对话框
 * @param reason 反初始化原因
 */
void OnDeinit(const int reason)
{
   ExtDialog.Destroy(reason);
}

/**
 * 指标计算函数
 * 更新面板数据
 * @param rates_total K线总数
 * @param prev_calculated 上次计算的K线数
 * @param begin 开始位置
 * @param price[] 价格数组
 * @return int 计算结果
 */
int OnCalculate(const int rates_total,
                const int prev_calculated,
                const int begin,
                const double &price[])
{
   ExtDialog.UpdateData();
   return rates_total;
}

/**
 * 图表事件处理函数
 * 处理对话框事件
 * @param id 事件ID
 * @param lparam 长整型参数
 * @param dparam 双精度参数
 * @param sparam 字符串参数
 */
void OnChartEvent(const int id,
                  const long &lparam,
                  const double &dparam,
                  const string &sparam)
{
   ExtDialog.ChartEvent(id,lparam,dparam,sparam);
}
