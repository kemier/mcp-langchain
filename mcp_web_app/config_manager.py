import json
import os
from typing import Dict, Optional
from .models.models import ServerConfig
import logging

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

# It's good practice to have a logger instance for this module too

# --- Keep old functions for now, but ideally refactor their usage in main.py --- 
# --- Or mark as deprecated / for internal use if ConfigManager is the primary interface --- 

# Default path for functions if not using the class instance
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