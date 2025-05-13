<template>
  <div class="llm-error-container" :class="errorClass">
    <div class="error-header">
      <div class="error-icon">
        <svg v-if="errorType === 'deepseek'" xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="12" cy="12" r="10"></circle>
          <line x1="12" y1="8" x2="12" y2="12"></line>
          <line x1="12" y1="16" x2="12.01" y2="16"></line>
        </svg>
        <svg v-else-if="errorType === 'ollama'" xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M5 10a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2z"></path>
          <path d="M12 12v.01"></path>
          <path d="M12 16v.01"></path>
          <path d="M16 12h.01"></path>
          <path d="M8 12h.01"></path>
          <path d="M12 8v.01"></path>
        </svg>
        <svg v-else-if="errorType === 'server'" xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <rect x="2" y="2" width="20" height="8" rx="2" ry="2"></rect>
          <rect x="2" y="14" width="20" height="8" rx="2" ry="2"></rect>
          <line x1="6" y1="6" x2="6.01" y2="6"></line>
          <line x1="6" y1="18" x2="6.01" y2="18"></line>
        </svg>
        <svg v-else xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"></polygon>
        </svg>
      </div>
      <h3>{{ title }}</h3>
    </div>
    <div class="error-content">
      <p>{{ message }}</p>
      <div v-if="showHelp" class="help-content">
        <h4>How to fix:</h4>
        <ul>
          <li v-for="(item, index) in helpItems" :key="index">{{ item }}</li>
        </ul>
      </div>
      <div v-if="fallbackInfo" class="fallback-info">
        <h4>Current status:</h4>
        <p>{{ fallbackInfo }}</p>
      </div>
    </div>
    <div v-if="actionText || showTryAgainAction" class="error-actions">
      <button v-if="actionText" @click="$emit('action-click')" class="action-button action-primary">
        {{ actionText }}
      </button>
      <button v-if="showTryAgainAction" @click="$emit('try-again')" class="action-button action-secondary">
        Try again
      </button>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue';

const props = defineProps({
  errorType: {
    type: String,
    default: 'general',
    validator: (value) => ['deepseek', 'ollama', 'server', 'general'].includes(value)
  },
  message: {
    type: String,
    required: true
  },
  actionText: {
    type: String,
    default: ''
  },
  showHelp: {
    type: Boolean,
    default: true
  },
  fallbackInfo: {
    type: String,
    default: ''
  },
  showTryAgainAction: {
    type: Boolean,
    default: false
  }
});

const emit = defineEmits(['action-click', 'try-again']);

const title = computed(() => {
  switch (props.errorType) {
    case 'deepseek':
      return 'DeepSeek API Error';
    case 'ollama':
      return 'Ollama Service Error';
    case 'server':
      return 'Server Error';
    default:
      return 'LLM Service Error';
  }
});

const errorClass = computed(() => {
  return `error-${props.errorType}`;
});

const helpItems = computed(() => {
  switch (props.errorType) {
    case 'deepseek':
      return [
        'Make sure you have set a valid DeepSeek API key in the .env file',
        'The API key should start with "sk-" and be at least 20 characters long',
        'Check your internet connection to ensure DeepSeek API is accessible',
        'If the problem persists, try using Ollama as a fallback option'
      ];
    case 'ollama':
      return [
        'Make sure Ollama is installed and running on your system',
        'Check if the Ollama service is running on the default port (11434)',
        'Try restarting the Ollama service',
        'Run "ollama pull llama3" to download a model if you haven\'t already'
      ];
    case 'server':
      return [
        'Check the server logs for specific error details',
        'Restart the application server',
        'Check if there are any environment variable issues',
        'Ensure that the server has proper internet connectivity'
      ];
    default:
      return [
        'Check your LLM configuration settings',
        'Ensure at least one LLM provider is properly configured',
        'Check server logs for detailed error information',
        'Try restarting the application'
      ];
  }
});
</script>

<style scoped>
.llm-error-container {
  border-radius: 8px;
  padding: 16px;
  margin: 16px 0;
  color: #333;
  border-left: 4px solid #f44336;
  background-color: #ffebee;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
}

.error-deepseek {
  border-left-color: #f44336;
  background-color: #ffebee;
}

.error-ollama {
  border-left-color: #ff9800;
  background-color: #fff3e0;
}

.error-server {
  border-left-color: #9c27b0;
  background-color: #f3e5f5;
}

.error-general {
  border-left-color: #2196f3;
  background-color: #e3f2fd;
}

.error-header {
  display: flex;
  align-items: center;
  margin-bottom: 12px;
}

.error-icon {
  margin-right: 12px;
  display: flex;
  align-items: center;
}

.error-deepseek .error-icon {
  color: #d32f2f;
}

.error-ollama .error-icon {
  color: #f57c00;
}

.error-server .error-icon {
  color: #7b1fa2;
}

.error-general .error-icon {
  color: #1976d2;
}

h3 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
}

.error-content p {
  margin-top: 0;
  line-height: 1.5;
}

.help-content, .fallback-info {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid rgba(0, 0, 0, 0.1);
}

.fallback-info {
  background-color: rgba(255, 255, 255, 0.5);
  padding: 8px 12px;
  border-radius: 4px;
}

h4 {
  margin: 0 0 8px 0;
  font-size: 14px;
  font-weight: 600;
}

ul {
  margin: 0;
  padding-left: 24px;
}

li {
  margin-bottom: 6px;
  font-size: 14px;
  line-height: 1.4;
}

.error-actions {
  margin-top: 16px;
  display: flex;
  gap: 12px;
}

.action-button {
  padding: 8px 16px;
  background-color: #2196f3;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-weight: 500;
  transition: background-color 0.2s;
}

.action-button:hover {
  background-color: #1976d2;
}

.action-primary {
  background-color: #2196f3;
}

.action-primary:hover {
  background-color: #1976d2;
}

.action-secondary {
  background-color: #6c757d;
}

.action-secondary:hover {
  background-color: #5a6268;
}

.error-deepseek .action-primary {
  background-color: #f44336;
}

.error-deepseek .action-primary:hover {
  background-color: #d32f2f;
}

.error-ollama .action-primary {
  background-color: #ff9800;
}

.error-ollama .action-primary:hover {
  background-color: #f57c00;
}

.error-server .action-primary {
  background-color: #9c27b0;
}

.error-server .action-primary:hover {
  background-color: #7b1fa2;
}
</style> 