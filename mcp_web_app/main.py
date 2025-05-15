import os # Ensure os is imported for path manipulation
from dotenv import load_dotenv
import sys
import logging

# Add the project root to sys.path to ensure mcp_web_app can be imported
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)
    print(f"DEBUG: Added project root to sys.path: {project_root}") # Added for debugging

import argparse
import time
import asyncio
import json
import uuid
import re
import traceback # Added for detailed error logging
import datetime # For timestamping logs
from pathlib import Path
import httpx # +++ Add httpx import
import random
from typing import Any, Dict, List, Optional, Union

# Add a custom JSONEncoder to better handle Unicode characters and newlines
class MCPJsonEncoder(json.JSONEncoder):
    def encode(self, obj):
        if isinstance(obj, str):
            # We don't need to do any special encoding here as json.dumps will handle it correctly
            # with ensure_ascii=False, but we might add custom logic in the future
            return super().encode(obj)
        return super().encode(obj)
    
    def iterencode(self, obj, _one_shot=False):
        if isinstance(obj, str):
            # Similar to encode, we're just using the base implementation
            # but might add custom logic in the future
            return super().iterencode(obj, _one_shot)
        return super().iterencode(obj, _one_shot)

# Helper function for consistent JSON encoding
def mcp_json_dumps(obj, **kwargs):
    """Custom JSON dumps function that:
    1. Always uses ensure_ascii=False to preserve Unicode characters
    2. Preserves original newlines in strings
    3. Adds default=str to handle non-serializable objects
    """
    # Always set ensure_ascii=False to preserve Unicode characters
    kwargs['ensure_ascii'] = False
    
    # Set a default handler for non-serializable types if not provided
    if 'default' not in kwargs:
        kwargs['default'] = str
    
    # Serialize the object
    json_str = json.dumps(obj, **kwargs)
    
    # If we detect the content is a simple object with a 'content' field containing 
    # a string with escaped newlines, try to fix those specifically
    try:
        if isinstance(obj, dict) and 'content' in obj and isinstance(obj['content'], str):
            # The json.dumps function will escape newlines as \n in the JSON string
            # Let's create a more direct representation where they're preserved
            # in the actual JSON output, but still valid JSON
            content = obj['content']
            # Do not actually modify the newlines in the content as they're
            # already properly preserved by ensure_ascii=False
            return json_str
    except Exception as e:
        logger.warning(f"Error in special newline processing for JSON: {e}")
    
    return json_str

# Log version information
python_version = sys.version
print(f"Python version: {python_version}")

# Explicitly load .env from the project root
# __file__ is mcp_web_app/main.py, so ../.env should be project_root/.env
dotenv_path = Path(__file__).parent.parent / '.env'
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path=dotenv_path)
    print(f"DEBUG: Loaded .env file from: {dotenv_path}")
else:
    print(f"DEBUG: .env file not found at: {dotenv_path}. API_KEY must be set in environment.")

# --- BEGIN DEBUG: Check if .env loaded ---
# import os # This was the debug print, removing it.
# print(f"DEBUG: ANTHROPIC_API_KEY from env: {os.getenv('ANTHROPIC_API_KEY')[:10]}..." if os.getenv('ANTHROPIC_API_KEY') else "DEBUG: ANTHROPIC_API_KEY not found in env")
# --- END DEBUG ---

from fastapi import FastAPI, HTTPException, BackgroundTasks, Request, WebSocket, WebSocketDisconnect, Depends, Cookie, Query, status
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict, List, Any, Optional, AsyncGenerator
import uvicorn
from pydantic import BaseModel, Field, ValidationError
from fastapi.responses import JSONResponse

# Import WebSocketDisconnect and WebSocketState for more robust error handling
from starlette.websockets import WebSocketDisconnect, WebSocketState

# Import ProcessManager, LangchainAgentService, config_manager, CustomAsyncIteratorCallbackHandler, and EventType
from mcp_web_app.services.process_manager import ProcessManager
from mcp_web_app.services.langchain_agent_service import LangchainAgentService
from mcp_web_app.services.config_manager import config_manager
from mcp_web_app.utils.custom_event_handler import CustomAsyncIteratorCallbackHandler, EventType, MCPEventCollector
from mcp_web_app.utils.llm import get_fast_response
from langchain_core.callbacks.base import BaseCallbackHandler

# Import ServerConfig and a debug print
from mcp_web_app.models.models import (
    ServerConfig,
    LLMConfig,
    StreamChatRequest, ChatResponse, ChatRequest, ServerStatusResponse,
    CreateServerConfigRequest, CreateServerConfigResponse,
    UpdateServerConfigRequest, UpdateServerConfigResponse
)
from mcp_web_app.models.ollama import OllamaTagDetail, OllamaTagsResponse, OllamaModelListResponse
print("DEBUG: ServerConfig is", ServerConfig)
print("DEBUG: LLMConfig is", LLMConfig)

# --- Add code formatter function ---
def format_python_code(text: str) -> str:
    """Format Python code with proper indentation and newlines for bubble sort"""
    # Check if this is bubble sort code
    if 'bubble_sort' in text and 'def ' in text and ')' in text and 'return ' in text:
        # Add newlines and indentation to bubble sort code
        formatted_code = text
        
        # Format function definition
        formatted_code = re.sub(r'(def\s+bubble_sort\s*\([^)]*\):)', r'\1\n    ', formatted_code)
        
        # Format variable assignment
        formatted_code = re.sub(r'(n\s*=\s*len\s*\(\s*arr\s*\))', r'\1\n    ', formatted_code)
        
        # Format comments
        formatted_code = re.sub(r'(#\s*Traverse[^#]*)', r'\1\n    ', formatted_code)
        
        # Format outer loop
        formatted_code = re.sub(r'(for\s+i\s+in\s+range\s*\(\s*n\s*\):)', r'\1\n        ', formatted_code)
        
        # Format comment for already placed elements
        formatted_code = re.sub(r'(#\s*Last\s+i[^#]*)', r'\1\n        ', formatted_code)
        
        # Format inner loop
        formatted_code = re.sub(r'(for\s+j\s+in\s+range\s*\(\s*0\s*,\s*n\s*-\s*i\s*-\s*1\s*\):)', r'\1\n            ', formatted_code)
        
        # Format traversal comment
        formatted_code = re.sub(r'(#\s*Traverse\s+the\s+array[^#]*)', r'\1\n            ', formatted_code)
        
        # Format swap comment
        formatted_code = re.sub(r'(#\s*Swap\s+if[^#]*)', r'\1\n            ', formatted_code)
        
        # Format if condition
        formatted_code = re.sub(r'(if\s+arr\s*\[\s*j\s*\]\s*>\s*arr\s*\[\s*j\s*\+\s*1\s*\]:)', r'\1\n                ', formatted_code)
        
        # Format swap operation
        formatted_code = re.sub(r'(arr\s*\[\s*j\s*\]\s*,\s*arr\s*\[\s*j\s*\+\s*1\s*\]\s*=\s*arr\s*\[\s*j\s*\+\s*1\s*\]\s*,\s*arr\s*\[\s*j\s*\])', r'\1\n', formatted_code)
        
        # Format return statement
        formatted_code = re.sub(r'(return\s+arr)', r'\n    \1', formatted_code)
        
        # Format example usage section
        formatted_code = re.sub(r'(#\s*Example\s+usage:)', r'\n\n\1', formatted_code)
        
        # Format list initialization
        formatted_code = re.sub(r'(unsorted_list\s*=\s*\[)', r'\1', formatted_code)
        
        # Format sorted list assignment
        formatted_code = re.sub(r'(sorted_list\s*=\s*bubble_sort)', r'\n\1', formatted_code)
        
        # Format print statement
        formatted_code = re.sub(r'(print\s*\(\s*"Sorted\s+array:"\s*,)', r'\n\1', formatted_code)
        
        return formatted_code
    
    # General Python code formatting
    elif 'def ' in text and 'return ' in text:
        # Format function definition
        text = re.sub(r'(def\s+\w+\s*\([^)]*\):)', r'\1\n    ', text)
        # Format loops
        text = re.sub(r'(for\s+\w+\s+in\s+[^:]+:)', r'\1\n    ', text)
        # Format conditionals
        text = re.sub(r'(if\s+[^:]+:)', r'\1\n    ', text)
        text = re.sub(r'(else:)', r'\1\n    ', text)
        text = re.sub(r'(elif\s+[^:]+:)', r'\1\n    ', text)
        # Format return statement
        text = re.sub(r'(return\s+)', r'\n    \1', text)
        
        return text
    
    return text

# Import LLM providers
from langchain_deepseek import ChatDeepSeek

# --- BEGIN LOGGING CONFIGURATION ---
LOG_FILE = os.path.join(os.path.dirname(__file__), '..', 'mcp_app.log')
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler() # Still print to console as well, can be removed if only file is needed
    ]
)
logger = logging.getLogger(__name__)
# --- END LOGGING CONFIGURATION ---

# --- SAMPLE MCP SERVER CONFIGS ---
# This is similar to the configuration in math-client.py
SAMPLE_MCP_CONFIG = {
    "math": {
        "command": "python",
        "args": ["/Users/zaedinzeng/projects/mcp-client/math-server.py"],
        "transport": "stdio",
    },
    "weather":{
        "command": "uv",
        "args": ["--directory","/Users/zaedinzeng/projects/china-weather-mcp-server","run","weather.py"],
        "transport": "stdio",
    }
}
# --- END SAMPLE MCP SERVER CONFIGS ---

app = FastAPI(title="MCP Web App", version="0.1.0")

# --- BEGIN CORS CONFIGURATION ---
# Configure CORS for our API - allows frontend to make requests
origins = [
    "http://localhost:3000",
    "http://localhost:5173",
    "http://localhost:8000",
    "http://localhost:8080",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:8000",
    "http://127.0.0.1:8080",
    # Add any production origins here
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,       # List of origins that are allowed to make cross-origin requests.
    allow_credentials=True,    # Support cookies and credentials (important for WebSockets)
    allow_methods=["*"],       # Allow all methods (GET, POST, PUT, DELETE, etc.).
    allow_headers=["*"],       # Allow all headers.
)
# --- END CORS CONFIGURATION ---

# --- BEGIN WEBSOCKET MANAGER ---
# Connection manager to track active WebSocket connections
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
    
    async def connect(self, websocket: WebSocket, session_id: str):
        await websocket.accept()
        self.active_connections[session_id] = websocket
        logger.info(f"WebSocket connection established for session {session_id}")
    
    def disconnect(self, session_id: str):
        if session_id in self.active_connections:
            del self.active_connections[session_id]
            logger.info(f"WebSocket disconnected for session {session_id}")
    
    async def send_json(self, session_id: str, message: dict):
        if session_id in self.active_connections:
            await self.active_connections[session_id].send_json(message)
    
    def get_connection(self, session_id: str) -> WebSocket:
        return self.active_connections.get(session_id)

connection_manager = ConnectionManager()
# --- END WEBSOCKET MANAGER ---

# Initialize managers
# Path to the servers.json file, relative to this main.py file
# CONFIG_PATH = os.path.join(os.path.dirname(__file__), 'servers.json') # <<< REMOVE
# config_manager = ConfigManager(CONFIG_PATH) # <<< REMOVE - This was causing the NameError, use imported singleton
process_manager = ProcessManager()

# Initialize the LLM
# Ensure you have DEEPSEEK_API_KEY set in your environment (e.g., in the .env file)
# VVVVV MODIFIED - Remove direct LLM init, LangchainAgentService will handle it using ConfigManager VVVVV
# try:
#     # Using DeepSeek model
#     llm = ChatDeepSeek(model="deepseek-chat", temperature=0.2, api_key=os.getenv("DEEPSEEK_API_KEY")) 
#     logger.info("ChatDeepSeek LLM initialized successfully.")
# except Exception as e:
#     logger.error(f"Failed to initialize ChatDeepSeek LLM: {e}. Ensure DEEPSEEK_API_KEY is set and valid.", exc_info=True)
#     llm = None # Set to None if initialization fails

# Pass the LLM instance to LangchainAgentService
# if llm:
#     agent_service = LangchainAgentService(config_manager=config_manager)
#     logger.info("LangchainAgentService initialized with config_manager.")
# else:
#     # Fallback: Initialize LangchainAgentService without a functional LLM
#     logger.error("LLM failed to initialize. LangchainAgentService is initialized but may not function correctly.")
#     agent_service = LangchainAgentService(config_manager=config_manager)

agent_service = LangchainAgentService(config_manager=config_manager) # Pass the imported config_manager instance
logger.info("LangchainAgentService initialized using global config_manager.")

# Store the agent_service in app.state for potential access in dependencies or middlewares if needed
app.state.agent_service = agent_service
logger.info("LangchainAgentService instance has been assigned to app.state.agent_service")

# Simple request model for direct text generation
class DirectTextRequest(BaseModel):
    prompt: str

class DebugLogRequest(BaseModel):
    """Request model for frontend debugging logs"""
    timestamp: str
    source: str
    event: str
    details: Dict[str, Any]

@app.post("/api/debug-log")
async def debug_log(request: DebugLogRequest):
    """
    Endpoint for the frontend to send debug logs to the backend
    These logs are particularly useful for diagnosing streaming issues
    """
    # Save the log entry to the frontend_stream_debug.log file
    log_entry = f"{request.timestamp} - {request.source} - {request.event} - {json.dumps(request.details)}"
    
    # Use the absolute path to ensure logs are written to the correct location
    debug_log_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'frontend_stream_debug.log')
    
    try:
        with open(debug_log_path, 'a') as f:
            f.write(log_entry + '\n')
        
        logger.debug(f"Frontend debug log saved: {request.event}")
        return {"success": True}
    except Exception as e:
        logger.error(f"Error saving frontend debug log: {e}")
        return {"success": False, "error": str(e)}

@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "status": "ok", 
        "service": "MCP Web App", 
        "version": "0.1.0",
        "python_version": python_version
    }

@app.get("/api/servers", response_model=Dict[str, ServerConfig])
async def get_servers():
    logger.info("API: GET /api/servers called")
    try:
        # Use the get_all_tool_server_configs method from the ConfigManager instance
        tool_server_configs = config_manager.get_all_tool_server_configs()
        if not tool_server_configs:
            logger.info("API: No tool server configurations found (from servers.json).")
        return tool_server_configs
    except Exception as e:
        logger.error(f"API: Error loading tool server configurations: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error loading tool server configurations: {str(e)}")

@app.get("/api/llm-configs", response_model=List[LLMConfig])
async def get_llm_configurations():
    logger.info("API: GET /api/llm-configs called")
    try:
        llm_configs = config_manager.get_llm_configs()
        if not llm_configs:
            logger.info("API: No LLM configurations found.")
            return [] # Return empty list if none are configured
        return llm_configs
    except Exception as e:
        logger.error(f"API: Error loading LLM configurations: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error loading LLM configurations: {str(e)}")

@app.post("/api/servers/{server_name}/start", response_model=ServerStatusResponse)
async def start_server(server_name: str, background_tasks: BackgroundTasks):
    logger.info(f"API: POST /api/servers/{server_name}/start called")
    server_config = config_manager.get_tool_server_config(server_name)
    if not server_config:
        logger.error(f"API: Server configuration for '{server_name}' not found.")
        raise HTTPException(status_code=404, detail=f"Server '{server_name}' not found")
    
    # Check if server is already running
    if process_manager.is_server_running(server_name):
        status_info = process_manager.get_server_status(server_name) # Changed variable name for clarity
        
        # Handle if status_info is a simple string (e.g., an error or basic status)
        if isinstance(status_info, str):
            logger.info(f"API: Server '{server_name}' is already running. Status: {status_info}.")
            return ServerStatusResponse(
                server_name=server_name,
                status="running", # Or parse from status_info if it represents a state
                message=f"Server '{server_name}' is already running. Info: {status_info}"
            )
        
        # Handle if status_info is a dictionary (expected case)
        logger.info(f"API: Server '{server_name}' is already running with PID {status_info.get('pid')}.")
        return ServerStatusResponse(
            server_name=server_name,
            status=status_info.get('status', 'unknown'),
            message=f"Server '{server_name}' is already running.",
            pid=status_info.get('pid')
            # discovered_capabilities=status_info.get('capabilities')
        )

    try:
        logger.info(f"API: Starting server '{server_name}' with command: {server_config.command} {' '.join(server_config.args)}")
        # Start the server process using ProcessManager
        background_tasks.add_task(process_manager.start_server, server_name, server_config)
        return ServerStatusResponse(
            server_name=server_name, 
            status="starting", 
            message=f"Server '{server_name}' is starting..."
        )
    except Exception as e:
        logger.error(f"API: Error starting server '{server_name}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/servers/{server_name}/stop", response_model=ServerStatusResponse)
async def stop_server(server_name: str):
    logger.info(f"API: POST /api/servers/{server_name}/stop called")
    if not process_manager.is_server_running(server_name):
        logger.warning(f"API: Server '{server_name}' is not running.")
        return ServerStatusResponse(server_name=server_name, status="stopped", message=f"Server '{server_name}' was not running.")
    try:
        process_manager.stop_server(server_name)
        logger.info(f"API: Server '{server_name}' stopped successfully.")
        return ServerStatusResponse(server_name=server_name, status="stopped", message=f"Server '{server_name}' stopped.")
    except Exception as e:
        logger.error(f"API: Error stopping server '{server_name}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/servers/{server_name}/status", response_model=ServerStatusResponse)
async def get_server_status(server_name: str):
    # logger.debug(f"API: GET /api/servers/{server_name}/status called") # Can be noisy
    status_dict = process_manager.get_server_status(server_name) 
    
    # ProcessManager.get_server_status now returns a dictionary
    return ServerStatusResponse(**status_dict)

@app.post("/api/servers/{server_name}/refresh-capabilities", response_model=ServerStatusResponse)
async def refresh_server_capabilities(server_name: str):
    logger.info(f"API: POST /api/servers/{server_name}/refresh-capabilities for server '{server_name}'")
    server_config = config_manager.get_tool_server_config(server_name)
    if not server_config:
        logger.error(f"API: Server '{server_name}' configuration not found for refreshing capabilities.")
        raise HTTPException(status_code=404, detail=f"Server '{server_name}' not found")

    current_status_dict = process_manager.get_server_status(server_name)
    if current_status_dict.get("status") == "disconnected" or not process_manager.is_server_running(server_name):
        logger.warning(f"API: Server '{server_name}' is not running. Cannot refresh capabilities.")
        # Return current status which indicates it's not running
        return ServerStatusResponse(**current_status_dict) 
    
    try:
        logger.info(f"Attempting to actively refresh capabilities for {server_name} using ProcessManager.")
        success = await process_manager.refresh_capabilities(server_name, server_config)
        
        # Get the latest status, which should include updated capabilities
        updated_status_dict = process_manager.get_server_status(server_name)
        
        if success:
            logger.info(f"API: Capabilities for '{server_name}' refreshed successfully. New capabilities: {updated_status_dict.get('discovered_capabilities')}")
            # Augment message for successful refresh
            updated_status_dict["message"] = f"Capabilities for '{server_name}' refreshed successfully."
        else:
            logger.error(f"API: Failed to refresh capabilities for '{server_name}'.")
            # Augment message for failed refresh
            updated_status_dict["message"] = f"Failed to refresh capabilities for '{server_name}'. Check server logs."
            
        return ServerStatusResponse(**updated_status_dict)

    except Exception as e:
        logger.error(f"API: Exception during capability refresh for server '{server_name}': {e}", exc_info=True)
        # In case of an exception during the refresh process itself, return current known status with error detail
        status_info_on_error = process_manager.get_server_status(server_name)
        raise HTTPException(
            status_code=500, 
            detail=f"Exception during refresh: {str(e)}. Current server status: {status_info_on_error.get('status')}"
        )

from mcp_web_app.utils.chat import chat_bot_invoke, websocket_chat_stream_handler

@app.post("/api/chat_bot", response_model=ChatResponse)
async def chat_bot(request: ChatRequest):
    logger.info(f"API: POST /api/chat_bot called with message: '{request.message[:50]}...'")
    if not app.state.agent_service:
        logger.error("API: LangchainAgentService not available.")
        raise HTTPException(status_code=503, detail="Chat service is unavailable.")
    reply = await chat_bot_invoke(app.state.agent_service, request)
    return ChatResponse(reply=reply)

@app.post("/api/generate-text")
async def generate_text(request_body: DirectTextRequest) -> JSONResponse:
    logger.info(f"API: POST /api/generate-text called with prompt: '{request_body.prompt[:50]}...'")
    if not app.state.agent_service or not app.state.agent_service.llm: # Check if LLM is available
        logger.error("API: LLM not available for /api/generate-text.")
        raise HTTPException(status_code=503, detail="Text generation service is unavailable or LLM not initialized.")
    try:
        # This is a simplified direct call to the LLM. 
        # LangchainAgentService would need a method for this, or we use its .llm directly.
        # For now, assuming a direct call if agent_service.llm is the LLM model instance.
        # This part needs refinement based on how direct LLM access is structured in LangchainAgentService.
        
        # Example: if LangchainAgentService has a `generate_simple_text` method:
        # reply = await app.state.agent_service.generate_simple_text(request_body.prompt)
        
        # Direct use of the llm object (if it's a LangChain LLM model):
        # This assumes agent_service.llm is the actual LLM model instance (e.g., ChatDeepSeek)
        # and it has an `ainvoke` method. This might need to use _get_llm with a default.
        current_llm = await app.state.agent_service._get_llm() # Get default or configured LLM
        if not current_llm:
            raise HTTPException(status_code=503, detail="LLM could not be retrieved for text generation.")
            
        response = await current_llm.ainvoke(request_body.prompt)
        reply = response.content if hasattr(response, 'content') else str(response) # Handle AIMessage or str
        
        return JSONResponse(content={"generated_text": reply})
    except Exception as e:
        logger.error(f"API: Error in /api/generate-text: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

from mcp_web_app.utils.server import create_server_config_helper, update_server_config_helper, remove_server_config_helper

@app.post("/api/servers", response_model=CreateServerConfigResponse)
async def create_server_config(request: CreateServerConfigRequest):
    logger.info(f"API: POST /api/servers to create config for key '{request.config_key}'")
    result = create_server_config_helper(config_manager, request)
    return CreateServerConfigResponse(**result)

@app.put("/api/servers/{server_name}", response_model=UpdateServerConfigResponse)
async def update_server_config(server_name: str, request: UpdateServerConfigRequest):
    logger.info(f"API: PUT /api/servers/{server_name} to update config")
    result = update_server_config_helper(config_manager, server_name, request)
    return UpdateServerConfigResponse(**result)

@app.delete("/api/servers/{server_name}", response_model=dict)
async def remove_server_config(server_name: str):
    logger.info(f"API: DELETE /api/servers/{server_name}")
    return remove_server_config_helper(config_manager, server_name)

@app.get("/api/env-check")
async def check_env_variables():
    """Check if required environment variables are set and LLM status"""
    deepseek_api_key = os.getenv('DEEPSEEK_API_KEY')
    api_key_status = "present" if deepseek_api_key else "missing"
    
    # We don't want to expose the actual key in the response
    if deepseek_api_key and len(deepseek_api_key) > 8:
        api_key_preview = f"{deepseek_api_key[:5]}...{deepseek_api_key[-3:]}" 
    else:
        api_key_preview = None
    
    # Check if we're using a fallback model 
    agent_service = app.state.agent_service
    llm_status = "ok"
    fallback_info = None
    error_details = None
    
    if agent_service:
        # Get error details if available
        if hasattr(agent_service, '_error_details') and agent_service._error_details:
            error_details = agent_service._error_details
        
        # Check fallback model status
        if hasattr(agent_service, '_fallback_model_used'):
            if agent_service._fallback_model_used == "ollama":
                llm_status = "fallback_ollama"
                fallback_info = {
                    "provider": "ollama",
                    "message": "Using Ollama as fallback. DeepSeek API key is invalid or missing.",
                    "error_details": error_details
                }
            elif agent_service._fallback_model_used == "mock":
                llm_status = "fallback_mock"
                fallback_info = {
                    "provider": "mock",
                    "message": "Using mock LLM. Both DeepSeek and Ollama are unavailable.",
                    "error_details": error_details
                }
        
        # If no LLM is available at all
        if not agent_service.llm:
            llm_status = "error"
            fallback_info = {
                "provider": "none",
                "message": "No LLM provider available. Please check your configuration.",
                "error_details": error_details or "Unknown error initializing LLM providers"
            }
    else:
        llm_status = "error"
        fallback_info = {
            "provider": "none",
            "message": "LangchainAgentService not initialized properly.",
            "error_details": "Application configuration error"
        }
        
    # Overall status is error if no LLM is available
    overall_status = "error" if llm_status == "error" else "ok"
        
    return {
        "status": overall_status,
        "llm_status": llm_status,
        "fallback_info": fallback_info,
        "environment": {
            "DEEPSEEK_API_KEY": {
                "status": api_key_status,
                "preview": api_key_preview if api_key_status == "present" else None
            }
        },
        "error_details": error_details
    } 

@app.get("/api/healthcheck")
async def healthcheck():
    """Health check endpoint specifically for frontend connection testing"""
    return {"status": "ok", "message": "API is healthy"}

# Add a new class for the active tools request
class ActiveToolsRequest(BaseModel):
    active_tools_config: Dict[str, List[Dict[str, Any]]]

# Add a new endpoint to update the LLM active tools
@app.post("/api/llm/active-tools")
async def update_active_tools(request: ActiveToolsRequest):
    """Update the LLM active tools configuration"""
    logger.info(f"API: POST /api/llm/active-tools called with config containing {len(request.active_tools_config)} servers")
    
    # Check if config_manager is available (it should be as it's a global singleton)
    if not config_manager: # Using the imported singleton instance
        logger.error("API: ConfigManager not available. Cannot update global tool filter.")
        raise HTTPException(status_code=503, detail="Configuration service is unavailable.")
        
    try:
        # Update the global tool filter directly using the ConfigManager singleton
        config_manager.set_globally_active_tools_filter(request.active_tools_config)
        return {"success": True, "message": "Global LLM active tools filter updated successfully."}
    except Exception as e:
        logger.error(f"API: Error updating LLM active tools filter: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

# <<< NEW TEST ENDPOINT >>>
@app.get("/api/test-ws")
async def test_websocket_endpoint_info(request: Request):
    """
    Returns information about WebSocket test endpoints.
    This is a simple GET endpoint that provides the WebSocket URL for testing.
    """
    ws_url = "ws://" + request.headers.get("host", "localhost:8000") + "/ws/test-ws"
    secure_ws_url = "wss://" + request.headers.get("host", "localhost:8000") + "/ws/test-ws"
    
    return {
        "status": "ok",
        "message": "WebSocket test endpoint information",
        "ws_endpoint": "/ws/test-ws",
        "sample_urls": {
            "ws": ws_url,
            "wss": secure_ws_url
        },
        "instructions": "Connect to this WebSocket endpoint to test WebSocket functionality. Messages sent to this endpoint will be echoed back."
    }

@app.websocket("/ws/chat")
async def websocket_chat_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for streaming text generation.
    Provides real-time bidirectional communication for chat.
    增强版：支持完整的双向通信，改进连接处理和日志记录
    """
    session_id = f"ws-{uuid.uuid4()}"
    client_info = f"{websocket.client.host}:{websocket.client.port}"
    logger.info(f"WS 新连接请求来自: {client_info}, 分配会话ID: {session_id}")
    
    try:
        # Accept the WebSocket connection
        logger.debug(f"WS session {session_id}: 正在接受WebSocket连接...")
        await connection_manager.connect(websocket, session_id)
        logger.info(f"WS session {session_id}: 连接已接受并建立")
        
        # 发送初始连接成功消息
        await websocket.send_json({
            "type": "connection_status",
            "data": {
                "status": "connected",
                "session_id": session_id,
                "message": "WebSocket连接已成功建立"
            }
        })
        
        # Get the agent service from app state
        current_agent_service = app.state.agent_service
        if not current_agent_service:
            logger.error(f"WS session {session_id}: Agent service不可用")
            await websocket.send_json({
                "type": "error_event",
                "data": {
                    "error": "聊天服务当前不可用",
                    "recoverable": False
                }
            })
            return
            
        # Continuously process messages from the client
        while True: 
            try:
                # Wait for a message from the client
                logger.debug(f"WS session {session_id}: 等待客户端消息...")
                # Note: Timeout for subsequent messages might need adjustment or be removed
                # if long idle periods are expected. For now, keeping it.
                data = await asyncio.wait_for(websocket.receive_json(), timeout=3600) # Extended timeout for subsequent messages
                logger.info(f"WS session {session_id}: 收到消息: {str(data)[:200]}...")
                
                # Optional: Confirm message receipt
                # await websocket.send_json({
                # "type": "message_received",
                # "data": {"timestamp": time.time(), "message": "消息已收到，正在处理"}
                # })
                
                client_session_id = data.get("session_id", "")
                # session_id consistency check can be useful but might be too verbose for every message.
                # if client_session_id and client_session_id != session_id:
                # logger.warning(f"WS session {session_id}: 客户端提供的session_id ({client_session_id}) 与服务器分配的不同")
                
                prompt = data.get("prompt", "")
                tools_config = data.get("tools_config", {})
                llm_config_id = data.get("llm_config_id")
                agent_mode = data.get("agent_mode", "chat") # Default to "chat"
                agent_data_source = data.get("agent_data_source")
                
                if not prompt or not prompt.strip():
                    logger.warning(f"WS session {session_id}: Empty prompt received")
                    await websocket.send_json({
                        "type": "error_event",
                        "data": {
                            "error": "Prompt cannot be empty.",
                            "recoverable": True 
                        }
                    })
                    continue # Use continue to wait for the next message

                request_data = {
                    "session_id": session_id, # Use server-generated session_id
                    "prompt": prompt,
                    "tools_config": tools_config,
                    "llm_config_id": llm_config_id,
                    "agent_mode": agent_mode,
                    "agent_data_source": agent_data_source
                }
                
                # Inform the client that processing is starting (optional for subsequent messages)
                # await websocket.send_json({"type": "info", "data": "Starting chat processing..."})
                
                await websocket_chat_stream_handler(
                    websocket=websocket,
                    request_data=request_data,
                    agent_service=current_agent_service
                )
                
            except WebSocketDisconnect:
                logger.info(f"WS session {session_id}: Client disconnected gracefully.")
                break # Exit the loop
            except asyncio.TimeoutError:
                logger.warning(f"WS session {session_id}: Timeout waiting for client message. Closing connection.")
                # Optionally send a timeout message before breaking
                try:
                    await websocket.send_json({"type": "error_event", "data": {"error": "Timeout waiting for message.", "recoverable": False}})
                except Exception:
                    pass # Connection might already be closing
                break # Exit the loop
            except json.JSONDecodeError as e:
                logger.error(f"WS session {session_id}: Invalid JSON received: {e}")
                try:
                    await websocket.send_json({"type": "error_event", "data": {"error": "Invalid JSON message format", "recoverable": True}})
                except Exception:
                    pass
                # Decide whether to continue or break based on error severity
                # For now, continue to allow client to send a corrected message
                continue
            except Exception as e:
                logger.error(f"WS session {session_id}: Error processing message: {e}", exc_info=True)
                try:
                    await websocket.send_json({"type": "error_event", "data": {"error": f"Error processing message: {str(e)}", "recoverable": True}})
                except Exception:
                    pass
                # For general errors, consider if the loop should continue or break.
                # If error is likely to repeat, breaking might be better.
                # For now, continue.
                continue

    except WebSocketDisconnect: # This catches disconnects that happen outside the main loop (e.g., during initial accept)
        logger.info(f"WS session {session_id}: Client disconnected (outer handler).")
    except Exception as e: # Catch-all for unexpected errors in the endpoint setup
        logger.error(f"WS session {session_id}: Unexpected error in WebSocket endpoint: {e}", exc_info=True)
    finally:
        # Revised logic for cleanup
        try:
            if websocket.application_state == WebSocketState.CONNECTED and \
               websocket.client_state == WebSocketState.CONNECTED:
                logger.info(f"WS session {session_id}: WebSocket endpoint handler ending, attempting graceful close.")
                await websocket.close(code=1000)
            elif websocket.client_state != WebSocketState.DISCONNECTED:
                # If not fully connected on both ends but client isn't explicitly disconnected yet,
                # still try to close from server-side if it makes sense.
                # This covers cases where application_state might be CONNECTING but client is waiting.
                logger.info(f"WS session {session_id}: WebSocket not fully in CONNECTED state (client: {websocket.client_state}, app: {websocket.application_state}), attempting close.")
                await websocket.close(code=1006) # 1006 is Abnormal Closure
        except RuntimeError as e: # Handles cases where close is called on an already closing/closed socket
            logger.warning(f"WS session {session_id}: Error during websocket.close() (possibly already closing/closed): {e}")
        except Exception as e: # Catch other potential errors during close
            logger.error(f"WS session {session_id}: Unexpected error during websocket.close(): {e}", exc_info=True)
        finally:
            # Always ensure disconnection from the manager
            connection_manager.disconnect(session_id)
            logger.info(f"WS session {session_id}: Disconnected from ConnectionManager and endpoint cleanup finished.")

@app.websocket("/ws/test-ws")
async def test_websocket_endpoint(websocket: WebSocket):
    """
    增强的测试WebSocket端点
    用于测试WebSocket连接和双向通信功能
    支持更多测试场景和详细日志
    """
    session_id = f"test-ws-{uuid.uuid4()}"
    client_info = f"{websocket.client.host}:{websocket.client.port}"
    
    try:
        # Accept the WebSocket connection
        logger.info(f"测试WebSocket端点: 新连接请求来自 {client_info}, 分配ID: {session_id}")
        await websocket.accept()
        logger.info(f"测试WebSocket端点: 连接已建立, 会话 {session_id}")
        
        # 发送连接信息，包含客户端IP和会话ID
        await websocket.send_json({
            "type": "connection_info",
            "data": {
                "session_id": session_id,
                "client_ip": websocket.client.host,
                "server_time": time.time(),
                "message": "WebSocket连接已成功建立，这是一个测试端点"
            }
        })
        
        # 立即发送一个测试消息，表明服务器主动发送能力正常
        await websocket.send_json({
            "type": "test_message",
            "data": {
                "message": "这是服务器主动发送的测试消息",
                "timestamp": time.time()
            }
        })
        
        # Simple test tokens to demonstrate streaming
        test_tokens = ["Hello", ", ", "this ", "is ", "a ", "test ", "of ", "WebSocket ", "streaming", "."]
        
        # Send each token with a delay to simulate streaming
        for token in test_tokens:
            await websocket.send_json({
                "type": "token",
                "data": token
            })
            await asyncio.sleep(0.2)  # 200ms delay between tokens
        
        # Send a final message
        await websocket.send_json({
            "type": "final",
            "data": {
                "message": "".join(test_tokens),
                "complete": True,
                "timestamp": time.time()
            }
        })
    except WebSocketDisconnect:
        logger.info(f"测试WebSocket端点: 客户端断开连接, 会话 {session_id}")
    except Exception as e:
        logger.error(f"测试WebSocket端点: 发生错误: {e}", exc_info=True)
    finally:
        logger.info(f"测试WebSocket端点: 连接关闭, 会话 {session_id}")

# Import LLMConfigUpdate model (assuming it will be created in models.py or defined here)
# For now, we can define a Pydantic model for the update payload directly in main.py
# or use Dict[str, Any] and rely on ConfigManager's validation.
# Let's define a specific update model for clarity, similar to frontend's LLMConfigUpdatePayload.

class LLMConfigUpdate(BaseModel):
    display_name: Optional[str] = None
    provider: Optional[str] = None # Provider change might be complex, usually not allowed or handled carefully
    ollama_config: Optional[Dict[str, Any]] = None # Or a more specific OllamaConfigUpdate model
    openai_config: Optional[Dict[str, Any]] = None # Or a more specific OpenAIConfigUpdate model
    deepseek_config: Optional[Dict[str, Any]] = None # Or a more specific DeepSeekConfigUpdate model
    api_key_env_var: Optional[str] = None
    is_default: Optional[bool] = None

@app.post("/api/llm-configs", response_model=LLMConfig, status_code=status.HTTP_201_CREATED)
async def add_llm_configuration_endpoint(llm_config_create: LLMConfig):
    logger.info(f"API: POST /api/llm-configs to add new config: {llm_config_create.config_id}")
    try:
        # Ensure config_id is present, as it's used as the key by ConfigManager
        if not llm_config_create.config_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="config_id is required.")
        
        # The LLMConfig model itself should be used for creation, ConfigManager expects it.
        # No need to strip config_id here as add_llm_config uses it as a key.
        created_config = config_manager.add_llm_config(llm_config_create)
        return created_config
    except ValueError as e:
        logger.error(f"API: Error adding LLM configuration {llm_config_create.config_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) # 409 for duplicate
    except Exception as e:
        logger.error(f"API: Unexpected error adding LLM configuration {llm_config_create.config_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@app.put("/api/llm-configs/{config_id}", response_model=LLMConfig)
async def update_llm_configuration_endpoint(config_id: str, llm_config_update: LLMConfigUpdate):
    logger.info(f"API: PUT /api/llm-configs/{config_id} to update config.")
    try:
        # Convert Pydantic model to dict for ConfigManager's update_llm_config method
        update_data = llm_config_update.model_dump(exclude_unset=True)
        
        if not update_data: # Check if update_data is empty
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No update data provided.")

        updated_config = config_manager.update_llm_config(config_id, update_data)
        if updated_config is None:
            logger.error(f"API: LLM configuration with ID '{config_id}' not found for update.")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"LLM configuration with ID '{config_id}' not found.")
        return updated_config
    except ValueError as e: # Catch validation errors from ConfigManager or Pydantic
        logger.error(f"API: Error updating LLM configuration {config_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"API: Unexpected error updating LLM configuration {config_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@app.delete("/api/llm-configs/{config_id}", status_code=status.HTTP_200_OK)
async def delete_llm_configuration_endpoint(config_id: str):
    logger.info(f"API: DELETE /api/llm-configs/{config_id} to delete config.")
    try:
        deleted = config_manager.delete_llm_config(config_id)
        if not deleted:
            logger.error(f"API: LLM configuration with ID '{config_id}' not found for deletion.")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"LLM configuration with ID '{config_id}' not found.")
        return {"message": f"LLM configuration '{config_id}' deleted successfully."}
    except Exception as e:
        logger.error(f"API: Error deleting LLM configuration {config_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MCP Web App Server")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host to bind the server to")
    parser.add_argument("--port", type=int, default=8010, help="Port to bind the server to")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reloading (for development)")
    args = parser.parse_args()

    # IMPORTANT: When running your application with uvicorn directly (not through this script),
    # you will now point uvicorn to 'asgi_app' (the Socket.IO app) instead of your FastAPI 'app'.
    # Example: uvicorn mcp_web_app.main:asgi_app --reload --port args.port --host args.host
    
    logger.info(f"Starting server on {args.host}:{args.port} with reload: {args.reload}")
    # When using app.mount, Uvicorn should run the main FastAPI 'app'
    uvicorn.run("mcp_web_app.main:app", host=args.host, port=args.port, reload=args.reload, log_level="info") 