const { defineConfig } = require("vitest/config");
const react = require("@vitejs/plugin-react").default;

module.exports = defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8001",
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: "./src/test/setup.ts",
  },
});
