<script setup lang="ts">
import { ref, onMounted, reactive, watch, onUnmounted, nextTick, computed } from 'vue';
import { useRouter } from 'vue-router';
import { useStore } from 'vuex';
import {
    getServers,
    fetchLLMConfigurations,
    type ServerConfig,
    type LLMConfig,
    type ChatMessage,
    streamTextGenerationObservable,
    API_BASE_URL
} from '../services/apiService';
import { type Subscription } from 'rxjs';
import ChatMessageComponent from '../components/ChatMessage.vue';

const servers = ref<Record<string, ServerConfig>>({});
const serverStatuses = reactive<Record<string, { status: string; message?: string; pid?: number; discovered_capabilities?: any[], last_updated_timestamp?: string }>>({});
const error = ref<string | null>(null);
const isLoading = ref<boolean>(true);

// --- Chat State ---
const inputMessage = ref<string>("");
const chatHistory = computed(() => store.getters.getChatHistory);
const selectedToolsForBot = reactive<Record<string, boolean>>({});
const isChatLoading = ref<boolean>(false);
const chatError = ref<string | null>(null);
const currentChatSubscription = ref<Subscription | null>(null);
const currentGeneratingMessageId = ref<string | null>(null);
const chatHistoryContainer = ref<HTMLElement | null>(null);

// +++ LLM Configuration State +++
const llmConfigs = ref<LLMConfig[]>([]);
const selectedLLMConfigId = ref<string | null>(null);
const isLLMLoading = ref<boolean>(false);
const llmError = ref<string | null>(null);

const router = useRouter();
const store = useStore();

function copyToClipboard(text: string, event?: MouseEvent) {
  console.log('[COPY-DEBUG] copyToClipboard called with text:', text, 'event:', event);
  navigator.clipboard.writeText(text)
    .then(() => {
      // const event = window.event as MouseEvent; // Replaced with passed event
      if (event?.target instanceof HTMLElement) {
        const button = event.target.closest('button'); // Try to get the button more reliably
        if (button) {
            const originalTextElement = button.querySelector('.copy-status') || button;
            const originalText = originalTextElement.textContent;
            
            if (originalTextElement.textContent !== 'Copied!') { // Avoid re-setting if already copied
                originalTextElement.textContent = 'Copied!';
                button.classList.add('copied'); // Assuming there's a 'copied' class for styling
                
                setTimeout(() => {
                  originalTextElement.textContent = originalText || 'Copy';
                  button.classList.remove('copied');
                }, 2000);
            }
        }
      }
    })
    .catch(err => {
      console.error('Failed to copy text: ', err);
    });
}

async function fetchInitialStatuses() {
    for (const serverName of Object.keys(servers.value)) {
        selectedToolsForBot[serverName] = false; 
        try {
            serverStatuses[serverName] = { 
                status: 'unknown',
                message: 'Status pending...',
                pid: undefined,
                discovered_capabilities: servers.value[serverName]?.capabilities_for_tool_config || [],
                last_updated_timestamp: new Date().toISOString()
            };
        } catch (err: any) {
            console.error(`Failed to get initial status for ${serverName}:`, err);
            serverStatuses[serverName] = { status: 'unknown', message: err?.message || 'Failed to fetch status', discovered_capabilities: [], last_updated_timestamp: new Date().toISOString() };
        }
    }
}

function setupCopyButtons() {
  // This function's direct button manipulation might conflict with Vue's reactivity.
  // Consider integrating copy logic more directly into components or using event delegation if issues arise.
  // For now, assuming it works with nextTick for components that re-render.
}

watch(chatHistory, () => {
  nextTick(() => {
    setupCopyButtons();
    if (chatHistoryContainer.value) {
      chatHistoryContainer.value.scrollTop = chatHistoryContainer.value.scrollHeight;
    }
  });
}, { deep: true });

onMounted(async () => {
  try {
    await fetchServers(); 
    await loadLLMConfigs();
  } catch (error) {
    console.error('Error during initialization:', error);
    // Continue with the app even if there are errors
  }
});

onUnmounted(() => {
  if (currentChatSubscription.value) {
    console.log("[CHAT-RXJS-DEBUG] Component unmounting, unsubscribing from active chat stream.");
    currentChatSubscription.value.unsubscribe();
    currentChatSubscription.value = null;
  }
});

async function handleSendMessage() {
  console.log('[CHAT-TRACE] ========== SENDING NEW MESSAGE ==========');
  if (!inputMessage.value.trim()) {
    console.log('[CHAT-TRACE] Message empty, not sending');
    return;
  }
  if (isChatLoading.value) { 
      console.warn('[CHAT-TRACE] Already loading/streaming, preventing double send');
      return; 
  }

  const messageText = inputMessage.value.trim();
  console.log('[CHAT-TRACE] Message text length:', messageText.length);
  console.log('[CHAT-TRACE] Message preview:', messageText.substring(0, 50) + (messageText.length > 50 ? '...' : ''));

  // Create user message and add to store
  const userMessage: ChatMessage = {
    id: `msg-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`,
    sender: 'user',
    text: messageText,
  };
  
  console.log('[CHAT-TRACE] Generated user message ID:', userMessage.id);
  store.dispatch('addChatMessage', userMessage);
  console.log('[CHAT-TRACE] Added user message to history.');

  const currentMessagePrompt = inputMessage.value;
  inputMessage.value = '';

  isChatLoading.value = true;
  chatError.value = null;

  // Generate or reuse session ID
  if (!currentGeneratingMessageId.value) {
    currentGeneratingMessageId.value = `session-${Date.now()}-${Math.random().toString(36).substring(2, 11)}`;
    console.log('[CHAT-TRACE] Created new chat session ID:', currentGeneratingMessageId.value);
  } else {
    console.log('[CHAT-TRACE] Reusing existing session ID:', currentGeneratingMessageId.value);
  }

  // Create agent message placeholder
  const agentMessageId = `msg-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;
  console.log('[CHAT-TRACE] Created agent message ID:', agentMessageId);

  const agentMessage: ChatMessage = {
    id: agentMessageId,
    sender: 'agent',
    text: '',
    isGenerating: true,
    isStreaming: true
  };
  
  // Add agent message to store
  store.dispatch('addChatMessage', agentMessage);
  console.log('[CHAT-TRACE] Added agent message to store');
  
  // Prepare tools config
  const activeTools = Object.entries(selectedToolsForBot)
    .filter(([_, isSelected]) => isSelected)
    .map(([name]) => name);
  
  const activeToolsConfig: Record<string, any[]> = {};
  
  for (const toolName of activeTools) {
    // Add each selected tool's config
    if (servers.value[toolName]?.capabilities_for_tool_config) {
      activeToolsConfig[toolName] = servers.value[toolName].capabilities_for_tool_config;
    }
  }
  
  console.log('[CHAT-TRACE] Active tools config:', JSON.stringify(activeToolsConfig));

  // Clean up previous subscription if it exists
  if (currentChatSubscription.value) {
    console.log('[CHAT-TRACE] Unsubscribing from existing subscription');
    currentChatSubscription.value.unsubscribe();
    currentChatSubscription.value = null;
  }

  try {
    console.log('[CHAT-TRACE] Starting stream...');

    const sessionId = currentGeneratingMessageId.value!;
    
    // Track subscription in a ref to allow cancellation
    currentChatSubscription.value = streamTextGenerationObservable(
      sessionId,
      currentMessagePrompt,
      activeToolsConfig,
      selectedLLMConfigId.value,
      API_BASE_URL,
      true // Debug mode enabled
    ).subscribe({
      next: (eventPayload: any) => {
        
        // Get the agent message and log this event
        const eventType = eventPayload.type || 'unknown';
        console.log(`[CHAT-TRACE] ⬇️ Received event (${eventType})`, {
          dataPreview: typeof eventPayload.data === 'string' 
            ? eventPayload.data.substring(0, 30) + (eventPayload.data.length > 30 ? '...' : '')
            : typeof eventPayload.data
        });
        
        // Process different event types using the store
        switch(eventPayload.type) {
          case 'token': {
            // Extract token content with improved nested JSON handling
            let tokenContent = '';
            
            try {
              if (typeof eventPayload.data === 'string') {
                // Handle string data - might be plain text or JSON
                if (eventPayload.data.trim().startsWith('{')) {
                  try {
                    // Try to parse as JSON
                    const parsedToken = JSON.parse(eventPayload.data);
                    
                    // Look for .type === 'token' and .data structure
                    if (parsedToken && parsedToken.type === 'token' && parsedToken.data !== undefined) {
                      tokenContent = parsedToken.data;
                    } else {
                      // Not in expected format, use as is
                      tokenContent = eventPayload.data;
                    }
                  } catch (jsonError) {
                    // Not valid JSON, use as is
                    tokenContent = eventPayload.data;
                  }
                } else {
                  // Plain string, use as is
                  tokenContent = eventPayload.data;
                }
              } 
              else if (typeof eventPayload.data === 'object' && eventPayload.data !== null) {
                // Handle object data - extract the actual content
                if (eventPayload.data.type === 'token' && eventPayload.data.data !== undefined) {
                  // Extract from nested token structure
                  tokenContent = eventPayload.data.data;
                } else if ('data' in eventPayload.data) {
                  // Simple nested data
                  tokenContent = eventPayload.data.data;
                } else if ('content' in eventPayload.data) {
                  // Content field
                  tokenContent = eventPayload.data.content;
                } else {
                  // Fallback to stringify
                  tokenContent = JSON.stringify(eventPayload.data);
                }
              } else {
                // Fallback for other types
                tokenContent = String(eventPayload.data || '');
              }
              
              // Skip empty tokens
              if (!tokenContent.trim()) {
                console.log('[CHAT-TRACE] Skipping empty token');
                break;
              }
              
              // Log the extracted content
              console.log('[CHAT-TRACE] 🔤 EXTRACTED TOKEN:', 
                tokenContent.length > 50 ? tokenContent.substring(0, 50) + '...' : tokenContent);
              
              // Use the store to process the token - this manages duplication
              store.dispatch('processStreamingToken', { 
                messageId: agentMessageId, 
                token: tokenContent 
              });
            } catch (error) {
              console.error('[CHAT-TRACE] Error processing token:', error);
            }
            
            break;
          }
          
          // Add special handling for on_chain_start events
          case 'on_chain_start': {
            console.log('[CHAT-TRACE] 🔄 Chain start event received');
            
            /* REMOVED dispatching processOtherEvent to prevent display
            // Extract any useful content to display
            let chainStartContent = '';
            try {
              if (typeof eventPayload.data === 'object' && eventPayload.data !== null) {
                if ('name' in eventPayload.data) {
                  chainStartContent = `Starting ${eventPayload.data.name}...`;
                }
              }
              
              // If we have meaningful content, display it
              if (chainStartContent) {
                store.dispatch('processOtherEvent', { 
                  messageId: agentMessageId, 
                  content: chainStartContent 
                });
              }
            } catch (error) {
              console.error('[CHAT-TRACE] Error processing chain start event:', error);
            }
            */
            
            break;
          }
          
          case 'final':
          case 'on_chain_end': {
            // Extract final content with improved handling
            let finalContent = '';
            
            try {
              if (typeof eventPayload.data === 'string') {
                finalContent = eventPayload.data;
              } else if (typeof eventPayload.data === 'object' && eventPayload.data !== null) {
                // If it's an object, check for various content fields
                if ('content' in eventPayload.data) {
                  finalContent = eventPayload.data.content;
                } else if ('data' in eventPayload.data) {
                  finalContent = eventPayload.data.data;
                } else if ('text' in eventPayload.data) {
                  finalContent = eventPayload.data.text;
                } else {
                  // Fallback to stringifying the whole object
                  finalContent = JSON.stringify(eventPayload.data);
                }
              } else {
                // Last resort - convert to string
                finalContent = String(eventPayload.data || '');
              }
              
              // Skip special markers or empty content
              if (!finalContent || 
                  finalContent === 'Stream complete' || 
                  finalContent === '[DONE]') {
                console.log('[CHAT-TRACE] Skipping special marker in final content');
                store.dispatch('finishStreaming', agentMessageId);
                break;
              }
              
              console.log('[CHAT-TRACE] 🏁 Final content:', finalContent ? 
                (finalContent.length > 50 ? finalContent.substring(0, 50) + '...' : finalContent) : 
                '(empty)');
              
              // Check if this final content is already included in the message
              const currentMessageText = 
                store.getters.getChatHistory.find((msg: ChatMessage) => msg.id === agentMessageId)?.text || '';
                
              if (currentMessageText.includes(finalContent)) {
                console.log('[CHAT-TRACE] Final content already in message, skipping');
                store.dispatch('finishStreaming', agentMessageId);
              } else {
                // Process the final content
                store.dispatch('processFinalContent', { 
                  messageId: agentMessageId, 
                  content: finalContent 
                });
              }
            } catch (error) {
              console.error('[CHAT-TRACE] Error processing final content:', error);
              store.dispatch('finishStreaming', agentMessageId);
            }
            
            // Update loading state
            isChatLoading.value = false;
            console.log('[CHAT-TRACE] Streaming completed, loading state set to false');
            break;
          }
          
          case 'error_event': {
            let errorContent = '';
            
            try {
              if (typeof eventPayload.data === 'string') {
                errorContent = eventPayload.data;
              } else if (typeof eventPayload.data === 'object' && eventPayload.data !== null) {
                // Check for various error fields
                if ('error' in eventPayload.data) {
                  errorContent = eventPayload.data.error;
                } else if ('message' in eventPayload.data) {
                  errorContent = eventPayload.data.message;
                } else if ('content' in eventPayload.data) {
                  errorContent = eventPayload.data.content;
                } else if ('data' in eventPayload.data) {
                  errorContent = eventPayload.data.data;
                } else {
                  // Fallback to stringifying the whole object
                  errorContent = JSON.stringify(eventPayload.data);
                }
              } else {
                // Last resort - convert to string
                errorContent = String(eventPayload.data || 'Unknown error');
              }
              
              console.log('[CHAT-TRACE] ❌ Error content:', errorContent);
              
              // Process the error
              store.dispatch('processError', { 
                messageId: agentMessageId, 
                error: errorContent 
              });
              
              // Update UI state
              isChatLoading.value = false;
              
              // Check if it's a recoverable error
              if (typeof eventPayload.data === 'object' && 
                  eventPayload.data !== null && 
                  eventPayload.data.recoverable) {
                console.log('[CHAT-TRACE] This is a recoverable error, recovery handled by stream service');
              }
            } catch (error) {
              console.error('[CHAT-TRACE] Error processing error event:', error);
              store.dispatch('processError', { 
                messageId: agentMessageId, 
                error: 'Failed to process error event'
              });
              isChatLoading.value = false;
            }
            break;
          }
        }
      },
      
      error: (error) => {
        console.error('[CHAT-ERROR] ❌ Error during streaming:', error);
        isChatLoading.value = false;
        chatError.value = `Error: ${error.message || 'Unknown streaming error'}`;
        
        // If there's a current message being generated, mark it as error
        if (currentGeneratingMessageId.value) {
          store.dispatch('markMessageAsError', {
            messageId: currentGeneratingMessageId.value,
            errorMessage: error.message || 'Error during streaming'
          });
          
          // Add a detailed error log for diagnosis
          console.log('[CHAT-DEBUG] WebSocket connection details:',
            {
              url: window.location.href,
              apiBase: API_BASE_URL,
              sessionId: currentGeneratingMessageId.value
            }
          );
          
          // Try to send telemetry about the error
          fetch('/api/debug-log', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              timestamp: new Date().toISOString(),
              source: 'client',
              event: 'streaming_error',
              details: {
                errorMessage: error.message,
                browserInfo: navigator.userAgent,
                sessionId: currentGeneratingMessageId.value
              }
            })
          }).catch(e => console.error('[CHAT-ERROR] Failed to send error telemetry:', e));
        }
        
        currentGeneratingMessageId.value = null;
      },
      
      complete: () => {
        console.log('[CHAT-TRACE] ✅ Stream completed for message ID:', agentMessageId);
        
        // Mark the message as complete in the store
        store.dispatch('finishStreaming', agentMessageId);
        
        // Reset states
        isChatLoading.value = false;
        currentChatSubscription.value = null;
      }
    });

  } catch (e: any) {
    console.error('[CHAT-TRACE] Outer catch block error:', e);
    
    // Display error message
    chatError.value = e.message || 'Failed to initiate chat stream.';
    
    // Update the agent message with the error
    store.dispatch('processError', {
      messageId: agentMessageId,
      error: e.message || 'Failed to initiate chat stream.'
    });
    
    isChatLoading.value = false;
  }
}

async function fetchServers() {
  try {
    isLoading.value = true;
    servers.value = await getServers();
    await fetchInitialStatuses();
    error.value = null;
  } catch (err: any) {
    console.error('Failed to reload servers:', err);
    error.value = err.message || 'An unknown error occurred while fetching servers.';
  } finally {
    isLoading.value = false;
  }
}

async function loadLLMConfigs() {
  isLLMLoading.value = true;
  llmError.value = null;
  try {
    const fetchedLLMs = await fetchLLMConfigurations();
    llmConfigs.value = fetchedLLMs; 
    selectedLLMConfigId.value = null;

    const defaultLLM = fetchedLLMs.find(cfg => cfg.is_default);
    const ollamaConfig = fetchedLLMs.find(cfg => cfg.provider === 'ollama');
    
    if (defaultLLM) {
      selectedLLMConfigId.value = defaultLLM.config_id ?? null; 
    } else if (ollamaConfig) {
      selectedLLMConfigId.value = ollamaConfig.config_id ?? null;
    } else if (fetchedLLMs.length > 0) {
        selectedLLMConfigId.value = fetchedLLMs[0].config_id ?? null;
    }
     // console.log(\"[LLM-CONFIG] Loaded LLMs:\", llmConfigs.value, \"Selected ID:\", selectedLLMConfigId.value); // Commented out due to persistent build errors

  } catch (err: any) {
    console.error('Failed to load LLM configurations:', err);
    llmConfigs.value = [{
      config_id: 'default_fallback_llm',
      provider: 'fallback',
      display_name: '默认模型 (服务器连接错误)',
      is_default: true
    }];
    selectedLLMConfigId.value = 'default_fallback_llm';
    llmError.value = "无法连接到LLM服务器。使用默认模型继续。";
  } finally {
    isLLMLoading.value = false;
  }
}

function goToSeverControls() {
  router.push('/server-controls'); // Assumes router is correctly setup and needed
}

async function testWebSocketConnection() {
  console.log('[CHAT-TEST] Starting WebSocket connection test');
  chatError.value = null;
  isChatLoading.value = true;

  // Add a message to the chat history to display the test results
  const testMessageId = `test-${Date.now()}`;
  store.dispatch('addChatMessage', {
    id: testMessageId,
    sender: 'agent',
    text: 'Testing WebSocket connection...',
    isGenerating: true,
    isStreaming: false,
    isError: false
  });
  
  // Create a new session ID for this test
  const testSessionId = `test-session-${Date.now()}`;
  console.log(`[CHAT-TEST] Created test session ID: ${testSessionId}`);
  
  try {
    if (currentChatSubscription.value) {
      console.log('[CHAT-TEST] Unsubscribing from previous subscription');
      currentChatSubscription.value.unsubscribe();
    }
    
    // Use WebSocket to connect to test endpoint
    console.log('[CHAT-TEST] Connecting to WebSocket test endpoint');
    
    // Create WebSocket connection
    let wsUrl = '';
    if (window.location.protocol === 'https:') {
      wsUrl = `wss://${window.location.host}/ws/test-ws`;
    } else {
      wsUrl = `ws://${window.location.host}/ws/test-ws`;
    }
    
    console.log(`[CHAT-TEST] WebSocket URL: ${wsUrl}`);
    
    // Update message to show connecting status
    store.dispatch('addChatMessage', {
      id: testMessageId,
      sender: 'agent',
      text: 'Connecting to WebSocket at ' + wsUrl + '...',
      isGenerating: true
    });
    
    const socket = new WebSocket(wsUrl);
    
    // Handle WebSocket events
    socket.onopen = () => {
      console.log('[CHAT-TEST] WebSocket connection established');
      store.dispatch('addChatMessage', {
        id: testMessageId,
        sender: 'agent',
        text: 'WebSocket connection established. Waiting for messages...',
        isGenerating: true
      });
      
      // Send a test message
      socket.send(JSON.stringify({
        type: 'test',
        message: 'Hello from client!',
        session_id: testSessionId
      }));
    };
    
    socket.onmessage = (event) => {
      console.log('[CHAT-TEST] Received message:', event.data);
      try {
        const data = JSON.parse(event.data);
        // Update the message with the received data
        store.dispatch('addChatMessage', {
          id: testMessageId,
          sender: 'agent',
          text: store.getters.getChatHistory.find(msg => msg.id === testMessageId)?.text + 
                '\n\nReceived: ' + JSON.stringify(data, null, 2),
          isGenerating: true
        });
      } catch (e) {
        console.error('[CHAT-TEST] Error parsing message:', e);
        store.dispatch('addChatMessage', {
          id: testMessageId,
          sender: 'agent',
          text: store.getters.getChatHistory.find(msg => msg.id === testMessageId)?.text + 
                '\n\nReceived raw message: ' + event.data,
          isGenerating: true
        });
      }
    };
    
    socket.onerror = (error) => {
      console.error('[CHAT-TEST] WebSocket error:', error);
      store.dispatch('addChatMessage', {
        id: testMessageId,
        sender: 'agent',
        text: store.getters.getChatHistory.find(msg => msg.id === testMessageId)?.text + 
              '\n\nWebSocket error occurred.',
        isError: true,
        isGenerating: false
      });
      isChatLoading.value = false;
    };
    
    socket.onclose = (event) => {
      console.log('[CHAT-TEST] WebSocket closed:', event);
      store.dispatch('addChatMessage', {
        id: testMessageId,
        sender: 'agent',
        text: store.getters.getChatHistory.find(msg => msg.id === testMessageId)?.text + 
              '\n\nWebSocket connection closed.' + 
              (event.wasClean ? ' (Clean close)' : ' (Connection error)'),
        isGenerating: false
      });
      isChatLoading.value = false;
    };
    
    // Set a timeout to close the connection after 10 seconds
    setTimeout(() => {
      if (socket.readyState === WebSocket.OPEN) {
        console.log('[CHAT-TEST] Closing test connection after timeout');
        socket.close();
        store.dispatch('addChatMessage', {
          id: testMessageId,
          sender: 'agent',
          text: store.getters.getChatHistory.find(msg => msg.id === testMessageId)?.text + 
                '\n\nTest completed - connection closed after timeout.',
          isGenerating: false
        });
      }
      isChatLoading.value = false;
    }, 10000);
    
  } catch (e) {
    console.error('[CHAT-TEST] Test failed:', e);
    // Update the test message with the error
    store.dispatch('addChatMessage', {
      id: testMessageId,
      sender: 'agent',
      text: `WebSocket test failed: ${e}`,
      isGenerating: false,
      isStreaming: false,
      isError: true
    });
    chatError.value = `WebSocket test failed: ${e}`;
    isChatLoading.value = false;
  }
}

</script>

<template>
  <div class="server-management-view">
    <header class="app-header">
      <div class="logo-title">
        <img src="../assets/logo.png" alt="MCP App Logo" class="logo"/>
        <h1>MCP Server & Chat Management</h1>
      </div>
      <nav class="header-nav">
        <router-link to="/settings/llm-management" class="nav-button">LLM Settings</router-link>
        <button @click="goToSeverControls" class="nav-button add-server-button">Server Controls Panel</button>
      </nav>
    </header>

    <div v-if="isLoading && !Object.keys(servers).length" class="loading-fullscreen">
      Loading initial data...
    </div>
    <div v-if="error && !Object.keys(servers).length" class="error-fullscreen">
      Error loading initial data: {{ error }}
    </div>

    <div v-if="!isLoading || Object.keys(servers).length" class="main-content-grid">
      <!-- Server Management Section REMOVED -->
      <!-- 
      <section class="server-management-section">
        <h2>Tool Servers</h2>
        ...
      </section>
      -->

      <!-- Chat Section -->
      <section class="chat-section full-width-chat">
        <div class="flex flex-col">
          <div class="mb-4 flex justify-between items-center">
            <h2 class="text-xl font-bold">Agent Chat</h2>
          </div>
        </div>

        <!-- +++ LLM Selection Dropdown +++ -->
        <div class="llm-selector-container">
          <label for="llm-select">LLM:</label>
          <select id="llm-select" v-model="selectedLLMConfigId" :disabled="isLLMLoading || llmConfigs.length === 0">
            <option v-if="isLLMLoading" :value="null" disabled>Loading LLMs...</option>
            <option v-else-if="llmError" :value="null" disabled>Error loading LLMs</option>
            <option v-else-if="!llmConfigs.length" :value="null" disabled>No LLMs configured</option>
            <template v-else>
              <option v-for="llm in llmConfigs" :key="llm.config_id" :value="llm.config_id">
                {{ llm.display_name }} {{ llm.is_default ? '(Default)' : '' }}
              </option>
            </template>
          </select>
          <div v-if="isLLMLoading" class="spinner llm-spinner"></div>
        </div>
        
        <!-- Simple error message if there's an issue loading LLMs -->
        <div v-if="!isLLMLoading && llmError" class="error-message error-subtle">{{ llmError }}</div>

        <div class="chat-history" ref="chatHistoryContainer">
          <ChatMessageComponent 
            v-for="msg in chatHistory" 
            :key="msg.id" 
            :message="msg"
            @copy="(text, event) => copyToClipboard(text, event)"
          />
          <div v-if="chatHistory.length === 0" class="chat-welcome-message">
            <h3>欢迎使用MCP聊天助手</h3>
            <p>输入您的问题开始对话。即使服务器暂时无法连接，聊天仍然会正常工作，错误信息会直接显示在对话中。</p>
          </div>
        </div>

        <div class="chat-input-container">
          <textarea 
            v-model="inputMessage" 
            class="chat-input" 
            placeholder="输入您的问题..." 
            @keydown.enter.prevent="handleSendMessage" 
            :disabled="isChatLoading"
          ></textarea>
          <button class="send-button" @click="handleSendMessage" :disabled="isChatLoading || !inputMessage.trim()">
            <span v-if="isChatLoading" class="spinner send-spinner"></span>
            <span v-else>发送</span>
          </button>
        </div>

        <!-- Disclaimer added here -->
        <div class="agent-chat-disclaimer">
          <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="disclaimer-icon"><path d="M12 2a10 10 0 1 0 10 10A10 10 0 0 0 12 2z"/><path d="m15 9-6 6"/><path d="m9 9 6 6"/></svg>
          <span>AI 生成的回答可能不准确</span>
        </div>
      </section>
    </div>
    
    <!-- Debugging tools section can be fully removed if no longer used -->
    <div style="display:none;">
      <div id="troubleshoot-tools">
      </div>
    </div>
  </div>
</template>

<style scoped>
/* General Page Styles */
.server-management-view {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
  background-color: #f0f2f5;
  color: #333;
  font-family: 'Roboto', sans-serif;
}

.app-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 15px 30px;
  background-color: #ffffff;
  box-shadow: 0 2px 4px rgba(0,0,0,0.1);
  border-bottom: 1px solid #e0e0e0;
}

.logo-title {
  display: flex;
  align-items: center;
}

.logo {
  height: 40px;
  margin-right: 15px;
}

.app-header h1 {
  font-size: 1.5rem;
  font-weight: 500;
  color: #2c3e50;
  margin: 0;
}

.header-nav .nav-button {
  margin-left: 15px;
  padding: 8px 15px;
  border: 1px solid #007bff;
  background-color: #007bff;
  color: white;
  border-radius: 5px;
  text-decoration: none;
  font-size: 0.9rem;
  transition: background-color 0.2s ease, color 0.2s ease;
  cursor: pointer;
}
.header-nav .nav-button:hover {
  background-color: #0056b3;
  border-color: #0056b3;
}

.main-content-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 25px;
  padding: 25px;
  flex-grow: 1;
  overflow-y: auto;
}

/* NEW class to ensure chat section takes available space if needed, 
   though grid-template-columns: 1fr on parent might be sufficient */
.chat-section.full-width-chat {
  /* No specific styles needed here if parent grid handles width correctly */
}

/* Server Management Section styles are no longer needed if section is removed */
/* .server-management-section { ... } */
/* .server-cards-container { ... } */
/* .server-card { ... } */
/* ... etc. ... */


/* Chat Section styles remain */
.chat-section {
  background-color: #ffffff;
  padding: 25px;
  border-radius: 8px;
  box-shadow: 0 4px 12px rgba(0,0,0,0.08);
  display: flex;
  flex-direction: column;
  max-height: calc(100vh - 150px);
  overflow: hidden;
}

.chat-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 15px;
  padding-bottom: 10px;
  border-bottom: 2px solid #e0e0e0;
}
.chat-header h2 {
  font-size: 1.4rem;
  color: #2c3e50;
  margin: 0;
}
.new-chat-button {
  padding: 8px 15px;
  font-size: 0.9rem;
  color: #fff;
  background-color: #6c757d;
  border: none;
  border-radius: 5px;
  cursor: pointer;
  transition: background-color 0.2s ease;
}
.new-chat-button:hover {
  background-color: #5a6268;
}

/* +++ LLM Selector Styles +++ */
.llm-selector-container {
  margin-bottom: 15px;
  display: flex;
  align-items: center;
  gap: 10px;
  position: relative;
}

.llm-selector-container label {
  font-weight: 500;
  color: #333;
  font-size: 0.95rem;
}

.llm-selector-container select {
  padding: 8px 12px;
  border-radius: 6px;
  border: 1px solid #ccc;
  background-color: white;
  font-size: 0.95rem;
  min-width: 220px;
  flex-grow: 1;
  transition: border-color 0.2s ease-in-out;
}
.llm-selector-container select:disabled {
    background-color: #e9ecef;
    cursor: not-allowed;
}
.llm-selector-container select:focus {
  outline: none;
  border-color: #007bff; 
  box-shadow: 0 0 0 0.2rem rgba(0,123,255,.25);
}
.llm-spinner {
  margin-left: 10px;
  width: 18px !important;
  height: 18px !important;
  border-width: 2px !important;
}
/* +++ End LLM Selector Styles +++ */

.chat-history {
  flex-grow: 1;
  overflow-y: auto;
  padding-right: 10px;
  margin-bottom: 15px;
  background-color: #f9f9f9;
  border-radius: 6px;
  border: 1px solid #e9ecef;
  padding: 15px;
}

.chat-welcome-message {
  text-align: center;
  color: #444;
  padding: 30px 20px;
  background-color: #f0f7ff;
  border-radius: 8px;
  margin: 20px auto;
  max-width: 90%;
  box-shadow: 0 2px 5px rgba(0,0,0,0.05);
}

.chat-welcome-message h3 {
  font-size: 1.4rem;
  margin-bottom: 10px;
  color: #0056b3;
}

.chat-welcome-message p {
  font-size: 1rem;
  line-height: 1.5;
}

.chat-error-display {
  margin: 10px 0;
  padding: 10px 15px;
  background-color: #fff0f0;
  border: 1px solid #ffcaca;
  border-radius: 4px;
  color: #d32f2f;
}

.chat-error-display p {
  margin: 5px 0;
}

.chat-error-display ul {
  margin: 5px 0;
  padding-left: 20px;
}

.chat-error-display li {
  margin: 3px 0;
}

.chat-input-container {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  margin-top: auto;
  padding-top: 15px;
  border-top: 1px solid #e9ecef;
}

.chat-input {
  flex-grow: 1;
  padding: 12px 15px;
  border: 1px solid #ced4da;
  border-radius: 6px;
  font-size: 1rem;
  resize: none;
  transition: border-color 0.2s ease, box-shadow 0.2s ease;
  min-height: 50px;
}
.chat-input:focus {
  outline: none;
  border-color: #007bff;
  box-shadow: 0 0 0 0.2rem rgba(0,123,255,.25);
}

.send-button {
  padding: 0 20px;
  height: 50px;
  background-color: #007bff;
  color: white;
  border: none;
  border-radius: 6px;
  font-size: 1rem;
  cursor: pointer;
  transition: background-color 0.2s ease;
  display: flex;
  align-items: center;
  justify-content: center;
}
.send-button:disabled {
  background-color: #a0cfff;
  cursor: not-allowed;
}
.send-button:hover:not(:disabled) {
  background-color: #0056b3;
}

/* Spinner for Send Button and LLM loading */
.spinner {
  width: 20px;
  height: 20px;
  border: 3px solid rgba(255, 255, 255, 0.3);
  border-radius: 50%;
  border-top-color: #fff;
  animation: spin 1s ease-in-out infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* Responsive adjustments */
@media (max-width: 992px) {
  .main-content-grid {
    grid-template-columns: 1fr;
  }
  .server-management-section, .chat-section {
    max-height: none;
    overflow-y: visible;
  }
}

@media (max-width: 768px) {
  .app-header {
    flex-direction: column;
    align-items: flex-start;
    padding: 15px;
  }
  .app-header h1 {
    margin-bottom: 10px;
  }
  .header-nav {
    width: 100%;
    display: flex;
    justify-content: flex-start;
    gap: 10px;
  }
  .header-nav .nav-button {
    margin-left: 0; 
    flex-grow: 1;
    text-align: center;
  }
  .main-content-grid {
    padding: 15px;
  }
  .server-management-section, .chat-section {
    padding: 15px;
  }
  .chat-input-container {
    flex-direction: column;
  }
  .chat-input {
    width: 100%;
    margin-bottom: 10px;
  }
  .send-button {
    width: 100%;
    height: 44px;
  }
}

/* ++ Styles for capabilities list to match server-controls page ++ */
.capabilities-list.main-page-caps {
  list-style-type: none;
  padding-left: 0;
}

.main-page-caps .capability-item {
  padding: 8px 0;
  border-bottom: 1px dashed #eee;
}

.main-page-caps .capability-item:last-child {
  border-bottom: none;
}

.main-page-caps .capability-name {
  display: block;
  font-weight: bold;
  color: #333;
  margin-bottom: 4px;
}

.main-page-caps .capability-description {
  font-size: 0.9em;
  color: #555;
  margin: 0;
  padding-left: 10px;
}

.no-capabilities-message {
    font-style: italic;
    color: #777;
    padding: 10px;
    margin-top: 5px;
}

.loading-fullscreen, .error-fullscreen {
    display: flex;
    justify-content: center;
    align-items: center;
    height: calc(100vh - 70px);
    font-size: 1.2rem;
}
.loading-fullscreen { color: #007bff; }
.error-fullscreen { color: #dc3545; }

.send-spinner {
  width: 16px;
  height: 16px;
  margin-right: 0;
}

.api-key-error {
  padding: 10px 15px;
  margin-bottom: 15px;
  background-color: #fff6f0;
  border: 1px solid #ffad99;
  border-radius: 4px;
  color: #d35400;
}

.api-key-error strong {
  font-weight: 600;
}

.api-key-error ul {
  margin: 5px 0;
  padding-left: 20px;
}

.api-key-error li {
  margin: 3px 0;
}

.error-subtle {
  padding: 5px 10px;
  color: #842029;
  background-color: #f8d7da;
  border: 1px solid #f5c2c7;
  border-radius: 4px;
  margin-bottom: 10px;
}

/* Styles for the disclaimer within the chat view */
.agent-chat-disclaimer {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0.6em 1em;
  margin: 0 auto 1em auto; /* Center horizontally, bottom margin */
  max-width: 90%; /* Adjust width as needed */
  width: fit-content; /* Shrink to content width */
  font-size: 0.8rem; /* Smaller font size */
  color: #6c757d; /* Muted text color */
  background-color: #f8f9fa; /* Very light background */
  border-radius: 6px;
  border-top: 1px solid #e9ecef; /* Subtle top border */
  text-align: center;
  flex-shrink: 0; /* Prevent shrinking */
}

.agent-chat-disclaimer .disclaimer-icon {
  margin-right: 0.5em;
  flex-shrink: 0;
}
</style> 