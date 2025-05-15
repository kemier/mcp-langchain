import time
import json
import logging
import asyncio
from fastapi import HTTPException, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState
from mcp_web_app.utils.events import websocket_output_stream_fn_factory, error_generator

logger = logging.getLogger(__name__)

async def websocket_chat_stream_handler(websocket: WebSocket, request_data: dict, agent_service, stream_timeout=180):
    """Handle WebSocket chat stream requests from clients.
    
    This function manages the streaming of chat responses through WebSockets.
    支持双向通信：接收客户端消息并发送响应。
    """
    overall_start_time = time.time()
    session_id = request_data.get('session_id', f'ws-{time.time()}')
    # Attach session_id to the websocket object for easy access in other functions
    setattr(websocket, 'session_id', session_id)
    event_queue = asyncio.Queue()
    
    # Parse request data - print detailed debug logs
    prompt = request_data.get('prompt', '')
    tools_config = request_data.get('tools_config', {})
    llm_config_id = request_data.get('llm_config_id')
    agent_mode = request_data.get('agent_mode', 'chat')
    agent_data_source = request_data.get('agent_data_source')
    
    logger.info(f"WS session {session_id}: Starting WebSocket chat stream handler")
    logger.debug(f"WS session {session_id}: Request data: prompt length={len(prompt)}, "
                f"tools_config keys={list(tools_config.keys()) if isinstance(tools_config, dict) else 'not a dict'}, "
                f"llm_config_id={llm_config_id}, mode={agent_mode}")

    # 发送连接确认消息
    try:
        await websocket.send_json({
            "type": "connection_established",
            "data": {
                "session_id": session_id,
                "message": "WebSocket连接已建立，开始处理请求"
            }
        })
        logger.info(f"WS session {session_id}: 发送连接确认消息")
    except Exception as e:
        logger.error(f"WS session {session_id}: 发送确认消息失败: {e}", exc_info=True)

    # Get the event pusher function from the factory
    # This function will be called by the CustomAsyncIteratorCallbackHandler in the agent service
    event_pusher_fn = websocket_output_stream_fn_factory(websocket, event_queue)

    agent_task = None
    try:
        logger.info(f"WS session {session_id}: Creating background task for agent_service.astream_ask_agent_events.")
        # Debug log for the request
        logger.debug(f"Request details: session_id={session_id}, llm_config_id={request_data.get('llm_config_id')}")

        agent_task = asyncio.create_task(
            agent_service.astream_ask_agent_events(
                session_id=session_id,
                question=request_data.get('prompt', ''),
                tools_config=request_data.get('tools_config', {}),
                llm_config_id=request_data.get('llm_config_id'),
                output_stream_fn=event_pusher_fn, # Pass the queue pusher
                agent_mode=request_data.get('agent_mode', 'chat'),
                agent_data_source=request_data.get('agent_data_source')
            )
        )

        token_received = False
        accumulated_tokens = []
        event_count = 0
        # Timeout for individual queue.get() operations
        queue_get_timeout = stream_timeout # Or a shorter duration like 5-10 seconds

        while True:
            try:
                # Wait for an event from the agent service
                # Use a timeout to prevent indefinite blocking if the agent stalls
                event_type, data = await asyncio.wait_for(event_queue.get(), timeout=queue_get_timeout)
                event_count += 1
                logger.debug(f"WS session {session_id}: Event {event_count} received from queue: Type: {event_type}, Data: {str(data)[:100]}...")

                # Determine the string value of the event type for JSON serialization
                # Prefer .name for the string representation of the enum member's key
                event_type_str = event_type.name if hasattr(event_type, 'name') else str(event_type)

                # WebSocket JSON formatting
                if event_type == "token":
                    token_received = True
                    token_data = data
                    if not isinstance(data, str):
                        token_data = str(data)
                    
                    accumulated_tokens.append(token_data)
                    # Send token as JSON object
                    await websocket.send_json({
                        "type": event_type_str,
                        "data": token_data
                    })
                
                elif event_type == "on_chain_end" or event_type == "message":
                    message_content = ""
                    if isinstance(data, dict) and "content" in data:
                        message_content = data["content"]
                    elif isinstance(data, str):
                        message_content = data
                    else:
                        try:
                            if isinstance(data, dict):
                                message_content = data.get("content") or data.get("output") or str(data)
                            else:
                                message_content = str(data)
                        except Exception as e_format:
                            logger.error(f"WS session {session_id}: Error formatting 'message' data: {e_format}", exc_info=True)
                            message_content = f"Error processing message data: {str(e_format)}"
                    
                    logger.info(f"WS session {session_id}: Received event '{event_type}'. Content: {message_content[:100]}...")
                    if message_content:
                        await websocket.send_json({
                            "type": event_type_str,
                            "data": message_content
                        })

                elif event_type == "error":
                    error_msg = str(data.get("error", data)) if isinstance(data, dict) else str(data)
                    logger.error(f"WS session {session_id}: Yielding error event from queue: {error_msg}")
                    await websocket.send_json({
                        "type": "error_event",
                        "data": {
                            "error": error_msg,
                            "recoverable": True
                        }
                    })

                elif event_type == "end":
                    logger.info(f"WS session {session_id}: Received 'end' event from queue. Terminating stream.")
                    await websocket.send_json({
                        "type": "end",
                        "data": "complete"
                    })
                    break # Exit the while loop

                else: # Generic event pass-through
                    logger.debug(f"WS session {session_id}: Sending generic event type '{event_type_str}' from queue.")
                    # Send all other events as JSON objects
                    if isinstance(data, str):
                        await websocket.send_json({
                            "type": event_type_str,
                            "data": data
                        })
                    else:
                        # Send complex data with proper serialization
                        await websocket.send_json({
                            "type": event_type_str,
                            "data": data
                        })

                # Check overall stream timeout
                if time.time() - overall_start_time > stream_timeout:
                    logger.warning(f"WS session {session_id}: Overall stream timeout ({stream_timeout}s) exceeded.")
                    await websocket.send_json({
                        "type": "error_event",
                        "data": {
                            "error": "Stream timeout exceeded",
                            "recoverable": False
                        }
                    })
                    break
                
                event_queue.task_done()

            except asyncio.TimeoutError:
                logger.debug(f"WS session {session_id}: Timeout waiting for event from queue.")
                # Check if the agent task is still running
                if agent_task and agent_task.done():
                    logger.info(f"WS session {session_id}: Agent task finished while waiting for queue. Checking for exceptions.")
                    try:
                        agent_task.result() # Raise exception if agent task failed
                    except Exception as e_agent:
                        logger.error(f"WS session {session_id}: Agent task failed with: {e_agent}", exc_info=True)
                        await websocket.send_json({
                            "type": "error_event",
                            "data": {
                                "error": f"Agent task error: {str(e_agent)}",
                                "recoverable": False
                            }
                        })
                    break
                
                # Check overall stream timeout
                if time.time() - overall_start_time > stream_timeout:
                    logger.warning(f"WS session {session_id}: Overall stream timeout ({stream_timeout}s) exceeded during queue wait.")
                    await websocket.send_json({
                        "type": "error_event",
                        "data": {
                            "error": "Stream timeout exceeded",
                            "recoverable": False
                        }
                    })
                    break
                continue
                
            except WebSocketDisconnect:
                logger.info(f"WS session {session_id}: WebSocket disconnected by client.")
                break
            
            except Exception as e_send:
                logger.error(f"WS session {session_id}: Error sending WebSocket message: {e_send}", exc_info=True)
                # Check if the error is due to the connection being closed
                if isinstance(e_send, RuntimeError) and "Cannot call \"send\" once a close message has been sent" in str(e_send):
                    logger.warning(f"WS session {session_id}: Cannot send message, connection already closed.")
                elif websocket.client_state != WebSocketState.CONNECTED:
                    logger.warning(f"WS session {session_id}: WebSocket state is {websocket.client_state}, cannot send.")
                else:
                    # For other send errors, try to inform the client if possible
                    try:
                        if websocket.client_state == WebSocketState.CONNECTED:
                            await websocket.send_json({
                                "type": "error_event",
                                "data": {
                                    "error": f"Internal error sending message: {str(e_send)}",
                                    "recoverable": True # May or may not be recoverable
                                }
                            })
                    except Exception as e_inner:
                         logger.error(f"WS session {session_id}: Failed to send error message about send failure: {e_inner}")
                break # Break the loop on send error

        logger.info(f"WS session {session_id}: Exited event processing loop. Token_received: {token_received}, Events processed: {event_count}")
        
        # Send final accumulated message if tokens were received
        final_message = "".join(accumulated_tokens)
        if final_message:
            logger.info(f"WS session {session_id}: Sending final accumulated message: {final_message[:100]}...")
            try:
                # Check state before sending final message
                if websocket.client_state == WebSocketState.CONNECTED:
                    await websocket.send_json({
                        "type": "final",
                        "data": final_message
                    })
            except Exception as e_final:
                 logger.error(f"WS session {session_id}: Failed to send final message: {e_final}. State: {websocket.client_state}")

    except WebSocketDisconnect:
        logger.info(f"WS session {session_id}: WebSocket disconnected during processing.")
        if agent_task and not agent_task.done():
            agent_task.cancel()
    except asyncio.CancelledError:
        logger.info(f"WS session {session_id}: websocket_chat_stream_handler task was cancelled.")
        if agent_task and not agent_task.done():
            agent_task.cancel()
        raise
    except Exception as e_outer:
        logger.error(f"WS session {session_id}: CRITICAL ERROR in WebSocket stream: {type(e_outer).__name__} - {e_outer}", exc_info=True)
        try:
             # Check state before sending critical error message
             if websocket.client_state == WebSocketState.CONNECTED:
                await websocket.send_json({
                    "type": "error_event",
                    "data": {
                        "error": f"Critical stream error: {str(e_outer)}",
                        "recoverable": False
                    }
                })
        except Exception as e_crit:
            logger.error(f"WS session {session_id}: Failed to send error to client after critical error: {e_crit}. State: {websocket.client_state}")
    finally:
        elapsed = time.time() - overall_start_time
        logger.info(f"WS session {session_id}: websocket_chat_stream_handler NORMALLY EXITING 'finally' block. Total Elapsed: {elapsed:.2f}s.")
        # Ensure the agent task is cancelled if it's still running
        if agent_task and not agent_task.done():
            logger.info(f"WS session {session_id}: Cancelling agent task in finally block.")
            agent_task.cancel()
            try:
                # Wait briefly for cancellation to propagate
                await asyncio.wait_for(agent_task, timeout=5.0) 
            except asyncio.CancelledError:
                logger.info(f"WS session {session_id}: Agent task successfully cancelled.")
            except asyncio.TimeoutError:
                 logger.warning(f"WS session {session_id}: Timeout waiting for agent task cancellation.")
            except Exception as e_cancel:
                 logger.error(f"WS session {session_id}: Error during agent task cleanup: {e_cancel}", exc_info=True)
                 # Don't try to send error if outer try failed, connection likely gone

        logger.info(f"WS session {session_id}: Cleaned up resources.")

async def chat_bot_invoke(agent_service, request):
    try:
        session_id = request.session_id if hasattr(request, 'session_id') else None
        reply = await agent_service.invoke_agent(
            user_message=request.message,
            active_tools_config=request.active_tools_config,
            session_id=session_id or None
        )
        return reply
    except Exception as e:
        logger.error(f"Error in chat_bot_invoke: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) 