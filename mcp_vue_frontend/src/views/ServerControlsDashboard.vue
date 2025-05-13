<script setup lang="ts">
import { ref, onMounted, reactive } from 'vue';
import { useRouter } from 'vue-router';
import { 
    getServers, 
    startServer as apiStartServer, 
    stopServer as apiStopServer, 
    getServerStatus as apiGetServerStatus,
    refreshServerCapabilities as apiRefreshServerCapabilities,
    removeServerConfig as apiRemoveServerConfig,
    updateLLMActiveTools,
    type ServerConfig,
    updateServerConfig,
    // deleteServerConfig as apiDeleteServerConfig, // Assuming this will be added to apiService
} from '../services/apiService';

interface ServerStatusInfo {
  status: string;
  message?: string;
  pid?: number;
  discovered_capabilities?: Array<{ name: string; description?: string }>;
  last_updated_timestamp?: string; 
}

const servers = ref<Record<string, ServerConfig>>({});
const serverStatuses = reactive<Record<string, ServerStatusInfo>>({});
const error = ref<string | null>(null);
const isLoading = ref<boolean>(true);
const actionFeedback = reactive<Record<string, { message: string; type: 'success' | 'error' } | null>>({});
const router = useRouter();

// New state for LLM sync
const isLlmSyncing = ref(false);
const llmSyncMessage = ref<{ text: string; type: 'success' | 'error' } | null>(null);

function formatTimestamp(isoTimestamp?: string): string {
  if (!isoTimestamp) return 'N/A';
  try {
    // More user-friendly format
    const date = new Date(isoTimestamp);
    return date.toLocaleDateString(undefined, { year: 'numeric', month: 'numeric', day: 'numeric' }) + ' ' + 
           date.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  } catch (e) {
    console.error("Failed to format timestamp:", e);
    return 'Invalid Date';
  }
}

async function fetchInitialData() {
  isLoading.value = true;
  try {
    servers.value = await getServers();
    await fetchInitialStatuses();
    error.value = null;
  } catch (err: any) {
    console.error('Failed to load initial data for dashboard:', err);
    error.value = err.message || 'An unknown error occurred.';
    servers.value = {};
  } finally {
    isLoading.value = false;
  }
}

async function fetchInitialStatuses() {
    for (const serverName of Object.keys(servers.value)) {
        try {
            const statusResponse = await apiGetServerStatus(serverName);
            serverStatuses[serverName] = { 
                status: statusResponse.status,
                message: statusResponse.message,
                pid: statusResponse.pid,
                discovered_capabilities: statusResponse.discovered_capabilities || [],
                last_updated_timestamp: statusResponse.last_updated_timestamp || new Date().toISOString()
            };
        } catch (err: any) {
            console.error(`Failed to get initial status for ${serverName}:`, err);
            serverStatuses[serverName] = { 
                status: 'unknown', 
                message: err.message || 'Failed to fetch status', 
                discovered_capabilities: [],
                last_updated_timestamp: new Date().toISOString() // Timestamp of the failed attempt
            };
        }
    }
}

onMounted(fetchInitialData);

async function handleStartServer(serverName: string) {
    if (!serverName || !servers.value[serverName]) {
        console.error(`[DASHBOARD] Invalid server name or server not found:`, serverName);
        actionFeedback[serverName] = { message: 'Invalid server.', type: 'error' };
        return;
    }
    actionFeedback[serverName] = null;
    serverStatuses[serverName] = { // Set an immediate "starting" state
        ...(serverStatuses[serverName] || {}),
        status: 'starting',
        message: `Server ${serverName} is initiating start...`,
        // pid: undefined, // Explicitly clear pid on start attempt if desired
        // discovered_capabilities: [], // Optionally clear capabilities on start attempt
        last_updated_timestamp: new Date().toISOString()
    };

    try {
        console.log(`[DASHBOARD] Attempting to start server: ${serverName}`);
        const initialResponse = await apiStartServer(serverName);

        // Update with initial response (might still be "starting" or "error" if immediate failure)
        serverStatuses[serverName] = { 
            ...(serverStatuses[serverName] || {}), // Preserve any previous info not in initialResponse
            status: initialResponse.status, 
            message: initialResponse.message, 
            // pid and discovered_capabilities are usually NOT in the initialResponse from /start for background processes
            // They will be populated by the follow-up fetchServerStatus
            last_updated_timestamp: initialResponse.last_updated_timestamp || new Date().toISOString()
        };

        actionFeedback[serverName] = { 
            message: initialResponse.message || `Server ${serverName} start initiated.`, 
            type: initialResponse.status === 'error' || initialResponse.status === 'unknown' ? 'error' : 'success' 
        };

        // If the server is reported as starting or potentially running from the initial call,
        // schedule a follow-up status check to get full details including capabilities.
        if (initialResponse.status === 'starting' || initialResponse.status === 'running') {
            setTimeout(async () => {
                console.log(`[DASHBOARD] Follow-up status check for ${serverName} after start attempt.`);
                await fetchServerStatus(serverName); // This will update with PID and capabilities
            }, 3000); // Delay for 3 seconds (adjustable) to allow backend to process
        } else if (initialResponse.status === 'error' || initialResponse.status === 'unknown') {
            // If immediate error or unknown, still refresh status to get a definitive state
             await fetchServerStatus(serverName);
        }

    } catch (err: any) {
        console.error(`[DASHBOARD] Failed to start server ${serverName}:`, err);
        actionFeedback[serverName] = { message: err.response?.data?.detail || err.message || `Failed to start ${serverName}.`, type: 'error' };
        await fetchServerStatus(serverName); // This will update the timestamp
    }
}

async function handleStopServer(serverName: string) {
    if (!serverName || !servers.value[serverName]) {
        console.error(`[DASHBOARD] Invalid server name or server not found:`, serverName);
        actionFeedback[serverName] = { message: 'Invalid server.', type: 'error' };
        return;
    }
    actionFeedback[serverName] = null;
    try {
        console.log(`[DASHBOARD] Attempting to stop server: ${serverName}`);
        const response = await apiStopServer(serverName);
        serverStatuses[serverName] = { 
            status: response.status, 
            message: response.message,
            pid: response.pid, // Stop might clear PID
            discovered_capabilities: response.status === 'stopped' ? [] : (response.discovered_capabilities || serverStatuses[serverName]?.discovered_capabilities),
            last_updated_timestamp: new Date().toISOString()
        };
        actionFeedback[serverName] = { message: response.message || `Server ${serverName} stopped.`, type: 'success' };
    } catch (err: any) {
        console.error(`[DASHBOARD] Failed to stop server ${serverName}:`, err);
        actionFeedback[serverName] = { message: err.response?.data?.detail || err.message || `Failed to stop ${serverName}.`, type: 'error' };
        await fetchServerStatus(serverName); // This will update the timestamp
    }
}

async function fetchServerStatus(serverName: string) {
    if (!serverName || !servers.value[serverName]) {
        console.error(`[DASHBOARD] Invalid server name or server not found for status refresh:`, serverName);
        actionFeedback[serverName] = { message: 'Invalid server for status refresh.', type: 'error' };
        if (serverStatuses[serverName]) { // Still update timestamp for the attempt
            serverStatuses[serverName].last_updated_timestamp = new Date().toISOString();
        }
        return;
    }
    // Do not clear actionFeedback[serverName] = null; here, let the caller manage overall feedback.
    // Or, if this is a direct user action (Refresh Status button), then clear it.
    // Assuming direct user action if called from template.
    // For now, let's clear it when called directly. If it's called from other error handlers, they'll set their own.
    // This makes the "Refresh Status" button give its own feedback.
    // actionFeedback[serverName] = null; // Decided to let specific callers manage actionFeedback.

    try {
        console.log(`[DASHBOARD] Refreshing status for server: ${serverName}`);
        const statusResponse = await apiGetServerStatus(serverName);
        serverStatuses[serverName] = { 
            status: statusResponse.status,
            message: statusResponse.message,
            pid: statusResponse.pid,
            discovered_capabilities: statusResponse.discovered_capabilities || serverStatuses[serverName]?.discovered_capabilities || [],
            last_updated_timestamp: statusResponse.last_updated_timestamp || new Date().toISOString()
        };
        actionFeedback[serverName] = { message: `Status for ${serverName} refreshed.`, type: 'success' }; // Provide feedback for direct refresh
    } catch (err: any) {
        console.error(`[DASHBOARD] Failed to get status for ${serverName}:`, err);
        const existingStatus = serverStatuses[serverName] || {};
        serverStatuses[serverName] = { 
            ...existingStatus, // Preserve old capabilities if fetch fails
            status: 'unknown', 
            message: err.message || 'Failed to fetch status',
            last_updated_timestamp: new Date().toISOString()
        };
        actionFeedback[serverName] = { message: `Failed to refresh status for ${serverName}.`, type: 'error' }; // Provide feedback for direct refresh
    }
}

async function handleRefreshCapabilities(serverName: string) {
    if (!serverName || !servers.value[serverName]) {
        console.error(`[DASHBOARD] Invalid server name or server not found for caps refresh:`, serverName);
        actionFeedback[serverName] = { message: 'Invalid server for capabilities refresh.', type: 'error' };
        return;
    }
    actionFeedback[serverName] = null;
    try {
        console.log(`[DASHBOARD] Refreshing capabilities for server: ${serverName}`);
        const response = await apiRefreshServerCapabilities(serverName);
        serverStatuses[serverName] = { 
            status: response.status, 
            message: response.message, 
            pid: response.pid,
            discovered_capabilities: response.discovered_capabilities || [], // Refresh should replace old caps
            last_updated_timestamp: new Date().toISOString()
        };
        actionFeedback[serverName] = { message: `Capabilities for ${serverName} refreshed.`, type: 'success' };
         if (response.status === 'running' && response.discovered_capabilities) {
            console.log(`[DASHBOARD] ${serverName} capabilities:`, response.discovered_capabilities);
        }
    } catch (err: any) {
        console.error(`[DASHBOARD] Failed to refresh capabilities for ${serverName}:`, err);
        actionFeedback[serverName] = { message: err.response?.data?.detail || err.message ||`Failed to refresh capabilities for ${serverName}.`, type: 'error' };
        // Update timestamp to reflect this failed attempt, then refresh overall status
        if(serverStatuses[serverName]) {
            serverStatuses[serverName].last_updated_timestamp = new Date().toISOString();
        }
        await fetchServerStatus(serverName); // Refresh full status, which will also update timestamp
    }
}

function handleEditServer(serverName: string) {
    console.log(`[DASHBOARD] Edit server clicked: ${serverName}`);
    router.push({ path: `/server-configs/edit/${serverName}` });
}

async function handleRemoveServer(serverName: string) {
    console.log(`[DASHBOARD] Remove server clicked: ${serverName}`);
    if (window.confirm(`Are you sure you want to remove the server configuration for "${serverName}"? This action cannot be undone.`)) {
        actionFeedback[serverName] = { message: `Attempting to remove ${serverName}...`, type: 'success' };
        try {
            const response = await apiRemoveServerConfig(serverName);
            console.log(`[DASHBOARD] "${serverName}" removal response:`, response);
            
            if (response.success) {
                // If successful, remove from local state
                delete servers.value[serverName];
                delete serverStatuses[serverName];
                delete actionFeedback[serverName]; // Clear specific feedback or set new success
                // Optionally, show a global success message if you have a system for it.
                console.log(`[DASHBOARD] "${serverName}" successfully removed.`);
            } else {
                throw new Error(response.message || `Failed to remove ${serverName} due to a server-side issue.`);
            }
        } catch (err: any) {
            console.error(`[DASHBOARD] Failed to remove server ${serverName}:`, err);
            actionFeedback[serverName] = { message: err.message || `Failed to remove ${serverName}.`, type: 'error' };
        }
    } else {
        console.log(`[DASHBOARD] Removal of ${serverName} cancelled by user.`);
        actionFeedback[serverName] = { message: `Removal of ${serverName} cancelled.`, type: 'success' };
        setTimeout(() => { 
            if (actionFeedback[serverName]?.message === `Removal of ${serverName} cancelled.`) {
                actionFeedback[serverName] = null; 
            }
        }, 3000);
    }
}

async function handleToggleShell(serverName: string) {
    const serverConfig = servers.value[serverName];
    if (!serverConfig) {
        console.error(`[DASHBOARD] Config not found for ${serverName} on shell toggle.`);
        actionFeedback[serverName] = { message: `Configuration for ${serverName} not found.`, type: 'error' };
        return;
    }

    // The checkbox v-model directly updates serverConfig.shell, so it should be the new value.
    const newShellValue = serverConfig.shell === undefined ? false : serverConfig.shell; // Ensure boolean

    actionFeedback[serverName] = { message: `Updating 'Use Shell' for ${serverName}...`, type: 'success' };

    try {
        // Create a new object for the update to ensure reactivity if needed, though direct mutation might also work
        const updatedConfig: ServerConfig = {
            ...serverConfig, // Spread existing config
            shell: newShellValue // Set the new shell value
        };

        // Ensure args is an array if it became undefined/null during spread or otherwise
        if (!updatedConfig.args) {
            updatedConfig.args = [];
        }
        
        console.log(`[DASHBOARD] Updating shell for ${serverName} to ${newShellValue}. Config to send:`, JSON.parse(JSON.stringify(updatedConfig)));

        // We need to pass the original serverName (config key) as the first argument if the API expects it
        // and the config object as the second.
        // The `updateServerConfig` in apiService.ts takes `(serverId: string, config: ServerConfig)`
        await updateServerConfig(serverName, updatedConfig);

        // Update local state to reflect the persisted change
        servers.value[serverName].shell = newShellValue;
        actionFeedback[serverName] = { message: `'Use Shell' for ${serverName} updated to ${newShellValue}.`, type: 'success' };

    } catch (err: any) {
        console.error(`[DASHBOARD] Failed to update shell for ${serverName}:`, err);
        actionFeedback[serverName] = { message: err.message || `Failed to update shell for ${serverName}.`, type: 'error' };
        // Revert local change on error
        servers.value[serverName].shell = !newShellValue; 
    }
}

function navigateToAddServerConfig() {
    router.push({ path: '/server-configs/new' });
}

// Function to gather active capabilities
function getActiveCapabilities(): Record<string, Array<{ name: string; description?: string; inputSchema?: any }>> {
    const activeCaps: Record<string, Array<{ name: string; description?: string; inputSchema?: any }>> = {};
    for (const serverName in serverStatuses) {
        const statusInfo = serverStatuses[serverName];
        if (statusInfo && (statusInfo.status === 'running' || statusInfo.status === 'connected') && statusInfo.discovered_capabilities && statusInfo.discovered_capabilities.length > 0) {
            // Ensure we only pass name, description, and inputSchema if they exist
            activeCaps[serverName] = statusInfo.discovered_capabilities.map(cap => ({
                name: cap.name,
                ...(cap.description && { description: cap.description }),
                // Assuming inputSchema is already in the correct format or not needed for this payload
                // If inputSchema is needed and its structure is complex, ensure it's correctly passed
            }));
        }
    }
    return activeCaps;
}

// Function to send capabilities to LLM
const sendCapabilitiesToLLM = async () => {
  isLlmSyncing.value = true;
  llmSyncMessage.value = null;
  // actionFeedback.value = {}; // Clear other feedbacks <-- Incorrect
  // Fix: Clear actionFeedback correctly
  Object.keys(actionFeedback).forEach(key => {
      actionFeedback[key] = null;
  });

  const activeCapsPayload = getActiveCapabilities();

  if (Object.keys(activeCapsPayload).length === 0) {
    llmSyncMessage.value = { text: 'No active servers with capabilities to send.', type: 'error' };
    setTimeout(() => llmSyncMessage.value = null, 5000);
    isLlmSyncing.value = false;
    console.log("[DASHBOARD LLM SYNC] No active capabilities to send.", activeCapsPayload);
    return;
  }

  try {
    console.log("[DASHBOARD LLM SYNC] Sending active capabilities to LLM:", JSON.stringify(activeCapsPayload, null, 2));
    const response = await updateLLMActiveTools(activeCapsPayload);
    llmSyncMessage.value = { text: response.message || 'Capabilities sent to LLM successfully!', type: 'success' };
    console.log("[DASHBOARD LLM SYNC] Successfully sent capabilities to LLM:", response);
  } catch (error: any) {
    console.error("[DASHBOARD LLM SYNC] Error sending capabilities to LLM:", error);
    llmSyncMessage.value = { text: error.message || 'Failed to send capabilities to LLM.', type: 'error' };
  } finally {
    console.log("[DASHBOARD LLM SYNC] Sync process finished.");
    isLlmSyncing.value = false;
    setTimeout(() => llmSyncMessage.value = null, 5000); // Clear message after 5s
  }
};

</script>

<template>
  <div class="server-controls-dashboard">
    <div class="dashboard-header-controls">
      <h2>MCP Server Dashboard</h2>
      <div class="header-buttons-group">
        <button @click="router.push('/')" class="action-button back-to-chat-button">
          <span>返回聊天</span>
        </button>
        <button @click="sendCapabilitiesToLLM" class="action-button llm-sync-button" :disabled="isLlmSyncing">
          <span v-if="isLlmSyncing">Syncing with LLM...</span>
          <span v-else>Send Active Capabilities to LLM</span>
        </button>
        <button @click="navigateToAddServerConfig" class="action-button add-server-config-button">
          + Add / Configure Servers
        </button>
      </div>
    </div>

    <div v-if="llmSyncMessage" :class="['llm-sync-feedback-message', llmSyncMessage.type]">
      {{ llmSyncMessage.text }}
    </div>

    <div v-if="isLoading" class="loading-message">Loading server information...</div>
    <div v-if="error" class="error-message">Error: {{ error }}</div>
    
    <div v-if="!isLoading && !error" class="server-list">
      <div v-for="(config, serverName) in servers" :key="serverName" class="server-item">
        
        <div class="server-item-header">
          <span class="server-name-display">{{ config.display_name || (serverName as string) }}</span>
          <span :class="`status-badge status-${serverStatuses[serverName as string]?.status}`">{{ serverStatuses[serverName as string]?.status || 'N/A' }}</span>
        </div>

        <div class="command-line-display" v-if="config.command">
          {{ config.command }} {{ config.args?.join(' ') }}
        </div>

        <div v-if="serverStatuses[serverName as string]?.discovered_capabilities && Array.isArray(serverStatuses[serverName as string]?.discovered_capabilities) && (serverStatuses[serverName as string]!.discovered_capabilities!).length > 0" class="capabilities-section">
          <h4>Discovered Capabilities:</h4>
          <div class="capabilities-pills">
            <span 
              v-for="(cap, index) in serverStatuses[serverName as string].discovered_capabilities" 
              :key="index" 
              class="capability-pill"
            >
              {{ cap.name }}
            </span>
          </div>
        </div>
        <div v-else-if="serverStatuses[serverName as string]?.status === 'running' || serverStatuses[serverName as string]?.status === 'connected'" class="capabilities-section">
          <h4>Capabilities</h4>
          <p class="no-capabilities-text">No capabilities discovered or server not providing them.</p>
        </div>

        <p class="last-updated-timestamp">
          Last updated: {{ formatTimestamp(serverStatuses[serverName as string]?.last_updated_timestamp) }}
        </p>

        <div class="server-actions">
          <button @click="handleStartServer(serverName as string)" :disabled="serverStatuses[serverName as string]?.status === 'running' || serverStatuses[serverName as string]?.status === 'connected'" class="action-button start-button">Start</button>
          <button @click="handleStopServer(serverName as string)" :disabled="serverStatuses[serverName as string]?.status === 'stopped' || serverStatuses[serverName as string]?.status === 'disconnected' || !serverStatuses[serverName as string]?.status" class="action-button stop-button">Stop</button>
          <button @click="fetchServerStatus(serverName as string)" class="action-button refresh-button">Refresh Status</button>
          <button @click="handleRefreshCapabilities(serverName as string)" :disabled="serverStatuses[serverName as string]?.status !== 'running' && serverStatuses[serverName as string]?.status !== 'connected'" class="action-button capabilities-button">Refresh Capabilities</button>
          <button @click="handleEditServer(serverName as string)" class="action-button edit-button">Edit</button>
          <button @click="handleRemoveServer(serverName as string)" class="action-button remove-button">Remove</button>
        </div>
        <div class="server-shell-toggle form-section-checkbox">
          <label :for="`shell-toggle-${serverName}`" class="checkbox-label">
            <input 
              type="checkbox" 
              :id="`shell-toggle-${serverName}`" 
              v-model="config.shell" 
              @change="handleToggleShell(serverName)"
            />
            Use Shell
          </label>
        </div>
        <div v-if="actionFeedback[serverName as string]" :class="['feedback-message', actionFeedback[serverName as string]?.type]">
          {{ actionFeedback[serverName as string]?.message }}
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.server-controls-dashboard {
  padding: 25px;
  font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
  background-color: #2D2D2D; /* Dark background for the page */
  color: #EAEAEA; /* Light text color for the page */
  min-height: 100vh; /* Ensure dark background covers full viewport height */
}

.dashboard-header-controls {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px; /* Reduced margin slightly */
  padding-bottom: 20px; /* Increased padding for visual separation */
  border-bottom: 1px solid #4A4A4A; /* Slightly lighter border for definition */
}

.header-buttons-group {
  display: flex;
  gap: 12px; /* Slightly reduced gap */
}

.server-controls-dashboard h2 {
  color: #EAEAEA; 
  margin: 0; 
  font-weight: 600;
  font-size: 1.8em; /* Slightly larger title */
  text-align: left; /* Ensure left alignment */
}

/* Updated Button Styles to match image */
.action-button.llm-sync-button,
.action-button.add-server-config-button {
  background-color: #3F3F3F; /* Subtle dark background for buttons */
  color: #E0E0E0;
  padding: 8px 15px;
  font-size: 0.85em; /* Slightly smaller font for these header buttons */
  border-radius: 6px;
  transition: background-color 0.2s ease, border-color 0.2s ease, color 0.2s ease;
}

.action-button.llm-sync-button {
  border: 1px solid #7E57C2; /* Purple border */
}
.action-button.llm-sync-button:hover:not(:disabled) {
  background-color: #4A4A4A;
  border-color: #A07ED8;
  color: #F0F0F0;
}
.action-button.llm-sync-button:disabled {
  background-color: #333;
  border-color: #5E478C;
  color: #7A6A96;
}

.action-button.add-server-config-button {
  border: 1px solid #00acc1; /* Teal border */
}
.action-button.add-server-config-button:hover:not(:disabled) {
  background-color: #4A4A4A;
  border-color: #4DD0E1;
  color: #F0F0F0;
}

/* Styling for the LLM sync feedback message to match image */
.llm-sync-feedback-message {
  padding: 12px 20px;
  margin-bottom: 25px; /* More space below */
  border-radius: 8px; /* More pronounced rounding */
  text-align: center;
  font-size: 0.9em;
  width: 100%; /* Make it span wider */
  box-sizing: border-box; /* Include padding and border in the element's total width and height */
}
.llm-sync-feedback-message.success {
  background-color: #3E8E41; /* Green background from image */
  color: #FFFFFF; /* White text */
  border: 1px solid #388E3C; /* Slightly darker green border */
}
.llm-sync-feedback-message.error {
  background-color: #D32F2F; /* Red background for errors */
  color: #FFFFFF; /* White text */
  border: 1px solid #C62828; /* Slightly darker red border */
}

.loading-message, .error-message { /* General error/loading messages, not the LLM one */
  padding: 15px;
  margin-bottom: 20px;
  border-radius: 6px;
  text-align: center;
  border: 1px solid #444; 
}

.loading-message {
  background-color: #3A3A3A; 
  color: #A0C8F0; 
}

.error-message {
  background-color: #5A3A3A; 
  color: #F0A0A0; 
}

.server-list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(380px, 1fr));
  gap: 25px;
}

.server-item {
  border: 1px solid #4A4A4A; 
  border-radius: 10px;
  padding: 20px;
  background-color: #3C3C3C; 
  box-shadow: 0 4px 8px rgba(0,0,0,0.3); 
  transition: box-shadow 0.3s ease-in-out, transform 0.3s ease-in-out;
  display: flex;
  flex-direction: column;
}

.server-item:hover {
  box-shadow: 0 6px 12px rgba(0,0,0,0.5);
  transform: translateY(-3px);
}

.server-item-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  border-bottom: 1px solid #555;
  padding-bottom: 12px;
}

.server-name-display {
  font-size: 1.3em; 
  color: #E0E0E0;
  font-weight: 600;
}

.status-badge {
  padding: 5px 12px;
  border-radius: 15px; 
  font-size: 0.85em;
  font-weight: bold;
  color: #FFFFFF; 
  text-transform: capitalize;
}

.status-badge.status-running,
.status-badge.status-connected {
  background-color: #4CAF50; 
}
.status-badge.status-stopped,
.status-badge.status-disconnected {
  background-color: #D32F2F; 
}
.status-badge.status-error {
  background-color: #FF9800; 
}
.status-badge.status-unknown,
.status-badge.status-starting,
.status-badge.status-stopping {
  background-color: #757575; 
}

.command-line-display {
  background-color: #2a2a2a; 
  color: #B0B0B0;
  padding: 8px 12px;
  border-radius: 6px;
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, Courier, monospace;
  font-size: 0.85em;
  margin-bottom: 15px;
  word-break: break-all; 
  border: 1px solid #454545;
}

.capabilities-section {
  margin-bottom: 15px; 
}

.capabilities-section h4 {
  font-size: 1.05em; 
  color: #DCDCDC;
  margin-top: 0; 
  margin-bottom: 10px;
  font-weight: 600;
}

.capabilities-pills {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.capability-pill {
  background-color: #5A5A5A; 
  color: #E0E0E0;
  padding: 5px 10px;
  border-radius: 15px; 
  font-size: 0.8em;
  line-height: 1.4;
  box-shadow: 0 1px 2px rgba(0,0,0,0.2);
}

.no-capabilities-text {
    font-size: 0.9em;
    color: #9e9e9e;
    font-style: italic;
}

.last-updated-timestamp {
  font-size: 0.8em;
  color: #9E9E9E; 
  margin-top: auto; 
  padding-top: 10px; 
  margin-bottom: 15px; 
  text-align: left;
}

.server-actions {
  margin-top: 15px; 
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

/* General action button style (for card buttons) */
.server-actions .action-button {
  padding: 8px 12px;
  border: 1px solid #888; 
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.9em;
  background-color: transparent; 
  color: #DADADA; 
  transition: background-color 0.2s ease, color 0.2s ease, border-color 0.2s ease;
}

.server-actions .action-button:disabled {
  border-color: #666; 
  color: #777; 
  background-color: transparent;
  cursor: not-allowed;
}

.server-actions .action-button:hover:not(:disabled) {
  border-color: #ADADAD; 
  color: #F0F0F0; 
}

/* Specific button colors (for card buttons) */
.server-actions .start-button { border-color: #4CAF50; color: #66BB6A; }
.server-actions .start-button:hover:not(:disabled) { border-color: #81C784; color: #81C784; }
.server-actions .stop-button { border-color: #f44336; color: #EF5350; }
.server-actions .stop-button:hover:not(:disabled) { border-color: #E57373; color: #E57373; }
.server-actions .refresh-button { border-color: #2196F3; color: #64B5F6; }
.server-actions .refresh-button:hover:not(:disabled) { border-color: #90CAF9; color: #90CAF9; }
.server-actions .capabilities-button { border-color: #FF9800; color: #FFB74D; }
.server-actions .capabilities-button:hover:not(:disabled) { border-color: #FFCC80; color: #FFCC80; }
.server-actions .edit-button { border-color: #00acc1; color: #4DD0E1; }
.server-actions .edit-button:hover:not(:disabled) { border-color: #80DEEA; color: #80DEEA; }
.server-actions .remove-button { border-color: #d32f2f; color: #E57373; }
.server-actions .remove-button:hover:not(:disabled) { border-color: #EF9A9A; color: #EF9A9A; }

.feedback-message {
  margin-top: 10px;
  padding: 8px;
  border-radius: 4px;
  font-size: 0.85em;
  border: 1px solid #555; 
}
.feedback-message.success {
  background-color: #3A5A3A; 
  color: #A0F0A0; 
}
.feedback-message.error {
  background-color: #5A3A3A; 
  color: #F0A0A0; 
}

.action-button.back-to-chat-button {
  border: 1px solid #4db6ac; /* 青色边框 */
  background-color: #3F3F3F; 
  color: #E0E0E0;
}
.action-button.back-to-chat-button:hover:not(:disabled) {
  background-color: #4A4A4A;
  border-color: #80cbc4;
  color: #F0F0F0;
}

.server-shell-toggle {
  margin-top: 10px;
  padding: 8px;
  background-color: #f8f9fa; /* Light background for the toggle section */
  border-radius: 4px;
  border: 1px solid #e9ecef;
}

.server-shell-toggle .checkbox-label {
  display: flex;
  align-items: center;
  font-size: 0.9em;
  font-weight: normal;
  color: #333;
}

.server-shell-toggle input[type="checkbox"] {
  width: auto; /* Override general input styling if any */
  margin-right: 8px;
  transform: scale(0.9); /* Slightly smaller checkbox */
}

</style> 