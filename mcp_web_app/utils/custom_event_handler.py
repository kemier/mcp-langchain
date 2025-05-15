import logging # ADDED
from typing import Any, Dict, List, Optional, Union # Added import for type hints
import asyncio  # Added for Queue
from langchain_core.callbacks import AsyncCallbackHandler # ADDED: Import base handler
from langchain_core.outputs import ChatGenerationChunk, GenerationChunk, LLMResult # REMOVED ChatMessage
from langchain_core.messages import ChatMessage, AIMessage, HumanMessage, SystemMessage, FunctionMessage, ToolMessage, BaseMessage # ADDED ChatMessage here, and BaseMessage
from langchain_core.agents import AgentAction, AgentFinish # ADDED: For type hints
from langchain_core.prompt_values import ChatPromptValue
# from langchain_core.messages import BaseMessage # For type checking # MOVED BaseMessage to combined import
import re

# Placeholder for custom event handler

logger = logging.getLogger(__name__) # ADDED

class EventType:
    TOKEN = "token"
    MESSAGE = "message" # For complete messages or significant updates
    ERROR = "error"
    END = "end"         # General stream end
    CHAIN_START = "on_chain_start"
    CHAIN_END = "on_chain_end"
    TOOL_START = "on_tool_start"
    TOOL_END = "on_tool_end"
    AGENT_ACTION = "on_agent_action"
    AGENT_FINISH = "on_agent_finish"
    CHAT_MODEL_STREAM = "on_chat_model_stream" # Langchain standard for raw token chunks 
    START = "start"     # Added for model start events

class CustomAsyncIteratorCallbackHandler(AsyncCallbackHandler):
    # run_inline, ignore_chain, ignore_llm, ignore_agent, ignore_tool, raise_error
    # are inherited from BaseCallbackHandler via AsyncCallbackHandler with default values.
    # No need to redefine them unless overriding the default.

    def __init__(self, output_stream_fn: callable, **kwargs: Any):
        super().__init__(**kwargs)
        self.output_stream_fn = output_stream_fn
        # Initialize queue for token handling
        self.queue = asyncio.Queue()
        # Initialize token counter
        self.token_count = 0
        # Buffer to accumulate tokens
        self.token_buffer = ""
        # Flag to track if we've successfully sent tokens to the UI
        self.tokens_sent = False
        # event_type_class is no longer used to set instance attributes here

    def _serialize_data(self, data: Any) -> Any:
        if isinstance(data, dict):
            return {key: self._serialize_data(value) for key, value in data.items()}
        elif isinstance(data, list):
            return [self._serialize_data(item) for item in data]
        elif isinstance(data, ChatPromptValue):
            # Convert ChatPromptValue to a list of message dicts
            return [self._serialize_data(msg) for msg in data.to_messages()]
        elif isinstance(data, BaseMessage):
            # Convert BaseMessage objects (AIMessage, HumanMessage, etc.) to dict
            return data.dict() 
        elif hasattr(data, 'dict') and callable(getattr(data, 'dict')) and not isinstance(data, type):
            # For other Pydantic models or objects with a .dict() method
            try:
                return data.dict()
            except Exception:
                return str(data) # Fallback to string representation
        elif isinstance(data, (str, int, float, bool, type(None))):
            return data
        else:
            # Fallback for other types
            return str(data)

    async def on_llm_new_token(self, token: str, *, chunk: Optional[Union[GenerationChunk, ChatGenerationChunk]] = None, **kwargs: Any) -> None:
        logger.debug(f"CustomAsyncIteratorCallbackHandler.on_llm_new_token: Received token '{token}'")
        try:
            # Send the token directly to the output stream
            # Important: We now directly call output_stream_fn, not expecting a return value
            # The output_stream_fn will directly yield the event to the client
            self.output_stream_fn(EventType.TOKEN, token)
            
            # Log token for debugging
            logger.info(f"Token directly sent to output_stream_fn: '{token}'")
            
            self.tokens_sent = True
            
            # Add to buffer for potential message reassembly later
            self.token_buffer += token
            
            # Also put in queue for other consumers
            await self.queue.put(token)
            self.token_count += 1
            
            # Special log for the first token
            if self.token_count == 1:
                logger.info(f"First token sent via CallbackHandler. This should trigger SSE event.")
        except Exception as e:
            logger.error(f"Error processing token in on_llm_new_token: {e}", exc_info=True)

    async def on_tool_start(self, serialized: Dict[str, Any], input_str: str, **kwargs: Any) -> None:
        payload = {"name": serialized.get("name"), "input": input_str}
        self.output_stream_fn("on_tool_start", self._serialize_data(payload))

    async def on_tool_end(self, output: str, **kwargs: Any) -> None:
        self.output_stream_fn("on_tool_end", self._serialize_data({"output": output}))

    async def on_chain_start(self, serialized: Dict[str, Any], inputs: Dict[str, Any], **kwargs: Any) -> None:
        chain_name = "Unknown Chain (serialized is None)"
        if serialized:
            chain_name = serialized.get("name", serialized.get("id", ["Unknown chain"])[-1])
        payload = {"name": chain_name, "inputs": inputs}
        self.output_stream_fn("on_chain_start", self._serialize_data(payload))

    async def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        logger.debug(f"CustomAsyncIteratorCallbackHandler on_llm_end. Response: {response}")
        # Log the raw response from LLM
        # logger.debug(f"CustomAsyncIteratorCallbackHandler on_llm_end. Response: {response!r} llm_output={response.llm_output} run={kwargs.get('run_id')}")

        # LLM streaming is finished. Clear the buffer if needed.
        # Do NOT send ON_CHAIN_END from here; let the service handle the final chain output.
        if self.token_buffer:
             buffered_content = "".join(self.token_buffer)
             logger.info(f"CustomAsyncIteratorCallbackHandler on_llm_end: LLM stream finished. Buffered content: {buffered_content[:70]}...")
             self.token_buffer = "" # Clear buffer after LLM part is done.
        # else:
            # logger.info("CustomAsyncIteratorCallbackHandler on_llm_end: LLM stream finished. Buffer was already empty.")

    async def on_chain_end(self, outputs: Dict[str, Any], **kwargs: Any) -> None:
        logger.debug(f"CustomAsyncIteratorCallbackHandler on_chain_end. Outputs: {outputs}")
        
        # This method is called when a chain ends. We will log the output,
        # but we will NOT send the ON_CHAIN_END event from here.
        # The LangchainAgentService will determine the true final output and send it.

    async def on_agent_action(self, action: AgentAction, **kwargs: Any) -> None:
        self.output_stream_fn("on_agent_action", self._serialize_data(action))
        
    async def on_agent_finish(self, finish: AgentFinish, **kwargs: Any) -> None:
        # Send the final agent output as a 'message' type event
        # The 'output' key within return_values is commonly where the final string is.
        final_output_data = finish.return_values.get("output", finish.return_values)
        self.output_stream_fn("message", self._serialize_data(final_output_data))
        
    async def on_llm_error(self, error: BaseException, **kwargs: Any) -> None:
        self.output_stream_fn("error", str(error))

    async def on_chain_error(self, error: BaseException, **kwargs: Any) -> None:
        self.output_stream_fn("error", str(error))

    async def on_tool_error(self, error: BaseException, **kwargs: Any) -> None:
        self.output_stream_fn("error", f"Tool Error: {str(error)}")

    async def send_final_event_if_needed(self, final_response: str):
        self.output_stream_fn("message", self._serialize_data(final_response))
        self.output_stream_fn("end", "Stream ended")

    async def on_chat_model_start(
        self, serialized: Dict[str, Any], prompts: List[List[BaseMessage]], **kwargs
    ) -> Any:
        logger.debug(f"CustomAsyncIteratorCallbackHandler.on_chat_model_start: Chat model starting")
        try:
            await self.queue.put({"type": "on_chat_model_start"})
            self.output_stream_fn(EventType.START, {"type": "chat_model"})
        except Exception as e:
            logger.error(f"Error in on_chat_model_start: {e}", exc_info=True)

class MCPEventCollector(AsyncCallbackHandler):
    """
    Collects key events from the Langchain stream, particularly the final output.
    This helps in capturing a structured final response for logging or history.
    """
    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)
        self.final_output: Optional[str] = None
        self.collected_events: List[Dict[str, Any]] = []
        logger.info("MCPEventCollector initialized.")

    async def on_chain_end(self, outputs: Dict[str, Any], **kwargs: Any) -> None:
        """Collects output when a chain ends."""
        logger.debug(f"MCPEventCollector on_chain_end. Outputs: {outputs}")
        self.collected_events.append({"event": "on_chain_end", "data": outputs})
        # Heuristic to find the final output string
        if isinstance(outputs, dict):
            if "output" in outputs and isinstance(outputs["output"], str):
                self.final_output = outputs["output"]
                logger.info(f"MCPEventCollector captured final_output from on_chain_end (output key): {self.final_output[:100]}...")
            elif "content" in outputs and isinstance(outputs["content"], str): # If output is AIMessage like
                self.final_output = outputs["content"]
                logger.info(f"MCPEventCollector captured final_output from on_chain_end (content key): {self.final_output[:100]}...")
            elif "result" in outputs and isinstance(outputs["result"], str): # Fallback
                self.final_output = outputs["result"]
                logger.info(f"MCPEventCollector captured final_output from on_chain_end (result key): {self.final_output[:100]}...")


    async def on_agent_finish(self, finish: AgentFinish, **kwargs: Any) -> None:
        """Collects the final output when an agent finishes."""
        logger.debug(f"MCPEventCollector on_agent_finish. Finish: {finish}")
        self.collected_events.append({"event": "on_agent_finish", "data": finish.return_values})
        if "output" in finish.return_values and isinstance(finish.return_values["output"], str):
            self.final_output = finish.return_values["output"]
            logger.info(f"MCPEventCollector captured final_output from on_agent_finish: {self.final_output[:100]}...")

    def get_final_output(self) -> Optional[str]:
        """Returns the captured final output."""
        logger.debug(f"MCPEventCollector get_final_output called. Returning: {self.final_output[:100] if self.final_output else 'None'}")
        return self.final_output

    def get_collected_events(self) -> List[Dict[str, Any]]:
        """Returns all collected events."""
        return self.collected_events

# MOVED EventType class to the top of the file
# class EventType:
#     TOKEN = "token"
#     MESSAGE = "message" # For complete messages or significant updates
#     ERROR = "error"
#     END = "end"         # General stream end
#     CHAIN_START = "on_chain_start"
#     CHAIN_END = "on_chain_end"
#     TOOL_START = "on_tool_start"
#     TOOL_END = "on_tool_end"
#     AGENT_ACTION = "on_agent_action"
#     AGENT_FINISH = "on_agent_finish"
#     CHAT_MODEL_STREAM = "on_chat_model_stream" # Langchain standard for raw token chunks 