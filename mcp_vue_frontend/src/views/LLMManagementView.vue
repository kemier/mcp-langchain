<template>
  <div class="llm-management-view">
    <header class="app-header">
      <div class="logo-title">
        <img src="../assets/logo.png" alt="MCP App Logo" class="logo"/>
        <h1>LLM Configuration Management</h1>
      </div>
      <nav class="header-nav">
        <router-link to="/chat" class="nav-button">Dashboard</router-link>
      </nav>
    </header>

    <main class="content-area">
      <h2>Manage LLM Configurations</h2>
      <p>
        Here you can add, edit, or remove LLM configurations that will be available for the chat agent.
      </p>
      
      <div class="actions-bar">
        <button @click="openAddModal" class="action-button add-llm-button">Add New LLM Config</button>
      </div>

      <div v-if="isLoading" class="loading-message">Loading LLM configurations...</div>
      <div v-if="error" class="error-message">{{ error }}</div>

      <div v-if="!isLoading && !error && llmConfigs.length === 0" class="no-configs-message">
        No LLM configurations found. Click "Add New LLM Config" to get started.
      </div>

      <div v-if="!isLoading && llmConfigs.length > 0" class="llm-configs-list">
        <table>
          <thead>
            <tr>
              <th>Display Name</th>
              <th>Config ID</th>
              <th>Provider</th>
              <th>Default</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="config in llmConfigs" :key="config.config_id">
              <td>{{ config.display_name }}</td>
              <td><code>{{ config.config_id }}</code></td>
              <td>{{ config.provider }}</td>
              <td>
                <span v-if="config.is_default" class="default-badge">Yes</span>
                <button v-else @click="setDefault(config.config_id!)" class="set-default-button" :disabled="isUpdating || !config.config_id">Set Default</button>
              </td>
              <td class="actions-cell">
                <button @click="openEditModal(config)" class="action-button edit-button" :disabled="isUpdating">Edit</button>
                <button @click="confirmDelete(config.config_id!)" class="action-button delete-button" :disabled="isUpdating || !config.config_id">Delete</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Add/Edit Modal (Simplified Example) -->
      <div v-if="isModalOpen" class="modal-overlay" @click.self="closeModal">
        <div class="modal-content">
          <h3>{{ modalMode === 'add' ? 'Add New' : 'Edit' }} LLM Configuration</h3>
          <form @submit.prevent="handleSubmit">
            <div class="form-group">
              <label for="configId">Config ID (e.g., ollama_llama3_local):</label>
              <input type="text" id="configId" v-model="currentConfig.config_id" :disabled="modalMode === 'edit'" required>
              <small v-if="modalMode === 'edit'">Config ID cannot be changed after creation.</small>
            </div>
            <div class="form-group">
              <label for="displayName">Display Name (e.g., Local Llama 3):</label>
              <input type="text" id="displayName" v-model="currentConfig.display_name" required>
            </div>
            <div class="form-group">
              <label for="provider">Provider:</label>
              <select id="provider" v-model="currentConfig.provider" required>
                <option value="ollama">Ollama</option>
                <option value="deepseek">DeepSeek</option>
                <option value="openai">OpenAI</option> 
                <!-- Add other providers as needed -->
              </select>
            </div>

            <!-- Ollama Specific Fields -->
            <div v-if="currentConfig.provider === 'ollama'" class="provider-options">
              <h4>Ollama Options</h4>
              <div class="form-group">
                <label for="ollamaBaseUrl">Ollama Base URL:</label>
                <input type="url" id="ollamaBaseUrl" v-model="currentConfig.ollama_config!.base_url" placeholder="http://localhost:11434" required>
              </div>
              <div class="form-group">
                <label for="ollamaModel">Model Name:</label>
                <input type="text" id="ollamaModel" v-model="currentConfig.ollama_config!.model" placeholder="e.g., llama3:latest, mistral" required>
              </div>
              <div class="form-group">
                <label for="ollamaTemp">Temperature:</label>
                <input type="number" step="0.1" id="ollamaTemp" v-model.number="currentConfig.ollama_config!.temperature" placeholder="e.g., 0.7">
              </div>
              <!-- Ollama Connection Test -->
              <div class="form-group connection-test">
                <button @click="testOllama" :disabled="!currentConfig.ollama_config?.base_url || isTestingConnection">
                  {{ isTestingConnection ? 'Testing...' : 'Test Connection' }}
                </button>
                <span v-if="testResultMessage" :class="{'test-success': isTestSuccess, 'test-error': !isTestSuccess}" class="test-result">
                  {{ testResultMessage }}
                </span>
              </div>
              <!-- Ollama Model Fetch -->
              <div class="form-group model-fetch">
                  <label for="ollamaModelSelect">Select Model (Optional):</label>
                  <div class="model-select-wrapper">
                      <select id="ollamaModelSelect" v-model="currentConfig.ollama_config!.model" class="form-control">
                          <option disabled value="">-- Select a model --</option>
                          <option v-if="!availableOllamaModels.length && currentConfig.ollama_config?.model" :value="currentConfig.ollama_config.model">{{ currentConfig.ollama_config.model }} (current)</option>
                          <option v-for="model in availableOllamaModels" :key="model" :value="model">{{ model }}</option>
                      </select>
                      <button @click="loadOllamaModels" :disabled="!currentConfig.ollama_config?.base_url || isLoadingModels" class="load-models-btn">
                          {{ isLoadingModels ? 'Loading...' : 'Load Available Models' }}
                      </button>
                  </div>
                  <p v-if="loadModelsError" class="error-message">{{ loadModelsError }}</p>
              </div>
            </div>

            <!-- DeepSeek Specific Fields -->
            <div v-if="currentConfig.provider === 'deepseek'" class="provider-options">
              <h4>DeepSeek Options</h4>
              <div class="form-group">
                <label for="deepseekApiKeyEnv">API Key Env Var:</label>
                <input type="text" id="deepseekApiKeyEnv" v-model="currentConfig.api_key_env_var" placeholder="e.g., DEEPSEEK_API_KEY" required>
              </div>
              <!-- Add model, temperature for DeepSeek if they are configurable -->
            </div>
            
            <!-- OpenAI Specific Fields -->
            <div v-if="currentConfig.provider === 'openai'" class="provider-options">
                <h4>OpenAI Options</h4>
                <div class="form-group">
                    <label for="openaiApiKeyEnv">API Key Env Var:</label>
                    <input type="text" id="openaiApiKeyEnv" v-model="currentConfig.api_key_env_var" placeholder="e.g., OPENAI_API_KEY" required>
                </div>
                <div class="form-group">
                    <label for="openaiModel">Model Name:</label>
                    <input type="text" id="openaiModel" v-model="currentConfig.openai_config!.model" placeholder="e.g., gpt-4-turbo">
                </div>
                <div class="form-group">
                    <label for="openaiBaseUrl">API Base URL (Optional):</label>
                    <input type="url" id="openaiBaseUrl" v-model="currentConfig.openai_config!.base_url" placeholder="e.g., https://api.openai.com/v1">
                </div>
            </div>

            <div class="form-group checkbox-group">
              <input type="checkbox" id="isDefault" v-model="currentConfig.is_default">
              <label for="isDefault">Set as Default LLM</label>
            </div>

            <div class="modal-actions">
              <button type="submit" class="action-button save-button primary-button" :disabled="isSubmitting">{{ isSubmitting ? 'Saving...' : 'Save' }}</button>
              <button type="button" @click="closeModal" class="action-button cancel-button secondary-button">Cancel</button>
            </div>
            <div v-if="modalError" class="error-message modal-error">{{ modalError }}</div>
          </form>
        </div>
      </div>

    </main>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, watch } from 'vue';
// import { useRouter } from 'vue-router'; // Unused
import {
  fetchLLMConfigurations,
  addLLMConfiguration,
  updateLLMConfiguration,
  deleteLLMConfiguration,
  testOllamaConnection,
  fetchOllamaModels,
  type LLMConfig,
  type LLMConfigUpdatePayload,
  type OllamaConnectionTestResponse,
  // Unused: type OllamaModelListApiResponse 
} from '../services/apiService';
// Unused: import LLMErrorAlert from '../components/LLMErrorAlert.vue'; // Ensure this path is correct
// Unused: import LLMConfigForm from '../components/LLMConfigForm.vue'; // Ensure this path is correct

// const router = useRouter(); // Unused

const llmConfigs = ref<LLMConfig[]>([]);
const isLoading = ref(false);
const isUpdating = ref<boolean>(false);
const error = ref<string | null>(null);

const isModalOpen = ref<boolean>(false);
const modalMode = ref<'add' | 'edit'>('add');
const currentConfig = reactive<Partial<LLMConfig>>({});
const isSubmitting = ref<boolean>(false);
const modalError = ref<string | null>(null);

const isTestingConnection = ref<boolean>(false);
const testResultMessage = ref<string | null>(null);
const isTestSuccess = ref<boolean>(false);

const isLoadingModels = ref<boolean>(false);
const availableOllamaModels = ref<string[]>([]);
const loadModelsError = ref<string | null>(null);
const selectedProvider = ref<string>('ollama'); // Default provider
const ollamaConnectionStatus = ref<OllamaConnectionTestResponse | null>(null);
// const configToDeleteId = ref<string | null>(null); // Unused
// const showDeleteConfirmation = ref(false); // Unused

async function loadLLMConfigs() {
  isLoading.value = true;
  error.value = null;
  try {
    llmConfigs.value = await fetchLLMConfigurations();
  } catch (err: any) {
    console.error("Failed to fetch LLM configurations:", err);
    error.value = err.message || "Could not load LLM configurations.";
  } finally {
    isLoading.value = false;
  }
}

onMounted(() => {
  loadLLMConfigs();
});

function resetCurrentConfig() {
  Object.assign(currentConfig, {
    config_id: '',
    display_name: '',
    provider: 'ollama',
    is_default: false,
    api_key_env_var: undefined,
    ollama_config: { base_url: 'http://localhost:11434', model: 'llama3:latest', temperature: 0.7 },
    deepseek_config: { api_key_env_var: undefined },
    openai_config: { model: '', base_url: '', api_key_env_var: undefined }
  });
}

function openAddModal() {
  modalMode.value = 'add';
  resetCurrentConfig();
  modalError.value = null;
  resetTestConnectionState();
  resetFetchModelsState();
  isModalOpen.value = true;
}

function openEditModal(config: LLMConfig) {
  modalMode.value = 'edit';
  const configCopy = JSON.parse(JSON.stringify(config));
  Object.assign(currentConfig, configCopy);
  
  if (config.provider === 'ollama' && !currentConfig.ollama_config) {
    //currentConfig.ollama_config = { ...currentConfig.ollama_config };
  }
  if (config.provider === 'deepseek' && !currentConfig.deepseek_config) {
    currentConfig.deepseek_config = { api_key_env_var: config.api_key_env_var || undefined };
  } 
  if (config.provider === 'openai' && !currentConfig.openai_config) {
    currentConfig.openai_config = { model: '', base_url: '', api_key_env_var: config.api_key_env_var || undefined };
  }
  
  modalError.value = null;
  resetTestConnectionState();
  resetFetchModelsState();
  isModalOpen.value = true;
}

function closeModal() {
  isModalOpen.value = false;
  resetTestConnectionState();
  resetFetchModelsState();
}

function resetTestConnectionState() {
    isTestingConnection.value = false;
    testResultMessage.value = null;
    isTestSuccess.value = false;
}

function resetFetchModelsState() {
    isLoadingModels.value = false;
    availableOllamaModels.value = [];
    loadModelsError.value = null;
}

async function testOllama() {
  error.value = null; // Clear previous errors
  ollamaConnectionStatus.value = null; // Reset status
  if (!currentConfig.ollama_config?.base_url) {
    error.value = 'Ollama Base URL is required to test connection.';
    return;
  }
  isLoading.value = true;
  try {
    const response = await testOllamaConnection(currentConfig.ollama_config.base_url);
    ollamaConnectionStatus.value = response;
    if (!response.success) {
      error.value = response.message || 'Failed to connect to Ollama.';
    }
  } catch (err: any) {
    console.error("Error testing Ollama connection:", err);
    error.value = err.message || 'An error occurred while testing the connection.';
    ollamaConnectionStatus.value = { success: false, message: error.value ?? 'Unknown connection error' };
  } finally {
    isLoading.value = false;
  }
}

async function loadOllamaModels() {
  error.value = null;
  availableOllamaModels.value = []; // Reset models
  if (!currentConfig.ollama_config?.base_url) {
    error.value = 'Ollama Base URL is required to fetch models.';
    return;
  }
  isLoading.value = true;
  try {
    const response = await fetchOllamaModels(currentConfig.ollama_config.base_url);
    if (response.success && response.models) {
      availableOllamaModels.value = response.models;
       if (availableOllamaModels.value.length > 0 && currentConfig.ollama_config && !currentConfig.ollama_config.model) {
          currentConfig.ollama_config.model = availableOllamaModels.value[0];
       }
    } else {
      error.value = response.message || 'Failed to fetch Ollama models.';
    }
  } catch (err: any) {
    console.error("Error fetching Ollama models:", err);
    error.value = err.message || 'An error occurred while fetching models.';
  } finally {
    isLoading.value = false;
  }
}

async function handleSubmit() {
  isSubmitting.value = true;
  modalError.value = null;

  const payload: LLMConfig = {
    config_id: currentConfig.config_id!,
    display_name: currentConfig.display_name!,
    provider: currentConfig.provider!,
    is_default: currentConfig.is_default || false,
    api_key_env_var: currentConfig.api_key_env_var,
  } as LLMConfig;

  if (currentConfig.provider === 'ollama') {
    payload.ollama_config = currentConfig.ollama_config || { base_url: 'http://localhost:11434', model: 'llama3:latest', temperature: 0.7 };
  }
  if (currentConfig.provider === 'deepseek') {
  }

  try {
    if (modalMode.value === 'add') {
      await addLLMConfiguration(payload);
    } else {
      const updatePayload: LLMConfigUpdatePayload = {};
      if (currentConfig.display_name !== undefined) updatePayload.display_name = currentConfig.display_name;
      if (currentConfig.provider !== undefined) updatePayload.provider = currentConfig.provider;
      if (currentConfig.is_default !== undefined) updatePayload.is_default = currentConfig.is_default;
      if (currentConfig.api_key_env_var !== undefined) updatePayload.api_key_env_var = currentConfig.api_key_env_var;
      
      if (currentConfig.provider === 'ollama') {
        updatePayload.ollama_config = currentConfig.ollama_config;
      }

      await updateLLMConfiguration(currentConfig.config_id!, updatePayload);
    }
    closeModal();
    loadLLMConfigs();
  } catch (err: any) {
    console.error("Failed to save LLM configuration:", err);
    modalError.value = err.message || "Could not save configuration.";
  } finally {
    isSubmitting.value = false;
  }
}

async function confirmDelete(configId: string) {
  if (window.confirm(`Are you sure you want to delete LLM configuration "${configId}"? This cannot be undone.`)) {
    isUpdating.value = true;
    error.value = null; // Clear previous general errors
    try {
      await deleteLLMConfiguration(configId);
      await loadLLMConfigs(); // Ensure this is awaited
    } catch (err: any) {
      console.error(`Failed to delete LLM configuration ${configId}:`, err);
      error.value = err.message || `Could not delete ${configId}.`;
    } finally {
      isUpdating.value = false;
    }
  }
}

async function setDefault(configId: string) {
  isUpdating.value = true;
  error.value = null; // Clear previous general errors
  let previousDefaultId: string | undefined = undefined;

  try {
    // Find the current default LLM config
    const currentDefault = llmConfigs.value.find(c => c.is_default);
    if (currentDefault && currentDefault.config_id && currentDefault.config_id !== configId) {
      previousDefaultId = currentDefault.config_id;
      console.log(`[LLM-DEFAULT] Attempting to unset current default: ${previousDefaultId}`);
      await updateLLMConfiguration(previousDefaultId, { is_default: false });
      console.log(`[LLM-DEFAULT] Successfully unset previous default: ${previousDefaultId}`);
    }
    
    // Set the new LLM as default
    console.log(`[LLM-DEFAULT] Attempting to set new default: ${configId}`);
    await updateLLMConfiguration(configId, { is_default: true });
    console.log(`[LLM-DEFAULT] Successfully set new default: ${configId}`);
    
    // Reload configurations to reflect changes in the UI
    await loadLLMConfigs();
    console.log("[LLM-DEFAULT] LLM configurations reloaded.");

  } catch (err: any) {
    console.error(`Error setting default LLM ${configId}:`, err);
    let userMessage = `Failed to set ${configId} as default.`;
    if (err.message) {
      userMessage += ` Details: ${err.message}`;
    }
    if (err.response && typeof err.response.text === 'function') { // Check if response body can be read
        try {
            const errorBody = await err.response.text();
            console.error("[LLM-DEFAULT] Error response body:", errorBody);
            userMessage += ` Server response: ${errorBody}`;
        } catch (e) {
            console.error("[LLM-DEFAULT] Could not read error response body.");
        }
    }
    error.value = userMessage;

    // Optional: Attempt to revert the unsetting of the previous default if setting the new one failed
    // This adds complexity and might also fail.
    if (previousDefaultId && configId !== previousDefaultId) {
        try {
            console.warn(`[LLM-DEFAULT] Attempting to revert unsetting of previous default ${previousDefaultId} due to error setting ${configId}.`);
            await updateLLMConfiguration(previousDefaultId, { is_default: true });
            await loadLLMConfigs(); // Reload again after attempted revert
        } catch (revertError: any) {
            console.error(`[LLM-DEFAULT] Failed to revert previous default ${previousDefaultId}:`, revertError);
            error.value += ` | Additionally, failed to restore previous default ${previousDefaultId}. Manual check recommended.`;
        }
    }

  } finally {
    isUpdating.value = false;
  }
}

// Watch for provider changes
watch(selectedProvider, () => {
  // Reset related state when provider changes
  availableOllamaModels.value = [];
  ollamaConnectionStatus.value = null;
  // Reset relevant parts of currentConfig, e.g.:
  if (currentConfig.ollama_config) {
      currentConfig.ollama_config.base_url = ''; // Or appropriate reset value
      currentConfig.ollama_config.model = '';
  }
  // Reset other provider configs as needed
  if (currentConfig.openai_config) {
    // ... reset openai config ...
  }
  // etc.
});

</script>

<style scoped>
.llm-management-view {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
  background-color: #f0f2f5;
}

.app-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 15px 30px;
  background-color: #ffffff;
  box-shadow: 0 2px 4px rgba(0,0,0,0.1);
  border-bottom: 1px solid #e0e0e0;
}

.logo-title {
  display: flex;
  align-items: center;
}

.logo {
  height: 40px;
  margin-right: 15px;
}

.app-header h1 {
  font-size: 1.5rem;
  font-weight: 500;
  color: #2c3e50;
  margin: 0;
}

.header-nav .nav-button {
  margin-left: 15px;
  padding: 8px 15px;
  border: 1px solid #007bff;
  background-color: #007bff;
  color: white;
  border-radius: 5px;
  text-decoration: none;
  font-size: 0.9rem;
  transition: background-color 0.2s ease, color 0.2s ease;
}
.header-nav .nav-button:hover {
  background-color: #0056b3;
}

.content-area {
  padding: 25px;
  flex-grow: 1;
}

.content-area h2 {
  font-size: 1.8rem;
  color: #2c3e50;
  margin-top: 0;
  margin-bottom: 20px;
}

.actions-bar {
  margin-bottom: 20px;
}

.action-button {
  padding: 10px 18px;
  border: none;
  border-radius: 5px;
  color: white;
  font-size: 0.95rem;
  cursor: pointer;
  transition: background-color 0.2s ease, opacity 0.2s ease;
  margin-right: 10px;
}
.action-button:disabled {
    opacity: 0.6;
    cursor: not-allowed;
}

.add-llm-button { background-color: #28a745; }
.add-llm-button:hover:not(:disabled) { background-color: #218838; }

.edit-button { background-color: #007bff; font-size: 0.85rem; padding: 6px 12px;}
.edit-button:hover:not(:disabled) { background-color: #0056b3; }

.delete-button { background-color: #dc3545; font-size: 0.85rem; padding: 6px 12px; }
.delete-button:hover:not(:disabled) { background-color: #c82333; }

.set-default-button {
    background-color: #6c757d;
    color: white;
    border: none;
    padding: 4px 8px;
    font-size: 0.8rem;
    border-radius: 4px;
    cursor: pointer;
}
.set-default-button:hover:not(:disabled) { background-color: #5a6268; }
.set-default-button:disabled { opacity: 0.5; cursor: not-allowed; }

.default-badge {
    background-color: #28a745;
    color: white;
    padding: 3px 7px;
    border-radius: 4px;
    font-size: 0.8rem;
    font-weight: bold;
}

.loading-message, .no-configs-message, .error-message {
  text-align: center;
  padding: 20px;
  font-size: 1rem;
  color: #555;
  background-color: #fff;
  border-radius: 8px;
  box-shadow: 0 2px 4px rgba(0,0,0,0.05);
}
.error-message { color: #c0392b; background-color: #f8d7da; border: 1px solid #f5c6cb; }

.llm-configs-list table {
  width: 100%;
  border-collapse: collapse;
  background-color: #fff;
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.07);
  overflow: hidden;
}

.llm-configs-list th, .llm-configs-list td {
  padding: 12px 15px;
  text-align: left;
  border-bottom: 1px solid #e0e0e0;
}

.llm-configs-list th {
  background-color: #f8f9fa;
  font-weight: 600;
  color: #343a40;
  font-size: 0.9rem;
  text-transform: uppercase;
}

.llm-configs-list tr:last-child td {
  border-bottom: none;
}

.llm-configs-list tr:hover {
  background-color: #f1f1f1;
}

.llm-configs-list code {
  background-color: #e9ecef;
  padding: 2px 5px;
  border-radius: 4px;
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, Courier, monospace;
  font-size: 0.85em;
}

.actions-cell {
    display: flex;
    gap: 8px;
}

.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background-color: rgba(0, 0, 0, 0.6);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 1000;
}

.modal-content {
  background-color: white;
  padding: 30px;
  border-radius: 8px;
  box-shadow: 0 5px 15px rgba(0, 0, 0, 0.3);
  width: 90%;
  max-width: 600px;
  max-height: 90vh;
  overflow-y: auto;
}

.modal-content h3 {
  margin-top: 0;
  margin-bottom: 25px;
  color: #333;
  font-size: 1.6rem;
}

.form-group {
  margin-bottom: 20px;
}

.form-group label {
  display: block;
  margin-bottom: 8px;
  font-weight: 500;
  color: #495057;
}

.form-group input[type="text"],
.form-group input[type="url"],
.form-group input[type="number"],
.form-group select {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid #ced4da;
  border-radius: 4px;
  box-sizing: border-box;
  font-size: 1rem;
}
.form-group input:disabled {
    background-color: #e9ecef;
    cursor: not-allowed;
}

.form-group small {
    font-size: 0.8rem;
    color: #6c757d;
    margin-top: 4px;
    display: block;
}

.checkbox-group {
    display: flex;
    align-items: center;
}
.checkbox-group input[type="checkbox"] {
    margin-right: 10px;
    width: auto;
    height: auto;
    transform: scale(1.2);
}

.provider-options {
    border: 1px solid #e0e0e0;
    border-radius: 6px;
    padding: 15px;
    margin-top: 15px;
    margin-bottom: 20px;
    background-color: #fdfdfd;
}
.provider-options h4 {
    margin-top: 0;
    margin-bottom: 15px;
    font-size: 1.1rem;
    color: #0056b3;
    border-bottom: 1px solid #eee;
    padding-bottom: 8px;
}

.modal-actions {
  margin-top: 30px;
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}

.save-button { background-color: #007bff; }
.save-button:hover:not(:disabled) { background-color: #0056b3; }
.cancel-button { background-color: #6c757d; }
.cancel-button:hover:not(:disabled) { background-color: #5a6268; }

.modal-error {
    margin-top: 15px;
    text-align: left;
    padding: 10px;
}

.section-box {
  border: 1px solid #e2e8f0;
  padding: 15px;
  margin-top: 15px;
  margin-bottom: 15px;
  border-radius: 8px;
  background-color: #f9fafb;
}

.section-title {
  font-size: 1.1em;
  font-weight: 600;
  margin-top: 0;
  margin-bottom: 5px;
  color: #334155;
}

.section-description {
  font-size: 0.9em;
  color: #64748b;
  margin-bottom: 15px;
}

.primary-button {
  background-color: #3b82f6;
  color: white;
  border: none;
}
.primary-button:hover {
  background-color: #2563eb;
}

.secondary-button {
  background-color: #e5e7eb;
  color: #374151;
  border: 1px solid #d1d5db;
}
.secondary-button:hover {
  background-color: #d1d5db;
}

.text-success {
  color: #28a745;
  font-weight: bold;
}

.text-danger {
  color: #dc3545;
  font-weight: bold;
}

.mt-2 {
    margin-top: 0.5rem;
}

.form-control {
    width: 100%;
    padding: 10px 12px;
    border: 1px solid #ced4da;
    border-radius: 4px;
    box-sizing: border-box;
    font-size: 1rem;
    background-color: white;
}

.connection-test {
  margin-bottom: 10px;
}

.connection-test button {
  margin-left: 10px;
}

.test-result {
  margin-left: 10px;
  font-weight: bold;
}

.model-fetch {
  margin-bottom: 10px;
}

.model-select-wrapper {
  display: flex;
  align-items: center;
}

.model-select-wrapper select {
  flex: 1;
}

.model-select-wrapper button {
  margin-left: 10px;
}

.load-models-btn {
  background-color: #007bff;
  color: white;
  border: none;
  padding: 6px 12px;
  border-radius: 4px;
  cursor: pointer;
  transition: background-color 0.2s ease;
}

.load-models-btn:hover:not(:disabled) {
  background-color: #0056b3;
}

.load-models-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

</style> 