<script setup lang="ts">
import { ref, onMounted, computed, reactive } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import ServerConfigCard from '../components/ServerConfigCard.vue';
import { getServers, addServer, updateServerConfig, type ServerConfig } from '../services/apiService'; // Assuming removeServerConfig will be handled by ServerConfigCard or here if needed
import LLMErrorAlert from '../components/LLMErrorAlert.vue';

const route = useRoute();
const router = useRouter();

const isLoading = ref(false);
const error = ref<string | null>(null);
const serverKeyToEdit = ref<string | null>(null);
const isNewMode = ref(false);

const formConfigData = reactive<ServerConfig>({
  name: '',
  display_name: '',
  command: '',
  args: [],
  transport: 'stdio',
  cwd: '',
  env: {},
  description: '',
  capabilities_for_tool_config: [],
});

const pageTitle = computed(() => {
  if (isNewMode.value) {
    return 'Create New Server Configuration';
  }
  return `Edit Server: ${serverKeyToEdit.value || 'Loading...'}`;
});

const cardServerKey = computed(() => {
    return isNewMode.value ? '__NEW_SERVER_FORM__' : serverKeyToEdit.value;
});

onMounted(async () => {
  const routeServerName = route.params.serverName as string;
  if (routeServerName) {
    // Edit mode
    isNewMode.value = false;
    serverKeyToEdit.value = routeServerName;
    isLoading.value = true;
    try {
      // In a real scenario, you might have an API endpoint to get a single server's config
      // For now, we fetch all and find the one.
      const allServers = await getServers();
      if (allServers[routeServerName]) {
        Object.assign(formConfigData, JSON.parse(JSON.stringify(allServers[routeServerName])));
      } else {
        error.value = `Server configuration for "${routeServerName}" not found.`;
      }
    } catch (err: any) {
      console.error('Failed to load server configuration for editing:', err);
      error.value = err.message || 'An unknown error occurred.';
    } finally {
      isLoading.value = false;
    }
  } else {
    // New mode (e.g., if route is /server-configs/new)
    isNewMode.value = true;
    serverKeyToEdit.value = null; // Clear any previous edit state
    // Reset formConfigData to defaults for a new server
    Object.assign(formConfigData, {
        name: '',
        display_name: '',
        command: '',
        args: [],
        transport: 'stdio',
        cwd: '',
        env: {},
        description: '',
        capabilities_for_tool_config: [],
    });
  }
});

async function handleSaveConfig(configToSave: ServerConfig) {
  isLoading.value = true; // Indicate processing
  error.value = null;
  try {
    if (isNewMode.value) {
      if (!configToSave.name || !configToSave.name.trim()) {
        alert('Server Name (Configuration Key) is required for a new server.');
        isLoading.value = false;
        return;
      }
      // Consider checking for duplicate server names if fetching all servers first isn't too slow
      // const allServers = await getServers();
      // if (allServers[configToSave.name]) {
      //     alert(`Server with key "${configToSave.name}" already exists.`);
      //     isLoading.value = false;
      //     return;
      // }
      await addServer(configToSave.name, configToSave);
      alert('Server created successfully!');
    } else if (serverKeyToEdit.value) {
      await updateServerConfig(serverKeyToEdit.value, configToSave);
      alert('Server updated successfully!');
    }
    router.push('/server-configs'); // Navigate back to the list after save
  } catch (err: any) {
    console.error('Error saving server configuration:', err);
    error.value = 'Error saving configuration: ' + (err.message || 'Unknown error');
    // alert here or display error.value in template
  } finally {
    isLoading.value = false;
  }
}

function handleCancelForm() {
  router.push('/server-controls'); // Navigate to the server controls dashboard
}

// Delete is handled by ServerConfigCard, which emits 'delete'.
// If this view needs to react (e.g., navigate after delete), we'd add that handler.
// For now, assuming ServerConfigCard's delete + subsequent navigation (if any) is sufficient
// OR, if ServerConfigCard expects parent to handle deletion API call & navigation:
/*
async function handleDeleteServer(serverKeyToDelete: string) {
    if (!confirm(`Are you sure you want to delete server '${serverKeyToDelete}'?`)) return;
    isLoading.value = true;
    error.value = null;
    try {
        // await actualDeleteApiCall(serverKeyToDelete);
        alert('Server deleted successfully!'); // Placeholder
        router.push('/server-configs');
    } catch (err: any) {
        console.error('Error deleting server:', err);
        error.value = 'Error deleting server: ' + (err.message || 'Unknown error');
    } finally {
        isLoading.value = false;
    }
}
*/

</script>

<template>
  <div class="server-config-form-view">
    <div v-if="isLoading && !error" class="loading-message">Loading configuration...</div>
    <div v-if="error" class="error-message">
      Error: {{ error }}
    </div>
    <LLMErrorAlert v-if="error" :message="error" />

    <div v-if="!isLoading && !error" class="form-container">
      <ServerConfigCard
        :initialConfig="formConfigData"
        :serverKey="cardServerKey!" 
        :isNew="isNewMode"
        :isProcessing="isLoading" 
        :errorMessage="error ?? undefined" 
        @save="handleSaveConfig"
        @cancel="handleCancelForm"
        class="config-form-card"
        />
        <!-- If ServerConfigCard emits delete and expects parent to handle API call:
        @delete="handleDeleteServer" 
        -->
    </div>
  </div>
</template>

<style scoped>
.server-config-form-view {
  max-width: 800px;
  margin: 0 auto;
  padding: 25px;
  font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
}

.loading-message, .error-message {
  padding: 15px;
  margin: 20px 0;
  border-radius: 6px;
  text-align: center;
}

.loading-message {
  background-color: #e0ebaf;
  border: 1px solid #b3d4fc;
  color: #004085;
}

.error-message {
  background-color: #f8d7da;
  border: 1px solid #f5c6cb;
  color: #721c24;
}

.form-container {
  /* Styles for the container of ServerConfigCard if needed */
}

.config-form-card {
  /* ServerConfigCard has its own styles, but you can add overrides or container styles here */
  /* For example, if you wanted to ensure it's not overly wide on this dedicated page */
}
</style> 