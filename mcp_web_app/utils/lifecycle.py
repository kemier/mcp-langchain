import logging

logger = logging.getLogger(__name__)

async def shutdown_process_manager(process_manager):
    try:
        active_servers = []
        if hasattr(process_manager, "get_active_servers"):
            active_servers = process_manager.get_active_servers()
        elif hasattr(process_manager, "get_all_servers"):
            active_servers = process_manager.get_all_servers()
        elif hasattr(process_manager, "get_running_servers"):
            active_servers = process_manager.get_running_servers()
        else:
            logger.warning("ProcessManager does not provide a method to get active servers. Cannot shut them down.")
        for server_name in active_servers:
            try:
                process_manager.stop_server(server_name)
                logger.info(f"Stopped server {server_name} during shutdown")
            except Exception as e:
                logger.error(f"Error stopping server {server_name} during shutdown: {e}")
    except Exception as e:
        logger.error(f"Error during ProcessManager shutdown: {e}")

async def shutdown_agent_service(agent_service):
    try:
        logger.info("Stopping agent service dispatcher...")
        agent_service.shutdown() # This will call stop_dispatcher()
        logger.info("Agent service dispatcher stopped.")
        if hasattr(agent_service, "close_mcp_clients"):
            logger.info("Closing MCP clients from agent service...")
            await agent_service.close_mcp_clients()
            logger.info("MCP clients closed.")
        else:
            logger.warning("Agent service does not have close_mcp_clients method.")
    except Exception as e:
        logger.error(f"Error during agent service shutdown: {e}", exc_info=True) 