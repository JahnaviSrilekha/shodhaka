import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import "./styles.css";

// the recorded demo opens on its first analysis instead of an almost empty home page
if (import.meta.env.VITE_DEMO === "1" && import.meta.env.VITE_DEMO_START && !location.hash.slice(2)) {
  location.hash = import.meta.env.VITE_DEMO_START;
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
