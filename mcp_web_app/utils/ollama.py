import httpx
import logging
from typing import Optional, List, Dict, Any
from pydantic import ValidationError
from mcp_web_app.models.ollama import OllamaTagsResponse

logger = logging.getLogger(__name__)

async def test_ollama_connection_helper(base_url: str) -> Dict[str, Any]:
    base_url = base_url.rstrip('/') + '/'
    test_url = base_url
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(test_url)
        if response.status_code == 200:
            if "ollama is running" in response.text.lower():
                return {"success": True, "message": "Successfully connected to Ollama and recognized the server."}
            else:
                return {"success": False, "message": "Connected to the server, but it doesn't appear to be an Ollama instance.", "details": f"Status: {response.status_code}. Response: {response.text[:200]}"}
        else:
            return {"success": False, "message": f"Failed to connect to Ollama. Server returned status {response.status_code}.", "details": response.text[:200]}
    except httpx.TimeoutException:
        return {"success": False, "message": "Connection to Ollama timed out. Ensure the server is reachable and not blocked by a firewall."}
    except httpx.ConnectError:
        return {"success": False, "message": "Connection to Ollama failed. Ensure the Base URL is correct and the Ollama server is running."}
    except Exception as e:
        return {"success": False, "message": f"An unexpected error occurred: {str(e)}"}

async def list_ollama_models_helper(base_url: str) -> Dict[str, Any]:
    base_url = base_url.rstrip('/')
    list_tags_url = f"{base_url}/api/tags"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(list_tags_url)
        if response.status_code == 200:
            try:
                tags_data = response.json()
                ollama_tags = OllamaTagsResponse(**tags_data)
                model_names = [model.name for model in ollama_tags.models]
                return {"success": True, "models": model_names}
            except ValidationError as e_val:
                return {"success": False, "message": "Failed to parse response from Ollama server.", "details": str(e_val)}
            except Exception as e_parse:
                return {"success": False, "message": "Error processing data from Ollama server.", "details": str(e_parse)}
        else:
            return {"success": False, "message": f"Ollama server returned status {response.status_code}.", "details": response.text[:200]}
    except httpx.TimeoutException:
        return {"success": False, "message": "Request to fetch models from Ollama timed out."}
    except Exception as e:
        return {"success": False, "message": f"An unexpected error occurred: {str(e)}"} 