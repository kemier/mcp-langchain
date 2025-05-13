<template>
  <div class="websocket-test-container">
    <h2>WebSocket Streaming Test</h2>
    
    <div class="test-controls">
      <div class="input-group">
        <label for="test-message">Test Message (optional):</label>
        <input 
          id="test-message" 
          v-model="testMessage" 
          type="text" 
          placeholder="Enter a custom message to stream"
        />
      </div>
      
      <div class="input-group">
        <label for="delay-ms">Token Delay (ms):</label>
        <input 
          id="delay-ms" 
          v-model.number="delayMs" 
          type="number" 
          min="10" 
          max="1000"
        />
      </div>
      
      <button 
        class="test-button" 
        @click="runTest" 
        :disabled="isStreaming"
      >
        {{ isStreaming ? 'Streaming...' : 'Start Test Stream' }}
      </button>
      
      <div class="direct-websocket-controls">
        <button 
          class="websocket-button" 
          @click="connectDirectWebSocket"
          :disabled="socket && (socket.readyState === 1 || socket.readyState === 0)"
        >
          Connect WebSocket Directly
        </button>
        
        <button 
          class="websocket-button disconnect" 
          @click="disconnectWebSocket"
          :disabled="!socket || socket.readyState !== 1"
        >
          Disconnect WebSocket
        </button>
      </div>
    </div>
    
    <div class="stream-output-container">
      <h3>Stream Output:</h3>
      <div 
        class="stream-output" 
        ref="outputContainer" 
      >
        <span v-if="!streamedText">No stream data yet. Click "Start Test Stream" to begin.</span>
        <span v-else>{{ streamedText }}</span>
      </div>
    </div>
    
    <div class="connection-status">
      <h3>WebSocket Status:</h3>
      <div class="status-indicator" :class="connectionStatusClass">
        {{ connectionStatus }}
      </div>
    </div>
    
    <div class="debug-info">
      <h3>Debug Info:</h3>
      <div class="log-container">
        <div v-for="(log, index) in logs" :key="index" class="log-entry">
          <span class="timestamp">{{ log.timestamp }}</span>
          <span class="event-type" :class="log.type">{{ log.type }}</span>
          <span class="event-message">{{ log.message }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { API_BASE_URL, WS_BASE_URL, streamTextGenerationObservable, sendDebugLog } from '../services/apiService';

export default {
  name: 'WebSocketTestComponent',
  
  data() {
    return {
      testMessage: 'Hello! This is a test of WebSocket streaming with Chinese characters: 你好，这是一个测试。',
      delayMs: 100,
      streamedText: '',
      isStreaming: false,
      logs: [],
      streamSubscription: null,
      socket: null,
      connectionStatus: 'Disconnected',
      connectionStatusClass: 'disconnected'
    };
  },
  
  methods: {
    logEvent(type, message) {
      const timestamp = new Date().toISOString().split('T')[1].slice(0, 12);
      this.logs.unshift({ timestamp, type, message });
      
      // Limit log entries
      if (this.logs.length > 50) {
        this.logs.pop();
      }
    },
    
    async runTest() {
      if (this.isStreaming) return;
      
      this.isStreaming = true;
      this.streamedText = '';
      this.logs = [];
      
      const sessionId = `test-${Date.now()}`;
      
      try {
        this.logEvent('info', 'Starting WebSocket test stream...');
        
        // Option 1: Use our standard WebSocket streaming via the API service
        this.streamSubscription = streamTextGenerationObservable(
          sessionId,         // session ID
          this.testMessage,  // prompt 
          {},                // tools_config
          null,              // llm_config_id
          API_BASE_URL,      // base URL
          true               // enable debug mode
        ).subscribe({
          next: (event) => {
            console.log('[WS-TEST] Received event:', event);
            
            // Emergency fallback for non-standard formats
            if (!event || (!event.type && !event.data)) {
              let rawContent = '';
              if (typeof event === 'string') {
                rawContent = event;
                this.logEvent('raw', `Received raw string: "${rawContent.substring(0, 30)}${rawContent.length > 30 ? '...' : ''}"`);
              } else if (typeof event === 'object') {
                try {
                  rawContent = JSON.stringify(event);
                  this.logEvent('raw', `Received raw object, stringified: "${rawContent.substring(0, 30)}${rawContent.length > 30 ? '...' : ''}"`);
                } catch (e) {
                  this.logEvent('error', `Received unprocessable object: ${e.message}`);
                  rawContent = String(event);
                }
              } else {
                rawContent = String(event);
                this.logEvent('raw', `Received raw content (${typeof event}): "${rawContent}"`);
              }
              
              if (rawContent) {
                this.streamedText += rawContent;
                
                // Scroll to bottom of output container
                this.$nextTick(() => {
                  if (this.$refs.outputContainer) {
                    this.$refs.outputContainer.scrollTop = this.$refs.outputContainer.scrollHeight;
                  }
                });
              }
              return;
            }
            
            if (event.type === 'token') {
              const tokenText = typeof event.data === 'string' ? event.data : JSON.stringify(event.data);
              this.streamedText += tokenText;
              this.logEvent('token', `Received token (${tokenText.length} chars): "${tokenText.substring(0, 20)}${tokenText.length > 20 ? '...' : ''}"`);
            } else if (event.type === 'info') {
              const infoText = typeof event.data === 'string' ? event.data : JSON.stringify(event.data);
              this.logEvent('info', `Received info event: ${infoText.substring(0, 50)}${infoText.length > 50 ? '...' : ''}`);
            } else if (event.type === 'final' || event.type === 'on_chain_end') {
              const finalText = typeof event.data === 'string' ? event.data : 
                (event.data && event.data.content) ? event.data.content : JSON.stringify(event.data);
              this.streamedText += '\n\n[FINAL: ' + finalText + ']';
              this.logEvent('complete', `Received final event: ${finalText.substring(0, 50)}${finalText.length > 50 ? '...' : ''}`);
              this.isStreaming = false;
            } else if (event.type === 'error_event') {
              const errorMsg = typeof event.data === 'string' ? event.data : JSON.stringify(event.data);
              this.logEvent('error', `Received error event: ${errorMsg}`);
              this.isStreaming = false;
            } else if (event.type === 'raw') {
              // Handle raw data
              const rawText = typeof event.data === 'string' ? event.data : JSON.stringify(event.data);
              this.streamedText += rawText;
              this.logEvent('raw', `Received raw data (${rawText.length} chars): "${rawText.substring(0, 30)}${rawText.length > 30 ? '...' : ''}"`);
            } else {
              this.logEvent('info', `Received unknown event type: ${event.type}`);
            }
            
            // Scroll to bottom of output container
            this.$nextTick(() => {
              if (this.$refs.outputContainer) {
                this.$refs.outputContainer.scrollTop = this.$refs.outputContainer.scrollHeight;
              }
            });
          },
          error: (error) => {
            this.logEvent('error', `Stream error: ${error.message}`);
            this.isStreaming = false;
            sendDebugLog('websocket-test-component', 'stream_error', {
              sessionId,
              error: error.message,
              errorObj: JSON.stringify(error)
            });
          },
          complete: () => {
            this.logEvent('complete', 'Stream completed successfully');
            this.isStreaming = false;
            sendDebugLog('websocket-test-component', 'stream_complete', {
              sessionId,
              messageLength: this.streamedText.length
            });
          }
        });
      } catch (error) {
        this.logEvent('error', `Failed to start stream: ${error.message}`);
        this.isStreaming = false;
      }
    },
    
    // Direct WebSocket connection for testing the raw connection
    connectDirectWebSocket() {
      if (this.socket && (this.socket.readyState === WebSocket.OPEN || this.socket.readyState === WebSocket.CONNECTING)) {
        this.logEvent('info', 'Already connected or connecting to WebSocket');
        return;
      }
      
      // Build proper WebSocket URL - use the server's test-ws endpoint
      let wsUrl = '';
      if (window.location.protocol === 'https:') {
        wsUrl = `wss://${window.location.host}/ws/test-ws`;
      } else {
        wsUrl = `ws://${window.location.host}/ws/test-ws`;
      }
      
      this.logEvent('info', `Connecting to WebSocket at ${wsUrl}`);
      this.connectionStatus = 'Connecting...';
      this.connectionStatusClass = 'connecting';
      
      try {
        this.socket = new WebSocket(wsUrl);
        
        this.socket.onopen = () => {
          this.logEvent('info', 'WebSocket connection established');
          this.connectionStatus = 'Connected';
          this.connectionStatusClass = 'connected';
          
          // Send a test message
          const message = {
            type: 'test',
            message: this.testMessage,
            session_id: `direct-${Date.now()}`
          };
          
          this.socket.send(JSON.stringify(message));
          this.logEvent('info', `Sent test message: ${JSON.stringify(message)}`);
        };
        
        this.socket.onmessage = (event) => {
          const data = event.data;
          this.logEvent('message', `Received message: ${data.substring(0, 100)}${data.length > 100 ? '...' : ''}`);
          
          try {
            const parsedData = JSON.parse(data);
            if (parsedData.type === 'token') {
              this.streamedText += parsedData.data || '';
            } else if (parsedData.type === 'info') {
              // Just log info events
            } else if (parsedData.type === 'error') {
              this.logEvent('error', `WebSocket error: ${parsedData.message || 'Unknown error'}`);
            }
          } catch (e) {
            // Handle plain text data
            this.streamedText += data;
          }
          
          // Scroll to bottom of output container
          this.$nextTick(() => {
            if (this.$refs.outputContainer) {
              this.$refs.outputContainer.scrollTop = this.$refs.outputContainer.scrollHeight;
            }
          });
        };
        
        this.socket.onerror = (error) => {
          this.logEvent('error', `WebSocket error: ${error}`);
          this.connectionStatus = 'Error';
          this.connectionStatusClass = 'error';
        };
        
        this.socket.onclose = (event) => {
          const reason = event.reason ? ` Reason: ${event.reason}` : '';
          this.logEvent('info', `WebSocket connection closed. Code: ${event.code}.${reason}`);
          this.connectionStatus = 'Disconnected';
          this.connectionStatusClass = 'disconnected';
        };
      } catch (error) {
        this.logEvent('error', `Failed to connect to WebSocket: ${error.message}`);
        this.connectionStatus = 'Connection Failed';
        this.connectionStatusClass = 'error';
      }
    },
    
    disconnectWebSocket() {
      if (this.socket) {
        this.socket.close(1000, 'User closed connection');
        this.socket = null;
        this.logEvent('info', 'WebSocket connection closed by user');
      }
    }
  },
  
  beforeUnmount() {
    // Clean up any active subscription
    if (this.streamSubscription) {
      this.streamSubscription.unsubscribe();
    }
    
    // Close any direct WebSocket connection
    this.disconnectWebSocket();
  }
};
</script>

<style scoped>
.websocket-test-container {
  max-width: 800px;
  margin: 0 auto;
  padding: 20px;
  font-family: Arial, sans-serif;
}

.test-controls {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-bottom: 20px;
  padding: 15px;
  background-color: #f5f5f5;
  border-radius: 5px;
}

.input-group {
  display: flex;
  flex-direction: column;
  gap: 5px;
}

label {
  font-weight: bold;
}

input {
  padding: 8px;
  border: 1px solid #ccc;
  border-radius: 4px;
}

.test-button {
  padding: 10px 15px;
  background-color: #4CAF50;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-weight: bold;
  margin-top: 10px;
}

.test-button:disabled {
  background-color: #cccccc;
  cursor: not-allowed;
}

.stream-output-container {
  margin-bottom: 20px;
}

.stream-output {
  padding: 15px;
  border: 1px solid #ddd;
  border-radius: 5px;
  background-color: #f9f9f9;
  min-height: 100px;
  max-height: 300px;
  overflow-y: auto;
  white-space: pre-wrap;
  word-break: break-word;
}

.connection-status {
  margin-bottom: 20px;
}

.status-indicator {
  display: inline-block;
  padding: 6px 12px;
  border-radius: 4px;
  font-weight: bold;
}

.status-indicator.disconnected {
  background-color: #f5f5f5;
  color: #666;
}

.status-indicator.connecting {
  background-color: #FFF9C4;
  color: #FF8F00;
}

.status-indicator.connected {
  background-color: #E8F5E9;
  color: #2E7D32;
}

.status-indicator.error {
  background-color: #FFEBEE;
  color: #D32F2F;
}

.debug-info {
  margin-top: 20px;
}

.log-container {
  max-height: 300px;
  overflow-y: auto;
  border: 1px solid #ddd;
  border-radius: 5px;
  background-color: #f9f9f9;
}

.log-entry {
  padding: 8px;
  font-family: monospace;
  border-bottom: 1px solid #eee;
  display: flex;
  gap: 10px;
}

.timestamp {
  color: #888;
  min-width: 100px;
}

.event-type {
  font-weight: bold;
  min-width: 80px;
}

.info {
  color: #2196F3;
}

.token {
  color: #4CAF50;
}

.raw {
  color: #FF9800;
}

.error {
  color: #F44336;
}

.complete {
  color: #9C27B0;
}

.message {
  color: #00BCD4;
}

h2, h3 {
  color: #333;
}

.direct-websocket-controls {
  display: flex;
  gap: 10px;
  margin-top: 10px;
}

.websocket-button {
  padding: 10px 15px;
  background-color: #4CAF50;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-weight: bold;
}

.websocket-button:disabled {
  background-color: #cccccc;
  cursor: not-allowed;
}

.websocket-button.disconnect {
  background-color: #F44336;
}
</style> 