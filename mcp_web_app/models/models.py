from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any, Union

class ServerConfig(BaseModel):
    name: str
    description: str
    command: str
    args: List[str]
    transport: str # Added: e.g., "stdio", "sse"
    # Optional fields for different transport types or configurations
    url: Optional[str] = None  # For SSE, HTTP-based transports
    cwd: Optional[str] = None  # For stdio transport if a specific CWD is needed
    env: Optional[Dict[str, str]] = {}  # Environment variables for the server
    # This might become obsolete if langchain-mcp-adapters discovers tools directly
    # shell: bool = True # Removed
    # Add other fields from your TypeScript ServerConfig as needed
    # e.g., windowsHide, heartbeatEnabled, autoApprove

class ServerStatusResponse(BaseModel):
    server_name: str
    status: str
    message: Optional[str] = None
    pid: Optional[int] = None 
    discovered_capabilities: Optional[List[Any]] = None

# --- Added Chat Models ---
class ChatRequest(BaseModel):
    message: str
    active_tools_config: Optional[Dict[str, List[Dict[str, Any]]]] = None

class ChatResponse(BaseModel):
    reply: str

# --- Added Stream Chat Models ---
class StreamChatRequest(BaseModel):
    session_id: str
    prompt: str
    tools_config: Optional[Dict[str, List[Dict[str, Any]]]] = None
    llm_config_id: Optional[str] = None # Added field for LLM selection
    agent_mode: Optional[str] = None # Added field for agent mode
    agent_data_source: Optional[Union[str, Dict]] = None # Added field for agent data source

# For creating a new server config
class CreateServerConfigRequest(BaseModel):
    config_key: str
    config: ServerConfig

# For response from creating a new server config
class CreateServerConfigResponse(BaseModel):
    success: bool
    message: str

# For updating an existing server config
class UpdateServerConfigRequest(BaseModel):
    config: ServerConfig

# For response from updating a server config
class UpdateServerConfigResponse(BaseModel):
    success: bool
    message: str 

# --- LLM Configuration Models ---
class OllamaConfig(BaseModel):
    base_url: str = "http://localhost:11434"
    model: str # e.g., "llama3:8b", "mistral"
    temperature: float = 0.7
    # Add other Ollama-specific options here if needed, like num_ctx, top_k, top_p etc.
    # Example: options: Optional[Dict[str, Any]] = None 

class DeepSeekConfig(BaseModel):
    model: str = "deepseek-chat" # Default model
    temperature: float = 0.7
    api_key: Optional[str] = None
    # Add other DeepSeek-specific options here if needed

class LLMConfig(BaseModel):
    config_id: str # Unique identifier, e.g., "ollama_local_llama3"
    provider: str # e.g., "ollama", "openai", "deepseek"
    display_name: str # User-friendly name, e.g., "Local Llama3 (Ollama)"
    ollama_config: Optional[OllamaConfig] = None
    deepseek_config: Optional[DeepSeekConfig] = None # Uncommented and defined
    # Add other provider configs here as needed, e.g.:
    # openai_config: Optional[OpenAIConfig] = None
    api_key_env_var: Optional[str] = None # e.g., "OPENAI_API_KEY", "DEEPSEEK_API_KEY"
    is_default: Optional[bool] = False 