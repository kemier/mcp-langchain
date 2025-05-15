#!/usr/bin/env python3
"""
Parser utilities for handling agent tool inputs and outputs.
"""
import logging
import json
from typing import Union
from langchain.agents.output_parsers.react_single_input import ReActSingleInputOutputParser
from langchain_core.agents import AgentAction, AgentFinish

# Initialize logger
logger = logging.getLogger(__name__)

class CustomReActParser(ReActSingleInputOutputParser):
    """
    Custom Parser to handle ReAct agent tool inputs more robustly.
    This parser improves on the standard ReAct parser by:
    1. Handling JSON inputs wrapped in markdown code blocks
    2. Properly parsing JSON tool inputs
    3. Providing better error handling
    """
    def parse(self, text: str) -> Union[AgentAction, AgentFinish]:
        """
        Parse the output of an LLM call to determine the next action.
        
        Args:
            text: The output of the LLM call
            
        Returns:
            AgentAction or AgentFinish
        """
        # First use the parent class's parse method
        parsed_output = super().parse(text)

        # If it's an AgentAction, attempt to parse the tool_input
        if isinstance(parsed_output, AgentAction):
            if isinstance(parsed_output.tool_input, str):
                raw_tool_input_str = parsed_output.tool_input
                cleaned_input_str = raw_tool_input_str.strip()

                # Handle markdown-formatted JSON
                if cleaned_input_str.startswith("```json"):
                    cleaned_input_str = cleaned_input_str[len("```json"):].strip()
                
                if cleaned_input_str.startswith("```"): 
                    cleaned_input_str = cleaned_input_str[len("```"):].strip()
                
                if cleaned_input_str.endswith("```"):
                    cleaned_input_str = cleaned_input_str[:-len("```")].strip()
                
                # Try to parse as JSON if it looks like JSON
                if ((cleaned_input_str.startswith("{") and cleaned_input_str.endswith("}")) or 
                    (cleaned_input_str.startswith("[") and cleaned_input_str.endswith("]"))):
                    try:
                        loaded_json = json.loads(cleaned_input_str)
                        parsed_output.tool_input = loaded_json
                        logger.debug(f"CustomReActParser successfully parsed tool_input string to JSON: {loaded_json}")
                    except json.JSONDecodeError as e:
                        logger.warning(f"CustomReActParser: Failed to parse cleaned tool_input string as JSON: '{cleaned_input_str}'. Error: {e}. Keeping as cleaned string.")
                        parsed_output.tool_input = cleaned_input_str 
                else:
                    parsed_output.tool_input = cleaned_input_str
                    logger.debug(f"CustomReActParser: Tool input does not appear to be JSON, kept as cleaned string: '{cleaned_input_str}'")
        
        return parsed_output 