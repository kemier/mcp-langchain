#!/usr/bin/env python3
import asyncio
import uvicorn
import json
import random
from typing import List, Optional
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

# Create FastAPI app
app = FastAPI(title="SSE Test Server", version="0.1.0")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for testing
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class SSETestRequest(BaseModel):
    """Request model for the SSE test endpoint"""
    delay_ms: Optional[int] = 100  # Delay between tokens in milliseconds
    tokens: Optional[List[str]] = None  # Optional list of tokens to send
    message: Optional[str] = None  # Optional complete message to tokenize and send

@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "status": "ok", 
        "service": "SSE Test Server", 
        "version": "0.1.0"
    }

@app.post("/api/test-sse-stream")
async def test_sse_stream(request: SSETestRequest):
    """
    Test endpoint that sends a stream of SSE events to help diagnose
    frontend streaming issues. This simulates what a real LLM stream would do.
    """
    print(f"SSE Test: Starting test stream with delay: {request.delay_ms}ms")
    
    # Determine what tokens to send
    tokens = request.tokens
    if not tokens and request.message:
        # Split the message into artificial tokens
        message = request.message
        tokens = []
        while message:
            # Take 1-5 characters at a time to simulate variable token lengths
            token_len = min(len(message), random.randint(1, 5))
            tokens.append(message[:token_len])
            message = message[token_len:]
    
    if not tokens:
        # Default test tokens if none provided
        tokens = ["Hello", " world", "!", " This", " is", " a", " test", " of", " the", " SSE", " streaming", " functionality", "."]
    
    # Set appropriate headers for SSE
    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",  # Disable Nginx buffering
    }
    
    # Define the test event generator
    async def generate_test_events():
        try:
            # Send each token
            for i, token in enumerate(tokens):
                yield {
                    "event": "token",
                    "data": json.dumps({"content": token})
                }
                print(f"SSE Test: Sent token #{i+1}: '{token}'")
                await asyncio.sleep(request.delay_ms / 1000)  # Convert ms to seconds
            
            # Send completion event with the full message
            full_message = "".join(tokens)
            yield {
                "event": "generation_complete",
                "data": json.dumps({"status": "done", "content": full_message})
            }
            print(f"SSE Test: Completed test stream, sent {len(tokens)} tokens")
        except Exception as e:
            print(f"SSE Test: Error in test stream: {e}")
            yield {
                "event": "error_event",
                "data": json.dumps({"error": str(e)})
            }
    
    # Return the test event stream
    return EventSourceResponse(
        generate_test_events(),
        media_type="text/event-stream",
        headers=headers
    )

@app.post("/api/test-server/add")
async def add_numbers(a: float, b: float):
    """Simple test endpoint to add two numbers"""
    result = a + b
    return {"result": result}

if __name__ == "__main__":
    print("Starting SSE test server on http://localhost:8010")
    uvicorn.run(app, host="0.0.0.0", port=8010) 