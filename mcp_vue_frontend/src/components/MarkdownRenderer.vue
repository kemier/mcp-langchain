<template>
  <div class="markdown-container">
    <div v-if="isLoading && !markdownText" class="loading-indicator">
      <div class="spinner"></div>
      <p>加载中...</p>
    </div>
    
    <div v-if="error" class="error-message">
      <p>{{ error }}</p>
      <button v-if="isRecoverable" @click="attemptRecovery" class="retry-button">
        重试
      </button>
    </div>
    
    <vue-markdown-render :source="markdownText" :options="markdownItOptions" class="markdown-content" />
    <!-- <pre class="raw-markdown-debug" style="white-space: pre-wrap; word-wrap: break-word; background-color: #f0f0f0; border: 1px solid #ccc; padding: 10px;">{{ markdownText }}</pre> -->

  </div>
</template>

<script>
import { StreamService } from '../services/streamService';
import VueMarkdownRender from 'vue-markdown-render';
import hljs from 'highlight.js/lib/core'; // Import core library
// Import languages you expect to use
import javascript from 'highlight.js/lib/languages/javascript';
import python from 'highlight.js/lib/languages/python';
import xml from 'highlight.js/lib/languages/xml'; // For HTML
import css from 'highlight.js/lib/languages/css';
import bash from 'highlight.js/lib/languages/bash';
import json from 'highlight.js/lib/languages/json';
import plaintext from 'highlight.js/lib/languages/plaintext';
import rust from 'highlight.js/lib/languages/rust'; // +++ Import Rust
// Import the desired style
import 'highlight.js/styles/github.css'; // SWITCHED TO GITHUB LIGHT THEME

// Register the languages
hljs.registerLanguage('javascript', javascript);
hljs.registerLanguage('python', python);
hljs.registerLanguage('xml', xml); // Register for HTML
hljs.registerLanguage('html', xml); // Alias HTML to XML
hljs.registerLanguage('css', css);
hljs.registerLanguage('bash', bash);
hljs.registerLanguage('json', json);
hljs.registerLanguage('plaintext', plaintext);
hljs.registerLanguage('rust', rust); // +++ Register Rust

const streamService = StreamService.getInstance();

export default {
  name: 'MarkdownRenderer',
  components: {
    VueMarkdownRender
  },
  props: {
    initialMarkdown: {
      type: String,
      default: ''
    },
    streamEndpoint: {
      type: String,
      default: '/ws/chat' // This will be used to construct the full URL
    },
    streamPayload: {
      type: Object,
      default: () => ({})
    },
    debugMode: {
      type: Boolean,
      default: false
    }
  },
  data() {
    return {
      markdownText: this.initialMarkdown,
      internalMarkdownText: this.initialMarkdown,
      isLoading: false,
      error: null,
      isRecoverable: false,
      subscription: null,
      sessionId: 'markdown-' + Date.now(),
      reconnectAttempts: 0,
      maxReconnectAttempts: 3,
      isRenderThrottled: false,
      renderThrottleTimeoutId: null,
      renderThrottleDelay: 1100,
      // --- New Data Property for Markdown-it Options ---
      markdownItOptions: {
        html: true, // Enable HTML tags in source
        xhtmlOut: false, // Use '/' to close single tags (<br />)
        breaks: true, // Convert '\\n' in paragraphs into <br>
        langPrefix: 'language-', // CSS language prefix for fenced blocks
        linkify: true, // Autoconvert URL-like text to links
        typographer: true, // Enable some language-neutral replacement + quotes beautification
        // --- Custom Highlight Function ---
        highlight: this.customHighlight, 
        // --- Add markdown-it instance customization for links ---
        markdownIt: (md) => {
          console.log('[MarkdownRenderer] Customizing markdown-it instance. Linkify is:', md.options.linkify); // Log if customization fn runs

          const defaultRender = md.renderer.rules.link_open || function(tokens, idx, options, env, self) {
            return self.renderToken(tokens, idx, options);
          };

          md.renderer.rules.link_open = function (tokens, idx, options, env, self) {
            console.log('[MarkdownRenderer] link_open rule executed for token:', JSON.parse(JSON.stringify(tokens[idx]))); // Log if rule is hit

            const hrefAttr = tokens[idx].attrGet('href');
            console.log('[MarkdownRenderer] Link href:', hrefAttr);

            // Set target
            const targetAttrIndex = tokens[idx].attrIndex('target');
            if (targetAttrIndex < 0) {
              tokens[idx].attrPush(['target', '_blank']);
              console.log('[MarkdownRenderer] Added target="_blank"');
            } else {
              tokens[idx].attrs[targetAttrIndex][1] = '_blank';
              console.log('[MarkdownRenderer] Set existing target to _blank');
            }

            // Set rel
            const relAttrIndex = tokens[idx].attrIndex('rel');
            let currentRel = tokens[idx].attrs[relAttrIndex]?.[1] || '';
            let newRelParts = new Set(currentRel.split(' ').filter(s => s)); // Existing parts
            newRelParts.add('noopener');
            newRelParts.add('noreferrer');
            const newRel = Array.from(newRelParts).join(' ');

            if (relAttrIndex < 0) {
              tokens[idx].attrPush(['rel', newRel]);
              console.log('[MarkdownRenderer] Added rel="' + newRel + '"');
            } else {
              tokens[idx].attrs[relAttrIndex][1] = newRel;
              console.log('[MarkdownRenderer] Updated existing rel to "' + newRel + '"');
            }
            
            console.log('[MarkdownRenderer] Token after modification:', JSON.parse(JSON.stringify(tokens[idx])));
            // Pass token to default renderer.
            return defaultRender(tokens, idx, options, env, self);
          };
        }
      }
      // --- End New Data Property ---
    };
  },
  watch: {
    initialMarkdown(newVal) {
      this.internalMarkdownText = newVal;
      this.markdownText = newVal;
      if (this.renderThrottleTimeoutId) {
        clearTimeout(this.renderThrottleTimeoutId);
        this.isRenderThrottled = false;
      }
    }
  },
  mounted() {
    if (this.streamEndpoint) {
      this.startMarkdownStream();
    }
    // Add event listener to the container for delegated copy clicks
    this.$el.addEventListener('click', this.copyCode);
  },
  beforeUnmount() {
    this.cleanupStream();
    if (this.renderThrottleTimeoutId) {
      clearTimeout(this.renderThrottleTimeoutId);
    }
    // Remove event listener
    this.$el.removeEventListener('click', this.copyCode);
  },
  methods: {
    // --- New Method: Custom Highlighter ---
    customHighlight(str, lang) {
      const langName = lang || 'plaintext';
      let highlightedCode = '';
      
      // Try highlighting, fallback to plaintext on error or unknown lang
      try {
        if (lang && hljs.getLanguage(lang)) {
          highlightedCode = hljs.highlight(str, { language: lang, ignoreIllegals: true }).value;
        } else {
          highlightedCode = hljs.highlight(str, { language: 'plaintext', ignoreIllegals: true }).value;
        }
      } catch (__) {
        highlightedCode = hljs.highlight(str, { language: 'plaintext', ignoreIllegals: true }).value; // Fallback on error
      }

      // Generate unique ID for the button to target the correct pre element
      const uniqueId = `code-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;

      // Wrap the highlighted code with language name and copy button
      return `
        <div class="code-block-container">
          <div class="code-block-header">
            <span class="language-name">${langName}</span>
            <button class="copy-button" data-clipboard-target="#${uniqueId}" title="Copy code">
               <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" class="bi bi-clipboard" viewBox="0 0 16 16">
                <path d="M4 1.5H3a2 2 0 0 0-2 2V14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V3.5a2 2 0 0 0-2-2h-1v1h1a1 1 0 0 1 1 1V14a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V3.5a1 1 0 0 1 1-1h1z"/>
                <path d="M10.5 1a.5.5 0 0 1 .5.5v1a.5.5 0 0 1-1 0v-1a.5.5 0 0 1 .5-.5M8.5 1a.5.5 0 0 1 .5.5v1a.5.5 0 0 1-1 0v-1a.5.5 0 0 1 .5-.5M12 3a1 1 0 0 0-1-1H5a1 1 0 0 0-1 1v1h8z"/>
               </svg>
               <span class="copy-status">Copy</span>
            </button>
          </div>
          <pre id="${uniqueId}" class="hljs ${lang ? `language-${lang}` : ''}"><code class="code-content">${highlightedCode}</code></pre>
        </div>
      `;
    },
    // --- End New Method ---

    // --- New Method: Copy Code Logic ---
    // Note: This relies on event delegation set up in the template or mounted hook
    copyCode(event) {
      const button = event.target.closest('.copy-button');
      if (!button) return;
      
      const targetSelector = button.getAttribute('data-clipboard-target');
      if (!targetSelector) return;

      const preElement = this.$el.querySelector(targetSelector);
      if (!preElement) {
        console.error('Copy target not found:', targetSelector);
        return;
      }

      const codeContentElement = preElement.querySelector('.code-content');
      const codeToCopy = codeContentElement ? codeContentElement.innerText : preElement.innerText; // Use innerText to preserve formatting

      navigator.clipboard.writeText(codeToCopy).then(() => {
        const statusSpan = button.querySelector('.copy-status');
        if (statusSpan) {
          statusSpan.textContent = 'Copied!';
          button.classList.add('copied');
          setTimeout(() => {
            statusSpan.textContent = 'Copy';
             button.classList.remove('copied');
          }, 2000); // Reset after 2 seconds
        }
      }).catch(err => {
        console.error('Failed to copy code:', err);
         const statusSpan = button.querySelector('.copy-status');
         if (statusSpan) {
           statusSpan.textContent = 'Error';
           setTimeout(() => { statusSpan.textContent = 'Copy'; }, 2000);
         }
      });
    },
    // --- End New Method ---

    startMarkdownStream() {
      // --- Client-side prompt validation ---
      if (!this.streamPayload || typeof this.streamPayload.prompt !== 'string' || !this.streamPayload.prompt.trim()) {
        // Remove setting the error property to prevent UI display
        // this.error = 'Client Error: Prompt cannot be empty. Please provide a valid prompt in streamPayload.';
        this.isLoading = false;
        this.isRecoverable = false; // This is usually not recoverable by just retrying
        if (this.debugMode) {
          console.warn('[MARKDOWN] Stream not started due to empty or missing prompt in payload.', this.streamPayload);
        }
        // Emit an error event so the parent component is aware
        this.$emit('stream-error', { error: 'Client Error: Prompt cannot be empty', recoverable: false }); // Still emit the error event
        return; // Stop execution
      }
      // --- End validation ---

      this.isLoading = true;
      
      try {
        const backendPort = 8010; // Assuming your backend is on this port
        const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsHost = window.location.hostname;
        const wsUrl = `${wsProtocol}//${wsHost}:${backendPort}${this.streamEndpoint}`;
        
        if (this.debugMode) {
          console.log(`[MARKDOWN] Constructed WebSocket URL: ${wsUrl}`);
        }

        const stream$ = streamService.createWebSocketStream(
          wsUrl,
          {
            ...this.streamPayload,
            session_id: this.sessionId
          },
          this.sessionId,
          this.debugMode
        );
        
        if (this.debugMode) {
          console.log(`[MARKDOWN] Starting stream with session ID: ${this.sessionId}`);
        }
        
        this.subscription = stream$.subscribe({
          next: (event) => this.handleStreamEvent(event),
          error: (err) => this.handleStreamError(err),
          complete: () => {
            this.isLoading = false;
            if (this.debugMode) {
              console.log(`[MARKDOWN RENDERER] Stream subscription completed for session ${this.sessionId}.`);
              console.log(`[MARKDOWN RENDERER] Emitting stream-complete with content:`, this.markdownText);
            }
            this.$emit('stream-complete', { 
              sessionId: this.sessionId, 
              content: this.markdownText 
            });
          }
        });
      } catch (error) {
        console.error('Failed to start markdown stream:', error);
        this.handleStreamError(error);
      }
    },
    
    handleStreamEvent(event) {
      if (this.debugMode) {
        console.log(`[MARKDOWN] Received event:`, event);
      }
      
      if (event.type === 'token') {
        this.internalMarkdownText += event.data;
        this.scheduleRenderUpdate();
        this.$emit('content-update', this.internalMarkdownText);
      } else if (event.type === 'error_event') {
        this.error = event.data.error || '处理流时发生错误';
        this.isRecoverable = event.data.recoverable === true;
        this.$emit('stream-error', event.data);
        this.forceRenderUpdate();
      } else if (event.type === 'connection_established') {
        this.isLoading = false;
        this.$emit('stream-connected', event.data);
      } else if (event.type === 'final') {
        if (typeof event.data === 'string' && event.data.trim()) {
          this.internalMarkdownText = event.data;
          this.$emit('content-final', this.internalMarkdownText);
        }
        this.forceRenderUpdate();
      } else if (event.type === StreamEventType.END || event.type === 'CHAIN_END' || event.type === 'end') { 
        if (event.data && typeof event.data.content === 'string') {
          this.internalMarkdownText = event.data.content; 
          if (this.debugMode) {
            console.log(`[MARKDOWN RENDERER] handleStreamEvent (END/CHAIN_END): Set internalMarkdownText to:`, this.internalMarkdownText);
          }
        } else if (typeof event.data === 'string' && this.internalMarkdownText !== event.data) {
            if(!this.internalMarkdownText && event.data) {
                this.internalMarkdownText = event.data;
            }
            if (this.debugMode) {
                console.log(`[MARKDOWN RENDERER] handleStreamEvent (END/CHAIN_END) with simple string: '${event.data}'. internalMarkdownText is now: '${this.internalMarkdownText}'`);
            }
        }
        this.forceRenderUpdate();
      }
    },
    
    handleStreamError(error) {
      console.error('Markdown stream error:', error);
      this.isLoading = false;
      this.error = error.message || '流处理过程中发生错误';
      this.isRecoverable = true;
      this.$emit('stream-error', { error: this.error, recoverable: true });
    },
    
    attemptRecovery() {
      if (this.reconnectAttempts >= this.maxReconnectAttempts) {
        this.error = `已达到最大重试次数 (${this.maxReconnectAttempts})`;
        this.isRecoverable = false;
        return;
      }
      
      this.reconnectAttempts++;
      this.error = null;
      this.cleanupStream();
      
      setTimeout(() => {
        if (this.debugMode) {
          console.log(`[MARKDOWN] Attempting reconnection (${this.reconnectAttempts}/${this.maxReconnectAttempts})`);
        }
        this.startMarkdownStream();
      }, 1000);
    },
    
    scheduleRenderUpdate() {
      if (this.renderThrottleTimeoutId) {
        clearTimeout(this.renderThrottleTimeoutId);
      }
      this.renderThrottleTimeoutId = setTimeout(() => {
        this.markdownText = this.internalMarkdownText;
        this.renderThrottleTimeoutId = null;
        if (this.debugMode) {
          console.log('[MARKDOWN] Throttled render executed.');
        }
      }, this.renderThrottleDelay);
    },

    forceRenderUpdate() {
      if (this.renderThrottleTimeoutId) {
        clearTimeout(this.renderThrottleTimeoutId);
        this.renderThrottleTimeoutId = null;
      }
      if (this.markdownText !== this.internalMarkdownText) {
         this.markdownText = this.internalMarkdownText;
         if (this.debugMode) {
            console.log('[MARKDOWN] Forced final render update.');
         }
      }
    },
    
    cleanupStream() {
      if (this.subscription) {
        this.subscription.unsubscribe();
        this.subscription = null;
      }
      this.forceRenderUpdate(); 
      if (this.renderThrottleTimeoutId) {
         clearTimeout(this.renderThrottleTimeoutId);
         this.renderThrottleTimeoutId = null;
      }
      try {
        streamService.closeStream(this.sessionId);
      } catch (e) {
        if (this.debugMode) {
          console.warn(`[MARKDOWN] Error while closing stream for session ${this.sessionId}: ${e.message}`);
        }
      }
    }
  }
};
</script>

<style>
/* Import highlight.js theme (if not already imported globally) */
/* @import 'highlight.js/styles/github-dark.css'; REMOVED REDUNDANT IMPORT */ 

.markdown-content {
  padding: 0.75rem 1.25rem; /* Adjusted padding */
  line-height: 1.65; /* Slightly more generous line height */
  word-wrap: break-word;
  font-family: 'Open Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, 'Helvetica Neue', sans-serif;
  font-size: 1rem; /* Restored base font size */
  color: #3a3a3a; /* Slightly softer main text color */
}

.markdown-content h1, .markdown-content h2, .markdown-content h3, .markdown-content h4, .markdown-content h5, .markdown-content h6 {
  font-family: 'Nunito', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, 'Helvetica Neue', sans-serif;
  margin-top: 1.2em;
  margin-bottom: 0.6em;
  padding-bottom: 0.2em;
  border-bottom: 1px solid #e0e0e0; /* Softer border */
  color: #2a2a2a; /* Softer heading color */
}

.markdown-content h1 { font-size: 1.7rem; }
.markdown-content h2 { font-size: 1.45rem; }
.markdown-content h3 { font-size: 1.2rem; }

.markdown-content p {
  margin-bottom: 0.75em; /* Balanced paragraph spacing */
}

.markdown-content a {
  color: #007bff; /* Standard friendly blue for links */
  text-decoration: none;
}

.markdown-content a:hover {
  text-decoration: underline;
}

.markdown-content pre {
  background-color: #f9f9f9; /* Light pre background */
  border: 1px solid #e8e8e8;
  border-radius: 8px; /* More pronounced rounded corners */
  font-family: 'Fira Code', 'Source Code Pro', Menlo, Monaco, Consolas, "Courier New", monospace;
  font-size: 0.875em; /* Good code font size */
  padding: 1em;
  overflow: auto;
  margin: 1em 0;
  box-shadow: 0 1px 3px rgba(0,0,0,0.06); /* Softer, subtle shadow */
}

.markdown-content code:not(pre code) {
  background-color: #f0f0f0; /* Lighter inline code background */
  border-radius: 4px;
  font-family: 'Fira Code', 'Source Code Pro', Menlo, Monaco, Consolas, "Courier New", monospace;
  font-size: 0.85em;
  padding: 0.2em 0.45em;
  color: #333;
}

.markdown-content blockquote {
  margin-left: 0;
  margin-right: 0;
  padding: 0.6em 1em;
  color: #505050;
  border-left: 3px solid #007bff; /* Accent color for blockquote border */
  background-color: #f9f9f9;
  border-radius: 6px;
  margin-bottom: 0.75em;
  box-shadow: 0 1px 2px rgba(0,0,0,0.05);
}

.markdown-content img {
  max-width: 100%;
  height: auto;
}

.markdown-content table {
  border-collapse: separate; /* Allows for rounded corners on table */
  border-spacing: 0;
  width: 100%;
  margin-bottom: 1em;
  border: 1px solid #e0e0e0;
  border-radius: 8px; /* Rounded corners for table */
  overflow: hidden; /* Needed for border-radius on table */
}

.markdown-content table th,
.markdown-content table td {
  padding: 0.6em 0.8em;
  border-bottom: 1px solid #e0e0e0;
}

.markdown-content table th:not(:last-child),
.markdown-content table td:not(:last-child) {
  border-right: 1px solid #e0e0e0;
}

.markdown-content table tr:last-child td {
  border-bottom: none; /* Remove bottom border for last row */
}

.markdown-content table th {
  background-color: #f9f9f9;
  font-weight: 600; /* Bolder headers */
  text-align: left;
}

/* List Styles */
.markdown-content ol,
.markdown-content ul {
  padding-left: 1.8em; /* Good indent */
  margin-bottom: 0.75em;
}

.markdown-content li {
  margin-bottom: 0.35em;
}

.markdown-content li > p {
  margin-bottom: 0.15em; 
}

/* Disclaimer Styles - REMOVED */

</style>

<style scoped>
.markdown-container {
  width: 100%;
  max-width: 100%;
  margin: 0 auto;
  font-family: 'Open Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, 'Helvetica Neue', sans-serif;
  color: #333;
  padding: 1em;
  background-color: #fff;
}

.loading-indicator {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 20px;
  color: #555;
}

.spinner {
  border: 4px solid #f3f3f3; /* Light grey */
  border-top: 4px solid #3498db; /* Blue */
  border-radius: 50%;
  width: 30px;
  height: 30px;
  animation: spin 1s linear infinite;
  margin-bottom: 10px;
}

.error-message {
  color: red;
  padding: 10px;
  border: 1px solid red;
  border-radius: 4px;
  background-color: #ffebeb;
}

.retry-button {
  margin-top: 10px;
  padding: 5px 10px;
  cursor: pointer;
}

/* Debug raw markdown */
.raw-markdown-debug {
  white-space: pre-wrap;
  word-wrap: break-word;
  background-color: #f0f0f0;
  border: 1px solid #ccc;
  padding: 10px;
  margin-top: 15px; /* Space it out from rendered content */
}

/* General styling for rendered markdown content */
:deep(.markdown-content) {
  /* Ensure it inherits colors or set defaults */
  color: inherit; 
  font-size: 1em;
  line-height: 1.6;
}

/* ---- STYLES FOR CODE BLOCKS (NEW/ADJUSTED) ---- */
:deep(.code-block-container) {
  background-color: transparent !important; /* Remove distinct background */
  border: 1px solid #e0e0e0; /* Softer border than before, or remove if not needed */
  border-radius: 6px;
  margin-top: 0.5em;
  margin-bottom: 0.5em;
  padding: 0 !important; /* Remove container padding */
  overflow: hidden; /* To ensure child border-radius is respected */
}

:deep(.code-block-header) {
  display: flex;
  justify-content: space-between;
  align-items: center;
  background-color: #f5f5f5; /* Light header background */
  padding: 0.3em 0.8em !important; /* Reduced padding */
  border-bottom: 1px solid #e0e0e0; /* Separator */
}

:deep(.language-name) {
  font-size: 0.85em;
  color: #555;
  text-transform: uppercase;
}

:deep(.copy-button) {
  background-color: #e9ecef;
  color: #495057;
  border: 1px solid #ced4da;
  padding: 0.25em 0.6em;
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.8em;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
:deep(.copy-button .bi-clipboard) {
  /* SVG already has width/height, no need to resize here explicitly unless overriding */
}

:deep(.copy-button .copy-status) {
  /* Style for "Copy" / "Copied!" text */
}

:deep(.copy-button.copied) {
  background-color: #28a745; /* Green background for copied state */
  color: white;
  border-color: #28a745;
}

/* Styling for the <pre> and <code> tags from highlight.js */
:deep(.code-block-container pre.hljs) {
  padding: 0.8em !important; /* Minimal padding inside the pre */
  margin: 0 !important; /* Remove margins from pre */
  background-color: transparent !important; /* Make pre background transparent */
  border-radius: 0 0 6px 6px; /* Match container's bottom radius */
  overflow-x: auto; /* Allow horizontal scrolling for long lines */
}

:deep(.code-block-container pre.hljs code) {
  background-color: transparent !important; /* Ensure code tag is also transparent */
  font-size: 0.9em; /* Adjust font size if needed */
  /* color: inherit; */ /* It should inherit from parent or hljs theme */
}

/* ---- END STYLES FOR CODE BLOCKS ---- */


/* Example of further global styling for markdown elements if needed */
:deep(.markdown-content h1) {
  font-size: 1.8em;
  margin-top: 1em;
  margin-bottom: 0.5em;
  border-bottom: 1px solid #eee;
  padding-bottom: 0.3em;
}

:deep(.markdown-content h2) {
  font-size: 1.5em;
  margin-top: 1em;
  margin-bottom: 0.4em;
}

:deep(.markdown-content p) {
  margin-bottom: 0.8em;
}

:deep(.markdown-content ul),
:deep(.markdown-content ol) {
  padding-left: 20px;
  margin-bottom: 0.8em;
}

:deep(.markdown-content blockquote) {
  border-left: 4px solid #ccc;
  padding-left: 10px;
  margin-left: 0;
  color: #555;
  font-style: italic;
}

:deep(.markdown-content table) {
  width: auto; /* Let table size itself, or set to 100% for full width */
  border-collapse: collapse;
  margin-bottom: 1em;
  border: 1px solid #ddd;
}

:deep(.markdown-content th),
:deep(.markdown-content td) {
  border: 1px solid #ddd;
  padding: 8px;
  text-align: left;
}

:deep(.markdown-content th) {
  background-color: #f7f7f7;
  font-weight: bold;
}

:deep(.markdown-content img) {
  max-width: 100%;
  height: auto;
  border-radius: 4px;
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}
</style> 