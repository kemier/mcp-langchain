#!/usr/bin/env python3
"""
WebSocket handlers for the MCP web application.
"""
import json
import logging
from typing import Dict, Any, Optional

from fastapi import WebSocket, WebSocketDisconnect

from mcp_web_app.services.session_utils import SessionManager, ChatSession

# Setup logging
logger = logging.getLogger(__name__)

async def handle_websocket_chat(
    websocket: WebSocket,
    session_id: Optional[str],
    session_manager: SessionManager,
    agent_service: Any
) -> None:
    """
    Handle a WebSocket connection for chat with session support.
    
    Args:
        websocket: The WebSocket connection
        session_id: The session ID to use, or None/new to create a new session
        session_manager: The session manager
        agent_service: The agent service
    """
    if not agent_service:
        await websocket.close(code=1013, reason="Agent service not initialized")
        return
    
    await websocket.accept()
    
    # Create or validate session
    if not session_id or session_id == "new":
        # Create a new session
        session_id = session_manager.create_session(agent_service)
        await websocket.send_json({"event": "session_created", "session_id": session_id})
    else:
        # Verify session exists
        session = session_manager.get_session(session_id)
        if not session:
            await websocket.send_json({"error": f"Session {session_id} not found"})
            await websocket.close()
            return
    
    try:
        await handle_websocket_messages(websocket, session_id, session_manager, agent_service)
    except WebSocketDisconnect:
        logger.info(f"WebSocket for session {session_id} disconnected")
    except Exception as e:
        logger.exception(f"Error in WebSocket handler for session {session_id}")
        try:
            await websocket.send_json({"error": str(e)})
        except:
            pass
            
async def handle_websocket_messages(
    websocket: WebSocket,
    session_id: str,
    session_manager: SessionManager,
    agent_service: Any
) -> None:
    """
    Handle WebSocket messages for a chat session.
    
    Args:
        websocket: The WebSocket connection
        session_id: The session ID
        session_manager: The session manager
        agent_service: The agent service
    """
    while True:
        # Receive message from client
        data = await websocket.receive_text()
        request_data = json.loads(data)
        
        # Extract query
        query = request_data.get("query")
        if not query:
            await websocket.send_json({"error": "No query provided"})
            continue
        
        # Get the session
        session = session_manager.get_session(session_id)
        session.update_activity()
        
        # Process the query and stream events
        await stream_agent_response(websocket, session, query, agent_service)
        
async def stream_agent_response(
    websocket: WebSocket,
    session: ChatSession,
    query: str,
    agent_service: Any
) -> None:
    """
    Stream an agent's response to a WebSocket.
    
    Args:
        websocket: The WebSocket connection
        session: The chat session
        query: The user query
        agent_service: The agent service
    """
    # Stream agent response events
    full_response = ""
    async for event in agent_service.astream_ask_agent_events(query):
        # Track the full response if it's a text event
        if event.get("event") == "text" and "text" in event:
            full_response += event["text"]
        
        # Send the event to the client
        await websocket.send_json(event)
        
    # Send a completion event
    await websocket.send_json({"event": "completion"})
    
    # Add to session history
    session.add_to_history(query, full_response) 