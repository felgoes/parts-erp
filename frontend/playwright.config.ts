import { defineConfig, devices } from '@playwright/test';

const baseURL = process.env.E2E_BASE_URL ?? 'http://127.0.0.1:4200';
const apiURL = process.env.E2E_API_URL ?? 'http://127.0.0.1:8000';
const allowedHosts = new Set(['localhost', '127.0.0.1', '::1']);

if (![baseURL, apiURL].every((url) => allowedHosts.has(new URL(url).hostname))) {
  throw new Error('Os testes E2E só podem acessar uma instância local do ERP e da API.');
}

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  reporter: 'list',
  use: {
    ...devices['Desktop Chrome'],
    baseURL,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
});
