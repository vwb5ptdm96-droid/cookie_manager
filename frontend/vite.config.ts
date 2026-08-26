import { readFileSync } from "node:fs";
import { fileURLToPath, URL } from "node:url";
import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

// 读取根目录 .env 的 APP_PORT，让开发代理跟随后端实际监听端口（后端端口被占时可改 .env，无需改这里）
function loadBackendPort(): number {
  if (process.env.APP_PORT) {
    return Number(process.env.APP_PORT);
  }
  try {
    const envPath = fileURLToPath(new URL("../.env", import.meta.url));
    const content = readFileSync(envPath, "utf-8");
    const match = content.match(/^APP_PORT\s*=\s*"?(\d+)"?/m);
    if (match) return Number(match[1]);
  } catch {
    // .env 缺失时使用默认值
  }
  return 8081;
}

const backendPort = loadBackendPort();

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  server: {
    host: "0.0.0.0",
    port: 5173,
    proxy: {
      "/api": {
        target: `http://127.0.0.1:${backendPort}`,
        changeOrigin: true,
      },
    },
  },
});
