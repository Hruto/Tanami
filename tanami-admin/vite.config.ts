import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";

// In development the API runs separately (tanami-backend). The proxy keeps
// requests same-origin, so no CORS setup is needed while working locally.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, ".", "");
  const target = env.TANAMI_API_PROXY || "http://127.0.0.1:8000";
  return {
    plugins: [react()],
    server: {
      port: 5173,
      proxy: {
        "/api": { target, changeOrigin: true },
        "/media": { target, changeOrigin: true },
      },
    },
  };
});
