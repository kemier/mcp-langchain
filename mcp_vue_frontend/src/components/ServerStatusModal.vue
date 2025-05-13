<template>
  <div v-if="visible" class="modal-overlay" @click.self="$emit('close')">
    <div class="modal-content">
      <button @click="$emit('close')" class="close-button">&times;</button>
      <h2>Server Details: {{ serverConfig?.display_name || serverKey }}</h2>

      <div v-if="serverConfig && serverKey">
        <div class="server-details">
          <p><strong>Name:</strong> {{ serverConfig.name }}</p>
          <p><strong>Description:</strong> {{ serverConfig.description }}</p>
          <p><strong>Status:</strong>
            <span :class="['server-status', statusClass(serverStatus?.status)]">
              {{ statusText(serverStatus?.status) }}
            </span>
             <span v-if="serverStatus?.pid">(PID: {{ serverStatus.pid }})</span>
          </p>
          <p v-if="serverStatus?.message"><strong>Message:</strong> {{ serverStatus.message }}</p>
          <p v-if="serverStatus?.last_updated_timestamp"><strong>Last Updated:</strong> {{ new Date(serverStatus.last_updated_timestamp).toLocaleString() }}</p>
        </div>

        <div class="capabilities-section">
          <h4>Configured Capabilities</h4>
          <div v-if="serverConfig.capabilities_for_tool_config?.length > 0" class="capability-container">
             <div v-for="cap in serverConfig.capabilities_for_tool_config" :key="cap.name" class="capability-item">
                <span class="capability-tag">{{ cap.name }}</span>
                <span v-if="cap.description" class="capability-description">: {{ cap.description }}</span>
             </div>
          </div>
          <p v-else>None configured.</p>
        </div>

        <div class="capabilities-section">
          <h4>Discovered Capabilities</h4>
           <!-- Check serverStatus before accessing discovered_capabilities -->
          <template v-if="serverStatus?.discovered_capabilities && serverStatus.discovered_capabilities.length > 0">
              <div class="capability-container">
                <div v-for="(cap, index) in serverStatus.discovered_capabilities" :key="index" class="capability-item">
                    <span class="capability-tag">{{ typeof cap === 'object' ? cap.name : cap }}</span>
                </div>
              </div>
              <button @click="$emit('refresh-capabilities', serverKey)" class="refresh-capabilities-btn">Refresh</button>
          </template>
          <p v-else>
             None discovered.
             <button v-if="isServerRunning" @click="$emit('refresh-capabilities', serverKey)" class="refresh-capabilities-btn">Refresh</button>
          </p>
        </div>

        <div class="server-actions">
          <button @click="$emit('start-server', serverKey)" :disabled="isServerRunning">Start</button>
          <button @click="$emit('stop-server', serverKey)" :disabled="!isServerRunning">Stop</button>
          <button @click="$emit('refresh-status', serverKey)">Refresh Status</button>
          <button @click="$emit('edit-server', serverKey)">Edit Config</button>
          <button @click="$emit('remove-server', serverKey)" class="danger-btn">Remove Server</button>
        </div>
      </div>
      <div v-else>
        <p>Loading server details...</p>
      </div>
    </div>
  </div>
</template>

<script lang="ts">
import { defineComponent, type PropType, computed } from 'vue';
import type { ServerConfig, ServerStatusResponse } from '../services/apiService';

export default defineComponent({
  name: 'ServerStatusModal',
  props: {
    visible: { type: Boolean, required: true },
    serverConfig: { type: Object as PropType<ServerConfig | null>, default: null },
    serverStatus: { type: Object as PropType<ServerStatusResponse | null>, default: null },
    serverKey: { type: String, default: null },
  },
  emits: ['close', 'add-server', 'start-server', 'stop-server', 'refresh-status', 'refresh-capabilities', 'edit-server', 'remove-server'],
  setup(props) {
    const isServerRunning = computed(() => {
      return props.serverStatus?.status === 'running' || props.serverStatus?.status === 'connected';
    });

    const statusClass = (status: string | undefined) => {
      if (!status) return 'status-unknown';
      if (status === 'running' || status === 'connected') return 'status-running';
      if (status === 'stopped' || status === 'error' || status === 'failed') return 'status-stopped';
      return 'status-unknown';
    };

    const statusText = (status: string | undefined) => {
        if (!status) return 'Unknown';
        return status.charAt(0).toUpperCase() + status.slice(1);
    };

    return { isServerRunning, statusClass, statusText };
  }
});
</script>

<style scoped>
.modal-overlay {
  position: fixed;
  top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(0,0,0,0.35);
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: center;
}
.modal-content {
  background: #fff;
  border-radius: 10px;
  box-shadow: 0 8px 32px rgba(0,0,0,0.18);
  padding: 32px 24px 24px 24px;
  min-width: 600px;
  max-width: 900px;
  max-height: 90vh;
  overflow-y: auto;
  position: relative;
}
.close-button {
  position: absolute;
  top: 16px;
  right: 16px;
  font-size: 2rem;
  background: none;
  border: none;
  color: #888;
  cursor: pointer;
}
.server-details p {
  margin: 5px 0;
}
.server-status {
  font-weight: bold;
  padding: 2px 6px;
  border-radius: 4px;
  color: white;
  margin-left: 5px;
}
.status-running { background-color: #28a745; }
.status-stopped { background-color: #dc3545; }
.status-unknown { background-color: #6c757d; }
.capabilities-section {
    margin-top: 15px;
    padding-top: 15px;
    border-top: 1px solid #eee;
}
.capability-container {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-top: 5px;
}
.capability-item {
    background-color: #f0f0f0;
    padding: 3px 8px;
    border-radius: 12px;
    font-size: 0.9em;
}
.capability-tag { font-weight: bold; }
.capability-description { color: #555; margin-left: 4px; }
.server-actions {
    margin-top: 20px;
    padding-top: 15px;
    border-top: 1px solid #eee;
    display: flex;
    gap: 10px;
    flex-wrap: wrap;
}
.server-actions button {
    padding: 8px 15px;
    border-radius: 4px;
    border: 1px solid #ccc;
    background-color: #f8f9fa;
    cursor: pointer;
}
.server-actions button:disabled {
    opacity: 0.6;
    cursor: not-allowed;
}
.server-actions button.danger-btn {
    background-color: #fdd;
    border-color: #fbb;
    color: #d8000c;
}
.refresh-capabilities-btn {
    margin-left: 10px;
    font-size: 0.8em;
    padding: 2px 6px;
}
</style> 