/// <reference types="vitest" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: { output: { manualChunks: { deck: ["@deck.gl/core", "@deck.gl/layers", "@deck.gl/react", "@deck.gl/extensions"], echarts: ["echarts"] } } },
    chunkSizeWarningLimit: 1200,
  },
  test: { environment: "node", include: ["src/**/*.test.ts"] },
});
