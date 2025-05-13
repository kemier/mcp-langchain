<script setup>
import { ref, computed, onMounted } from 'vue';
import hljs from 'highlight.js';
import 'highlight.js/styles/atom-one-dark.css';

const props = defineProps({
  code: { type: String, required: true },
  language: { type: String, default: '' },
  isGenerating: { type: Boolean, default: false }
});

const copied = ref(false);
const codeId = `code-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;

// Detect language if not provided
const detectedLanguage = computed(() => {
  if (props.language) {
    return props.language.toLowerCase();
  }
  
  // Auto-detect language if not specified
  try {
    const result = hljs.highlightAuto(props.code, [
      'python', 'javascript', 'typescript', 'json', 'html', 'css', 'bash', 'shell'
    ]);
    return result.language || 'plaintext';
  } catch (e) {
    console.error('Error detecting language:', e);
    return 'plaintext';
  }
});

const displayLanguage = computed(() => {
  const lang = detectedLanguage.value;
  return lang.charAt(0).toUpperCase() + lang.slice(1);
});

const highlightedCode = computed(() => {
  try {
    if (detectedLanguage.value === 'plaintext') {
      return props.code;
    }
    const result = hljs.highlight(props.code, { 
      language: detectedLanguage.value
    });
    return result.value;
  } catch (e) {
    console.error('Error highlighting code:', e);
    return props.code;
  }
});

function copyCode() {
  navigator.clipboard.writeText(props.code);
  copied.value = true;
  setTimeout(() => {
    copied.value = false;
  }, 2000);
}

// Function to generate a random filename
function generateRandomString(length = 3, lowercase = true) {
  const chars = "ABCDEFGHJKLMNPQRSTUVWXY3456789"; // excluding similar looking characters
  let result = "";
  for (let i = 0; i < length; i++) {
    result += chars.charAt(Math.floor(Math.random() * chars.length));
  }
  return lowercase ? result.toLowerCase() : result;
}

// New function to download code as a file
function downloadAsFile() {
  if (typeof window === "undefined") {
    return;
  }
  
  // Map of common extensions for languages
  const fileExtensions = {
    javascript: ".js",
    python: ".py",
    java: ".java",
    c: ".c",
    cpp: ".cpp",
    "c++": ".cpp",
    "c#": ".cs",
    ruby: ".rb",
    php: ".php",
    swift: ".swift",
    typescript: ".ts",
    go: ".go",
    rust: ".rs",
    html: ".html",
    css: ".css",
    shell: ".sh",
    bash: ".sh",
    sql: ".sql",
    json: ".json"
  };
  
  const fileExtension = fileExtensions[detectedLanguage.value] || ".txt";
  const suggestedFileName = `file-${generateRandomString(3, true)}${fileExtension}`;
  const fileName = window.prompt("Enter file name", suggestedFileName);

  if (!fileName) {
    return;
  }

  const blob = new Blob([props.code], { type: "text/plain" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.download = fileName;
  link.href = url;
  link.style.display = "none";
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

onMounted(() => {
  // If we want to register custom languages or configure highlight.js
  // we would do it here
  hljs.configure({
    ignoreUnescapedHTML: true
  });
});
</script>

<template>
  <div 
    class="code-block" 
    :class="[
      `language-${detectedLanguage}`,
      { 'generating': isGenerating }
    ]" 
    :data-language="isGenerating ? 'GENERATING' : undefined"
  >
    <div class="code-header">
      <span class="language-label">{{ isGenerating ? 'Generating response...' : displayLanguage }}</span>
      
      <div class="header-actions" v-if="!isGenerating">
        <button class="action-button" @click="downloadAsFile" title="Download as file">
          <svg viewBox="0 0 24 24" width="16" height="16">
            <path d="M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z" fill="currentColor"></path>
          </svg>
        </button>
        
        <button class="action-button" @click="copyCode" title="Copy to clipboard">
          <svg v-if="!copied" class="copy-icon" viewBox="0 0 24 24" width="16" height="16">
            <path d="M16 1H4C2.9 1 2 1.9 2 3V17H4V3H16V1ZM19 5H8C6.9 5 6 5.9 6 7V21C6 22.1 6.9 23 8 23H19C20.1 23 21 22.1 21 21V7C21 5.9 20.1 5 19 5ZM19 21H8V7H19V21Z" fill="currentColor"></path>
          </svg>
          <svg v-else class="copy-icon" viewBox="0 0 24 24" width="16" height="16">
            <path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41L9 16.17z" fill="currentColor"></path>
          </svg>
          <span class="action-text">{{ copied ? 'Copied!' : 'Copy' }}</span>
        </button>
      </div>
      
      <div v-else class="generating-indicator">
        <span class="dot"></span>
        <span class="dot"></span>
        <span class="dot"></span>
      </div>
    </div>
    
    <pre :class="{ 'generating-pre': isGenerating }">
      <code :id="codeId" v-html="highlightedCode"></code>
    </pre>
  </div>
</template>

<style scoped>
.code-block {
  margin: 15px 0;
  width: 100%;
  border-radius: 8px;
  overflow: hidden;
  background-color: #1e1e1e;
  box-shadow: 0 4px 12px rgba(0,0,0,0.2);
  max-width: 100%;
  position: relative;
  border-left: 4px solid #4a6bff;
  animation: fadeIn 0.3s ease;
}

.code-block::before {
  content: attr(data-language);
  position: absolute;
  top: 0;
  right: 0;
  padding: 4px 10px;
  background-color: rgba(0,0,0,0.5);
  color: #fff;
  font-size: 0.8em;
  border-bottom-left-radius: 6px;
  z-index: 10;
  font-family: 'Segoe UI', sans-serif;
  display: none;
}

/* Only show the label when data-language is set (for generating state) */
.code-block[data-language]::before {
  display: block;
}

/* Language-specific borders */
.code-block.language-python {
  border-left-color: #3572A5;
}

.code-block.language-javascript,
.code-block.language-js {
  border-left-color: #f7df1e;
}

.code-block.language-typescript,
.code-block.language-ts {
  border-left-color: #3178c6;
}

.code-block.language-html {
  border-left-color: #e34c26;
}

.code-block.language-css {
  border-left-color: #264de4;
}

.code-block.language-bash,
.code-block.language-shell {
  border-left-color: #4eaa25;
}

.code-block.language-json {
  border-left-color: #f5871f;
}

.code-header {
  background-color: #252526;
  color: #e0e0e0;
  padding: 8px 12px;
  font-size: 0.85em;
  font-family: 'Consolas', 'Monaco', monospace;
  border-bottom: 1px solid #333;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.language-label {
  font-weight: 500;
}

.header-actions {
  display: flex;
  gap: 8px;
}

.action-button {
  background-color: rgba(255,255,255,0.1);
  color: #e0e0e0;
  border: none;
  border-radius: 4px;
  padding: 4px 10px;
  font-size: 0.85em;
  cursor: pointer;
  transition: all 0.2s ease;
  display: flex;
  align-items: center;
  gap: 5px;
}

.action-button:hover {
  background-color: rgba(255,255,255,0.2);
}

.action-button:active {
  transform: translateY(1px);
  background-color: rgba(255,255,255,0.25);
}

.action-text {
  display: none;
}

@media (min-width: 640px) {
  .action-text {
    display: inline;
  }
}

.copy-icon {
  fill: currentColor;
}

.code-block pre {
  margin: 0;
  padding: 16px;
  overflow-x: auto;
  background-color: #1e1e1e;
  color: #f8f8f2;
  max-width: 100%;
  -webkit-overflow-scrolling: touch; /* Smooth scrolling on iOS */
  tab-size: 4;
  -moz-tab-size: 4;
}

.code-block code {
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 0.9em;
  white-space: pre;
  line-height: 1.5;
  display: inline-block;
  min-width: 100%;
  text-align: left;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}

/* Generating state styles */
.code-block.generating {
  border-left-color: #555;
  background-color: #121212;
}

.code-block.generating .code-header {
  background-color: #1a1a1a;
}

.generating-pre {
  opacity: 0.7;
}

.generating-indicator {
  display: flex;
  align-items: center;
  gap: 4px;
}

.dot {
  height: 6px;
  width: 6px;
  background-color: #777;
  border-radius: 50%;
  display: inline-block;
  animation: pulse 1.4s infinite ease-in-out;
}

.dot:nth-child(2) {
  animation-delay: 0.2s;
}

.dot:nth-child(3) {
  animation-delay: 0.4s;
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
</style> 