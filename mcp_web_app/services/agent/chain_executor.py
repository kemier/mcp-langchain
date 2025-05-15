#!/usr/bin/env python3
"""
Chain executor implementation for streamlined LLM chaining.
"""
import logging
from typing import Dict, Any, Optional, AsyncIterator, Union

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.runnables import RunnableSerializable, Runnable, RunnableConfig
from langchain_core.messages import (
    AIMessage, AIMessageChunk, BaseMessage
)

# Initialize logger
logger = logging.getLogger(__name__)

class SimpleChainExecutor(RunnableSerializable):
    """
    A streamlined executor for simple LLM chains.
    
    This executor simplifies the process of running a prompt template
    through an LLM and handling the various output formats and streaming.
    """
    # Define required fields
    executable_pipeline: Runnable 
    llm_instance_ref: BaseChatModel

    class Config:
        """Pydantic config for allowing arbitrary types."""
        arbitrary_types_allowed = True

    def __init__(self, 
                 prompt_template: ChatPromptTemplate, 
                 llm_instance: BaseChatModel, 
                 **kwargs):
        """
        Initialize the chain executor with a prompt template and LLM.
        
        Args:
            prompt_template: The prompt template to use
            llm_instance: The language model to use
            **kwargs: Additional arguments to pass to the parent class
        """
        # Explicitly construct the pipeline that will be executed
        pipeline = prompt_template | llm_instance
        
        # Pass to super's __init__ to set the fields
        super().__init__(executable_pipeline=pipeline, 
                          llm_instance_ref=llm_instance, 
                          **kwargs)
        
        logger.info(f"SimpleChainExecutor initialized. Executable pipeline: {self.executable_pipeline}, LLM ref: {self.llm_instance_ref}")

    def _call_chain_for_invoke(self, 
                               inputs: Dict[str, Any], 
                               config: Optional[RunnableConfig] = None) -> AIMessage:
        """
        Call the chain synchronously and format the response.
        
        Args:
            inputs: Input data for the chain
            config: Optional configuration for the runnable
            
        Returns:
            An AIMessage containing the formatted response
        """
        # Ensure chat_history exists in inputs
        if "chat_history" not in inputs:
            inputs["chat_history"] = []
            
        # Invoke the pipeline
        response_message = self.executable_pipeline.invoke(inputs, config=config)
        
        # Process the response into a standardized format
        return self._format_response(response_message)
    
    def _format_response(self, response_message: Any) -> AIMessage:
        """
        Convert various response types into a standardized AIMessage.
        
        Args:
            response_message: The raw response from the chain
            
        Returns:
            An AIMessage with proper content and metadata
        """
        final_content = ""
        final_metadata = {}
        
        if isinstance(response_message, BaseMessage):
            final_content = response_message.content
            final_metadata = response_message.response_metadata or {}
            
            # Preserve tool calls if they are part of the message
            if hasattr(response_message, 'tool_calls') and response_message.tool_calls:
                final_metadata['tool_calls'] = response_message.tool_calls
            if hasattr(response_message, 'tool_call_chunks') and response_message.tool_call_chunks:
                final_metadata['tool_call_chunks'] = response_message.tool_call_chunks
                
        elif isinstance(response_message, str):
            final_content = response_message
            
        elif isinstance(response_message, dict) and 'content' in response_message:
            final_content = str(response_message['content'])
            final_metadata = {k: v for k, v in response_message.items() if k != 'content'}
            
        else: 
            logger.warning(f"Unexpected response type from chain: {type(response_message)}. Converting to string.")
            final_content = str(response_message)
            
        return AIMessage(content=final_content, response_metadata=final_metadata)

    def invoke(self, 
               inputs: Dict[str, Any], 
               config: Optional[RunnableConfig] = None) -> Dict[str, Any]:
        """
        Invoke the chain synchronously.
        
        Args:
            inputs: Input data for the chain
            config: Optional configuration for the runnable
            
        Returns:
            A dictionary containing the output
        """
        response_message = self._call_chain_for_invoke(inputs, config)
        return {"output": response_message.content}

    async def _call_chain_for_ainvoke(self, 
                                      inputs: Dict[str, Any], 
                                      config: Optional[RunnableConfig] = None) -> AIMessage:
        """
        Call the chain asynchronously and format the response.
        
        Args:
            inputs: Input data for the chain
            config: Optional configuration for the runnable
            
        Returns:
            An AIMessage containing the formatted response
        """
        # Ensure chat_history exists in inputs
        if "chat_history" not in inputs:
            inputs["chat_history"] = []
            
        # Invoke the pipeline asynchronously
        response_message = await self.executable_pipeline.ainvoke(inputs, config=config)
        
        # Use the same formatting logic as the synchronous version
        return self._format_response(response_message)

    async def ainvoke(self, 
                      inputs: Dict[str, Any], 
                      config: Optional[RunnableConfig] = None) -> Dict[str, Any]:
        """
        Invoke the chain asynchronously.
        
        Args:
            inputs: Input data for the chain
            config: Optional configuration for the runnable
            
        Returns:
            A dictionary containing the output
        """
        response_message = await self._call_chain_for_ainvoke(inputs, config)
        return {"output": response_message.content}

    async def astream(self, 
                      inputs: Dict[str, Any], 
                      config: Optional[RunnableConfig] = None, 
                      **kwargs: Optional[Any]) -> AsyncIterator[AIMessageChunk]:
        """
        Stream the chain's output asynchronously.
        
        Args:
            inputs: Input data for the chain
            config: Optional configuration for the runnable
            **kwargs: Additional arguments
            
        Yields:
            Chunks of the LLM's output as they become available
        """
        logger.info(f"SimpleChainExecutor.astream CALLED. Input keys: {list(inputs.keys())}")
        if "chat_history" not in inputs:
            inputs["chat_history"] = []

        # Stream from the pipeline
        logger.debug(f"SimpleChainExecutor.astream: About to iterate self.executable_pipeline.astream() with inputs: {str(inputs)[:200]}")
        async for chunk in self.executable_pipeline.astream(inputs, config=config):
            # Handle different chunk types
            logger.debug(f"SimpleChainExecutor.astream: Received chunk of type {type(chunk)}: {str(chunk)[:100]}")
            if isinstance(chunk, AIMessageChunk):
                yield chunk
            elif isinstance(chunk, BaseMessage): 
                if chunk.content or chunk.content == "":  # Yield even if content is empty string
                    yield AIMessageChunk(content=chunk.content)
            elif isinstance(chunk, str):
                yield AIMessageChunk(content=chunk)
            elif isinstance(chunk, dict) and "content" in chunk and isinstance(chunk["content"], str):
                yield AIMessageChunk(content=chunk["content"])
            else:
                # Check if the chunk has actual content to avoid logging empty chunks
                str_chunk_content = str(chunk) if chunk is not None else ""
                if str_chunk_content and str_chunk_content.strip() and str_chunk_content != "{}":
                    logger.debug(f"SimpleChainExecutor.astream received unhandled chunk type: {type(chunk)}, "
                                f"yielding as string content: '{str_chunk_content}'")
                    yield AIMessageChunk(content=str_chunk_content) 