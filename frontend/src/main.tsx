import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import App from "./App.tsx";

// Amplify is optional - only configure if outputs exist
try {
  const { Amplify } = await import('aws-amplify');
  const outputs = await import("../amplify_outputs.json");
  Amplify.configure(outputs.default || outputs);
} catch {
  // Amplify not configured - running without authentication
  console.log('Running without Amplify authentication');
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>
);
