import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Relative base so the built site works from any static server path,
// including a GitHub Pages project subfolder.
export default defineConfig({
  base: './',
  plugins: [react()],
})
