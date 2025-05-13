<script setup lang="ts">
import { ref, onMounted, nextTick } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { getServers, removeServerConfig, type ServerConfig } from '../services/apiService';

const servers = ref<Record<string, ServerConfig>>({});
const isLoading = ref(true);
const error = ref<string | null>(null);
const router = useRouter();

async function fetchServers() {
  isLoading.value = true;
  error.value = null;
  try {
    servers.value = await getServers();
  } catch (err: any) {
    console.error('Failed to load server configurations:', err);
    error.value = err.message || 'An unknown error occurred while fetching server configs.';
  } finally {
    isLoading.value = false;
  }
}

function handleAddNewServerClick() {
  router.push('/server-configs/new');
}

function handleEditClick(serverKey: string) {
  router.push(`/server-configs/edit/${serverKey}`);
}

async function handleDeleteServer(serverKey: string) {
  if (!confirm(`Are you sure you want to delete server '${serverKey}'?`)) return;
  isLoading.value = true;
  try {
    await removeServerConfig(serverKey);
    await fetchServers();
  } catch (err:any) {
    alert('Error deleting server: ' + (err.message || 'Unknown error'));
  } finally {
    isLoading.value = false;
  }
}

onMounted(async () => {
  await fetchServers();
  const route = useRoute();
  const serverToFocus = route.query.focusServer as string;

  if (serverToFocus) {
    await nextTick();
    const element = document.getElementById(`server-card-wrapper-${serverToFocus}`);
    if (element) {
      element.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }
});

</script>

<template>
  <div class="server-config-dashboard">
    <header class="dashboard-header">
      <h1>Server Configuration Management</h1>
      <button @click="handleAddNewServerClick" class="action-button add-new-button">
        + Add New Server
      </button>
    </header>

    <div v-if="isLoading && Object.keys(servers).length === 0" class="loading-message">Loading server configurations...</div>
    <div v-if="error" class="error-message">{{ error }}</div>

    <div class="server-cards-container" v-if="!isLoading || Object.keys(servers).length > 0">
      <div v-for="(config, key) in servers" 
           :key="key" 
           :id="`server-card-wrapper-${key}`" 
           class="server-card-wrapper">

        <div class="server-card-display">
          <h3>{{ config.display_name || key }}</h3>
          <p><strong>Key:</strong> {{ key }}</p>
          <p><strong>Command:</strong> {{ config.command }}</p>
          <p v-if="config.args && config.args.length"><strong>Args:</strong> {{ config.args.join(' ') }}</p>
          <p v-if="config.description"><strong>Desc:</strong> {{ config.description }}</p>
          <div class="card-actions">
            <button @click="handleEditClick(key)" class="action-button edit-button">Edit</button>
            <button @click="handleDeleteServer(key)" class="action-button delete-button">Delete</button>
          </div>
        </div>
      </div>
      
      <div v-if="Object.keys(servers).length === 0 && !isLoading && !error" class="no-servers-message">
        No server configurations found. Click "+ Add New Server" to create one.
      </div>
    </div>
  </div>
</template>

<style scoped>
.server-config-dashboard {
  padding: 25px;
  font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
  background-color: #f4f7f6;
  min-height: 100vh;
}

.dashboard-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 25px;
  padding-bottom: 15px;
  border-bottom: 1px solid #d1d9e6;
}

.dashboard-header h1 {
  color: #2c3e50;
  font-size: 1.8em;
  font-weight: 600;
}

.loading-message, .error-message, .no-servers-message {
  padding: 20px;
  margin: 20px auto;
  border-radius: 8px;
  text-align: center;
  max-width: 600px;
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

.no-servers-message {
  background-color: #f8f9fa;
  border: 1px solid #e9ecef;
  color: #6c757d;
  grid-column: 1 / -1;
}

.server-cards-container {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(400px, 1fr));
  gap: 25px;
}

.server-card-display {
  border: 1px solid #d1d9e6;
  border-radius: 10px;
  padding: 20px;
  background-color: #ffffff;
  box-shadow: 0 4px 8px rgba(0,0,0,0.05);
  display: flex;
  flex-direction: column;
  transition: box-shadow 0.3s ease-in-out, opacity 0.3s ease;
  min-height: 200px;
}

.server-card-display:hover {
    box-shadow: 0 6px 12px rgba(0,0,0,0.1);
}

.server-card-display h3 {
  margin-top: 0;
  color: #2c3e50;
  border-bottom: 1px solid #e0e0e0;
  padding-bottom: 12px;
  margin-bottom: 15px;
  font-size: 1.3em;
  font-weight: 600;
}

.server-card-display p {
  font-size: 0.95em;
  line-height: 1.5;
  margin-bottom: 8px;
  color: #495057;
}

.server-card-display strong {
    color: #343a40;
}

.card-actions {
  margin-top: auto;
  padding-top: 15px;
  border-top: 1px solid #e0e0e0;
  display: flex;
  gap: 10px;
  justify-content: flex-end;
}

.action-button {
  padding: 8px 15px;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 0.9em;
  font-weight: 500;
  transition: background-color 0.2s ease, transform 0.1s ease;
}
.action-button:hover:not(:disabled) {
    transform: translateY(-1px);
}
.action-button:disabled {
  background-color: #e9ecef !important; 
  color: #6c757d !important;
  cursor: not-allowed;
  transform: none;
}

.add-new-button {
  background-color: #007bff;
  color: white;
}
.add-new-button:hover:not(:disabled) {
  background-color: #0069d9;
}

.edit-button {
  background-color: #ffc107; 
  color: #212529;
}
.edit-button:hover:not(:disabled) {
  background-color: #e0a800;
}

.delete-button {
  background-color: #dc3545;
  color: white;
}
.delete-button:hover:not(:disabled) {
  background-color: #c82333;
}

</style> 