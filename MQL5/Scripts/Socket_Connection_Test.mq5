//+------------------------------------------------------------------+
//|                                                      Socket_Connection_Test.mq5 |
//|                                     MQL5 Socket连接测试脚本 |
//|                                      版本: 1.0 |
//+------------------------------------------------------------------+
#property copyright "2026-04-18"
#property link      ""
#property version   "1.00"
#property description "Socket服务器连接测试脚本"
#property description "用于诊断EA Socket连接问题"
#property description "测试目标: 127.0.0.1:8080"
#property script_show_inputs

// 输入参数
input string   InpSocketHost = "127.0.0.1";   // Socket服务器地址
input int      InpSocketPort = 8080;          // Socket服务器端口
input int      InpConnectTimeout = 3000;      // 连接超时(ms)
input int      InpSendTimeout = 1000;         // 发送超时(ms)
input int      InpReceiveTimeout = 5000;      // 接收超时(ms)

// 错误描述函数
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

// 字符串重复函数（从EA复制）
string StringRepeat(string str, int count)
{
   string result = "";
   for(int i = 0; i < count; i++)
   {
      result += str;
   }
   return result;
}

//+------------------------------------------------------------------+
//| 脚本开始函数                                                     |
//+------------------------------------------------------------------+
void OnStart()
{
   Print("\n" + StringRepeat("=", 70));
   Print("MQL5 Socket连接诊断测试");
   Print("目标服务器: ", InpSocketHost, ":", InpSocketPort);
   Print("连接超时: ", InpConnectTimeout, "ms");
   Print(StringRepeat("=", 70));
   
   // 1. 创建Socket
   Print("\n1. 创建Socket...");
   int socket_handle = SocketCreate();
   if(socket_handle == INVALID_HANDLE)
   {
      int last_error = GetLastError();
      Print("❌ 无法创建Socket");
      Print("   错误代码: ", last_error);
      Print("   错误描述: ", ErrorDescription(last_error));
      Print(StringRepeat("=", 70));
      return;
   }
   Print("✅ Socket创建成功，句柄: ", socket_handle);
   
   // 2. 连接服务器
   Print("\n2. 连接服务器...");
   uint connect_start_time = GetTickCount();
   bool connect_result = SocketConnect(socket_handle, InpSocketHost, InpSocketPort, InpConnectTimeout);
   uint connect_end_time = GetTickCount();
   uint connect_duration = connect_end_time - connect_start_time;
   
   if(!connect_result)
   {
      int last_error = GetLastError();
      Print("❌ Socket连接失败");
      Print("   连接耗时: ", connect_duration, "ms");
      Print("   错误代码: ", last_error);
      Print("   错误描述: ", ErrorDescription(last_error));
      SocketClose(socket_handle);
      Print(StringRepeat("=", 70));
      return;
   }
   
   Print("✅ Socket连接成功");
   Print("   连接耗时: ", connect_duration, "ms");
   
   // 3. 发送测试消息
   Print("\n3. 发送测试消息...");
   uchar test_msg[] = {0x54, 0x45, 0x53, 0x54, 0x0A}; // "TEST\n" 与EA的测试消息相同
   uint send_start_time = GetTickCount();
   int send_result = SocketSend(socket_handle, test_msg, ArraySize(test_msg));
   uint send_end_time = GetTickCount();
   
   if(send_result <= 0)
   {
      int last_error = GetLastError();
      Print("⚠️  测试消息发送失败");
      Print("   发送耗时: ", send_end_time - send_start_time, "ms");
      Print("   错误代码: ", last_error);
      Print("   错误描述: ", ErrorDescription(last_error));
      Print("   注意: 连接已建立，但发送失败");
   }
   else
   {
      Print("✅ 测试消息发送成功");
      Print("   发送字节: ", send_result);
      Print("   发送耗时: ", send_end_time - send_start_time, "ms");
   }
   
   // 4. 尝试接收测试响应
   Print("\n4. 接收测试响应...");
   uchar response_buffer[1024];
   uint response_start_time = GetTickCount();
   int receive_result = SocketRead(socket_handle, response_buffer, ArraySize(response_buffer), InpReceiveTimeout);
   uint response_end_time = GetTickCount();
   
   if(receive_result <= 0)
   {
      int last_error = GetLastError();
      Print("⚠️  接收测试响应失败");
      Print("   接收耗时: ", response_end_time - response_start_time, "ms");
      Print("   错误代码: ", last_error);
      Print("   错误描述: ", ErrorDescription(last_error));
      Print("   注意: 服务器可能不响应测试消息");
   }
   else
   {
      string response_str = CharArrayToString(response_buffer, 0, receive_result);
      Print("✅ 收到测试响应");
      Print("   接收耗时: ", response_end_time - response_start_time, "ms");
      Print("   响应长度: ", receive_result, "字节");
      Print("   响应内容: ", response_str);
   }
   
   // 5. 发送JSON请求
   Print("\n5. 发送JSON请求...");
   string json_request = "{\"symbol\":\"BTCUSD\",\"bid\":77000.0,\"ask\":77050.0,\"time\":" + IntegerToString((int)TimeCurrent()) + "}";
   uchar json_buffer[];
   int len = StringToCharArray(json_request, json_buffer, 0, StringLen(json_request));
   
   uint json_send_start = GetTickCount();
   int json_send_result = SocketSend(socket_handle, json_buffer, len);
   uint json_send_end = GetTickCount();
   
   if(json_send_result <= 0)
   {
      int last_error = GetLastError();
      Print("❌ JSON请求发送失败");
      Print("   发送耗时: ", json_send_end - json_send_start, "ms");
      Print("   错误代码: ", last_error);
      Print("   错误描述: ", ErrorDescription(last_error));
   }
   else
   {
      Print("✅ JSON请求发送成功");
      Print("   发送耗时: ", json_send_end - json_send_start, "ms");
      Print("   请求内容: ", json_request);
      
      // 6. 接收JSON响应
      Print("\n6. 接收JSON响应...");
      uchar json_response_buffer[4096];
      uint json_receive_start = GetTickCount();
      int json_receive_result = SocketRead(socket_handle, json_response_buffer, ArraySize(json_response_buffer), InpReceiveTimeout);
      uint json_receive_end = GetTickCount();
      
      if(json_receive_result <= 0)
      {
         int last_error = GetLastError();
         Print("❌ JSON响应接收失败");
         Print("   接收耗时: ", json_receive_end - json_receive_start, "ms");
         Print("   错误代码: ", last_error);
         Print("   错误描述: ", ErrorDescription(last_error));
      }
      else
      {
         string json_response_str = CharArrayToString(json_response_buffer, 0, json_receive_result);
         Print("✅ 收到JSON响应");
         Print("   接收耗时: ", json_receive_end - json_receive_start, "ms");
         Print("   响应长度: ", json_receive_result, "字节");
         Print("   响应内容: ", json_response_str);
         
         // 简单验证JSON格式
         if(StringFind(json_response_str, "{") == 0 && StringFind(json_response_str, "}") > 0)
         {
            Print("✅ JSON格式验证通过");
         }
         else
         {
            Print("❌ JSON格式验证失败 - 响应可能不是有效的JSON");
         }
      }
   }
   
   // 7. 关闭Socket
   Print("\n7. 关闭Socket连接...");
   SocketClose(socket_handle);
   Print("✅ Socket已关闭");
   
   Print("\n" + StringRepeat("=", 70));
   Print("Socket连接测试完成");
   Print("建议:");
   Print("1. 如果所有测试通过: Socket服务器工作正常");
   Print("2. 如果连接失败: 检查防火墙、杀毒软件设置");
   Print("3. 如果发送/接收失败: 检查网络或服务器配置");
   Print("4. 确保EA已重新编译（按F7键）");
   Print(StringRepeat("=", 70));
}
//+------------------------------------------------------------------+