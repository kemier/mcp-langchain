#!/usr/bin/env python
"""
Test script to verify both English and Chinese text generation work properly.
"""

import requests
import sys
import time

# Base URL of the running server
BASE_URL = "http://localhost:8008/api"

def test_direct_text_generation(prompt, language="English"):
    """Test the direct text generation endpoint with a prompt"""
    url = f"{BASE_URL}/generate-text"
    
    payload = {
        "prompt": prompt
    }
    
    print(f"Sending {language} text to direct text generation: {prompt}")
    print("This endpoint is using Server-Sent Events, so we'll see streaming updates...")
    
    try:
        # Make a streaming request
        with requests.post(url, json=payload, stream=True, timeout=60) as response:
            if response.status_code == 200:
                # Process the SSE stream
                buffer = ""
                line_buffer = ""
                start_time = time.time()
                
                # Track if we've received any content
                received_content = False
                
                for chunk in response.iter_content(chunk_size=1024, decode_unicode=False):
                    if chunk:
                        received_content = True
                        
                        # Decode the chunk
                        try:
                            decoded_chunk = chunk.decode('utf-8')
                            line_buffer += decoded_chunk
                        except UnicodeDecodeError as e:
                            print(f"\nError decoding chunk: {e}")
                            continue
                        
                        # Process complete lines
                        if '\n' in line_buffer:
                            lines = line_buffer.split('\n')
                            line_buffer = lines.pop()
                            
                            for line in lines:
                                if line.startswith('data:'):
                                    data = line[5:].strip()
                                    if data:
                                        print(data, end='', flush=True)
                                        buffer += data
                        
                        if time.time() - start_time > 60:
                            print("\nTest timeout after 60 seconds")
                            break
                
                # Process any remaining data
                if line_buffer and line_buffer.startswith('data:'):
                    data = line_buffer[5:].strip()
                    if data:
                        print(data, end='', flush=True)
                        buffer += data
                
                print("\n" + "-" * 80)
                print(f"Total response time: {time.time() - start_time:.2f} seconds")
                print(f"Total response length: {len(buffer)} characters")
                
                # Display full response content
                print("\nFull response content:")
                print("=" * 80)
                print(buffer)
                print("=" * 80)
                
                return received_content
            else:
                print(f"Error: {response.status_code}")
                print(response.text)
                return False
    except Exception as e:
        print(f"\nError: {e}")
        return False

if __name__ == "__main__":
    print("Testing both English and Chinese text generation")
    print("=" * 80)
    
    print("\nTest 1: English text generation")
    print("-" * 80)
    test_direct_text_generation("Write a bubble sort algorithm in Python", "English")
    
    print("\nTest 2: Chinese text generation")
    print("-" * 80)
    test_direct_text_generation("写一个冒泡排序算法", "Chinese") 