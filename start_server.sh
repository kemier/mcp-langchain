#!/bin/bash

echo "=== MCP App Server Startup Script ==="
echo "Checking for existing server processes..."

# Kill all Python processes with mcp_web_app in their command line
echo "Looking for MCP-related processes..."
ps aux | grep -E "python.*mcp_web_app" | grep -v grep

# Kill all processes using port 8008 or with mcp_web_app in their command line
echo "Killing any existing MCP server processes..."
pkill -9 -f "python.*mcp_web_app" || echo "No MCP processes found to kill"

# Double-check port 8008 specifically
PID=$(lsof -ti:8008)
if [ ! -z "$PID" ]; then
  echo "Found process using port 8008 (PID: $PID). Terminating..."
  kill -9 $PID
  sleep 1
fi

# Make sure we're in the right directory
cd "$(dirname "$0")"
PROJECT_ROOT=$(pwd)
echo "Project root: $PROJECT_ROOT"

# Create an __init__.py file in mcp_web_app if it doesn't exist
# This helps with Python module imports
if [ ! -f "$PROJECT_ROOT/mcp_web_app/__init__.py" ]; then
  echo "Creating mcp_web_app/__init__.py for better module imports"
  touch "$PROJECT_ROOT/mcp_web_app/__init__.py"
fi

# Ensure Python packages are available
if [ -d ".venv" ]; then
  echo "Activating virtual environment..."
  source .venv/bin/activate
fi

# Start the server from the project root
echo "Starting server..."
echo "PYTHONPATH=$PROJECT_ROOT python -m uvicorn mcp_web_app.main:app --reload --host 0.0.0.0 --port 8008"
PYTHONPATH=$PROJECT_ROOT python -m uvicorn mcp_web_app.main:app --reload --host 0.0.0.0 --port 8008 