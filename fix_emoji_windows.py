#!/usr/bin/env python3
"""
修复Windows控制台编码问题 - 替换所有emoji字符
"""

import os
import re
import sys
from pathlib import Path

# 需要修复的目录
CORE_DIRS = [
    "core",
    "tools",
    "tests",
    "."
]

# 排除的文件
EXCLUDE_FILES = [
    "__pycache__",
    ".pyc",
    ".git",
    ".idea",
    ".vscode",
    "node_modules",
    "venv",
    "env",
]

# emoji替换映射
EMOJI_REPLACEMENTS = {
    # 常见emoji
    '[OK]': '[OK]',
    '[ERR]': '[ERR]',
    '[WARN]': '[WARN]',
    '->': '->',
    '[AI]': '[AI]',
    '[RM]': '[RM]',
    '[TEST]': '[TEST]',
    '[TOOL]': '[TOOL]',
    '[DATA]': '[DATA]',
    '[DONE]': '[DONE]',
    '[TIP]': '[TIP]',
    '[LOG]': '[LOG]',
    '[UP]': '[UP]',
    '[DOWN]': '[DOWN]',
    '[TIME]': '[TIME]',
    '[ALERT]': '[ALERT]',
    '[FAST]': '[FAST]',
    '[ALARM]': '[ALARM]',
    '[REFRESH]': '[REFRESH]',
    '[CLIP]': '[CLIP]',
    '[LINK]': '[LINK]',
    '[DIR]': '[DIR]',
    '[FILE]': '[FILE]',
    '[WORK]': '[WORK]',
    '[AI]': '[AI]',
    '[MONEY]': '[MONEY]',
    '[PIN]': '[PIN]',
    '[LOCK]': '[LOCK]',
    '[UNLOCK]': '[UNLOCK]',
    '[STAR]': '[STAR]',
    '[HOT]': '[HOT]',
    '[VIP]': '[VIP]',
    '[CONFIG]': '[CONFIG]',
    
    # 数字符号
    '[1]': '[1]',
    '[2]': '[2]',
    '[3]': '[3]',
    '[4]': '[4]',
    '[5]': '[5]',
    '[6]': '[6]',
    '[7]': '[7]',
    '[8]': '[8]',
    '[9]': '[9]',
    '[0]': '[0]',
    
    # Unicode符号
    '\u2705': '[OK]',      # [OK]
    '\u274c': '[ERR]',     # [ERR]
    '\u26a0': '[WARN]',    # [WARN]
    '\u26a0\ufe0f': '[WARN]', # [WARN]
    '\u2611': '[CHECK]',   # [CHECK]
    '\u2714': '[TICK]',    # [TICK]
    '\u2716': '[CROSS]',   # [CROSS]
    '\u2699': '[CONFIG]',    # [CONFIG]
    '\u2699\ufe0f': '[CONFIG]', # [CONFIG]
    
    # 杂项
    '\U0001f4ca': '[DATA]',    # [DATA]
    '\U0001f4c8': '[UP]',       # [UP]
    '\U0001f4c9': '[DOWN]',     # [DOWN]
    '\U0001f6e1': '[RM]',   # [RM]
    '\U0001f6e1\ufe0f': '[RM]', # [RM]
    '\U0001f527': '[TOOL]',   # [TOOL]
    '\U0001f527\ufe0f': '[TOOL]', # [TOOL]️
}

def replace_emoji_in_text(text):
    """替换文本中的emoji字符"""
    for emoji, replacement in EMOJI_REPLACEMENTS.items():
        text = text.replace(emoji, replacement)
    return text

def process_file(file_path):
    """处理单个文件"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        original_len = len(content)
        new_content = replace_emoji_in_text(content)
        
        if content != new_content:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
            
            diff = original_len - len(new_content)
            print(f"  [修复] {file_path} ({diff} 字符)")
            return True
        
        return False
    
    except UnicodeDecodeError:
        # 跳过非UTF-8文件
        return False
    except Exception as e:
        print(f"  [错误] {file_path}: {e}")
        return False

def find_python_files(base_dir):
    """查找所有Python文件"""
    py_files = []
    
    for root, dirs, files in os.walk(base_dir):
        # 排除不需要的目录
        dirs[:] = [d for d in dirs if not any(excl in d for excl in EXCLUDE_FILES)]
        
        for file in files:
            if file.endswith('.py'):
                full_path = os.path.join(root, file)
                py_files.append(full_path)
    
    return py_files

def main():
    """主函数"""
    print("=" * 70)
    print("Windows控制台编码问题修复工具")
    print("=" * 70)
    
    base_dir = os.path.dirname(os.path.abspath(__file__))
    
    total_fixed = 0
    total_files = 0
    
    for dir_name in CORE_DIRS:
        dir_path = os.path.join(base_dir, dir_name)
        
        if not os.path.exists(dir_path):
            continue
        
        print(f"\n扫描目录: {dir_path}")
        
        py_files = find_python_files(dir_path)
        
        for file_path in py_files:
            total_files += 1
            if process_file(file_path):
                total_fixed += 1
    
    print("\n" + "=" * 70)
    print(f"修复完成:")
    print(f"  扫描文件: {total_files} 个")
    print(f"  修复文件: {total_fixed} 个")
    print(f"  EMOJI替换: {len(EMOJI_REPLACEMENTS)} 个字符")
    print("=" * 70)
    
    if total_fixed > 0:
        print("\n建议下一步:")
        print("  1. 重新运行测试: python test_mql5_integration.py")
        print("  2. 检查所有模块功能正常")
        print("  3. 在MT5中加载更新后的EA进行测试")

if __name__ == "__main__":
    main()