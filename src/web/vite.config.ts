import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The API uses an HttpOnly session cookie, so the browser must talk to it same-origin.
// In dev, Vite forwards the API paths (and the WebSocket) to the backend.
const target = process.env.API_PROXY_TARGET ?? 'http://localhost:8000'
const paths = ['/auth', '/users', '/me', '/departments', '/conversations', '/messages', '/files', '/embeds',
  '/search', '/notifications', '/tasks', '/projects', '/suggestions', '/commands', '/admin', '/health']

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      ...Object.fromEntries(paths.map(p => [p, { target }])),
      '/ws': { target, ws: true },
    },
  },
})
