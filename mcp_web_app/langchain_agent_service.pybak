import os # Ensure os is imported for path manipulation
from dotenv import load_dotenv
import asyncio
from typing import AsyncGenerator
import time
import json
import uuid # Added for potential use, though session_id comes from main.py
import re # For regex matching


# Explicitly load .env from the project root
# __file__ is mcp_web_app/langchain_agent_service.py, so ../.env should be project_root/.env
dotenv_path = os.path.join(os.path.dirname(__file__), '..', '.env')
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path=dotenv_path)
    # print(f"DEBUG: langchain_agent_service: Loaded .env file from: {dotenv_path}") # Optional: can enable for more verbose debug
# else:
    # print(f"DEBUG: langchain_agent_service: .env file not found at: {dotenv_path}") # Optional

import logging
from typing import List, Dict, Any, Optional

from langchain_core.tools import BaseTool
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.callbacks.base import BaseCallbackHandler
from langchain_core.outputs import LLMResult
from langchain.agents import create_react_agent

# from langchain_anthropic import ChatAnthropic # Remove Anthropic
from langchain_deepseek import ChatDeepSeek # Add DeepSeek
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_mcp_adapters.client import MultiServerMCPClient # Import MultiServerMCPClient

# Using relative imports
from ..config_manager import ConfigManager, ServerConfig # Relative import

# Import AgentExecutor and hub for react prompt
from langchain import hub

logger = logging.getLogger(__name__)

# Custom callback handler for streaming responses
class StreamingCallbackHandler(BaseCallbackHandler):
    """Callback handler for streaming LLM responses (legacy implementation)."""
    
    def __init__(self):
        self.streaming_queue = asyncio.Queue()
        self.full_response = ""
    
    async def on_llm_new_token(self, token: str, **kwargs) -> None:
        """Process each new LLM token."""
        # Add to complete response
        self.full_response += token
        # Send token to queue
        await self.streaming_queue.put(token)
    
    async def on_llm_start(self, serialized: Dict[str, Any], prompts: List[str], **kwargs) -> None:
        """Called when LLM starts generating."""
        # Reset response
        self.full_response = ""
    
    async def on_llm_end(self, response: LLMResult, **kwargs) -> None:
        """Called when LLM generation ends."""
        # Signal end of stream
        await self.streaming_queue.put(None)
    
    async def on_llm_error(self, error: Exception, **kwargs) -> None:
        """Handle LLM errors."""
        await self.streaming_queue.put(f"Error during generation: {error}")
        await self.streaming_queue.put(None)
        
    async def on_tool_start(self, tool_name: str, tool_input: Dict, **kwargs) -> None:
        """Handle tool start events."""
        await self.streaming_queue.put(f"\nUsing tool: {tool_name} with input: {json.dumps(tool_input, ensure_ascii=False)}\n")
        
    async def on_tool_end(self, output: str, **kwargs) -> None:
        """Handle tool end events."""
        await self.streaming_queue.put(f"\nTool output: {output}\n")
        
    async def on_tool_error(self, error: Exception, **kwargs) -> None:
        """Handle tool errors."""
        await self.streaming_queue.put(f"\nTool error: {str(error)}\n")

# Placeholder for actual MCP interaction logic
# This would eventually involve making calls to the MCP server
async def mcp_action_placeholder(server_name: str, tool_name: str, tool_input: Dict[str, Any]) -> str:
    logger.info(f"Attempting to call MCP Action: Server '{server_name}', Tool '{tool_name}', Input: {tool_input}")
    # In a real scenario, this would use an MCP client to send a request
    # to the specified server and tool, then return its response.
    # For now, it just echoes the input.
    return f"MCP Action Response from '{server_name}' for tool '{tool_name}': Processed input: {tool_input}"


class LangchainAgentService:
    # Use the aliased module to qualify the ConfigManager type hint
    def __init__(self, config_manager: ConfigManager):
        self.config_manager = config_manager
        # Initialize the LLM. Requires DEEPSEEK_API_KEY environment variable.
        self.using_placeholder_token = False
        # Add cache for LLM instance to avoid recreating it
        self._llm_cache = None
        # Add a map of fast-path responses for simple queries
        self._fast_responses = {
            "ping": "pong",
            "hello": "Hello! How can I help you today?",
            "hi": "Hi there! How can I assist you?",
        }
        self.sessions: Dict[str, Dict[str, Any]] = {} # Session store
        
        # Try to load LLM from environment configs
        self.llm = None
        self._fallback_model_used = None
        self._error_details = None
        
        try:
            # First try DeepSeek API
            api_key_from_env = os.getenv('DEEPSEEK_API_KEY')
            if not api_key_from_env or len(api_key_from_env.strip()) == 0:
                logger.warning("LangchainAgentService: DEEPSEEK_API_KEY not found or empty in environment.")
                self._error_details = "DeepSeek API key is missing or empty. Please add it to your environment variables."
                raise ValueError("Missing or empty DeepSeek API key")

            # Basic validation of API key format
            if not api_key_from_env.startswith("sk-") or len(api_key_from_env.strip()) < 20:
                logger.warning(f"LangchainAgentService: DEEPSEEK_API_KEY appears invalid (doesn't start with 'sk-' or too short)")
                self._error_details = "DeepSeek API key appears to be invalid. It should start with 'sk-' and be at least 20 characters."
                raise ValueError("Invalid DeepSeek API key format")
                
            logger.info(f"LangchainAgentService: Initializing DeepSeek LLM. API key starts with: {api_key_from_env[:5]}...")
            self.llm = ChatDeepSeek(
                model="deepseek-chat",
                api_key=api_key_from_env
            )
            self._llm_cache = self.llm  # Cache the LLM instance
            self._fallback_model_used = None
            self._error_details = None
            logger.info("ChatDeepSeek model 'deepseek-chat' initialized successfully.")
                
        except Exception as deepseek_error:
            logger.error(f"Error initializing ChatDeepSeek: {deepseek_error}", exc_info=True)
            logger.info("Attempting to fall back to Ollama...")
            
            if not self._error_details:
                self._error_details = f"DeepSeek API error: {str(deepseek_error)}"
            
            # Try Ollama as first fallback
            try:
                from langchain_community.llms import Ollama
                
                ollama_url = os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434')
                logger.info(f"Trying Ollama at: {ollama_url}")
                
                # First check if Ollama is available
                try:
                    import httpx
                    with httpx.Client() as client:
                        response = client.get(f"{ollama_url}/api/tags", timeout=3.0)
                        if response.status_code == 200:
                            # Get available models
                            models = response.json().get("models", [])
                            if models:
                                # Prefer these models in order if available
                                preferred_models = ["llama3", "llama2", "gemma", "mistral", "phi"]
                                selected_model = None
                                
                                # Try to find a preferred model
                                for preferred in preferred_models:
                                    for model in models:
                                        if preferred in model['name'].lower():
                                            selected_model = model['name']
                                            break
                                    if selected_model:
                                        break
                                
                                # If no preferred model found, use the first one
                                if not selected_model and models:
                                    selected_model = models[0]['name']
                                
                                if selected_model:
                                    logger.info(f"Using Ollama model: {selected_model}")
                                    self.llm = Ollama(model=selected_model, base_url=ollama_url)
                                    self._llm_cache = self.llm
                                    self._fallback_model_used = "ollama"
                                    logger.info(f"Successfully initialized Ollama with model: {selected_model}")
                        else:
                            logger.warning(f"Ollama API returned non-200 status code: {response.status_code}")
                            raise ConnectionError(f"Ollama returned status code: {response.status_code}")
                            
                except Exception as e:
                    logger.error(f"Error connecting to Ollama: {e}")
                    raise e
                    
            except Exception as ollama_error:
                logger.error(f"Failed to initialize Ollama fallback: {ollama_error}", exc_info=True)
                
                # If we reach this point, both DeepSeek and Ollama failed
                # Create a mock LLM as last resort
                try:
                    from langchain.llms.fake import FakeListLLM
                    
                    logger.warning("Creating a FakeListLLM as last resort fallback")
                    responses = [
                        "I'm running in fallback mode. DeepSeek API and Ollama are not available. Please check your configuration.",
                        "The system is in fallback mode. Please configure a valid DeepSeek API key or ensure Ollama is running.",
                        "Your request cannot be fully processed. The AI service is running in limited mode due to configuration issues."
                    ]
                    
                    self.llm = FakeListLLM(responses=responses)
                    self._llm_cache = self.llm
                    self._fallback_model_used = "mock"
                    self._error_details = f"Using mock LLM. DeepSeek error: {str(deepseek_error)}. Ollama error: {str(ollama_error)}"
                    logger.info("Initialized FakeListLLM as last-resort fallback")
                    
                except Exception as mock_error:
                    logger.error(f"Failed to create mock LLM: {mock_error}", exc_info=True)
                    self.llm = None
                    self._error_details = f"No LLM available. All providers failed. Original error: {str(deepseek_error)}"
                    logger.critical("No LLM available! The service will not function correctly.")

        # AgentExecutor will be initialized on-demand
        self.agent_executor = None
        # Cache for MCP client configurations to avoid rebuilding for the same config
        self._mcp_client_config_cache = {}
        # Removed: self.mcp_tool_factory = MCPServerToolFactory()

    def _check_fast_path(self, message: str) -> Optional[str]:
        """Check if the message can be handled via fast path without LLM."""
        # Normalize the message: trim whitespace and convert to lowercase
        normalized_msg = message.strip().lower()
        
        # Check for exact matches in fast responses map
        if normalized_msg in self._fast_responses:
            logger.info(f"Using fast path response for message: '{message}'")
            return self._fast_responses[normalized_msg]
            
        return None

    def _prepare_mcp_client_config(self, active_tools_config: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Dict[str, Any]]:
        mcp_servers_for_client: Dict[str, Dict[str, Any]] = {}
        
        if not active_tools_config:
            return mcp_servers_for_client

        # get_all_server_configs() should return Dict[str, models_module.ServerConfig]
        all_server_configs = self.config_manager.get_all_server_configs()

        for server_name_key in active_tools_config.keys():
            server_config: Optional[ServerConfig] = all_server_configs.get(server_name_key)
            
            if server_config:
                # Construct the config for MultiServerMCPClient
                # Ensure this matches what MultiServerMCPClient expects for each transport type
                client_entry: Dict[str, Any] = {
                    "transport": server_config.transport,
                }
                if server_config.transport == "stdio":
                    client_entry["command"] = server_config.command
                    client_entry["args"] = server_config.args
                    if server_config.cwd: # Check and add cwd if present
                        client_entry["cwd"] = server_config.cwd
                    # Add environment variables if present
                    if server_config.env:
                        client_entry["env"] = server_config.env
                elif server_config.transport in ["sse", "streamable_http"]:
                    # We need a URL for these transports.
                    # This implies ServerConfig should store URL if these transports are used.
                    # For now, we'll log a warning if this case is hit without a URL.
                    if server_config.url:
                        client_entry["url"] = server_config.url
                    else:
                        logger.warning(f"Server '{server_name_key}' uses transport '{server_config.transport}' but no URL is configured in ServerConfig.")
                        continue # Skip this server if essential info is missing
                
                mcp_servers_for_client[server_name_key] = client_entry
            else:
                logger.warning(f"Configuration for server '{server_name_key}' not found. Skipping for MCP client.")
        
        logger.info(f"Prepared MCP client config for servers: {list(mcp_servers_for_client.keys())}")
        return mcp_servers_for_client

    # Add a helper to determine if a message likely needs tools
    def _message_likely_needs_tools(self, message: str) -> bool:
        """Quickly determine if a message is likely to need tools."""
        # Keywords that might indicate tool usage needed
        tool_keywords = [
            "search", "find", "lookup", "github", "repository", "repo", "code", "file", 
            "create", "update", "get", "list", "issue", "pull request", "PR", "branch",
            "check", "status", "web", "fetch", "weather", "temperature", "forecast"
        ]
        
        # Simple heuristic: check if the message contains any tool keywords
        lower_message = message.lower()
        needs_tools = any(keyword in lower_message for keyword in tool_keywords)
        logger.info(f"_message_likely_needs_tools: Checking message: '{message}'. Keywords found: {[keyword for keyword in tool_keywords if keyword in lower_message]}. Result: {needs_tools}")
        return needs_tools
        
    # --- Helper for getting a configured streaming LLM ---
    def _get_configured_streaming_llm(self):
        # Consolidates creation of the LLM for streaming
        # Ensures API key and other parameters are consistently applied
        try:
            api_key = os.getenv('DEEPSEEK_API_KEY')
            if not api_key:
                logger.warning("DEEPSEEK_API_KEY not found for streaming LLM. This might fail.")
            # Ensure that the LLM used by the agent supports streaming and is configured for it.
            # For ChatDeepSeek, streaming=True is usually set at instantiation.
            return ChatDeepSeek(
                model="deepseek-chat", # Or from config
                api_key=api_key,
                streaming=True, # Ensure streaming is enabled
                temperature=0.7, # Or from config
                max_tokens=2000, # Or from config
            )
        except Exception as e:
            logger.error(f"Error initializing streaming LLM: {e}", exc_info=True)
            return None

    # --- Helper for getting MCP tools ---
    async def _get_mcp_tools_and_client(self, tools_config: Dict[str, List[Dict[str, Any]]]):
        # Encapsulates MCP client setup and tool fetching
        mcp_tools: List[BaseTool] = []
        mcp_client_instance = None # To store the successfully initialized client

        # mcp_client_config should be the direct input for MultiServerMCPClient constructor
        # _prepare_mcp_client_config already returns Dict[str, Dict[str, Any]]
        prepared_mcp_server_configs = self._prepare_mcp_client_config(tools_config)
        
        if not prepared_mcp_server_configs:
            logger.info("No active MCP tools config prepared, proceeding without MCP tools.")
            return mcp_tools, None # Return None for client

        temp_client = None # Initialize to ensure it's defined for finally block
        try:
            logger.info(f"Attempting to initialize MultiServerMCPClient with prepared config: {prepared_mcp_server_configs}")
            temp_client = MultiServerMCPClient(prepared_mcp_server_configs)
            await temp_client.__aenter__() # Enter context
            mcp_tools = list(temp_client.get_tools()) # Ensure this is awaited if get_tools becomes async
            mcp_client_instance = temp_client # Assign if successful
            logger.info(f"Successfully fetched {len(mcp_tools)} tools: {[t.name for t in mcp_tools] if mcp_tools else 'None'}")
        except Exception as e:
            logger.error(f"Error initializing MCP client or fetching tools: {e}", exc_info=True)
            if temp_client and mcp_client_instance is None: 
                try:
                    logger.info("Attempting to clean up MCP client after initialization/tool fetching error...")
                    await temp_client.__aexit__(type(e), e, e.__traceback__) 
                except Exception as ae_ex:
                    logger.error(f"Error during __aexit__ after MCP tool fetch failure: {ae_ex}", exc_info=True)
            # Do not re-raise here, allow agent to proceed without tools or handle upstream
            return [], None # Return empty tools and no client on error

        return mcp_tools, mcp_client_instance
        
    async def stream_llm_directly(self, user_message: str) -> AsyncGenerator[str, None]:
        """
        直接从LLM流式获取响应，无需agent或工具的开销。
        使用LangChain的原生流式处理功能。
        
        Args:
            user_message: 用户的输入消息
            
        Yields:
            响应内容的字符串片段，按生成顺序
        """
        if not self.llm:
            logger.error("LLM not initialized. Cannot process query.")
            yield "Error: Language model not initialized. Please check server logs."
            return

        # Check for fast path responses to bypass LLM call completely
        fast_path_response = self._check_fast_path(user_message)
        if fast_path_response:
            # For fast path responses, create artificial streaming
            for chunk in [fast_path_response[i:i+5] for i in range(0, len(fast_path_response), 5)]:
                yield chunk
                await asyncio.sleep(0.01)  # Small delay for visible streaming
            return
            
        # 检测消息中是否包含中文
        has_chinese = any('\u4e00' <= char <= '\u9fff' for char in user_message)
        
        if has_chinese:
            logger.info("Streaming Chinese message: " + user_message[:15] + " ...")
        else:
            logger.info("Streaming English message: " + user_message[:15] + " ...")

        # Create a human message from the user input
        messages = [HumanMessage(content=user_message)]
        
        try:
            # Create a properly configured LLM for streaming
            stream_llm = ChatDeepSeek(
                model="deepseek-chat",
                api_key=os.getenv('DEEPSEEK_API_KEY'),
                streaming=True,
                temperature=0.7,
                max_tokens=2000,
            )
            
            logger.info("Starting token streaming using LangChain's native astream method")
            
            # Use LangChain's built-in streaming capability
            token_count = 0
            contains_chinese = False
            async for chunk in stream_llm.astream(messages):
                # The chunk is an AIMessageChunk
                content = chunk.content
                if content:
                    token_count += 1
                    
                    # Check if the content contains Chinese characters
                    if not contains_chinese and any('\u4e00' <= char <= '\u9fff' for char in content):
                        contains_chinese = True
                        logger.info(f"Detected Chinese characters in stream response. First Chinese token: {content}")
                    
                    if token_count <= 3:  # Log only first few tokens for debugging
                        logger.info(f"Token {token_count}: {content}")
                    elif token_count % 20 == 0:  # Log every 20th token
                        logger.info(f"Token count: {token_count}")
                    
                    yield content
                    
            logger.info(f"Streaming complete. Received {token_count} tokens. Contains Chinese: {contains_chinese}")
            
        except Exception as e:
            logger.error(f"Error in direct LLM streaming: {e}", exc_info=True)
            yield f"Error: {str(e)}"

    async def _get_or_create_session_components(self, session_id: str, tools_config: Dict[str, List[Dict[str, Any]]]):
        """Gets or creates agent components for a given session_id."""
        if session_id not in self.sessions:
            logger.info(f"Session {session_id}: Creating new session components.")
            
            mcp_client_for_session = None
            agent_tools = []
            prepared_mcp_config = self._prepare_mcp_client_config(tools_config)

            if prepared_mcp_config:
                try:
                    mcp_client_for_session = MultiServerMCPClient(prepared_mcp_config)
                    await mcp_client_for_session.__aenter__() # Activate client
                    agent_tools = list(mcp_client_for_session.get_tools())
                    logger.info(f"Session {session_id}: MCP Client created and {len(agent_tools)} tools loaded: {[t.name for t in agent_tools]}")
                except Exception as e_mcp_init:
                    logger.error(f"Session {session_id}: Failed to initialize MCP client or get tools: {e_mcp_init}", exc_info=True)
                    # Decide if we proceed without tools or raise/return error
                    # For now, we'll proceed with an empty tool list if MCP client fails
                    if mcp_client_for_session:
                        try: # Attempt to clean up if partially initialized
                            await mcp_client_for_session.__aexit__(type(e_mcp_init), e_mcp_init, e_mcp_init.__traceback__)
                        except Exception as e_mcp_exit: logger.error(f"Session {session_id}: Error exiting MCP client during init failure: {e_mcp_exit}")
                        mcp_client_for_session = None
                    agent_tools = [] # Ensure tools are empty
            else:
                logger.info(f"Session {session_id}: No MCP tools_config provided or prepared. Proceeding without tools.")

            # LLM (ensure it's initialized - self.llm should be ready)
            # If self.llm can be None (due to init error), add check here
            current_llm = self.llm 
            if not current_llm:
                logger.error(f"Session {session_id}: LLM is not available. Cannot create agent.")
                # This is a critical failure for creating an agent.
                # We might need to yield an error and stop for this session immediately.
                # For now, the session will be created but executor will be None.
                pass # Executor will remain None

            agent_executor = None
            if current_llm: # Only create agent if LLM is available
                try:
                    # Prompt
                    prompt = hub.pull("hwchase17/openai-tools-agent")
                    # Agent
                    agent = create_openai_tools_agent(current_llm, agent_tools, prompt)
                    # Executor
                    agent_executor = AgentExecutor(
                        agent=agent,
                        tools=agent_tools,
                        verbose=True, # Or from config
                        # handle_parsing_errors might be needed if issues arise
                    )
                    logger.info(f"Session {session_id}: AgentExecutor created successfully.")
                except Exception as e_agent_create:
                    logger.error(f"Session {session_id}: Failed to create agent executor: {e_agent_create}", exc_info=True)
                    agent_executor = None # Ensure executor is None on failure
            
            self.sessions[session_id] = {
                "chat_history": [],
                "agent_executor": agent_executor,
                "mcp_client": mcp_client_for_session, # Store the active client
                "tools": agent_tools # Store tools for reference if needed
            }
        else:
            logger.info(f"Session {session_id}: Reusing existing session components.")
        
        return self.sessions[session_id]

    async def cleanup_session(self, session_id: str):
        """Cleans up resources for a given session_id, especially the MCP client."""
        logger.info(f"Attempting to cleanup session: {session_id}")
        session_data = self.sessions.pop(session_id, None)
        if session_data:
            mcp_client = session_data.get("mcp_client")
            if mcp_client:
                logger.info(f"Session {session_id}: Closing MCP client.")
                try:
                    await mcp_client.__aexit__(None, None, None)
                    logger.info(f"Session {session_id}: MCP client closed successfully.")
                except Exception as e:
                    logger.error(f"Session {session_id}: Error closing MCP client: {e}", exc_info=True)
            logger.info(f"Session {session_id}: Cleaned up.")
        else:
            logger.warning(f"Session {session_id}: Not found for cleanup.")

    async def invoke_agent_stream(self, session_id: str, user_message: str, tools_config: Dict[str, List[Dict[str, Any]]]) -> AsyncGenerator[str, None]:
        """Invokes the Langchain agent and streams responses, managing sessions."""
        logger.info(f"invoke_agent_stream called for session_id: {session_id}, user_message: '{user_message[:50]}...', tools_config: {list(tools_config.keys()) if tools_config else 'None'}")

        # Fast path check (session independent for now)
        fast_response = self._check_fast_path(user_message)
        if fast_response:
            # await self._yield_event("text", fast_response) # _yield_event needs to be defined/accessible
            yield json.dumps({"type": "text", "data": fast_response}) + "\n"
            yield json.dumps({"type": "end"}) + "\n"
            return

        # Get or create session components (agent_executor, chat_history, mcp_client)
        try:
            session_data = await self._get_or_create_session_components(session_id, tools_config)
        except Exception as e_session_setup:
            logger.error(f"Session {session_id}: Critical error setting up session components: {e_session_setup}", exc_info=True)
            yield json.dumps({"type": "error", "data": f"Failed to initialize session: {str(e_session_setup)}"}) + "\n"
            yield json.dumps({"type": "end"}) + "\n"
            return

        agent_executor = session_data.get("agent_executor")
        chat_history = session_data.get("chat_history")
        # mcp_client = session_data.get("mcp_client") # Available if needed for direct calls, but executor uses tools

        if not agent_executor:
            logger.error(f"Session {session_id}: AgentExecutor not available. Cannot process message.")
            yield json.dumps({"type": "error", "data": "Agent could not be initialized for this session."}) + "\n"
            yield json.dumps({"type": "end"}) + "\n"
            return
        
        # Placeholder: Actual agent invocation and streaming will replace this
        # For now, just echo back for testing the structure
        async def dummy_stream_after_session_setup():
            yield json.dumps({"type": "text", "data": f"Session {session_id} received: {user_message}. Agent ready." }) + "\n"
            current_history_summary = [f"{type(msg).__name__}: {msg.content[:30]}..." for msg in chat_history]
            yield json.dumps({"type": "info", "data": {"message": "Agent logic with astream_events to be implemented next.", "history_summary": current_history_summary }}) + "\n"
            yield json.dumps({"type": "end"}) + "\n"

        async for chunk in dummy_stream_after_session_setup(): 
            yield chunk

    # Original invoke_agent commented out in summary, so not modifying it unless needed.

    # --- Helper to yield structured events (ensure it's compatible or adapt) ---
    # This helper was defined inside invoke_agent_stream previously.
    # It needs to be accessible if invoke_agent_stream is to use it directly,
    # or its logic replicated. For now, assuming it will be part of the new stream handling.
    # async def _yield_event(self, event_type: str, data: Any):
    #     # This needs to be defined if called as self._yield_event
    #     # For now, the dummy stream yields JSON directly.
    #     pass 

    # --- Direct LLM Streaming (session independent for now) ---
    async def stream_llm_directly(self, user_message: str) -> AsyncGenerator[str, None]:
        """
        直接从LLM流式获取响应，无需agent或工具的开销。
        使用LangChain的原生流式处理功能。
        
        Args:
            user_message: 用户的输入消息
            
        Yields:
            响应内容的字符串片段，按生成顺序
        """
        if not self.llm:
            logger.error("LLM not initialized. Cannot process query.")
            yield "Error: Language model not initialized. Please check server logs."
            return

        # Check for fast path responses to bypass LLM call completely
        fast_path_response = self._check_fast_path(user_message)
        if fast_path_response:
            # For fast path responses, create artificial streaming
            for chunk in [fast_path_response[i:i+5] for i in range(0, len(fast_path_response), 5)]:
                yield chunk
                await asyncio.sleep(0.01)  # Small delay for visible streaming
            return
            
        # 检测消息中是否包含中文
        has_chinese = any('\u4e00' <= char <= '\u9fff' for char in user_message)
        
        if has_chinese:
            logger.info("Streaming Chinese message: " + user_message[:15] + " ...")
        else:
            logger.info("Streaming English message: " + user_message[:15] + " ...")

        # Create a human message from the user input
        messages = [HumanMessage(content=user_message)]
        
        try:
            # Create a properly configured LLM for streaming
            stream_llm = ChatDeepSeek(
                model="deepseek-chat",
                api_key=os.getenv('DEEPSEEK_API_KEY'),
                streaming=True,
                temperature=0.7,
                max_tokens=2000,
            )
            
            logger.info("Starting token streaming using LangChain's native astream method")
            
            # Use LangChain's built-in streaming capability
            token_count = 0
            contains_chinese = False
            async for chunk in stream_llm.astream(messages):
                # The chunk is an AIMessageChunk
                content = chunk.content
                if content:
                    token_count += 1
                    
                    # Check if the content contains Chinese characters
                    if not contains_chinese and any('\u4e00' <= char <= '\u9fff' for char in content):
                        contains_chinese = True
                        logger.info(f"Detected Chinese characters in stream response. First Chinese token: {content}")
                    
                    if token_count <= 3:  # Log only first few tokens for debugging
                        logger.info(f"Token {token_count}: {content}")
                    elif token_count % 20 == 0:  # Log every 20th token
                        logger.info(f"Token count: {token_count}")
                    
                    yield content
                    
            logger.info(f"Streaming complete. Received {token_count} tokens. Contains Chinese: {contains_chinese}")
            
        except Exception as e:
            logger.error(f"Error in direct LLM streaming: {e}", exc_info=True)
            yield f"Error: {str(e)}"

    async def invoke_agent(self, user_message: str, active_tools_config: Dict[str, List[Dict[str, Any]]]) -> str:
        """
        Invoke the agent asynchronously.
        
        Args:
            user_message: The message from the user to respond to
            active_tools_config: Configuration for enabled MCP tools
            
        Returns:
            The agent's response
        """
        # Check for fast path responses first
        fast_response = self._check_fast_path(user_message)
        if fast_response:
            return fast_response
        
        if not self.llm:
            logger.error("LLM not initialized. Cannot process query.")
            return "Error: LLM not initialized. Cannot process query."
        
        # Use cached LLM if available
        if self._llm_cache:
            self.llm = self._llm_cache
        
        # Check if tools are likely needed for this query
        needs_tools = self._message_likely_needs_tools(user_message)
        
        if not needs_tools:
            logger.info(f"Message '{user_message}' likely doesn't need tools, proceeding with direct LLM call")
            # Make a direct call to the LLM
            try:
                # Use proper message format for LLM call
                response = await self.llm.ainvoke([HumanMessage(content=user_message)])
                return response.content
            except Exception as e:
                logger.error(f"Error in direct LLM call: {e}")
                return f"I'm sorry, I encountered an error: {str(e)}"

        mcp_tools: List[BaseTool] = []
        mcp_client = None
        
        # Prepare the configuration for MultiServerMCPClient
        mcp_client_config = self._prepare_mcp_client_config(active_tools_config)

        try:
            if mcp_client_config:
                logger.info(f"Attempting to initialize MultiServerMCPClient with config: {mcp_client_config}")
                
                try:
                    # Important: we need to keep the client object in scope during the entire operation
                    # Instead of using async with which closes the client when execution leaves its scope,
                    # we'll manually handle the context by keeping a reference to the client
                    mcp_client = MultiServerMCPClient(mcp_client_config)
                    # Manually enter the context
                    await mcp_client.__aenter__()
                    
                    # Now get tools from the client
                    mcp_tools = list(mcp_client.get_tools())
                    logger.info(f"Successfully fetched {len(mcp_tools)} tools from MultiServerMCPClient: {[t.name for t in mcp_tools]}")
                except Exception as e:
                    logger.error(f"Error initializing MCP client or fetching tools: {e}", exc_info=True)
                    return f"Error: Could not initialize MCP client or fetch tools: {e}"
            else:
                logger.info("No active MCP tools config, proceeding without MCP tools.")

            if not mcp_tools:
                logger.info("No MCP tools available/created. Proceeding with LLM call without tools.")
                response = await self.llm.ainvoke([HumanMessage(content=user_message)]) # type: ignore
                response_content = response.content # type: ignore
                return response_content
            
            logger.info(f"Initializing agent with {len(mcp_tools)} tools: {[t.name for t in mcp_tools]}")

            prompt = ChatPromptTemplate.from_messages(
                [
                    ("system", "You are a helpful assistant that can use tools to answer questions."),
                    MessagesPlaceholder("chat_history", optional=True),
                    ("human", "{input}"),
                    MessagesPlaceholder("agent_scratchpad"),
                ]
            )

            agent = create_tool_calling_agent(self.llm, mcp_tools, prompt)
            # Create a fresh agent_executor for each request
            agent_executor = AgentExecutor(agent=agent, tools=mcp_tools, verbose=True, handle_tool_error=True) # type: ignore

            logger.info(f"Invoking agent with message: '{user_message}' and {len(mcp_tools)} tools.")
            try:
                # Create a timeout for the agent execution to prevent hanging
                response = await asyncio.wait_for(
                    agent_executor.ainvoke({"input": user_message, "chat_history": []}), # type: ignore
                    timeout=120  # 2 minute timeout
                )
                
                agent_response = response.get("output", "Error: No output from agent.")
                logger.info(f"Agent output: {agent_response[:200]}...")
                
                return agent_response
            except asyncio.TimeoutError:
                logger.error("Agent execution timed out after 120 seconds")
                return "Error: The agent operation timed out. Please try a simpler query or try again later."
            except Exception as agent_error:
                logger.error(f"Error during agent execution: {agent_error}", exc_info=True)
                error_msg = str(agent_error)
                
                if "ClosedResourceError" in error_msg:
                    return "Error: API connection closed unexpectedly. Please try again or restart the server."
                
                return f"Error processing your request: {agent_error}"

        except Exception as e:
            logger.error(f"Error invoking agent: {e}", exc_info=True)
            # Check if the error is from MultiServerMCPClient initialization itself
            if "MultiServerMCPClient" in str(e) and not mcp_tools:
                 return f"Error initializing MCP tool client: {e}"
            return f"Error processing your request with the agent: {e}"
        finally:
            # Make sure we close the client when we're done with the whole operation
            if mcp_client:
                try:
                    logger.info("Closing MultiServerMCPClient...")
                    await mcp_client.__aexit__(None, None, None)
                    logger.info("MultiServerMCPClient closed successfully")
                except Exception as close_error:
                    logger.error(f"Error closing MultiServerMCPClient: {close_error}", exc_info=True)

# # Removed old _create_mcp_tools method
# # Removed old main_test as it relied on the old tool creation logic and factory

# # To test this, you would need to:
# # 1. Ensure ConfigManager is passed correctly during LangchainAgentService instantiation in main.py
# # 2. Ensure your servers.json and models.py (ServerConfig) are up to date.
# #    Specifically, if you plan to use 'sse' or 'streamable_http' transports,
# #    the ServerConfig model and servers.json should include a 'url' field for those servers.
# #    Our current echo_server in servers.json is 'stdio', which should work with 'command' and 'args'. 