import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig({
    plugins: [react()],
    base: './', // Important for Electron
    server: {
        port: 5173,
        // Never allow the project-root Anthropic credential file to be served.
        fs: { deny: ['config.json', '**/config.json'] },
    }
})
