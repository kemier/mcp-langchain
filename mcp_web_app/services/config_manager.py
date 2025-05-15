import json
from pathlib import Path
from typing import Dict, List, Optional, Any

from pydantic import BaseModel, ValidationError

from mcp_web_app.models.models import LLMConfig, ServerConfig

# Path for the main server config (e.g., FastAPI server settings, if any)
# This was originally assumed to be config.json for a single ServerConfig object.
# If config.json is for general app settings and not tool servers, its loading needs to be specific.
APP_CONFIG_FILE_PATH = Path(__file__).parent.parent / "config.json" 

# Path for tool server configurations (like the old servers.json)
TOOL_SERVERS_CONFIG_FILE_PATH = Path(__file__).parent.parent / "servers.json"
LLM_CONFIG_FILE_PATH = Path(__file__).parent.parent / "llm_configs.json"


class ConfigManager:
    """Manages application, LLM, and tool server configurations."""

    _instance = None
    _app_config: Optional[Dict[str, Any]] = None # General app config from config.json
    _tool_server_configs: Dict[str, ServerConfig] = {} # Loaded from servers.json
    _llm_configs: Dict[str, LLMConfig] = {}
    _default_llm_id: Optional[str] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ConfigManager, cls).__new__(cls)
            cls._instance._load_app_config() # Load general app config
            cls._instance._load_tool_server_configs() # Load tool server configs
            cls._instance._load_llm_configs()
        return cls._instance

    def _load_app_config(self):
        """Loads the main application configuration from config.json (if it exists)."""
        if APP_CONFIG_FILE_PATH.exists():
            try:
                with open(APP_CONFIG_FILE_PATH, "r") as f:
                    config_data = json.load(f)
                # Assuming config.json might not be a single ServerConfig object
                # but a general dict. Adjust if it has a Pydantic model.
                self._app_config = config_data 
                print(f"Successfully loaded app config from {APP_CONFIG_FILE_PATH}")
            except json.JSONDecodeError as e:
                print(f"Error loading app config from {APP_CONFIG_FILE_PATH}: {e}")
                self._app_config = None
            except Exception as e:
                print(f"An unexpected error occurred while loading app config: {e}")
                self._app_config = None
        else:
            print(f"App config file not found at {APP_CONFIG_FILE_PATH}. Using defaults or environment variables if applicable.")
            self._app_config = None

    def _load_tool_server_configs(self):
        """Loads tool server configurations from servers.json."""
        if TOOL_SERVERS_CONFIG_FILE_PATH.exists():
            try:
                with open(TOOL_SERVERS_CONFIG_FILE_PATH, "r") as f:
                    configs_data = json.load(f)
                if not isinstance(configs_data, dict):
                    print(f"Tool servers config file {TOOL_SERVERS_CONFIG_FILE_PATH} is not in the expected format (should be a dict of server_name: ServerConfig).")
                    return
                
                loaded_server_names = []
                for server_name, server_data in configs_data.items():
                    try:
                        server_config = ServerConfig(**server_data['config'])
                        self._tool_server_configs[server_name] = server_config
                        loaded_server_names.append(server_name)
                    except ValidationError as e:
                        print(f"Error validating tool server config for '{server_name}': {e}")
                if loaded_server_names:
                    print(f"Successfully loaded tool server configs for: {', '.join(loaded_server_names)} from {TOOL_SERVERS_CONFIG_FILE_PATH}")
            except json.JSONDecodeError as e:
                print(f"Error decoding JSON from {TOOL_SERVERS_CONFIG_FILE_PATH}: {e}")
            except Exception as e:
                print(f"An unexpected error occurred while loading tool server configs: {e}")
        else:
            print(f"Tool servers config file not found at {TOOL_SERVERS_CONFIG_FILE_PATH}. No tool servers will be loaded from it.")
            
    def _load_llm_configs(self):
        """Loads LLM configurations from llm_configs.json."""
        if LLM_CONFIG_FILE_PATH.exists():
            try:
                with open(LLM_CONFIG_FILE_PATH, "r") as f:
                    llm_configs_data = json.load(f)
                
                if not isinstance(llm_configs_data, dict):
                    print(f"LLM config file {LLM_CONFIG_FILE_PATH} is not in the expected format (should be a dictionary of LLM configurations).")
                    return

                loaded_configs_ids = []
                potential_default_id = None

                for llm_id, llm_data in llm_configs_data.items():
                    if not isinstance(llm_data, dict):
                        print(f"Skipping invalid LLM config entry for ID '{llm_id}': not a dictionary.")
                        continue
                    
                    # Ensure the config_id from the model matches the key from the JSON dict
                    # If llm_data also contains 'config_id', the one from the key takes precedence for internal mapping.
                    # The LLMConfig model itself expects 'config_id'.
                    current_config_id = llm_data.get("config_id")
                    if not current_config_id: # if 'config_id' field is missing in JSON value
                        llm_data["config_id"] = llm_id # Use the key as config_id
                    elif current_config_id != llm_id:
                        print(f"Warning: LLM ID mismatch for '{llm_id}'. Key is '{llm_id}', but 'config_id' field in value is '{current_config_id}'. Using key '{llm_id}'.")
                        llm_data["config_id"] = llm_id


                    try:
                        llm_config = LLMConfig(**llm_data)
                        self._llm_configs[llm_id] = llm_config # Store with the key as ID
                        loaded_configs_ids.append(llm_id)
                        
                        if llm_data.get("is_default") is True:
                            if potential_default_id is not None:
                                print(f"Warning: Multiple default LLMs specified. Using the last one encountered: '{llm_id}'.")
                            potential_default_id = llm_id

                    except ValidationError as e:
                        print(f"Error validating LLM config for ID '{llm_id}': {e}")
                
                if loaded_configs_ids:
                    print(f"Successfully loaded LLM configs for: {', '.join(loaded_configs_ids)} from {LLM_CONFIG_FILE_PATH}")

                if potential_default_id:
                    self._default_llm_id = potential_default_id
                    print(f"Default LLM set to: {self._default_llm_id}")
                elif self._llm_configs:
                    # If no explicit default, try to find one marked in model, or take the first one as a fallback
                    found_model_default = next((cfg_id for cfg_id, cfg in self._llm_configs.items() if cfg.is_default), None)
                    if found_model_default:
                        self._default_llm_id = found_model_default
                        print(f"Default LLM set using 'is_default' flag in model: {self._default_llm_id}")
                    else:
                        first_llm_key = next(iter(self._llm_configs.keys()), None)
                        if first_llm_key:
                             self._default_llm_id = first_llm_key
                             print(f"No explicit default LLM set. Using the first loaded LLM as default: {self._default_llm_id}")
                else:
                     print("No LLM configurations loaded. No default LLM will be set.")


            except json.JSONDecodeError as e:
                print(f"Error decoding JSON from {LLM_CONFIG_FILE_PATH}: {e}")
            except Exception as e:
                print(f"An unexpected error occurred while loading LLM configs: {e}")
        else:
            print(f"LLM config file not found at {LLM_CONFIG_FILE_PATH}. No LLMs will be available.")

    def get_app_config(self) -> Optional[Dict[str, Any]]:
        """Returns the loaded application configuration (from config.json)."""
        return self._app_config

    def get_all_tool_server_configs(self) -> Dict[str, ServerConfig]:
        """Returns a dictionary of all loaded tool server configurations."""
        return self._tool_server_configs

    def get_tool_server_config(self, server_name: str) -> Optional[ServerConfig]:
        """Returns a specific tool server configuration by its name."""
        return self._tool_server_configs.get(server_name)

    def get_llm_configs(self) -> List[LLMConfig]:
        """Returns a list of all loaded LLM configurations."""
        return list(self._llm_configs.values())

    def get_llm_config_by_id(self, llm_id: str) -> Optional[LLMConfig]:
        """Returns a specific LLM configuration by its ID."""
        return self._llm_configs.get(llm_id)
        
    def get_default_llm_config(self) -> Optional[LLMConfig]:
        """Returns the default LLM configuration if set, otherwise None."""
        if self._default_llm_id:
            return self.get_llm_config_by_id(self._default_llm_id)
        # Fallback: if no explicit default, return the first loaded LLM, if any
        if self._llm_configs:
            return next(iter(self._llm_configs.values()), None)
        return None

    # +++ NEW METHODS for LLM Config CRUD +++
    def _save_llm_configs(self):
        """Saves the current state of _llm_configs to llm_configs.json."""
        try:
            # Prepare data for JSON serialization: convert LLMConfig objects to dicts
            configs_to_save = { 
                config_id: config.model_dump(exclude_none=True) 
                for config_id, config in self._llm_configs.items()
            }
            with open(LLM_CONFIG_FILE_PATH, "w") as f:
                json.dump(configs_to_save, f, indent=4)
            print(f"Successfully saved LLM configurations to {LLM_CONFIG_FILE_PATH}")
        except Exception as e:
            print(f"Error saving LLM configurations to {LLM_CONFIG_FILE_PATH}: {e}")
            # Potentially raise the error or handle it more gracefully depending on requirements

    def add_llm_config(self, llm_config: LLMConfig) -> LLMConfig:
        """Adds a new LLM configuration and saves it."""
        if llm_config.config_id in self._llm_configs:
            raise ValueError(f"LLM configuration with ID '{llm_config.config_id}' already exists.")

        # If this new config is set as default, unset any other existing default
        if llm_config.is_default:
            for config_id in self._llm_configs:
                if self._llm_configs[config_id].is_default:
                    self._llm_configs[config_id].is_default = False
            self._default_llm_id = llm_config.config_id
        
        self._llm_configs[llm_config.config_id] = llm_config
        self._save_llm_configs() # Persist changes
        print(f"Added LLM config: {llm_config.config_id}")
        if llm_config.is_default:
             print(f"Set {llm_config.config_id} as new default LLM.")
        return llm_config

    def update_llm_config(self, config_id: str, updated_config_data: Dict[str, Any]) -> Optional[LLMConfig]:
        """Updates an existing LLM configuration and saves it."""
        existing_config = self._llm_configs.get(config_id)
        if not existing_config:
            return None # Or raise ValueError

        # Ensure config_id from payload matches the one in path, or is not present to change it.
        if "config_id" in updated_config_data and updated_config_data["config_id"] != config_id:
            raise ValueError("Cannot change config_id during update. Delete and add new if ID change is needed.")
        
        # Create a copy of the existing config data and update it
        # This ensures that all fields are present before Pydantic validation
        current_config_dict = existing_config.model_dump()
        current_config_dict.update(updated_config_data)
        
        try:
            updated_llm_config = LLMConfig(**current_config_dict)
        except ValidationError as e:
            print(f"Validation error updating LLM config '{config_id}': {e}")
            raise # Re-raise the validation error to be handled by the caller

        # Handle default status change
        if updated_llm_config.is_default:
            if self._default_llm_id != config_id: # If it wasn't default before, or default changed
                for cfg_id in self._llm_configs:
                    if self._llm_configs[cfg_id].is_default and cfg_id != config_id:
                        self._llm_configs[cfg_id].is_default = False
                self._default_llm_id = config_id
                print(f"Set {config_id} as new default LLM.")
        elif self._default_llm_id == config_id and not updated_llm_config.is_default:
            # If it was default and now it's not, clear default or find a new one
            self._default_llm_id = None
            print(f"Unset {config_id} as default LLM. Finding new default...")
            # Attempt to set a new default (e.g., the first one found marked as default, or just the first)
            new_default = next((cfg.config_id for cfg in self._llm_configs.values() if cfg.is_default and cfg.config_id != config_id), None)
            if not new_default and self._llm_configs:
                 new_default = next(iter(self._llm_configs.keys()), None)
            if new_default:
                self._default_llm_id = new_default
                if self._llm_configs[new_default]: self._llm_configs[new_default].is_default = True # Ensure the flag is set
                print(f"New default LLM set to: {self._default_llm_id}")
            else:
                print("No other LLM available to set as default.")

        self._llm_configs[config_id] = updated_llm_config
        self._save_llm_configs() # Persist changes
        print(f"Updated LLM config: {config_id}")
        return updated_llm_config

    def delete_llm_config(self, config_id: str) -> bool:
        """Deletes an LLM configuration and saves the changes."""
        if config_id not in self._llm_configs:
            return False

        was_default = self._llm_configs[config_id].is_default
        del self._llm_configs[config_id]
        print(f"Deleted LLM config: {config_id}")

        if was_default:
            self._default_llm_id = None
            print(f"{config_id} was the default LLM. Finding new default...")
            # Attempt to set a new default
            new_default = next((cfg.config_id for cfg in self._llm_configs.values() if cfg.is_default), None)
            if not new_default and self._llm_configs:
                new_default = next(iter(self._llm_configs.keys()), None) # Pick first available
            
            if new_default:
                self._default_llm_id = new_default
                if self._llm_configs[new_default]: self._llm_configs[new_default].is_default = True # Ensure flag is set for the new default
                print(f"New default LLM set to: {self._default_llm_id}")
            else:
                print("No LLM configurations left to set as default.")
        
        self._save_llm_configs() # Persist changes
        return True
    # +++ END NEW METHODS +++

# Global instance
config_manager = ConfigManager() 