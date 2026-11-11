import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  reporter: [
    ['list'],
    ['json', { outputFile: 'test-results/playwright-report.json' }],
    ['junit', { outputFile: 'test-results/playwright-junit.xml' }]
  ],
  use: {
    baseURL: process.env.OHRM_BASE_URL || 'http://127.0.0.1:5121/web/index.php',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure'
  }
});
