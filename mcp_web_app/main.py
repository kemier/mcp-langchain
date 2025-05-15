import os # Ensure os is imported for path manipulation
from dotenv import load_dotenv
import sys
import logging
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
from fastapi.responses import JSONResponse, StreamingResponse

# Import WebSocketDisconnect and WebSocketState for more robust error handling
from starlette.websockets import WebSocketDisconnect, WebSocketState

# Import ProcessManager, LangchainAgentService, config_manager, CustomAsyncIteratorCallbackHandler, and EventType
from mcp_web_app.services.process_manager import ProcessManager
from mcp_web_app.services.langchain_agent_service import LangchainAgentService
from mcp_web_app.services.config_manager import config_manager, PREDEFINED_ERICAI_MODEL_IDENTIFIERS
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
from langchain_openai import ChatOpenAI # Used for EricAI integration

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
    
    if not app.state.agent_service:
        logger.error("API: LangchainAgentService not available.")
        raise HTTPException(status_code=503, detail="LLM service is unavailable.")
        
    try:
        # Update the active tools configuration in the agent service
        await app.state.agent_service.update_globally_active_tools(request.active_tools_config)
        return {"success": True, "message": "LLM active tools updated successfully."}
    except Exception as e:
        logger.error(f"API: Error updating LLM active tools: {e}", exc_info=True)
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
            
        # Continuously process messages from the client - REMOVED while True
        # while True: # REMOVED
        try:
            # Wait for a message from the client with a timeout
            logger.debug(f"WS session {session_id}: 等待客户端消息...")
            data = await asyncio.wait_for(websocket.receive_json(), timeout=120) # Increased timeout for first message
            logger.info(f"WS session {session_id}: 收到消息: {str(data)[:200]}...")
            
            # 确认收到消息
            await websocket.send_json({
                "type": "message_received",
                "data": {
                    "timestamp": time.time(),
                    "message": "消息已收到，正在处理"
                }
            })
            
            # Extract parameters from the request
            client_session_id = data.get("session_id", "")
            if client_session_id and client_session_id != session_id:
                logger.warning(f"WS session {session_id}: 客户端提供的session_id ({client_session_id}) 与服务器分配的不同")
                
            prompt = data.get("prompt", "")
            tools_config = data.get("tools_config", {})
            llm_config_id = data.get("llm_config_id")
            agent_mode = data.get("agent_mode", "chat")
            agent_data_source = data.get("agent_data_source")
            
            # Validate the prompt
            if not prompt or not prompt.strip():
                logger.warning(f"WS session {session_id}: Empty prompt received")
                await websocket.send_json({
                    "type": "error_event",
                    "data": {
                        "error": "Prompt cannot be empty.",
                        "recoverable": True
                    }
                })
                return
                
            # Create a request object to pass to the WebSocket handler
            request_data = {
                "session_id": session_id,
                "prompt": prompt,
                "tools_config": tools_config,
                "llm_config_id": llm_config_id,
                "agent_mode": agent_mode,
                "agent_data_source": agent_data_source
            }
            
            # Inform the client that processing is starting
            await websocket.send_json({
                "type": "info",
                "data": "Starting chat processing..."
            })
            
            # Process the chat and stream results
            await websocket_chat_stream_handler(
                websocket=websocket,
                request_data=request_data,
                agent_service=current_agent_service
            )
            
        except WebSocketDisconnect:
            logger.info(f"WS session {session_id}: Client disconnected during message processing")
            # break # REMOVED break, function will now exit naturally
        except json.JSONDecodeError as e:
            logger.error(f"WS session {session_id}: Invalid JSON received: {e}")
            # Attempt to send error before closing
            try:
                await websocket.send_json({
                    "type": "error_event",
                    "data": {
                        "error": "Invalid JSON message format",
                        "recoverable": True
                    }
                })
            except Exception:
                logger.warning(f"WS session {session_id}: Failed to send JSON error message, connection likely closed.")
        except asyncio.TimeoutError:
             logger.warning(f"WS session {session_id}: Timeout waiting for initial client message.")
             try:
                 await websocket.send_json({
                     "type": "error_event",
                     "data": {
                         "error": "Timeout waiting for initial message.",
                         "recoverable": False
                     }
                 })
             except Exception:
                 logger.warning(f"WS session {session_id}: Failed to send timeout error message, connection likely closed.")
        except Exception as e:
            logger.error(f"WS session {session_id}: Error processing message: {e}", exc_info=True)
            try:
                await websocket.send_json({
                    "type": "error_event",
                    "data": {
                        "error": f"Error processing message: {str(e)}",
                        "recoverable": True # Or False depending on error? Maybe keep True for now
                    }
                })
            except Exception:
                logger.warning(f"WS session {session_id}: Failed to send generic error message, connection likely closed.")
                # break # REMOVED break

    except WebSocketDisconnect:
        logger.info(f"WS session {session_id}: Client disconnected during connection or processing.")
    except Exception as e:
        logger.error(f"WS session {session_id}: Unexpected error in WebSocket endpoint: {e}", exc_info=True)
    finally:
        # Clean up the connection
        connection_manager.disconnect(session_id)

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

# --- Configuration Loading ---
LLM_CONFIG_FILE = "llm_configs.json"

def load_all_llm_configs() -> list:
    try:
        with open(LLM_CONFIG_FILE, 'r') as f:
            configs = json.load(f)
        if not isinstance(configs, list):
            print(f"Warning: {LLM_CONFIG_FILE} does not contain a list.")
            return []
        return configs
    except FileNotFoundError:
        print(f"Warning: {LLM_CONFIG_FILE} not found.")
        return []
    except json.JSONDecodeError:
        print(f"Warning: Error decoding {LLM_CONFIG_FILE}.")
        return []

# --- FastAPI App and CORS ---
app = FastAPI(title="MCP LLM API - Modular Config & Streaming")

# CORS Middleware (ensure it's correctly set up)
origins = [ "http://localhost:5173"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Pydantic Models for EricAI Chat ---
class EricAIChatRequest(BaseModel):
    message: str
    config_id: str = Field(..., description="Unique config_id from llm_configs.json")

class EricAIModelInfo(BaseModel): # For /ericai_models endpoint
    config_id: str
    display_name: str

class EricAIModelsResponse(BaseModel): # For /ericai_models endpoint
    models: list[EricAIModelInfo]

# Updated import from config_manager
from .config_manager import (
    llm_config_router,
    LLMConfigManager,
    LLMConfig as LLMConfigModel,
)

# --- Event Handlers ---
@app.on_event("startup")
async def on_app_startup():
    """Tasks to run on application startup."""
    print("Application starting up...")
    await config_manager.ensure_default_ericai_configs_on_startup()
    print("Default EricAI config check complete.")

# Include the LLM config CRUD router
app.include_router(llm_config_router)

# --- New Endpoint for Predefined EricAI Models ---
class EricAIProviderModelsResponse(BaseModel): # Pydantic model for the response
    models: List[str]

@app.get("/ericai_provider_models", response_model=EricAIProviderModelsResponse, tags=["EricAI Chat Support"])
async def get_predefined_ericai_model_names():
    """Returns the list of predefined EricAI model identifiers for config forms."""
    return EricAIProviderModelsResponse(models=PREDEFINED_ERICAI_MODEL_IDENTIFIERS)

# GET /ericai_models (List of configured EricAI services for chat dropdown - no change)
@app.get("/ericai_models", response_model=EricAIModelsResponse, tags=["EricAI Chat"])
async def get_ericai_display_models_from_manager():
    all_configs = await llm_config_manager.get_all_llm_configs()
    ericai_configs_list = [
        EricAIModelInfo(config_id=cfg.config_id, display_name=cfg.display_name)
        for cfg in all_configs if cfg.provider == "ericai"
    ]
    return EricAIModelsResponse(models=ericai_configs_list)

# POST /ericai_chat (Streaming chat - no change in its core logic, still uses configured model_name_or_path)
@app.post("/ericai_chat", tags=["EricAI Chat"])
async def ericai_streaming_chat_from_manager(request: EricAIChatRequest):
    # ... (This endpoint's internal logic remains the same as the previous version)
    # It will use the `model_name_or_path` that was selected from the dropdown
    # and saved into the specific LLMConfig via the /llm_configs endpoints.
    try:
        model_config_pydantic = await llm_config_manager.get_llm_config_by_id(request.config_id)
        if not model_config_pydantic: raise HTTPException(status_code=404, detail=f"Config ID '{request.config_id}' not found.")
        if model_config_pydantic.provider != "ericai": raise HTTPException(status_code=400, detail=f"Config ID '{request.config_id}' not 'ericai'.")

        model_name = model_config_pydantic.model_name_or_path
        base_url = model_config_pydantic.base_url
        temperature = model_config_pydantic.temperature
        max_tokens = model_config_pydantic.max_tokens
        api_key = model_config_pydantic.api_key

        if not model_name: raise HTTPException(status_code=500, detail=f"Config '{request.config_id}': 'model_name_or_path' missing.")
        if not base_url: raise HTTPException(status_code=500, detail=f"Config '{request.config_id}': 'base_url' missing.")
        if not api_key: raise HTTPException(status_code=500, detail=f"Config '{request.config_id}': 'api_key' missing.")

        llm = ChatOpenAI( model=model_name, temperature=temperature if temperature is not None else 0.7, max_tokens=max_tokens if max_tokens is not None and max_tokens > 0 else None, openai_api_base=base_url, openai_api_key=api_key, streaming=True,)
    except HTTPException as http_exc: raise http_exc
    except Exception as e:
        print(f"Error setting up LLM stream for config {request.config_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to initialize LLM stream: {str(e)}")

    async def stream_generator():
        try:
            async for chunk in llm.astream(request.message):
                content = chunk.content
                if content: yield f"data: {json.dumps({'chunk': content})}\n\n"; await asyncio.sleep(0.01)
        except Exception as e:
            print(f"Error during EricAI stream (Config ID: {request.config_id}): {e}")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
    return StreamingResponse(stream_generator(), media_type="text/event-stream")

# Root endpoint
@app.get("/", tags=["Root"])
async def read_root_info():
    return {"message": "MCP LLM API with predefined EricAI models in config form."}

# To run: uvicorn main:app --reload (from mcp_web_app directory)

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