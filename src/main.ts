import { renderApp } from "./App";
import "./style.css";

const appRoot = document.querySelector<HTMLDivElement>("#app");

if (!appRoot) {
  throw new Error("App root not found");
}

appRoot.innerHTML = renderApp();
