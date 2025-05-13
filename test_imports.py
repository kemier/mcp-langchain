#!/usr/bin/env python3
# Simple script to verify imports and module paths

import sys
import os
import importlib

print("Python version:", sys.version)
print("Current working directory:", os.getcwd())
print("sys.path:", sys.path)

# Test direct import
print("\n----- Testing direct import -----")
try:
    import mcp_web_app
    print("✅ Successfully imported mcp_web_app")
    
    # Test importing models
    try:
        from mcp_web_app.models.models import ServerConfig
        print("✅ Successfully imported ServerConfig from mcp_web_app.models.models")
    except ImportError as e:
        print(f"❌ Failed to import from mcp_web_app.models.models: {e}")
        
    # Test importing services
    try:
        from mcp_web_app.services.config_manager import config_manager
        print("✅ Successfully imported config_manager from mcp_web_app.services.config_manager")
    except ImportError as e:
        print(f"❌ Failed to import from mcp_web_app.services.config_manager: {e}")
        
except ImportError as e:
    print(f"❌ Failed to import mcp_web_app module: {e}")

# Test adding directory to path
print("\n----- Testing with directory in sys.path -----")
mcp_web_app_dir = os.path.join(os.getcwd(), "mcp_web_app")
if mcp_web_app_dir not in sys.path:
    sys.path.append(mcp_web_app_dir)
    print(f"Added {mcp_web_app_dir} to sys.path")

try:
    import models
    print("✅ Successfully imported models module")
except ImportError as e:
    print(f"❌ Failed to import models module: {e}")

# Print module details
print("\n----- Module file paths -----")
for module_name in ["mcp_web_app", "models", "mcp_web_app.models"]:
    try:
        module = importlib.import_module(module_name)
        print(f"{module_name}: {module.__file__}")
    except (ImportError, AttributeError) as e:
        print(f"{module_name}: Not found - {str(e)}") 