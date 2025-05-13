<template>
  <div class="code-formatter">
    <pre><code v-html="highlightedCode"></code></pre>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue';
import hljs from 'highlight.js';
import 'highlight.js/styles/atom-one-dark.css';

const props = defineProps({
  code: {
    type: String,
    required: true
  },
  language: {
    type: String,
    default: '' // Auto-detect if empty
  }
});

// Detect language from code if not specified
function detectLanguage(code) {
  if (props.language) {
    return props.language;
  }
  
  try {
    const result = hljs.highlightAuto(code);
    return result.language || 'plaintext';
  } catch (error) {
    console.error('Error detecting language:', error);
    return 'plaintext';
  }
}

// Apply syntax highlighting to the code
function applySyntaxHighlighting(code) {
  if (!code) return '';
  
  try {
    const language = detectLanguage(code);
    if (language) {
      const result = hljs.highlight(code, { language });
      return result.value;
    } else {
      return hljs.highlightAuto(code).value;
    }
  } catch (error) {
    console.error('Error applying syntax highlighting:', error);
    return hljs.highlightAuto(code).value;
  }
}

// Computed property for the highlighted code
const highlightedCode = computed(() => {
  return applySyntaxHighlighting(props.code);
});

// Computed property for the detected language (for styling)
const detectedLanguage = computed(() => {
  return detectLanguage(props.code);
});
</script>

<style scoped>
.code-formatter {
  margin: 15px 0;
  border-radius: 8px;
  overflow: hidden;
  box-shadow: 0 4px 12px rgba(0,0,0,0.15);
}

pre {
  margin: 0;
  padding: 20px;
  background-color: #1e1e1e;
  color: #f8f8f2;
  border-radius: 8px;
  overflow-x: auto;
  tab-size: 4;
  -moz-tab-size: 4;
  font-family: 'JetBrains Mono', 'Fira Code', 'Consolas', 'Monaco', monospace;
  font-size: 0.95em;
  line-height: 1.6;
  letter-spacing: 0.3px;
  border-left: 5px solid v-bind('languageColor');
}

/* Syntax highlighting colors with more vibrant theme */
:deep(.hljs-keyword) {
  color: #ff79c6;
  font-weight: bold;
}

:deep(.hljs-function) {
  color: #50fa7b;
}

:deep(.hljs-string) {
  color: #f1fa8c;
}

:deep(.hljs-number) {
  color: #bd93f9;
}

:deep(.hljs-comment) {
  color: #6272a4;
  font-style: italic;
}

/* Add styles for more syntax elements */
:deep(.hljs-built_in) {
  color: #8be9fd;
  font-style: italic;
}

:deep(.hljs-operator) {
  color: #ff79c6;
}

:deep(.hljs-punctuation) {
  color: #f8f8f2;
}

:deep(.hljs-variable) {
  color: #f8f8f2;
}

:deep(.hljs-params) {
  color: #ffb86c;
}

:deep(.hljs-preprocessor), 
:deep(.hljs-pragma), 
:deep(.hljs-include) {
  color: #ff79c6;
}

/* Add hover effect to make code more interactive */
.code-formatter:hover {
  box-shadow: 0 6px 16px rgba(0,0,0,0.2);
  transform: translateY(-2px);
  transition: all 0.3s ease;
}

/* Add a header to the code block */
.code-formatter::before {
  content: v-bind('languageName');
  display: block;
  background-color: #282a36;
  color: #f8f8f2;
  padding: 8px 16px;
  font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  font-size: 0.85em;
  border-bottom: 1px solid #44475a;
  font-weight: 500;
}
</style>

<script>
export default {
  computed: {
    languageColor() {
      // Color coding for different languages
      switch (this.detectedLanguage) {
        case 'python':
          return '#3572A5'; // Python blue
        case 'c':
          return '#555555'; // C gray
        case 'javascript':
        case 'js':
          return '#f7df1e'; // JavaScript yellow
        case 'typescript':
        case 'ts':
          return '#007acc'; // TypeScript blue
        case 'java':
          return '#b07219'; // Java brown
        case 'html':
          return '#e34c26'; // HTML orange
        case 'css':
          return '#563d7c'; // CSS purple
        case 'bash':
        case 'shell':
          return '#89e051'; // Shell green
        case 'php':
          return '#4F5D95'; // PHP purple
        case 'ruby':
          return '#701516'; // Ruby red
        case 'go':
          return '#00ADD8'; // Go blue
        case 'rust':
          return '#dea584'; // Rust orange
        case 'csharp':
        case 'cs':
          return '#178600'; // C# green
        case 'cpp':
          return '#f34b7d'; // C++ pink
        default:
          return '#4a4a4a'; // Default dark gray
      }
    },
    languageName() {
      // Display name for the language
      switch (this.detectedLanguage) {
        case 'python':
          return 'Python';
        case 'c':
          return 'C';
        case 'javascript':
        case 'js':
          return 'JavaScript';
        case 'typescript':
        case 'ts':
          return 'TypeScript';
        case 'java':
          return 'Java';
        case 'html':
          return 'HTML';
        case 'css':
          return 'CSS';
        case 'bash':
        case 'shell':
          return 'Shell';
        case 'php':
          return 'PHP';
        case 'ruby':
          return 'Ruby';
        case 'go':
          return 'Go';
        case 'rust':
          return 'Rust';
        case 'csharp':
        case 'cs':
          return 'C#';
        case 'cpp':
          return 'C++';
        case 'json':
          return 'JSON';
        case 'xml':
          return 'XML';
        case 'markdown':
        case 'md':
          return 'Markdown';
        case 'sql':
          return 'SQL';
        case 'yaml':
        case 'yml':
          return 'YAML';
        case 'plaintext':
          return 'Plain Text';
        default:
          return this.detectedLanguage ? this.detectedLanguage.charAt(0).toUpperCase() + this.detectedLanguage.slice(1) : 'Code';
      }
    }
  }
}
</script> 