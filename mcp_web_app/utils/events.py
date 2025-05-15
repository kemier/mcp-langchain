import json
import time
import logging
import asyncio
from typing import Any, Callable, Dict, Optional, Union
from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

def websocket_output_stream_fn_factory(websocket: WebSocket, event_queue: asyncio.Queue) -> Callable[[str, Any], None]:
    """Factory to create a WebSocket event pusher function.
    
    This function creates a synchronous callback that takes an event type and data,
    and puts it onto the provided asyncio.Queue for later processing by the WebSocket sender.
    """
    async def websocket_event_pusher(event_type: str, data: Any) -> None:
        session_id = getattr(websocket, 'session_id', 'unknown')
        # Add debug logging
        logger.debug(f"WS session {session_id}: websocket_event_pusher called with event_type: {event_type}, data: {str(data)[:100]}...")
        
        try:
            # 在添加到队列前预处理数据
            # 根据不同的事件类型进行特殊处理
            processed_data = data
            
            # 如果是JSON格式的字符串，尝试解析
            if isinstance(data, str) and data.strip().startswith('{') and data.strip().endswith('}'):
                try:
                    processed_data = json.loads(data)
                    logger.debug(f"WS session {session_id}: Parsed JSON string to object")
                except json.JSONDecodeError:
                    # 如果解析失败，保持原样
                    pass
            
            # 确保错误事件有正确的格式
            if event_type == "error" and isinstance(processed_data, str):
                processed_data = {
                    "error": processed_data,
                    "recoverable": True
                }
            
            # 添加到队列
            event_queue.put_nowait((event_type, processed_data))
            logger.debug(f"WS session {session_id}: Event ({event_type}) successfully added to queue.")
        except Exception as e:
            logger.error(f"WS session {session_id}: Error adding event to queue: {e}", exc_info=True)
            
            # 尝试添加错误事件到队列
            try:
                error_event = {
                    "error": f"Failed to process {event_type} event: {str(e)}",
                    "event_type": event_type,
                    "recoverable": True
                }
                event_queue.put_nowait(("error", error_event))
            except Exception as e2:
                logger.critical(f"WS session {session_id}: Failed to add error event to queue: {e2}")
        
    return websocket_event_pusher

async def error_generator(error_title: str, error_detail: str = None):
    """Generate error messages for WebSocket responses."""
    # Create error message - combine title and detail if both provided
    error_message = error_title
    if error_detail:
        error_message = f"{error_title}: {error_detail}"
    
    # Send error as JSON format compatible with WebSocket
    yield {"type": "error_event", "data": {"error": error_message, "recoverable": False}}
    yield {"type": "end", "data": "Stream terminated with error"} 