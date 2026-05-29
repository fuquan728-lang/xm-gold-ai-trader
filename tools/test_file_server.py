#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import time
import json
from datetime import datetime

print("Testing file server...")

# Test file operations
test_file = "test_file.txt"

try:
    # Test writing
    with open(test_file, 'w') as f:
        f.write("Test content")
    print("✓ File write successful")
    
    # Test reading
    with open(test_file, 'r') as f:
        content = f.read()
    print(f"✓ File read successful: {content}")
    
    # Test deletion
    os.remove(test_file)
    print("✓ File delete successful")
    
except Exception as e:
    print(f"✗ File operation failed: {e}")

# Test JSON operations
test_json = "test_json.json"
test_data = {
    "action": "SELL",
    "confidence": 0.65,
    "reason": "Test reason"
}

try:
    # Test JSON write
    with open(test_json, 'w', encoding='utf-16') as f:
        json.dump(test_data, f, ensure_ascii=False)
    print("✓ JSON write successful")
    
    # Test JSON read
    with open(test_json, 'r', encoding='utf-16') as f:
        loaded_data = json.load(f)
    print(f"✓ JSON read successful: {loaded_data}")
    
    # Test deletion
    os.remove(test_json)
    print("✓ JSON delete successful")
    
except Exception as e:
    print(f"✗ JSON operation failed: {e}")

print("File server test completed.")
input("Press Enter to exit...")
