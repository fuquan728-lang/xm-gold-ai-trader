#property strict
#property version   "1.00"
#property description "Read-only safety monitor for xm-gold-ai-trader. This EA never sends orders."

input string InpSymbol = "GOLD_";
input bool InpAllowLiveTrading = false;
input int InpMaxSpreadPoints = 350;

int OnInit()
{
   if(!SymbolSelect(InpSymbol, true))
   {
      Print("Failed to select symbol: ", InpSymbol);
      return INIT_FAILED;
   }

   Print("xm-gold-ai-trader safety guard initialized for ", InpSymbol);
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   Comment("");
}

void OnTick()
{
   if(!SymbolSelect(InpSymbol, true))
   {
      Comment("xm-gold-ai-trader\nSymbol unavailable: ", InpSymbol);
      return;
   }

   long account_trade_mode = AccountInfoInteger(ACCOUNT_TRADE_MODE);
   bool is_demo = (account_trade_mode == ACCOUNT_TRADE_MODE_DEMO);
   bool live_blocked = (!InpAllowLiveTrading && !is_demo);

   double point = SymbolInfoDouble(InpSymbol, SYMBOL_POINT);
   double tick_size = SymbolInfoDouble(InpSymbol, SYMBOL_TRADE_TICK_SIZE);
   double tick_value = SymbolInfoDouble(InpSymbol, SYMBOL_TRADE_TICK_VALUE);
   double contract_size = SymbolInfoDouble(InpSymbol, SYMBOL_TRADE_CONTRACT_SIZE);
   double volume_min = SymbolInfoDouble(InpSymbol, SYMBOL_VOLUME_MIN);
   double volume_max = SymbolInfoDouble(InpSymbol, SYMBOL_VOLUME_MAX);
   double volume_step = SymbolInfoDouble(InpSymbol, SYMBOL_VOLUME_STEP);
   long spread = SymbolInfoInteger(InpSymbol, SYMBOL_SPREAD);
   long stops_level = SymbolInfoInteger(InpSymbol, SYMBOL_TRADE_STOPS_LEVEL);

   string status = "OK";
   if(live_blocked)
      status = "LIVE BLOCKED";
   else if(spread > InpMaxSpreadPoints)
      status = "SPREAD TOO WIDE";

   Comment(
      "xm-gold-ai-trader safety guard\n",
      "Status: ", status, "\n",
      "Symbol: ", InpSymbol, "\n",
      "Demo account: ", (is_demo ? "true" : "false"), "\n",
      "Live allowed by EA input: ", (InpAllowLiveTrading ? "true" : "false"), "\n",
      "Spread points: ", spread, " / max ", InpMaxSpreadPoints, "\n",
      "Point: ", DoubleToString(point, 10), "\n",
      "Tick size: ", DoubleToString(tick_size, 10), "\n",
      "Tick value: ", DoubleToString(tick_value, 4), "\n",
      "Contract size: ", DoubleToString(contract_size, 4), "\n",
      "Volume min/max/step: ",
      DoubleToString(volume_min, 4), " / ",
      DoubleToString(volume_max, 4), " / ",
      DoubleToString(volume_step, 4), "\n",
      "Stops level: ", stops_level
   );
}
