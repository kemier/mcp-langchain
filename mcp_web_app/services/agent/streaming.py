#!/usr/bin/env python3
"""
Streaming utilities for handling agent event streams.
"""
import logging
import sys
import traceback
from typing import Dict, Any, Optional, AsyncGenerator, Union, Callable

from langchain_core.messages import AIMessageChunk
from langchain_core.callbacks.base import BaseCallbackHandler

from ..agent.callbacks import StreamingCallback, MCPEventCollector
from ...utils.custom_event_handler import EventType

# Initialize logger
logger = logging.getLogger(__name__)

async def handle_simple_chain_stream(
    session_id: str,
    agent_executor: Any,
    input_data: Dict[str, Any],
    callbacks: list,
    output_stream_fn: Callable,
    config: Dict[str, Any]
) -> Optional[str]:
    """
    Handle streaming for a SimpleChainExecutor.
    
    Args:
        session_id: The session ID
        agent_executor: The agent executor to stream from
        input_data: The input data for the executor
        callbacks: Callbacks to use during execution
        output_stream_fn: Function to call with streaming events
        config: Configuration for the execution
        
    Returns:
        The final accumulated content, or None on error
    """
    logger.info(f"Session {session_id}: ENTERING handle_simple_chain_stream. Agent executor type: {type(agent_executor)}")
    accumulated_content = ""
    stream_chunk_count = 0
    
    try:
        # Stream from the executor
        async for chunk in agent_executor.astream(input_data, config=config):
            stream_chunk_count += 1
            
            # Handle different possible chunk types from astream
            chunk_content = None
            if isinstance(chunk, AIMessageChunk):
                chunk_content = chunk.content
            elif isinstance(chunk, str):
                chunk_content = chunk
            elif isinstance(chunk, dict) and 'content' in chunk:
                chunk_content = chunk.get('content', '')
            elif hasattr(chunk, 'content'):
                chunk_content = getattr(chunk, 'content', '')

            # Send content if we have any
            if chunk_content is not None and chunk_content != "":
                logger.debug(f"Session {session_id}: SimpleChain stream chunk "
                            f"#{stream_chunk_count} content: '{chunk_content}'")
                await output_stream_fn(EventType.TOKEN, chunk_content)
                accumulated_content += chunk_content
            else:
                logger.debug(f"Session {session_id}: SimpleChain stream chunk "
                            f"#{stream_chunk_count} was empty or None. Type: {type(chunk)}")

        logger.info(f"Session {session_id}: SUCCESSFULLY COMPLETED iteration of "
                   f"SimpleChainExecutor.astream. Total chunks: {stream_chunk_count}")
        
        return accumulated_content
        
    except Exception as e:
        logger.error(f"Session {session_id}: Error during SimpleChainExecutor.astream(): {e}", 
                    exc_info=True)
        # Send error via output_stream_fn
        await output_stream_fn(EventType.ERROR, 
                        {"error": f"Error during simple stream: {str(e)}"})
        return None

async def handle_agent_stream_events(
    session_id: str,
    agent_executor: Any,
    input_data: Dict[str, Any],
    callbacks: list,
    output_stream_fn: Callable,
    config: Dict[str, Any]
) -> Optional[str]:
    """
    Handle streaming events for a regular agent executor.
    
    Args:
        session_id: The session ID
        agent_executor: The agent executor to stream from
        input_data: The input data for the executor
        callbacks: Callbacks to use during execution
        output_stream_fn: Function to call with streaming events
        config: Configuration for the execution
        
    Returns:
        The final captured content, or None if not available
    """
    stream_event_count = 0
    final_response_content = None
    mcp_event_collector = next((c for c in callbacks if isinstance(c, MCPEventCollector)), None)
    
    # Stream events from the executor
    async for event in agent_executor.astream_events(input_data, version="v1", config=config):
        stream_event_count += 1
        logger.debug(f"Session {session_id}: Langchain event #{stream_event_count} received: "
                    f"{event.get('event')} - Name: {event.get('name')}")
        
        # Capture final response from the event stream (fallback mechanism)
        if event["event"] == "on_chain_end":
            parent_ids = event.get("parent_ids")
            # Check if it's the end of the RunnableWithMessageHistory or an event without parents
            if event.get("name") == "RunnableWithMessageHistory" or not parent_ids: 
                outputs = event.get("data", {}).get("output", {})
                captured_content = None
                
                if isinstance(outputs, dict) and "content" in outputs:
                    captured_content = outputs["content"]
                elif isinstance(outputs, dict) and "output" in outputs:
                    captured_content = outputs["output"]
                elif hasattr(outputs, 'content'):
                    captured_content = outputs.content
                
                if captured_content is not None:
                    final_response_content = captured_content
                    logger.info(f"Session {session_id}: Captured potential final_response_content "
                               f"from on_chain_end event: "
                               f"{final_response_content[:100] if final_response_content else 'None'}")

    logger.info(f"Session {session_id}: SUCCESSFULLY COMPLETED iteration of "
               f"agent_executor.astream_events. Total events: {stream_event_count}")
    
    # If final_response_content wasn't captured via the event, try the collector
    if not final_response_content and mcp_event_collector:
        collected_output = mcp_event_collector.get_final_output()
        if collected_output:
            final_response_content = collected_output
            logger.info(f"Session {session_id}: Using final response from MCPEventCollector: "
                       f"{final_response_content[:100] if final_response_content else 'None'}")
    
    return final_response_content

async def stream_agent_response(
    session_id: str,
    question: str,
    session_data: Dict[str, Any],
    output_stream_fn: Callable[[str, Any], None]
) -> None:
    """
    Stream an agent's response to a question.
    
    Args:
        session_id: The session ID
        question: The user's question
        session_data: Session data containing the agent executor
        output_stream_fn: Function to call with streaming events
    """
    logger.info(f"---> [SERVICE ENTRY] stream_agent_response ENTERED for session {session_id}")
    logger.info(f"stream_agent_response for session {session_id} CALLED with q: '{question[:50]}'")
    
    stream_terminated_successfully = False # Flag to track if a terminal event was sent

    try:
        # Get the agent executor from the session
        agent_executor = session_data.get("agent_executor")
        raw_agent_executor = session_data.get("raw_agent_executor")

        if not agent_executor:
            logger.error(f"Session {session_id}: Agent executor not available")
            await output_stream_fn(EventType.ERROR, {"error": "Agent not initialized for streaming"})
            await output_stream_fn(EventType.END, {"content": "Stream terminated due to initialization error"})
            stream_terminated_successfully = True # Mark as terminated
            return

        # Create callbacks for streaming
        custom_handler = StreamingCallback(output_stream_fn)
        mcp_event_collector = MCPEventCollector()
        callbacks = [custom_handler, mcp_event_collector]
        
        # Prepare input data and configuration
        input_data = {"input": question}
        config_for_stream = {
            "callbacks": callbacks,
            "configurable": {"session_id": session_id}
        }
        
        # Determine how to handle streaming based on executor type
        final_response_content = None
        
        if hasattr(raw_agent_executor, "executable_pipeline"):  # SimpleChainExecutor
            logger.info(f"Session {session_id}: Using agent_executor.astream() for SimpleChainExecutor")
            logger.debug(f"Session {session_id}: Calling handle_simple_chain_stream with agent_executor type: {type(agent_executor)}, input_data: {str(input_data)[:200]}")
            final_response_content = await handle_simple_chain_stream(
                session_id, agent_executor, input_data, callbacks, output_stream_fn, config_for_stream
            )
        else:  # Regular agent executor
            logger.info(f"Session {session_id}: Using agent_executor.astream_events() for "
                       f"agent type: {type(raw_agent_executor).__name__}")
            final_response_content = await handle_agent_stream_events(
                session_id, agent_executor, input_data, callbacks, output_stream_fn, config_for_stream
            )

        # Send final event if we have content
        if final_response_content is not None:
            logger.info(f"Session {session_id}: Sending final CHAIN_END event with content: "
                       f"{str(final_response_content)[:70]}...")
            try:
                await output_stream_fn(EventType.CHAIN_END, {"content": str(final_response_content)})
                stream_terminated_successfully = True # Mark as terminated
            except Exception as e:
                logger.error(f"Session {session_id}: Error sending final CHAIN_END event: {e}", 
                            exc_info=True)
        else:
            logger.warning(f"Session {session_id}: No final_response_content captured. "
                          f"Sending generic END event.")
            await output_stream_fn(EventType.END, {"content": "Stream finished without specific final content"})
            stream_terminated_successfully = True # Mark as terminated

    except Exception as e:
        # Log the exception with full traceback
        exc_type, exc_value, exc_traceback = sys.exc_info()
        traceback_details = traceback.format_exception(exc_type, exc_value, exc_traceback)
        logger.error(f"stream_agent_response for session {session_id}: "
                    f"CRITICAL ERROR: {type(e).__name__} - {e}\n"
                    f"{''.join(traceback_details)}", exc_info=False)
        
        try:
            await output_stream_fn(EventType.ERROR, {"error": f"Critical agent error: {str(e)}"})
            await output_stream_fn(EventType.END, {"content": "Stream terminated due to critical error"})
            stream_terminated_successfully = True # Mark as terminated
        except Exception as ex:
            logger.error(f"stream_agent_response for session {session_id}: "
                        f"FAILED TO SEND error event: {ex}", exc_info=True)
    
    finally:
        if not stream_terminated_successfully:
            try:
                logger.warning(f"Session {session_id}: stream_agent_response.finally - stream not marked as successfully terminated. Sending fallback END event.")
                await output_stream_fn(EventType.END, {"content": "Stream finalized by fallback handler."})
            except Exception as final_ex:
                logger.error(f"Session {session_id}: stream_agent_response.finally - FAILED TO SEND fallback END event: {final_ex}", exc_info=True)
        
        logger.info(f"stream_agent_response for session {session_id}: COMPLETED (stream_terminated_successfully: {stream_terminated_successfully})") 