//+------------------------------------------------------------------+
//|                                                     MQL5_FileUpdate |
//|                      AI 交易系统 - 文件模式数据推送模块           |
//|         写入 JSON 文件，Python 读取（稳定、无连接问题）          |
//+------------------------------------------------------------------+
#property copyright "MT5 AI Trading System"
#property link      ""
#property version   "3.1"
#property strict
#property indicator_chart_window

//+------------------------------------------------------------------+
//| 全局变量                                                         |
//+------------------------------------------------------------------+
input string DataFolder = "MQL5/Files";  // 数据保存文件夹（相对于 MQL5 目录）
input string DataFileName = "mt5_account.json";  // 数据文件名
input int UpdateInterval = 2;         // 更新间隔（秒）

ulong last_update_time = 0;          // 上次更新时间

//+------------------------------------------------------------------+
//| 初始化函数                                                       |
//+------------------------------------------------------------------+
int OnInit()
{
    Print("✅ MQL5 文件模式数据推送模块初始化");
    return(INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
//| 去初始化函数                                                     |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
    Print("🔴 MQL5 文件模式数据推送模块关闭");
}

//+------------------------------------------------------------------+
//| 主循环                                                           |
//+------------------------------------------------------------------+
void OnTick()
{
    ulong current_time = TimeCurrent();
    if(current_time - last_update_time >= UpdateInterval)
    {
        WriteDataToFile();
        last_update_time = current_time;
    }
}

//+------------------------------------------------------------------+
//| 写入数据到 JSON 文件                                             |
//+------------------------------------------------------------------+
void WriteDataToFile()
{
    string json = BuildJsonData();
    if(json == "")
    {
        return;
    }
    
    string file_path = DataFileName;
    
    // 打开文件（重写模式）
    int file_handle = FileOpen(file_path, FILE_WRITE|FILE_TXT|FILE_ANSI);
    if(file_handle == INVALID_HANDLE)
    {
        Print("❌ 打开文件失败: ", file_path, ", 错误: ", GetLastError());
        return;
    }
    
    // 写入数据
    FileWrite(file_handle, json);
    FileClose(file_handle);
    
    // Print("📊 数据已写入: ", file_path);
}

//+------------------------------------------------------------------+
//| 构建 JSON 数据                                                   |
//+------------------------------------------------------------------+
string BuildJsonData()
{
    string result = "{";
    result += "\"type\":\"mql5_data\",";
    result += "\"source\":\"file\",";
    
    // 1. 账户信息
    result += "\"account\":";
    result += BuildAccountJson();
    result += ",";
    
    // 2. 持仓信息
    result += "\"positions\":";
    result += BuildPositionsJson();
    result += ",";
    
    // 3. 时间戳
    result += "\"timestamp\":" + IntegerToString((int)TimeCurrent());
    
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
    json += "\"leverage\":" + IntegerToString((int)AccountInfoInteger(ACCOUNT_LEVERAGE)) + ",";
    json += "\"account\":" + IntegerToString((int)AccountInfoInteger(ACCOUNT_LOGIN)) + ",";
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
        string symbol = PositionGetSymbol(i);
        if(symbol == "")
        {
            continue;
        }
        
        if(!PositionSelect(symbol))
        {
            continue;
        }
        
        if(!first)
        {
            json += ",";
        }
        first = false;
        
        int digits = (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS);
        double current_price = PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY ? 
                              SymbolInfoDouble(symbol, SYMBOL_BID) : 
                              SymbolInfoDouble(symbol, SYMBOL_ASK);
        
        json += "{";
        json += "\"ticket\":" + IntegerToString((int)PositionGetInteger(POSITION_TICKET)) + ",";
        json += "\"symbol\":\"" + symbol + "\",";
        json += "\"type\":\"" + (PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY ? "BUY" : "SELL") + "\",";
        json += "\"volume\":" + DoubleToString(PositionGetDouble(POSITION_VOLUME), 2) + ",";
        json += "\"open_time\":\"" + TimeToString((datetime)PositionGetInteger(POSITION_TIME), TIME_DATE|TIME_SECONDS) + "\",";
        json += "\"open_price\":" + DoubleToString(PositionGetDouble(POSITION_PRICE_OPEN), digits) + ",";
        json += "\"sl\":" + DoubleToString(PositionGetDouble(POSITION_SL), digits) + ",";
        json += "\"tp\":" + DoubleToString(PositionGetDouble(POSITION_TP), digits) + ",";
        json += "\"current_price\":" + DoubleToString(current_price, digits) + ",";
        json += "\"profit\":" + DoubleToString(PositionGetDouble(POSITION_PROFIT), 2) + ",";
        json += "\"swap\":" + DoubleToString(PositionGetDouble(POSITION_SWAP), 2) + ",";
        json += "\"comment\":\"" + PositionGetString(POSITION_COMMENT) + "\"";
        json += "}";
    }
    
    json += "]";
    return json;
}
//+------------------------------------------------------------------+
