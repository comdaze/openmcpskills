import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import App from "./App.tsx";

// Configure Amplify if available (optional)
async function initApp() {
  let authConfigured = false;
  try {
    const { Amplify } = await import('aws-amplify');
    const outputs = await import("../amplify_outputs.json");
    const config = outputs.default || outputs;
    Amplify.configure(config);
    // Check if auth section is actually present
    authConfigured = !!(config as any)?.auth;
  } catch {
    // Amplify not configured - running without authentication
    console.log('Running without Amplify authentication');
  }

  // Expose flag for use-auth hook
  (window as any).__AMPLIFY_AUTH_CONFIGURED__ = authConfigured;

  createRoot(document.getElementById("root")!).render(
    <StrictMode>
      <App />
    </StrictMode>
  );
}

initApp();
