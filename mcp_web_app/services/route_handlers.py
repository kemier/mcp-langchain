#!/usr/bin/env python3
"""
Route handlers for the MCP web application.
"""
import logging
from typing import Dict, Any, Optional, List

from fastapi import HTTPException
from fastapi.responses import HTMLResponse

from mcp_web_app.services.session_utils import SessionManager
from mcp_web_app.models.models import (
    ChatRequest, ChatResponse, SessionCreateResponse, 
    SessionListResponse, SessionDeleteResponse, StatusResponse
)
from mcp_web_app.utils.templates import get_home_template, get_chat_session_template

# Setup logging
logger = logging.getLogger(__name__)

async def handle_home() -> HTMLResponse:
    """
    Handle request for the home page.
    
    Returns:
        HTML response for the home page
    """
    html_content = get_home_template()
    return HTMLResponse(content=html_content)

async def handle_status(agent_service: Any) -> StatusResponse:
    """
    Handle request for API status.
    
    Args:
        agent_service: The agent service
        
    Returns:
        Status response
        
    Raises:
        HTTPException: If agent service is not initialized
    """
    if agent_service and agent_service.agent_executor:
        tools = [tool.name for tool in agent_service.tools] if agent_service.tools else []
        return StatusResponse(
            status="initialized",
            model=agent_service.model_name,
            tools_count=len(tools),
            tools=tools
        )
    return StatusResponse(
        status="not_initialized",
        error="Agent service not initialized or no agent executor available"
    )

async def handle_chat(
    request: ChatRequest, 
    session_manager: SessionManager, 
    agent_service: Any
) -> ChatResponse:
    """
    Handle a chat request.
    
    Args:
        request: The chat request
        session_manager: The session manager
        agent_service: The agent service
        
    Returns:
        Chat response
        
    Raises:
        HTTPException: If agent service is not initialized or session not found
    """
    if not agent_service:
        raise HTTPException(status_code=503, detail="Agent service not initialized")
    
    # Create a new session if none is provided
    session_id = request.session_id
    if not session_id:
        session_id = session_manager.create_session(agent_service)
    else:
        # Verify session exists
        session = session_manager.get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    
    try:
        # Ask the agent
        response = await agent_service.aask_agent(request.query)
        
        # Add to session history
        session = session_manager.get_session(session_id)
        session.add_to_history(request.query, response)
        
        return ChatResponse(answer=response, session_id=session_id)
    except Exception as e:
        logger.exception("Error in chat endpoint")
        raise HTTPException(status_code=500, detail=str(e))

async def handle_create_session(
    session_manager: SessionManager, 
    agent_service: Any
) -> SessionCreateResponse:
    """
    Handle request to create a new session.
    
    Args:
        session_manager: The session manager
        agent_service: The agent service
        
    Returns:
        Session creation response
        
    Raises:
        HTTPException: If agent service is not initialized
    """
    if not agent_service:
        raise HTTPException(status_code=503, detail="Agent service not initialized")
    
    session_id = session_manager.create_session(agent_service)
    return SessionCreateResponse(session_id=session_id)

async def handle_list_sessions(
    session_manager: SessionManager
) -> SessionListResponse:
    """
    Handle request to list all sessions.
    
    Args:
        session_manager: The session manager
        
    Returns:
        Session list response
    """
    sessions = session_manager.list_sessions()
    return SessionListResponse(sessions=sessions)

async def handle_delete_session(
    session_id: str, 
    session_manager: SessionManager
) -> SessionDeleteResponse:
    """
    Handle request to delete a session.
    
    Args:
        session_id: The session ID to delete
        session_manager: The session manager
        
    Returns:
        Session deletion response
        
    Raises:
        HTTPException: If session not found
    """
    if session_manager.delete_session(session_id):
        return SessionDeleteResponse(status="deleted", session_id=session_id)
    
    raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

async def handle_chat_session(
    session_id: str, 
    session_manager: SessionManager
) -> HTMLResponse:
    """
    Handle request for a chat session page.
    
    Args:
        session_id: The session ID
        session_manager: The session manager
        
    Returns:
        HTML response for the chat session page
        
    Raises:
        HTTPException: If session not found
    """
    # Verify session exists
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    
    html_content = get_chat_session_template(session_id, session.history)
    return HTMLResponse(content=html_content) 