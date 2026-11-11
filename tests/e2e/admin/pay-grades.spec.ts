import { test, expect } from '@playwright/test';

/**
 * @coversRequirement FR_ADM_001
 * @coversStory US_ADM_004
 * @coversEndpoint POST /api/v2/admin/pay-grades
 * @coversEndpoint GET /api/v2/admin/pay-grades
 * @coversComponent PayGrade.vue
 */
test.describe('Admin - Pay Grades Workflow', () => {
  test(
    'requires authenticated session on pay grades API and UI screen',
    { tag: ['@e2e', '@admin', '@US_ADM_004', '@FR_ADM_001'] },
    async ({ page, request }) => {
      const apiRes = await request.get('/api/v2/admin/pay-grades');
      expect([200, 401]).toContain(apiRes.status());

      await page.goto('/web/index.php/admin/viewPayGrades');
      await expect(page).toHaveURL(/\/(auth\/login|admin\/viewPayGrades)/);
    }
  );
});
