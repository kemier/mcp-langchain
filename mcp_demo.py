#!/usr/bin/env python3
"""
Demo script showing how to use the MCP client with the agents.
This demonstrates the basic functionality implemented in the web app.
"""

import logging
import os
import sys
import asyncio
from dotenv import load_dotenv

# Load environment variables
dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path=dotenv_path)
    print(f"Loaded .env file from: {dotenv_path}")

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import from the web app's services
from mcp_web_app.services.langchain_agent_service import LangchainAgentService
from mcp_web_app.config_manager import ConfigManager

# Sample MCP configuration
MCP_CONFIG = {
    "math": {
        "command": "python",
        "args": ["/Users/zaedinzeng/projects/mcp-client/math-server.py"],
        "transport": "stdio",
    },
    "weather":{
        "command": "uv",
        "args": ["--directory","/Users/zaedinzeng/projects/china-weather-mcp-server","run","weather.py"],
        "transport": "stdio",
    }
}

def main():
    # Initialize ConfigManager (required by LangchainAgentService)
    config_path = os.path.join(os.path.dirname(__file__), 'mcp_web_app', 'servers.json')
    config_manager = ConfigManager(config_path)
    
    # Initialize the agent service
    agent_service = LangchainAgentService(config_manager=config_manager)
    
    try:
        # Sample session ID
        session_id = "demo-session"
        
        # Sample questions
        questions = [
            "what's (3 + 5) x 12?",
            "what's the result divided by 6?",
            "what is the weather in chengdu?"
        ]
        
        # Ask each question
        for question in questions:
            print("\n------------------------------")
            print(f"Question: {question}")
            answer = agent_service.ask_agent(session_id, question, MCP_CONFIG)
            print(f"Answer: {answer}")
        
        # Clear the session
        print("\nClearing session...")
        agent_service.clear_session(session_id)
        
        # One more question with a new session
        session_id = "new-session"
        question = "what's (3 + 5) x 12?"
        print("\n------------------------------")
        print(f"New Session Question: {question}")
        answer = agent_service.ask_agent(session_id, question, MCP_CONFIG)
        print(f"Answer: {answer}")
        
    finally:
        # Clean up
        agent_service.stop_dispatcher()
        print("\nDispatcher stopped. Exiting.")
        

if __name__ == "__main__":
    main() 