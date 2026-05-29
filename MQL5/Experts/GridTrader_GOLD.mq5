//+------------------------------------------------------------------+
//|                                              GridTrader_GOLD.mq5 |
//|                        网格交易EA - 适用于黄金(GOLD/XAUUSD)      |
//|                                                                  |
//+------------------------------------------------------------------+
#property copyright   "Grid Trader"
#property link        "https://www.mql5.com"
#property version     "1.00"
#property description "网格交易EA - 在价格波动中自动建仓和平仓"
#property description "适用于黄金等波动较大的品种"

#define GRID_MAGIC 98765432

#include <Trade\Trade.mqh>
#include <Trade\SymbolInfo.mqh>
#include <Trade\PositionInfo.mqh>
#include <Trade\AccountInfo.mqh>

input double InpLotSize         = 0.01;     // 起始手数
input int    InpGridDistance     = 50;       // 网格间距(点数)
input int    InpMaxGridLevels    = 5;        // 最大网格层数
input int    InpTakeProfit       = 50;       // 止盈点数
input int    InpTradeDirection   = 0;        // 交易方向: 0=双向, 1=仅做多, 2=仅做空
input bool   InpUseDynamicTP     = true;     // 使用动态止盈
input double InpMaxRiskPercent   = 10.0;     // 最大风险百分比

/**
 * 网格交易EA主类
 * 实现网格交易的核心逻辑，包括开仓、加仓、止盈平仓等功能
 */
class CGridTrader
{
protected:
   double            m_adjusted_point;       // 调整后的点值（用于3/5位小数）
   CTrade            m_trade;                 // 交易对象
   CSymbolInfo       m_symbol;                // 品种信息对象
   CPositionInfo     m_position;              // 持仓信息对象
   CAccountInfo      m_account;               // 账户信息对象

   double            m_grid_distance;         // 网格间距（价格）
   double            m_take_profit;           // 止盈距离（价格）
   double            m_lot_size;              // 每单手数
   int               m_max_levels;            // 最大网格层数
   int               m_trade_direction;       // 交易方向

public:
   /**
    * 构造函数
    * 初始化成员变量
    */
                     CGridTrader(void);
   
   /**
    * 析构函数
    */
                    ~CGridTrader(void);
   
   /**
    * 初始化函数
    * 设置交易环境、参数验证、指标初始化
    * @return bool 初始化是否成功
    */
   bool              Init(void);
   
   /**
    * 反初始化函数
    * 清理资源
    */
   void              Deinit(void);
   
   /**
    * 主处理函数
    * 每个tick调用，执行网格交易逻辑
    * @return bool 是否执行了交易操作
    */
   bool              Processing(void);

protected:
   /**
    * 检查输入参数有效性
    * @return bool 参数是否有效
    */
   bool              CheckParameters(void);
   
   /**
    * 统计当前EA的持仓数量
    * @return int 持仓数量
    */
   int               CountOpenPositions(void);
   
   /**
    * 计算所有持仓的平均开仓价格
    * @return double 平均价格
    */
   double            GetAvgPrice(void);
   
   /**
    * 计算所有持仓的总利润
    * @return double 总利润
    */
   double            GetTotalProfit(void);
   
   /**
    * 判断是否可以开多单
    * @return bool 是否可以开多单
    */
   bool              CanOpenBuy(void);
   
   /**
    * 判断是否可以开空单
    * @return bool 是否可以开空单
    */
   bool              CanOpenSell(void);
   
   /**
    * 开多单
    * @return bool 开单是否成功
    */
   bool              OpenBuy(void);
   
   /**
    * 开空单
    * @return bool 开单是否成功
    */
   bool              OpenSell(void);
   
   /**
    * 平掉所有EA的持仓
    * @return bool 平仓是否全部成功
    */
   bool              CloseAllPositions(void);
   
   /**
    * 判断是否达到止盈条件
    * @return bool 是否应该止盈
    */
   bool              ShouldTakeProfit(void);
};

CGridTrader ExtGridTrader;

/**
 * 构造函数实现
 */
CGridTrader::CGridTrader(void) : m_adjusted_point(0),
                                   m_grid_distance(0),
                                   m_take_profit(0),
                                   m_lot_size(0),
                                   m_max_levels(0),
                                   m_trade_direction(0)
{
}

/**
 * 析构函数实现
 */
CGridTrader::~CGridTrader(void)
{
}

/**
 * 初始化函数实现
 * 设置交易环境、调整点值、验证参数
 */
bool CGridTrader::Init(void)
{
   m_symbol.Name(Symbol());
   m_trade.SetExpertMagicNumber(GRID_MAGIC);
   m_trade.SetMarginMode();
   m_trade.SetTypeFillingBySymbol(Symbol());

   int digits_adjust = 1;
   if(m_symbol.Digits() == 3 || m_symbol.Digits() == 5)
      digits_adjust = 10;
   m_adjusted_point = m_symbol.Point() * digits_adjust;

   m_grid_distance = InpGridDistance * m_adjusted_point;
   m_take_profit = InpTakeProfit * m_adjusted_point;
   m_lot_size = InpLotSize;
   m_max_levels = InpMaxGridLevels;
   m_trade_direction = InpTradeDirection;

   m_trade.SetDeviationInPoints(3 * digits_adjust);

   if(!CheckParameters())
      return false;

   return true;
}

/**
 * 参数检查函数实现
 * 验证手数、网格层数等参数的有效性
 */
bool CGridTrader::CheckParameters(void)
{
   if(m_lot_size < m_symbol.LotsMin() || m_lot_size > m_symbol.LotsMax())
   {
      printf("手数必须在 %f 到 %f 之间", m_symbol.LotsMin(), m_symbol.LotsMax());
      return false;
   }

   if(MathAbs(m_lot_size / m_symbol.LotsStep() - MathRound(m_lot_size / m_symbol.LotsStep())) > 1.0E-10)
   {
      printf("手数必须符合最小变动单位 %f", m_symbol.LotsStep());
      return false;
   }

   if(m_max_levels < 1)
   {
      printf("最大网格层数必须大于0");
      return false;
   }

   return true;
}

/**
 * 反初始化函数实现
 */
void CGridTrader::Deinit(void)
{
}

/**
 * 统计持仓数量函数实现
 * 遍历所有持仓，统计由本EA创建的持仓
 */
int CGridTrader::CountOpenPositions(void)
{
   int count = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      if(m_position.SelectByIndex(i))
      {
         if(m_position.Symbol() == m_symbol.Name() && m_position.Magic() == GRID_MAGIC)
            count++;
      }
   }
   return count;
}

/**
 * 计算平均价格函数实现
 * 按手数加权计算所有持仓的平均开仓价
 */
double CGridTrader::GetAvgPrice(void)
{
   double total_price = 0;
   double total_lots = 0;

   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      if(m_position.SelectByIndex(i))
      {
         if(m_position.Symbol() == m_symbol.Name() && m_position.Magic() == GRID_MAGIC)
         {
            total_price += m_position.PriceOpen() * m_position.Volume();
            total_lots += m_position.Volume();
         }
      }
   }

   if(total_lots > 0)
      return total_price / total_lots;
   return 0;
}

/**
 * 计算总利润函数实现
 * 累加所有持仓的浮动盈亏
 */
double CGridTrader::GetTotalProfit(void)
{
   double total_profit = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      if(m_position.SelectByIndex(i))
      {
         if(m_position.Symbol() == m_symbol.Name() && m_position.Magic() == GRID_MAGIC)
         {
            total_profit += m_position.Profit();
         }
      }
   }
   return total_profit;
}

/**
 * 判断是否可以开多单函数实现
 * 检查交易方向、层数限制、网格间距条件
 */
bool CGridTrader::CanOpenBuy(void)
{
   if(m_trade_direction == 2)
      return false;

   int pos_count = CountOpenPositions();
   if(pos_count >= m_max_levels)
      return false;

   if(pos_count == 0)
      return true;

   double min_buy_price = DBL_MAX;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      if(m_position.SelectByIndex(i))
      {
         if(m_position.Symbol() == m_symbol.Name() && 
            m_position.Magic() == GRID_MAGIC && 
            m_position.PositionType() == POSITION_TYPE_BUY)
         {
            if(m_position.PriceOpen() < min_buy_price)
               min_buy_price = m_position.PriceOpen();
         }
      }
   }

   if(min_buy_price != DBL_MAX)
   {
      if(m_symbol.Ask() <= min_buy_price - m_grid_distance)
         return true;
   }

   return false;
}

/**
 * 判断是否可以开空单函数实现
 * 检查交易方向、层数限制、网格间距条件
 */
bool CGridTrader::CanOpenSell(void)
{
   if(m_trade_direction == 1)
      return false;

   int pos_count = CountOpenPositions();
   if(pos_count >= m_max_levels)
      return false;

   if(pos_count == 0)
      return true;

   double max_sell_price = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      if(m_position.SelectByIndex(i))
      {
         if(m_position.Symbol() == m_symbol.Name() && 
            m_position.Magic() == GRID_MAGIC && 
            m_position.PositionType() == POSITION_TYPE_SELL)
         {
            if(m_position.PriceOpen() > max_sell_price)
               max_sell_price = m_position.PriceOpen();
         }
      }
   }

   if(max_sell_price > 0)
   {
      if(m_symbol.Bid() >= max_sell_price + m_grid_distance)
         return true;
   }

   return false;
}

/**
 * 开多单函数实现
 * 检查保证金后开多单
 */
bool CGridTrader::OpenBuy(void)
{
   double price = m_symbol.Ask();
   if(m_account.FreeMarginCheck(m_symbol.Name(), ORDER_TYPE_BUY, m_lot_size, price) < 0.0)
   {
      printf("保证金不足，无法开多单");
      return false;
   }

   if(m_trade.PositionOpen(m_symbol.Name(), ORDER_TYPE_BUY, m_lot_size, price, 0.0, 0.0))
   {
      printf("开多单成功: %s, 价格: %f, 手数: %f", m_symbol.Name(), price, m_lot_size);
      return true;
   }
   else
   {
      printf("开多单失败: %s", m_trade.ResultComment());
      return false;
   }
}

/**
 * 开空单函数实现
 * 检查保证金后开空单
 */
bool CGridTrader::OpenSell(void)
{
   double price = m_symbol.Bid();
   if(m_account.FreeMarginCheck(m_symbol.Name(), ORDER_TYPE_SELL, m_lot_size, price) < 0.0)
   {
      printf("保证金不足，无法开空单");
      return false;
   }

   if(m_trade.PositionOpen(m_symbol.Name(), ORDER_TYPE_SELL, m_lot_size, price, 0.0, 0.0))
   {
      printf("开空单成功: %s, 价格: %f, 手数: %f", m_symbol.Name(), price, m_lot_size);
      return true;
   }
   else
   {
      printf("开空单失败: %s", m_trade.ResultComment());
      return false;
   }
}

/**
 * 平仓函数实现
 * 平掉所有由本EA创建的持仓
 */
bool CGridTrader::CloseAllPositions(void)
{
   bool result = true;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      if(m_position.SelectByIndex(i))
      {
         if(m_position.Symbol() == m_symbol.Name() && m_position.Magic() == GRID_MAGIC)
         {
            if(m_trade.PositionClose(m_symbol.Name()))
            {
               printf("平仓成功: %s, 利润: %f", m_symbol.Name(), m_position.Profit());
            }
            else
            {
               printf("平仓失败: %s", m_trade.ResultComment());
               result = false;
            }
         }
      }
   }
   return result;
}

/**
 * 止盈判断函数实现
 * 根据动态或静态止盈条件判断是否平仓
 */
bool CGridTrader::ShouldTakeProfit(void)
{
   int pos_count = CountOpenPositions();
   if(pos_count == 0)
      return false;

   double avg_price = GetAvgPrice();
   if(avg_price == 0)
      return false;

   int buy_count = 0;
   int sell_count = 0;
   double buy_profit = 0;
   double sell_profit = 0;

   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      if(m_position.SelectByIndex(i))
      {
         if(m_position.Symbol() == m_symbol.Name() && m_position.Magic() == GRID_MAGIC)
         {
            if(m_position.PositionType() == POSITION_TYPE_BUY)
            {
               buy_count++;
               if(m_symbol.Bid() >= m_position.PriceOpen() + m_take_profit)
                  buy_profit += m_position.Profit();
            }
            else
            {
               sell_count++;
               if(m_symbol.Ask() <= m_position.PriceOpen() - m_take_profit)
                  sell_profit += m_position.Profit();
            }
         }
      }
   }

   if(InpUseDynamicTP)
   {
      double total_profit = GetTotalProfit();
      if(total_profit > 0 && (buy_count == 0 || sell_count == 0))
         return true;
   }
   else
   {
      if(buy_count > 0 && sell_count == 0)
      {
         if(m_symbol.Bid() >= avg_price + m_take_profit)
            return true;
      }
      else if(sell_count > 0 && buy_count == 0)
      {
         if(m_symbol.Ask() <= avg_price - m_take_profit)
            return true;
      }
   }

   return false;
}

/**
 * 主处理函数实现
 * 每个tick调用，依次检查止盈、开仓、加仓条件
 */
bool CGridTrader::Processing(void)
{
   if(!m_symbol.RefreshRates())
      return false;

   int pos_count = CountOpenPositions();

   if(pos_count > 0 && ShouldTakeProfit())
   {
      printf("达到止盈条件，全部平仓");
      CloseAllPositions();
      return true;
   }

   if(pos_count == 0)
   {
      if(m_trade_direction != 2)
         OpenBuy();
      if(m_trade_direction != 1)
         OpenSell();
      return true;
   }

   if(CanOpenBuy())
   {
      OpenBuy();
      return true;
   }

   if(CanOpenSell())
   {
      OpenSell();
      return true;
   }

   return false;
}

int OnInit(void)
{
   if(!ExtGridTrader.Init())
      return INIT_FAILED;
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   ExtGridTrader.Deinit();
}

void OnTick(void)
{
   static datetime last_trade_time = 0;
   if(TimeCurrent() >= last_trade_time + 1)
   {
      if(ExtGridTrader.Processing())
         last_trade_time = TimeCurrent();
   }
}
