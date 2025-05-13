import os # Ensure os is imported for path manipulation
from dotenv import load_dotenv
import asyncio
import logging
import json
import uuid # Added for potential use, though session_id comes from main.py
import re # For regex matching
from queue import Queue 
from concurrent.futures import Future
import threading
import sys # ADDED: For MemorySaver fallback check
from typing import AsyncGenerator, Dict, Any, List, Tuple, Optional, Union, AsyncIterator
import time
from datetime import datetime
import yaml # Added for YAML loading
import traceback

# Initialize logger at the top of the file
logger = logging.getLogger(__name__)

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.agents import AgentExecutor, create_openai_tools_agent, create_react_agent
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, BaseMessage, ToolMessage, AIMessageChunk, FunctionMessage
from langchain_core.tools import BaseTool
from langchain_core.callbacks.base import BaseCallbackHandler
from langchain_core.outputs import LLMResult, ChatGenerationChunk, GenerationChunk
from langchain_core.agents import AgentAction, AgentFinish
from langchain_core.language_models import BaseLanguageModel

# Consolidate runnables imports
from langchain_core.runnables import (
    RunnableConfig, 
    RunnablePassthrough, 
    RunnableSerializable,
    RunnableWithMessageHistory,
    Runnable
)

from langchain.agents.output_parsers.react_single_input import ReActSingleInputOutputParser

from langchain import hub

from langchain_deepseek import ChatDeepSeek # Add DeepSeek
from langchain_community.chat_models import ChatOllama # Added for Ollama
from langchain_mcp_adapters.client import MultiServerMCPClient # Import MultiServerMCPClient
from langchain_community.agent_toolkits import JsonToolkit, create_json_agent # ADDED
from langchain_community.tools.json.tool import JsonSpec # ADDED

from ..config_manager import ConfigManager, ServerConfig # Relative import
from ..models.models import LLMConfig # Correct import for LLMConfig
from ..utils.mcp_tool_scripthost import MCPServerToolFactory # Relative import for factory
from ..utils.custom_event_handler import CustomAsyncIteratorCallbackHandler, EventType, MCPEventCollector # MODIFIED: Import EventType and MCPEventCollector

from langchain_community.chat_message_histories import ChatMessageHistory 
from ..utils.io import load_json_or_yaml
from ..utils.llm import get_fast_response
from ..utils.session import needs_session_recreation, create_new_session_dict

# Explicitly load .env from the project root
dotenv_path = os.path.join(os.path.dirname(__file__), '..', '..', '.env')
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path=dotenv_path)

# Define a simple streaming callback handler for LLM
class StreamingCallback(BaseCallbackHandler):
    def __init__(self, output_stream_fn):
        super().__init__()
        self.output_stream_fn = output_stream_fn

    async def on_llm_new_token(self, token: str, **kwargs: Any) -> None:
        logger.debug(f"StreamingCallback on_llm_new_token: '{token}'")
        await self.output_stream_fn("token", token)

    async def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        logger.debug(f"StreamingCallback on_llm_end. Response: {response}")
        pass

    async def on_llm_error(self, error: BaseException, **kwargs: Any) -> None:
        logger.error(f"StreamingCallback on_llm_error: {error}", exc_info=True)
        await self.output_stream_fn("error", str(error))

# Custom Parser to handle ReAct agent tool inputs more robustly
class CustomReActParser(ReActSingleInputOutputParser):
    def parse(self, text: str) -> Union[AgentAction, AgentFinish]:
        parsed_output = super().parse(text)

        if isinstance(parsed_output, AgentAction):
            if isinstance(parsed_output.tool_input, str):
                raw_tool_input_str = parsed_output.tool_input
                cleaned_input_str = raw_tool_input_str.strip()

                if cleaned_input_str.startswith("```json"):
                    cleaned_input_str = cleaned_input_str[len("```json"):].strip()
                
                if cleaned_input_str.startswith("```"): 
                    cleaned_input_str = cleaned_input_str[len("```"):].strip()
                
                if cleaned_input_str.endswith("```"):
                    cleaned_input_str = cleaned_input_str[:-len("```")].strip()
                
                if (cleaned_input_str.startswith("{") and cleaned_input_str.endswith("}")) or \
                   (cleaned_input_str.startswith("[") and cleaned_input_str.endswith("]")):
                    try:
                        loaded_json = json.loads(cleaned_input_str)
                        parsed_output.tool_input = loaded_json
                        logger.debug(f"CustomReActParser successfully parsed tool_input string to JSON: {loaded_json}")
                    except json.JSONDecodeError as e:
                        logger.warning(f"CustomReActParser: Failed to parse cleaned tool_input string as JSON: '{cleaned_input_str}'. Error: {e}. Keeping as cleaned string.")
                        parsed_output.tool_input = cleaned_input_str 
                else:
                    parsed_output.tool_input = cleaned_input_str
                    logger.debug(f"CustomReActParser: Tool input does not appear to be JSON, kept as cleaned string: '{cleaned_input_str}'")
        
        return parsed_output

class SimpleChainExecutor(RunnableSerializable):
    # Reverted field names to not use leading underscores
    executable_pipeline: Runnable 
    llm_instance_ref: BaseLanguageModel

    class Config:
        arbitrary_types_allowed = True

    # Updated __init__ signature to accept prompt_template and llm_instance for clarity
    def __init__(self, prompt_template: ChatPromptTemplate, llm_instance: BaseLanguageModel, **kwargs):
        # Explicitly construct the pipeline that will be executed
        pipeline = prompt_template | llm_instance
        
        # Pass to super's __init__ to set the renamed fields
        super().__init__(executable_pipeline=pipeline, llm_instance_ref=llm_instance, **kwargs)
        
        logger.info(f"SimpleChainExecutor initialized. Executable pipeline: {self.executable_pipeline}, LLM ref: {self.llm_instance_ref}")

    def _call_chain_for_invoke(self, inputs: Dict[str, Any], config: Optional[RunnableConfig] = None) -> AIMessage:
        if "chat_history" not in inputs:
            inputs["chat_history"] = []
        response_message = self.executable_pipeline.invoke(inputs, config=config) # Use new field name
        final_content = ""
        final_metadata = {}
        if isinstance(response_message, BaseMessage):
            final_content = response_message.content
            final_metadata = response_message.response_metadata or {}
            if hasattr(response_message, 'tool_calls') and response_message.tool_calls:
                final_metadata['tool_calls'] = response_message.tool_calls
            if hasattr(response_message, 'tool_call_chunks') and response_message.tool_call_chunks:
                final_metadata['tool_call_chunks'] = response_message.tool_call_chunks
        elif isinstance(response_message, str):
            final_content = response_message
        elif isinstance(response_message, dict) and 'content' in response_message:
            final_content = str(response_message['content'])
            final_metadata = {k: v for k, v in response_message.items() if k != 'content'}
        else: 
            logger.warning(f"Unexpected response type from sync chain in SimpleChainExecutor: {type(response_message)}. Converting to string.")
            final_content = str(response_message)
        return AIMessage(content=final_content, response_metadata=final_metadata)

    def invoke(self, inputs: Dict[str, Any], config: Optional[RunnableConfig] = None) -> Dict[str, Any]:
        """Invoke the chain synchronously."""
        response_message = self._call_chain_for_invoke(inputs, config)
        return {"output": response_message.content}

    async def _call_chain_for_ainvoke(self, inputs: Dict[str, Any], config: Optional[RunnableConfig] = None) -> AIMessage:
        if "chat_history" not in inputs:
            inputs["chat_history"] = []
        response_message = await self.executable_pipeline.ainvoke(inputs, config=config) # Use new field name
        final_content = ""
        final_metadata = {}
        if isinstance(response_message, BaseMessage):
            final_content = response_message.content
            final_metadata = response_message.response_metadata or {}
            # Preserve tool calls if they are part of the message, though unlikely for a simple chain
            if hasattr(response_message, 'tool_calls') and response_message.tool_calls:
                final_metadata['tool_calls'] = response_message.tool_calls
            if hasattr(response_message, 'tool_call_chunks') and response_message.tool_call_chunks: # For completeness
                final_metadata['tool_call_chunks'] = response_message.tool_call_chunks
        elif isinstance(response_message, str):
            final_content = response_message
        elif isinstance(response_message, dict) and 'content' in response_message: # Some models might return dict
            final_content = str(response_message['content'])
            final_metadata = {k: v for k, v in response_message.items() if k != 'content'}
        else: 
            logger.warning(f"Unexpected response type from chain in SimpleChainExecutor: {type(response_message)}. Converting to string.")
            final_content = str(response_message)
        return AIMessage(content=final_content, response_metadata=final_metadata)

    async def ainvoke(self, inputs: Dict[str, Any], config: Optional[RunnableConfig] = None) -> Dict[str, Any]:
        response_message = await self._call_chain_for_ainvoke(inputs, config)
        # RunnableWithMessageHistory expects 'output' key to be a string if output_messages_key is not used.
        return {"output": response_message.content} 

    async def astream(self, inputs: Dict[str, Any], config: Optional[RunnableConfig] = None, **kwargs: Optional[Any]) -> AsyncIterator[AIMessageChunk]:
        if "chat_history" not in inputs:
            inputs["chat_history"] = []

        async for chunk in self.executable_pipeline.astream(inputs, config=config): # Use new field name
            if isinstance(chunk, AIMessageChunk):
                yield chunk
            elif isinstance(chunk, BaseMessage): 
                if chunk.content or chunk.content == "": # Yield even if content is empty string from a BaseMessage chunk
                    yield AIMessageChunk(content=chunk.content)
            elif isinstance(chunk, str):
                yield AIMessageChunk(content=chunk)
            elif isinstance(chunk, dict) and "content" in chunk and isinstance(chunk["content"], str):
                yield AIMessageChunk(content=chunk["content"])
            else:
                # Avoid excessive logging for common non-contentful intermediate chunks or empty strings
                str_chunk_content = str(chunk) if chunk is not None else ""
                if str_chunk_content and str_chunk_content.strip() and str_chunk_content !="{}":
                    logger.debug(f"SimpleChainExecutor.astream received unhandled chunk type: {type(chunk)}, yielding as string content: '{str_chunk_content}'")
                    yield AIMessageChunk(content=str_chunk_content)
                elif not str_chunk_content.strip() and str_chunk_content !="{}": # Log if it's spaces or empty but not just "{}"
                    pass # logger.debug(f"SimpleChainExecutor.astream received empty or whitespace-only chunk type: {type(chunk)}, value: '{chunk}'. Skipping.")
                # else don't log for common empty dicts {} or None

class LangchainAgentService:
    def __init__(self, config_manager: ConfigManager):
        self.config_manager = config_manager # Use the passed-in ConfigManager
        self._llm_cache: Dict[str, Any] = {}
        self.llm = None # Default LLM instance, to be loaded by _get_llm
        self.globally_active_tools: Optional[Dict[str, List[Dict[str, Any]]]] = None # This might need to be populated from ConfigManager tool server configs
        
        # Initial LLM loading can be triggered here if needed, or lazily via _get_llm
        try:
            # Ensure an event loop is running if we are in a non-async context trying to create a task
            loop = asyncio.get_event_loop()
            if loop.is_running():
                 asyncio.create_task(self._get_llm()) # Load default LLM
            else: # If no loop running (e.g. direct script run for testing), run synchronously
                 loop.run_until_complete(self._get_llm())
        except Exception as e:
            logger.error(f"Failed to initialize default LLM during LangchainAgentService startup: {e}", exc_info=True)

        self._fast_responses = {
            "ping": "pong",
            "hello": "Hello! How can I help you today?",
            "hi": "Hi there! How can I assist you?",
            "test": "I'm working! How can I help you?"
        }
        self.sessions: Dict[str, Dict[str, Any]] = {}
        
        self.request_queue: Queue[tuple[Optional[str], str, Dict[str, Any], Optional[str], Optional[str], Optional[Union[str, Dict]], Future]] = Queue() # Added agent_mode, agent_data_source
        self.loop = None
        self.dispatcher_thread = None
        
        self.agent_executor = None # Per-session
        self._mcp_client_config_cache = {}
        
        self.start_dispatcher()

    async def update_globally_active_tools(self, tools: Dict[str, List[Dict[str, Any]]]):
        """
        Updates the globally active tools.
        The `tools` dict is expected to be like: {"server_name": [{"name": "tool_name", "description": "..."}]}
        """
        logger.debug(f"update_globally_active_tools: Received tools payload: {tools}")
        self.globally_active_tools = tools
        logger.debug(f"update_globally_active_tools: self.globally_active_tools is now: {self.globally_active_tools}")
        # If there are session components that depend on these global tools and need
        # to be refreshed, you might add logic here to invalidate/recreate them,
        # or have sessions check this global config when they are next used.
        # For now, it just updates the property.

    async def _get_llm(self, llm_config_id: Optional[str] = None) -> Any:
        llm_config_manager = self.config_manager

        # Try to get the llm_config_id based on provided ID or default
        if llm_config_id:
            logger.info(f"Attempting to use explicit LLM config ID: '{llm_config_id}'")
            effective_llm_config_id = llm_config_id
        else:
            logger.info("No explicit LLM config ID provided, looking for default")
            # Try to find the default LLM config
            default_llm_config = llm_config_manager.get_default_llm_config()
            if default_llm_config:
                effective_llm_config_id = default_llm_config.config_id
                logger.info(f"Using default LLM config ID: '{effective_llm_config_id}'")
            else:
                # If no default is set, use the first LLM config if available
                all_llm_configs = llm_config_manager.get_llm_configs()
                if all_llm_configs:
                    effective_llm_config_id = all_llm_configs[0].config_id
                    logger.info(f"No default LLM config found. Using first available config: '{effective_llm_config_id}'")
                else:
                    logger.error("No LLM configs found. Unable to initialize an LLM.")
                    return None

        # Check if we have already cached this LLM instance
        if effective_llm_config_id in self._llm_cache:
            logger.info(f"Returning cached LLM for config ID: '{effective_llm_config_id}'")
            self.llm = self._llm_cache[effective_llm_config_id]  # Update current LLM reference
            return self._llm_cache[effective_llm_config_id]

        # Load the LLM config
        all_llm_configs = llm_config_manager.get_llm_configs()
        llm_config_to_use = next((config for config in all_llm_configs if config.config_id == effective_llm_config_id), None)
        if not llm_config_to_use:
            logger.error(f"LLM config for '{effective_llm_config_id}' not found.")
            return None

        logger.info(f"Creating new LLM instance for config ID: '{effective_llm_config_id}', provider: {llm_config_to_use.provider}")
        
        try:
            created_llm = None # Initialize created_llm
            if llm_config_to_use.provider == "deepseek":
                # Critical debugging for DeepSeek API key issues
                if not llm_config_to_use.deepseek_config:
                    logger.error(f"DeepSeek provider selected for '{effective_llm_config_id}' but no deepseek_config found.")
                    return None

                # Check both sources for API key
                env_api_key = None
                config_api_key = None
                
                # 1. Check environment variable
                if llm_config_to_use.api_key_env_var:
                    env_api_key = os.getenv(llm_config_to_use.api_key_env_var)
                    if env_api_key:
                        logger.info(f"Found DeepSeek API key in environment variable '{llm_config_to_use.api_key_env_var}' (first 5 chars: {env_api_key[:5]}***)")
                    else:
                        logger.warning(f"No DeepSeek API key found in environment variable '{llm_config_to_use.api_key_env_var}'")
                
                # 2. Check config
                if hasattr(llm_config_to_use.deepseek_config, 'api_key') and llm_config_to_use.deepseek_config.api_key:
                    config_api_key = llm_config_to_use.deepseek_config.api_key
                    logger.info(f"Found DeepSeek API key in config (first 5 chars: {config_api_key[:5]}***)")
                
                # Use config API key or fall back to env var
                api_key_to_use = config_api_key or env_api_key
                
                if not api_key_to_use:
                    logger.error(f"DeepSeek API key not found via env var '{llm_config_to_use.api_key_env_var}' or in deepseek_config.api_key for '{effective_llm_config_id}'.")
                    
                    # Create a fallback to Ollama if available
                    logger.info("Attempting to fall back to a local Ollama instance")
                    try:
                        # Try to find an Ollama config
                        ollama_configs = [config for config in llm_config_manager.get_llm_configs() 
                                          if config.provider == "ollama" and config.ollama_config]
                        
                        if ollama_configs:
                            ollama_config = ollama_configs[0]
                            logger.info(f"Falling back to Ollama LLM: {ollama_config.config_id}")
                            
                            created_llm = ChatOllama(
                                model=ollama_config.ollama_config.model,
                                base_url=ollama_config.ollama_config.base_url,
                                temperature=ollama_config.ollama_config.temperature
                            )
                            logger.info(f"Successfully created fallback ChatOllama instance")
                            # Cache and return the Ollama LLM
                            self._llm_cache[effective_llm_config_id] = created_llm
                            self.llm = created_llm
                            return created_llm
                        else:
                            logger.warning("No Ollama configs available for fallback")
                            return None
                    except Exception as fallback_error:
                        logger.error(f"Error creating fallback Ollama LLM: {fallback_error}")
                        return None
                
                logger.info(f"Creating ChatDeepSeek with model={llm_config_to_use.deepseek_config.model}, temp={llm_config_to_use.deepseek_config.temperature}")
                try:
                    created_llm = ChatDeepSeek(
                        model=llm_config_to_use.deepseek_config.model,
                        temperature=llm_config_to_use.deepseek_config.temperature,
                        api_key=api_key_to_use,
                        streaming=True
                    )
                    logger.info(f"Successfully created ChatDeepSeek instance with streaming=True for config '{effective_llm_config_id}'")
                except Exception as deepseek_error:
                    logger.error(f"Failed to create ChatDeepSeek: {deepseek_error}")
                    # Fall back to a mock LLM for testing that always returns a fixed response
                    logger.warning("Creating a fallback mock LLM that will return fixed responses")
                    
                    from langchain.llms.fake import FakeListLLM
                    created_llm = FakeListLLM(responses=["I'm a fallback response because the DeepSeek API is unavailable. Please check your API key and try again."])
            
            elif llm_config_to_use.provider == "ollama":
                if not llm_config_to_use.ollama_config:
                    logger.error(f"Ollama provider selected for '{effective_llm_config_id}' but no ollama_config found.")
                    return None
                
                try:
                    created_llm = ChatOllama(
                        model=llm_config_to_use.ollama_config.model,
                        base_url=llm_config_to_use.ollama_config.base_url,
                        temperature=llm_config_to_use.ollama_config.temperature,
                    )
                except Exception as ollama_error:
                    logger.error(f"Failed to create ChatOllama: {ollama_error}")
                    # Fall back to a mock LLM
                    logger.warning("Creating a fallback mock LLM for Ollama that will return fixed responses")
                    from langchain.llms.fake import FakeListLLM
                    created_llm = FakeListLLM(responses=["I'm a fallback response because Ollama is unavailable. Please make sure Ollama is running and try again."])
            
            # Add other providers like "openai" here
            else:
                logger.error(f"Unsupported LLM provider: {llm_config_to_use.provider} for config ID '{effective_llm_config_id}'")
                return None
                
            # Cache the LLM for future use
            if created_llm:
                self._llm_cache[effective_llm_config_id] = created_llm
                self.llm = created_llm  # Update the current LLM reference
                logger.info(f"LLM instance created and cached for '{effective_llm_config_id}'. Current self.llm is set.")
            return created_llm
            
        except Exception as e:
            logger.error(f"Error creating LLM for config '{effective_llm_config_id}': {e}", exc_info=True)
            return None

    async def _get_or_create_session_components(self, 
                                                session_id: str, 
                                                tools_config: Dict[str, Any], 
                                                llm_config_id: Optional[str] = None,
                                                agent_mode: Optional[str] = None, # New
                                                agent_data_source: Optional[Union[str, Dict]] = None # New
                                               ) -> Dict[str, Any]:
        session_exists = session_id in self.sessions
        session = self.sessions[session_id] if session_exists else None
        session_needs_recreation = needs_session_recreation(session, llm_config_id, tools_config, agent_mode, agent_data_source)
        current_llm = None
        effective_llm_config_id = llm_config_id

        if session_needs_recreation:
            # Get LLM instance first, as it's needed for new session dict and agent creation
            current_llm = await self._get_llm(llm_config_id)
            if not current_llm:
                logger.error(f"Session {session_id}: Failed to obtain an LLM instance for recreation/creation.")
                if session_exists:
                    self.sessions[session_id]["agent_executor"] = None
                    self.sessions[session_id]["raw_agent_executor"] = None
                else:
                    self.sessions[session_id] = create_new_session_dict(
                        None, effective_llm_config_id, tools_config, agent_mode, agent_data_source
                    )
                return self.sessions[session_id] # Return early if LLM failed

            if session_exists:
                logger.info(f"Session {session_id}: Re-creating session components due to changed LLM/Tools/AgentMode/DataSource config.")
                
                # FIX: Close the old MCP client if it exists
                old_mcp_client = self.sessions[session_id].get("mcp_client")
                if old_mcp_client and hasattr(old_mcp_client, "__aexit__"):
                    logger.info(f"Session {session_id}: Closing old MCP client before recreation.")
                    try:
                        await old_mcp_client.__aexit__(None, None, None)
                        setattr(old_mcp_client, "_explicitly_closed_in_recreation", True) # Mark it
                    except Exception as e_close:
                        logger.error(f"Session {session_id}: Error closing old MCP client: {e_close}", exc_info=True)
                
                existing_history_obj = self.sessions[session_id].get("memory_saver")
                if not isinstance(existing_history_obj, ChatMessageHistory):
                    logger.warning(f"Session {session_id}: Existing memory_saver is not ChatMessageHistory or missing. Creating new ChatMessageHistory.")
                    existing_history_obj = ChatMessageHistory()
                
                # Preserve existing display history list - RENAME THIS for clarity
                # This list is mainly for our direct manipulation/logging if needed, RWMH uses memory_saver
                existing_chat_messages_for_log = self.sessions[session_id].get("chat_messages_for_log", []) 

                self.sessions[session_id].update({
                    "llm": current_llm, 
                    "agent_executor": None, 
                    "raw_agent_executor": None, 
                    "mcp_client": None, 
                    "memory_saver": existing_history_obj, 
                    "chat_messages_for_log": existing_chat_messages_for_log, # Store the list of messages for logging/display
                    "llm_config_id_used": effective_llm_config_id,
                    "tools_config_used": tools_config,
                    "agent_mode_used": agent_mode,
                    "agent_data_source_used": agent_data_source
                })
            else: # This is a NEW session
                logger.info(f"Session {session_id}: Creating new session components (first time for this session_id)")
                self.sessions[session_id] = {
                    "llm": current_llm,
                    "agent_executor": None, 
                    "raw_agent_executor": None, 
                    "mcp_client": None, 
                    "memory_saver": ChatMessageHistory(), 
                    "chat_messages_for_log": [], # Initialize as empty list for logging/display
                    "llm_config_id_used": effective_llm_config_id,
                    "tools_config_used": tools_config,
                    "agent_mode_used": agent_mode,
                    "agent_data_source_used": agent_data_source
                }
            
            # Now, self.sessions[session_id] definitely exists.
            # Use its chat_history and memory_saver for the agent creation process.
            # existing_chat_history_for_agent = self.sessions[session_id]["chat_history"] # Not strictly needed as var
            # current_memory_saver_for_agent = self.sessions[session_id]["memory_saver"] # Not strictly needed as var
            
            current_llm = await self._get_llm(llm_config_id)
            if not current_llm:
                logger.error(f"Session {session_id}: Failed to obtain an LLM instance.")
                # Update the now-existing session entry
                self.sessions[session_id].update({
                    "agent_executor": None, 
                    "mcp_client": None, 
                    "llm_config_id": llm_config_id or (self.config_manager.get_default_llm_config().config_id if self.config_manager.get_default_llm_config() else None),
                    "tools_config_used": tools_config,
                    "agent_mode_used": agent_mode,
                    "agent_data_source_used": agent_data_source
                    # chat_history and memory_saver are already in their initial/preserved state
                })
                return self.sessions[session_id]

            raw_agent_executor: Any = None
            mcp_client = None # This is the local mcp_client for this creation, will be assigned to session
            agent_tools: List[BaseTool] = [] # Initialize agent_tools correctly here

            if agent_mode == "json" and agent_data_source:
                logger.info(f"Session {session_id}: Attempting to initialize JSON Agent.")
                agent_tools: List[BaseTool] = [] # Initialize for JSON agent block
                try:
                    json_data = None
                    if isinstance(agent_data_source, str) or isinstance(agent_data_source, dict):
                        json_data = load_json_or_yaml(agent_data_source) if isinstance(agent_data_source, str) else agent_data_source
                        if json_data is not None:
                            logger.info(f"Session {session_id}: Loaded JSON/YAML data for JSON agent.")
                        else:
                            logger.error(f"Session {session_id}: Failed to load or parse JSON/YAML data for JSON Agent.")
                    else:
                        logger.error(f"Session {session_id}: agent_data_source is not a str or dict. Type: {type(agent_data_source)}")

                    if json_data:
                        json_spec = JsonSpec(dict_=json_data, max_value_length=4000)
                        json_toolkit = JsonToolkit(spec=json_spec)
                        if not current_llm: # Should be caught earlier
                             logger.error(f"Session {session_id}: LLM not available for JSON agent creation (critical).")
                             raise ValueError("LLM not available for JSON agent")

                        raw_agent_executor = create_json_agent(
                            llm=current_llm,
                            toolkit=json_toolkit,
                            verbose=True # Consider making this configurable
                        )
                        logger.info(f"Session {session_id}: JSON Agent created successfully.")
                    else:
                        logger.error(f"Session {session_id}: Failed to load or parse JSON data for JSON Agent. Falling back.")
                        # Fallback will occur naturally as raw_agent_executor is None
                except Exception as e:
                    logger.error(f"Session {session_id}: Error initializing JSON Agent: {e}. Falling back.", exc_info=True)
                    raw_agent_executor = None # Ensure it's None on error
            
            elif agent_mode == "react":
                agent_tools: List[BaseTool] = []
                logger.info(f"Session {session_id}: Mode is 'react'. Creating ReAct agent.")

                if tools_config and tools_config.get("enabled_tools"):
                    logger.info(f"Session {session_id}: Initializing MCP Client for ReAct tools: {tools_config['enabled_tools']}")
                    all_server_configs = self.config_manager.get_all_tool_server_configs()
                    if not all_server_configs:
                        logger.warning(f"Session {session_id}: No tool server configurations found for ReAct agent.")
                    else:
                        # Determine required server names from tools_config["enabled_tools"]
                        required_server_names: List[str] = []
                        if isinstance(tools_config.get("enabled_tools"), dict):
                            required_server_names = list(tools_config["enabled_tools"].keys())
                        elif isinstance(tools_config.get("enabled_tools"), list):
                            # This case is if enabled_tools is a flat list of tool names,
                            # which doesn't directly give server names.
                            # This logic might need refinement if flat lists are common.
                            # For now, assume enabled_tools is a dict {server_name: [tool_details]}
                            # If it's a flat list, we might need to iterate all_server_configs
                            # and see which ones provide these tools, which is more complex.
                            # Sticking to dict assumption for server names from tools_config for now.
                            logger.warning(f"Session {session_id}: tools_config['enabled_tools'] is a list, cannot directly get server names. MCP client might connect to all servers if not filtered properly.")
                            # As a fallback, if we can't determine servers from a flat list of tools,
                            # we might have to connect to all. Or, ideally, tools_config always maps server names.
                            # For safety, let's assume if it's a list, it implies tools from *any* configured server.
                            # This part of the logic might need to be more sophisticated if a flat list of tool names
                            # (without server context) is provided in tools_config.enabled_tools
                            # For now, if it's a list, we won't filter servers effectively here.
                            pass # Let it fall through to use all_server_configs if required_server_names is empty.

                        filtered_server_configs = {
                            name: cfg for name, cfg in all_server_configs.items()
                            if name in required_server_names
                        } if required_server_names else all_server_configs # Fallback to all if no specific servers identified

                        if not filtered_server_configs and required_server_names:
                            logger.warning(f"Session {session_id}: No matching server configurations found for required servers: {required_server_names}. Will attempt with all if any exist.")
                            filtered_server_configs = all_server_configs # Try all if specific ones not found

                        if not filtered_server_configs:
                             logger.warning(f"Session {session_id}: No server configurations to use for MCP client in ReAct mode after filtering.")
                             # agent_tools will remain empty

                        else:
                            all_tool_server_configs_dict = {
                                name: config.model_dump() for name, config in filtered_server_configs.items()
                            }
                            mcp_client = MultiServerMCPClient(connections=all_tool_server_configs_dict)
                        
                        logger.info(f"Session {session_id}: MCP Client created. Attempting to activate...")
                        try:
                            await mcp_client.__aenter__() # ACTIVATE THE CLIENT
                            self.sessions[session_id]["mcp_client"] = mcp_client # Store it first
                            
                            # Extract flat list of tool names for the factory
                            tool_names_to_enable: List[str] = []
                            if isinstance(tools_config.get("enabled_tools"), dict): # Assuming enabled_tools is a dict like globally_active_tools
                                for server_name, tool_list_details in tools_config["enabled_tools"].items():
                                    for tool_detail in tool_list_details:
                                        if isinstance(tool_detail, dict) and "name" in tool_detail:
                                            tool_names_to_enable.append(tool_detail["name"])
                            elif isinstance(tools_config.get("enabled_tools"), list): # If it's already a flat list
                                 tool_names_to_enable = [t_name for t_name in tools_config["enabled_tools"] if isinstance(t_name, str)]


                            logger.info(f"Session {session_id}: Extracted tool names for ReAct factory: {tool_names_to_enable}")

                            tool_factory = MCPServerToolFactory(client=mcp_client, enabled_tools_list=tool_names_to_enable)
                            agent_tools = tool_factory.create_tools()
                            logger.info(f"Session {session_id}: Created {len(agent_tools)} tools for ReAct agent.")
                        except Exception as e:
                            logger.error(f"Session {session_id}: Error initializing MCP Client: {e}. Falling back.", exc_info=True)
                            raw_agent_executor = None # Ensure it's None on error
                else:
                    logger.info(f"Session {session_id}: No tools_config or enabled_tools provided for ReAct agent.")

                if not current_llm:
                    logger.error(f"Session {session_id}: LLM not available. Cannot create ReAct agent.")
                    self.sessions[session_id].update({
                        "agent_executor": None, "raw_agent_executor": None, "mcp_client": mcp_client,
                        # llm_config_id_used, etc. are already set or preserved
                    })
                    return self.sessions[session_id]

                logger.info(f"Session {session_id}: Preparing to create ReAct agent with {len(agent_tools)} tools.")
                react_prompt = hub.pull("hwchase17/react")
                # Using CustomReActParser for consistency, if it handles edge cases better for tool inputs.
                # create_react_agent will use its default parser if output_parser is None.
                custom_parser = CustomReActParser()
                agent = create_react_agent(current_llm, agent_tools, react_prompt, output_parser=custom_parser) 
                
                raw_agent_executor = AgentExecutor(
                    agent=agent, 
                    tools=agent_tools, 
                    verbose=True, 
                    handle_parsing_errors=True # Standard handling for AgentExecutor
                )
                logger.info(f"Session {session_id}: ReAct agent created.")

            # Default to a ReAct/Tool-using agent (using OpenAI Tools agent structure as per user reference)
            else: 
                agent_tools: List[BaseTool] = [] 
                logger.info(f"Session {session_id}: Mode is not 'json' or 'react' or no data_source for json or react. Creating ReAct/Tool-using agent.")
                
                # Log current state of tool configurations before deciding effective_tools_config_to_use
                logger.debug(f"Session {session_id}: Checking tool configs. Session tools_config: {tools_config}")
                logger.debug(f"Session {session_id}: Checking tool configs. Global self.globally_active_tools: {self.globally_active_tools}")

                effective_tools_config_to_use = None
                if tools_config and tools_config.get("enabled_tools"):
                    logger.info(f"Session {session_id}: Using session-specific tools_config: {tools_config['enabled_tools']}")
                    effective_tools_config_to_use = tools_config["enabled_tools"]
                elif self.globally_active_tools:
                    logger.info(f"Session {session_id}: No session-specific tools_config. Falling back to globally_active_tools: {self.globally_active_tools}")
                    effective_tools_config_to_use = self.globally_active_tools
                else:
                    logger.info(f"Session {session_id}: No session-specific or global tools configured.")

                if effective_tools_config_to_use:
                    logger.info(f"Session {session_id}: Initializing MCP Client for default agent tools: {effective_tools_config_to_use}")
                    all_server_configs = self.config_manager.get_all_tool_server_configs()
                    if not all_server_configs:
                        logger.warning(f"Session {session_id}: No tool server configurations found for default agent.")
                    else:
                        # Determine required server names from effective_tools_config_to_use
                        required_server_names: List[str] = []
                        if isinstance(effective_tools_config_to_use, dict):
                            required_server_names = list(effective_tools_config_to_use.keys())
                        
                        filtered_server_configs = {
                            name: cfg for name, cfg in all_server_configs.items()
                            if name in required_server_names
                        } if required_server_names else all_server_configs # Fallback to all if no specific servers identified

                        if not filtered_server_configs and required_server_names:
                            logger.warning(f"Session {session_id}: No matching server configurations found for required servers: {required_server_names}. Will attempt with all if any exist.")
                            filtered_server_configs = all_server_configs

                        if not filtered_server_configs:
                            logger.warning(f"Session {session_id}: No server configurations to use for MCP client in default mode after filtering.")
                            # agent_tools will remain empty

                        else:
                            all_tool_server_configs_dict = {
                                name: config.model_dump() for name, config in filtered_server_configs.items()
                            }
                            mcp_client = MultiServerMCPClient(connections=all_tool_server_configs_dict)
                        
                        logger.info(f"Session {session_id}: MCP Client created. Attempting to activate...")
                        try:
                            await mcp_client.__aenter__() # ACTIVATE THE CLIENT
                            self.sessions[session_id]["mcp_client"] = mcp_client # Store it first
                            
                            # Extract flat list of tool names for the factory
                            tool_names_to_enable: List[str] = []
                            if isinstance(effective_tools_config_to_use, dict):
                                for server_name, tool_list in effective_tools_config_to_use.items():
                                    for tool_info in tool_list:
                                        if isinstance(tool_info, dict) and "name" in tool_info:
                                            tool_names_to_enable.append(tool_info["name"])
                                        else:
                                            logger.warning(f"Session {session_id}: Malformed tool_info {tool_info} in effective_tools_config for server {server_name}")
                            else:
                                logger.warning(f"Session {session_id}: effective_tools_config_to_use is not a dict: {effective_tools_config_to_use}")
                            
                            logger.info(f"Session {session_id}: Extracted tool names for default factory: {tool_names_to_enable}")

                            tool_factory = MCPServerToolFactory(client=mcp_client, enabled_tools_list=tool_names_to_enable)
                            agent_tools = tool_factory.create_tools()
                        except Exception as e:
                            logger.error(f"Session {session_id}: Error initializing MCP Client: {e}. Falling back.", exc_info=True)
                            raw_agent_executor = None # Ensure it's None on error
                else:
                    logger.info(f"Session {session_id}: No effective tools_config (session or global). No MCP tools will be created for ReAct/Tool-using agent.")
                
                if not current_llm:
                    logger.error(f"Session {session_id}: LLM not available. Cannot create ReAct/Tool-using agent components.")
                    # Update session state to reflect failure
                    self.sessions[session_id].update({
                        "agent_executor": None, "raw_agent_executor": None, "mcp_client": None,
                        "llm_config_id_used": llm_config_id or (self.config_manager.get_default_llm_config().config_id if self.config_manager.get_default_llm_config() else None),
                        "tools_config_used": tools_config,
                        "agent_mode_used": agent_mode, # Store the mode that was attempted
                        "agent_data_source_used": agent_data_source
                    })
                    return self.sessions[session_id]

                # If agent_tools is empty, use a simple chain instead of an agent that requires tools
                if not agent_tools:
                    logger.info(f"Session {session_id}: No tools available. Creating a SimpleChainExecutor instead of OpenAI Tools agent.")
                    # Create a very basic prompt for the LLM
                    # Ensure MessagesPlaceholder for "chat_history" is included if SimpleChainExecutor expects it
                    # and RunnableWithMessageHistory will wrap it.
                    simple_prompt = ChatPromptTemplate.from_messages([
                        ("system", "You are a helpful assistant."),
                        MessagesPlaceholder(variable_name="chat_history", optional=True),
                        ("human", "{input}")
                    ])
                    # SimpleChainExecutor expects chain and llm. The chain here is prompt | llm.
                    simple_chain = simple_prompt | current_llm
                    raw_agent_executor = SimpleChainExecutor(prompt_template=simple_prompt, llm_instance=current_llm)
                    logger.info(f"Session {session_id}: SimpleChainExecutor created for basic LLM interaction.")
                else:
                    logger.info(f"Session {session_id}: Preparing to create ReAct/Tool-using agent (via OpenAI Tools structure) with {len(agent_tools)} tools.")
                    prompt = hub.pull("hwchase17/openai-tools-agent")
                    agent = create_openai_tools_agent(current_llm, agent_tools, prompt)

                    raw_agent_executor = AgentExecutor( # This is the executor before history
                        agent=agent, 
                        tools=agent_tools, 
                        verbose=True, 
                        handle_parsing_errors=True
                    )
                    logger.info(f"Session {session_id}: ReAct/Tool-using agent (via OpenAI Tools structure) created.")

            # After creating raw_agent_executor (either JSON or ReAct/Tool-using style)
            # Wrap it with RunnableWithMessageHistory if it was successfully created
            if raw_agent_executor:
                agent_executor_with_history = RunnableWithMessageHistory(
                    raw_agent_executor, # Pass the created AgentExecutor (JSON or ReAct/Tool-using)
                    lambda sid_from_runnable: self.sessions[sid_from_runnable]["memory_saver"],
                    input_messages_key="input", # Corrected to 'input' based on create_json_agent and openai_tools_agent examples
                    history_messages_key="chat_history",
                    # output_messages_key="output" # Usually not needed if the agent returns a dict with 'output'
                )
                self.sessions[session_id].update({
                    "agent_executor": agent_executor_with_history, 
                    "raw_agent_executor": raw_agent_executor, # Store the non-history executor too
                    "mcp_client": mcp_client, # Store the active client for this session (primarily for non-JSON agents)
                    # llm, memory_saver, chat_history_display already set or preserved
                    # llm_config_id_used, tools_config_used, etc., are already set from the start of session_needs_recreation block
                })
                logger.info(f"Session {session_id}: AgentExecutor wrapped with history and session updated.")
            else:
                # This case means raw_agent_executor was not created (e.g. JSON agent failed and no fallback, or LLM failed)
                # Ensure session reflects no usable executor
                self.sessions[session_id]["agent_executor"] = None
                self.sessions[session_id]["raw_agent_executor"] = None
                # mcp_client might be None or an instance if tool setup succeeded but agent creation failed later
                self.sessions[session_id]["mcp_client"] = mcp_client 
                logger.warning(f"Session {session_id}: No agent executor could be created/configured. Session will lack an agent.")
        
        else: # Session exists and no relevant config changed
            logger.info(f"Session {session_id}: Reusing existing session components.")
            self.sessions[session_id].setdefault("chat_messages_for_log", [])
            self.sessions[session_id].setdefault("memory_saver", ChatMessageHistory())

        return self.sessions[session_id]
    
    def ask_agent(self, session_id: str, question: str, tools_config: Dict[str, Any], 
                  llm_config_id: Optional[str] = None,
                  agent_mode: Optional[str] = None, # New
                  agent_data_source: Optional[Union[str, Dict]] = None # New
                 ) -> str:
        logger.warning("Synchronous ask_agent is deprecated. Use astream_ask_agent_events.")
        future = self.submit_request(session_id, question, tools_config, llm_config_id, agent_mode, agent_data_source)
        try:
            return future.result(timeout=120) 
        except Exception as e:
            logger.error(f"Error getting result from future: {e}")
            return f"Error: {str(e)}"

    async def astream_ask_agent_events(
        self, session_id: str, question: str, 
        tools_config: Dict[str, Any], 
        output_stream_fn: callable,
        llm_config_id: Optional[str] = None,
        agent_mode: Optional[str] = None, # New
        agent_data_source: Optional[Union[str, Dict]] = None # New
    ) -> None: # MODIFIED: Changed return type from AsyncGenerator to None
        """
        Asynchronously asks the agent a question and streams events using a callback.
        Events (tokens, errors, etc.) are sent via the output_stream_fn.
        """
        logger.info(f"---> [SERVICE ENTRY] astream_ask_agent_events ENTERED for session {session_id}") 
        
        logger.info(f"astream_ask_agent_events for session {session_id} CALLED with q: '{question[:50]}'. LLM: {llm_config_id}, Mode: {agent_mode}")

        from ..utils.custom_event_handler import EventType # Ensure EventType is in scope

        try:
            logger.info(f"astream_ask_agent_events for session {session_id}: ENTERING main try block.")
            final_response_content = None # INITIALIZE HERE

            custom_handler = CustomAsyncIteratorCallbackHandler(output_stream_fn=output_stream_fn)
            # MCPEventCollector is for collecting a final response, can be used alongside
            mcp_event_collector = MCPEventCollector()
            callbacks = [custom_handler, mcp_event_collector]
            
            session_data = await self._get_or_create_session_components(
                session_id, tools_config, llm_config_id, agent_mode, agent_data_source
            )
            agent_executor = session_data.get("agent_executor")
            raw_agent_executor = session_data.get("raw_agent_executor") # Get the raw executor before history wrapping

            if not agent_executor:
                logger.error(f"Session {session_id}: Agent executor could not be created. Cannot stream.")
                output_stream_fn(EventType.ERROR, {"error": "Agent could not be initialized for streaming."})
                # Send an END event to signal termination to the queue processor in main.py
                output_stream_fn(EventType.END, {"content": "Stream terminated due to agent initialization error."}) 
                return

            input_data = {"input": question}
            
            config_for_stream = {
                "callbacks": callbacks, # Callbacks might still be useful for logging/collecting with astream
                "configurable": {"session_id": session_id}
            }
            
            # === Conditional Streaming Logic ===
            if isinstance(raw_agent_executor, SimpleChainExecutor):
                logger.info(f"Session {session_id}: Using agent_executor.astream() for SimpleChainExecutor.")
                accumulated_content = ""
                stream_chunk_count = 0
                try:
                    async for chunk in agent_executor.astream(input_data, config=config_for_stream):
                        stream_chunk_count += 1
                        # Handle different possible chunk types from astream
                        chunk_content = None
                        if isinstance(chunk, AIMessageChunk):
                            chunk_content = chunk.content
                        elif isinstance(chunk, str):
                            chunk_content = chunk
                        elif isinstance(chunk, dict) and 'content' in chunk:
                            chunk_content = chunk.get('content', '')
                        elif hasattr(chunk, 'content'):
                            chunk_content = getattr(chunk, 'content', '')

                        if chunk_content is not None and chunk_content != "": # Ensure we have actual content
                            logger.debug(f"Session {session_id}: SimpleChain stream chunk #{stream_chunk_count} content: '{chunk_content}'")
                            output_stream_fn(EventType.TOKEN, chunk_content)
                            accumulated_content += chunk_content
                        else:
                             logger.debug(f"Session {session_id}: SimpleChain stream chunk #{stream_chunk_count} was empty or None. Type: {type(chunk)}")

                    logger.info(f"Session {session_id}: SUCCESSFULLY COMPLETED iteration of SimpleChainExecutor.astream. Total chunks: {stream_chunk_count}")
                    final_response_content = accumulated_content # Use accumulated content
                except Exception as e_simple_stream:
                    logger.error(f"Session {session_id}: Error during SimpleChainExecutor.astream(): {e_simple_stream}", exc_info=True)
                    # Send error via output_stream_fn
                    output_stream_fn(EventType.ERROR, {"error": f"Error during simple stream: {str(e_simple_stream)}"})
                    # Signal termination
                    output_stream_fn(EventType.END, {"content": "Stream terminated due to simple stream error."}) 
                    return # Exit after error

            else: # Use astream_events for regular agents (ReAct, OpenAI Tools, JSON)
                logger.info(f"Session {session_id}: Using agent_executor.astream_events() for agent type: {type(raw_agent_executor).__name__}.")
                stream_event_count = 0
                # This loop handles events via callbacks, but we still need to iterate to drive it
                # and potentially capture final_response_content if MCPEventCollector fails.
                async for event in agent_executor.astream_events(
                    input_data, version="v1", config=config_for_stream
                ):
                    stream_event_count += 1
                    logger.debug(f"Session {session_id}: Langchain event #{stream_event_count} received by service: {event.get('event')} - Name: {event.get('name')}")
                    
                    # Capture final response from the event stream (fallback mechanism)
                    if event["event"] == "on_chain_end":
                        parent_ids = event.get("parent_ids")
                        # Check if it's the end of the RunnableWithMessageHistory or an event without parents (likely top-level)
                        if event.get("name") == "RunnableWithMessageHistory" or not parent_ids: 
                            outputs = event.get("data", {}).get("output", {})
                            captured_content = None
                            if isinstance(outputs, dict) and "content" in outputs:
                                captured_content = outputs["content"]
                            elif isinstance(outputs, dict) and "output" in outputs: # Handle nested 'output' sometimes seen
                                captured_content = outputs["output"]
                            elif hasattr(outputs, 'content'):
                                captured_content = outputs.content
                            
                            if captured_content is not None:
                                final_response_content = captured_content # Update if found
                                logger.info(f"Session {session_id}: Captured potential final_response_content from on_chain_end event: {final_response_content[:100] if final_response_content else 'None'}")

                logger.info(f"Session {session_id}: SUCCESSFULLY COMPLETED iteration of agent_executor.astream_events. Total events processed by service: {stream_event_count}")
                
                # If final_response_content wasn't captured via the event, try the collector
                if not final_response_content:
                    collected_output = mcp_event_collector.get_final_output()
                    if collected_output:
                        final_response_content = collected_output
                        logger.info(f"Session {session_id}: Using final response from MCPEventCollector: {final_response_content[:100] if final_response_content else 'None'}")


            # === Send Final Event (Common Logic) ===
            # This part runs after either the astream or astream_events loop finishes successfully
            if final_response_content is not None: # Check if content was actually captured/accumulated
                logger.info(f"Session {session_id}: Sending final CHAIN_END event via output_stream_fn with content: {str(final_response_content)[:70]}...")
                try:
                    # Ensure data is serializable (should be string here)
                    output_stream_fn(EventType.CHAIN_END, {"content": str(final_response_content)}) 
                except NameError: 
                    logger.warning("EventType not defined when sending final CHAIN_END event. Importing.")
                    from mcp_web_app.utils.custom_event_handler import EventType 
                    output_stream_fn(EventType.CHAIN_END, {"content": str(final_response_content)})
                except Exception as e_send_final:
                    logger.error(f"Session {session_id}: Error sending final CHAIN_END event: {e_send_final}", exc_info=True)
            else:
                logger.warning(f"Session {session_id}: No final_response_content captured or accumulated after stream completion. No specific CHAIN_END event sent by service.")
                # Maybe send a generic END event here? Or rely on the one potentially sent from main.py's finally block?
                # Let's send a generic END from here to be safe if no content.
                output_stream_fn(EventType.END, {"content": "Stream finished without specific final content."})


            # Existing logic to update history log (can be removed if RWMH handles it)
            # collected_output = mcp_event_collector.get_final_output() # Already checked above for astream_events case
            # ... (rest of history logging can likely be removed as RWMH should handle memory) ...
            logger.debug(f"Session {session_id}: History should be managed by RunnableWithMessageHistory now.")

        except BaseException as e_agent_stream:
            # Log the exception with full traceback
            exc_type, exc_value, exc_traceback = sys.exc_info()
            traceback_details = traceback.format_exception(exc_type, exc_value, exc_traceback)
            logger.error(f"astream_ask_agent_events for session {session_id}: CRITICAL ERROR during agent execution or event streaming: {type(e_agent_stream).__name__} - {e_agent_stream}\\n{''.join(traceback_details)}", exc_info=False) # Log traceback manually
            try:
                output_stream_fn(EventType.ERROR, {"error": f"Critical agent error: {str(e_agent_stream)}"})
                output_stream_fn(EventType.END, {"content": "Stream terminated due to critical agent error."})
            except Exception as ex_send_error:
                logger.error(f"astream_ask_agent_events for session {session_id}: FAILED TO SEND error event via output_stream_fn after critical error: {ex_send_error}", exc_info=True)
        finally:
            logger.info(f"astream_ask_agent_events for session {session_id}: NORMALLY EXITING.")

    def submit_request(self, session_id: Optional[str], question: str, tools_config: Dict[str, Any], 
                       llm_config_id: Optional[str], 
                       agent_mode: Optional[str], # New
                       agent_data_source: Optional[Union[str, Dict]] # New
                      ) -> Future:
        future = Future()
        if not self.dispatcher_thread or not self.dispatcher_thread.is_alive():
            logger.error("Dispatcher thread is not running. Cannot process request.")
            future.set_exception(RuntimeError("Dispatcher thread not running."))
            return future
            
        if session_id is None:
            session_id = f"request-{uuid.uuid4()}" # Ensure session_id for queue item
            logger.info(f"No session_id provided for submit_request, generated: {session_id}")

        self.request_queue.put((session_id, question, tools_config, llm_config_id, agent_mode, agent_data_source, future))
        return future

    def _process_queue(self):
        if not self.loop:
            logger.error("Asyncio event loop not set for dispatcher thread.")
            return
        asyncio.set_event_loop(self.loop)

        while True:
            try: # Added agent_mode, agent_data_source
                session_id, question, tools_config, llm_config_id, agent_mode, agent_data_source, future = self.request_queue.get()
                if question is None and session_id is None: # Refined stop signal check
                    logger.info("Dispatcher thread received stop signal.")
                    break
                
                logger.info(f"Dispatcher: Processing request for session '{session_id}', question: '{question[:30]}...', mode: {agent_mode}")
                try:
                    logger.warning("Synchronous request processing via _process_queue is not designed for streaming.")
                    
                    session_components_coro = self._get_or_create_session_components(
                        session_id, tools_config, llm_config_id, agent_mode, agent_data_source
                    )
                    session_components = asyncio.run_coroutine_threadsafe(session_components_coro, self.loop).result()
                    
                    agent_executor = session_components["agent_executor"]
                    memory_saver = session_components["memory_saver"]
                    chat_messages_for_log = session_components["chat_messages_for_log"] # For our manual logging/display

                    if not agent_executor:
                        raise RuntimeError("Agent executor not available.")

                    inputs = {"input": question}
                    response_coro = agent_executor.ainvoke(inputs) # AgentExecutor ainvoke
                    response_dict = asyncio.run_coroutine_threadsafe(response_coro, self.loop).result()
                    
                    answer = ""
                    if isinstance(response_dict, dict) and "output" in response_dict:
                        answer = response_dict["output"]
                    elif isinstance(response_dict, str): # Should be rare for AgentExecutor
                        answer = response_dict
                    else: # Fallback for AIMessage or other types
                        answer = str(getattr(response_dict, 'content', response_dict))

                    chat_messages_for_log.append(HumanMessage(content=question))
                    chat_messages_for_log.append(AIMessage(content=answer))
                    future.set_result(answer)
                    logger.info(f"Dispatcher: Successfully processed sync request for session '{session_id}'.")

                except Exception as e:
                    logger.error(f"Error processing request in dispatcher: {e}", exc_info=True)
                    future.set_exception(e)
                finally:
                    self.request_queue.task_done()
            except Exception as e: # Catch errors from queue.get() or outer loop
                logger.error(f"Outer loop error in dispatcher thread: {e}", exc_info=True)
                # If future was defined and item retrieved, set exception
                if 'future' in locals() and isinstance(future, Future) and not future.done():
                    future.set_exception(e)
                # Ensure task_done if item was retrieved, even if processing failed early
                if 'session_id' in locals(): # Heuristic: if session_id is defined, item was likely dequeued
                    self.request_queue.task_done()


    def start_dispatcher(self):
        if self.dispatcher_thread and self.dispatcher_thread.is_alive():
            logger.info("Dispatcher thread already running.")
            return

        self.loop = asyncio.new_event_loop()
        self.dispatcher_thread = threading.Thread(target=self._process_queue, daemon=True)
        self.dispatcher_thread.start()
        logger.info("Request dispatcher thread started.")

    def stop_dispatcher(self):
        if self.dispatcher_thread and self.dispatcher_thread.is_alive():
            logger.info("Stopping dispatcher thread...")
            # Sentinel for stop: (None session_id, None question, None tools_config, None llm_config_id, None agent_mode, None agent_data_source, None future)
            self.request_queue.put((None, None, None, None, None, None, None)) 
            self.dispatcher_thread.join(timeout=5)
            if self.dispatcher_thread.is_alive():
                logger.warning("Dispatcher thread did not stop in time.")
            else:
                logger.info("Dispatcher thread stopped.")
        if self.loop and self.loop.is_running(): 
            self.loop.call_soon_threadsafe(self.loop.stop)

    async def close_mcp_clients(self):
        logger.info("Attempting to close active MCP clients in sessions...")
        closed_clients = 0
        for session_id, session_data in self.sessions.items():
            mcp_client = session_data.get("mcp_client")
            if mcp_client and hasattr(mcp_client, "__aexit__") and \
               not getattr(mcp_client, "_closed", False) and \
               not getattr(mcp_client, "_explicitly_closed_in_recreation", False): # CHECK FLAG
                try:
                    logger.info(f"Closing MCP client for session {session_id}...")
                    await mcp_client.__aexit__(None, None, None) # type: ignore
                    setattr(mcp_client, "_closed", True) # Mark as closed by general shutdown
                    closed_clients += 1
                    logger.info(f"MCP client for session {session_id} closed.")
                except Exception as e:
                    logger.error(f"Error closing MCP client for session {session_id}: {e}", exc_info=True)
        if closed_clients > 0:
            logger.info(f"Successfully closed {closed_clients} MCP clients.")
        else:
            logger.info("No active MCP clients found in sessions to close.")

    def shutdown(self):
        """Gracefully shuts down the agent service components."""
        logger.info("LangchainAgentService shutdown initiated.")
        self.stop_dispatcher()
        # close_mcp_clients is async, so it needs to be run in an event loop.
        # If shutdown is called from a sync context, we might need to create a new loop
        # or use asyncio.run_coroutine_threadsafe if called from a running loop in another thread.
        # For simplicity, assuming this might be called from a context where a loop is accessible
        # or that stop_dispatcher is the primary synchronous part.
        # If main.py's shutdown_event is async, it can await self.close_mcp_clients()
        logger.info("Dispatcher stopped. MCP client closure should be handled by the caller if async.")
        # A more robust solution for async cleanup from sync shutdown:
        # try:
        #     loop = asyncio.get_event_loop()
        #     if loop.is_running():
        #         asyncio.ensure_future(self.close_mcp_clients(), loop=loop)
        #     else:
        #         loop.run_until_complete(self.close_mcp_clients())
        # except RuntimeError: # No event loop
        #     asyncio.run(self.close_mcp_clients())
    
    async def async_shutdown(self):
        """Async version of shutdown that properly closes MCP clients."""
        logger.info("LangchainAgentService async_shutdown initiated.")
        self.stop_dispatcher()
        await self.close_mcp_clients()
        logger.info("LangchainAgentService async_shutdown completed.")

# Fallback MemorySaver if langgraph is not installed
try:
    from langgraph.checkpoint.memory import MemorySaver # Already imported
except ImportError:
    logger.info("Defining local MemorySaver (already attempted above, this is a safeguard).")
    if not hasattr(sys.modules[__name__], 'MemorySaver'): # Avoid redefinition if already defined
        class MemorySaver:
            def __init__(self):
                self.storage: Dict[str, List[BaseMessage]] = {}
                logger.debug("Initialized local MemorySaver.")

            async def aget(self, config: Dict[str, Any]) -> Optional[List[BaseMessage]]:
                session_id = config.get("configurable", {}).get("session_id")
                if session_id:
                    messages = self.storage.get(session_id)
                    logger.debug(f"MemorySaver aget for session '{session_id}': Found {len(messages) if messages else 0} messages.")
                    return messages
                logger.debug(f"MemorySaver aget: No session_id in config: {config}")
                return None

            async def aput(self, messages_map: Dict[str, List[BaseMessage]], config: Dict[str, Any]) -> None:
                session_id = config.get("configurable", {}).get("session_id")
                messages = messages_map.get("messages") # messages_map is {"messages": [BaseMessage,...]}
                if session_id and messages is not None: # Ensure messages is not None
                    self.storage[session_id] = messages
                    logger.debug(f"MemorySaver aput for session '{session_id}': Stored {len(messages)} messages.")
                else:
                    logger.warning(f"MemorySaver aput: Missing session_id or messages. Config: {config}, MsgMapKeys: {messages_map.keys()}")
            
            # Sync versions for any legacy use, though async is primary
            def get(self, config: Dict[str, Any]) -> Optional[List[BaseMessage]]:
                # Best effort to run async in sync context if needed by a caller
                try:
                    loop = asyncio.get_running_loop()
                    if loop.is_running(): # If called from within an async context
                        # This is problematic; direct call to async from sync is bad.
                        # This sync `get` should ideally not be used from an async path.
                        # For now, log a warning.
                        logger.warning("Synchronous MemorySaver.get called from a running asyncio loop. This may cause issues.")
                        # Fallback: create a new loop to run, which is also not ideal.
                        return asyncio.run(self.aget(config))
                except RuntimeError: # No running event loop
                    return asyncio.run(self.aget(config))
                return asyncio.run(self.aget(config)) # Default path if no loop or other issues

            def put(self, messages_map: Dict[str, List[BaseMessage]], config: Dict[str, Any]) -> None:
                try:
                    loop = asyncio.get_running_loop()
                    if loop.is_running():
                        logger.warning("Synchronous MemorySaver.put called from a running asyncio loop. This may cause issues.")
                        asyncio.run(self.aput(messages_map, config)) # Not ideal
                        return
                except RuntimeError:
                    asyncio.run(self.aput(messages_map, config))
                asyncio.run(self.aput(messages_map, config)) # Default path 