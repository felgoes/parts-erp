import { expect, test, type Page, type APIRequestContext } from '@playwright/test';

const apiURL = process.env.E2E_API_URL ?? 'http://127.0.0.1:8000';
const email = process.env.E2E_TEST_EMAIL;
const password = process.env.E2E_TEST_PASSWORD;

async function authenticateTestSession(page: Page, request: APIRequestContext) {
  if (!email || !password) {
    throw new Error('Configure E2E_TEST_EMAIL e E2E_TEST_PASSWORD em frontend/.env.e2e.local.');
  }
  const response = await request.post(`${apiURL}/api/v1/auth/login`, {
    form: { username: email, password },
  });
  expect(response.ok(), 'A API local deve autenticar a conta de QA').toBeTruthy();
  const session = await response.json();

  // Reuse the ERP's regular JWT/session format; this only avoids typing into
  // the login screen during automated local tests. Production auth is untouched.
  await page.goto('/login');
  await page.evaluate((value) => {
    sessionStorage.setItem('parts-erp-session', JSON.stringify(value));
  }, session);
  await page.goto('/dashboard');
  await expect(page.getByRole('heading', { name: 'Visão geral' })).toBeVisible();
}

test('dashboard separates confirmed revenue from canceled orders', async ({ page, request }) => {
  await authenticateTestSession(page, request);

  await expect(page.getByText(/1 cancelada\(s\)/)).toBeVisible();
  await expect(page.getByText('VEN-2026-900002')).toBeVisible();
  await expect(page.getByText('VEN-2026-900001')).toBeVisible();
  await page.screenshot({ path: 'test-results/dashboard-desktop.png', fullPage: true });
});

test('invoice details show the return request and refund information', async ({
  page,
  request,
}) => {
  await authenticateTestSession(page, request);
  await page.goto('/invoices');

  const canceledInvoice = page.getByRole('row').filter({ hasText: 'VEN-2026-900002' });
  await expect(canceledInvoice).toBeVisible();
  await expect(canceledInvoice).toContainText('Cancelada');
  await expect(canceledInvoice).toContainText('Devolução');
  await canceledInvoice.click();
  await page.getByRole('button', { name: /Pós-venda/ }).click();

  await expect(page.getByRole('heading', { name: 'Devolução' })).toBeVisible();
  await expect(page.getByText('Devolução solicitada pelo comprador', { exact: true })).toBeVisible();
  await expect(page.getByText('DEV-TEST-001')).toBeVisible();
  await expect(page.getByText('R$125.00', { exact: true }).first()).toBeVisible();
});

test('invoice list and post-sale object fit a mobile viewport', async ({ page, request }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await authenticateTestSession(page, request);
  await page.goto('/invoices');

  const canceledInvoice = page.getByRole('row').filter({ hasText: 'VEN-2026-900002' });
  await expect(canceledInvoice).toBeVisible();
  await canceledInvoice.click();
  await page.getByRole('button', { name: /Pós-venda/ }).click();
  await expect(page.getByRole('heading', { name: 'Devolução' })).toBeVisible();
  await page.screenshot({ path: 'test-results/post-sale-mobile.png', fullPage: true });

  const documentWidth = await page.evaluate(() => document.documentElement.scrollWidth);
  expect(documentWidth).toBeLessThanOrEqual(390);
});
