<template>
  <div v-if="!isLoading && !error" class="form-container">
    <ServerConfigCard
      :initialConfig="formConfigData"
      :serverKey="cardServerKey!"
      :isNew="isNewMode"
      :isProcessing="isLoading"
      :errorMessage="error || undefined"
      @save="handleSaveConfig"
      @cancel="handleCancelForm"
      class="config-form-card"
    />
  </div>
</template>