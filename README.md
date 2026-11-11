# OrangeHRM QA Automation (`orangehrm-qa-automation`)

Standalone QA automation repository decoupled from the `Orange-HRMS` application repository (`REPOS.QA = 'orangehrm-qa-automation'`).

## Repository Structure

- `tests/` — **Playwright TypeScript** suites (`smoke/`, `api/`, `e2e/`) parsed by `@orangehrm/qkg-extractor` (`AST_PLAYWRIGHT`).
- `cypress/` — Genuine **Cypress Integration** suites (`cypress/e2e/integration/`, `fixtures/`, `support/`).
- `scripts/` — Standalone live E2E/RBAC/UI Playwright Python verification utilities.
- `.github/workflows/qa-graph-sync.yml` — CI sync pipeline pushing AST test links and Playwright/Cypress execution history to the QKG.

## QKG Traceability Conventions

Annotate Playwright specs cleanly so `@orangehrm/qkg-extractor` binds tests to requirements, endpoints, and components:

```ts
/**
 * @coversRequirement FR_PIM_001
 * @coversStory US_PIM_001
 * @coversRule BR_PIM_001
 * @coversEndpoint GET /api/v2/pim/employees
 * @coversComponent SaveEmployee.vue
 */
```

- **App-repo boundary:** Developer unit/integration tests (`orange_hrm/src/plugins/*/test/` PHPUnit and `orange_hrm/src/client/src/**/__tests__/` Jest) stay in `Orange-HRMS`.
- **Zero empty stubs:** Placeholder `expect(true)` / `assertTrue(true)` tests are prohibited.

## Local QKG Wiring

Point the `Orange-HRMS` QKG engine to this checkout:

```env
QKG_QA_REPO_DIR=C:/Users/parav/Workspace/orangehrm-qa-automation
```
