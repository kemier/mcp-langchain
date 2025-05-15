<script setup>
import { ref } from 'vue';

const isLlmSyncing = ref(false);
const llmSyncMessage = ref(null);
const actionFeedback = ref({});

// Function to send capabilities to LLM
const sendCapabilitiesToLLM = async () => {
  isLlmSyncing.value = true;
  llmSyncMessage.value = null;
  // actionFeedback.value = {}; // Clear other feedbacks -- Incorrect assignment
  // Clear feedback individually
  Object.keys(actionFeedback.value).forEach(key => {
    actionFeedback.value[key as keyof typeof actionFeedback.value] = null;
  });

  const activeCapsPayload = getActiveCapabilities();
  // ... existing code ...
};

// function clearAllFeedback() { // Remove unused function
//   // Assign null to clear the reactive object properties correctly
//   for (const key in actionFeedback.value) {
//       actionFeedback.value[key] = null;
//   }
//   // Or if you want to clear the whole object structure:
//   // actionFeedback.value = {}; // Re-assigning empty object might break reactivity if not careful
//   // Assigning null to specific keys is usually safer.
// }
</script>

          {{ config.command }} {{ config.args?.join(' ') }}
        </div>

        <!-- Refined v-if for capabilities -->
        <div v-if="serverStatuses[serverName as string]?.status === 'running' || serverStatuses[serverName as string]?.status === 'connected'" class="capabilities-section">
          <h4>Discovered Capabilities:</h4>
          <div v-if="serverStatuses[serverName as string]?.discovered_capabilities && serverStatuses[serverName as string].discovered_capabilities.length > 0" class="capabilities-pills">
            <span 
              v-for="(cap, index) in serverStatuses[serverName as string].discovered_capabilities" 
              :key="index" 
// ... existing code ... 