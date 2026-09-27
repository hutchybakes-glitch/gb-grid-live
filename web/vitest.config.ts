import { defineConfig } from 'vitest/config'

// Unit tests only; Playwright specs in e2e/ are run separately.
export default defineConfig({
  test: { include: ['src/**/*.test.ts'] },
})
