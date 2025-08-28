import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { resolve } from "path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": resolve(__dirname, "src"), // allow `@/...` imports
    },
  },
  publicDir: "public", // default: anything in /public is copied as-is
  build: {
    outDir: "dist",
    assetsDir: "assets",
  },
});
