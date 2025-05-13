# Placeholder for MCP Tool Scripthost - Now being implemented

from langchain_core.tools import BaseTool
from typing import List, Optional, Any
import logging
import asyncio # Added for the example, though not used in main factory logic
from collections.abc import Callable # Added for the example

logger = logging.getLogger(__name__)

class MCPServerToolFactory:
    def __init__(self, client: Any, enabled_tools_list: Optional[List[str]] = None):
        """
        Initializes the factory with an MCP client and an optional list of enabled tool names.

        Args:
            client: An instance of MultiServerMCPClient (or a compatible client).
            enabled_tools_list: An optional list of tool names to filter for. 
                                If None or empty, all tools from the client may be used.
        """
        if client is None:
            raise ValueError("MCP client cannot be None for MCPServerToolFactory")
        self.client = client
        self.enabled_tools_list = enabled_tools_list if enabled_tools_list else [] # Ensure it's a list
        logger.info(f"MCPServerToolFactory initialized. Client: {type(client).__name__}, Enabled tools: {self.enabled_tools_list}")

    def create_tools(self) -> List[BaseTool]:
        """
        Creates and returns a list of BaseTool instances.

        It retrieves all tools from the configured MCP client and then filters them
        based on the enabled_tools_list provided during initialization.
        """
        all_client_tools: List[BaseTool] = []
        try:
            all_client_tools = self.client.get_tools()
            if not isinstance(all_client_tools, list):
                logger.warning(f"client.get_tools() did not return a list, got {type(all_client_tools)}. Attempting to convert.")
                try:
                    all_client_tools = list(all_client_tools)
                except TypeError:
                    logger.error("Failed to convert tools from client to a list. Returning empty tool list.")
                    return []
            logger.info(f"Retrieved {len(all_client_tools)} tools from MCP client: {[tool.name for tool in all_client_tools if hasattr(tool, 'name')]}")
        except AttributeError:
            logger.error("MCP client is missing the 'get_tools' method. Cannot create tools.", exc_info=True)
            return []
        except Exception as e:
            logger.error(f"Error retrieving tools from MCP client: {e}", exc_info=True)
            return []

        if not self.enabled_tools_list:
            logger.info("No specific tools enabled in factory, returning all tools from client.")
            return all_client_tools

        created_tools: List[BaseTool] = []
        client_tool_names = {tool.name for tool in all_client_tools if hasattr(tool, 'name')}

        for tool_name_to_enable in self.enabled_tools_list:
            if tool_name_to_enable in client_tool_names:
                # Find the tool object from all_client_tools
                tool_to_add = next((tool for tool in all_client_tools if hasattr(tool, 'name') and tool.name == tool_name_to_enable), None)
                if tool_to_add:
                    created_tools.append(tool_to_add)
            else:
                logger.warning(f"Tool '{tool_name_to_enable}' from enabled_tools_list was not found in client's offerings: {list(client_tool_names)}")
        
        logger.info(f"MCPServerToolFactory created {len(created_tools)} tools based on enabled list: {[tool.name for tool in created_tools if hasattr(tool, 'name')]}")
        if not created_tools and self.enabled_tools_list:
             logger.warning(f"Enabled tools list was specified as {self.enabled_tools_list}, but no matching tools were found or created.")
        return created_tools

# Example of how a BaseTool might be structured if coming from the client
# This is just for illustration if we needed to manually create them,
# but client.get_tools() should ideally return fully formed BaseTool instances.
#
# from langchain_core.tools import tool as tool_decorator
#
# class ExampleClientTool(BaseTool):
#     name: str
#     description: str
#     client_method: Callable
#
#     def _run(self, *args: Any, **kwargs: Any) -> Any:
#         return self.client_method(*args, **kwargs)
#
#     async def _arun(self, *args: Any, **kwargs: Any) -> Any:
#         # If the client_method is async
#         # return await self.client_method(*args, **kwargs)
#         # If it's sync, wrap it
#         loop = asyncio.get_event_loop()
#         return await loop.run_in_executor(None, self.client_method, *args, **kwargs)
# Ensure the file ends with a newline for linters 