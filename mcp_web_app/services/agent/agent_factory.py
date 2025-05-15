#!/usr/bin/env python3
"""
Factory methods for creating agent executors for different types of agents.
"""
import logging
from typing import Dict, Any, List, Optional

from langchain import hub
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.runnables import RunnableWithMessageHistory
from langchain_community.tools import BaseTool
from langchain.agents import AgentExecutor, create_openai_tools_agent, create_react_agent
from langchain_community.agent_toolkits import JsonToolkit, create_json_agent
from langchain_community.tools.json.tool import JsonSpec

from ..agent.parser import CustomReActParser
from ...utils.io import load_json_or_yaml

# Initialize logger
logger = logging.getLogger(__name__)

def create_json_agent_executor(
    llm: BaseChatModel,
    json_data: Dict[str, Any],
    verbose: bool = True
) -> Optional[AgentExecutor]:
    """
    Create a JSON agent executor for working with JSON data.
    
    Args:
        llm: The language model to use
        json_data: The JSON data to use with the agent
        verbose: Whether to enable verbose output
        
    Returns:
        The agent executor, or None if creation fails
    """
    try:
        # Create JSON specification and toolkit
        json_spec = JsonSpec(dict_=json_data, max_value_length=4000)
        json_toolkit = JsonToolkit(spec=json_spec)
        
        # Create the JSON agent
        agent_executor = create_json_agent(
            llm=llm,
            toolkit=json_toolkit,
            verbose=verbose
        )
        
        return agent_executor
        
    except Exception as e:
        logger.error(f"Error creating JSON agent executor: {e}", exc_info=True)
        return None

def create_react_agent_executor(
    llm: BaseChatModel, 
    tools: List[BaseTool],
    verbose: bool = True
) -> Optional[AgentExecutor]:
    """
    Create a ReAct agent executor using OpenAI tools format.
    
    Args:
        llm: The language model to use
        tools: The tools to provide to the agent
        verbose: Whether to enable verbose output
        
    Returns:
        The agent executor, or None if creation fails
    """
    try:
        # Get the prompt from Langchain Hub
        prompt = hub.pull("hwchase17/openai-tools-agent")
        
        # Create the OpenAI tools agent
        agent = create_openai_tools_agent(llm, tools, prompt)

        # Create the agent executor
        agent_executor = AgentExecutor(
            agent=agent, 
            tools=tools, 
            verbose=verbose, 
            handle_parsing_errors=True
        )
        
        return agent_executor
        
    except Exception as e:
        logger.error(f"Error creating ReAct agent executor: {e}", exc_info=True)
        return None

def create_legacy_react_agent_executor(
    llm: BaseChatModel, 
    tools: List[BaseTool],
    verbose: bool = True
) -> Optional[AgentExecutor]:
    """
    Create a legacy ReAct agent executor with custom parsing.
    
    Args:
        llm: The language model to use
        tools: The tools to provide to the agent
        verbose: Whether to enable verbose output
        
    Returns:
        The agent executor, or None if creation fails
    """
    try:
        # Create system prompt
        system_prompt = """You are a helpful AI assistant with access to various tools.
        When asked a question, think through what tools might help you answer it.
        Use the tools available to you to provide the best possible response.
        """
        
        # Create prompt template
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("human", "{input}"),
        ])
        
        # Create custom output parser
        output_parser = CustomReActParser()
        
        # Create the ReAct agent
        agent = create_react_agent(llm, tools, prompt, output_parser=output_parser)

        # Create the agent executor
        agent_executor = AgentExecutor(
            agent=agent, 
            tools=tools, 
            verbose=verbose
        )
        
        return agent_executor
        
    except Exception as e:
        logger.error(f"Error creating legacy ReAct agent executor: {e}", exc_info=True)
        return None

def add_message_history(
    agent_executor: AgentExecutor,
    memory_getter: callable
) -> RunnableWithMessageHistory:
    """
    Wrap an agent executor with message history support.
    
    Args:
        agent_executor: The agent executor to wrap
        memory_getter: Function that returns a memory object for a session
        
    Returns:
        The wrapped agent executor
    """
    agent_with_history = RunnableWithMessageHistory(
        agent_executor,
        memory_getter,
        input_messages_key="input",
        history_messages_key="chat_history"
    )
    
    return agent_with_history

async def create_agent_for_mode(
    mode: str,
    llm: BaseChatModel,
    data_source: Optional[Dict[str, Any]] = None,
    tools: Optional[List[BaseTool]] = None,
    memory_getter: Optional[callable] = None,
    session_id: Optional[str] = None
) -> Optional[tuple[AgentExecutor, AgentExecutor]]:
    """
    Create an agent based on the specified mode.
    
    Args:
        mode: The agent mode (e.g., "json", "react")
        llm: The language model to use
        data_source: Data source for data-specific agents
        tools: Tools for tool-using agents
        memory_getter: Function that returns a memory object for a session
        session_id: The session ID
        
    Returns:
        Tuple of (agent_with_history, raw_agent) or None if creation fails
    """
    raw_agent_executor = None
    
    # Create the appropriate agent based on mode
    if mode == "json" and data_source:
        # Load JSON data if provided as a string
        json_data = None
        if isinstance(data_source, str):
            json_data = load_json_or_yaml(data_source)
        elif isinstance(data_source, dict):
            json_data = data_source
            
        if json_data:
            raw_agent_executor = create_json_agent_executor(llm, json_data)
            
    elif mode == "react" and tools:
        raw_agent_executor = create_react_agent_executor(llm, tools)
        
    # If no executor was created, return None
    if not raw_agent_executor:
        return None
        
    # Add message history if a memory getter was provided
    if memory_getter:
        agent_with_history = add_message_history(
            raw_agent_executor,
            lambda sid: memory_getter(sid or session_id)
        )
        return agent_with_history, raw_agent_executor
    
    # Otherwise, return the raw agent as both values
    return raw_agent_executor, raw_agent_executor 