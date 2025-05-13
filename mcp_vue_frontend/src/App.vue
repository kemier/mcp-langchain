<template>
  <div id="app-layout">
    <!-- Navigation bar REMOVED
    <nav>
      <router-link to="/">首页</router-link>
      <router-link to="/server-management">服务器管理</router-link>
      <router-link to="/llm-management">LLM 配置</router-link>
    </nav>
    -->
    <router-view />

    <!-- Global Disclaimer REMOVED -->
    <!-- 
    <div class="global-disclaimer">
      © AI 生成的回答可能不准确
    </div> 
    -->
  </div>
</template>

<script lang="ts">
import { defineComponent } from 'vue';

export default defineComponent({
  name: 'App',
});
</script>

<style scoped>
#app-layout {
  padding: 20px;
}

/* nav styling REMOVED
nav {
  margin-bottom: 20px;
  padding-bottom: 10px;
  border-bottom: 1px solid #ccc;
  display: flex;
  gap: 15px;
}

nav a {
  font-weight: bold;
  color: #2c3e50;
  text-decoration: none;
  padding: 5px 10px;
  border-radius: 4px;
}

nav a:hover {
  background-color: #f5f5f5;
}

nav a.router-link-active {
  color: #42b983;
  border-bottom: 2px solid #42b983;
}
*/

/* Global styles or styles for App.vue layout */
html, body {
  margin: 0;
  padding: 0;
  height: 100%;
}

#app {
  display: flex;
  flex-direction: column;
  min-height: 100vh; /* Ensure app takes full viewport height */
  font-family: Avenir, Helvetica, Arial, sans-serif;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  color: #2c3e50;
}

/* Ensure router view takes available space */
#app > .router-view-wrapper { /* Assuming you might wrap router-view */
  flex-grow: 1;
  display: flex;
  flex-direction: column;
}

/* Global Disclaimer Styles REMOVED */
/*
.global-disclaimer {
  position: fixed;
  bottom: 10px;
  left: 50%;
  transform: translateX(-50%);
  background-color: rgba(240, 240, 240, 0.9);
  color: #666;
  padding: 5px 15px;
  border-radius: 12px;
  font-size: 12px;
  text-align: center;
  z-index: 1000; // Ensure it's above most content
  box-shadow: 0 1px 3px rgba(0,0,0,0.1);
}
*/
</style>
