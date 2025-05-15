#!/usr/bin/env python3
"""
I/O utilities for file operations.
"""
import json
import logging
import os
import yaml
from typing import Any, Dict, Optional, Union

# Initialize logger
logger = logging.getLogger(__name__)

def load_json_or_yaml(file_path_or_content: str) -> Optional[Dict[str, Any]]:
    """
    Load JSON or YAML data from a file path or directly from a string.
    
    Args:
        file_path_or_content: Either a file path or a JSON/YAML string
        
    Returns:
        Parsed data as a dictionary, or None if parsing fails
    """
    # First, check if the input is a file path
    if os.path.exists(file_path_or_content):
        try:
            # Determine file type from extension
            _, ext = os.path.splitext(file_path_or_content)
            
            with open(file_path_or_content, 'r') as f:
                content = f.read()
                
            if ext.lower() in ['.yaml', '.yml']:
                logger.info(f"Loading YAML data from file: {file_path_or_content}")
                return yaml.safe_load(content)
            elif ext.lower() == '.json':
                logger.info(f"Loading JSON data from file: {file_path_or_content}")
                return json.loads(content)
            else:
                # Try to detect format from content
                return _parse_string_content(content)
        except Exception as e:
            logger.error(f"Error loading from file {file_path_or_content}: {e}", exc_info=True)
            return None
    else:
        # Treat input as a string content
        return _parse_string_content(file_path_or_content)

def _parse_string_content(content: str) -> Optional[Dict[str, Any]]:
    """
    Parse a string as either JSON or YAML.
    
    Args:
        content: String containing JSON or YAML content
        
    Returns:
        Parsed data as a dictionary, or None if parsing fails
    """
    # First try parsing as JSON
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        # If JSON parsing fails, try YAML
        try:
            return yaml.safe_load(content)
        except yaml.YAMLError as e:
            logger.error(f"Failed to parse content as either JSON or YAML: {e}", exc_info=True)
            return None
    except Exception as e:
        logger.error(f"Unexpected error parsing content: {e}", exc_info=True)
        return None

def save_json(data: Any, file_path: str, indent: int = 2) -> bool:
    """
    Save data to a JSON file.
    
    Args:
        data: Data to save
        file_path: Path to save the file
        indent: JSON indentation level
        
    Returns:
        True if saved successfully, False otherwise
    """
    try:
        with open(file_path, 'w') as f:
            json.dump(data, f, indent=indent)
        logger.info(f"Successfully saved data to {file_path}")
        return True
    except Exception as e:
        logger.error(f"Error saving data to {file_path}: {e}", exc_info=True)
        return False

def save_yaml(data: Any, file_path: str) -> bool:
    """
    Save data to a YAML file.
    
    Args:
        data: Data to save
        file_path: Path to save the file
        
    Returns:
        True if saved successfully, False otherwise
    """
    try:
        with open(file_path, 'w') as f:
            yaml.safe_dump(data, f, default_flow_style=False)
        logger.info(f"Successfully saved data to {file_path}")
        return True
    except Exception as e:
        logger.error(f"Error saving data to {file_path}: {e}", exc_info=True)
        return False

def ensure_directory_exists(directory_path: str) -> bool:
    """
    Ensure that a directory exists, creating it if necessary.
    
    Args:
        directory_path: Path to the directory
        
    Returns:
        True if the directory exists or was created, False otherwise
    """
    try:
        if not os.path.exists(directory_path):
            os.makedirs(directory_path)
            logger.info(f"Created directory: {directory_path}")
        return True
    except Exception as e:
        logger.error(f"Error creating directory {directory_path}: {e}", exc_info=True)
        return False 