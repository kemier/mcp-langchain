#!/usr/bin/env python3
"""
Session management utilities for agent service.
"""
import logging
import uuid
from typing import Dict, Any, Optional, List, Union

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage
from langchain_community.chat_message_histories import ChatMessageHistory
from langchain.agents import AgentExecutor

# Initialize logger
logger = logging.getLogger(__name__)

def needs_session_recreation(
    session: Optional[Dict[str, Any]], 
    llm_config_id: Optional[str],
    tools_config: Dict[str, Any],
    agent_mode: Optional[str],
    agent_data_source: Optional[Union[str, Dict]]
) -> bool:
    """
    Determine if a session needs to be recreated based on configuration changes.
    
    Args:
        session: The current session data, or None if no session exists
        llm_config_id: The requested LLM configuration ID
        tools_config: The requested tools configuration
        agent_mode: The requested agent mode
        agent_data_source: The requested agent data source
        
    Returns:
        True if the session needs to be recreated, False otherwise
    """
    if not session:
        # No existing session, so it needs to be created
        return True
    
    # Check if any of the key parameters have changed
    if (session.get("llm_config_id_used") != llm_config_id or
        session.get("agent_mode_used") != agent_mode):
        return True
    
    # Check for data source changes
    current_data_source = session.get("agent_data_source_used")
    if ((current_data_source is None and agent_data_source is not None) or
        (current_data_source is not None and agent_data_source is None) or
        (current_data_source != agent_data_source)):
        return True
    
    # Check for tools configuration changes
    current_tools_config = session.get("tools_config_used", {})
    
    # Compare enabled tools
    current_enabled = current_tools_config.get("enabled_tools", {})
    new_enabled = tools_config.get("enabled_tools", {})
    
    if current_enabled != new_enabled:
        return True
    
    # If we got here, the session can be reused
    return False

def create_new_session_dict(
    llm: Optional[BaseChatModel],
    llm_config_id: Optional[str],
    tools_config: Dict[str, Any],
    agent_mode: Optional[str],
    agent_data_source: Optional[Union[str, Dict]]
) -> Dict[str, Any]:
    """
    Create a new session dictionary with default values.
    
    Args:
        llm: The LLM instance to use, or None
        llm_config_id: The LLM configuration ID
        tools_config: The tools configuration
        agent_mode: The agent mode
        agent_data_source: The agent data source
        
    Returns:
        A new session dictionary
    """
    return {
        "llm": llm,
        "agent_executor": None,
        "raw_agent_executor": None,
        "mcp_client": None,
        "memory_saver": ChatMessageHistory(),
        "chat_messages_for_log": [],
        "llm_config_id_used": llm_config_id,
        "tools_config_used": tools_config,
        "agent_mode_used": agent_mode,
        "agent_data_source_used": agent_data_source
    }

class MemorySaver:
    """
    A simple memory saver for storing and retrieving conversation history.
    Used as a fallback when langgraph is not available.
    """
    
    def __init__(self):
        """Initialize the memory saver with an empty storage dictionary."""
        self.storage: Dict[str, List[BaseMessage]] = {}
        logger.debug("Initialized local MemorySaver.")

    async def aget(self, config: Dict[str, Any]) -> Optional[List[BaseMessage]]:
        """
        Asynchronously get the message history for a session.
        
        Args:
            config: Configuration containing the session ID
            
        Returns:
            List of messages, or None if not found
        """
        session_id = config.get("configurable", {}).get("session_id")
        if session_id:
            messages = self.storage.get(session_id)
            logger.debug(f"MemorySaver aget for session '{session_id}': "
                         f"Found {len(messages) if messages else 0} messages.")
            return messages
        logger.debug(f"MemorySaver aget: No session_id in config: {config}")
        return None

    async def aput(self, 
                  messages_map: Dict[str, List[BaseMessage]], 
                  config: Dict[str, Any]) -> None:
        """
        Asynchronously store message history for a session.
        
        Args:
            messages_map: Dictionary containing messages
            config: Configuration containing the session ID
        """
        session_id = config.get("configurable", {}).get("session_id")
        messages = messages_map.get("messages")  # messages_map is {"messages": [BaseMessage,...]}
        if session_id and messages is not None:
            self.storage[session_id] = messages
            logger.debug(f"MemorySaver aput for session '{session_id}': "
                        f"Stored {len(messages)} messages.")
        else:
            logger.warning(f"MemorySaver aput: Missing session_id or messages. "
                          f"Config: {config}, MsgMapKeys: {messages_map.keys()}")
    
    # Synchronous versions for legacy use
    def get(self, config: Dict[str, Any]) -> Optional[List[BaseMessage]]:
        """
        Synchronously get the message history for a session.
        
        Args:
            config: Configuration containing the session ID
            
        Returns:
            List of messages, or None if not found
        """
        session_id = config.get("configurable", {}).get("session_id")
        if session_id:
            messages = self.storage.get(session_id)
            logger.debug(f"MemorySaver get for session '{session_id}': "
                         f"Found {len(messages) if messages else 0} messages.")
            return messages
        logger.debug(f"MemorySaver get: No session_id in config: {config}")
        return None

    def put(self, 
           messages_map: Dict[str, List[BaseMessage]], 
           config: Dict[str, Any]) -> None:
        """
        Synchronously store message history for a session.
        
        Args:
            messages_map: Dictionary containing messages
            config: Configuration containing the session ID
        """
        session_id = config.get("configurable", {}).get("session_id")
        messages = messages_map.get("messages")
        if session_id and messages is not None:
            self.storage[session_id] = messages
            logger.debug(f"MemorySaver put for session '{session_id}': "
                        f"Stored {len(messages)} messages.")
        else:
            logger.warning(f"MemorySaver put: Missing session_id or messages. "
                          f"Config: {config}, MsgMapKeys: {messages_map.keys()}")

def generate_session_id() -> str:
    """
    Generate a new unique session ID.
    
    Returns:
        A new session ID
    """
    return str(uuid.uuid4()) 