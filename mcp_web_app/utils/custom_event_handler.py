#!/usr/bin/env python3
"""
Custom event handlers for streaming LLM and agent responses.
"""
import logging
import sys
from enum import Enum, auto
from typing import Any, Dict, List, Optional, AsyncGenerator

from langchain_core.callbacks.base import BaseCallbackHandler

# Initialize logger
logger = logging.getLogger(__name__)

class EventType(Enum):
    """Enum for different types of streaming events."""
    TOKEN = auto()       # New token from LLM
    TOOL_START = auto()  # Tool execution started
    TOOL_END = auto()    # Tool execution completed
    ERROR = auto()       # Error event
    END = auto()         # End of stream
    CHAIN_END = auto()   # End of chain with final result
    THINKING = auto()    # Agent thinking step
    ACTION = auto()      # Agent taking action

class CustomAsyncIteratorCallbackHandler(BaseCallbackHandler):
    """
    Callback handler that forwards events to an output stream function.
    
    This is a more flexible version of StreamingCallback that can handle
    various event types and forward them to any output function.
    """
    
    def __init__(self, output_stream_fn):
        """
        Initialize with a function to call for each event.
        
        Args:
            output_stream_fn: Function that takes (event_type, data) parameters
        """
        self.output_stream_fn = output_stream_fn
        super().__init__()
    
    async def on_llm_new_token(self, token: str, **kwargs: Any) -> None:
        """Send new token events."""
        await self.output_stream_fn(EventType.TOKEN.name, token)
    
    async def on_llm_error(self, error: Exception, **kwargs: Any) -> None:
        """Send error events."""
        await self.output_stream_fn(EventType.ERROR.name, {"error": str(error)})
    
    async def on_tool_start(
        self, serialized: Dict[str, Any], input_str: str, **kwargs: Any
    ) -> None:
        """Send tool start events."""
        await self.output_stream_fn(EventType.TOOL_START.name, {
            "name": serialized.get("name", "unknown_tool"),
            "input": input_str
        })
    
    async def on_tool_end(
        self, output: str, observation_prefix: Optional[str] = None, **kwargs: Any
    ) -> None:
        """Send tool end events."""
        await self.output_stream_fn(EventType.TOOL_END.name, {
            "output": output,
            "prefix": observation_prefix
        })
    
    async def on_agent_action(self, action, **kwargs: Any) -> None:
        """Send agent action events."""
        if hasattr(action, "tool") and hasattr(action, "tool_input"):
            await self.output_stream_fn(EventType.ACTION.name, {
                "tool": action.tool,
                "input": action.tool_input
            })
    
    async def on_chain_end(self, outputs: Dict[str, Any], **kwargs: Any) -> None:
        """Send chain end events with output."""
        # Extract the actual output content from various possible formats
        content = None
        
        if isinstance(outputs, dict):
            if "output" in outputs:
                content = outputs["output"]
            elif "response" in outputs and hasattr(outputs["response"], "content"):
                content = outputs["response"].content
        elif hasattr(outputs, "content"):
            content = outputs.content
        
        if content:
            await self.output_stream_fn(EventType.CHAIN_END.name, {"content": content})

class MCPEventCollector(BaseCallbackHandler):
    """
    Callback handler that collects and stores the final output from agent execution.
    
    This is a simpler version that can be used for non-streaming scenarios where
    we just want to capture the final result.
    """
    
    def __init__(self):
        """Initialize the collector."""
        super().__init__()
        self._final_output = None
        self._chain_end_outputs = []
        self._full_message = None
    
    def get_final_output(self) -> Optional[str]:
        """
        Get the final output that was collected.
        
        Returns:
            The final output string, or None if no output was collected
        """
        # Try the full message first
        if self._full_message:
            return self._full_message
            
        # Then try the last chain_end output
        if self._chain_end_outputs:
            return self._chain_end_outputs[-1]
            
        # Fall back to the explicit final output
        return self._final_output
    
    def on_agent_finish(self, finish: Any, **kwargs: Any) -> None:
        """Capture agent finish output."""
        if hasattr(finish, "return_values") and "output" in finish.return_values:
            self._final_output = finish.return_values["output"]
    
    def on_chain_end(self, outputs: Dict[str, Any], **kwargs: Any) -> None:
        """Capture chain end output."""
        content = None
        
        if isinstance(outputs, dict):
            if "output" in outputs:
                content = outputs["output"]
            elif "response" in outputs and hasattr(outputs["response"], "content"):
                content = outputs["response"].content
        elif hasattr(outputs, "content"):
            content = outputs.content
        
        if content:
            self._chain_end_outputs.append(content)
    
    def on_text(self, text: str, **kwargs: Any) -> None:
        """Capture raw text."""
        self._full_message = text