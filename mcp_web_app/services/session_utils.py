#!/usr/bin/env python3
"""
Session utilities for managing agent sessions and chat history.
"""
import asyncio
import logging
import uuid
from typing import Dict, List, Any, Optional, Union

# Setup logging
logger = logging.getLogger(__name__)

class ChatSession:
    """
    Class to manage a chat session with history and agent state
    """
    
    def __init__(self, session_id: str, agent_service: Any):
        """
        Initialize a chat session
        
        Args:
            session_id: Unique identifier for the session
            agent_service: Reference to the agent service for this session
        """
        self.session_id = session_id
        self.agent_service = agent_service
        self.created_at = asyncio.get_event_loop().time()
        self.last_activity = self.created_at
        self.history = []
    
    def update_activity(self) -> None:
        """Update the last activity timestamp"""
        self.last_activity = asyncio.get_event_loop().time()
    
    def add_to_history(self, query: str, response: str) -> None:
        """
        Add a query-response pair to the session history
        
        Args:
            query: The user query
            response: The agent's response
        """
        self.history.append({"query": query, "response": response})
        self.update_activity()
        
    def get_history(self) -> List[Dict[str, str]]:
        """
        Get the session history
        
        Returns:
            List of query-response pairs
        """
        return self.history
    
    def get_session_info(self) -> Dict[str, Any]:
        """
        Get information about the session
        
        Returns:
            Dictionary with session information
        """
        return {
            "session_id": self.session_id,
            "created_at": self.created_at,
            "last_activity": self.last_activity,
            "message_count": len(self.history)
        }

class SessionManager:
    """
    Manager for chat sessions
    """
    
    def __init__(self):
        """Initialize the session manager"""
        self.sessions: Dict[str, ChatSession] = {}
    
    def create_session(self, agent_service: Any) -> str:
        """
        Create a new chat session
        
        Args:
            agent_service: Reference to the agent service for this session
            
        Returns:
            The session ID
        """
        session_id = str(uuid.uuid4())
        self.sessions[session_id] = ChatSession(session_id, agent_service)
        logger.info(f"Created new session: {session_id}")
        return session_id
    
    def get_session(self, session_id: str) -> Optional[ChatSession]:
        """
        Get a session by ID
        
        Args:
            session_id: The session ID to retrieve
            
        Returns:
            The chat session, or None if not found
        """
        return self.sessions.get(session_id)
    
    def delete_session(self, session_id: str) -> bool:
        """
        Delete a session
        
        Args:
            session_id: The session ID to delete
            
        Returns:
            True if the session was deleted, False otherwise
        """
        if session_id in self.sessions:
            del self.sessions[session_id]
            logger.info(f"Deleted session: {session_id}")
            return True
        return False
    
    def list_sessions(self) -> List[Dict[str, Any]]:
        """
        List all active sessions
        
        Returns:
            List of session information dictionaries
        """
        return [
            {
                "session_id": session.session_id,
                "created_at": session.created_at,
                "last_activity": session.last_activity,
                "message_count": len(session.history)
            }
            for session in self.sessions.values()
        ]
    
    def get_or_create_session(self, session_id: Optional[str], agent_service: Any) -> tuple[str, ChatSession]:
        """
        Get a session by ID, or create a new one if it doesn't exist
        
        Args:
            session_id: The session ID to retrieve, or None to create a new one
            agent_service: The agent service to use for new sessions
            
        Returns:
            Tuple of (session_id, session)
        """
        if session_id:
            session = self.get_session(session_id)
            if session:
                logger.debug(f"Retrieved existing session: {session_id}")
                return session_id, session
                
        # Create a new session if not found or not provided
        new_session_id = self.create_session(agent_service)
        return new_session_id, self.sessions[new_session_id] 