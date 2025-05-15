import sys
import os
# Ensure the project root is in sys.path for absolute imports

"""
LangChain Agent Service for MCP web application.
Provides agent-based chat with multiple LLM and tool options.
"""
import os
from dotenv import load_dotenv
import asyncio
import logging
import uuid
from typing import Dict, Any, Optional, Union, List, AsyncGenerator, Tuple

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from mcp_web_app.services.config_manager import ConfigManager
from mcp_web_app.models.models import LLMConfig
from mcp_web_app.utils.custom_event_handler import EventType
from .agent.parser import CustomReActParser
from .agent.callbacks import StreamingCallback, MCPEventCollector
from .agent.chain_executor import SimpleChainExecutor
from .agent.session_manager import needs_session_recreation, create_new_session_dict, MemorySaver
from .agent.dispatcher import RequestDispatcher
from .agent.streaming import stream_agent_response
from .agent.tools import get_tools_for_config, close_mcp_client
from .agent.llm_factory import create_llm_from_config
from .agent.agent_factory import create_agent_for_mode

# Explicitly load .env from the project root
dotenv_path = os.path.join(os.path.dirname(__file__), '..', '..', '.env')
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path=dotenv_path)

# Initialize logger
logger = logging.getLogger(__name__)

class LangchainAgentService:
    """
    Service for creating and managing LangChain agents.
    """
    
    def __init__(self, config_manager: ConfigManager):
        """
        Initialize the LangChain agent service.
        
        Args:
            config_manager: Configuration manager for LLM and tool settings
        """
        self.config_manager = config_manager
        self._llm_cache: Dict[str, Any] = {}
        self.llm = None  # Default LLM instance
        
        # Fast response templates
        self._fast_responses = {
            "ping": "pong",
            "hello": "Hello! How can I help you today?",
            "hi": "Hi there! How can I assist you?",
            "test": "I'm working! How can I help you?"
        }
        
        # Session storage
        self.sessions: Dict[str, Dict[str, Any]] = {}
        
        # Request dispatcher
        self.dispatcher = RequestDispatcher(self)
        
        # Try to load the default LLM
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(self._get_llm())
            else:
                loop.run_until_complete(self._get_llm())
        except Exception as e:
            logger.error(f"Failed to initialize default LLM: {e}", exc_info=True)
        
        # Start the dispatcher
        self.start_dispatcher()
        logger.info(f"LangchainAgentService __init__ completed for instance {id(self)}. Sessions initialized: {hasattr(self, 'sessions')}")
    
    async def _determine_effective_llm_config_id(self, llm_config_id: Optional[str]) -> str:
        """
        Determine which LLM config to use.
        
        Args:
            llm_config_id: Requested LLM config ID, or None for default
            
        Returns:
            The effective LLM config ID to use
        """
        # If a specific config was requested, use it
        if llm_config_id:
            return llm_config_id
            
        # Otherwise use the default config
        default_config = self.config_manager.get_default_llm_config()
        if default_config:
            return default_config.config_id
            
        # Fall back to a known default if no default is specified
        return "default"
    
    async def _get_llm(self, llm_config_id: Optional[str] = None) -> Optional[BaseChatModel]:
        """
        Get an LLM instance for the given config ID.
        
        Args:
            llm_config_id: LLM config ID, or None for default
            
        Returns:
            An LLM instance, or None if creation fails
        """
        # Determine which config to use
        effective_llm_config_id = await self._determine_effective_llm_config_id(llm_config_id)
        
        # Check if we already have this LLM cached
        if effective_llm_config_id in self._llm_cache:
            logger.debug(f"Using cached LLM for '{effective_llm_config_id}'")
            return self._llm_cache[effective_llm_config_id]
        
        # Load the LLM config
        llm_config = self.config_manager.get_llm_config_by_id(effective_llm_config_id)
        if not llm_config:
            logger.error(f"No LLM config found for '{effective_llm_config_id}'")
            return None
        
        # Create the LLM instance
        created_llm = await create_llm_from_config(llm_config, effective_llm_config_id)
        
        # Cache the LLM if creation was successful
        if created_llm:
            self._llm_cache[effective_llm_config_id] = created_llm
            self.llm = created_llm  # Update the current LLM reference
            logger.info(f"LLM instance created and cached for '{effective_llm_config_id}'")
        else:
            logger.error(f"Failed to create LLM instance for '{effective_llm_config_id}'")
        
        return created_llm
    
    async def _check_session_reusability_and_get_llm(
        self, 
        session_id: str, 
        llm_config_id: Optional[str],
        tools_config: Dict[str, Any],
        agent_mode: Optional[str],
        agent_data_source: Optional[Union[str, Dict]]
    ) -> Tuple[str, Optional[BaseChatModel], str, Optional[Dict[str, Any]]]:
        logger.debug(f"Instance {id(self)} entering _check_session_reusability_and_get_llm. Has 'sessions' attr: {hasattr(self, 'sessions')}")
        if not hasattr(self, 'sessions'):
            logger.critical(f"Instance {id(self)} in _check_session_reusability_and_get_llm: CRITICAL - self.sessions attribute is missing. This indicates a severe initialization problem or the attribute was deleted.")
            raise AttributeError(f"'LangchainAgentService' instance (id: {id(self)}) has no attribute 'sessions'. Initialization might have failed or the attribute was improperly deleted.")
        
        # Proceed to use self.sessions, now that we've confirmed it exists via hasattr
        logger.debug(f"Type of self.sessions: {type(self.sessions)}")
        # else: # This else block is now covered by the check above
            # logger.error(f"Instance {id(self)} in _check_session_reusability_and_get_llm: FATAL - self.sessions does NOT exist!")
            # If sessions attribute is missing, we cannot proceed. 
            # This will likely cause the original AttributeError when self.sessions.get is called.
            # Consider raising an immediate exception or returning an error state here
            # For now, it will fall through and error on the next line as before, but with more logging.

        session = self.sessions.get(session_id)
        session_needs_rebuild = needs_session_recreation(
            session, llm_config_id, tools_config, agent_mode, agent_data_source
        )
        effective_llm_config_id = await self._determine_effective_llm_config_id(llm_config_id)

        if not session_needs_rebuild and session:
            logger.info(f"Session {session_id}: Reusing existing session components")
            session.setdefault("chat_messages_for_log", [])
            session.setdefault("memory_saver", MemorySaver())
            return "REUSE", None, effective_llm_config_id, session

        # Session needs rebuild or is new
        current_llm = await self._get_llm(effective_llm_config_id)
        if not current_llm:
            logger.error(f"Session {session_id}: LLM init failed. Session structure will be updated/created without LLM.")
            return "SETUP_NEEDED_NO_LLM", None, effective_llm_config_id, None 

        return "SETUP_NEEDED", current_llm, effective_llm_config_id, None

    async def _update_session_dictionary_structure(
        self,
        session_id: str,
        current_llm: Optional[BaseChatModel], # Can be None if LLM init failed
        effective_llm_config_id: str,
        tools_config: Dict[str, Any],
        agent_mode: Optional[str],
        agent_data_source: Optional[Union[str, Dict]]
    ):
        """Initializes or updates the session dictionary in self.sessions."""
        session_exists = session_id in self.sessions
        
        if session_exists:
            logger.info(f"Session {session_id}: Re-building session structure with LLM: {current_llm is not None}")
            session_data = self.sessions[session_id]
            
            old_mcp_client = session_data.get("mcp_client")
            if old_mcp_client and hasattr(old_mcp_client, "__aexit__"):
                logger.info(f"Session {session_id}: Closing old MCP client during rebuild")
                try:
                    await close_mcp_client(old_mcp_client)
                    # Mark as explicitly closed to avoid double closing in shutdown
                    setattr(old_mcp_client, "_explicitly_closed_in_recreation", True) 
                except Exception as e:
                    logger.error(f"Session {session_id}: Error closing old MCP client: {e}", exc_info=True)

            # Preserve existing history and memory
            existing_memory_saver = session_data.get("memory_saver", MemorySaver())
            existing_chat_messages = session_data.get("chat_messages_for_log", [])

            session_data.update({
                "llm": current_llm,
                "agent_executor": None, # Will be set by _configure_agent_for_session if LLM is available
                "raw_agent_executor": None,
                "mcp_client": None, # Will be set by _configure_agent_for_session if ReAct agent
                "memory_saver": existing_memory_saver,
                "chat_messages_for_log": existing_chat_messages,
                "llm_config_id_used": effective_llm_config_id,
                "tools_config_used": tools_config,
                "agent_mode_used": agent_mode,
                "agent_data_source_used": agent_data_source
            })
        else:
            logger.info(f"Session {session_id}: Creating new session structure with LLM: {current_llm is not None}")
            self.sessions[session_id] = create_new_session_dict(
                current_llm, effective_llm_config_id, tools_config, agent_mode, agent_data_source
            )
            # create_new_session_dict already sets agent_executor etc. to None if current_llm is None

    async def _configure_agent_for_session(
        self,
        session_id: str,
        current_llm: BaseChatModel, # This is guaranteed to be non-None when called
        agent_mode: Optional[str],
        agent_data_source: Optional[Union[str, Dict]],
        tools_config: Dict[str, Any]
    ):
        """Configures and sets the agent executor in self.sessions[session_id]."""
        session_data = self.sessions[session_id] # Should exist at this point
        agent_tools: List[BaseTool] = []
        mcp_client = None

        if agent_mode == "json" and agent_data_source:
            logger.info(f"Session {session_id}: Setting up JSON agent")
            executors = await create_agent_for_mode(
                "json", current_llm, data_source=agent_data_source,
                memory_getter=lambda sid: session_data["memory_saver"], session_id=session_id
            )
            if executors:
                session_data["agent_executor"], session_data["raw_agent_executor"] = executors
                logger.info(f"Session {session_id}: JSON agent created successfully")
            else:
                logger.error(f"Session {session_id}: Failed to create JSON agent")
        
        elif agent_mode == "react":
            logger.info(f"Session {session_id}: Setting up ReAct agent")
            
            # Get global tool filter
            global_tools_filter = self.config_manager.get_globally_active_tools_filter()
            session_tools_filter = tools_config.get("enabled_tools", {}) # Default to empty dict if not provided
            
            effective_tools_filter = {}
            if global_tools_filter is not None:
                if session_tools_filter: # Both global and session filters exist
                    # Intersect: only include servers present in both
                    # And for each server, if its value is a dict (sub-tool selection), intersect those too
                    # For simplicity here, we'll prioritize session if global allows the server at all.
                    # A more complex intersection might be needed based on filter structure.
                    effective_tools_filter = {}
                    for server_name, session_server_config in session_tools_filter.items():
                        if server_name in global_tools_filter:
                            global_server_config = global_tools_filter[server_name]
                            if isinstance(session_server_config, dict) and isinstance(global_server_config, dict):
                                # If both are dicts, this implies specific tool selection within the server
                                # Only take tools enabled in both. This is a basic intersection of sub-tools.
                                common_sub_tools = { \
                                    tool_key: tool_val \
                                    for tool_key, tool_val in session_server_config.items() \
                                    if tool_key in global_server_config and global_server_config[tool_key] == tool_val and tool_val == True\
                                }
                                if common_sub_tools: # Only add server if there are common enabled tools
                                     effective_tools_filter[server_name] = common_sub_tools
                                elif not any(isinstance(v, dict) for v in session_server_config.values()) and \
                                     not any(isinstance(v, dict) for v in global_server_config.values()) and \
                                     session_server_config == True and global_server_config == True: # Both are simple True flags
                                     effective_tools_filter[server_name] = True
                            elif session_server_config == True and global_server_config == True:
                                # Simpler case: if session enables server and global also enables it
                                effective_tools_filter[server_name] = True
                            # If global_server_config is True, and session_server_config is a dict, allow session's specifics.
                            elif global_server_config == True and isinstance(session_server_config, dict):
                                effective_tools_filter[server_name] = session_server_config
                        # If a server is in session_filter but not in global_tools_filter, it's effectively disabled.
                    logger.info(f"Session {session_id}: Applied global and session tool filters. Effective: {effective_tools_filter}")
                else: # Only global filter exists (session filter is empty or None)
                    effective_tools_filter = global_tools_filter
                    logger.info(f"Session {session_id}: Using global tool filter as session filter is empty. Effective: {effective_tools_filter}")
            else: # No global filter
                effective_tools_filter = session_tools_filter
                logger.info(f"Session {session_id}: No global tool filter. Using session tool filter. Effective: {effective_tools_filter}")

            if not effective_tools_filter: # Check if the effective filter ended up empty
                logger.info(f"Session {session_id}: No tools effectively enabled after applying filters for ReAct agent.")
                # agent_tools will remain empty, leading to default simple chain further down.
            else:
                all_server_configs = self.config_manager.get_all_tool_server_configs()
                if all_server_configs:
                    server_configs_dict = {name: config.model_dump() for name, config in all_server_configs.items()}
                    # Use the effective_tools_filter here
                    agent_tools, mcp_client = await get_tools_for_config(server_configs_dict, effective_tools_filter)
                    session_data["mcp_client"] = mcp_client # Store client
                    if agent_tools:
                        logger.info(f"Session {session_id}: Loaded {len(agent_tools)} tools for ReAct agent")
                        executors = await create_agent_for_mode(
                            "react", current_llm, tools=agent_tools,
                            memory_getter=lambda sid: session_data["memory_saver"], session_id=session_id
                        )
                        if executors:
                            session_data["agent_executor"], session_data["raw_agent_executor"] = executors
                            logger.info(f"Session {session_id}: ReAct agent created successfully")
                        else:
                            logger.error(f"Session {session_id}: Failed to create ReAct agent with tools")
                    else:
                        logger.warning(f"Session {session_id}: No tools loaded for ReAct agent, will use simple chain if no agent set.")
                else:
                    logger.warning(f"Session {session_id}: No tool servers configured for ReAct agent.")

        # For simple chain mode
        else: # Not ReAct, not JSON
            logger.info(f"Session {session_id}: No specific agent configured or ReAct tools missing, using default simple chain.")
            if current_llm: # current_llm is guaranteed non-None here by caller _get_or_create_session_components
                prompt = ChatPromptTemplate.from_messages([
                    MessagesPlaceholder(variable_name="chat_history"),
                    ("user", "{input}")
                ])
                try:
                    logger.debug(f"Session {session_id}: Attempting to create SimpleChainExecutor with LLM: {type(current_llm)}.")
                    simple_executor = SimpleChainExecutor(prompt_template=prompt, llm_instance=current_llm)
                    logger.debug(f"Session {session_id}: SimpleChainExecutor successfully created: {type(simple_executor)}. Assigning to session_data.")
                    session_data["agent_executor"] = simple_executor 
                    session_data["raw_agent_executor"] = simple_executor # For simple chain, they are the same
                    logger.info(f"Session {session_id}: SimpleChainExecutor assigned to session_data.")
                except Exception as e:
                    logger.error(f"Session {session_id}: CRITICAL - Error during SimpleChainExecutor creation or assignment: {e}", exc_info=True)
                    session_data["agent_executor"] = None # Ensure it's None if creation failed
                    session_data["raw_agent_executor"] = None
            else:
                # This case should ideally not be hit if current_llm is guaranteed by caller
                logger.error(f"Session {session_id}: current_llm is None in _configure_agent_for_session when setting up SimpleChain. This is unexpected.")
        
    async def _get_or_create_session_components(
        self, 
        session_id: str, 
        tools_config: Dict[str, Any], 
        llm_config_id: Optional[str] = None,
        agent_mode: Optional[str] = None,
        agent_data_source: Optional[Union[str, Dict]] = None
    ) -> Dict[str, Any]:
        """
        Get or create components for a session using helper methods.
        """
        logger.debug(f"[{session_id}] _get_or_create_session_components called with: llm_config_id='{llm_config_id}', agent_mode='{agent_mode}', tools_config_keys={list(tools_config.keys()) if tools_config else 'None'}")
        status, current_llm, effective_llm_config_id, session_to_return_early = (
            await self._check_session_reusability_and_get_llm(
                session_id, llm_config_id, tools_config, agent_mode, agent_data_source
            )
        )
        logger.debug(f"[{session_id}] _check_session_reusability_and_get_llm returned: status='{status}', current_llm_is_none={current_llm is None}, effective_llm_config_id='{effective_llm_config_id}'")

        if status == "REUSE":
            logger.info(f"[{session_id}] Reusing existing session components.")
            # Ensure session_to_return_early is not None, which _check_... guarantees for "REUSE"
            return session_to_return_early if session_to_return_early is not None else {} 

        # For "SETUP_NEEDED" or "SETUP_NEEDED_NO_LLM", current_llm might be None.
        # effective_llm_config_id is always set.
        logger.debug(f"[{session_id}] Proceeding to update/create session structure. LLM available: {current_llm is not None}")
        await self._update_session_dictionary_structure(
            session_id, current_llm, effective_llm_config_id, tools_config, 
            agent_mode, agent_data_source
        )
        logger.debug(f"[{session_id}] _update_session_dictionary_structure completed.")

        if current_llm: # Only configure agent if LLM is available
            logger.debug(f"[{session_id}] LLM is available, proceeding to _configure_agent_for_session.")
            await self._configure_agent_for_session(
                session_id, current_llm, agent_mode, agent_data_source, tools_config
            )
            logger.debug(f"[{session_id}] _configure_agent_for_session completed.")
        else:
            logger.warning(f"[{session_id}] LLM is NOT available. Agent configuration will be skipped. Session agent_executor will be None.")
        
        # self.sessions[session_id] should now be fully populated or correctly set for no-LLM case
        final_session_data = self.sessions.get(session_id, {})
        logger.debug(f"[{session_id}] _get_or_create_session_components returning: session_data keys={list(final_session_data.keys())}, agent_executor is_none={final_session_data.get('agent_executor') is None}, llm_is_none={final_session_data.get('llm') is None}")
        return final_session_data
    
    def ask_agent(
        self, 
        session_id: str, 
        question: str, 
        tools_config: Dict[str, Any], 
        llm_config_id: Optional[str] = None,
        agent_mode: Optional[str] = None,
        agent_data_source: Optional[Union[str, Dict]] = None
    ) -> str:
        """
        Ask a question to the agent (synchronous).
        
        Args:
            session_id: The session ID
            question: The user's question
            tools_config: Tool configuration
            llm_config_id: LLM config ID, or None for default
            agent_mode: The agent mode (e.g., "json", "react")
            agent_data_source: Data source for data-specific agents
            
        Returns:
            The agent's response
        """
        logger.warning("Synchronous ask_agent is deprecated. Use astream_ask_agent_events.")
        future = self.submit_request(
            session_id, question, tools_config, llm_config_id, agent_mode, agent_data_source
        )
        try:
            return future.result(timeout=120)
        except Exception as e:
            logger.error(f"Error getting result from future: {e}")
            return f"Error: {str(e)}"
    
    async def astream_ask_agent_events(
        self, 
        session_id: str, 
        question: str, 
        tools_config: Dict[str, Any], 
        output_stream_fn: callable,
        llm_config_id: Optional[str] = None,
        agent_mode: Optional[str] = None,
        agent_data_source: Optional[Union[str, Dict]] = None
    ) -> None:
        """
        Stream agent responses as events.
        
        Args:
            session_id: The session ID
            question: The user's question
            tools_config: Tool configuration
            output_stream_fn: Function to call with streaming events
            llm_config_id: LLM config ID, or None for default
            agent_mode: The agent mode (e.g., "json", "react")
            agent_data_source: Data source for data-specific agents
        """
        logger.info(f"astream_ask_agent_events for session {session_id} with query: '{question[:50]}'")
        logger.debug(f"[{session_id}] astream_ask_agent_events called with: llm_config_id='{llm_config_id}', agent_mode='{agent_mode}', tools_config_keys={list(tools_config.keys()) if tools_config else 'None'}, output_stream_fn_is_none={output_stream_fn is None}")
        
        # Check for fast responses
        if question.lower().strip() in self._fast_responses:
            response = self._fast_responses[question.lower().strip()]
            logger.info(f"[{session_id}] Using fast response for query: '{question[:50]}'")
            output_stream_fn(EventType.CHAIN_END.name, {"content": response})
            return
        
        # Get or create session components
        logger.debug(f"[{session_id}] Attempting to get or create session components...")
        session_data = await self._get_or_create_session_components(
            session_id, tools_config, llm_config_id, agent_mode, agent_data_source
        )
        agent_executor = session_data.get("agent_executor")
        llm_instance = session_data.get("llm")
        logger.debug(f"[{session_id}] Session components retrieved/created. agent_executor is_none={agent_executor is None}, llm_instance is_none={llm_instance is None}. Agent type: {type(agent_executor) if agent_executor else 'N/A'}")

        if not agent_executor:
            logger.error(f"[{session_id}] No agent_executor available for session. Cannot stream response. LLM present: {llm_instance is not None}")
            output_stream_fn(EventType.ERROR.name, {"message": "Failed to initialize agent. Please check server logs."})
            return

        if not llm_instance: # Though agent_executor should ideally not be set without an LLM for most cases
             logger.warning(f"[{session_id}] LLM instance is missing in session_data, though agent_executor is present. This might lead to issues.")

        # Stream the agent response
        logger.info(f"[{session_id}] Starting stream_agent_response for query: '{question[:50]}'")
        try:
            await stream_agent_response(session_id, question, session_data, output_stream_fn)
            logger.info(f"[{session_id}] stream_agent_response completed for query: '{question[:50]}'")
        except Exception as e:
            logger.error(f"[{session_id}] Exception during stream_agent_response: {e}", exc_info=True)
            try:
                output_stream_fn(EventType.ERROR.name, {"message": f"An error occurred during streaming: {e}"})
            except Exception as ex_send:
                logger.error(f"[{session_id}] Failed to send error event to client: {ex_send}", exc_info=True)
    
    def submit_request(
        self, 
        session_id: str, 
        question: str, 
        tools_config: Dict[str, Any], 
        llm_config_id: Optional[str] = None,
        agent_mode: Optional[str] = None,
        agent_data_source: Optional[Union[str, Dict]] = None
    ):
        """
        Submit a request to be processed asynchronously.
        
        Args:
            session_id: The session ID
            question: The user's question
            tools_config: Tool configuration
            llm_config_id: LLM config ID, or None for default
            agent_mode: The agent mode (e.g., "json", "react")
            agent_data_source: Data source for data-specific agents
            
        Returns:
            A future that will be resolved with the response
        """
        # Generate a session ID if none was provided
        if session_id is None:
            session_id = f"request-{uuid.uuid4()}"
            logger.info(f"No session_id provided, generated: {session_id}")
        
        # Submit to the dispatcher
        return self.dispatcher.submit_request(
            session_id, question, tools_config, llm_config_id, agent_mode, agent_data_source
        )
    
    def start_dispatcher(self):
        """Start the request dispatcher."""
        self.dispatcher.start()
    
    def stop_dispatcher(self):
        """Stop the request dispatcher."""
        self.dispatcher.stop()
    
    async def close_mcp_clients(self):
        """Close all MCP clients in sessions."""
        logger.info("Closing all active MCP clients in sessions")
        closed_clients = 0
        
        for session_id, session_data in self.sessions.items():
            mcp_client = session_data.get("mcp_client")
            if mcp_client and hasattr(mcp_client, "__aexit__") and \
               not getattr(mcp_client, "_closed", False) and \
               not getattr(mcp_client, "_explicitly_closed_in_recreation", False):
                try:
                    logger.info(f"Closing MCP client for session {session_id}")
                    await close_mcp_client(mcp_client)
                    setattr(mcp_client, "_closed", True)
                    closed_clients += 1
                except Exception as e:
                    logger.error(f"Error closing MCP client for session {session_id}: {e}", exc_info=True)
        
        if closed_clients > 0:
            logger.info(f"Successfully closed {closed_clients} MCP clients")
    
    def shutdown(self):
        """Shutdown the agent service."""
        logger.info("LangchainAgentService shutdown initiated")
        self.stop_dispatcher()
        logger.info("Dispatcher stopped")
    
    async def async_shutdown(self):
        """Asynchronous shutdown of the agent service."""
        logger.info("LangchainAgentService async_shutdown initiated")
        self.stop_dispatcher()
        await self.close_mcp_clients()
        logger.info("LangchainAgentService async_shutdown completed") 