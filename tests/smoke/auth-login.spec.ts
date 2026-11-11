import { test, expect } from '@playwright/test';

/**
 * @coversRequirement FR_ADM_002
 * @coversEndpoint GET /auth/login
 * @coversEndpoint POST /auth/validate
 * @coversComponent Login.vue
 */
test.describe('Core - Authentication Smoke', () => {
  test(
    'renders login form and enforces required fields',
    { tag: ['@smoke', '@auth', '@FR_ADM_002'] },
    async ({ page }) => {
      await page.goto('/web/index.php/auth/login');
      const usernameInput = page.locator('input[name="username"]');
      const passwordInput = page.locator('input[name="password"]');
      await expect(usernameInput).toBeVisible();
      await expect(passwordInput).toBeVisible();
      await page.locator('button[type="submit"]').click();
      await expect(page.locator('.oxd-input-field-error-message').first()).toBeVisible();
    }
  );
});
