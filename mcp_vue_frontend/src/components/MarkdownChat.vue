<template>
  <div class="markdown-chat-container">
    <div class="chat-header">
      <h2>Markdown 聊天示例</h2>
    </div>
    
    <div class="chat-messages" ref="chatMessages">
      <div v-for="(message, index) in messages" :key="index" class="message-container" :class="message.sender">
        <div class="message-header">
          <strong>{{ getSenderName(message.sender) }}</strong>
          <span class="message-time">{{ formatTime(message.timestamp) }}</span>
        </div>
        
        <markdown-renderer 
          v-if="message.sender === 'agent'"
          :initialMarkdown="message.content" 
          :streamEndpoint="message.isStreaming ? wsEndpoint : ''"
          :streamPayload="message.payload"
          :debugMode="true"
          @content-update="onContentUpdate(index, $event)"
          @stream-error="onStreamError(index, $event)"
          @stream-complete="onStreamComplete(index, $event)"
        />
        
        <markdown-renderer 
          v-else-if="message.sender === 'user'"
          :initialMarkdown="message.content"
          :debugMode="false"
        />
        
        <div v-else class="user-message">
          {{ message.content }}
        </div>
      </div>
      
      <div v-if="isAgentTyping" class="message-container agent typing-indicator">
        <div class="typing-dots">
          <span></span>
          <span></span>
          <span></span>
        </div>
      </div>
    </div>
    
    <div class="chat-input">
      <textarea 
        v-model="userInput" 
        placeholder="输入你的消息（支持Markdown语法）..." 
        @keydown.enter.prevent="sendMessage"
        :disabled="isWaitingForResponse"
      ></textarea>
      <button @click="sendMessage" :disabled="isWaitingForResponse || !userInput.trim()">
        发送
      </button>
    </div>
  </div>
</template>

<script>
import MarkdownRenderer from './MarkdownRenderer.vue';
import { streamService } from '@/services/streamService';

export default {
  name: 'MarkdownChat',
  components: {
    MarkdownRenderer
  },
  data() {
    return {
      wsEndpoint: `ws://${window.location.hostname}:8010/ws/chat`,
      userInput: '',
      messages: [],
      isWaitingForResponse: false,
      isAgentTyping: false,
      currentSessionId: null
    };
  },
  mounted() {
    // Add a welcome message
    this.messages.push({
      sender: 'agent',
      content: '# 欢迎使用 Markdown 聊天！\n\n我可以处理各种 Markdown 格式，包括：\n\n* **粗体文本**\n* *斜体文本*\n* `代码片段`\n* 表格\n* 等等...\n\n```python\ndef hello_world():\n    print("Hello, world!")\n```\n\n请输入您的问题，也可以**使用Markdown语法**！',
      timestamp: new Date(),
      isStreaming: false
    });
  },
  methods: {
    sendMessage() {
      if (!this.userInput.trim() || this.isWaitingForResponse) return;
      
      // Add user message
      this.messages.push({
        sender: 'user',
        content: this.userInput,
        timestamp: new Date()
      });
      
      // Prepare for agent response
      this.isWaitingForResponse = true;
      this.isAgentTyping = true;
      
      // Save the input and clear it
      const userMessage = this.userInput;
      this.userInput = '';
      
      // Scroll to bottom
      this.$nextTick(() => {
        this.scrollToBottom();
      });
      
      // Generate session ID for this conversation
      this.currentSessionId = 'chat-' + Date.now();
      
      // Prepare payload for the agent
      const payload = {
        prompt: userMessage,
        session_id: this.currentSessionId,
        tools_config: {},
        agent_mode: 'chat'
      };
      
      // Add a placeholder for agent response that will be streamed
      const messageIndex = this.messages.length;
      this.messages.push({
        sender: 'agent',
        content: '',
        timestamp: new Date(),
        isStreaming: true,
        payload: payload
      });
      
      // Scroll to the typing indicator
      this.$nextTick(() => {
        this.scrollToBottom();
      });
    },
    
    onContentUpdate(messageIndex, content) {
      // The MarkdownRenderer will handle updating its own content,
      // but we might want to save the updated content to our message object
      if (messageIndex >= 0 && messageIndex < this.messages.length) {
        this.messages[messageIndex].content = content;
      }
      
      // Scroll to show the latest content
      this.$nextTick(() => {
        this.scrollToBottom();
      });
    },
    
    onStreamError(messageIndex, error) {
      console.error('Stream error:', error);
      this.isWaitingForResponse = false;
      this.isAgentTyping = false;
      
      // Add error information to the message if needed
      if (messageIndex >= 0 && messageIndex < this.messages.length) {
        this.messages[messageIndex].error = error;
      }
    },
    
    onStreamComplete(messageIndex, data) {
      console.log('[MARKDOWN CHAT] onStreamComplete received data:', JSON.parse(JSON.stringify(data)));

      this.isWaitingForResponse = false;
      this.isAgentTyping = false;
      
      if (messageIndex >= 0 && messageIndex < this.messages.length) {
        this.messages[messageIndex].isStreaming = false;
        if (data && data.content) { 
          this.messages[messageIndex].content = data.content;
          console.log(`[MARKDOWN CHAT] Updated message ${messageIndex} content to:`, data.content);
        } else {
          console.warn(`[MARKDOWN CHAT] onStreamComplete: data.content is missing or empty. Data:`, JSON.parse(JSON.stringify(data)));
        }
      }
    },
    
    getSenderName(sender) {
      return sender === 'user' ? '你' : 'AI 助手';
    },
    
    formatTime(timestamp) {
      if (!timestamp) return '';
      
      const date = new Date(timestamp);
      return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    },
    
    scrollToBottom() {
      if (this.$refs.chatMessages) {
        this.$refs.chatMessages.scrollTop = this.$refs.chatMessages.scrollHeight;
      }
    }
  }
};
</script>

<style scoped>
.markdown-chat-container {
  display: flex;
  flex-direction: column;
  height: 100%;
  max-height: 800px;
  border-radius: 8px;
  border: 1px solid #e1e4e8;
  background-color: #fff;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.1);
}

.chat-header {
  padding: 1rem;
  border-bottom: 1px solid #e1e4e8;
  background-color: #f6f8fa;
  border-radius: 8px 8px 0 0;
}

.chat-header h2 {
  margin: 0;
  font-size: 1.25rem;
  color: #24292e;
}

.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 1rem;
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.message-container {
  max-width: 80%;
  border-radius: 8px;
  padding: 0.5rem;
  position: relative;
}

.message-container.user {
  align-self: flex-end;
  background-color: #e1f5fe;
  border-bottom-right-radius: 0;
}

.message-container.agent {
  align-self: flex-start;
  background-color: #f5f5f5;
  border-bottom-left-radius: 0;
}

.message-header {
  font-size: 0.8rem;
  margin-bottom: 0.5rem;
  display: flex;
  justify-content: space-between;
}

.message-time {
  color: #6a737d;
}

.user-message {
  white-space: pre-wrap;
  word-break: break-word;
}

.typing-indicator {
  padding: 1rem;
  max-width: 5rem;
}

.typing-dots {
  display: flex;
  justify-content: center;
  align-items: center;
  height: 1.5rem;
}

.typing-dots span {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background-color: #6a737d;
  margin: 0 2px;
  animation: typing-dot 1.4s infinite ease-in-out both;
}

.typing-dots span:nth-child(1) {
  animation-delay: 0s;
}

.typing-dots span:nth-child(2) {
  animation-delay: 0.2s;
}

.typing-dots span:nth-child(3) {
  animation-delay: 0.4s;
}

@keyframes typing-dot {
  0%, 80%, 100% { 
    transform: scale(0.6);
    opacity: 0.6;
  }
  40% { 
    transform: scale(1);
    opacity: 1;
  }
}

.chat-input {
  padding: 1rem;
  border-top: 1px solid #e1e4e8;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.chat-input textarea {
  flex: 1;
  min-height: 40px;
  max-height: 120px;
  padding: 0.5rem;
  border: 1px solid #e1e4e8;
  border-radius: 4px;
  resize: vertical;
  font-family: inherit;
}

.chat-input button {
  background-color: #2196f3;
  color: white;
  border: none;
  border-radius: 4px;
  padding: 0.5rem 1rem;
  cursor: pointer;
  font-weight: bold;
  height: 40px;
}

.chat-input button:hover:not(:disabled) {
  background-color: #1976d2;
}

.chat-input button:disabled {
  background-color: #e1e4e8;
  cursor: not-allowed;
  color: #6a737d;
}

/* 修改用户消息的样式，确保Markdown内容显示正确 */
.message-container.user .markdown-content {
  color: #000;
}

.message-container.user pre,
.message-container.user code {
  background-color: rgba(0, 0, 0, 0.05);
}
</style> 