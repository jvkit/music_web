import { createApp } from 'vue';
import { createPinia } from 'pinia';
import App from './App.vue';
import router from './router/index.js';
import '@phosphor-icons/web/regular';
import '@phosphor-icons/web/fill';
import './assets/tailwind.css';
import './assets/styles.css';

const app = createApp(App);
app.use(createPinia());
app.use(router);
app.mount('#app');
