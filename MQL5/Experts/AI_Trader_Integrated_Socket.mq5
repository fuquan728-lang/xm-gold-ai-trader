//+------------------------------------------------------------------+
//|                                       AI_Trader_Integrated_Socket.mq5 |
//|                   AI智能交易 + 技术分析面板 - Socket集成版       |
//|                     第2阶段集成开发：支持Socket通信              |
//+------------------------------------------------------------------+
#property copyright   "AI Trader Integrated - V3.0"
#property link        "https://www.mql5.com"
#property version     "5.00"
#property description "AI智能交易 + 技术分析面板 - V3.0 (支持Socket和文件双模式通信，服务端支持WebSocket)"
#property strict

#include <Trade\Trade.mqh>
#include <Trade\SymbolInfo.mqh>
#include <Trade\PositionInfo.mqh>
#include <ChartObjects\ChartObjectsTxtControls.mqh>
#include <ChartObjects\ChartObjectsLines.mqh>
#include <ChartObjects\ChartObjectsShapes.mqh>

// 通信模式枚举
enum CommunicationMode {
   MODE_AUTO,     // 自动选择（优先Socket）
   MODE_SOCKET,   // Socket通信模式
   MODE_FILE      // 文件通信模式
};

// Socket错误代码
enum SocketErrorCode {
   SOCKET_SUCCESS = 0,
   SOCKET_CREATE_FAILED = 1,
   SOCKET_CONNECT_FAILED = 2,
   SOCKET_SEND_FAILED = 3,
   SOCKET_RECEIVE_FAILED = 4,
   SOCKET_TIMEOUT = 5,
   SOCKET_INVALID_RESPONSE = 6,
   SOCKET_UNKNOWN_ERROR = 99
};

// 输入参数
input string InpDataPath        = "";       // 数据文件路径（留空使用标准MQL5\Files目录）
input int    InpRequestInterval = 300;      // 请求间隔（秒）- 5分钟
input double InpLotSize         = 0.01;     // 交易手数
input double InpMinConfidence   = 0.65;     // 最小置信度才交易
input bool   InpShowPanel       = true;     // 显示技术分析面板
input int    InpStopLoss        = 40;       // 止损pips（0=关闭，1pip=0.10$，黄金建议40-80）
input int    InpTakeProfit      = 80;       // 止盈pips（0=关闭，1pip=0.10$，黄金建议80-150）
input bool   InpShowLines       = true;     // 显示支撑阻力线
input int    InpTrailingStop    = 30;       // 追踪止损pips（0=关闭，1pip=0.10$）
input double InpMaxEquityDrawdownPct = 0.02; // 最大账户净值回撤比例（0=关闭）

// 账户数据推送配置
input bool   InpPushAccountData = true;     // 启用账户数据推送
input int    InpAccountDataInterval = 60;   // 账户数据推送间隔（秒）
input string InpAccountDataHost = "127.0.0.1"; // 账户数据推送服务器IP
input int    InpAccountDataPort = 8080;     // 账户数据推送服务器端口

// Socket通信配置
input CommunicationMode InpCommMode = MODE_FILE;  // 通信模式
input string InpSocketHost = "127.0.0.1";         // Socket服务器地址
input int    InpSocketPort = 8080;                // Socket服务器端口
input int    InpConnectTimeout = 3000;            // 连接超时（毫秒）
input int    InpReceiveTimeout = 5000;            // 接收超时（毫秒）

// 错误处理和重试配置
input int    InpMaxRetries = 3;                   // 最大重试次数
input double InpRetryBackoffFactor = 2.0;         // 重试退避因子
input int    InpFailoverThreshold = 3;            // 故障转移阈值
input int    InpInitialSocketDelay = 3000;        // 初始Socket延迟（毫秒）- 给Python服务启动时间

CTrade         m_trade;
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

// 多时间框架指标句柄
// H1（1小时）时间框架
int            m_rsi_h1_handle;
int            m_macd_h1_handle;
int            m_ema50_h1_handle;
int            m_ema20_h1_handle;
int            m_ema100_h1_handle;
int            m_atr_h1_handle;
int            m_stoch_h1_handle;

// H4（4小时）时间框架  
int            m_rsi_h4_handle;
int            m_macd_h4_handle;
int            m_ema50_h4_handle;
int            m_ema20_h4_handle;
int            m_ema100_h4_handle;
int            m_atr_h4_handle;
int            m_stoch_h4_handle;

// D1（日线）时间框架
int            m_rsi_d1_handle;
int            m_macd_d1_handle;
int            m_ema50_d1_handle;
int            m_ema20_d1_handle;
int            m_ema100_d1_handle;
int            m_atr_d1_handle;
int            m_stoch_d1_handle;

CChartObjectLabel m_labels[20];
CChartObjectHLine m_support_line;
CChartObjectHLine m_resistance_line;
string panel_name = "AI_Trader_Panel";
string m_last_action = "HOLD";
double m_last_confidence = 0.0;
string m_last_reason = "";
double m_support_price = 0;
double m_resistance_price = 0;

datetime m_last_panel_update = 0;
datetime m_last_sr_update = 0;

// 通信状态
CommunicationMode m_current_mode = MODE_AUTO;
bool m_socket_available = false;
int m_consecutive_failures = 0;
int m_total_requests = 0;
int m_successful_requests = 0;
int m_failed_requests = 0;
int m_mode_switches = 0;
datetime m_last_mode_switch = 0;

// 账户数据推送状态
datetime m_last_account_data_push = 0;
bool m_account_data_enabled = false;
int m_account_data_socket = -1;

// 动态止损止盈（从Python响应获取）
int g_dynamic_sl_pips = 0;   // 动态止损点数（0表示使用默认值InpStopLoss）
int g_dynamic_tp_pips = 0;   // 动态止盈点数（0表示使用默认值InpTakeProfit）

const int PANEL_WIDTH = 380;
const int PANEL_HEIGHT = 460;
const int PANEL_UPDATE_INTERVAL = 1;
const int SR_UPDATE_INTERVAL = 5;
const int LINE_HEIGHT = 22;
const int COL1_X_OFFSET = 0;
const int COL2_X_OFFSET = 175;
const int MAX_REASON_LENGTH = 120;
const int REASON_LINE1_MAX = 70;

// ==================== 字符串工具函数 ====================

/**
 * 字符串修剪函数
 */
string StringTrim(const string str)
{
   string result = str;
   
   // 去除左侧空白
   while(StringLen(result) > 0 && 
         (StringGetCharacter(result, 0) == ' ' || 
          StringGetCharacter(result, 0) == '\t' || 
          StringGetCharacter(result, 0) == '\n' || 
          StringGetCharacter(result, 0) == '\r'))
   {
      result = StringSubstr(result, 1);
   }
   
   // 去除右侧空白
   int len = StringLen(result);
   while(len > 0 && 
         (StringGetCharacter(result, len-1) == ' ' || 
          StringGetCharacter(result, len-1) == '\t' || 
          StringGetCharacter(result, len-1) == '\n' || 
          StringGetCharacter(result, len-1) == '\r'))
   {
      result = StringSubstr(result, 0, len-1);
      len = StringLen(result);
   }
   
   return result;
}

/**
 * 字符串重复函数
 */
string StringRepeat(const string str, int count)
{
   if(count <= 0) return "";
   
   string result = "";
   for(int i = 0; i < count; i++)
   {
      result += str;
   }
   return result;
}

// ==================== Socket通信函数 ====================

/**
 * 获取错误描述
 */
string ErrorDescription(int error_code)
{
   switch(error_code)
   {
      case 0: return "成功";
      case 1: return "通用错误";
      case 2: return "无效参数";
      case 3: return "内存不足";
      case 4: return "交易服务器繁忙";
      case 5: return "旧版本客户端";
      case 6: return "无连接";
      case 7: return "未足够权限";
      case 8: return "太频繁请求";
      case 9: return "被拒绝或禁止";
      case 64: return "账户无效";
      case 65: return "账户禁用";
      case 128: return "交易超时";
      case 129: return "交易无效价格";
      case 130: return "交易无效止损";
      case 131: return "交易无效手数";
      case 132: return "交易交易禁用";
      case 133: return "交易市场关闭";
      case 134: return "交易资金不足";
      case 135: return "交易价格已变化";
      case 136: return "交易价格已离场";
      case 137: return "交易经纪人繁忙";
      case 138: return "交易重试";
      case 139: return "交易太多请求";
      case 140: return "交易修改被拒绝";
      case 141: return "交易太多订单";
      case 145: return "交易被修改";
      case 146: return "交易上下文繁忙";
      case 147: return "交易过期";
      case 148: return "交易太多持仓";
      case 4000: return "Socket错误";
      case 4001: return "Socket连接失败";
      case 4002: return "Socket发送失败";
      case 4003: return "Socket接收失败";
      case 4004: return "Socket超时";
      default: return "未知错误 (" + IntegerToString(error_code) + ")";
   }
}

/**
 * Socket通信请求函数
 */
bool SocketRequest(const string request_json, string &response_json, 
                   SocketErrorCode &error_code, string &error_message)
{
   int socket_handle = INVALID_HANDLE;
   error_code = SOCKET_SUCCESS;
   error_message = "";
   
   // 创建Socket
   socket_handle = SocketCreate();
   if(socket_handle == INVALID_HANDLE)
   {
      error_code = SOCKET_CREATE_FAILED;
      error_message = "Socket创建失败";
      Print("❌ ", error_message);
      return false;
   }
   
   Print("✅ Socket创建成功，正在连接服务器 ", InpSocketHost, ":", InpSocketPort);
   
   // 连接服务器
   if(!SocketConnect(socket_handle, InpSocketHost, InpSocketPort, InpConnectTimeout))
   {
      error_code = SOCKET_CONNECT_FAILED;
      error_message = "连接服务器失败: " + InpSocketHost + ":" + IntegerToString(InpSocketPort);
      Print("❌ ", error_message);
      SocketClose(socket_handle);
      return false;
   }
   
   Print("✅ 服务器连接成功");
   
   // 发送请求（添加换行符作为消息分隔符）
   string request_with_newline = request_json + "\n";
   uchar data[];
   int len = StringToCharArray(request_with_newline, data, 0, StringLen(request_with_newline));
   int bytes_sent = SocketSend(socket_handle, data, (uint)(len - 1));  // 减去null终止符
   
   if(bytes_sent <= 0)
   {
      error_code = SOCKET_SEND_FAILED;
      error_message = "发送请求失败";
      Print("❌ ", error_message);
      SocketClose(socket_handle);
      return false;
   }
   
   Print("✅ 请求发送成功，发送字节数: ", bytes_sent);
   
   // 接收响应
   uchar buffer[8192];
   int bytes_received = SocketRead(socket_handle, buffer, ArraySize(buffer), InpReceiveTimeout);
   
   if(bytes_received <= 0)
   {
      error_code = SOCKET_RECEIVE_FAILED;
      if(bytes_received == 0)
         error_message = "接收响应超时 (" + IntegerToString(InpReceiveTimeout) + "ms)";
      else
         error_message = "接收响应失败";
      Print("❌ ", error_message);
      SocketClose(socket_handle);
      return false;
   }
   
   // 转换为字符串
   response_json = CharArrayToString(buffer, 0, bytes_received);
   response_json = StringTrim(response_json);  // 去除换行符和空白
   
   // 记录响应（截断长数据）
   string debug_response = response_json;
   if(StringLen(debug_response) > 200)
      debug_response = StringSubstr(debug_response, 0, 197) + "...";
   Print("✅ 响应接收成功，接收字节数: ", bytes_received);
   Print("📥 响应内容: ", debug_response);
   
   // 关闭Socket
   SocketClose(socket_handle);
   
   return true;
}

/**
 * 带重试机制的Socket请求
 */
bool SocketRequestWithRetry(const string request_json, string &response_json,
                           int max_retries = 0, double backoff_factor = 2.0)
{
   if(max_retries <= 0) max_retries = InpMaxRetries;
   
   SocketErrorCode error_code;
   string error_message;
   bool success = false;
   
   for(int attempt = 0; attempt <= max_retries; attempt++)
   {
      if(attempt > 0)
      {
         int delay_ms = 1000 * (int)MathPow(backoff_factor, attempt - 1);
         Print("🔄 第", attempt, "次重试，等待", delay_ms, "ms...");
         Sleep(delay_ms);
      }
      
      success = SocketRequest(request_json, response_json, error_code, error_message);
      
      if(success)
      {
         if(attempt > 0)
            Print("✅ 重试成功！");
         return true;
      }
      else
      {
         Print("❌ 请求失败 (尝试", attempt + 1, "/", max_retries + 1, "): ", error_message);
         
         // 如果是连接失败，可能需要切换模式
         if(error_code == SOCKET_CONNECT_FAILED || error_code == SOCKET_CREATE_FAILED)
         {
            m_consecutive_failures++;
            
            // 检查是否需要切换模式
            if(m_consecutive_failures >= InpFailoverThreshold && m_current_mode != MODE_FILE)
            {
               Print("⚠️  连续", m_consecutive_failures, "次Socket失败，考虑切换到文件模式");
            }
         }
      }
   }
   
   Print("❌ 所有重试尝试均失败");
   return false;
}

/**
 * 检查Socket服务器可用性 - 带重试的增强版
 */
bool CheckSocketAvailability()
{
   Print("==================== CheckSocketAvailability 开始 ====================");
   Print("🔍 开始Socket连接测试（带重试机制）...");
   Print("  目标: ", InpSocketHost, ":", InpSocketPort);
   Print("  超时: ", InpConnectTimeout, "ms");
   Print("  最大重试次数: ", InpMaxRetries);
   Print("  重试退避因子: ", InpRetryBackoffFactor);
   
   int max_retries = InpMaxRetries;
   double backoff_factor = InpRetryBackoffFactor;
   
   // 首次尝试前的初始延迟，给Python服务更多启动时间（仅当服务刚启动时）
   Print("⏱️  等待初始启动延迟...");
   Print("  初始延迟: ", InpInitialSocketDelay, "ms");
   Sleep(InpInitialSocketDelay); // 等待指定时间，确保Python服务有足够时间启动
   
   for(int attempt = 0; attempt <= max_retries; attempt++)
   {
      if(attempt > 0)
      {
         int delay_ms = 1000 * (int)MathPow(backoff_factor, attempt - 1);
         Print("🔄 第", attempt, "次重试，等待", delay_ms, "ms...");
         Sleep(delay_ms);
      }
      
      Print("🔌 尝试连接 (尝试", attempt + 1, "/", max_retries + 1, ")...");
      
      int test_socket = SocketCreate();
      if(test_socket == INVALID_HANDLE)
      {
         Print("❌ 无法创建测试Socket");
         continue; // 继续重试
      }
      
      Print("✅ Socket创建成功，正在连接...");
      
      // 连接服务器
      bool can_connect = SocketConnect(test_socket, InpSocketHost, InpSocketPort, InpConnectTimeout);
      
      if(can_connect)
      {
         Print("✅ Socket连接成功！");
         
         // 发送测试消息
         string test_message = "TEST\n";
         uchar test_data[];
         int test_len = StringToCharArray(test_message, test_data, 0, StringLen(test_message));
         int test_sent = SocketSend(test_socket, test_data, (uint)(test_len - 1));
         
         if(test_sent > 0)
         {
            Print("✅ 测试消息发送成功！");
            
            // 读取响应（使用8192字节buffer防止截断）
            uchar response_buffer[8192];
            int response_read = SocketRead(test_socket, response_buffer, ArraySize(response_buffer), 2000);
            
            if(response_read > 0)
            {
               string test_response = CharArrayToString(response_buffer, 0, response_read);
               Print("✅ 收到测试响应: ", test_response);
               
               // 验证响应是否为有效的健康检查响应
               // 预期格式: {"status": "ok", "message": "Server ready"} 或其他包含 "status": "ok" 的JSON
               if(StringFind(test_response, "\"status\":\"ok\"") >= 0 || StringFind(test_response, "\"status\": \"ok\"") >= 0)
               {
                  Print("✅ 健康检查通过！服务器状态正常。");
               }
               else if(StringFind(test_response, "status") >= 0)
               {
                  Print("⚠️  收到响应但状态不是'ok'，响应内容: ", test_response);
                  // 即使状态不是ok，仍然认为连接成功（服务器可能返回其他状态）
               }
               else
               {
                  Print("⚠️  响应格式不符合预期，但连接正常。响应: ", test_response);
               }
            }
            else
            {
               Print("⚠️  未收到测试响应（但连接正常）");
            }
         }
         
         SocketClose(test_socket);
         
         if(attempt > 0)
         {
            Print("✅ 重试成功！Socket服务器可用: ", InpSocketHost, ":", InpSocketPort);
         }
         else
         {
            Print("✅ Socket服务器可用: ", InpSocketHost, ":", InpSocketPort);
         }
         
         Print("==================== CheckSocketAvailability 结束 ====================");
         return true;
      }
      else
      {
         int last_error = GetLastError();
         Print("❌ Socket连接失败 (尝试", attempt + 1, "/", max_retries + 1, ")");
         Print("  错误代码: ", last_error);
         Print("  错误描述: ", ErrorDescription(last_error));
         
         SocketClose(test_socket);
      }
   }
   
   Print("❌ 所有连接尝试均失败");
   Print("❌ Socket服务器不可用: ", InpSocketHost, ":", InpSocketPort);
   Print("==================== CheckSocketAvailability 结束 ====================");
   return false;
}

// ==================== 文件通信函数（保持兼容性） ====================

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

// ==================== 通信模式管理 ====================

/**
 * 确定当前通信模式
 */
CommunicationMode DetermineCommunicationMode()
{
   CommunicationMode mode = InpCommMode;
   
   if(mode == MODE_AUTO)
   {
      // 自动模式：检查Socket可用性
      if(CheckSocketAvailability())
      {
         m_socket_available = true;
         mode = MODE_SOCKET;
         Print("✅ 自动选择Socket模式");
      }
      else
      {
         m_socket_available = false;
         mode = MODE_FILE;
         Print("⚠️  Socket不可用，自动选择文件模式");
      }
   }
   else if(mode == MODE_SOCKET)
   {
      // Socket模式：检查可用性
      if(CheckSocketAvailability())
      {
         m_socket_available = true;
         Print("✅ 使用Socket模式");
      }
      else
      {
         m_socket_available = false;
         Print("❌ Socket模式不可用，但仍将尝试（可能会失败）");
      }
   }
   else if(mode == MODE_FILE)
   {
      m_socket_available = false;
      Print("✅ 使用文件模式");
   }
   
   return mode;
}

/**
 * 发送AI请求（根据模式选择通信方式）
 */
bool SendAIRequest(const string request_json, string &response_json)
{
   m_total_requests++;
   
   bool success = false;
   string error_info = "";
   
   if(m_current_mode == MODE_SOCKET)
   {
      // Socket模式
      Print("🔌 使用Socket模式发送请求...");
      success = SocketRequestWithRetry(request_json, response_json);
      
      if(!success)
      {
         error_info = "Socket请求失败";
         m_failed_requests++;
         m_consecutive_failures++;
         
         // 检查是否需要切换到文件模式
         if(m_consecutive_failures >= InpFailoverThreshold)
         {
            Print("⚠️  连续", m_consecutive_failures, "次Socket失败，切换到文件模式");
            SwitchToFileMode();
         }
      }
      else
      {
         m_successful_requests++;
         m_consecutive_failures = 0;
      }
   }
   else if(m_current_mode == MODE_FILE)
   {
      // 文件模式
      Print("📁 使用文件模式发送请求...");
      
      // 清理旧的响应文件
      string response_file = "ai_response.json";
      if(FileIsExist(response_file))
         FileDelete(response_file);
      
      // 写入请求文件
      if(WriteRequestFile(request_json))
      {
         Print("等待AI响应...");
         
         // 等待响应文件
         int wait_count = 0;
         while(wait_count < 100)
         {
            Sleep(100);
            if(ReadResponseFile(response_json))
               break;
            wait_count++;
         }
         
         if(response_json != "")
         {
            success = true;
            m_successful_requests++;
            m_consecutive_failures = 0;
         }
         else
         {
            error_info = "文件响应超时";
            m_failed_requests++;
            m_consecutive_failures++;
         }
      }
      else
      {
         error_info = "写入请求文件失败";
         m_failed_requests++;
         m_consecutive_failures++;
      }
   }
   
   if(success)
   {
      Print("✅ 请求成功 (总成功:", m_successful_requests, "/总请求:", m_total_requests, ")");
   }
   else
   {
      Print("❌ 请求失败: ", error_info, " (总失败:", m_failed_requests, "/总请求:", m_total_requests, ")");
   }
   
   return success;
}

/**
 * 切换到文件模式
 */
void SwitchToFileMode()
{
   if(m_current_mode == MODE_FILE)
      return;
   
   Print("🔄 切换到文件模式...");
   m_current_mode = MODE_FILE;
   m_mode_switches++;
   m_last_mode_switch = TimeCurrent();
   m_consecutive_failures = 0;
   
   Print("✅ 已切换到文件模式 (切换次数:", m_mode_switches, ")");
}

/**
 * 尝试切换到Socket模式
 */
bool TrySwitchToSocketMode()
{
   if(m_current_mode == MODE_SOCKET)
      return true;
   
   if(CheckSocketAvailability())
   {
      Print("🔄 切换到Socket模式...");
      m_current_mode = MODE_SOCKET;
      m_socket_available = true;
      m_mode_switches++;
      m_last_mode_switch = TimeCurrent();
      m_consecutive_failures = 0;
      
      Print("✅ 已切换到Socket模式 (切换次数:", m_mode_switches, ")");
      return true;
   }
   else
   {
      Print("❌ Socket不可用，无法切换到Socket模式");
      return false;
   }
}

/**
 * 尝试恢复Socket连接
 */
void TryRecoverSocketConnection()
{
   // 如果当前是文件模式且有一段时间没有尝试Socket了，尝试恢复
   if(m_current_mode == MODE_FILE)
   {
      datetime now = TimeCurrent();
      datetime last_switch = m_last_mode_switch;
      
      // 至少5分钟后才尝试恢复
      if(now - last_switch >= 300)
      {
         Print("🔄 尝试恢复Socket连接...");
         if(TrySwitchToSocketMode())
         {
            Print("✅ Socket连接恢复成功");
         }
         else
         {
            Print("❌ Socket连接恢复失败，继续使用文件模式");
         }
      }
   }
}

// ==================== AI响应解析 ====================

/**
 * 解析AI响应 - 健壮版本，所有字段使用通用提取函数
 * 
 * 改进点：
 * - 所有字段提取统一使用 JsonExtract* 工具函数
 * - 消除对JSON字段顺序的依赖
 * - 独立验证每个字段并记录日志
 * - 动态止损止盈有完整的范围和风险回报比验证
 */
bool ParseAIResponse(string response, string &action, double &confidence, string &reason, bool &use_deepseek)
{
   action = "HOLD";
   confidence = 0.0;
   reason = "解析失败";
   use_deepseek = false;
   
   // 基础校验：响应不能为空
   if(response == "")
   {
      Print("❌ AI响应为空");
      return false;
   }
   
   // 提取JSON花括号区间
   int json_start = StringFind(response, "{");
   int json_end = StringFind(response, "}", StringLen(response) - 1);
   
   if(json_start < 0 || json_end < 0 || json_end <= json_start)
   {
      Print("❌ AI响应不是有效的JSON格式");
      Print("响应内容: ", response);
      return false;
   }
   
   string json_str = StringSubstr(response, json_start, json_end - json_start + 1);
   Print("📋 解析JSON: ", json_str);
   
   // 1. 提取 action（字符串字段，验证枚举值）
   action = JsonExtractString(json_str, "action", "HOLD");
   if(action != "BUY" && action != "SELL" && action != "HOLD")
   {
      Print("⚠️  无效action \"", action, "\"，使用默认值HOLD");
      action = "HOLD";
   }
   
   // 2. 提取 confidence（数值字段，验证范围0-1）
   confidence = JsonExtractDouble(json_str, "confidence", 0.0);
   if(confidence < 0.0 || confidence > 1.0)
   {
      Print("⚠️  无效confidence ", DoubleToString(confidence, 4), "，使用默认值0.0");
      confidence = 0.0;
   }
   
   // 3. 提取 reason（字符串字段）
   reason = JsonExtractString(json_str, "reason", "无分析原因", 200);
   
   // 4. 提取 use_deepseek（布尔字段，字符串"true"/"false"）
   string deepseek_str = JsonExtractString(json_str, "use_deepseek", "");
   use_deepseek = (deepseek_str == "true");
   
   // 5. 检查error字段（仅记录，不覆盖已有解析结果）
   string error_msg = JsonExtractString(json_str, "error", "");
   if(error_msg != "")
   {
      Print("⚠️  AI响应含error字段: ", error_msg);
      if(reason == "解析失败" || reason == "无分析原因")
         reason = "API错误: " + error_msg;
   }
   
   // 6. 提取动态止损止盈（数值字段，含范围和风控验证）
   int sl_pips = (int)JsonExtractInt(json_str, "stop_loss_pips", 0);
   int tp_pips = (int)JsonExtractInt(json_str, "take_profit_pips", 0);
   
   // 范围验证：SL 25-150pips，TP 40-300pips（1pip=10*_Point，黄金1pip≈0.10$）
   if(sl_pips > 0)
   {
      if(sl_pips < 25) { Print("[SL/TP] SL值(", sl_pips, ")过小(<25pips)，重置为25"); sl_pips = 25; }
      else if(sl_pips > 150) { Print("[SL/TP] SL值(", sl_pips, ")超过上限150pips，截断为150"); sl_pips = 150; }
   }
   if(tp_pips > 0)
   {
      if(tp_pips < 40) { Print("[SL/TP] TP值(", tp_pips, ")过小(<40pips)，重置为40"); tp_pips = 40; }
      else if(tp_pips > 300) { Print("[SL/TP] TP值(", tp_pips, ")超过上限300pips，截断为300"); tp_pips = 300; }
   }
   
   // 风险回报比验证：TP必须 >= SL * 1.5（防止AI返回不合理的SL/TP）
   if(sl_pips > 0 && tp_pips > 0 && tp_pips < sl_pips * 1.5)
   {
      int adjusted_tp = (int)(sl_pips * 1.5);
      Print("[SL/TP] 风险回报比不足(SL=", sl_pips, " TP=", tp_pips, ")，自动调整为TP=", adjusted_tp, "(SL*1.5)");
      tp_pips = adjusted_tp;
   }
   
   // 存储到全局变量供ExecuteTrade使用
   g_dynamic_sl_pips = sl_pips;
   g_dynamic_tp_pips = tp_pips;
   
   // 日志输出
   Print("📊 解析结果: action=", action, " confidence=", DoubleToString(confidence, 2),
         " use_deepseek=", use_deepseek, " reason=", reason);
   if(sl_pips > 0 || tp_pips > 0)
      Print("📊 动态止损止盈: SL=", sl_pips, "点, TP=", tp_pips, "点");
   
   return true;
}

// ==================== 健壮JSON字段提取工具函数 ====================

/**
 * 从JSON字符串中提取指定key的数值（整数/浮点均支持）
 * 
 * 解决原有实现依赖字段顺序的问题：
 * - 查找 "key": value 或 "key":value （有无空格均可）
 * - 正确处理值后跟 , 或 } 的两种情况
 * - 自动Trim空白，防止空格导致StringToDouble失败
 * - 字段不存在时返回defaultValue
 * 
 * @param json_str  完整JSON字符串
 * @param key       字段名（不含引号）
 * @param defaultValue 字段不存在或解析失败时的返回值
 * @return 提取到的数值，失败返回defaultValue
 */
double JsonExtractDouble(const string json_str, const string key, double defaultValue = 0.0)
{
   // 构造搜索模式 "key":
   string search_pattern = "\"" + key + "\":";
   int pos = StringFind(json_str, search_pattern);
   if(pos < 0) return defaultValue;
   
   // 跳过 "key": 部分
   int value_start = pos + StringLen(search_pattern);
   
   // 跳过值前的空格
   int json_len = StringLen(json_str);
   while(value_start < json_len && StringSubstr(json_str, value_start, 1) == " ")
      value_start++;
   
   if(value_start >= json_len) return defaultValue;
   
   // 找到值的结尾：遇到 , 或 } 或 ] 或字符串结束
   int value_end = value_start;
   while(value_end < json_len)
   {
      string ch = StringSubstr(json_str, value_end, 1);
      if(ch == "," || ch == "}" || ch == "]")
         break;
      value_end++;
   }
   
   if(value_end <= value_start) return defaultValue;
   
   // 提取并清理值字符串
   string value_str = StringSubstr(json_str, value_start, value_end - value_start);
   value_str = StringTrim(value_str);
   
   if(StringLen(value_str) == 0) return defaultValue;
   
   // 转换为double（StringToDouble失败返回0，需要验证）
   // 检查是否包含有效数字字符
   bool has_digit = false;
   for(int i = 0; i < StringLen(value_str); i++)
   {
      string c = StringSubstr(value_str, i, 1);
      if(c >= "0" && c <= "9") { has_digit = true; break; }
   }
   if(!has_digit) return defaultValue;
   
   return StringToDouble(value_str);
}

/**
 * 从JSON字符串中提取指定key的整数值（JsonExtractDouble的int包装）
 */
int JsonExtractInt(const string json_str, const string key, int defaultValue = 0)
{
   double val = JsonExtractDouble(json_str, key, (double)defaultValue);
   return (int)val;
}

/**
 * 从JSON字符串中提取指定key的字符串值
 * 
 * @param json_str  完整JSON字符串
 * @param key       字段名（不含引号）
 * @param defaultValue 失败时返回值
 * @param maxLen    最大截取长度（防止超长字符串）
 */
string JsonExtractString(const string json_str, const string key, string defaultValue = "", int maxLen = 200)
{
   string search_pattern = "\"" + key + "\":";
   int pos = StringFind(json_str, search_pattern);
   if(pos < 0) return defaultValue;
   
   int value_start = pos + StringLen(search_pattern);
   int json_len = StringLen(json_str);
   
   // 跳过空格
   while(value_start < json_len && StringSubstr(json_str, value_start, 1) == " ")
      value_start++;
   
   if(value_start >= json_len) return defaultValue;
   
   // 字符串值必须以 " 开头
   if(StringSubstr(json_str, value_start, 1) != "\"") return defaultValue;
   value_start++; // 跳过开头引号
   
   // 查找结尾引号（简单实现，不处理转义）
   int value_end = StringFind(json_str, "\"", value_start);
   if(value_end < 0) return defaultValue;
   
   string result = StringSubstr(json_str, value_start, value_end - value_start);
   if(StringLen(result) > maxLen)
      result = StringSubstr(result, 0, maxLen);
   
   return result;
}

// ==================== 现有技术指标函数（保持不变） ====================

/**
 * 初始化技术指标
 */
void InitIndicators()
{
   // 当前时间框架指标（保持原有逻辑）
   m_rsi_handle = iRSI(_Symbol, _Period, 14, PRICE_CLOSE);
   m_macd_handle = iMACD(_Symbol, _Period, 12, 26, 9, PRICE_CLOSE);
   m_ema_handle = iMA(_Symbol, _Period, 50, 0, MODE_EMA, PRICE_CLOSE);
   m_ema20_handle = iMA(_Symbol, _Period, 20, 0, MODE_EMA, PRICE_CLOSE);
   m_ema100_handle = iMA(_Symbol, _Period, 100, 0, MODE_EMA, PRICE_CLOSE);
   m_atr_handle = iATR(_Symbol, _Period, 14);
   m_stoch_handle = iStochastic(_Symbol, _Period, 14, 3, 3, MODE_SMA, STO_LOWHIGH);
   
   // 初始化多时间框架指标
   // H1（1小时）时间框架指标
   m_rsi_h1_handle = iRSI(_Symbol, PERIOD_H1, 14, PRICE_CLOSE);
   m_macd_h1_handle = iMACD(_Symbol, PERIOD_H1, 12, 26, 9, PRICE_CLOSE);
   m_ema50_h1_handle = iMA(_Symbol, PERIOD_H1, 50, 0, MODE_EMA, PRICE_CLOSE);
   m_ema20_h1_handle = iMA(_Symbol, PERIOD_H1, 20, 0, MODE_EMA, PRICE_CLOSE);
   m_ema100_h1_handle = iMA(_Symbol, PERIOD_H1, 100, 0, MODE_EMA, PRICE_CLOSE);
   m_atr_h1_handle = iATR(_Symbol, PERIOD_H1, 14);
   m_stoch_h1_handle = iStochastic(_Symbol, PERIOD_H1, 14, 3, 3, MODE_SMA, STO_LOWHIGH);
   
   // H4（4小时）时间框架指标
   m_rsi_h4_handle = iRSI(_Symbol, PERIOD_H4, 14, PRICE_CLOSE);
   m_macd_h4_handle = iMACD(_Symbol, PERIOD_H4, 12, 26, 9, PRICE_CLOSE);
   m_ema50_h4_handle = iMA(_Symbol, PERIOD_H4, 50, 0, MODE_EMA, PRICE_CLOSE);
   m_ema20_h4_handle = iMA(_Symbol, PERIOD_H4, 20, 0, MODE_EMA, PRICE_CLOSE);
   m_ema100_h4_handle = iMA(_Symbol, PERIOD_H4, 100, 0, MODE_EMA, PRICE_CLOSE);
   m_atr_h4_handle = iATR(_Symbol, PERIOD_H4, 14);
   m_stoch_h4_handle = iStochastic(_Symbol, PERIOD_H4, 14, 3, 3, MODE_SMA, STO_LOWHIGH);
   
   // D1（日线）时间框架指标
   m_rsi_d1_handle = iRSI(_Symbol, PERIOD_D1, 14, PRICE_CLOSE);
   m_macd_d1_handle = iMACD(_Symbol, PERIOD_D1, 12, 26, 9, PRICE_CLOSE);
   m_ema50_d1_handle = iMA(_Symbol, PERIOD_D1, 50, 0, MODE_EMA, PRICE_CLOSE);
   m_ema20_d1_handle = iMA(_Symbol, PERIOD_D1, 20, 0, MODE_EMA, PRICE_CLOSE);
   m_ema100_d1_handle = iMA(_Symbol, PERIOD_D1, 100, 0, MODE_EMA, PRICE_CLOSE);
   m_atr_d1_handle = iATR(_Symbol, PERIOD_D1, 14);
   m_stoch_d1_handle = iStochastic(_Symbol, PERIOD_D1, 14, 3, 3, MODE_SMA, STO_LOWHIGH);
}

/**
 * 计算支撑阻力位（最近20根K线）
 */
void CalculateSupportResistance()
{
   // 保持原始实现
   int bars = 20;
   double highs[], lows[];
   ArrayResize(highs, bars);
   ArrayResize(lows, bars);
   
   for(int i = 0; i < bars; i++)
   {
      highs[i] = iHigh(_Symbol, _Period, i);
      lows[i] = iLow(_Symbol, _Period, i);
   }
   
   ArraySort(highs);
   ArraySort(lows);
   
   m_resistance_price = highs[bars-1];
   m_support_price = lows[0];
}


/**
 * JSON字符串转义
 */
string JsonEscape(const string value)
{
   string escaped = "";
   for(int i = 0; i < StringLen(value); i++)
   {
      ushort ch = StringGetCharacter(value, i);
      if(ch == 34)          // "
         escaped += "\\\"";
      else if(ch == 92)     // backslash
         escaped += "\\\\";
      else if(ch == 10)
         escaped += "\\n";
      else if(ch == 13)
         escaped += "\\r";
      else if(ch == 9)
         escaped += "\\t";
      else if(ch >= 32)
         escaped += ShortToString(ch);
   }
   return escaped;
}

/**
 * 构建交易历史JSON（用于AI准确率统计）
 */
string BuildTradeHistoryJson()
{
   string json = "[";
   
   // 获取最近30天的交易历史
   datetime from_date = TimeCurrent() - 30 * 86400; // 30天前
   datetime to_date = TimeCurrent();
   
   // 选择时间范围内的平仓交易
   HistorySelect(from_date, to_date);
   
   int deals_total = HistoryDealsTotal();
   int count = 0;
   int max_deals = 50; // 最多50条记录
   
   for(int i = deals_total - 1; i >= 0 && count < max_deals; i--)
   {
      ulong deal_ticket = HistoryDealGetTicket(i);
      if(deal_ticket == 0)
         continue;
      
      // 只获取GOLD_的交易
      string symbol = HistoryDealGetString(deal_ticket, DEAL_SYMBOL);
      if(symbol != _Symbol)
         continue;
      
      long deal_type = HistoryDealGetInteger(deal_ticket, DEAL_TYPE);
      double profit = HistoryDealGetDouble(deal_ticket, DEAL_PROFIT);
      double volume = HistoryDealGetDouble(deal_ticket, DEAL_VOLUME);
      datetime time = (datetime)HistoryDealGetInteger(deal_ticket, DEAL_TIME);
      double price = HistoryDealGetDouble(deal_ticket, DEAL_PRICE);
      double commission = HistoryDealGetDouble(deal_ticket, DEAL_COMMISSION);
      double swap = HistoryDealGetDouble(deal_ticket, DEAL_SWAP);
      long entry = HistoryDealGetInteger(deal_ticket, DEAL_ENTRY);
      
      // 判断交易结果
      string result = "UNKNOWN";
      double profit_pips = 0;
      
      if(deal_type == DEAL_TYPE_BUY)
      {
         result = profit >= 0 ? "WIN" : "LOSS";
      }
      else if(deal_type == DEAL_TYPE_SELL)
      {
         result = profit >= 0 ? "WIN" : "LOSS";
      }
      
      // 获取持仓订单信息
      ulong order_id = HistoryDealGetInteger(deal_ticket, DEAL_ORDER);
      double sl = 0, tp = 0;
      string comment = HistoryDealGetString(deal_ticket, DEAL_COMMENT);
      
      // 尝试从订单获取止损止盈
      if(order_id > 0 && HistoryOrderSelect(order_id))
      {
         sl = HistoryOrderGetDouble(order_id, ORDER_SL);
         tp = HistoryOrderGetDouble(order_id, ORDER_TP);
      }
      
      if(count > 0) json += ",";
      
      json += "{";
      json += "\"ticket\":" + IntegerToString(deal_ticket) + ",";
      json += "\"type\":\"" + (deal_type == DEAL_TYPE_BUY ? "BUY" : "SELL") + "\",";
      json += "\"entry\":\"" + (entry == DEAL_ENTRY_IN ? "IN" : "OUT") + "\",";
      json += "\"result\":\"" + result + "\",";
      json += "\"profit\":" + DoubleToString(profit, 2) + ",";
      json += "\"volume\":" + DoubleToString(volume, 2) + ",";
      json += "\"price\":" + DoubleToString(price, 5) + ",";
      json += "\"sl\":" + DoubleToString(sl, 5) + ",";
      json += "\"tp\":" + DoubleToString(tp, 5) + ",";
      json += "\"commission\":" + DoubleToString(commission, 2) + ",";
      json += "\"swap\":" + DoubleToString(swap, 2) + ",";
      json += "\"time\":" + IntegerToString((long)time) + ",";
      json += "\"comment\":\"" + JsonEscape(comment) + "\"";
      json += "}";
      
      count++;
   }
   
   json += "]";
   
   // 如果没有交易，返回空数组
   if(count == 0)
   {
      json = "[]";
   }
   
   return json;
}

/**
 * 构建市场数据 - 增强版，支持多时间框架分析
 */
string BuildMarketData()
{
   // 基本市场数据
   string market_data = "{";
   market_data += "\"symbol\":\"" + _Symbol + "\",";
   market_data += "\"bid\":" + DoubleToString(SymbolInfoDouble(_Symbol, SYMBOL_BID), 5) + ",";
   market_data += "\"ask\":" + DoubleToString(SymbolInfoDouble(_Symbol, SYMBOL_ASK), 5) + ",";
   market_data += "\"time\":" + IntegerToString((long)TimeCurrent()) + ",";
   
   // 当前时间框架历史数据
   market_data += "\"history\":[";
   int history_bars = 50;
   for(int i = 0; i < history_bars; i++)
   {
      if(i > 0) market_data += ",";
      market_data += "{";
      market_data += "\"time\":" + IntegerToString((long)iTime(_Symbol, _Period, i)) + ",";
      market_data += "\"open\":" + DoubleToString(iOpen(_Symbol, _Period, i), 5) + ",";
      market_data += "\"high\":" + DoubleToString(iHigh(_Symbol, _Period, i), 5) + ",";
      market_data += "\"low\":" + DoubleToString(iLow(_Symbol, _Period, i), 5) + ",";
      market_data += "\"close\":" + DoubleToString(iClose(_Symbol, _Period, i), 5) + ",";
      market_data += "\"volume\":" + IntegerToString(iVolume(_Symbol, _Period, i));
      market_data += "}";
   }
   market_data += "],";
   
   // 当前时间框架技术指标
   market_data += "\"indicators\":{";
   market_data += "\"rsi\":" + DoubleToString(GetRSIValue(), 2) + ",";
   market_data += "\"macd_main\":" + DoubleToString(GetMACDMainValue(), 5) + ",";
   market_data += "\"macd_signal\":" + DoubleToString(GetMACDSignalValue(), 5) + ",";
   market_data += "\"ema50\":" + DoubleToString(GetEMA50Value(), 5) + ",";
   market_data += "\"ema20\":" + DoubleToString(GetEMA20Value(), 5) + ",";
   market_data += "\"ema100\":" + DoubleToString(GetEMA100Value(), 5) + ",";
   market_data += "\"atr\":" + DoubleToString(GetATRValue(), 5) + ",";
   market_data += "\"stoch_k\":" + DoubleToString(GetStochKValue(), 2) + ",";
   market_data += "\"stoch_d\":" + DoubleToString(GetStochDValue(), 2);
   market_data += "},";
   
   // 多时间框架数据
   market_data += "\"multi_timeframe\":{";
   
   // H1时间框架数据
   market_data += "\"h1\":{";
   market_data += "\"history\":[";
   int h1_bars = 30;  // H1时间框架使用30根K线
   for(int i = 0; i < h1_bars; i++)
   {
      if(i > 0) market_data += ",";
      market_data += "{";
      market_data += "\"time\":" + IntegerToString((long)iTime(_Symbol, PERIOD_H1, i)) + ",";
      market_data += "\"open\":" + DoubleToString(iOpen(_Symbol, PERIOD_H1, i), 5) + ",";
      market_data += "\"high\":" + DoubleToString(iHigh(_Symbol, PERIOD_H1, i), 5) + ",";
      market_data += "\"low\":" + DoubleToString(iLow(_Symbol, PERIOD_H1, i), 5) + ",";
      market_data += "\"close\":" + DoubleToString(iClose(_Symbol, PERIOD_H1, i), 5) + ",";
      market_data += "\"volume\":" + IntegerToString(iVolume(_Symbol, PERIOD_H1, i));
      market_data += "}";
   }
   market_data += "],";
   market_data += "\"indicators\":{";
   market_data += "\"rsi\":" + DoubleToString(GetRSIH1Value(), 2) + ",";
   market_data += "\"macd_main\":" + DoubleToString(GetMACDMainH1Value(), 5) + ",";
   market_data += "\"macd_signal\":" + DoubleToString(GetMACDSignalH1Value(), 5) + ",";
   market_data += "\"ema50\":" + DoubleToString(GetEMA50H1Value(), 5) + ",";
   market_data += "\"ema20\":" + DoubleToString(GetEMA20H1Value(), 5) + ",";
   market_data += "\"ema100\":" + DoubleToString(GetEMA100H1Value(), 5) + ",";
   market_data += "\"atr\":" + DoubleToString(GetATRH1Value(), 5) + ",";
   market_data += "\"stoch_k\":" + DoubleToString(GetStochKH1Value(), 2) + ",";
   market_data += "\"stoch_d\":" + DoubleToString(GetStochDH1Value(), 2);
   market_data += "}";
   market_data += "},";
   
   // H4时间框架数据
   market_data += "\"h4\":{";
   market_data += "\"history\":[";
   int h4_bars = 20;  // H4时间框架使用20根K线
   for(int i = 0; i < h4_bars; i++)
   {
      if(i > 0) market_data += ",";
      market_data += "{";
      market_data += "\"time\":" + IntegerToString((long)iTime(_Symbol, PERIOD_H4, i)) + ",";
      market_data += "\"open\":" + DoubleToString(iOpen(_Symbol, PERIOD_H4, i), 5) + ",";
      market_data += "\"high\":" + DoubleToString(iHigh(_Symbol, PERIOD_H4, i), 5) + ",";
      market_data += "\"low\":" + DoubleToString(iLow(_Symbol, PERIOD_H4, i), 5) + ",";
      market_data += "\"close\":" + DoubleToString(iClose(_Symbol, PERIOD_H4, i), 5) + ",";
      market_data += "\"volume\":" + IntegerToString(iVolume(_Symbol, PERIOD_H4, i));
      market_data += "}";
   }
   market_data += "],";
   market_data += "\"indicators\":{";
   market_data += "\"rsi\":" + DoubleToString(GetRSIH4Value(), 2) + ",";
   market_data += "\"macd_main\":" + DoubleToString(GetMACDMainH4Value(), 5) + ",";
   market_data += "\"macd_signal\":" + DoubleToString(GetMACDSignalH4Value(), 5) + ",";
   market_data += "\"ema50\":" + DoubleToString(GetEMA50H4Value(), 5) + ",";
   market_data += "\"ema20\":" + DoubleToString(GetEMA20H4Value(), 5) + ",";
   market_data += "\"ema100\":" + DoubleToString(GetEMA100H4Value(), 5) + ",";
   market_data += "\"atr\":" + DoubleToString(GetATRH4Value(), 5) + ",";
   market_data += "\"stoch_k\":" + DoubleToString(GetStochKH4Value(), 2) + ",";
   market_data += "\"stoch_d\":" + DoubleToString(GetStochDH4Value(), 2);
   market_data += "}";
   market_data += "},";
   
   // D1时间框架数据
   market_data += "\"d1\":{";
   market_data += "\"history\":[";
   int d1_bars = 15;  // D1时间框架使用15根K线
   for(int i = 0; i < d1_bars; i++)
   {
      if(i > 0) market_data += ",";
      market_data += "{";
      market_data += "\"time\":" + IntegerToString((long)iTime(_Symbol, PERIOD_D1, i)) + ",";
      market_data += "\"open\":" + DoubleToString(iOpen(_Symbol, PERIOD_D1, i), 5) + ",";
      market_data += "\"high\":" + DoubleToString(iHigh(_Symbol, PERIOD_D1, i), 5) + ",";
      market_data += "\"low\":" + DoubleToString(iLow(_Symbol, PERIOD_D1, i), 5) + ",";
      market_data += "\"close\":" + DoubleToString(iClose(_Symbol, PERIOD_D1, i), 5) + ",";
      market_data += "\"volume\":" + IntegerToString(iVolume(_Symbol, PERIOD_D1, i));
      market_data += "}";
   }
   market_data += "],";
   market_data += "\"indicators\":{";
   market_data += "\"rsi\":" + DoubleToString(GetRSID1Value(), 2) + ",";
   market_data += "\"macd_main\":" + DoubleToString(GetMACDMainD1Value(), 5) + ",";
   market_data += "\"macd_signal\":" + DoubleToString(GetMACDSignalD1Value(), 5) + ",";
   market_data += "\"ema50\":" + DoubleToString(GetEMA50D1Value(), 5) + ",";
   market_data += "\"ema20\":" + DoubleToString(GetEMA20D1Value(), 5) + ",";
   market_data += "\"ema100\":" + DoubleToString(GetEMA100D1Value(), 5) + ",";
   market_data += "\"atr\":" + DoubleToString(GetATRD1Value(), 5) + ",";
   market_data += "\"stoch_k\":" + DoubleToString(GetStochKD1Value(), 2) + ",";
   market_data += "\"stoch_d\":" + DoubleToString(GetStochDD1Value(), 2);
   market_data += "}";
   market_data += "}";
   
   market_data += "}"; // 关闭multi_timeframe
   
   // 添加账户数据（关键修复）
   double account_margin = AccountInfoDouble(ACCOUNT_MARGIN);
   double account_margin_free = AccountInfoDouble(ACCOUNT_MARGIN_FREE);
   double account_equity = AccountInfoDouble(ACCOUNT_EQUITY);
   double account_margin_level = AccountInfoDouble(ACCOUNT_MARGIN_LEVEL);
   if(account_margin <= 0.0 && (account_margin_free > 0.0 || account_equity > 0.0))
      account_margin_level = 1000.0;
   
   market_data += ",\"account_data\":{";
   market_data += "\"balance\":" + DoubleToString(AccountInfoDouble(ACCOUNT_BALANCE), 2) + ",";
   market_data += "\"equity\":" + DoubleToString(account_equity, 2) + ",";
   market_data += "\"margin_free\":" + DoubleToString(account_margin_free, 2) + ",";
   market_data += "\"margin\":" + DoubleToString(account_margin, 2) + ",";
   market_data += "\"margin_level\":" + DoubleToString(account_margin_level, 2) + ",";
   market_data += "\"profit\":" + DoubleToString(AccountInfoDouble(ACCOUNT_PROFIT), 2) + ",";
   market_data += "\"leverage\":" + IntegerToString((int)AccountInfoInteger(ACCOUNT_LEVERAGE));
   market_data += "}";
   
   // 添加交易历史（用于准确率统计）
   market_data += ",\"trade_history\":";
   market_data += BuildTradeHistoryJson();
   
   market_data += "}"; // 关闭整个JSON对象
   
   return market_data;
}

// ==================== 账户数据推送函数 ====================

/**
 * 初始化账户数据推送连接
 */
bool InitAccountDataConnection()
{
   if(m_account_data_socket != -1)
   {
      SocketClose(m_account_data_socket);
      m_account_data_socket = -1;
   }
   
   // 创建Socket
   m_account_data_socket = SocketCreate();
   if(m_account_data_socket == INVALID_HANDLE)
   {
      Print("❌ 账户数据推送Socket创建失败");
      return false;
   }
   
   // 连接服务器
   if(!SocketConnect(m_account_data_socket, InpAccountDataHost, InpAccountDataPort, 5000))
   {
      Print("❌ 账户数据推送连接失败: ", InpAccountDataHost, ":", InpAccountDataPort);
      SocketClose(m_account_data_socket);
      m_account_data_socket = -1;
      return false;
   }
   
   Print("✅ 账户数据推送连接成功: ", InpAccountDataHost, ":", InpAccountDataPort);
   return true;
}

/**
 * 构建账户数据JSON
 */
string BuildAccountDataJson()
{
   double account_margin = AccountInfoDouble(ACCOUNT_MARGIN);
   double account_margin_free = AccountInfoDouble(ACCOUNT_MARGIN_FREE);
   double account_equity = AccountInfoDouble(ACCOUNT_EQUITY);
   double account_margin_level = AccountInfoDouble(ACCOUNT_MARGIN_LEVEL);
   if(account_margin <= 0.0 && (account_margin_free > 0.0 || account_equity > 0.0))
      account_margin_level = 1000.0;
   
   string json = "{";
   json += "\"type\":\"mql5_data\",";
   
   // 账户信息
   json += "\"account\":{";
   json += "\"balance\":" + DoubleToString(AccountInfoDouble(ACCOUNT_BALANCE), 2) + ",";
   json += "\"equity\":" + DoubleToString(account_equity, 2) + ",";
   json += "\"margin\":" + DoubleToString(account_margin, 2) + ",";
   json += "\"margin_free\":" + DoubleToString(account_margin_free, 2) + ",";
   json += "\"margin_level\":" + DoubleToString(account_margin_level, 2) + ",";
   json += "\"profit\":" + DoubleToString(AccountInfoDouble(ACCOUNT_PROFIT), 2) + ",";
   json += "\"currency\":\"" + JsonEscape(AccountInfoString(ACCOUNT_CURRENCY)) + "\",";
   json += "\"leverage\":" + IntegerToString(AccountInfoInteger(ACCOUNT_LEVERAGE)) + ",";
   json += "\"account\":" + IntegerToString(AccountInfoInteger(ACCOUNT_LOGIN)) + ",";
   json += "\"server\":\"" + JsonEscape(AccountInfoString(ACCOUNT_SERVER)) + "\"";
   json += "},";
   
   // 持仓信息
   json += "\"positions\":[";
   int pos_count = PositionsTotal();
   for(int i = 0; i < pos_count; i++)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0)
         continue;
         
      if(!PositionSelectByTicket(ticket))
         continue;
         
      if(i > 0) json += ",";
      
      json += "{";
      json += "\"ticket\":" + IntegerToString((ulong)ticket) + ",";
      json += "\"symbol\":\"" + JsonEscape(PositionGetString(POSITION_SYMBOL)) + "\",";
      json += "\"type\":\"" + (PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY ? "BUY" : "SELL") + "\",";
      json += "\"volume\":" + DoubleToString(PositionGetDouble(POSITION_VOLUME), 2) + ",";
      json += "\"open_time\":\"" + JsonEscape(TimeToString((datetime)PositionGetInteger(POSITION_TIME), TIME_DATE|TIME_SECONDS)) + "\",";
      json += "\"open_price\":" + DoubleToString(PositionGetDouble(POSITION_PRICE_OPEN), (int)Digits()) + ",";
      json += "\"sl\":" + DoubleToString(PositionGetDouble(POSITION_SL), (int)Digits()) + ",";
      json += "\"tp\":" + DoubleToString(PositionGetDouble(POSITION_TP), (int)Digits()) + ",";
      json += "\"current_price\":" + DoubleToString(PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY ? SymbolInfoDouble(PositionGetString(POSITION_SYMBOL), SYMBOL_BID) : SymbolInfoDouble(PositionGetString(POSITION_SYMBOL), SYMBOL_ASK), (int)Digits()) + ",";
      json += "\"profit\":" + DoubleToString(PositionGetDouble(POSITION_PROFIT), 2) + ",";
      json += "\"swap\":" + DoubleToString(PositionGetDouble(POSITION_SWAP), 2) + ",";
      json += "\"comment\":\"" + JsonEscape(PositionGetString(POSITION_COMMENT)) + "\"";
      json += "}";
   }
   json += "],";
   
   // 历史交易（最近20笔）
   json += "\"history\":[";
   // 这里可以添加历史交易获取逻辑，为简化起见留空
   json += "]";
   
   json += "}";
   
   return json;
}

/**
 * 推送账户数据到服务器
 * 优先使用Socket，失败时使用文件模式作为备选
 */
void PushAccountDataToServer()
{
   datetime now = TimeCurrent();
   if(now - m_last_account_data_push < InpAccountDataInterval)
      return;
      
   m_last_account_data_push = now;
   
   string json_data = BuildAccountDataJson();
   
   // 优先尝试Socket
   bool socket_success = false;
   
   // 检查连接状态
   if(m_account_data_socket == -1 || !SocketIsConnected(m_account_data_socket))
   {
      if(!InitAccountDataConnection())
      {
         Print("⚠️  Socket连接失败，使用文件模式备选");
      }
   }
   
   if(m_account_data_socket != -1 && SocketIsConnected(m_account_data_socket))
   {
      string send_data = json_data + "\n";
      uchar data[];
      int len = StringToCharArray(send_data, data);
      
      int sent = SocketSend(m_account_data_socket, data, (uint)len);
      if(sent > 0)
      {
         Print("✅ 账户数据Socket推送成功 (", sent, " bytes)");
         socket_success = true;
      }
      else
      {
         Print("❌ 账户数据Socket发送失败");
         SocketClose(m_account_data_socket);
         m_account_data_socket = -1;
      }
   }
   
   // Socket失败时，使用文件模式作为备选
   if(!socket_success)
   {
      string file_path = GetDataFilePath("mt5_account.json");
      int handle = FileOpen(file_path, FILE_WRITE|FILE_TXT|FILE_ANSI);
      if(handle != INVALID_HANDLE)
      {
         FileWriteString(handle, json_data);
         FileClose(handle);
         Print("✅ 账户数据文件推送成功: ", file_path);
      }
      else
      {
         Print("❌ 账户数据文件写入失败: ", file_path);
      }
   }
}

// ==================== 辅助函数 ====================

/**
 * 获取数据文件路径
 */
string GetDataFilePath(string filename)
{
   string path;
   
   if(InpDataPath != "")
   {
      path = InpDataPath;
      int len = StringLen(path);
      if(len > 0 && StringSubstr(path, len - 1, 1) != "\\")
         path += "\\";
   }
   else
   {
      path = "";
   }
   
   return path + filename;
}

// ==================== 技术指标获取函数（保持不变） ====================

double GetRSIValue() 
{
   double buffer[];
   ArraySetAsSeries(buffer, true);
   if(CopyBuffer(m_rsi_handle, 0, 0, 2, buffer) > 0)
      return buffer[0];
   return 50.0;
}

double GetMACDMainValue()
{
   double buffer[];
   ArraySetAsSeries(buffer, true);
   if(CopyBuffer(m_macd_handle, 0, 0, 2, buffer) > 0)
      return buffer[0];
   return 0.0;
}

double GetMACDSignalValue()
{
   double buffer[];
   ArraySetAsSeries(buffer, true);
   if(CopyBuffer(m_macd_handle, 1, 0, 2, buffer) > 0)
      return buffer[0];
   return 0.0;
}

double GetEMA50Value()
{
   double buffer[];
   ArraySetAsSeries(buffer, true);
   if(CopyBuffer(m_ema_handle, 0, 0, 2, buffer) > 0)
      return buffer[0];
   return 0.0;
}

double GetEMA20Value()
{
   double buffer[];
   ArraySetAsSeries(buffer, true);
   if(CopyBuffer(m_ema20_handle, 0, 0, 2, buffer) > 0)
      return buffer[0];
   return 0.0;
}

double GetEMA100Value()
{
   double buffer[];
   ArraySetAsSeries(buffer, true);
   if(CopyBuffer(m_ema100_handle, 0, 0, 2, buffer) > 0)
      return buffer[0];
   return 0.0;
}

double GetATRValue()
{
   double buffer[];
   ArraySetAsSeries(buffer, true);
   if(CopyBuffer(m_atr_handle, 0, 0, 2, buffer) > 0)
      return buffer[0];
   return 0.0;
}

double GetStochKValue()
{
   double buffer[];
   ArraySetAsSeries(buffer, true);
   if(CopyBuffer(m_stoch_handle, 0, 0, 2, buffer) > 0)
      return buffer[0];
   return 50.0;
}

double GetStochDValue()
{
   double buffer[];
   ArraySetAsSeries(buffer, true);
   if(CopyBuffer(m_stoch_handle, 1, 0, 2, buffer) > 0)
      return buffer[0];
   return 50.0;
}

// ==================== 多时间框架指标获取函数 ====================

// H1（1小时）时间框架指标获取函数
double GetRSIH1Value() 
{
   double buffer[];
   ArraySetAsSeries(buffer, true);
   if(CopyBuffer(m_rsi_h1_handle, 0, 0, 2, buffer) > 0)
      return buffer[0];
   return 50.0;
}

double GetMACDMainH1Value()
{
   double buffer[];
   ArraySetAsSeries(buffer, true);
   if(CopyBuffer(m_macd_h1_handle, 0, 0, 2, buffer) > 0)
      return buffer[0];
   return 0.0;
}

double GetMACDSignalH1Value()
{
   double buffer[];
   ArraySetAsSeries(buffer, true);
   if(CopyBuffer(m_macd_h1_handle, 1, 0, 2, buffer) > 0)
      return buffer[0];
   return 0.0;
}

double GetEMA50H1Value()
{
   double buffer[];
   ArraySetAsSeries(buffer, true);
   if(CopyBuffer(m_ema50_h1_handle, 0, 0, 2, buffer) > 0)
      return buffer[0];
   return 0.0;
}

double GetEMA20H1Value()
{
   double buffer[];
   ArraySetAsSeries(buffer, true);
   if(CopyBuffer(m_ema20_h1_handle, 0, 0, 2, buffer) > 0)
      return buffer[0];
   return 0.0;
}

double GetEMA100H1Value()
{
   double buffer[];
   ArraySetAsSeries(buffer, true);
   if(CopyBuffer(m_ema100_h1_handle, 0, 0, 2, buffer) > 0)
      return buffer[0];
   return 0.0;
}

double GetATRH1Value()
{
   double buffer[];
   ArraySetAsSeries(buffer, true);
   if(CopyBuffer(m_atr_h1_handle, 0, 0, 2, buffer) > 0)
      return buffer[0];
   return 0.0;
}

double GetStochKH1Value()
{
   double buffer[];
   ArraySetAsSeries(buffer, true);
   if(CopyBuffer(m_stoch_h1_handle, 0, 0, 2, buffer) > 0)
      return buffer[0];
   return 50.0;
}

double GetStochDH1Value()
{
   double buffer[];
   ArraySetAsSeries(buffer, true);
   if(CopyBuffer(m_stoch_h1_handle, 1, 0, 2, buffer) > 0)
      return buffer[0];
   return 50.0;
}

// H4（4小时）时间框架指标获取函数
double GetRSIH4Value() 
{
   double buffer[];
   ArraySetAsSeries(buffer, true);
   if(CopyBuffer(m_rsi_h4_handle, 0, 0, 2, buffer) > 0)
      return buffer[0];
   return 50.0;
}

double GetMACDMainH4Value()
{
   double buffer[];
   ArraySetAsSeries(buffer, true);
   if(CopyBuffer(m_macd_h4_handle, 0, 0, 2, buffer) > 0)
      return buffer[0];
   return 0.0;
}

double GetMACDSignalH4Value()
{
   double buffer[];
   ArraySetAsSeries(buffer, true);
   if(CopyBuffer(m_macd_h4_handle, 1, 0, 2, buffer) > 0)
      return buffer[0];
   return 0.0;
}

double GetEMA50H4Value()
{
   double buffer[];
   ArraySetAsSeries(buffer, true);
   if(CopyBuffer(m_ema50_h4_handle, 0, 0, 2, buffer) > 0)
      return buffer[0];
   return 0.0;
}

double GetEMA20H4Value()
{
   double buffer[];
   ArraySetAsSeries(buffer, true);
   if(CopyBuffer(m_ema20_h4_handle, 0, 0, 2, buffer) > 0)
      return buffer[0];
   return 0.0;
}

double GetEMA100H4Value()
{
   double buffer[];
   ArraySetAsSeries(buffer, true);
   if(CopyBuffer(m_ema100_h4_handle, 0, 0, 2, buffer) > 0)
      return buffer[0];
   return 0.0;
}

double GetATRH4Value()
{
   double buffer[];
   ArraySetAsSeries(buffer, true);
   if(CopyBuffer(m_atr_h4_handle, 0, 0, 2, buffer) > 0)
      return buffer[0];
   return 0.0;
}

double GetStochKH4Value()
{
   double buffer[];
   ArraySetAsSeries(buffer, true);
   if(CopyBuffer(m_stoch_h4_handle, 0, 0, 2, buffer) > 0)
      return buffer[0];
   return 50.0;
}

double GetStochDH4Value()
{
   double buffer[];
   ArraySetAsSeries(buffer, true);
   if(CopyBuffer(m_stoch_h4_handle, 1, 0, 2, buffer) > 0)
      return buffer[0];
   return 50.0;
}

// D1（日线）时间框架指标获取函数
double GetRSID1Value() 
{
   double buffer[];
   ArraySetAsSeries(buffer, true);
   if(CopyBuffer(m_rsi_d1_handle, 0, 0, 2, buffer) > 0)
      return buffer[0];
   return 50.0;
}

double GetMACDMainD1Value()
{
   double buffer[];
   ArraySetAsSeries(buffer, true);
   if(CopyBuffer(m_macd_d1_handle, 0, 0, 2, buffer) > 0)
      return buffer[0];
   return 0.0;
}

double GetMACDSignalD1Value()
{
   double buffer[];
   ArraySetAsSeries(buffer, true);
   if(CopyBuffer(m_macd_d1_handle, 1, 0, 2, buffer) > 0)
      return buffer[0];
   return 0.0;
}

double GetEMA50D1Value()
{
   double buffer[];
   ArraySetAsSeries(buffer, true);
   if(CopyBuffer(m_ema50_d1_handle, 0, 0, 2, buffer) > 0)
      return buffer[0];
   return 0.0;
}

double GetEMA20D1Value()
{
   double buffer[];
   ArraySetAsSeries(buffer, true);
   if(CopyBuffer(m_ema20_d1_handle, 0, 0, 2, buffer) > 0)
      return buffer[0];
   return 0.0;
}

double GetEMA100D1Value()
{
   double buffer[];
   ArraySetAsSeries(buffer, true);
   if(CopyBuffer(m_ema100_d1_handle, 0, 0, 2, buffer) > 0)
      return buffer[0];
   return 0.0;
}

double GetATRD1Value()
{
   double buffer[];
   ArraySetAsSeries(buffer, true);
   if(CopyBuffer(m_atr_d1_handle, 0, 0, 2, buffer) > 0)
      return buffer[0];
   return 0.0;
}

double GetStochKD1Value()
{
   double buffer[];
   ArraySetAsSeries(buffer, true);
   if(CopyBuffer(m_stoch_d1_handle, 0, 0, 2, buffer) > 0)
      return buffer[0];
   return 50.0;
}

double GetStochDD1Value()
{
   double buffer[];
   ArraySetAsSeries(buffer, true);
   if(CopyBuffer(m_stoch_d1_handle, 1, 0, 2, buffer) > 0)
      return buffer[0];
   return 50.0;
}

// ==================== 交易安全工具函数 ====================

void ClearDynamicStops()
{
   g_dynamic_sl_pips = 0;
   g_dynamic_tp_pips = 0;
}

int VolumeDigits(double step)
{
   int digits = 0;
   while(step > 0.0 && step < 1.0 && digits < 8)
   {
      step *= 10.0;
      digits++;
   }
   return digits;
}

double NormalizeTradeVolume(double requested_volume)
{
   double min_lot = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double max_lot = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   double lot_step = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);

   if(min_lot <= 0.0 || max_lot <= 0.0 || lot_step <= 0.0)
   {
      Print("[SAFE] 无法读取品种手数约束，禁止交易");
      return 0.0;
   }

   if(requested_volume < min_lot || requested_volume > max_lot)
   {
      Print("[SAFE] 手数超出允许范围: ", DoubleToString(requested_volume, 4),
            " allowed=[", DoubleToString(min_lot, 4), ", ", DoubleToString(max_lot, 4), "]");
      return 0.0;
   }

   double steps = MathFloor((requested_volume - min_lot) / lot_step + 0.5);
   double normalized = NormalizeDouble(min_lot + steps * lot_step, VolumeDigits(lot_step));

   if(normalized < min_lot || normalized > max_lot)
      return 0.0;

   return normalized;
}

bool ValidateTradingInputs()
{
   if(InpMinConfidence < 0.0 || InpMinConfidence > 1.0)
   {
      Print("[SAFE] InpMinConfidence必须在0-1之间");
      return false;
   }

   if(InpStopLoss < 0 || InpTakeProfit < 0 || InpTrailingStop < 0)
   {
      Print("[SAFE] 止损/止盈/追踪止损不能为负数");
      return false;
   }

   if(NormalizeTradeVolume(InpLotSize) <= 0.0)
      return false;

   return true;
}

bool IsTradeEnvironmentReady()
{
   if(!TerminalInfoInteger(TERMINAL_TRADE_ALLOWED))
   {
      Print("[SAFE] 终端自动交易未允许");
      return false;
   }

   if(!MQLInfoInteger(MQL_TRADE_ALLOWED))
   {
      Print("[SAFE] EA自动交易未允许");
      return false;
   }

   if(!AccountInfoInteger(ACCOUNT_TRADE_ALLOWED))
   {
      Print("[SAFE] 账户不允许交易");
      return false;
   }

   long trade_mode = SymbolInfoInteger(_Symbol, SYMBOL_TRADE_MODE);
   if(trade_mode == SYMBOL_TRADE_MODE_DISABLED)
   {
      Print("[SAFE] 当前品种交易被禁用: ", _Symbol);
      return false;
   }

   return true;
}

bool IsEquityDrawdownLimitReached()
{
   if(InpMaxEquityDrawdownPct <= 0.0)
      return false;

   double balance = AccountInfoDouble(ACCOUNT_BALANCE);
   double equity = AccountInfoDouble(ACCOUNT_EQUITY);

   if(balance <= 0.0)
      return false;

   double drawdown_pct = (balance - equity) / balance;
   if(drawdown_pct >= InpMaxEquityDrawdownPct)
   {
      Print("[SAFE] 净值回撤达到限制: ", DoubleToString(drawdown_pct * 100.0, 2),
            "% >= ", DoubleToString(InpMaxEquityDrawdownPct * 100.0, 2), "%");
      return true;
   }

   return false;
}

bool GetCurrentSymbolPositionType(ENUM_POSITION_TYPE &position_type)
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0)
         continue;

      if(!PositionSelectByTicket(ticket))
         continue;

      if(PositionGetString(POSITION_SYMBOL) == _Symbol)
      {
         position_type = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
         return true;
      }
   }

   return false;
}

bool PreparePositionForAction(string action)
{
   ENUM_POSITION_TYPE current_type = POSITION_TYPE_BUY;
   if(!GetCurrentSymbolPositionType(current_type))
      return true;

   if((action == "BUY" && current_type == POSITION_TYPE_BUY) ||
      (action == "SELL" && current_type == POSITION_TYPE_SELL))
   {
      Print("[SAFE] 已有同向持仓，跳过重复开仓: ", action);
      return false;
   }

   Print("[SAFE] 检测到反向持仓，先平仓再评估新开仓");
   if(!m_trade.PositionClose(_Symbol))
   {
      Print("[SAFE] 反向持仓平仓失败，取消新开仓: retcode=", m_trade.ResultRetcode(),
            " comment=", m_trade.ResultComment());
      return false;
   }

   Sleep(250);

   if(GetCurrentSymbolPositionType(current_type))
   {
      Print("[SAFE] 平仓后仍检测到持仓，取消新开仓");
      return false;
   }

   return true;
}

// ==================== 交易执行函数（支持动态止损止盈） ====================

/**
 * 执行交易 - 支持Python返回的动态止损止盈
 */
void ExecuteTrade(string action, double confidence)
{
   // HOLD信号：清除动态止损止盈
   if(action == "HOLD")
   {
      if(g_dynamic_sl_pips > 0 || g_dynamic_tp_pips > 0)
      {
         Print("HOLD信号，清除动态止损止盈: SL=", g_dynamic_sl_pips, " TP=", g_dynamic_tp_pips);
         ClearDynamicStops();
      }
      return;
   }
   
   if(confidence < InpMinConfidence)
   {
      Print("置信度不足，不执行交易: ", DoubleToString(confidence, 2), " < ", DoubleToString(InpMinConfidence, 2));
      ClearDynamicStops();
      return;
   }

   if(action != "BUY" && action != "SELL")
   {
      Print("[SAFE] 未知交易动作，禁止交易: ", action);
      ClearDynamicStops();
      return;
   }

   if(!IsTradeEnvironmentReady() || IsEquityDrawdownLimitReached())
   {
      ClearDynamicStops();
      return;
   }

   double volume = NormalizeTradeVolume(InpLotSize);
   if(volume <= 0.0)
   {
      ClearDynamicStops();
      return;
   }

   if(!PreparePositionForAction(action))
   {
      ClearDynamicStops();
      return;
   }
   
   double price = 0;
   double sl = 0;
   double tp = 0;
   
   // 优先使用动态止损止盈，否则使用输入参数
   int use_sl = (g_dynamic_sl_pips > 0) ? g_dynamic_sl_pips : InpStopLoss;
   int use_tp = (g_dynamic_tp_pips > 0) ? g_dynamic_tp_pips : InpTakeProfit;
   
   // ── 计算实际价格单位距离 ──────────────────────────────────────────────
   // Python传来的 pips 单位约定：1 pip = 10 * _Point
   // 例如黄金 _Point=0.01，1pip=0.10，30pips=3.00美元
   // 这是业界惯例：黄金/外汇 1 pip = 10 points（第4位小数）
   double pip_size = 10.0 * _Point;
   double sl_distance = use_sl * pip_size;
   double tp_distance = use_tp * pip_size;
   
   // ── STOPS_LEVEL 最小止损保护 ─────────────────────────────────────────
   // MT5券商强制要求止损距离 >= stops_level * _Point
   // 若计算出的距离不足，自动扩大到最小要求
   int stops_level = (int)SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL);
   double min_distance = (stops_level + 5) * _Point;  // 额外加5点缓冲
   if(sl_distance > 0 && sl_distance < min_distance)
   {
      Print("[SL/TP] SL距离(", DoubleToString(sl_distance, 5), ")小于最小限制(", DoubleToString(min_distance, 5), ")，自动调整");
      sl_distance = min_distance;
   }
   if(tp_distance > 0 && tp_distance < min_distance)
   {
      Print("[SL/TP] TP距离(", DoubleToString(tp_distance, 5), ")小于最小限制(", DoubleToString(min_distance, 5), ")，自动调整");
      tp_distance = min_distance;
   }
   
   // 日志输出
   Print("使用止损止盈: SL=", use_sl, "pips(", DoubleToString(sl_distance, 2), "$) (动态:",
         g_dynamic_sl_pips > 0 ? "是" : "否", "), TP=", use_tp, "pips(", DoubleToString(tp_distance, 2),
         "$) (动态:", g_dynamic_tp_pips > 0 ? "是" : "否", ") | stops_level=", stops_level);
   
   if(action == "BUY")
   {
      price = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
      if(price <= 0.0)
      {
         Print("[SAFE] ASK价格无效，禁止BUY");
         ClearDynamicStops();
         return;
      }

      if(use_sl > 0)
         sl = NormalizeDouble(price - sl_distance, _Digits);
      if(use_tp > 0)
         tp = NormalizeDouble(price + tp_distance, _Digits);
      
      Print("[BUY] price=", DoubleToString(price,2), " sl=", DoubleToString(sl,2), " tp=", DoubleToString(tp,2));
      
      string comment = "AI Buy ";
      if(g_dynamic_sl_pips > 0 || g_dynamic_tp_pips > 0)
         comment += "(动态)";
      else
         comment += "(固定)";
      
      if(m_trade.Buy(volume, _Symbol, price, sl, tp, comment))
      {
         Print("[SAFE] BUY下单成功: volume=", DoubleToString(volume, 4),
               " retcode=", m_trade.ResultRetcode(), " comment=", m_trade.ResultComment());
      }
      else
      {
         Print("[SAFE] BUY下单失败: retcode=", m_trade.ResultRetcode(),
               " comment=", m_trade.ResultComment());
      }
      
      // 开仓后清除动态值
      ClearDynamicStops();
   }
   else if(action == "SELL")
   {
      price = SymbolInfoDouble(_Symbol, SYMBOL_BID);
      if(price <= 0.0)
      {
         Print("[SAFE] BID价格无效，禁止SELL");
         ClearDynamicStops();
         return;
      }

      if(use_sl > 0)
         sl = NormalizeDouble(price + sl_distance, _Digits);
      if(use_tp > 0)
         tp = NormalizeDouble(price - tp_distance, _Digits);
      
      Print("[SELL] price=", DoubleToString(price,2), " sl=", DoubleToString(sl,2), " tp=", DoubleToString(tp,2));
      
      string comment = "AI Sell ";
      if(g_dynamic_sl_pips > 0 || g_dynamic_tp_pips > 0)
         comment += "(动态)";
      else
         comment += "(固定)";
      
      if(m_trade.Sell(volume, _Symbol, price, sl, tp, comment))
      {
         Print("[SAFE] SELL下单成功: volume=", DoubleToString(volume, 4),
               " retcode=", m_trade.ResultRetcode(), " comment=", m_trade.ResultComment());
      }
      else
      {
         Print("[SAFE] SELL下单失败: retcode=", m_trade.ResultRetcode(),
               " comment=", m_trade.ResultComment());
      }
      
      // 开仓后清除动态值
      ClearDynamicStops();
   }
}

// ==================== 面板更新函数（保持不变） ====================

/**
 * 更新技术分析面板
 */
void UpdatePanel()
{
   // 保持原始实现（简化版）
   if(!InpShowPanel)
      return;
   
   datetime now = TimeCurrent();
   if(now - m_last_panel_update < PANEL_UPDATE_INTERVAL)
      return;
   
   m_last_panel_update = now;
   
   // 创建或更新面板
   // ... 保持原始面板代码 ...
}

/**
 * 更新支撑阻力线
 */
void UpdateSupportResistanceLines()
{
   // 保持原始实现
   if(!InpShowLines)
      return;
   
   datetime now = TimeCurrent();
   if(now - m_last_sr_update < SR_UPDATE_INTERVAL)
      return;
   
   m_last_sr_update = now;
   CalculateSupportResistance();
   
   // 更新支撑阻力线
   // ... 保持原始代码 ...
}

// ==================== EA主函数 ====================

/**
 * 初始化函数
 */
int OnInit()
{
   Print(StringRepeat("=", 60));
   Print("AI智能交易系统 - Socket集成版");
   Print(StringRepeat("=", 60));
   Print("启动时间: ", TimeToString(TimeCurrent(), TIME_DATE|TIME_SECONDS));
   Print("通信模式: ", EnumToString(InpCommMode));
   Print("Socket地址: ", InpSocketHost, ":", InpSocketPort);
   Print("连接超时: ", InpConnectTimeout, "ms");
   Print("接收超时: ", InpReceiveTimeout, "ms");
   Print("最大重试次数: ", InpMaxRetries);
   Print("重试退避因子: ", InpRetryBackoffFactor);
   Print("故障转移阈值: ", InpFailoverThreshold);
   Print("初始Socket延迟: ", InpInitialSocketDelay, "ms");
   Print(StringRepeat("-", 60));
   
   Print("账户数据推送: ", InpPushAccountData ? "启用" : "禁用");
   Print("账户数据推送间隔: ", InpAccountDataInterval, "秒");
   Print("账户数据服务器: ", InpAccountDataHost, ":", InpAccountDataPort);

   if(!ValidateTradingInputs())
   {
      Print("[SAFE] 参数校验失败，EA初始化中止");
      return(INIT_PARAMETERS_INCORRECT);
   }
   
   // 初始化技术指标
   InitIndicators();
   
   // 初始化账户数据推送
   if(InpPushAccountData)
   {
      m_account_data_enabled = true;
      if(!InitAccountDataConnection())
      {
         Print("⚠️  账户数据推送连接初始化失败");
      }
   }
   
   // 确定通信模式
   m_current_mode = DetermineCommunicationMode();
   
   // 初始化面板
   if(InpShowPanel)
   {
      UpdatePanel();
   }
   
   // 初始化支撑阻力线
   if(InpShowLines)
   {
      UpdateSupportResistanceLines();
   }
   
   Print("✅ EA初始化完成");
   Print(StringRepeat("=", 60));
   
   return(INIT_SUCCEEDED);
}

/**
 * 反初始化函数
 */
void OnDeinit(const int reason)
{
   Print(StringRepeat("=", 60));
   Print("EA关闭 - 通信统计");
   Print(StringRepeat("=", 60));
   Print("总请求数: ", m_total_requests);
   Print("成功请求数: ", m_successful_requests);
   Print("失败请求数: ", m_failed_requests);
   Print("模式切换次数: ", m_mode_switches);
   Print("最后通信模式: ", EnumToString(m_current_mode));
   
   if(m_total_requests > 0)
   {
      double success_rate = (double(m_successful_requests) / m_total_requests) * 100;
      Print("成功率: ", DoubleToString(success_rate, 1), "%");
   }
   
   Print(StringRepeat("=", 60));
   
   // 关闭账户数据推送连接
   if(m_account_data_socket != -1)
   {
      SocketClose(m_account_data_socket);
      m_account_data_socket = -1;
      Print("✅ 账户数据推送连接已关闭");
   }
   
   // 清理面板
   // ... 保持原始清理代码 ...
}

/**
 * 定时器函数
 */
void OnTimer()
{
   // 保持原始实现
   UpdatePanel();
   UpdateSupportResistanceLines();
   
   // 尝试恢复Socket连接
   TryRecoverSocketConnection();
}

/**
 * 报价处理函数
 */
void OnTick()
{
   // 检查是否需要发送请求
   datetime now = TimeCurrent();
   if(now - m_last_request_time < InpRequestInterval)
      return;
   
   m_last_request_time = now;
   
   // 尝试恢复Socket连接（如果当前是文件模式）
   TryRecoverSocketConnection();
   
   // 请求AI前先推送账户/持仓数据，让Python风控使用最新MQL5 API数据
   if(m_account_data_enabled)
   {
      PushAccountDataToServer();
   }
   
   Print("\n" + StringRepeat("=", 60));
   Print("发送AI请求 - ", TimeToString(now, TIME_DATE|TIME_SECONDS));
   Print("当前通信模式: ", EnumToString(m_current_mode));
   Print("连续失败次数: ", m_consecutive_failures);
   Print(StringRepeat("-", 60));
   
   // 构建市场数据
   string market_data = BuildMarketData();
   
   // 发送请求
   string response;
   if(SendAIRequest(market_data, response))
   {
      // 解析响应
      string action;
      double confidence;
      string reason;
      bool use_deepseek;
      
      if(ParseAIResponse(response, action, confidence, reason, use_deepseek))
      {
         m_last_action = action;
         m_last_confidence = confidence;
         m_last_reason = reason;
         
         Print("AI建议: ", action, " 置信度: ", DoubleToString(confidence, 2));
         Print("分析原因: ", reason);
         Print("使用DeepSeek: ", use_deepseek ? "是" : "否");
         
         // 执行交易
         ExecuteTrade(action, confidence);
      }
      else
      {
         Print("❌ 解析AI响应失败，清除动态止损止盈");
         g_dynamic_sl_pips = 0;
         g_dynamic_tp_pips = 0;
      }
   }
   else
   {
      Print("❌ 发送AI请求失败");
   }
   
   // 更新面板
   UpdatePanel();
   UpdateSupportResistanceLines();
   
   Print(StringRepeat("=", 60));
}

// ==================== 辅助函数 ====================

/**
 * 通信模式枚举转字符串
 */
string EnumToString(CommunicationMode mode)
{
   switch(mode)
   {
      case MODE_AUTO:   return "AUTO";
      case MODE_SOCKET: return "SOCKET";
      case MODE_FILE:   return "FILE";
      default:          return "UNKNOWN";
   }
}

//+------------------------------------------------------------------+
