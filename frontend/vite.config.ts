import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const api = process.env.KELVO_API ?? "http://127.0.0.1:7860";

export default defineConfig({
  plugins: [react()],
  server: { proxy: { "/api": api, "/mcp": api } },
  build: { outDir: "../backend/kelvo/static", emptyOutDir: true, chunkSizeWarningLimit: 1200 },
});
