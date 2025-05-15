#!/usr/bin/env python3
"""
Agent utilities for MCP adapters.
Contains helper functions for agent creation and management.
"""
import logging
from typing import Dict, Any, List, AsyncGenerator

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.language_models.chat_models import BaseChatModel
from langchain.agents import AgentExecutor, create_react_agent
from langchain_community.chat_models import ChatOllama
from langchain_community.tools import BaseTool

# Setup logging
logger = logging.getLogger(__name__)

def create_agent_executor(
    llm: BaseChatModel, 
    tools: List[BaseTool], 
    verbose: bool = True
) -> AgentExecutor:
    """
    Create an AgentExecutor with the given LLM and tools.
    
    Args:
        llm: The language model to use
        tools: List of tools to provide to the agent
        verbose: Whether to enable verbose output
        
    Returns:
        An initialized AgentExecutor
    """
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
    
    try:
        # For Ollama models, we need to bind the tools to the LLM
        if isinstance(llm, ChatOllama):
            logger.info("Using Ollama-specific approach to bind tools")
            llm_with_tools = llm.bind_tools(tools=tools)
            agent = create_react_agent(llm_with_tools, tools, prompt)
        else:
            # For other LLMs, use the regular approach
            agent = create_react_agent(llm, tools, prompt)
            
        # Create agent executor
        agent_executor = AgentExecutor(
            agent=agent,
            tools=tools,
            verbose=verbose
        )
        
        return agent_executor
        
    except Exception as e:
        logger.error(f"Error creating agent: {str(e)}", exc_info=True)
        raise

def initialize_llm(
    model_name: str,
    temperature: float,
    top_p: float,
    **kwargs
) -> BaseChatModel:
    """
    Initialize a language model with the given parameters.
    
    Args:
        model_name: The name of the model to use
        temperature: Temperature setting for the model
        top_p: Top-p setting for the model
        **kwargs: Additional model parameters
        
    Returns:
        An initialized language model
    """
    # Only include supported parameters
    model_kwargs = {
        "temperature": temperature,
        "top_p": top_p,
        **kwargs
    }
    
    # Create the LLM instance
    llm = ChatOllama(
        model=model_name,
        format="json",  # Ensure proper JSON format for tool calling
        **model_kwargs
    )
    
    return llm

async def stream_agent_events(
    agent_executor: AgentExecutor,
    query: str
) -> AsyncGenerator[Dict[str, Any], None]:
    """
    Stream events from the agent's execution process.
    
    Args:
        agent_executor: The agent executor to use
        query: The user query
        
    Yields:
        Events from the agent execution
    """
    if not agent_executor:
        raise ValueError("Agent executor not initialized")
    
    async for event in agent_executor.astream_events(
        {"input": query},
        version="v1"
    ):
        yield event 