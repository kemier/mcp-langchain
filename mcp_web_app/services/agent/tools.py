#!/usr/bin/env python3
"""
Utilities for MCP tool management and connection.
"""
import logging
from typing import Dict, Any, List, Optional, Tuple

from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_community.tools import BaseTool

# Initialize logger
logger = logging.getLogger(__name__)

async def create_mcp_client(server_configs: Dict[str, Any]) -> Optional[MultiServerMCPClient]:
    """
    Create an MCP client for connecting to tool servers.
    
    Args:
        server_configs: Dictionary of server configurations
        
    Returns:
        An initialized MCP client, or None if creation fails
    """
    try:
        # Create the MCP client
        mcp_client = MultiServerMCPClient(connections=server_configs)
        
        # Activate the client
        await mcp_client.__aenter__()
        
        logger.info(f"Successfully created and activated MCP client for {len(server_configs)} servers")
        return mcp_client
        
    except Exception as e:
        logger.error(f"Failed to create or activate MCP client: {str(e)}", exc_info=True)
        return None

async def load_tools_from_client(
    mcp_client: MultiServerMCPClient,
    enabled_tool_filters: Dict[str, List[Dict[str, str]]]
) -> List[BaseTool]:
    """
    Load tools from an MCP client with filters.
    
    Args:
        mcp_client: The MCP client to load tools from
        enabled_tool_filters: Dictionary of server names to list of allowed tool capability dictionaries (e.g., [{'name': 'tool_name', 'description': '...'}]).
        
    Returns:
        List of LangChain tools
    """
    try:
        # Get all tools from the client
        all_tools = await mcp_client.get_all_tools_from_all_servers()
        
        if not all_tools:
            logger.warning("No tools retrieved from MCP servers")
            return []
        
        # If no filters provided (e.g. empty dict), it implies no servers are specified for tool loading.
        # Or, if a server is listed in filters but its tool list is empty, it means no tools for that server.
        if not enabled_tool_filters:
            logger.info("No tool filters provided (empty dict), so no tools will be loaded.")
            return []
        
        # Filter tools based on the enabled tool filters
        filtered_tools = []
        for tool in all_tools:
            server_name = None
            if hasattr(tool, "meta") and isinstance(tool.meta, dict):
                server_name = tool.meta.get("server_name")
            
            # If the tool has no server name, it cannot be filtered by server, so skip it unless filters are truly empty (covered above).
            if not server_name:
                logger.debug(f"Tool '{tool.name}' has no server_name in meta, skipping.")
                continue
            
            # Check if this server is even mentioned in the filters.
            # If a server is not in enabled_tool_filters, no tools from it should be loaded.
            if server_name not in enabled_tool_filters:
                logger.debug(f"Server '{server_name}' for tool '{tool.name}' not in enabled_tool_filters, skipping tool.")
                continue
            
            server_allowed_capabilities = enabled_tool_filters.get(server_name)
            # If the list of capabilities for this server is empty, it means no tools from this server are allowed.
            if not server_allowed_capabilities:
                logger.debug(f"Server '{server_name}' has an empty list of allowed capabilities in filters, skipping tool '{tool.name}'.")
                continue

            # Check if this specific tool.name is among the 'name' fields of the allowed capabilities for this server,
            # or if '*' is specified as a capability name for this server.
            is_tool_allowed = False
            for cap_dict in server_allowed_capabilities:
                if not isinstance(cap_dict, dict) or 'name' not in cap_dict:
                    logger.warning(f"Malformed capability entry for server '{server_name}': {cap_dict}. Skipping this capability entry.")
                    continue
                if cap_dict['name'] == tool.name or cap_dict['name'] == "*":
                    is_tool_allowed = True
                    break
            
            if is_tool_allowed:
                logger.debug(f"Tool '{tool.name}' from server '{server_name}' is allowed by filters.")
                filtered_tools.append(tool)
            else:
                logger.debug(f"Tool '{tool.name}' from server '{server_name}' is NOT allowed by filters. Allowed: {server_allowed_capabilities}")
        
        logger.info(f"Filtered {len(all_tools)} tools to {len(filtered_tools)} based on filters: {enabled_tool_filters}")
        return filtered_tools
        
    except Exception as e:
        logger.error(f"Error loading tools from MCP client: {str(e)}", exc_info=True)
        return []

async def close_mcp_client(mcp_client: MultiServerMCPClient) -> bool:
    """
    Safely close an MCP client.
    
    Args:
        mcp_client: The MCP client to close
        
    Returns:
        True if closed successfully, False otherwise
    """
    if not mcp_client:
        return True
    
    try:
        await mcp_client.__aexit__(None, None, None)
        logger.info("MCP client closed successfully")
        return True
        
    except Exception as e:
        logger.error(f"Error closing MCP client: {str(e)}", exc_info=True)
        return False

async def get_tools_for_config(
    server_configs: Dict[str, Any],
    enabled_tool_filters: Dict[str, List[Dict[str, str]]]
) -> Tuple[List[BaseTool], Optional[MultiServerMCPClient]]:
    """
    Get tools based on server configs and filters.
    
    Args:
        server_configs: Dictionary of server configurations (client's tools_config, e.g. {'server1': [{'name':'tool_a', ...}]})
        enabled_tool_filters: Dictionary of server names to list of allowed tool capability dicts (effectively same as server_configs here).
        
    Returns:
        Tuple of (list of tools, MCP client)
    """
    # The server_configs for MultiServerMCPClient should be the capability descriptions for each server.
    # The enabled_tool_filters is used to select which of the discovered tools are actually loaded.
    # In the current LangchainAgentService call, both are derived from the same client_tools_config.

    # Create the MCP client using the server_configs (which details what servers/capabilities to connect to)
    mcp_client = await create_mcp_client(server_configs)
    if not mcp_client:
        return [], None
    
    # Load tools from the client, using enabled_tool_filters to select among discovered tools.
    tools = await load_tools_from_client(mcp_client, enabled_tool_filters)
    
    return tools, mcp_client 