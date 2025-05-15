#!/usr/bin/env python3
"""
Request dispatcher for asynchronous processing of agent requests.
"""
import logging
import threading
import asyncio
import traceback
from typing import Dict, Any, Optional, Union, Tuple
from queue import Queue
from concurrent.futures import Future

from langchain_core.messages import HumanMessage, AIMessage

# Initialize logger
logger = logging.getLogger(__name__)

class RequestDispatcher:
    """
    Dispatcher for handling agent requests asynchronously in a separate thread.
    """
    
    def __init__(self, agent_service):
        """
        Initialize the request dispatcher.
        
        Args:
            agent_service: The agent service that owns this dispatcher
        """
        self.agent_service = agent_service
        self.request_queue = Queue()
        self.loop = None
        self.dispatcher_thread = None
        self.is_running = False
    
    def start(self):
        """Start the request dispatcher thread."""
        if self.dispatcher_thread and self.dispatcher_thread.is_alive():
            logger.info("Dispatcher thread already running.")
            return

        self.is_running = True
        self.loop = asyncio.new_event_loop()
        self.dispatcher_thread = threading.Thread(
            target=self._process_queue, 
            daemon=True
        )
        self.dispatcher_thread.start()
        logger.info("Request dispatcher thread started.")
    
    def stop(self):
        """Stop the request dispatcher thread."""
        if not self.dispatcher_thread or not self.dispatcher_thread.is_alive():
            logger.info("Dispatcher thread not running.")
            return
            
        logger.info("Stopping dispatcher thread...")
        # Send sentinel to signal thread to stop
        self.request_queue.put((None, None, None, None, None, None, None))
        self.dispatcher_thread.join(timeout=5)
        
        if self.dispatcher_thread.is_alive():
            logger.warning("Dispatcher thread did not stop in time.")
        else:
            logger.info("Dispatcher thread stopped.")
            
        self.is_running = False
        
        # Stop the event loop if it's running
        if self.loop and self.loop.is_running():
            self.loop.call_soon_threadsafe(self.loop.stop)
    
    def submit_request(
        self, 
        session_id: str, 
        question: str, 
        tools_config: Dict[str, Any], 
        llm_config_id: Optional[str] = None,
        agent_mode: Optional[str] = None,
        agent_data_source: Optional[Union[str, Dict]] = None
    ) -> Future:
        """
        Submit a request to be processed asynchronously.
        
        Args:
            session_id: The session ID
            question: The user's question
            tools_config: The tools configuration
            llm_config_id: The LLM configuration ID
            agent_mode: The agent mode
            agent_data_source: The agent data source
            
        Returns:
            A future that will be resolved with the response
            
        Raises:
            RuntimeError: If the dispatcher is not running
        """
        if not self.is_running or not self.dispatcher_thread or not self.dispatcher_thread.is_alive():
            raise RuntimeError("Dispatcher thread is not running. Cannot process request.")
            
        future = Future()
        self.request_queue.put((
            session_id, 
            question, 
            tools_config, 
            llm_config_id, 
            agent_mode, 
            agent_data_source, 
            future
        ))
        return future
    
    def _process_queue(self):
        """
        Process requests from the queue in the dispatcher thread.
        This is the main function of the dispatcher thread.
        """
        if not self.loop:
            logger.error("Asyncio event loop not set for dispatcher thread.")
            return
            
        asyncio.set_event_loop(self.loop)

        while True:
            try:
                # Get the next request from the queue
                (session_id, 
                 question, 
                 tools_config, 
                 llm_config_id, 
                 agent_mode, 
                 agent_data_source, 
                 future) = self.request_queue.get()
                
                # Check for stop signal
                if question is None and session_id is None:
                    logger.info("Dispatcher thread received stop signal.")
                    break
                
                logger.info(f"Dispatcher: Processing request for session '{session_id}', "
                           f"question: '{question[:30]}...', mode: {agent_mode}")
                
                try:
                    # Process the request
                    self._process_request(
                        session_id,
                        question,
                        tools_config,
                        llm_config_id,
                        agent_mode,
                        agent_data_source,
                        future
                    )
                except Exception as e:
                    logger.error(f"Error processing request in dispatcher: {e}", exc_info=True)
                    if not future.done():
                        future.set_exception(e)
                finally:
                    self.request_queue.task_done()
                    
            except Exception as e:
                # Catch errors from queue.get() or outer loop
                logger.error(f"Outer loop error in dispatcher thread: {e}", exc_info=True)
                # If future was defined and item retrieved, set exception
                if 'future' in locals() and isinstance(future, Future) and not future.done():
                    future.set_exception(e)
                # Ensure task_done if item was retrieved
                if 'session_id' in locals():
                    self.request_queue.task_done()
    
    def _process_request(
        self,
        session_id: str,
        question: str,
        tools_config: Dict[str, Any],
        llm_config_id: Optional[str],
        agent_mode: Optional[str],
        agent_data_source: Optional[Union[str, Dict]],
        future: Future
    ):
        """
        Process a single request.
        
        Args:
            session_id: The session ID
            question: The user's question
            tools_config: The tools configuration
            llm_config_id: The LLM configuration ID
            agent_mode: The agent mode
            agent_data_source: The agent data source
            future: The future to resolve with the response
        """
        try:
            # Get or create the session components
            session_components_coro = self.agent_service._get_or_create_session_components(
                session_id, tools_config, llm_config_id, agent_mode, agent_data_source
            )
            session_components = asyncio.run_coroutine_threadsafe(
                session_components_coro, 
                self.loop
            ).result()
            
            # Get the components we need
            agent_executor = session_components["agent_executor"]
            chat_messages_for_log = session_components["chat_messages_for_log"]

            if not agent_executor:
                raise RuntimeError("Agent executor not available.")

            # Prepare inputs and invoke the agent
            inputs = {"input": question}
            response_coro = agent_executor.ainvoke(inputs)
            response_dict = asyncio.run_coroutine_threadsafe(
                response_coro, 
                self.loop
            ).result()
            
            # Extract the answer from the response
            answer = self._extract_answer_from_response(response_dict)

            # Update the chat history
            chat_messages_for_log.append(HumanMessage(content=question))
            chat_messages_for_log.append(AIMessage(content=answer))
            
            # Set the result
            future.set_result(answer)
            logger.info(f"Dispatcher: Successfully processed sync request for session '{session_id}'.")

        except Exception as e:
            logger.error(f"Error processing request: {str(e)}")
            logger.error(traceback.format_exc())
            if not future.done():
                future.set_exception(e)
    
    def _extract_answer_from_response(self, response_dict: Any) -> str:
        """
        Extract the answer string from the agent's response.
        
        Args:
            response_dict: The response from the agent
            
        Returns:
            The extracted answer string
        """
        if isinstance(response_dict, dict) and "output" in response_dict:
            return response_dict["output"]
        elif isinstance(response_dict, str):
            return response_dict
        else:
            # Fallback for AIMessage or other types
            return str(getattr(response_dict, 'content', response_dict)) 