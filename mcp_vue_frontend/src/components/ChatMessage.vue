<script setup lang="ts">
import { computed, type PropType, ref, onUpdated, watch, nextTick } from 'vue';
// 导入自定义的MarkdownRenderer组件代替使用Marked
import MarkdownRenderer from './MarkdownRenderer.vue';
import DOMPurify from 'dompurify';
import hljs from 'highlight.js/lib/core';
import python from 'highlight.js/lib/languages/python';
import javascript from 'highlight.js/lib/languages/javascript';
import typescript from 'highlight.js/lib/languages/typescript';
import html from 'highlight.js/lib/languages/xml';
import css from 'highlight.js/lib/languages/css';
import java from 'highlight.js/lib/languages/java';
import cpp from 'highlight.js/lib/languages/cpp';
import csharp from 'highlight.js/lib/languages/csharp';
import ruby from 'highlight.js/lib/languages/ruby';
import go from 'highlight.js/lib/languages/go';
import php from 'highlight.js/lib/languages/php';
import bash from 'highlight.js/lib/languages/bash';
import sql from 'highlight.js/lib/languages/sql';
import json from 'highlight.js/lib/languages/json';
import markdown from 'highlight.js/lib/languages/markdown';
import 'highlight.js/styles/github.css';

// Register languages
hljs.registerLanguage('python', python);
hljs.registerLanguage('javascript', javascript);
hljs.registerLanguage('js', javascript);
hljs.registerLanguage('typescript', typescript);
hljs.registerLanguage('ts', typescript);
hljs.registerLanguage('html', html);
hljs.registerLanguage('xml', html);
hljs.registerLanguage('css', css);
hljs.registerLanguage('java', java);
hljs.registerLanguage('cpp', cpp);
hljs.registerLanguage('c++', cpp);
hljs.registerLanguage('c', cpp);
hljs.registerLanguage('csharp', csharp);
hljs.registerLanguage('cs', csharp);
hljs.registerLanguage('ruby', ruby);
hljs.registerLanguage('go', go);
hljs.registerLanguage('golang', go);
hljs.registerLanguage('php', php);
hljs.registerLanguage('bash', bash);
hljs.registerLanguage('shell', bash);
hljs.registerLanguage('sh', bash);
hljs.registerLanguage('sql', sql);
hljs.registerLanguage('json', json);
hljs.registerLanguage('markdown', markdown);
hljs.registerLanguage('md', markdown);

// Minimal ChatMessage interface
interface ChatMessage {
    id: string;
    sender: 'user' | 'agent' | 'system';
    text: string;
    isGenerating?: boolean;
    isStreaming?: boolean;
    isError?: boolean;
    renderedContent?: string;
}

// Props definition
const props = defineProps({
  message: {
    type: Object as PropType<ChatMessage>,
    required: true
  }
});

// Ref for the container div
const markdownContainer = ref<typeof MarkdownRenderer | null>(null);

// Basic computed properties
const isThinking = computed(() => {
  // Only show thinking state if isGenerating is true AND there's no text
  // Force false if streaming is active to ensure we display content immediately
  console.log('[CHAT-MESSAGE] Computing isThinking:', {
    isGenerating: !!props.message?.isGenerating,
    hasText: !!props.message?.text,
    isStreaming: !!props.message?.isStreaming,
    result: !!props.message?.isGenerating && !props.message?.text && !props.message?.isStreaming
  });
  return !!props.message?.isGenerating && !props.message?.text && !props.message?.isStreaming;
});

// Get raw message text
const messageText = computed(() => {
  let text = props.message?.text || '';
  
  if (text.length > 0 && props.message?.isStreaming) {
    console.log('[CHAT-MESSAGE] Message has text while streaming:', 
      text.length > 20 ? text.substring(0, 20) + '...' : text);
  }
  
  return text;
});

// Add a computed property for displaying either accumulated content or full content
const displayContent = computed(() => {
  // Always use the text from the store
  const content = props.message?.text || '';
  if (props.message?.sender === 'agent') {
    // Log only for agent messages and only if content is present to avoid flooding
    if (content) {
      console.log('[AGENT displayContent]:', content.substring(0, 100)); 
    }
  }
  return content;
});

// Detect changes to the message text to force immediate re-render
const messageVersion = ref(0);

// Watch streaming state changes
watch(() => props.message?.isStreaming, (newVal, oldVal) => {
  console.log('[CHAT-MESSAGE] isStreaming changed:', oldVal, '->', newVal);
  
  // When streaming ends, make sure content is complete (already handled by displayContent using props.message.text)
  if (oldVal === true && newVal === false) {
    console.log('[CHAT-MESSAGE] Streaming ended, displayContent will use final props.message.text');
    messageVersion.value++; // Still increment version if MarkdownRenderer needs a nudge
  }
  
  // Force update when streaming state changes
  if (newVal !== oldVal) {
    messageVersion.value++;
  }
}, { immediate: true });

// Watch generating state changes
watch(() => props.message?.isGenerating, (newVal, oldVal) => {
  console.log('[CHAT-MESSAGE] isGenerating changed:', oldVal, '->', newVal);
  if (newVal !== oldVal) {
    messageVersion.value++;
  }
}, { immediate: true });

// Watch for direct changes to props.message.text to increment messageVersion
// This ensures that MarkdownRenderer is re-evaluated if it depends on messageVersion or a key change.
watch(() => props.message?.text, () => {
    console.log('[CHAT-MESSAGE] props.message.text changed, incrementing messageVersion.');
    messageVersion.value++;
}, { immediate: true });

// Helper to escape markdown characters in streaming mode
function escapeMarkdownChars(text: string): string {
  // 不再转义Markdown语法，允许直接渲染
  return text;
}

// Function to add language tags and copy buttons
function enhanceCodeBlocks() {
  // MarkdownRenderer组件已经处理了代码块增强
  console.log("Code block enhancement handled by MarkdownRenderer");
}

// Run the enhancement function whenever the component updates
onUpdated(() => {
  // MarkdownRenderer组件自动处理这些功能
});

console.log('[ChatMessage] Message prop received:', JSON.parse(JSON.stringify(props.message)));

</script>

<template>
  <div class="chat-message" :class="[
    `chat-message-${props.message.sender === 'user' ? 'user' : 'agent'}`,
    { 'chat-message-thinking': isThinking },
    { 'message-error': props.message.isError }
  ]">
    <div class="avatar" :class="{ 'avatar-thinking': isThinking }">
       <span v-if="props.message.isError">⚠️</span>
       <span v-else>{{ props.message.sender === 'user' ? '👤' : '🤖' }}</span>
    </div>
    <div class="message-content-wrapper">
      <div class="message-header">
        <div class="sender-label">
             <span v-if="props.message.isError">Error</span>
             <span v-else>{{ props.message.sender === 'user' ? 'You' : 'Agent' }}</span>
             <!-- Always show streaming badge if streaming -->
             <span v-if="props.message.isStreaming" class="streaming-badge">streaming</span>
             <!-- Show connection error indicator if needed -->
             <span v-if="messageText.includes('[Connection error detected')">⚠️</span>
        </div>
      </div>
       <div :class="{ 'thinking-bg': isThinking }"> 
          <!-- Thinking indicator (only show if explicitly in thinking state and no text) -->
          <div v-if="isThinking" class="thinking-indicator">
            <span>Thinking</span>
            <span class="thinking-dots"><span>.</span><span>.</span><span>.</span></span>
          </div>
          
          <!-- 自定义组件用于渲染Markdown -->
          <markdown-renderer 
            v-else 
            :initialMarkdown="displayContent" 
            ref="markdownContainer" 
            class="markdown-content"
          />
          
          <!-- 流式光标 -->
          <span v-if="props.message.isStreaming" class="streaming-cursor">▌</span>
       </div>
    </div>
  </div>
</template>

<style scoped>
/* Keep existing styles - they shouldn't cause compile errors */
.chat-message {
  display: flex;
  margin-bottom: 15px;
  max-width: 85%;
  position: relative;
  animation: fadeIn 0.3s ease;
  user-select: none; /* Prevent selecting the whole bubble */
}

.chat-message-user {
  align-self: flex-end;
  flex-direction: row-reverse;
  max-width: 80%;
}

.chat-message-thinking {
  /* Style for the thinking state container if needed */
}

.avatar {
  font-size: 1.5em;
  margin-right: 10px;
  margin-top: 5px;
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  flex-shrink: 0;
}

.avatar-thinking {
  opacity: 0.6;
}

.chat-message-user .avatar {
  margin-right: 0;
  margin-left: 10px;
}

.message-content-wrapper {
  flex: 1;
  max-width: 100%;
  min-width: 0; /* Prevent overflow */
  background-color: #f0f0f0; /* Example: agent bubble color */
  padding: 10px 15px;
  border-radius: 15px;
  flex-grow: 1;
}

.message-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.sender-label {
  font-weight: 600;
  font-size: 0.9em;
}

.streaming-indicator {
  font-size: 0.75em;
  color: #888;
  background-color: #f2f2f2;
  padding: 2px 6px;
  border-radius: 8px;
  animation: pulse 1.4s infinite ease-in-out;
}

/* Style user messages */
.chat-message-user .message-content-wrapper {
  background-color: #007bff; /* Example: user bubble color */
  color: white;
}

.chat-message-agent .message-content-wrapper {
  background-color: #f8f9fa; /* Very light grey background */
  color: #343a40; /* Dark grey text */
}

/* Override MarkdownRenderer color if necessary within agent bubble */
.chat-message-agent .message-content-wrapper :deep(.markdown-content) {
  color: #343a40; /* Ensure markdown text matches agent bubble text color */
}

/* Thinking indicator styles */
.thinking-indicator {
  display: flex;
  align-items: center;
  padding: 6px 0;
  color: #555; /* Adjust color as needed */
}

.thinking-dots {
  display: inline-flex; /* Use inline-flex */
  align-items: center;
  gap: 2px; /* Adjust gap */
  margin-left: 4px;
}

.thinking-dots span {
  height: 6px; /* Smaller dots */
  width: 6px;
  background-color: #6169e6;
  border-radius: 50%;
  display: inline-block;
  animation: pulse 1.4s infinite ease-in-out;
}

.thinking-dots span:nth-child(2) {
  animation-delay: 0.2s;
}

.thinking-dots span:nth-child(3) {
  animation-delay: 0.4s;
}

/* This class is now on the div displaying text */
.markdown-content {
  /* Ensure this takes up space and any specific styles for markdown rendering itself */
  word-break: break-word;
  overflow-wrap: break-word;
  /* Remove any background/padding if it creates an inner box effect */
  background-color: transparent !important; /* Override if necessary */
  padding: 0 !important; /* Override if necessary */
}

/* Adjust thinking-bg if it was creating an inner box */
.thinking-bg {
  background-color: transparent !important; /* Make it transparent */
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}

@keyframes pulse {
  0%, 100% {
    transform: scale(0.6);
    opacity: 0.6;
  }
  50% {
    transform: scale(1);
    opacity: 1;
  }
}

.streaming-badge {
  font-size: 0.75em;
  color: #888;
  background-color: #f2f2f2;
  padding: 2px 6px;
  border-radius: 8px;
  margin-left: 8px;
  animation: pulse 1.4s infinite ease-in-out;
}

.streaming-cursor {
  display: inline-block;
  animation: blink 1s step-end infinite;
  font-weight: normal;
  opacity: 0.7;
  margin-left: 1px;
}

@keyframes blink {
  0%, 100% { opacity: 0; }
  50% { opacity: 1; }
}
</style>
