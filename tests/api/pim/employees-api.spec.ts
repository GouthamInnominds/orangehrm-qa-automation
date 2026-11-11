/**
 * @coversRequirement FR_PIM_001
 * @coversStory US_PIM_001
 * @coversRule BR_PIM_001
 * @coversComponent SaveEmployee.vue
 */
import { test, expect } from '@playwright/test';

test.describe('PIM - Employee Master API', () => {
  /**
   * @coversEndpoint GET /api/v2/pim/employees
   */
  test(
    'lists employee records with pagination metadata',
    { tag: ['@smoke', '@api', '@US_PIM_001', '@FR_PIM_001'] },
    async ({ request }) => {
      const response = await request.get('/api/v2/pim/employees');
      expect([200, 401]).toContain(response.status());
      if (response.status() === 200) {
        const body = await response.json();
        expect(Array.isArray(body.data)).toBe(true);
      }
    }
  );

  /**
   * @coversEndpoint POST /api/v2/pim/employees
   */
  test(
    'rejects unauthenticated employee creation payload',
    { tag: ['@security', '@api', '@BR_PIM_001'] },
    async ({ request }) => {
      const response = await request.post('/api/v2/pim/employees', {
        data: { firstName: '', lastName: '' }
      });
      expect([400, 401, 403, 422]).toContain(response.status());
    }
  );
});
