#!/usr/bin/env python3
"""
MCP client utilities for handling connections and tools.
"""
import logging
from typing import List, Dict, Any, Tuple, Optional, AsyncGenerator

from mcp import ClientSession
from langchain_mcp_adapters.client import sse_client
from langchain_mcp_adapters.tools import convert_mcp_tool_to_langchain_tool
from langchain_community.tools import BaseTool

# Setup logging
logger = logging.getLogger(__name__)

class MCPClientManager:
    """Manager for MCP client connections and tools"""
    
    def __init__(self, mcp_urls: List[str] = None):
        """
        Initialize the MCP client manager
        
        Args:
            mcp_urls: List of MCP server URLs to connect to
        """
        self.mcp_urls = mcp_urls or ["http://localhost:8000/sse"]
        self.read_stream = None
        self.write_stream = None
        self.session = None
        self._cm = None
        
    async def connect(self) -> None:
        """
        Connect to the MCP server
        
        Raises:
            ValueError: If no MCP URLs are provided
            Exception: If connection fails
        """
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
            
        except Exception as e:
            logger.error(f"Error connecting to MCP server: {str(e)}", exc_info=True)
            await self.close()
            raise e
            
    async def load_tools(self) -> List[BaseTool]:
        """
        Load tools from the MCP server
        
        Returns:
            List of LangChain tools
            
        Raises:
            ValueError: If not connected to an MCP server
        """
        if not self.session:
            raise ValueError("Not connected to an MCP server. Call connect() first.")
        
        try:
            # Get tools from the MCP server using the client session
            mcp_tools = await self.session.list_tools()
            logger.debug(f"Retrieved {len(mcp_tools)} tools from MCP server: {[t.name for t in mcp_tools]}")
            
            # Convert to LangChain tools
            langchain_tools = []
            for tool in mcp_tools:
                lc_tool = convert_mcp_tool_to_langchain_tool(tool, self.session)
                langchain_tools.append(lc_tool)
                logger.debug(f"Converted MCP tool '{tool.name}' to LangChain tool")
            
            if not langchain_tools:
                logger.warning("No tools were retrieved from MCP servers")
            else:
                logger.info(f"Loaded {len(langchain_tools)} tools from MCP servers")
                
            return langchain_tools
            
        except Exception as e:
            logger.error(f"Error loading tools: {str(e)}", exc_info=True)
            raise e
            
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
                logger.info("MCP client connection closed")
            except Exception as e:
                logger.error(f"Error closing MCP connection: {e}")

async def create_mcp_client(mcp_url: str) -> Tuple[MCPClientManager, List[BaseTool]]:
    """
    Create and initialize an MCP client, returning the manager and tools
    
    Args:
        mcp_url: URL of the MCP server
        
    Returns:
        Tuple of (client manager, tools)
    """
    client_manager = MCPClientManager([mcp_url])
    await client_manager.connect()
    tools = await client_manager.load_tools()
    
    return client_manager, tools 