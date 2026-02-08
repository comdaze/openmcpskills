import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import App from "./App.tsx";
import { Amplify } from 'aws-amplify'
import outputs from "../amplify_outputs.json";
import { ThemeProvider, amplifyTheme } from "./lib/amplify-theme";

Amplify.configure(outputs);

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ThemeProvider theme={amplifyTheme}>
      <App />
    </ThemeProvider>
  </StrictMode>
);
