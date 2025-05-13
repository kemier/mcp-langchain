import json
import os
import asyncio # For file lock in LLMConfigManager
from typing import Dict, List, Optional, Any # Added List, Any
from .models.models import ServerConfig
import logging
from fastapi import APIRouter, HTTPException, Body, status # For LLMConfig router
from pydantic import BaseModel, Field # For LLMConfig model

logger = logging.getLogger(__name__)

class ConfigManager:
    def __init__(self, config_file_path: str):
        self.config_file_path = config_file_path
        if not os.path.exists(self.config_file_path):
            # Create a default empty config if it doesn't exist to prevent load errors on first run
            self._save_configs_to_file({})

    def _load_configs_from_file(self) -> Dict[str, Dict]:
        """Helper to load raw data from JSON file."""
        try:
            with open(self.config_file_path, 'r') as f:
                data = json.load(f)
            return data
        except (json.JSONDecodeError, FileNotFoundError) as e:
            logger.error(f"Error loading or parsing {self.config_file_path}: {e}", exc_info=True)
            # Fallback to empty config if file is corrupted or truly missing after init check
            return {}

    def _save_configs_to_file(self, raw_data: Dict[str, Dict]):
        """Helper to save raw data to JSON file."""
        try:
            with open(self.config_file_path, 'w') as f:
                json.dump(raw_data, f, indent=2)
        except TypeError as e:
            logger.error(f"Error saving server configs to {self.config_file_path}: {e}", exc_info=True)

    def get_all_server_configs(self) -> Dict[str, ServerConfig]:
        raw_configs = self._load_configs_from_file()
        # Validate with Pydantic models
        validated_configs: Dict[str, ServerConfig] = {}
        for name, config_data in raw_configs.items():
            try:
                validated_configs[name] = ServerConfig(**config_data)
            except Exception as e: # PydanticValidationError or others
                logger.error(f"Validation error for server '{name}' in {self.config_file_path}: {e}", exc_info=True)
                # Optionally, skip this server or raise a more specific error
        return validated_configs

    def get_server_config(self, server_name: str) -> Optional[ServerConfig]:
        configs = self.get_all_server_configs()
        return configs.get(server_name)

    def save_all_server_configs(self, server_configs_map: Dict[str, ServerConfig]):
        # Convert Pydantic models to dicts for JSON serialization
        data_to_save = {name: config.model_dump() for name, config in server_configs_map.items()}
        self._save_configs_to_file(data_to_save)

    def add_server_config(self, config_key: str, config: ServerConfig):
        """Add a new server config and save to file."""
        configs = self.get_all_server_configs()
        if config_key in configs:
            raise ValueError(f"Server config with key '{config_key}' already exists.")
        configs[config_key] = config
        self.save_all_server_configs(configs)
        
    def update_server_config(self, config_key: str, config: ServerConfig):
        """Update an existing server config and save to file."""
        configs = self.get_all_server_configs()
        if config_key not in configs:
            raise ValueError(f"Server config with key '{config_key}' does not exist.")
        configs[config_key] = config
        self.save_all_server_configs(configs)
        return True
        
    def remove_server_config(self, config_key: str):
        """Remove a server config and save to file."""
        configs = self.get_all_server_configs()
        if config_key not in configs:
            raise ValueError(f"Server config with key '{config_key}' does not exist.")
        del configs[config_key]
        self.save_all_server_configs(configs)
        return True

# --- LLM Configuration Management ---

LLM_CONFIGS_FILENAME = "llm_configs.json" # Name of the file for LLM configs
LLM_CONFIG_LOCK = asyncio.Lock() # Separate lock for LLM configs

DEFAULT_ERICAI_BASE_URL_ENV = os.getenv(
    "DEFAULT_ERICAI_BASE_URL", 
    "YOUR_DEFAULT_ERICAI_BASE_URL_NEEDS_SETTING" 
)
if DEFAULT_ERICAI_BASE_URL_ENV == "YOUR_DEFAULT_ERICAI_BASE_URL_NEEDS_SETTING":
    logger.warning("DEFAULT_ERICAI_BASE_URL environment variable is not set. "
                   "Default EricAI configs will require manual Base URL entry if not overridden.")

# This list contains the "built-in" EricAI model identifiers.
# Your frontend will fetch these for the dropdown in the config form.
PREDEFINED_ERICAI_MODEL_IDENTIFIERS: List[str] = [
    "mistralai/Mistral-8x7B-Instruct-v0.1",
    "mistralai/mistral-7b-instruct-v0.2",
    "mistral-community/Mixtral-8x22B-v0.1",
    "mistralai/Mixtral-8x22B-Instruct-v0.1",
    "mistralai/Codestral-22B-v0.1",
    "HuggingFaceH4/zephyr-orpo-141b-A35b-v0.1",
    "amazon/LightGPT",
    "yunconglong/Truthful_DPO_TomGrc_FusionNet_7Bx2_MoE_13B"
]

# **MODIFIED** Default EricAI configuration templates
DEFAULT_ERICAI_CONFIG_TEMPLATES: List[Dict[str, Any]] = [
    {
        "config_id": "ericai_default_slot1",
        "display_name": "EricAI (Primary - Needs Setup)", # Indicate setup needed
        "provider": "ericai",
        "model_name_or_path": None, # <<<< MODIFIED: Initially None
        "base_url": DEFAULT_ERICAI_BASE_URL_ENV,
        "api_key": None, # User must configure this
        "temperature": 0.7,
        "max_tokens": 2048,
        "is_default": True
    },
    {
        "config_id": "ericai_creative_config",
        "display_name": "EricAI (Creative - Needs Setup)", # Indicate setup needed
        "provider": "ericai",
        "model_name_or_path": None, # <<<< MODIFIED: Initially None
        "base_url": DEFAULT_ERICAI_BASE_URL_ENV,
        "api_key": None, # User must configure this
        "temperature": 0.9,
        "max_tokens": 3000,
        "is_default": False
    }
]

# Pydantic model for an LLM configuration (move from main.py or define here)
class LLMConfig(BaseModel):
    config_id: str = Field(..., description="Unique identifier for the configuration")
    display_name: str = Field(..., description="User-friendly name")
    provider: str = Field(..., description="LLM provider, e.g., 'ericai', 'ollama'")
    model_name_or_path: Optional[str] = Field(None, description="Model identifier for the provider. For EricAI, choose from predefined list.")
    base_url: Optional[str] = Field(None, description="API base URL")
    api_key: Optional[str] = Field(None, description="API key (will be prompted if None)")
    temperature: Optional[float] = Field(None, description="Default temperature")
    max_tokens: Optional[int] = Field(None, description="Default max tokens")
    is_default: Optional[bool] = Field(False, description="Is this the default for the provider?")


class LLMConfigManager:
    def __init__(self, config_file_path: str = LLM_CONFIGS_FILENAME):
        self.config_file_path = config_file_path
        # Ensure default path is relative to this file if needed, or expect absolute path
        if not os.path.isabs(self.config_file_path):
             self.config_file_path = os.path.join(os.path.dirname(__file__), self.config_file_path)
        logger.info(f"LLMConfigManager initialized with config file: {self.config_file_path}")


    async def _load_llm_configs_from_file(self) -> List[Dict[str, Any]]:
        async with LLM_CONFIG_LOCK:
            if not os.path.exists(self.config_file_path):
                logger.info(f"{self.config_file_path} not found. Will be created with defaults by ensure_default_ericai_configs.")
                return [] # Return empty if file doesn't exist, ensure_default_ericai_configs will handle creation
            try:
                with open(self.config_file_path, 'r') as f:
                    data = json.load(f)
                return data if isinstance(data, list) else []
            except json.JSONDecodeError:
                logger.error(f"Error decoding LLM configs from {self.config_file_path}. Returning empty list.")
                return []
            except Exception as e:
                logger.error(f"Unexpected error loading LLM configs from {self.config_file_path}: {e}", exc_info=True)
                return []

    async def _save_llm_configs_to_file(self, configs_data: List[Dict[str, Any]]):
        async with LLM_CONFIG_LOCK:
            try:
                with open(self.config_file_path, 'w') as f:
                    json.dump(configs_data, f, indent=2)
                logger.info(f"LLM configurations saved to {self.config_file_path}")
            except Exception as e:
                logger.error(f"Error saving LLM configurations to {self.config_file_path}: {e}", exc_info=True)
                # In a real app, you might want to raise an exception here to signal failure
                raise HTTPException(status_code=500, detail="Failed to save LLM configurations.")


    async def ensure_default_ericai_configs(self):
        """Ensures default EricAI stubs are present if no 'ericai' providers exist or file is empty."""
        current_configs = await self._load_llm_configs_from_file()
        # Check if file was initially empty, meaning _load_llm_configs_from_file returned []
        # or if no EricAI providers are present in a non-empty file.
        ericai_providers_exist = any(cfg.get("provider") == "ericai" for cfg in current_configs)

        if not current_configs or not ericai_providers_exist: # If file was empty or no EricAI providers
            logger.info("No existing LLM configs or no 'ericai' provider configurations found. Adding default EricAI templates.")
            
            defaults_to_add = []
            for template in DEFAULT_ERICAI_CONFIG_TEMPLATES:
                # Ensure this template isn't already effectively present (by config_id)
                if not any(cfg.get("config_id") == template["config_id"] for cfg in current_configs):
                    cfg_copy = template.copy()
                    # Check placeholder for base_url
                    if cfg_copy["base_url"] == "YOUR_DEFAULT_ERICAI_BASE_URL_NEEDS_SETTING" and \
                       DEFAULT_ERICAI_BASE_URL_ENV == "YOUR_DEFAULT_ERICAI_BASE_URL_NEEDS_SETTING":
                        logger.warning(f"Default EricAI Base URL for {cfg_copy['config_id']} not set. User must configure it.")
                    defaults_to_add.append(cfg_copy)
            
            if defaults_to_add:
                current_configs.extend(defaults_to_add)
                await self._save_llm_configs_to_file(current_configs)
                logger.info(f"Added {len(defaults_to_add)} default EricAI config templates to {self.config_file_path}.")
            elif ericai_providers_exist:
                 logger.info("All default EricAI templates already exist or other EricAI configs present. No new templates added.")
        else:
            logger.info("Existing 'ericai' provider configurations found. Default templates not added.")

    async def get_all_llm_configs(self) -> List[LLMConfig]:
        raw_configs = await self._load_llm_configs_from_file()
        validated_configs: List[LLMConfig] = []
        for config_data in raw_configs:
            try:
                validated_configs.append(LLMConfig(**config_data))
            except Exception as e: # PydanticValidationError
                logger.error(f"Validation error for LLM config data: {config_data}. Error: {e}", exc_info=True)
        return validated_configs

    async def get_llm_config_by_id(self, config_id: str) -> Optional[LLMConfig]:
        configs = await self.get_all_llm_configs()
        return next((cfg for cfg in configs if cfg.config_id == config_id), None)

    async def add_llm_config(self, config: LLMConfig) -> LLMConfig:
        all_configs_objects = await self.get_all_llm_configs()
        if any(existing_cfg.config_id == config.config_id for existing_cfg in all_configs_objects):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"LLM Config ID '{config.config_id}' already exists.")
        
        # Convert Pydantic models back to list of dicts for saving
        raw_configs_to_save = [cfg.model_dump(exclude_none=True) for cfg in all_configs_objects]
        raw_configs_to_save.append(config.model_dump(exclude_none=True))
        await self._save_llm_configs_to_file(raw_configs_to_save)
        return config

    async def update_llm_config(self, config_id: str, config_update_data: LLMConfig) -> LLMConfig:
        if config_id != config_update_data.config_id:
             raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Path config_id does not match body config_id.")

        all_configs_objects = await self.get_all_llm_configs()
        config_index = next((i for i, cfg in enumerate(all_configs_objects) if cfg.config_id == config_id), -1)

        if config_index == -1:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"LLM Config '{config_id}' not found for update.")
        
        all_configs_objects[config_index] = config_update_data # Replace with new Pydantic model
        raw_configs_to_save = [cfg.model_dump(exclude_none=True) for cfg in all_configs_objects]
        await self._save_llm_configs_to_file(raw_configs_to_save)
        return config_update_data

    async def remove_llm_config(self, config_id: str) -> bool:
        all_configs_objects = await self.get_all_llm_configs()
        original_length = len(all_configs_objects)
        
        configs_to_keep_objects = [cfg for cfg in all_configs_objects if cfg.config_id != config_id]

        if len(configs_to_keep_objects) == original_length:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"LLM Config '{config_id}' not found for deletion.")
        
        raw_configs_to_save = [cfg.model_dump(exclude_none=True) for cfg in configs_to_keep_objects]
        await self._save_llm_configs_to_file(raw_configs_to_save)
        return True


# --- FastAPI Router for LLM Configurations ---
llm_config_router = APIRouter(
    prefix="/llm_configs",
    tags=["LLM Configuration Management (File-based)"]
)

# Create a single instance of LLMConfigManager to be used by router
# The path can be configured via environment variable or default
llm_manager_instance = LLMConfigManager(config_file_path=LLM_CONFIGS_FILENAME)


@llm_config_router.get("", response_model=List[LLMConfig])
async def get_all_llm_configs_endpoint():
    return await llm_manager_instance.get_all_llm_configs()

@llm_config_router.get("/{config_id}", response_model=LLMConfig)
async def get_llm_config_by_id_endpoint(config_id: str):
    config = await llm_manager_instance.get_llm_config_by_id(config_id)
    if not config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"LLM Config ID '{config_id}' not found.")
    return config

@llm_config_router.post("", response_model=LLMConfig, status_code=status.HTTP_201_CREATED)
async def add_llm_config_endpoint(config_data: LLMConfig = Body(...)):
    return await llm_manager_instance.add_llm_config(config_data)

@llm_config_router.put("/{config_id}", response_model=LLMConfig)
async def update_llm_config_endpoint(config_id: str, config_data: LLMConfig = Body(...)):
    return await llm_manager_instance.update_llm_config(config_id, config_data)

@llm_config_router.delete("/{config_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_llm_config_endpoint(config_id: str):
    await llm_manager_instance.remove_llm_config(config_id)
    return # No content for 204


# --- Old functions (load_server_configs, save_server_configs) ---
# These are still present from your original file. You might want to refactor
# their usage in main.py to use an instance of ConfigManager if it makes sense,
# or keep them if they serve a distinct purpose.
_DEFAULT_FUNCTION_CONFIG_PATH = os.path.join(os.path.dirname(__file__), 'servers.json')

def load_server_configs(file_path: str = _DEFAULT_FUNCTION_CONFIG_PATH) -> Dict[str, ServerConfig]:
    # This function now acts as a convenience but might be redundant if ConfigManager is always used
    temp_manager = ConfigManager(file_path)
    return temp_manager.get_all_server_configs()

def save_server_configs(configs: Dict[str, ServerConfig], file_path: str = _DEFAULT_FUNCTION_CONFIG_PATH):
    # This function now acts as a convenience
    temp_manager = ConfigManager(file_path)
    temp_manager.save_all_server_configs(configs)


if __name__ == '__main__':
    # Example usage of the new ConfigManager class
    print(f"Running ConfigManager example with path: {_DEFAULT_FUNCTION_CONFIG_PATH}")
    manager = ConfigManager(_DEFAULT_FUNCTION_CONFIG_PATH) # Use the default path for the example
    
    # Ensure the file exists for the example or create sample data
    if not os.path.exists(_DEFAULT_FUNCTION_CONFIG_PATH) or os.path.getsize(_DEFAULT_FUNCTION_CONFIG_PATH) == 0:
        print("servers.json is missing or empty. Creating sample config for example.")
        sample_configs_data = {
            "example_server_from_main": {
                "name": "Example From Main",
                "description": "A sample server config created by config_manager.py direct run.",
                "command": "echo",
                "args": ["Hello from config_manager.py example"],
                "transport": "stdio",
                "capabilities_for_tool_config": []
            }
        }
        # Need to convert to ServerConfig instances before saving
        sample_server_config_objects = {k: ServerConfig(**v) for k, v in sample_configs_data.items()}
        manager.save_all_server_configs(sample_server_config_objects)
        print(f"Sample config created in {_DEFAULT_FUNCTION_CONFIG_PATH}")

    loaded_configs_via_manager = manager.get_all_server_configs()
    print("Loaded configs via ConfigManager instance:", loaded_configs_via_manager)
    
    if "example_server_from_main" in loaded_configs_via_manager:
        specific_config = manager.get_server_config("example_server_from_main")
        print("Specific config for 'example_server_from_main':", specific_config) 