import { ref, onMounted, reactive, watch } from 'vue';
// import { useRouter } from 'vue-router'; // Remove unused import
import type { LLMConfig, LLMConfigUpdatePayload } from '../services/apiService';
import axios from 'axios';
// ... existing code ...
const isLoadingModels = ref<boolean>(false);
const availableOllamaModels = ref<string[]>([]);
const loadModelsError = ref<string | null>(null);
// const configToDeleteId = ref<string | null>(null); // Remove unused
// const showDeleteConfirmation = ref(false); // Remove unused

// Keep your LLMConfig interface relatively flat
interface LLMConfig {
  config_id?: string;
  display_name: string;
  provider: 'ericai' | 'ollama' | 'deepseek' | string; // Key differentiator
  model_name_or_path: string; // Model ID for EricAI, model name for Ollama, etc.
  base_url?: string; // Used by EricAI, Ollama, etc.
  api_key?: string; // Used by EricAI, DeepSeek, etc. (Handle securely)
  temperature?: number;
  max_tokens?: number;
  is_default?: boolean;
}

// currentConfig for the form - now flatter
const currentConfig = reactive<Partial<LLMConfig>>({});

const predefinedEricAIModels = ref<string[]>([]);

// Helper to determine if API key is typically needed (can be refined)
const providerRequiresApiKey = (provider?: string): boolean => {
  return ['ericai', 'deepseek' /* add others */].includes(provider || '');
};

// Helper to determine if Base URL is typically needed (can be refined)
const providerRequiresBaseUrl = (provider?: string): boolean => {
  return ['ericai', 'ollama' /* add others */].includes(provider || '');
};

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

// Function to fetch predefined EricAI models
const fetchPredefinedEricAIModels = async () => {
  try {
    // Assuming your apiService has a method for this, or use axios directly
    // const response = await apiService.getEricAIProviderModels(); 
    const response = await axios.get('http://localhost:8000/ericai_provider_models'); // Adjust URL
    predefinedEricAIModels.value = response.data.models;
  } catch (error) {
    console.error("Failed to fetch predefined EricAI models:", error);
    predefinedEricAIModels.value = []; // Clear on error
  }
};

// Watch for provider changes to fetch models if "ericai" is selected
watch(() => currentConfig.provider, (newProvider) => {
  if (newProvider === 'ericai') {
    if (predefinedEricAIModels.value.length === 0) { // Fetch only if not already fetched
        fetchPredefinedEricAIModels();
    }
    // Optionally set a default model if currentConfig.model_name_or_path is empty
    if (!currentConfig.model_name_or_path && predefinedEricAIModels.value.length > 0) {
        // currentConfig.model_name_or_path = predefinedEricAIModels.value[0];
    }
  } else {
    // Clear or handle model selection if provider changes from ericai
    // if (oldProvider === 'ericai') currentConfig.model_name_or_path = undefined;
  }
}, { immediate: false }); // 'immediate: false' if you openConfigForm sets initial provider

// When opening the form
function openConfigForm(configToEdit?: LLMConfig) {
  showConfigForm.value = true;
  isEditing.value = !!configToEdit;

  if (configToEdit) {
    // Deep copy to avoid modifying the original list item directly
    Object.assign(currentConfig, JSON.parse(JSON.stringify(configToEdit)));
  } else {
    // Reset for new config - flat structure
    Object.keys(currentConfig).forEach(key => delete (currentConfig as any)[key]);
    currentConfig.display_name = '';
    currentConfig.provider = 'ericai'; // Default provider
    currentConfig.model_name_or_path = '';
    currentConfig.base_url = ''; // Provide default empty strings for v-model
    currentConfig.api_key = '';
    currentConfig.temperature = 0.7;
    currentConfig.max_tokens = 1024;
    currentConfig.is_default = false;
  }

  if (currentConfig.provider === 'ericai') {
    fetchPredefinedEricAIModels();
  }
}

// In your saveLLMConfig function, the payload is already flat
async function saveLLMConfig() {
  // Construct payload directly from the flat currentConfig
  // Ensure any empty optional fields are handled correctly (e.g., send null or omit)
  const payload: Partial<LLMConfig> = {
    config_id: currentConfig.config_id, // Include if editing
    display_name: currentConfig.display_name,
    provider: currentConfig.provider,
    model_name_or_path: currentConfig.model_name_or_path,
    base_url: currentConfig.base_url || undefined, // Send undefined/null if empty? Check backend needs
    api_key: currentConfig.api_key || undefined, // Send undefined/null if empty? Check backend needs & security
    temperature: currentConfig.temperature,
    max_tokens: currentConfig.max_tokens,
    is_default: currentConfig.is_default,
  };
  
  // Remove undefined keys if backend prefers omitted keys over null/empty
  Object.keys(payload).forEach(key => {
    if (payload[key as keyof LLMConfig] === undefined || payload[key as keyof LLMConfig] === '') {
       // If backend expects missing keys instead of null/empty strings, uncomment below
       // delete payload[key as keyof LLMConfig];
    }
  });

  // Now send 'payload' to your backend save/update API.
  // Your backend API should save this flat structure directly into llm_configs.json (or DB)
  console.log("Saving config:", payload);
  // await yourApiService.saveConfiguration(payload);
  // ... then close form and refresh list
}

// Expose helpers to the template if needed for conditional rendering/placeholders
return {
  // ... your existing returns
  currentConfig,
  providerRequiresApiKey,
  providerRequiresBaseUrl,
  openConfigForm,
  saveLLMConfig,
  predefinedEricAIModels,
  // ...
}; 