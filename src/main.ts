const app = document.querySelector<HTMLDivElement>('#app');

if (!app) {
  throw new Error('App container not found');
}

app.innerHTML = '<h1>Hello from TypeScript + Vite</h1>';
