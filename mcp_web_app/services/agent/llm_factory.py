#!/usr/bin/env python3
"""
Factory methods for creating and configuring LLM instances.
"""
import logging
from typing import Optional, Dict, Any
import os

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_community.chat_models import ChatOllama
from langchain_deepseek import ChatDeepSeek

from ...models.models import LLMConfig

# Initialize logger
logger = logging.getLogger(__name__)

async def create_ollama_instance(
    llm_config: LLMConfig, 
    config_id: str
) -> Optional[BaseChatModel]:
    """
    Create an Ollama LLM instance from the given configuration.
    
    Args:
        llm_config: Configuration for the LLM
        config_id: Identifier for the configuration
        
    Returns:
        A configured Ollama LLM instance, or None if creation fails
    """
    if not llm_config.ollama_config:
        logger.error(f"Ollama configuration not found in LLMConfig for config_id '{config_id}'")
        return None

    try:
        # Access model and temperature from the nested ollama_config
        model_name = llm_config.ollama_config.model or "llama3"
        temperature = llm_config.ollama_config.temperature
        base_url = llm_config.ollama_config.base_url
        ollama_format = llm_config.ollama_config.format # Get format from config

        # Create the Ollama instance
        # Removed top_p and other_params as they are not in the current OllamaConfig model
        # and llm_config.parameters does not exist.
        # If needed, add these fields to the OllamaConfig Pydantic model.
        
        ollama_params = {
            "model": model_name,
            "temperature": temperature,
            "base_url": base_url
        }
        if ollama_format:
            ollama_params["format"] = ollama_format
            
        ollama_instance = ChatOllama(**ollama_params)
        
        logger.info(f"Successfully created Ollama LLM instance for config_id '{config_id}' with model '{model_name}' and format '{ollama_format}'")
        return ollama_instance
        
    except Exception as e:
        logger.error(f"Failed to create Ollama LLM for config_id '{config_id}': {str(e)}", exc_info=True)
        return None

async def create_deepseek_instance(
    llm_config: LLMConfig, 
    config_id: str
) -> Optional[BaseChatModel]:
    """
    Create a DeepSeek LLM instance from the given configuration.
    
    Args:
        llm_config: Configuration for the LLM
        config_id: Identifier for the configuration
        
    Returns:
        A configured DeepSeek LLM instance, or None if creation fails
    """
    if not llm_config.deepseek_config:
        logger.error(f"DeepSeek configuration not found in LLMConfig for config_id '{config_id}'")
        return None

    try:
        deepseek_cfg = llm_config.deepseek_config

        # Resolve API key: use specific key from config if provided, else from env var if defined
        api_key = deepseek_cfg.api_key
        if not api_key and llm_config.api_key_env_var:
            api_key = os.getenv(llm_config.api_key_env_var)
        
        if not api_key:
            logger.error(f"DeepSeek API key not found for config_id '{config_id}'. Checked deepseek_config.api_key and env var '{llm_config.api_key_env_var}'.")
            return None

        model_name = deepseek_cfg.model or "deepseek-chat"
        temperature = deepseek_cfg.temperature
        
        # Assuming base_url and other_params would be part of DeepSeekConfig if needed.
        # For now, only using model, api_key, and temperature from the model.
        # If you need base_url or other model_kwargs, add them to the DeepSeekConfig Pydantic model.

        # Create the DeepSeek instance
        deepseek_instance = ChatDeepSeek(
            model=model_name,
            api_key=api_key,
            temperature=temperature
            # model_kwargs can be added here if defined in DeepSeekConfig
        )
        
        logger.info(f"Successfully created DeepSeek LLM instance for config_id '{config_id}' with model '{model_name}'")
        return deepseek_instance
        
    except Exception as e:
        logger.error(f"Failed to create DeepSeek LLM for config_id '{config_id}': {str(e)}", exc_info=True)
        return None

async def create_llm_from_config(
    llm_config: LLMConfig, 
    config_id: str
) -> Optional[BaseChatModel]:
    """
    Create an LLM instance from the given configuration.
    
    Args:
        llm_config: Configuration for the LLM
        config_id: Identifier for the configuration
        
    Returns:
        A configured LLM instance, or None if creation fails
    """
    # Determine the type of LLM to create
    # Use llm_config.provider instead of llm_config.llm_type
    llm_provider = llm_config.provider.lower()
    
    if llm_provider == "ollama":
        return await create_ollama_instance(llm_config, config_id)
    elif llm_provider == "deepseek":
        return await create_deepseek_instance(llm_config, config_id)
    else:
        logger.error(f"Unsupported LLM type '{llm_provider}' for config_id '{config_id}'")
        return None 