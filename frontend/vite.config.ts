import path from "node:path";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 5173,
    proxy: {
      // Proxy all backend routes to FastAPI on :8000 so the frontend can
      // just call `fetch('/brokers')` without CORS config.
      "/auth": "http://127.0.0.1:8000",
      "/brokers": "http://127.0.0.1:8000",
      "/portfolio": "http://127.0.0.1:8000",
      "/holdings": "http://127.0.0.1:8000",
      "/events": "http://127.0.0.1:8000",
      "/health": "http://127.0.0.1:8000",
    },
  },
});
