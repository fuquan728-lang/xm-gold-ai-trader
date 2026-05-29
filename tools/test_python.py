#!/usr/bin/env python3
# -*- coding: utf-8 -*-

print("Testing Python environment...")

import sys
print(f"Python version: {sys.version}")

# Test requests library
try:
    import requests
    print("✓ requests library found")
    
    # Test basic HTTP request
    response = requests.get("https://www.google.com", timeout=5)
    print(f"✓ HTTP request successful: {response.status_code}")
    
except ImportError as e:
    print(f"✗ requests library not found: {e}")
except Exception as e:
    print(f"✗ HTTP request failed: {e}")

print("Test completed.")
input("Press Enter to exit...")
