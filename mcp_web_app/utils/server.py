from fastapi import HTTPException
import logging

logger = logging.getLogger(__name__)

def create_server_config_helper(config_manager, request):
    try:
        config_manager._tool_server_configs[request.config_key] = request.config
        logger.info(f"Tool server config '{request.config_key}' added to in-memory store.")
        return {"success": True, "message": f"Server configuration for '{request.config_key}' created/updated in memory."}
    except Exception as e:
        logger.error(f"Error creating server configuration for '{request.config_key}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

def update_server_config_helper(config_manager, server_name, request):
    try:
        if server_name not in config_manager.get_all_tool_server_configs():
            raise HTTPException(status_code=404, detail=f"Server configuration '{server_name}' not found.")
        config_manager._tool_server_configs[server_name] = request.config
        logger.info(f"Tool server config '{server_name}' updated in in-memory store.")
        return {"success": True, "message": f"Server configuration for '{server_name}' updated in memory."}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating server configuration for '{server_name}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

def remove_server_config_helper(config_manager, server_name):
    try:
        if server_name in config_manager._tool_server_configs:
            del config_manager._tool_server_configs[server_name]
            logger.info(f"Tool server config '{server_name}' removed from in-memory store.")
            return {"success": True, "message": f"Server configuration for '{server_name}' removed from memory."}
        else:
            logger.warning(f"Attempted to delete non-existent server config '{server_name}'.")
            raise HTTPException(status_code=404, detail=f"Server configuration '{server_name}' not found.")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting server configuration '{server_name}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) 