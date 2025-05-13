<script setup lang="ts">
import { ref, reactive, watch, type PropType } from 'vue';
import type { ServerConfig } from '../services/apiService'; // Assuming ServerConfig type is exported

const props = defineProps({
  initialConfig: {
    type: Object as PropType<ServerConfig>,
    default: () => ({ // Default for a new server
      name: '',
      display_name: '',
      command: '',
      args: [],
      transport: 'stdio', // Default transport
      cwd: '',
      env: {},
      description: '',
      capabilities_for_tool_config: [],
      // mcp_config: {} // If you have this field
    })
  },
  serverKey: {
    type: String,
    required: true // Can be a special key like '__NEW_SERVER__' for new ones
  },
  isNew: {
    type: Boolean,
    default: false
  },
  errorMessage: {
    type: String,
    default: ''
  },
  isProcessing: {
    type: Boolean,
    default: false
  },
  actionInProgress: { // New prop
    type: String as PropType<'save' | 'delete' | null>,
    default: null
  }
});

const emit = defineEmits(['save', 'cancel', 'delete']);

const localConfig = reactive<ServerConfig>({ ...JSON.parse(JSON.stringify(props.initialConfig)) });

// Ensure args is always an array on initial load or update
watch(() => props.initialConfig, (newVal) => {
  const parsedVal = JSON.parse(JSON.stringify(newVal));
  if (!parsedVal.args) {
    parsedVal.args = [];
  }
  Object.assign(localConfig, parsedVal);
}, { deep: true, immediate: true });

// --- Arguments Management ---
const newArg = ref('');
const editingArgIndex = ref<number | null>(null);
const editingArgValue = ref<string>('');

function addArgument() {
  if (newArg.value.trim()) {
    localConfig.args = localConfig.args || []; // Ensure args array exists
    localConfig.args.push(newArg.value.trim());
    newArg.value = '';
  }
}

function removeArgument(index: number) {
  if (localConfig.args) {
    localConfig.args.splice(index, 1);
    if (editingArgIndex.value === index) { // If removing the item being edited, cancel edit mode
        cancelEditArgument();
    }
  }
}

function startEditArgument(index: number) {
  editingArgIndex.value = index;
  editingArgValue.value = localConfig.args[index];
}

function saveEditedArgument() {
  if (editingArgIndex.value !== null && localConfig.args) {
    localConfig.args[editingArgIndex.value] = editingArgValue.value.trim();
    cancelEditArgument();
  }
}

function cancelEditArgument() {
  editingArgIndex.value = null;
  editingArgValue.value = '';
}
// --- End Arguments Management ---

// --- Environment Variables Management ---
const newEnvKey = ref('');
const newEnvValue = ref('');

function addEnvVar() {
  if (newEnvKey.value.trim()) {
    localConfig.env = localConfig.env || {};
    localConfig.env[newEnvKey.value.trim()] = newEnvValue.value;
    newEnvKey.value = '';
    newEnvValue.value = '';
  }
}

function removeEnvVar(key: string) {
  if (localConfig.env) {
    delete localConfig.env[key];
  }
}
// --- End Environment Variables Management ---

function handleSave() {
  if (props.isProcessing) return;
  if (props.isNew && !localConfig.name?.trim()) {
    alert('Server Name (Configuration Key) is required for a new server.');
    return;
  }
  // If an argument is being edited, save it before saving the whole config
  if (editingArgIndex.value !== null) {
    saveEditedArgument();
  }
  emit('save', props.serverKey, { ...localConfig });
}

function handleCancel() {
  if (props.isProcessing) return;
  emit('cancel');
}

function handleDelete() {
  if (props.isProcessing) return;
  emit('delete', props.serverKey);
}

</script>

<template>
  <div class="server-config-card-form" :class="{ 'processing': isProcessing }">
    <div v-if="errorMessage" class="card-error-message">
      {{ errorMessage }}
    </div>

    <div class="form-section">
      <label :for="`config-key-${serverKey}`">Configuration Key (Server Name):</label>
      <input :id="`config-key-${serverKey}`" v-model="localConfig.name" :disabled="!isNew || isProcessing" placeholder="unique-server-key" />
      <small v-if="!isNew">This is the unique identifier and cannot be changed after creation.</small>
      <small v-else>This will be the unique key for the server in servers.json.</small>
    </div>

    <div class="form-row">
        <div class="form-section">
            <label :for="`display-name-${serverKey}`">Display Name:</label>
            <input :id="`display-name-${serverKey}`" v-model="localConfig.display_name" :disabled="isProcessing" placeholder="Friendly Server Name" />
        </div>
        <div class="form-section">
            <label :for="`command-${serverKey}`">Command:</label>
            <input :id="`command-${serverKey}`" v-model="localConfig.command" :disabled="isProcessing" placeholder="e.g., python, npx, /path/to/executable" />
        </div>
    </div>

    <div class="form-section">
      <label :for="`description-${serverKey}`">Description:</label>
      <textarea :id="`description-${serverKey}`" v-model="localConfig.description" :disabled="isProcessing" placeholder="Optional server description" rows="3"></textarea>
    </div>
    
    <div class="form-row">
        <div class="form-section">
            <label :for="`transport-${serverKey}`">Transport:</label>
            <select :id="`transport-${serverKey}`" v-model="localConfig.transport" :disabled="isProcessing">
                <option value="stdio">stdio</option>
                <option value="http">http</option>
                <option value="none">none</option>
            </select>
        </div>
        <div class="form-section">
            <label :for="`cwd-${serverKey}`">Working Directory (CWD):</label>
            <input :id="`cwd-${serverKey}`" v-model="localConfig.cwd" :disabled="isProcessing" placeholder="Optional: /path/to/server/directory" />
        </div>
    </div>

    <div class="form-section arguments-section">
      <h4>Arguments</h4>
      <div v-for="(arg, index) in localConfig.args" :key="`arg-${index}-${serverKey}`" class="list-item argument-item">
        <div v-if="editingArgIndex === index" class="argument-edit-form">
          <input type="text" v-model="editingArgValue" @keyup.enter="saveEditedArgument" @keyup.esc="cancelEditArgument" class="inline-edit-input" placeholder="Argument value"/>
          <button @click="saveEditedArgument" class="inline-action-button save-arg-btn" :disabled="isProcessing">Save</button>
          <button @click="cancelEditArgument" class="inline-action-button cancel-arg-btn" :disabled="isProcessing">Cancel</button>
        </div>
        <div v-else class="argument-display">
          <span class="argument-text">{{ arg }}</span>
          <div class="argument-actions">
            <button @click="startEditArgument(index)" class="inline-action-button edit-arg-btn" :disabled="isProcessing">Edit</button>
            <button @click="removeArgument(index)" class="remove-btn" :disabled="isProcessing">Remove</button>
          </div>
        </div>
      </div>
      <div class="add-item-form">
        <input v-model="newArg" @keyup.enter="addArgument" placeholder="New argument" :disabled="isProcessing"/>
        <button @click="addArgument" class="add-btn" :disabled="isProcessing">Add Argument</button>
      </div>
    </div>

    <div class="form-section">
      <h4>Environment Variables</h4>
      <div v-for="(value, key) in localConfig.env" :key="`env-${key}-${serverKey}`" class="list-item">
        <span><strong>{{ key }}</strong>: {{ value }}</span>
        <button @click="removeEnvVar(key)" class="remove-btn" :disabled="isProcessing">Remove</button>
      </div>
      <div class="add-item-form env-var-form">
        <input v-model="newEnvKey" placeholder="New key" :disabled="isProcessing" />
        <input v-model="newEnvValue" placeholder="New value" @keyup.enter="addEnvVar" :disabled="isProcessing"/>
        <button @click="addEnvVar" class="add-btn" :disabled="isProcessing">Add Env Var</button>
      </div>
    </div>

    <div class="card-form-actions">
      <button @click="handleSave" class="action-button save-button" :disabled="isProcessing">
        <span v-if="isProcessing && actionInProgress === 'save'">{{ isNew ? 'Creating...' : 'Updating...' }}</span>
        <span v-else>{{ isNew ? 'Create Server' : 'Update Configuration' }}</span>
      </button>
      <button @click="handleCancel" class="action-button cancel-button" :disabled="isProcessing">Cancel</button>
      <button v-if="!isNew" @click="handleDelete" class="action-button delete-button-form" :disabled="isProcessing">
        <span v-if="isProcessing && actionInProgress === 'delete'">Deleting...</span>
        <span v-else>Delete This Server</span>
      </button>
    </div>
  </div>
</template>

<style scoped>
.server-config-card-form {
  padding: 30px; /* Increased padding */
  border: 1px solid #e0e6ed; /* Softer border */
  border-radius: 16px; /* More rounded corners */
  background-color: #ffffff;
  box-shadow: 0 6px 24px rgba(0, 0, 0, 0.07); /* Softer, slightly larger shadow */
  transition: opacity 0.3s ease;
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, 'Open Sans', 'Helvetica Neue', sans-serif; /* Consistent font */
  font-size: 15px; /* Increased base font size */
}

.server-config-card-form.processing {
  opacity: 0.6; /* Slightly more opacity when processing */
  pointer-events: none;
  color: #a91e2c; /* Darker error text */
}

.card-error-message {
  background-color: #fff0f1; /* Lighter error background */
  color: #c81e1e; /* Softer error text */
  border: 1px solid #fcc2c3; /* Softer error border */
  padding: 12px 18px;
  border-radius: 8px; /* Consistent rounding */
  margin-bottom: 20px; /* More space */
  font-size: 0.9em;
}

.form-section {
  margin-bottom: 24px; /* Increased spacing between sections */
}

.form-section h4 {
  font-weight: 600; /* Slightly bolder */
  margin-bottom: 8px;
  color: #333;
  font-size: 1.05em; /* Increased label/title font size */
}

.form-section label {
  display: block;
  font-weight: 400; /* Softer weight */
  margin-bottom: 8px;
  color: #4a5568; /* Softer label color */
  font-size: 0.9em; /* Slightly smaller */
}

.form-section input[type="text"],
.form-section input[type="password"],
.form-section textarea,
.form-section select {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid #ccc;
  border-radius: 6px;
  background-color: #fdfdfd;
  font-size: 1em; /* Match base font size */
  line-height: 1.5;
  box-sizing: border-box; /* Include padding/border in width */
  transition: border-color 0.2s ease, box-shadow 0.2s ease;
}

.form-section input:focus,
.form-section select:focus,
.form-section textarea:focus {
  outline: none;
  border-color: #007bff;
  box-shadow: 0 0 0 2px rgba(0, 123, 255, 0.2);
}

.form-section input:disabled,
.form-section select:disabled,
.form-section textarea:disabled {
  background-color: #e9ecef;
  cursor: not-allowed;
}

.form-section small {
  display: block;
  margin-top: 6px;
  font-size: 0.9em; /* Increased small text size */
  color: #555;
}

.form-row {
  display: flex;
  gap: 20px;
  margin-bottom: 24px; /* Consistent spacing */
}

.form-row > .form-section {
  flex: 1; /* Make sections share space */
  margin-bottom: 0; /* Remove bottom margin as row handles it */
}

/* Arguments and Env Vars Section Specifics */
.arguments-section,
.environment-variables-section { /* Assuming you might add this class */
  background-color: #f8f9fa; /* Slight background */
  padding: 20px;
  border-radius: 8px;
  border: 1px solid #e9ecef;
}

.list-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 15px; /* Adjusted padding */
  background-color: #fff;
  border: 1px solid #e0e6ed;
  border-radius: 6px;
  margin-bottom: 10px;
  font-size: 1em; /* Match base size */
}

.argument-item,
.env-var-item { /* Assuming you might add this class */
  /* Specific styles if needed */
}

.argument-edit-form,
.argument-display {
  display: flex;
  align-items: center;
  width: 100%;
  gap: 10px;
}

.argument-display {
  justify-content: space-between;
}

.argument-text {
  flex-grow: 1;
  word-break: break-all; /* Prevent long args from overflowing */
}

.inline-edit-input {
  flex-grow: 1;
  padding: 6px 8px;
  border: 1px solid #ccc;
  border-radius: 4px;
  font-size: 0.95em; /* Slightly smaller for edit */
}

.argument-actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0; /* Prevent buttons shrinking */
}

.add-item-form {
  display: flex;
  gap: 10px;
  margin-top: 15px;
  align-items: center;
}

.add-item-form input {
  flex-grow: 1;
  padding: 8px 10px;
  border: 1px solid #ccc;
  border-radius: 4px;
  font-size: 0.95em;
}

.env-var-form input {
  flex-basis: 40%; /* Give key/value inputs roughly equal space */
}

/* Button Styles */
.add-btn,
.remove-btn,
.inline-action-button {
  padding: 6px 12px;
  border: none;
  border-radius: 5px;
  cursor: pointer;
  font-size: 0.9em; /* Slightly larger button text */
  transition: background-color 0.2s ease, transform 0.1s ease;
}

.add-btn {
  background-color: #28a745;
  color: white;
}
.add-btn:hover:not(:disabled) {
  background-color: #218838;
}

.remove-btn {
  background-color: #dc3545;
  color: white;
  margin-left: 10px; /* Space it out */
}
.remove-btn:hover:not(:disabled) {
  background-color: #c82333;
}

.inline-action-button {
  background-color: #ffc107;
  color: #333;
}
.inline-action-button.save-arg-btn { background-color: #17a2b8; color: white; }
.inline-action-button.cancel-arg-btn { background-color: #6c757d; color: white; }

.inline-action-button:hover:not(:disabled) {
  opacity: 0.85;
}

.inline-action-button:disabled,
.add-btn:disabled,
.remove-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.card-form-actions {
  margin-top: 30px; /* Increased space before actions */
  padding-top: 20px;
  border-top: 1px solid #e0e6ed;
  display: flex;
  justify-content: flex-end;
  gap: 15px;
}

.action-button {
  padding: 10px 20px;
  border: none;
  border-radius: 6px;
  font-size: 1em; /* Match base size */
  font-weight: 500;
  cursor: pointer;
  transition: background-color 0.2s ease, box-shadow 0.2s ease;
}

.save-button {
  background-color: #007bff;
  color: white;
}
.save-button:hover:not(:disabled) {
  background-color: #0069d9;
}

.cancel-button {
  background-color: #6c757d;
  color: white;
}
.cancel-button:hover:not(:disabled) {
  background-color: #5a6268;
}

.delete-button-form {
    background-color: #e74c3c;
    color: white;
}
.delete-button-form:hover:not(:disabled) {
    background-color: #c0392b;
}

.form-section textarea {
    /* Already inherits from general input styling, which is now updated */
    /* min-height: 90px; */ /* This is now in the general input styling section if specific to textarea */
}

.argument-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
  /* Inherits .list-item styles like background, border-radius, margin-bottom */
}

.argument-edit-form {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 2px 0; /* Small padding to align with display mode */
}

.inline-edit-input {
  flex-grow: 1;
  padding: 9px 12px; /* Increased padding */
  border: 1px solid #b8c0c8; /* Slightly darker border for active edit */
  border-radius: 6px; /* Consistent rounding */
  font-size: 0.9em;
  background-color: #ffffff; /* White background for active edit */
}
.inline-edit-input:focus {
  border-color: #007bff;
  background-color: #fff;
  box-shadow: 0 0 0 3px rgba(0, 123, 255, 0.15); /* Softer focus shadow */
  outline: none;
}

.argument-display {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
  /* padding: 4px 0; /* Handled by list-item padding */
}

.argument-text {
  flex-grow: 1;
  word-break: break-all;
  margin-right: 10px;
  color: #34495e; /* Consistent input-like text color */
  font-size: 0.9em;
  line-height: 1.5; /* Better readability */
}

.argument-actions {
  display: flex;
  gap: 8px;
}

.inline-action-button {
  padding: 7px 12px; /* Increased padding */
  font-size: 0.85em; /* Slightly smaller */
  border-radius: 6px; /* Consistent rounding */
  border: 1px solid transparent;
  cursor: pointer;
  font-weight: 500;
  transition: background-color 0.15s ease, border-color 0.15s ease;
}

.save-arg-btn {
  background-color: #28a745;
  color: white;
  border-color: #28a745;
}
.save-arg-btn:hover:not(:disabled) {
  background-color: #218838;
}

.cancel-arg-btn {
  background-color: #6c757d;
  color: white;
  border-color: #6c757d;
}
.cancel-arg-btn:hover:not(:disabled) {
  background-color: #5a6268;
}

.edit-arg-btn {
  background-color: #ffc107;
  color: #212529;
  border-color: #ffc107;
}
.edit-arg-btn:hover:not(:disabled) {
  background-color: #e0a800;
}

.add-item-form input[type="text"] {
    /* Inherits general .form-section input styling. */
    /* background-color: #f7f9fc; */ /* Consistent with other inputs */
}

/* Adjust last-of-type for list items within sections to avoid double borders or missing ones */
.form-section > .list-item:last-of-type,
.form-section > div > .list-item:last-of-type { /* Catches items inside divs like v-for */
    border-bottom: none; /* Remove bottom border for the true last item */
}
.form-section > .add-item-form {
    margin-top: 12px; /* Space above "add item" form if list items exist */
}
/* If a list is empty and only add form shows, ensure spacing is fine */
.arguments-section > .add-item-form,
.form-section > .add-item-form { /* For env vars */
  /* margin-top: 0; */ /* If it's the first thing after h4 if list is empty */
} 
/* This logic might be complex with v-for, relying on margin-bottom of h4 and margin-top of form is safer */

</style> 