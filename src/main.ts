const app = document.querySelector<HTMLElement>("#app");

if (app) {
  app.textContent = "Vite + TypeScript frontend is ready.";
  app.dataset.boot = "true";
}
