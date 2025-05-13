#!/usr/bin/env python
"""
Test script to directly test non-ASCII (Chinese) text with the MCP server.
This bypasses the frontend and sends a direct request to our enhanced API.
"""

import requests
import json
import sys
import time

# Base URL of the running server
BASE_URL = "http://localhost:8008/api"

def test_chatbot_with_chinese():
    """Test the chat endpoint with Chinese text"""
    url = f"{BASE_URL}/chat_bot"
    chinese_text = "写一个冒泡排序"
    
    payload = {
        "message": chinese_text,
        "active_tools_config": {}  # No tools to force using direct LLM
    }
    
    print(f"Sending Chinese text to server: {chinese_text}")
    start_time = time.time()
    
    try:
        response = requests.post(url, json=payload, timeout=30)
        
        if response.status_code == 200:
            duration = time.time() - start_time
            result = response.json()
            print(f"Response received in {duration:.2f} seconds")
            print("Response:")
            print(result["reply"])
            return True
        else:
            duration = time.time() - start_time
            print(f"Error: {response.status_code}, {duration:.2f} seconds")
            print(response.text)
            return False
    except requests.exceptions.Timeout:
        print(f"Request timed out after 30 seconds")
        return False
    except Exception as e:
        print(f"Error: {e}")
        return False

def test_direct_text_generation():
    """Test the direct text generation endpoint with Chinese text"""
    url = f"{BASE_URL}/generate-text"
    chinese_text = "写一个冒泡排序"
    
    payload = {
        "prompt": chinese_text
    }
    
    print(f"Sending Chinese text to direct text generation: {chinese_text}")
    print("This endpoint is using Server-Sent Events, so we'll see streaming updates...")
    
    try:
        # Make a streaming request with longer timeout
        with requests.post(url, json=payload, stream=True, timeout=60) as response:
            if response.status_code == 200:
                # Process the SSE stream
                buffer = ""
                line_buffer = ""
                start_time = time.time()
                print_dot_interval = 5  # Print a dot every 5 seconds if no content
                last_dot_time = time.time()
                
                # Track if we've received any real content (not just initial messages)
                received_actual_content = False
                
                for chunk in response.iter_content(chunk_size=1024, decode_unicode=False):
                    if chunk:
                        # Track that we've received some response
                        received_actual_content = True
                        
                        # Decode the chunk using UTF-8 to handle Chinese characters
                        try:
                            decoded_chunk = chunk.decode('utf-8')
                            line_buffer += decoded_chunk
                        except UnicodeDecodeError as e:
                            print(f"\nError decoding chunk: {e}")
                            continue
                        
                        # Process any complete lines in the buffer
                        if '\n' in line_buffer:
                            lines = line_buffer.split('\n')
                            line_buffer = lines.pop()  # Keep incomplete line in buffer
                            
                            for line in lines:
                                if line.startswith('data:'):
                                    data = line[5:].strip()
                                    if data:
                                        print(data, end='', flush=True)
                                        buffer += data
                            
                        # Print a dot occasionally to show we're still waiting
                        current_time = time.time()
                        if not received_actual_content and current_time - last_dot_time > print_dot_interval:
                            print(".", end='', flush=True)
                            last_dot_time = current_time
                        
                        # Check for timeout
                        if current_time - start_time > 90:  # 90 second overall timeout
                            print("\nRequest timeout (90 seconds)")
                            break
                
                # Handle any remaining data in the line buffer
                if line_buffer and line_buffer.startswith('data:'):
                    data = line_buffer[5:].strip()
                    if data:
                        print(data, end='', flush=True)
                        buffer += data
                
                print("\n" + "-" * 80)
                print(f"Total response time: {time.time() - start_time:.2f} seconds")
                print(f"Total response length: {len(buffer)} characters")
                
                if not received_actual_content:
                    print("Warning: No actual content was received from the server")
                
                return received_actual_content
            else:
                print(f"Error: {response.status_code}")
                print(response.text)
                return False
    except requests.exceptions.Timeout:
        print("\nRequest timed out")
        return False
    except Exception as e:
        print(f"\nError: {e}")
        return False

if __name__ == "__main__":
    print("Testing Chinese text handling in MCP server")
    print("=" * 80)
    
    print("\nTest 1: Chat endpoint with Chinese text")
    print("-" * 80)
    test_chatbot_with_chinese()
    
    print("\nTest 2: Direct text generation with Chinese text")
    print("-" * 80)
    test_direct_text_generation() 