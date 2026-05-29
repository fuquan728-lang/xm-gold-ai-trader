//+------------------------------------------------------------------+
//|                                                  FindPath.mq5    |
//|                        查找MT5数据路径脚本                      |
//+------------------------------------------------------------------+
#property copyright   "Find Path"
#property link        "https://www.mql5.com"
#property version     "1.00"
#property strict
#property script_show_inputs

//+------------------------------------------------------------------+
//| Script program start function                                    |
//+------------------------------------------------------------------+
void OnStart()
  {
   Print("=== MT5路径信息 ===");
   Print("");
   Print("尝试写入测试文件...");
   
   string filename = "test_path.txt";
   int handle = FileOpen(filename, FILE_WRITE|FILE_TXT|FILE_ANSI);
   
   if(handle != INVALID_HANDLE)
     {
      FileWrite(handle, "Test file created successfully!");
      FileClose(handle);
      Print("✓ 测试文件已写入: ", filename);
      Print("");
      Print("=== 重要提示 ===");
      Print("请在文件资源管理器中搜索这个文件:");
      Print("文件名: ", filename);
      Print("");
      Print("找到后，请把该文件所在的文件夹路径告诉我！");
      Print("通常路径格式类似: C:\\Users\\...\\MQL5\\Files\\");
     }
   else
     {
      Print("✗ 无法写入文件，错误代码: ", GetLastError());
     }
   
   Print("");
   Print("=== 完成 ===");
  }
//+------------------------------------------------------------------+
