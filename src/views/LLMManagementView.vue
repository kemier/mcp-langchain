import { ref, onMounted, reactive } from 'vue';
// import { useRouter } from 'vue-router'; // Remove unused import
import type { LLMConfig, LLMConfigUpdatePayload } from '../services/apiService';
// ... existing code ...
const isLoadingModels = ref<boolean>(false);
const availableOllamaModels = ref<string[]>([]);
const loadModelsError = ref<string | null>(null);
// const configToDeleteId = ref<string | null>(null); // Remove unused
// const showDeleteConfirmation = ref(false); // Remove unused

async function loadLLMConfigs() {
// ... existing code ...
  Object.assign(currentConfig, configCopy);
  
  if (config.provider === 'ollama') {
    // Ensure ollama_config exists before spreading
    currentConfig.ollama_config = { ...(currentConfig.ollama_config || {}) }; 
  }
  if (config.provider === 'deepseek') {
// ... existing code ...
}

function resetTestConnectionState() {
// ... existing code ...

async function testOllama() {
  // Fix .value access
  if (!currentConfig.ollama_config?.base_url) {
    testResultMessage.value = "Ollama Base URL is required to test connection.";
// ... existing code ...

  try {
    // Fix .value access
    const response = await testOllamaConnection(currentConfig.ollama_config.base_url);
    testResultMessage.value = response.message;
// ... existing code ...

async function loadOllamaModels() {
  // Fix .value access
  if (!currentConfig.ollama_config?.base_url) {
    loadModelsError.value = "Ollama Base URL is required.";
// ... existing code ...
  try {
    // Fix .value access
    const response = await fetchOllamaModels(currentConfig.ollama_config.base_url);
    if (response.success && response.models) {
      availableOllamaModels.value = response.models;
      loadModelsError.value = null;
       // Fix .value access (twice)
       if (availableOllamaModels.value.length > 0 && currentConfig.ollama_config && !currentConfig.ollama_config.model) {
          // Fix .value access
          currentConfig.ollama_config.model = availableOllamaModels.value[0];
      }
    } else {
} 