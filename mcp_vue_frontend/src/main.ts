import { createApp } from 'vue'
import App from './App.vue'
import router from './router'
import store from './store'
import './style.css'
// 导入highlight.js样式
import 'highlight.js/styles/github.css'
// @ts-ignore Import the vue-markdown-shiki plugin
import VueMarkdownShiki from 'vue-markdown-shiki'
// The following import is causing build errors - commenting out for now
// import 'vue-markdown-shiki/dist/style.css' // Try importing from dist/

const app = createApp(App)
app.use(router)
app.use(store)
app.use(VueMarkdownShiki)
app.mount('#app')
