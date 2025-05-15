<template>
  <div class="chat-box">
    <div v-for="(message, index) in messages" :key="index" class="message">
      <VueMarkdownIt :content="message.content" :stream="true" />
    </div>
  </div>
</template>

<script>
import { VueMarkdownIt } from 'vue-markdown-shiki'

export default {
  components: {
    VueMarkdownIt
  },
  data() {
    return {
      messages: [
        { content: '# Hello, how are you?' },
        { content: 'I am fine, thank you!' },
        { content: 'Here is a list:\n- Item 1\n- Item 2\n- Item 3' }
      ]
    }
  }
}
</script>

<style>
.chat-box {
  width: 100%;
  max-height: 400px;
  overflow-y: auto;
  border: 1px solid #ccc;
  padding: 10px;
  background-color: #f9f9f9;
}

.message {
  margin-bottom: 10px;
  padding: 5px;
  background-color: #fff;
  border-radius: 5px;
}
</style> 