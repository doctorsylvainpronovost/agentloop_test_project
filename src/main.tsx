import React from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./style.css";

const appRoot = document.querySelector<HTMLDivElement>("#app");

if (!appRoot) {
  throw new Error("App root not found");
}

createRoot(appRoot).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
