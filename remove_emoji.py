#!/usr/bin/env python3
"""
移除测试脚本中的emoji字符，避免Windows控制台编码问题
"""

import re

def remove_emoji(text):
    """替换emoji为纯文本"""
    emoji_map = {
        '->': '->',
        '[AI]': '[AI]',
        '[RM]': '[RM]',
        '[TEST]': '[测试]',
        '[TOOL]': '[工具]',
        '[DATA]': '[数据]',
        '[DONE]': '[完成]',
        '[TIP]': '[提示]',
        '[ERR]': '[错误]',
        '[OK]': '[成功]',
        '[1]': '[1]',
        '[2]': '[2]',
        '[3]': '[3]',
        '[4]': '[4]',
        '[5]': '[5]',
    }
    
    for emoji, replacement in emoji_map.items():
        text = text.replace(emoji, replacement)
    
    return text

def process_file(file_path):
    """处理文件"""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    new_content = remove_emoji(content)
    
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(new_content)
    
    print(f"已处理文件: {file_path}")
    print(f"替换了 {len(content) - len(new_content)} 个字符")

if __name__ == "__main__":
    file_path = r"d:\搬家文件夹\XM Global MT5\test_mql5_integration.py"
    process_file(file_path)