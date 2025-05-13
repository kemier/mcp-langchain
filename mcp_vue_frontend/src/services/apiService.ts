// import { io, Socket } from 'socket.io-client'; // --- Remove Socket.IO import
import { Observable, Subject, throwError } from 'rxjs'; // Remove unused Subscription import
import { map } from 'rxjs/operators';
import { streamService, StreamEventType } from './streamService';

// Define the base URL for our backend API
export const API_BASE_URL = '/api'; // 使用相对路径，让vite的代理功能处理请求
// 后端WebSocket通常在8000端口而不是前端开发服务器端口
export const WS_BASE_URL = window.location.protocol === 'https:' 
  ? `wss://${window.location.hostname}:8010/ws`
  : `ws://${window.location.hostname}:8010/ws`; // WebSocket base URL

// Define an interface for the server configuration we expect from the backend
// This should match the Pydantic model in your FastAPI backend (models.ServerConfig)
export interface ToolCapability {
    name: string;
    description: string;
}

// Restore the original ServerConfig definition based on component usage errors
export interface ServerConfig {
    name: string; // Unique key/ID for the server config
    display_name?: string; // Optional user-friendly name
    description: string;
    command: string;
    args: string[];
    transport: string; // e.g., 'stdio', 'http'
    url?: string; // Optional URL, relevant for http transport
    cwd?: string; // Optional working directory
    env?: Record<string, string>; // Optional environment variables
    capabilities_for_tool_config: ToolCapability[]; // Discovered capabilities
    // Note: Fields like display_name, provider, ollama_config etc. belong in LLMConfig
}

// Define an interface for the server status response
export interface ServerStatusResponse {
    server_name: string;
    status: string;
    message?: string;
    pid?: number;
    discovered_capabilities?: any[];
    last_updated_timestamp?: string; // Added optional last_updated_timestamp property
}

// --- NEW Chat Message Interface ---
export interface ChatMessage {
    sender: 'user' | 'agent' | 'system';
    text: string;
    id?: string;
    isGenerating?: boolean;
    isStreaming?: boolean; // Added optional isStreaming property
    isError?: boolean; // Added optional isError property
}

// --- NEW Chat Request Interface (matches backend Pydantic model) ---
interface ChatBotRequest {
    message: string;
    active_tools_config: Record<string, any[]>; // Simplified for now
}

// --- NEW Chat Response Interface (matches backend Pydantic model) ---
interface ChatBotResponse {
    reply: string;
}

// --- LLM Configuration Model (matches backend Pydantic LLMConfig) ---
export interface OllamaConfig {
    base_url: string;
    model: string;
    temperature: number;
    // Add other Ollama-specific options if mirrored from backend
}

// Define simple interfaces for other provider configs based on usage errors
interface OpenAIConfig {
    model: string;
    base_url?: string;
    api_key_env_var?: string;
}

interface DeepSeekConfig {
    model?: string; // Assuming model is optional based on errors
    base_url?: string;
    api_key_env_var?: string;
}

export interface LLMConfig {
    config_id?: string; // Made optional based on usage
    provider: string; // e.g., "ollama", "openai", "deepseek"
    display_name: string; // User-friendly name, e.g., "Local Llama3 (Ollama)"
    ollama_config?: OllamaConfig; // Optional, present if provider is ollama
    openai_config?: OpenAIConfig; // Added optional openai_config
    deepseek_config?: DeepSeekConfig; // Added optional deepseek_config
    api_key_env_var?: string; // e.g., "OPENAI_API_KEY", if API key is needed from env
    is_default?: boolean;
}

// This interface is used when the frontend sends a new chat message to the WebSocket
export interface WebSocketChatPayload {
    session_id: string;
    prompt: string;
    tools_config: Record<string, any[]>;
    llm_config_id?: string | null; // Added for LLM selection
}

// +++ Type for LLM Config Update Payload (Partial LLMConfig for frontend use) +++
export type LLMConfigUpdatePayload = Partial<Omit<LLMConfig, 'config_id'>>;

/**
 * Fetches the list of all configured MCP servers from the backend.
 */
export async function getServers(): Promise<Record<string, ServerConfig>> {
    try {
        const response = await fetch(`${API_BASE_URL}/servers`);
        if (!response.ok) {
            // If the server response is not OK (e.g., 404, 500),
            // throw an error with the status text.
            const errorData = await response.text();
            throw new Error(`Failed to fetch servers: ${response.status} ${response.statusText} - ${errorData}`);
        }
        return await response.json() as Record<string, ServerConfig>;
    } catch (error) {
        console.error('Error fetching servers:', error);
        throw error; // Re-throw the error to be caught by the calling component
    }
}

/**
 * Fetches the list of all available LLM configurations from the backend.
 */
export async function fetchLLMConfigurations(): Promise<LLMConfig[]> {
    try {
        const response = await fetch(`${API_BASE_URL}/llm-configs`);
        if (!response.ok) {
            const errorData = await response.text();
            throw new Error(`Failed to fetch LLM configurations: ${response.status} ${response.statusText} - ${errorData}`);
        }
        return await response.json() as LLMConfig[];
    } catch (error) {
        console.error('Error fetching LLM configurations:', error);
        throw error; // Re-throw the error to be caught by the calling component
    }
}

/**
 * Sends a request to start a specific MCP server.
 * @param serverId The ID of the server to start.
 */
export async function startServer(serverId: string): Promise<ServerStatusResponse> {
    try {
        if (!serverId || typeof serverId !== 'string') {
            throw new Error(`Invalid server ID: ${serverId}`);
        }
        
        console.log(`[API-DEBUG] Starting server request for: ${serverId}`);
        const url = `${API_BASE_URL}/servers/${serverId}/start`;
        console.log(`[API-DEBUG] Request URL: ${url}`);
        
        let response;
        try {
            response = await fetch(url, {
                method: 'POST',
            });
            console.log(`[API-DEBUG] Server start response status: ${response.status} ${response.statusText}`);
        } catch (fetchError: any) {
            console.error(`[API-DEBUG] Fetch operation failed:`, fetchError);
            throw new Error(`Network error while starting server ${serverId}: ${fetchError.message}`);
        }
        
        if (!response.ok) {
            let errorData;
            try {
                errorData = await response.text();
                console.error(`[API-DEBUG] Error response body: ${errorData}`);
            } catch (textError: any) {
                console.error(`[API-DEBUG] Failed to read error response body:`, textError);
                errorData = 'Could not read error details';
            }
            
            throw new Error(`Failed to start server ${serverId}: ${response.status} ${response.statusText} - ${errorData}`);
        }
        
        let responseData;
        try {
            responseData = await response.json();
            console.log(`[API-DEBUG] Server start success response:`, responseData);
        } catch (jsonError: any) {
            console.error(`[API-DEBUG] Failed to parse JSON response:`, jsonError);
            throw new Error(`Invalid response format while starting server ${serverId}: ${jsonError.message}`);
        }
        
        return responseData as ServerStatusResponse;
    } catch (error) {
        console.error(`[API-DEBUG] Exception in startServer for ${serverId}:`, error);
        throw error;
    }
}

/**
 * Sends a request to stop a specific MCP server.
 * @param serverId The ID of the server to stop.
 */
export async function stopServer(serverId: string): Promise<ServerStatusResponse> {
    try {
        const response = await fetch(`${API_BASE_URL}/servers/${serverId}/stop`, {
            method: 'POST',
        });
        if (!response.ok) {
            const errorData = await response.text();
            throw new Error(`Failed to stop server ${serverId}: ${response.status} ${response.statusText} - ${errorData}`);
        }
        return await response.json() as ServerStatusResponse;
    } catch (error) {
        console.error(`Error stopping server ${serverId}:`, error);
        throw error;
    }
}

/**
 * Fetches the status of a specific MCP server.
 * @param serverId The ID of the server to get status for.
 */
export async function getServerStatus(serverId: string): Promise<ServerStatusResponse> {
    try {
        const response = await fetch(`${API_BASE_URL}/servers/${serverId}/status`);
        if (!response.ok) {
            const errorData = await response.text();
            throw new Error(`Failed to get status for server ${serverId}: ${response.status} ${response.statusText} - ${errorData}`);
        }
        return await response.json() as ServerStatusResponse;
    } catch (error) {
        console.error(`Error getting status for server ${serverId}:`, error);
        throw error;
    }
}

/**
 * Refreshes the capabilities of a specific MCP server.
 * @param serverId The ID of the server to refresh capabilities for.
 */
export async function refreshServerCapabilities(serverId: string): Promise<ServerStatusResponse> {
    try {
        const response = await fetch(`${API_BASE_URL}/servers/${serverId}/refresh-capabilities`, {
            method: 'POST',
        });
        if (!response.ok) {
            const errorData = await response.text();
            throw new Error(`Failed to refresh capabilities for server ${serverId}: ${response.status} ${response.statusText} - ${errorData}`);
        }
        return await response.json() as ServerStatusResponse;
    } catch (error) {
        console.error(`Error refreshing capabilities for server ${serverId}:`, error);
        throw error;
    }
}

/**
 * Adds a new server configuration.
 * @param serverName The name/identifier for the new server
 * @param config The server configuration object
 */
export async function addServer(serverName: string, config: ServerConfig): Promise<{ success: boolean; message: string }> {
    try {
        console.log(`[API] Adding new server: ${serverName}`, config);
        
        const response = await fetch(`${API_BASE_URL}/servers`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                config_key: serverName,
                config: config
            }),
        });
        
        const responseData = await response.json();
        
        if (!response.ok) {
            throw new Error(`Failed to add server: ${responseData.message || response.statusText}`);
        }
        
        return responseData;
    } catch (error) {
        console.error(`Error adding server ${serverName}:`, error);
        throw error;
    }
}

// --- NEW agentChat function ---
/**
 * Sends a message to the chat bot and gets a reply.
 * @param message The user's message.
 * @param activeToolsConfig The configuration of tools to be made available to the bot.
 */
export async function chatBot(message: string, activeToolsConfig: Record<string, any[]>): Promise<string> {
    const requestBody: ChatBotRequest = {
        message,
        active_tools_config: activeToolsConfig
    };

    try {
        const response = await fetch(`${API_BASE_URL}/chat_bot`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(requestBody),
        });

        if (!response.ok) {
            // Try to parse error detail from JSON response, otherwise use statusText
            const errorDetail = await response.json().then(data => data.detail).catch(() => response.statusText);
            throw new Error(`Chat bot failed: ${response.status} - ${errorDetail || 'Unknown error'}`);
        }
        const responseData: ChatBotResponse = await response.json();
        return responseData.reply;
    } catch (error) {
        console.error('Error in chatBot service call:', error);
        throw error; // Re-throw to be caught by the calling component
    }
}

/**
 * Creates a new server configuration by sending it to the backend.
 * @param configKey The unique key for the server config (used as the key in servers.json)
 * @param config The server configuration object
 */
export async function createServerConfig(configKey: string, config: ServerConfig): Promise<{ success: boolean; message: string }> {
    try {
        const response = await fetch(`${API_BASE_URL}/servers`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ config_key: configKey, config }),
        });
        if (!response.ok) {
            const errorData = await response.text();
            throw new Error(`Failed to create server config: ${response.status} ${response.statusText} - ${errorData}`);
        }
        return await response.json();
    } catch (error) {
        console.error('Error creating server config:', error);
        throw error;
    }
}

/**
 * Updates an existing server configuration by sending it to the backend.
 * @param serverId The unique key for the server config to update
 * @param config The updated server configuration object
 */
export async function updateServerConfig(serverId: string, config: ServerConfig): Promise<{ success: boolean; message: string }> {
    try {
        const response = await fetch(`${API_BASE_URL}/servers/${serverId}`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ config }),
        });
        if (!response.ok) {
            const errorData = await response.text();
            throw new Error(`Failed to update server config: ${response.status} ${response.statusText} - ${errorData}`);
        }
        return await response.json();
    } catch (error) {
        console.error(`Error updating server config for ${serverId}:`, error);
        throw error;
    }
}

/**
 * Removes a server configuration from the backend.
 * @param serverId The unique key for the server config to remove
 */
export async function removeServerConfig(serverId: string): Promise<{ success: boolean; message: string }> {
    try {
        const response = await fetch(`${API_BASE_URL}/servers/${serverId}`, {
            method: 'DELETE',
        });
        if (!response.ok) {
            const errorData = await response.text();
            throw new Error(`Failed to remove server config: ${response.status} ${response.statusText} - ${errorData}`);
        }
        return await response.json();
    } catch (error) {
        console.error(`Error removing server config for ${serverId}:`, error);
        throw error;
    }
}

/**
 * Creates an Observable stream for text generation using WebSockets
 * This is the main method used for streaming chat replies from the server
 */
export function streamTextGenerationObservable(
  sessionId: string,
  prompt: string,
  toolsConfig: any = {},
  llmConfigId: string | null = null,
  baseURL: string = API_BASE_URL,
  debugMode: boolean = false
): Observable<any> {
  if (!prompt || prompt.trim() === '') {
    console.error('Empty prompt provided to streamTextGenerationObservable');
    return throwError(() => new Error('Prompt cannot be empty'));
  }
  
  console.log(`[API-SERVICE] Starting WebSocket stream for session ${sessionId}`);
  
  // Create payload object
  const payload = {
    prompt: prompt,
    tools_config: toolsConfig,
    llm_config_id: llmConfigId,
    agent_mode: 'chat',
    session_id: sessionId
  };
  
  try {
    // 使用正确的后端WebSocket URL
    // 固定使用8010端口，而不是前端开发服务器端口5173
    const wsUrl = window.location.protocol === 'https:' 
      ? `wss://${window.location.hostname}:8010/ws/chat` 
      : `ws://${window.location.hostname}:8010/ws/chat`;
    
    // 开启WebSocket调试信息
    if (debugMode) {
      console.log(`[API-SERVICE] WebSocket连接URL: ${wsUrl}`);
      console.log(`[API-SERVICE] 发送payload: ${JSON.stringify(payload).substring(0, 200)}...`);
    }
    
    // 使用streamService创建WebSocket连接
    const stream$ = streamService.createWebSocketStream(
      wsUrl,
      payload,
      sessionId,
      debugMode
    );
    
    return stream$;
  } catch (error) {
    console.error('[API-SERVICE] Error creating stream:', error);
    return throwError(() => new Error(`Failed to start stream: ${error}`));
  }
}

// --- Debugging log function for frontend ---
// This function will send logs to a backend endpoint for server-side collection.
// This is useful for debugging issues that are hard to reproduce or inspect in the browser console.
const DEBUG_LOG_URL = '/api/debug-log'; // 使用相对路径，与API_BASE_URL保持一致

interface FrontendLogDetails {
    // Define a flexible structure for details
    [key: string]: any; 
}

// Function to send a debug log entry to the backend
export async function sendDebugLog(source: string, event: string, details: FrontendLogDetails) {
    const timestamp = new Date().toISOString();
    try {
        await fetch(DEBUG_LOG_URL, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ timestamp, source, event, details }),
        });
    } catch (error) {
        console.error('Failed to send debug log to backend:', error);
    }
}

// +++ LLM Configuration CRUD functions +++

/**
 * Adds a new LLM configuration to the backend.
 * @param config The LLM configuration object to add.
 * @returns The created LLM configuration.
 */
export async function addLLMConfiguration(config: LLMConfig): Promise<LLMConfig> {
    try {
        const response = await fetch(`${API_BASE_URL}/llm-configs`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(config),
        });
        if (!response.ok) {
            const errorData = await response.json().catch(() => ({ detail: response.statusText }));
            throw new Error(`Failed to add LLM configuration: ${response.status} - ${errorData.detail || 'Unknown error'}`);
        }
        return await response.json() as LLMConfig;
    } catch (error) {
        console.error('Error adding LLM configuration:', error);
        throw error;
    }
}

/**
 * Updates an existing LLM configuration on the backend.
 * @param configId The ID of the LLM configuration to update.
 * @param updatePayload An object containing the fields to update.
 * @returns The updated LLM configuration.
 */
export async function updateLLMConfiguration(configId: string, updatePayload: LLMConfigUpdatePayload): Promise<LLMConfig> {
    try {
        const response = await fetch(`${API_BASE_URL}/llm-configs/${configId}`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(updatePayload),
        });
        if (!response.ok) {
            const errorData = await response.json().catch(() => ({ detail: response.statusText }));
            throw new Error(`Failed to update LLM configuration ${configId}: ${response.status} - ${errorData.detail || 'Unknown error'}`);
        }
        return await response.json() as LLMConfig;
    } catch (error) {
        console.error(`Error updating LLM configuration ${configId}:`, error);
        throw error;
    }
}

/**
 * Deletes an LLM configuration from the backend.
 * @param configId The ID of the LLM configuration to delete.
 * @returns A success message object.
 */
export async function deleteLLMConfiguration(configId: string): Promise<{ message: string }> {
    try {
        const response = await fetch(`${API_BASE_URL}/llm-configs/${configId}`, {
            method: 'DELETE',
        });
        if (!response.ok) {
            const errorData = await response.json().catch(() => ({ detail: response.statusText }));
            throw new Error(`Failed to delete LLM configuration ${configId}: ${response.status} - ${errorData.detail || 'Unknown error'}`);
        }
        return await response.json() as { message: string };
    } catch (error) {
        console.error(`Error deleting LLM configuration ${configId}:`, error);
        throw error;
    }
}

// +++ End LLM Configuration CRUD functions +++

// +++ New function to test Ollama connection +++
export interface OllamaConnectionTestResponse {
    success: boolean;
    message: string;
    details?: string;
}

export async function testOllamaConnection(baseUrl: string): Promise<OllamaConnectionTestResponse> {
    try {
        const response = await fetch(`${baseUrl}/api/tags`, {
            method: 'GET',
            headers: {
                'Content-Type': 'application/json',
            },
        });
        if (!response.ok) {
            const errorData = await response.text();
            throw new Error(`Failed to test Ollama connection: ${response.status} ${response.statusText} - ${errorData}`);
        }
        const responseData = await response.json();
        return {
            success: true,
            message: 'Successfully connected to Ollama',
            details: JSON.stringify(responseData)
        };
    } catch (error) {
        console.error('Error testing Ollama connection:', error);
        return {
            success: false,
            message: error instanceof Error ? error.message : 'Unknown error connecting to Ollama',
            details: String(error)
        };
    }
}

// +++ New function to fetch Ollama models +++
export interface OllamaModelListApiResponse {
    success: boolean;
    message: string;
    models?: string[];
}

export async function fetchOllamaModels(baseUrl: string): Promise<OllamaModelListApiResponse> {
    try {
        const response = await fetch(`${baseUrl}/api/tags`, {
            method: 'GET',
            headers: {
                'Content-Type': 'application/json',
            },
        });
        if (!response.ok) {
            const errorData = await response.text();
            throw new Error(`Failed to fetch Ollama models: ${response.status} ${response.statusText} - ${errorData}`);
        }
        const responseData = await response.json();
        
        // The Ollama API returns a different structure than what we want
        // Transform it to our expected format
        const models = responseData.models?.map((model: any) => model.name) || [];
        
        return {
            success: true,
            message: `Successfully fetched ${models.length} models`,
            models: models
        };
    } catch (error) {
        console.error('Error fetching Ollama models:', error);
        return {
            success: false,
            message: error instanceof Error ? error.message : 'Unknown error fetching Ollama models'
        };
    }
}

/**
 * Updates the active tools for the LLM configuration.
 * @param activeToolsConfig Record of active tools configuration.
 * @returns A success response object.
 */
export async function updateLLMActiveTools(activeToolsConfig: Record<string, any[]>): Promise<{ success: boolean; message: string }> {
    try {
        const response = await fetch(`${API_BASE_URL}/llm/active-tools`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ active_tools_config: activeToolsConfig }),
        });
        if (!response.ok) {
            const errorData = await response.text();
            throw new Error(`Failed to update LLM active tools: ${response.status} ${response.statusText} - ${errorData}`);
        }
        return await response.json() as { success: boolean; message: string };
    } catch (error) {
        console.error('Error updating LLM active tools:', error);
        throw error;
    }
}