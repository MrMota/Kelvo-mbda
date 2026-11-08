import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import "@xyflow/react/dist/style.css";
import "./styles.css";
import App from "./App";
import { AuthGate } from "./auth";
import { StoreProvider } from "./store";
import { ToastProvider } from "./ui/kit";

try {
  const t = localStorage.getItem("kelvo-theme");
  if (t) document.documentElement.dataset.theme = t;
} catch {}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <ToastProvider>
        <AuthGate>
          <StoreProvider>
            <App />
          </StoreProvider>
        </AuthGate>
      </ToastProvider>
    </BrowserRouter>
  </React.StrictMode>,
);
