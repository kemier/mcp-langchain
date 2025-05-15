#!/usr/bin/env python3
"""
MCP Adapter for integrating Model Context Protocol with LangChain and Ollama.
This module provides the necessary functionality to connect to MCP servers,
load tools, and create agents that can use these tools via LangChain.
"""
import os
import asyncio
import logging
from typing import List, Dict, Any, Optional, AsyncGenerator, Tuple

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.language_models.chat_models import BaseChatModel

from langchain_community.chat_models import ChatOllama
from langchain.agents import AgentExecutor, create_react_agent
from langchain_community.tools import BaseTool

from mcp import ClientSession
from langchain_mcp_adapters.client import sse_client
from langchain_mcp_adapters.tools import convert_mcp_tool_to_langchain_tool

# Setup logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

class MCPOllamaAdapter:
    """
    Adapter for connecting Ollama with MCP for tool use capabilities.
    This adapter handles:
    1. Connecting to MCP servers to load tools
    2. Converting MCP tools to LangChain tools
    3. Creating a LangChain agent with Ollama that can use these tools
    """
    
    def __init__(
        self,
        model_name: str = "llama3",
        mcp_urls: List[str] = None,
        temperature: float = 0.7,
        top_p: float = 0.9,
    ):
        """
        Initialize the MCP Ollama Adapter
        
        Args:
            model_name: The Ollama model to use (e.g., "llama3")
            mcp_urls: List of MCP server URLs to connect to
            temperature: Temperature setting for the model
            top_p: Top-p setting for the model
        """
        self.model_name = model_name
        self.mcp_urls = mcp_urls or ["http://localhost:8000/sse"]
        self.temperature = temperature
        self.top_p = top_p
        
        # Will be populated during initialization
        self.tools = []
        self.llm = None
        self.agent_executor = None
        
        # Streams for MCP
        self.read_stream = None
        self.write_stream = None
        self.session = None
        
        # Track the context manager for connection
        self._cm = None
        
        logger.info(f"MCPOllamaAdapter created with URLs: {self.mcp_urls}")

    @classmethod
    def from_config(cls, config: Dict[str, Any]):
        """Create an adapter from a configuration dictionary"""
        # Extract Ollama-specific settings from config
        ollama_config = config.get("ollama_config", {})
        model_name = ollama_config.get("model", "llama3")
        temperature = ollama_config.get("temperature", 0.7)
        top_p = ollama_config.get("top_p", 0.9)
        
        # Get MCP URLs from config
        mcp_urls = config.get("mcp_urls", ["http://localhost:8000/sse"])
        
        return cls(
            model_name=model_name,
            mcp_urls=mcp_urls,
            temperature=temperature,
            top_p=top_p
        )
        
    async def initialize(self) -> None:
        """
        Initialize MCP client, tools, LLM, and agent
        """
        # Since we need to maintain the connection, we'll get a context manager
        # but won't exit it until close() is called
        if not self.mcp_urls:
            raise ValueError("No MCP URLs provided")
        
        # For simplicity, we'll use the first URL
        url = self.mcp_urls[0]
        logger.info(f"Connecting to MCP server at {url}")
        
        try:
            # Create and enter the context manager
            self._cm = sse_client(url=url)
            self.read_stream, self.write_stream = await self._cm.__aenter__()
            logger.debug(f"Got read_stream: {self.read_stream} and write_stream: {self.write_stream}")
            
            # Create a ClientSession for the MCP server
            self.session = ClientSession(self.read_stream, self.write_stream)
            await self.session.__aenter__()
            logger.debug(f"Client session created and entered: {self.session}")
            
            # Initialize the MCP session
            await self.session.initialize()
            logger.debug(f"MCP session initialized")
            
            # Get tools from the MCP server using the client session
            mcp_tools = await self.session.list_tools()
            logger.debug(f"Retrieved {len(mcp_tools)} tools from MCP server: {[t.name for t in mcp_tools]}")
            
            # Convert to LangChain tools
            self.tools = []
            for tool in mcp_tools:
                lc_tool = convert_mcp_tool_to_langchain_tool(tool, self.session)
                self.tools.append(lc_tool)
                logger.debug(f"Converted MCP tool '{tool.name}' to LangChain tool")
            
            if not self.tools:
                logger.warning("No tools were retrieved from MCP servers")
            else:
                logger.info(f"Loaded {len(self.tools)} tools from MCP servers")
                
            # Initialize the LLM
            self._initialize_llm()
            logger.debug(f"LLM initialized: {self.llm}")
            
            # Create the agent
            self._create_agent()
            logger.debug(f"Agent created: {self.agent_executor}")
            
            logger.info("MCPOllamaAdapter initialization completed successfully")
            
        except Exception as e:
            # Clean up if initialization fails
            logger.error(f"Error during initialization: {str(e)}", exc_info=True)
            await self.close()
            raise e
            
    def _initialize_llm(self) -> None:
        """Initialize the Ollama LLM with the proper configuration"""
        # Only include supported parameters
        model_kwargs = {
            "temperature": self.temperature,
            "top_p": self.top_p,
        }
        
        # Create the LLM instance
        self.llm = ChatOllama(
            model=self.model_name,
            format="json",  # Ensure proper JSON format for tool calling
            **model_kwargs
        )
        
    def _create_agent(self) -> None:
        """Create a ReAct agent with the tools and LLM"""
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
            if isinstance(self.llm, ChatOllama):
                logger.info("Using Ollama-specific approach to bind tools")
                ollama_with_tools = self.llm.bind_tools(tools=self.tools)
                agent = create_react_agent(ollama_with_tools, self.tools, prompt)
            else:
                # For other LLMs, use the regular approach
                agent = create_react_agent(self.llm, self.tools, prompt)
                
            # Create agent executor
            self.agent_executor = AgentExecutor(
                agent=agent,
                tools=self.tools,
                verbose=True
            )
        except Exception as e:
            logger.error(f"Error creating agent: {str(e)}", exc_info=True)
            raise
    
    async def aask_agent(self, query: str) -> str:
        """
        Ask the agent a question and get the response
        
        Args:
            query: The user query
            
        Returns:
            The agent's response as a string
        """
        if not self.agent_executor:
            raise ValueError("Agent not initialized. Call initialize() first.")
        
        result = await self.agent_executor.ainvoke({"input": query})
        return result["output"]
    
    async def astream_ask_agent_events(
        self, query: str
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Stream the agent's response as events
        
        Args:
            query: The user query
            
        Yields:
            Events from the agent execution
        """
        if not self.agent_executor:
            raise ValueError("Agent not initialized. Call initialize() first.")
        
        async for event in self.agent_executor.astream_events(
            {"input": query},
            version="v1"
        ):
            yield event
            
    async def close(self) -> None:
        """Close the MCP client connection"""
        if self._cm is not None:
            try:
                if self.session is not None:
                    await self.session.__aexit__(None, None, None)
                    self.session = None
                await self._cm.__aexit__(None, None, None)
                self._cm = None
                self.read_stream = None
                self.write_stream = None
            except Exception as e:
                logger.error(f"Error closing MCP connection: {e}")

# Example usage
async def test_mcp_adapter():
    # Create the adapter
    adapter = MCPOllamaAdapter(model_name="llama3")
    
    try:
        # Initialize
        await adapter.initialize()
        
        # Ask a question
        response = await adapter.aask_agent("What's the weather in New York?")
        print(response)
        
    finally:
        # Clean up
        await adapter.close()

if __name__ == "__main__":
    # Run the test
    asyncio.run(test_mcp_adapter()) 