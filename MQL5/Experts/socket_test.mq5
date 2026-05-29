//+------------------------------------------------------------------+
//|                                              socket_test.mq5     |
//|                    MT5 Socket通信客户端测试脚本                 |
//|                     第1阶段原型验证                             |
//+------------------------------------------------------------------+
#property copyright "Socket通信测试"
#property link      "https://www.mql5.com"
#property version   "1.00"
#property script_show_inputs

// 测试配置
input string InpServerHost   = "127.0.0.1";  // 服务器地址
input int    InpServerPort   = 8080;         // 服务器端口
input int    InpConnectTimeout = 3000;       // 连接超时（毫秒）
input int    InpReceiveTimeout = 5000;       // 接收超时（毫秒）
input bool   InpVerboseLog   = true;         // 详细日志输出

//+------------------------------------------------------------------+
//| 自定义字符串修剪函数                                            |
//+------------------------------------------------------------------+
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

//+------------------------------------------------------------------+
//| Socket通信函数                                                  |
//+------------------------------------------------------------------+
bool SocketRequest(const string request_json, string &response_json, 
                   const string host, const int port, 
                   const int connect_timeout, const int receive_timeout)
{
   int socket_handle = INVALID_HANDLE;
   
   // 创建Socket
   socket_handle = SocketCreate();
   if(socket_handle == INVALID_HANDLE)
   {
      if(InpVerboseLog) Print("❌ Socket创建失败");
      return false;
   }
   
   if(InpVerboseLog) Print("✅ Socket创建成功，正在连接服务器 ", host, ":", port);
   
   // 连接服务器
   if(!SocketConnect(socket_handle, host, port, connect_timeout))
   {
      if(InpVerboseLog) Print("❌ 连接服务器失败");
      SocketClose(socket_handle);
      return false;
   }
   
   if(InpVerboseLog) Print("✅ 服务器连接成功");
   
   // 发送请求（添加换行符作为消息分隔符）
   string request_with_newline = request_json + "\n";
   uchar send_buf[];
   StringToCharArray(request_with_newline, send_buf, 0, StringLen(request_with_newline));
   int bytes_sent = SocketSend(socket_handle, send_buf, ArraySize(send_buf));
   
   if(bytes_sent <= 0)
   {
      if(InpVerboseLog) Print("❌ 发送请求失败");
      SocketClose(socket_handle);
      return false;
   }
   
   if(InpVerboseLog) Print("✅ 请求发送成功，发送字节数: ", bytes_sent);
   
   // 接收响应 (尝试读取，部分版本 SocketReceive 签名不同)
   int bytes_received = 0;
   uchar buffer[];
   ArrayResize(buffer, 4096);
   // 使用循环轮询方式接收
   int waited = 0;
   while(waited < receive_timeout)
   {
      bytes_received = SocketIsReadable(socket_handle);
      if(bytes_received > 0) break;
      Sleep(10);
      waited += 10;
   }
   if(bytes_received > 0)
   {
      bytes_received = (int)SocketIsReadable(socket_handle);
      ArrayResize(buffer, bytes_received);
      bytes_received = SocketRead(socket_handle, buffer, bytes_received, 100);
   }
   
   if(bytes_received <= 0)
   {
      if(InpVerboseLog) Print("❌ 接收响应失败或超时");
      SocketClose(socket_handle);
      return false;
   }
   
   // 转换为字符串
   response_json = CharArrayToString(buffer, 0, bytes_received);
   response_json = StringTrim(response_json);  // 去除换行符和空白
   
   if(InpVerboseLog) 
   {
      string debug_response = response_json;
      if(StringLen(debug_response) > 200)
         debug_response = StringSubstr(debug_response, 0, 197) + "...";
      Print("✅ 响应接收成功，接收字节数: ", bytes_received);
      Print("📥 响应内容: ", debug_response);
   }
   
   // 关闭Socket
   SocketClose(socket_handle);
   
   return true;
}

//+------------------------------------------------------------------+
//| 生成测试请求数据                                                |
//+------------------------------------------------------------------+
string GenerateTestRequest()
{
   // 当前时间
   datetime current_time = TimeCurrent();
   long timestamp = (long)current_time;
   
   // 当前品种和价格
   string symbol = Symbol();
   double bid = SymbolInfoDouble(symbol, SYMBOL_BID);
   double ask = SymbolInfoDouble(symbol, SYMBOL_ASK);
   
   // 构建请求JSON
   string request = "{";
   request += "\"symbol\":\"" + symbol + "\",";
   request += "\"bid\":" + DoubleToString(bid, 5) + ",";
   request += "\"ask\":" + DoubleToString(ask, 5) + ",";
   request += "\"time\":" + IntegerToString(timestamp) + ",";
   
   // 添加示例历史数据（简化版）
   request += "\"history\":[";
   request += "{\"time\":" + IntegerToString(timestamp - 3600) + ",";
   request += "\"open\":" + DoubleToString(bid - 0.0010, 5) + ",";
   request += "\"high\":" + DoubleToString(bid + 0.0020, 5) + ",";
   request += "\"low\":" + DoubleToString(bid - 0.0020, 5) + ",";
   request += "\"close\":" + DoubleToString(bid - 0.0005, 5) + ",";
   request += "\"volume\":1000}";
   request += "],";
   
   // 添加示例指标数据
   request += "\"indicators\":{";
   request += "\"rsi\":55.5,";
   request += "\"macd_main\":0.0012,";
   request += "\"macd_signal\":0.0008,";
   request += "\"ema50\":" + DoubleToString(bid - 0.0005, 5);
   request += "}";
   request += "}";
   
   return request;
}

//+------------------------------------------------------------------+
//| 解析JSON响应                                                    |
//+------------------------------------------------------------------+
bool ParseJsonResponse(const string json_str, string &action, double &confidence, string &reason, bool &use_deepseek)
{
   // 简化版JSON解析（MQL5没有内置JSON解析，这里使用简单字符串处理）
   // 在实际项目中应使用更健壮的解析方法
   
   action = "HOLD";
   confidence = 0.0;
   reason = "解析失败";
   use_deepseek = false;
   
   // 检查是否包含错误字段
   if(StringFind(json_str, "\"error\"") >= 0)
   {
      reason = "服务器返回错误";
      return false;
   }
   
   // 提取action字段
   int action_start = StringFind(json_str, "\"action\":\"");
   if(action_start >= 0)
   {
      action_start += 10; // "\"action\":\"" 的长度
      int action_end = StringFind(json_str, "\"", action_start);
      if(action_end > action_start)
      {
         action = StringSubstr(json_str, action_start, action_end - action_start);
      }
   }
   
   // 提取confidence字段
   int conf_start = StringFind(json_str, "\"confidence\":");
   if(conf_start >= 0)
   {
      conf_start += 13; // "\"confidence\":" 的长度
      int conf_end = StringFind(json_str, ",", conf_start);
      if(conf_end < 0) conf_end = StringFind(json_str, "}", conf_start);
      
      if(conf_end > conf_start)
      {
         string conf_str = StringSubstr(json_str, conf_start, conf_end - conf_start);
         conf_str = StringTrim(conf_str);
         confidence = StringToDouble(conf_str);
      }
   }
   
   // 提取reason字段
   int reason_start = StringFind(json_str, "\"reason\":\"");
   if(reason_start >= 0)
   {
      reason_start += 10; // "\"reason\":\"" 的长度
      int reason_end = StringFind(json_str, "\"", reason_start);
      if(reason_end > reason_start)
      {
         reason = StringSubstr(json_str, reason_start, reason_end - reason_start);
      }
   }
   
   // 提取use_deepseek字段
   int deepseek_start = StringFind(json_str, "\"use_deepseek\":");
   if(deepseek_start >= 0)
   {
      deepseek_start += 15; // "\"use_deepseek\":" 的长度
      string deepseek_str = StringSubstr(json_str, deepseek_start, 4); // 取true或false
      use_deepseek = (StringFind(deepseek_str, "true") >= 0);
   }
   
   return true;
}

//+------------------------------------------------------------------+
//| 运行单次连接测试                                                |
//+------------------------------------------------------------------+
bool RunSingleTest(int test_num)
{
   Print("\n=== 测试 ", test_num, " ===");
   
   // 生成测试请求
   string request_json = GenerateTestRequest();
   
   if(InpVerboseLog)
   {
      string debug_request = request_json;
      if(StringLen(debug_request) > 200)
         debug_request = StringSubstr(debug_request, 0, 197) + "...";
      Print("📤 发送请求: ", debug_request);
   }
   
   // 发送请求并接收响应
   string response_json = "";
   uint start_time = GetTickCount();
   
   bool success = SocketRequest(request_json, response_json, 
                               InpServerHost, InpServerPort,
                               InpConnectTimeout, InpReceiveTimeout);
   
   uint elapsed_time = GetTickCount() - start_time;
   
   if(!success)
   {
      Print("❌ 测试 ", test_num, " 失败，耗时: ", elapsed_time, "ms");
      return false;
   }
   
   // 解析响应
   string action;
   double confidence;
   string reason;
   bool use_deepseek;
   
   bool parse_success = ParseJsonResponse(response_json, action, confidence, reason, use_deepseek);
   
   if(!parse_success)
   {
      Print("⚠️  测试 ", test_num, " 响应解析失败");
      Print("原始响应: ", response_json);
   }
   
   Print("✅ 测试 ", test_num, " 成功，耗时: ", elapsed_time, "ms");
   Print("📊 分析结果: ", action, " (置信度: ", DoubleToString(confidence, 2), ")");
   Print("💡 原因: ", reason);
   Print("🤖 使用DeepSeek: ", use_deepseek ? "是" : "否");
   
   return true;
}

//+------------------------------------------------------------------+
//| 运行压力测试（多个连续请求）                                    |
//+------------------------------------------------------------------+
void RunStressTest(int num_requests)
{
   Print("\n" + StringFormat("=", 60));
   Print("开始压力测试 (", num_requests, "个请求)");
   Print(StringFormat("=", 60));
   
   int success_count = 0;
   int fail_count = 0;
   uint total_time = 0;
   uint min_time = 0xFFFFFFFF; // 最大uint值
   uint max_time = 0;
   
   for(int i = 1; i <= num_requests; i++)
   {
      uint start_time = GetTickCount();
      bool success = RunSingleTest(i);
      uint elapsed_time = GetTickCount() - start_time;
      
      total_time += elapsed_time;
      
      if(elapsed_time < min_time) min_time = elapsed_time;
      if(elapsed_time > max_time) max_time = elapsed_time;
      
      if(success)
         success_count++;
      else
         fail_count++;
      
      // 请求间延迟（模拟真实交易场景）
      if(i < num_requests)
         Sleep(500);
   }
   
   // 打印统计结果
   Print("\n" + StringFormat("=", 60));
   Print("压力测试结果");
   Print(StringFormat("=", 60));
   Print("总请求数: ", num_requests);
   Print("成功: ", success_count);
   Print("失败: ", fail_count);
   
   if(success_count > 0)
   {
      double success_rate = (double(success_count) / num_requests) * 100;
      Print("成功率: ", DoubleToString(success_rate, 1), "%");
      
      double avg_time = double(total_time) / success_count;
      Print("平均响应时间: ", DoubleToString(avg_time, 1), "ms");
      Print("最小响应时间: ", min_time, "ms");
      Print("最大响应时间: ", max_time, "ms");
   }
   
   if(fail_count > 0)
   {
      double fail_rate = (double(fail_count) / num_requests) * 100;
      Print("失败率: ", DoubleToString(fail_rate, 1), "%");
   }
}

//+------------------------------------------------------------------+
//| 脚本入口函数                                                    |
//+------------------------------------------------------------------+
void OnStart()
{
   Print("============================================================");
   Print("MT5 Socket通信客户端测试脚本");
   Print("============================================================");
   Print("启动时间: ", TimeToString(TimeCurrent(), TIME_DATE|TIME_SECONDS));
   Print("服务器地址: ", InpServerHost, ":", InpServerPort);
   Print("连接超时: ", InpConnectTimeout, "ms");
   Print("接收超时: ", InpReceiveTimeout, "ms");
   Print("------------------------------------------------------------");
   
   // 检查服务器是否可访问
   Print("正在检查服务器可访问性...");
   
   int test_socket = SocketCreate();
   if(test_socket == INVALID_HANDLE)
   {
      Print("❌ 无法创建测试Socket，请检查网络权限");
      return;
   }
   
   bool can_connect = SocketConnect(test_socket, InpServerHost, InpServerPort, 1000);
   SocketClose(test_socket);
   
   if(!can_connect)
   {
      Print("❌ 无法连接到服务器 ", InpServerHost, ":", InpServerPort);
      Print("请确保:");
      Print("1. Python Socket服务器正在运行");
      Print("2. 防火墙允许端口 ", InpServerPort);
      Print("3. 服务器地址和端口正确");
      return;
   }
   
   Print("✅ 服务器可访问，开始测试...");
   
   // 运行测试
   int choice = 0;
   
   while(choice != 3)
   {
      Print("\n请选择测试模式:");
      Print("1. 单次连接测试");
      Print("2. 压力测试 (5次请求)");
      Print("3. 退出");
      
      // 在实际MT5中，需要使用Dialog或输入参数
      // 这里简化处理，直接运行预设测试
      choice = 2; // 默认运行压力测试
      
      if(choice == 1)
      {
         RunSingleTest(1);
         break;
      }
      else if(choice == 2)
      {
         RunStressTest(5);
         break;
      }
      else if(choice == 3)
      {
         Print("退出测试");
         break;
      }
      else
      {
         Print("无效选择，请重试");
      }
   }
   
   Print("\n============================================================");
   Print("测试完成");
   Print("完成时间: ", TimeToString(TimeCurrent(), TIME_DATE|TIME_SECONDS));
   Print("============================================================");
}

//+------------------------------------------------------------------+