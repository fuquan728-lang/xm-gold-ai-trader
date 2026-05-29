//+------------------------------------------------------------------+
//|                                                      MQL5_Update |
//|                                  AI 交易系统 - 数据推送模块      |
//|         向 Python 服务推送账户、持仓、交易历史数据               |
//+------------------------------------------------------------------+
#property copyright "MT5 AI Trading System"
#property link      ""
#property version   "3.1"

//+------------------------------------------------------------------+
//| 全局变量                                                         |
//+------------------------------------------------------------------+
input string ServerIP = "127.0.0.1";  // Python 服务器 IP
input int ServerPort = 8080;          // Python 服务器端口
input int UpdateInterval = 5;         // 更新间隔（秒）

int socket = -1;                      // Socket 连接句柄
ulong last_update_time = 0;          // 上次更新时间

//+------------------------------------------------------------------+
//| 初始化函数                                                       |
//+------------------------------------------------------------------+
int OnInit()
{
    Print("✅ MQL5 数据推送模块初始化");
    ConnectToServer();
    return(INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
//| 去初始化函数                                                     |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
    Print("🔴 MQL5 数据推送模块关闭");
    DisconnectFromServer();
}

//+------------------------------------------------------------------+
//| 主循环                                                           |
//+------------------------------------------------------------------+
void OnTick()
{
    // 定时推送数据
    ulong current_time = TimeCurrent();
    if(current_time - last_update_time >= UpdateInterval)
    {
        PushDataToServer();
        last_update_time = current_time;
    }
}

//+------------------------------------------------------------------+
//| 连接服务器                                                       |
//+------------------------------------------------------------------+
bool ConnectToServer()
{
    if(socket != -1)
    {
        SocketClose(socket);
    }
    
    socket = SocketCreate();
    if(socket == INVALID_HANDLE)
    {
        Print("❌ 创建 Socket 失败");
        return false;
    }
    
    if(!SocketConnect(socket, ServerIP, ServerPort, 10000))
    {
        Print("❌ 连接服务器失败: ", ServerIP, ":", ServerPort);
        SocketClose(socket);
        socket = -1;
        return false;
    }
    
    Print("✅ Socket 连接成功: ", ServerIP, ":", ServerPort);
    return true;
}

//+------------------------------------------------------------------+
//| 断开连接                                                         |
//+------------------------------------------------------------------+
void DisconnectFromServer()
{
    if(socket != -1)
    {
        SocketClose(socket);
        socket = -1;
    }
}

//+------------------------------------------------------------------+
//| 推送数据到服务器                                                 |
//+------------------------------------------------------------------+
void PushDataToServer()
{
    // 确保连接
    if(socket == -1 || !SocketIsConnected(socket))
    {
        Print("⚠️  Socket 未连接，尝试重连...");
        if(!ConnectToServer())
        {
            return;
        }
    }
    
    // 构建数据
    string json = BuildJsonData();
    if(json == "")
    {
        return;
    }
    
    // 发送数据
    if(SendJsonData(json))
    {
        Print("📊 数据推送成功");
    }
}

//+------------------------------------------------------------------+
//| 构建 JSON 数据                                                   |
//+------------------------------------------------------------------+
string BuildJsonData()
{
    string result = "{";
    result += "\"type\":\"mql5_data\",";
    
    // 1. 账户信息
    result += "\"account\":";
    result += BuildAccountJson();
    result += ",";
    
    // 2. 持仓信息
    result += "\"positions\":";
    result += BuildPositionsJson();
    result += ",";
    
    // 3. 历史交易（最近 50 笔）
    result += "\"history\":";
    result += BuildHistoryJson();
    
    result += "}";
    
    return result;
}

//+------------------------------------------------------------------+
//| 构建账户 JSON                                                    |
//+------------------------------------------------------------------+
string BuildAccountJson()
{
    string json = "{";
    
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
    
    json += "}";
    return json;
}

//+------------------------------------------------------------------+
//| 构建持仓 JSON                                                    |
//+------------------------------------------------------------------+
string BuildPositionsJson()
{
    string json = "[";
    
    int pos_count = PositionsTotal();
    bool first = true;
    
    for(int i = 0; i < pos_count; i++)
    {
        if(PositionGetSymbol(i) == "")
        {
            continue;
        }
        
        if(!first)
        {
            json += ",";
        }
        first = false;
        
        json += "{";
        json += "\"ticket\":" + IntegerToString((ulong)PositionGetInteger(POSITION_TICKET)) + ",";
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
    
    json += "]";
    return json;
}

//+------------------------------------------------------------------+
//| 构建历史交易 JSON                                                |
//+------------------------------------------------------------------+
string BuildHistoryJson()
{
    string json = "[";
    
    datetime from_date = TimeCurrent() - PeriodSeconds(PERIOD_D1) * 7;  // 最近 7 天
    datetime to_date = TimeCurrent();
    
    if(HistorySelect(from_date, to_date))
    {
        bool first = true;
        int count = HistoryDealsTotal();
        int limit = MathMin(count, 50);  // 最多 50 笔
        
        for(int i = 0; i < limit; i++)
        {
            ulong deal_ticket = HistoryDealGetTicket(i);
            if(deal_ticket == 0)
            {
                continue;
            }
            
            long deal_entry = HistoryDealGetInteger(deal_ticket, DEAL_ENTRY);
            if(deal_entry != DEAL_ENTRY_OUT)
            {
                continue;  // 只看平仓
            }
            
            if(!first)
            {
                json += ",";
            }
            first = false;
            
            string symbol = HistoryDealGetString(deal_ticket, DEAL_SYMBOL);
            int digits = (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS);
            
            json += "{";
            json += "\"ticket\":" + IntegerToString((ulong)HistoryDealGetInteger(deal_ticket, DEAL_ORDER)) + ",";
            json += "\"symbol\":\"" + symbol + "\",";
            json += "\"type\":\"" + (HistoryDealGetInteger(deal_ticket, DEAL_TYPE) == DEAL_TYPE_BUY ? "BUY" : "SELL") + "\",";
            json += "\"volume\":" + DoubleToString(HistoryDealGetDouble(deal_ticket, DEAL_VOLUME), 2) + ",";
            json += "\"open_time\":\"" + TimeToString((datetime)HistoryDealGetInteger(deal_ticket, DEAL_TIME_MSC), TIME_DATE|TIME_SECONDS) + "\",";
            json += "\"open_price\":" + DoubleToString(0, digits) + ",";
            json += "\"close_time\":\"" + TimeToString((datetime)HistoryDealGetInteger(deal_ticket, DEAL_TIME_MSC), TIME_DATE|TIME_SECONDS) + "\",";
            json += "\"close_price\":" + DoubleToString(HistoryDealGetDouble(deal_ticket, DEAL_PRICE), digits) + ",";
            json += "\"profit\":" + DoubleToString(HistoryDealGetDouble(deal_ticket, DEAL_PROFIT), 2) + ",";
            json += "\"swap\":" + DoubleToString(HistoryDealGetDouble(deal_ticket, DEAL_SWAP), 2) + ",";
            json += "\"commission\":" + DoubleToString(HistoryDealGetDouble(deal_ticket, DEAL_COMMISSION), 2) + ",";
            json += "\"comment\":\"" + HistoryDealGetString(deal_ticket, DEAL_COMMENT) + "\"";
            json += "}";
        }
    }
    
    json += "]";
    return json;
}

//+------------------------------------------------------------------+
//| 发送 JSON 数据                                                   |
//+------------------------------------------------------------------+
bool SendJsonData(string json)
{
    if(socket == -1)
    {
        Print("❌ Socket 未连接");
        return false;
    }
    
    string send_data = json + "\n";
    uchar data[];
    StringToCharArray(send_data, data);
    
    int sent = SocketSend(socket, data, ArraySize(data));
    if(sent <= 0)
    {
        Print("❌ 数据发送失败");
        return false;
    }
    
    // 接收响应（可选，部分MT5版本不支持SocketReceive，跳过）
    // uchar resp[];
    // ArrayResize(resp, 4096);
    // int received = SocketReceive(socket, resp, 1000);
    // if(received > 0)
    // {
    //     string resp_str = CharArrayToString(resp);
    // }
    
    return true;
}
//+------------------------------------------------------------------+
