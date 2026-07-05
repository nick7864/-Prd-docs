import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
export default defineConfig({
    plugins: [react(), tailwindcss()],
    server: {
        proxy: {
            "/prds": "http://localhost:8080",
            "/triage": "http://localhost:8080",
            "/render-report": "http://localhost:8080",
            "/health": "http://localhost:8080",
        },
    },
});
