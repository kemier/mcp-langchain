from fastapi import HTTPException
from pydantic import ValidationError
import logging

logger = logging.getLogger(__name__)

def add_llm_config_helper(config_manager, llm_config_payload):
    if not llm_config_payload.config_id:
        raise HTTPException(status_code=400, detail="config_id is required")
    try:
        created_config = config_manager.add_llm_config(llm_config_payload)
        return created_config
    except ValueError as e:
        logger.error(f"Error adding LLM config '{llm_config_payload.config_id}': {e}", exc_info=True)
        raise HTTPException(status_code=400, detail=str(e))
    except ValidationError as e:
        logger.error(f"Validation error for LLM config '{llm_config_payload.config_id}': {e}", exc_info=True)
        raise HTTPException(status_code=422, detail=e.errors())
    except Exception as e:
        logger.error(f"Unexpected error adding LLM config '{llm_config_payload.config_id}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {str(e)}")

def update_llm_config_helper(config_manager, config_id, llm_config_update_payload):
    try:
        updated_config = config_manager.update_llm_config(config_id, llm_config_update_payload.model_dump(exclude_none=True))
        if not updated_config:
            logger.warning(f"LLM config '{config_id}' not found for update.")
            raise HTTPException(status_code=404, detail=f"LLM configuration with ID '{config_id}' not found.")
        return updated_config
    except ValueError as e:
        logger.error(f"Error updating LLM config '{config_id}': {e}", exc_info=True)
        raise HTTPException(status_code=400, detail=str(e))
    except ValidationError as e:
        logger.error(f"Validation error updating LLM config '{config_id}': {e}", exc_info=True)
        raise HTTPException(status_code=422, detail=e.errors())
    except Exception as e:
        logger.error(f"Unexpected error updating LLM config '{config_id}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {str(e)}")

def delete_llm_config_helper(config_manager, config_id):
    try:
        config_manager.delete_llm_config(config_id)
        return {"status": "success", "message": f"LLM configuration '{config_id}' deleted successfully."}
    except ValueError as e:
        logger.warning(f"LLM configuration '{config_id}' not found for deletion: {e}")
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error deleting LLM configuration '{config_id}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred while deleting the configuration: {str(e)}") 