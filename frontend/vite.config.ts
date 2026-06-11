import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import electron from "vite-plugin-electron";
import renderer from "vite-plugin-electron-renderer";
import path from "path";

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => {
  // renderer 模式：只启动 Vite + React，不启动 Electron（便于纯 UI 调试）
  const isRendererOnly = mode === "renderer";

  return {
    plugins: [
      react(),
      ...(!isRendererOnly
        ? [
            electron([
              {
                // 主进程入口
                entry: "electron/main.ts",
                onstart(options) {
                  options.startup();
                },
                vite: {
                  build: {
                    outDir: "dist-electron",
                    sourcemap: true,
                    rollupOptions: {
                      external: ["electron"],
                    },
                  },
                },
              },
              {
                // 预加载脚本
                entry: "electron/preload.ts",
                onstart(options) {
                  options.reload();
                },
                vite: {
                  build: {
                    outDir: "dist-electron",
                    sourcemap: true,
                    rollupOptions: {
                      external: ["electron"],
                    },
                  },
                },
              },
            ]),
            renderer(),
          ]
        : []),
    ],
    resolve: {
      alias: {
        "@": path.resolve(__dirname, "./src"),
      },
    },
    server: {
      port: 5173,
      strictPort: true,
    },
  };
});
