import { defineConfig, devices } from '@playwright/test'

// Smoke tests run against the production build served statically,
// so they check exactly what gets deployed.
export default defineConfig({
  testDir: 'e2e',
  timeout: 30_000,
  reporter: [['list']],
  use: { baseURL: 'http://localhost:4173/' },
  webServer: {
    // STATIC_SERVER=python checks the build with a plain static file server.
    command: process.env.STATIC_SERVER === 'python'
      ? 'python -m http.server 4173 --directory dist'
      : 'npx vite preview --port 4173 --strictPort',
    url: 'http://localhost:4173/',
    reuseExistingServer: true,
    timeout: 60_000,
  },
  projects: [
    { name: 'desktop', use: { ...devices['Desktop Chrome'] } },
    { name: 'mobile-360', use: { ...devices['Desktop Chrome'], viewport: { width: 360, height: 740 }, isMobile: true, hasTouch: true } },
  ],
})
