import { createStore } from 'vuex';
import { type ChatMessage } from '../services/apiService';
import createPersistedState from 'vuex-persistedstate';

interface StreamingChunk {
  id: string;
  content: string;
  messageId: string;
}

interface State {
  streamingChunks: Record<string, StreamingChunk[]>;
  chatHistory: ChatMessage[];
  processingIds: Set<string>;
}

// Define a type for Vuex state to use in getters and mutations
type VuexState = State & {
  streamingChunks: {
    [key: string]: StreamingChunk[];
  };
};

// Define the type for commit (to fix "any" typing issues)
type CommitFunction = (type: string, payload?: any) => void;

export default createStore({
  state: {
    streamingChunks: {},    // Maps messageId -> array of chunks
    chatHistory: [],         // Stores the complete chat history
    processingIds: new Set() // Track which messages are being processed to avoid duplication
  } as State,
  
  plugins: [createPersistedState({
    key: 'mcp-chat-app',
    paths: ['chatHistory']
  })],
  
  getters: {
    getMessageChunks: (state: VuexState) => (messageId: string): StreamingChunk[] => {
      return state.streamingChunks[messageId] || [];
    },
    
    getChatHistory: (state: VuexState): ChatMessage[] => {
      return state.chatHistory;
    },
    
    isProcessing: (state: VuexState) => (chunkId: string): boolean => {
      return state.processingIds.has(chunkId);
    }
  },
  
  mutations: {
    ADD_CHAT_MESSAGE(state: VuexState, message: ChatMessage): void {
      // Initialize an empty array for this message's chunks if not exists
      if (message.id && !state.streamingChunks[message.id]) {
        state.streamingChunks[message.id] = [];
      }
      
      // Add message to chat history
      state.chatHistory.push(message);
    },
    
    ADD_STREAMING_CHUNK(state: VuexState, { messageId, chunk, chunkId }: { messageId: string, chunk: string, chunkId: string }): void {
      // Check if this chunk is already being processed to avoid duplication
      if (state.processingIds.has(chunkId)) {
        console.log(`[STORE] Skipping duplicate chunk: ${chunkId}`);
        return;
      }
      
      // Mark as processing
      state.processingIds.add(chunkId);
      
      // Ensure the message's chunks array exists
      if (!state.streamingChunks[messageId]) {
        state.streamingChunks[messageId] = [];
      }
      
      // Add the new chunk
      state.streamingChunks[messageId].push({
        id: chunkId,
        content: chunk,
        messageId
      });
      
      // Update the message text in chat history
      const messageIndex = state.chatHistory.findIndex((msg: ChatMessage) => msg.id === messageId);
      if (messageIndex !== -1) {
        // Combine all chunks to form the complete text
        const allChunks = state.streamingChunks[messageId].map((c: StreamingChunk) => c.content).join('');
        
        // Update the message
        state.chatHistory[messageIndex] = {
          ...state.chatHistory[messageIndex],
          text: allChunks,
          isStreaming: true,
          isGenerating: false
        };
      }
    },
    
    FINISH_STREAMING(state: VuexState, messageId: string): void {
      // Find the message
      const messageIndex = state.chatHistory.findIndex((msg: ChatMessage) => msg.id === messageId);
      if (messageIndex !== -1) {
        // Update streaming status
        state.chatHistory[messageIndex].isStreaming = false;
      }
    },
    
    CLEAR_PROCESSED_CHUNKS(state: VuexState, messageId: string): void {
      // Clear processing IDs for this message
      if (state.streamingChunks[messageId]) {
        state.streamingChunks[messageId].forEach((chunk: StreamingChunk) => {
          state.processingIds.delete(chunk.id);
        });
      }
      
      // Clean up the chunks array to free memory
      // You can choose to keep it if needed for other purposes
      delete state.streamingChunks[messageId];
    },

    UPDATE_MESSAGE_CONTENT(state: VuexState, { messageId, content }: { messageId: string, content: string }): void {
      const messageIndex = state.chatHistory.findIndex((msg: ChatMessage) => msg.id === messageId);
      if (messageIndex !== -1) {
        state.chatHistory[messageIndex] = {
          ...state.chatHistory[messageIndex],
          text: content,
          isStreaming: false,
          isGenerating: false
        };
      }
    },

    UPDATE_MESSAGE_ERROR(state: VuexState, { messageId, error }: { messageId: string, error: string }): void {
      const messageIndex = state.chatHistory.findIndex((msg: ChatMessage) => msg.id === messageId);
      if (messageIndex !== -1) {
        state.chatHistory[messageIndex] = {
          ...state.chatHistory[messageIndex],
          text: `Error: ${error}`,
          isStreaming: false,
          isGenerating: false,
          isError: true
        };
      }
    },

    APPEND_MESSAGE_CONTENT(state: VuexState, { messageId, content }: { messageId: string, content: string }): void {
      const messageIndex = state.chatHistory.findIndex((msg: ChatMessage) => msg.id === messageId);
      if (messageIndex !== -1) {
        const currentText = state.chatHistory[messageIndex].text || '';
        state.chatHistory[messageIndex] = {
          ...state.chatHistory[messageIndex],
          text: currentText + content,
          isStreaming: true,
          isGenerating: false
        };
      }
    }
  },
  
  actions: {
    addChatMessage({ commit }: { commit: CommitFunction }, message: ChatMessage): void {
      commit('ADD_CHAT_MESSAGE', message);
    },
    
    processStreamingToken({ commit }: { commit: CommitFunction }, { messageId, token }: { messageId: string, token: string }): void {
      // Generate a unique ID for this chunk
      const chunkId = `${messageId}-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;
      
      // Add the chunk to the store
      commit('ADD_STREAMING_CHUNK', {
        messageId,
        chunk: token,
        chunkId
      });
    },
    
    finishStreaming({ commit }: { commit: CommitFunction }, messageId: string): void {
      commit('FINISH_STREAMING', messageId);
      commit('CLEAR_PROCESSED_CHUNKS', messageId);
    },

    // Add missing actions that are used in ServerManagementView.vue
    processFinalContent({ commit }: { commit: CommitFunction }, { messageId, content }: { messageId: string, content: string }): void {
      commit('UPDATE_MESSAGE_CONTENT', { messageId, content });
      commit('FINISH_STREAMING', messageId);
      commit('CLEAR_PROCESSED_CHUNKS', messageId);
    },

    processError({ commit }: { commit: CommitFunction }, { messageId, error }: { messageId: string, error: string }): void {
      commit('UPDATE_MESSAGE_ERROR', { messageId, error });
      commit('FINISH_STREAMING', messageId);
      commit('CLEAR_PROCESSED_CHUNKS', messageId);
    },

    processOtherEvent({ commit }: { commit: CommitFunction }, { messageId, content }: { messageId: string, content: string }): void {
      commit('APPEND_MESSAGE_CONTENT', { messageId, content });
    },

    processWebSocketEvent({ commit }: { commit: CommitFunction }, { messageId, event }: { messageId: string, event: any }): void {
      // Process WebSocket events - extract content from event and append to message
      let content = '';
      
      if (typeof event === 'string') {
        content = event;
      } else if (event && typeof event === 'object') {
        if (event.data) {
          content = typeof event.data === 'string' ? event.data : JSON.stringify(event.data);
        } else if (event.type === 'token' && event.content) {
          content = event.content;
        } else {
          content = JSON.stringify(event);
        }
      }
      
      if (content.trim()) {
        commit('APPEND_MESSAGE_CONTENT', { messageId, content });
      }
    }
  }
}); 