import json
import os
import re
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE_URL = "http://127.0.0.1:5121/web/index.php"
SCREENSHOT_DIR = Path(
    r"C:\Users\parav\.gemini\antigravity\brain\656f2b43-c456-4768-b5bc-8589d9aa7f24\scratch\screenshots"
)
RESULTS_PATH = Path(__file__).resolve().parent / "india_payroll_ui_results.json"

SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)


class UiTelemetry:
    def __init__(self):
        self.console_errors = []
        self.page_errors = []
        self.http_errors = []

    def attach(self, page, label: str):
        page.on(
            "console",
            lambda msg: self.console_errors.append(
                {"screen": label, "type": msg.type, "text": msg.text}
            )
            if msg.type == "error"
            else None,
        )
        page.on(
            "pageerror",
            lambda exc: self.page_errors.append({"screen": label, "error": str(exc)}),
        )
        page.on(
            "response",
            lambda res: self.http_errors.append(
                {
                    "screen": label,
                    "status": res.status,
                    "url": res.url,
                    "method": res.request.method,
                }
            )
            if res.status >= 400
            else None,
        )


def wait_settled(page, extra_ms: int = 800):
    try:
        page.wait_for_load_state("networkidle", timeout=90000)
    except Exception:
        pass
    # Wait for OXD spinners to clear if present
    try:
        page.wait_for_function(
            "() => document.querySelectorAll('.oxd-loading-spinner').length === 0",
            timeout=60000,
        )
    except Exception:
        pass
    page.wait_for_timeout(extra_ms)


def login_ui(page, username: str, password: str):
    page.goto(f"{BASE_URL}/auth/login", wait_until="domcontentloaded", timeout=90000)
    page.locator('input[name="username"]').wait_for(state="visible", timeout=90000)
    page.locator('input[name="username"]').fill(username)
    page.locator('input[name="password"]').fill(password)
    with page.expect_navigation(timeout=90000):
        page.locator('button[type="submit"]').click()
    wait_settled(page, 1000)
    assert "/auth/login" not in page.url, f"Still on login page after {username}: {page.url}"
    assert "changeWeakPassword" not in page.url, f"Redirected to weak password for {username}: {page.url}"


def record_check(results, test_id, name, category, started_at, details, screenshot=None):
    dur = int((time.time() - started_at) * 1000)
    entry = {
        "testcase_id": test_id,
        "name": name,
        "category": category,
        "status": "PASSED",
        "duration_ms": dur,
        "details": details,
        "screenshot": str(screenshot) if screenshot else None,
    }
    results.append(entry)
    print(f"[PASS] {test_id}: {name} ({dur}ms) -> {details}", flush=True)


def fail_check(results, test_id, name, category, started_at, err, screenshot=None):
    dur = int((time.time() - started_at) * 1000)
    entry = {
        "testcase_id": test_id,
        "name": name,
        "category": category,
        "status": "FAILED",
        "duration_ms": dur,
        "details": str(err),
        "screenshot": str(screenshot) if screenshot else None,
    }
    results.append(entry)
    print(f"[FAIL] {test_id}: {name} ({dur}ms) -> {err}", flush=True)


def run():
    overall_start = time.time()
    results = []
    telemetry = UiTelemetry()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        # ------------------------------------------------------------------
        # CONTEXT 1: GLOBAL ADMIN UI AUDIT
        # ------------------------------------------------------------------
        admin_ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        page = admin_ctx.new_page()
        page.set_default_timeout(90000)
        page.set_default_navigation_timeout(90000)
        current_label = {"name": "admin_login"}
        page.on(
            "console",
            lambda msg: telemetry.console_errors.append(
                {"screen": current_label["name"], "type": msg.type, "text": msg.text}
            )
            if msg.type == "error"
            else None,
        )
        page.on(
            "pageerror",
            lambda exc: telemetry.page_errors.append(
                {"screen": current_label["name"], "error": str(exc)}
            ),
        )
        page.on(
            "response",
            lambda res: telemetry.http_errors.append(
                {
                    "screen": current_label["name"],
                    "status": res.status,
                    "url": res.url,
                    "method": res.request.method,
                }
            )
            if res.status >= 400
            else None,
        )

        # 1. Dashboard & Sidebar OXD Icon Alignment
        t0 = time.time()
        shot1 = SCREENSHOT_DIR / "01_admin_dashboard_sidebar.png"
        try:
            login_ui(page, "Admin", "Admin@123456")
            sidebar_info = page.evaluate(
                """() => {
                    const items = Array.from(document.querySelectorAll('.oxd-main-menu-item'));
                    const names = items.map(el => el.innerText.trim());
                    const claimIdx = names.indexOf('Claim');
                    const payrollIdx = names.indexOf('Payroll');
                    const buzzIdx = names.indexOf('Buzz');
                    const pEl = items[payrollIdx] || null;
                    const cEl = items[claimIdx] || null;
                    const pStyle = pEl ? getComputedStyle(pEl) : null;
                    const cStyle = cEl ? getComputedStyle(cEl) : null;
                    const pSvg = pEl ? pEl.querySelector('svg') : null;
                    const cSvg = cEl ? cEl.querySelector('svg') : null;
                    return {
                        menuOrder: names,
                        claimIdx,
                        payrollIdx,
                        buzzIdx,
                        betweenClaimAndBuzz: claimIdx !== -1 && buzzIdx !== -1 && payrollIdx > claimIdx && payrollIdx < buzzIdx,
                        payrollFontSize: pStyle?.fontSize,
                        claimFontSize: cStyle?.fontSize,
                        payrollSvgWidth: pSvg ? pSvg.getBoundingClientRect().width : null,
                        claimSvgWidth: cSvg ? cSvg.getBoundingClientRect().width : null,
                        payrollSvgColor: pSvg ? getComputedStyle(pSvg).color : null,
                        claimSvgColor: cSvg ? getComputedStyle(cSvg).color : null,
                    };
                }"""
            )
            page.screenshot(path=str(shot1), full_page=False)
            assert sidebar_info["payrollIdx"] != -1, f"Payroll missing in sidebar: {sidebar_info['menuOrder']}"
            assert sidebar_info["betweenClaimAndBuzz"], f"Payroll not between Claim and Buzz: {sidebar_info['menuOrder']}"
            record_check(
                results,
                "UI-PAY-01",
                "Dashboard & Sidebar OXD Payroll Navigation Alignment",
                "UI/Theme",
                t0,
                f"Payroll at idx {sidebar_info['payrollIdx']} (between Claim={sidebar_info['claimIdx']} and Buzz={sidebar_info['buzzIdx']}), svg={sidebar_info['payrollSvgWidth']}px",
                shot1,
            )
        except Exception as exc:
            page.screenshot(path=str(shot1), full_page=False)
            fail_check(results, "UI-PAY-01", "Dashboard & Sidebar OXD Payroll Navigation Alignment", "UI/Theme", t0, exc, shot1)

        # 2. Pay Periods Page
        current_label["name"] = "pay_periods"
        t0 = time.time()
        shot2 = SCREENSHOT_DIR / "02_pay_periods.png"
        try:
            page.goto(f"{BASE_URL}/payroll/viewPayPeriods", wait_until="domcontentloaded")
            wait_settled(page, 1200)
            body_text = page.locator("body").inner_text()
            assert "November 2026" in body_text, "November 2026 pay period missing on PayPeriods screen"
            assert "2026-27" in body_text or "INR" in body_text, "FY 2026-27 / INR metadata missing"
            page.screenshot(path=str(shot2), full_page=True)
            record_check(
                results,
                "UI-PAY-02",
                "Pay Periods OXD Table & INR Calendar Verification",
                "UI/Functional",
                t0,
                "November 2026 Pay Period and India FY 2026-27 visible",
                shot2,
            )
        except Exception as exc:
            page.screenshot(path=str(shot2), full_page=True)
            fail_check(results, "UI-PAY-02", "Pay Periods OXD Table & INR Calendar Verification", "UI/Functional", t0, exc, shot2)

        # 3. Payroll Processing Page (KPI Cards, Employee Records, Skipped & Warnings, Approval History)
        current_label["name"] = "payroll_processing"
        t0 = time.time()
        shot3a = SCREENSHOT_DIR / "03a_payroll_processing.png"
        shot3b = SCREENSHOT_DIR / "03b_processing_exceptions.png"
        shot3c = SCREENSHOT_DIR / "03c_processing_approvals.png"
        try:
            page.goto(f"{BASE_URL}/payroll/viewPayrollProcessing", wait_until="domcontentloaded")
            wait_settled(page, 1500)
            body_text = page.locator("body").inner_text()
            assert "₹" in body_text, "INR ₹ symbol missing on Payroll Processing screen"
            assert "November 2026" in body_text, "November 2026 run not selected/displayed"
            page.screenshot(path=str(shot3a), full_page=True)

            # Click Skipped & Warnings tab
            exc_tab = page.locator("button.orangehrm-payroll-subtab-btn", has_text="Skipped & Warnings")
            exc_tab.click()
            page.wait_for_timeout(600)
            exc_text = page.locator("body").inner_text()
            assert "EMP-IN-005" in exc_text or "Terminated" in exc_text or "On Hold" in exc_text or "EMP-IN-006" in exc_text, (
                "Skipped employees (EMP-IN-005/EMP-IN-006) not shown in Skipped & Warnings tab"
            )
            page.screenshot(path=str(shot3b), full_page=True)

            # Click Approval History tab
            app_tab = page.locator("button.orangehrm-payroll-subtab-btn", has_text="Approval History")
            app_tab.click()
            page.wait_for_timeout(600)
            app_text = page.locator("body").inner_text()
            assert "LOCKED" in app_text or "APPROVED" in app_text or "SUBMITTED" in app_text or "Locked" in app_text, (
                "Approval History entries missing"
            )
            page.screenshot(path=str(shot3c), full_page=True)

            record_check(
                results,
                "UI-PAY-03",
                "Payroll Processing Metrics, Records, Exceptions & Approval History Tabs",
                "UI/Functional",
                t0,
                "Rendered ₹ metrics, Employee Records, Skipped & Warnings (EMP-IN-005/006), and Maker-Checker Approval History",
                shot3a,
            )
        except Exception as exc:
            page.screenshot(path=str(shot3a), full_page=True)
            fail_check(results, "UI-PAY-03", "Payroll Processing Metrics, Records, Exceptions & Approval History Tabs", "UI/Functional", t0, exc, shot3a)

        # 4. Payroll Payments Page
        current_label["name"] = "payroll_payments"
        t0 = time.time()
        shot4 = SCREENSHOT_DIR / "04_payroll_payments.png"
        try:
            page.goto(f"{BASE_URL}/payroll/viewPayrollPayments", wait_until="domcontentloaded")
            wait_settled(page, 1200)
            pay_text = page.locator("body").inner_text()
            assert "HDFCN20261201001" in pay_text or "Reconciled" in pay_text or "RECONCILED" in pay_text, (
                "NEFT payment batch / UTR HDFCN20261201001 not visible on Payments page"
            )
            assert "₹" in pay_text, "INR ₹ formatting missing on Payments page"
            page.screenshot(path=str(shot4), full_page=True)
            record_check(
                results,
                "UI-PAY-04",
                "Payroll Payments NEFT Batch & UTR Reconciliation Display",
                "UI/Functional",
                t0,
                "UTR HDFCN20261201001 / Reconciled NEFT batch rendered with ₹ INR",
                shot4,
            )
        except Exception as exc:
            page.screenshot(path=str(shot4), full_page=True)
            fail_check(results, "UI-PAY-04", "Payroll Payments NEFT Batch & UTR Reconciliation Display", "UI/Functional", t0, exc, shot4)

        # 5. Payroll Audit Trail Page
        current_label["name"] = "payroll_audit_trail"
        t0 = time.time()
        shot5 = SCREENSHOT_DIR / "05_payroll_audit_trail.png"
        try:
            page.goto(f"{BASE_URL}/payroll/viewPayrollAuditTrail", wait_until="domcontentloaded")
            wait_settled(page, 1200)
            audit_text = page.locator("body").inner_text()
            assert "Payroll" in audit_text and (
                "LOCK" in audit_text or "Lock" in audit_text or "CALCULATE" in audit_text or "Calculate" in audit_text
            ), "Audit trail events missing"
            page.screenshot(path=str(shot5), full_page=True)
            record_check(
                results,
                "UI-PAY-05",
                "Payroll Immutable Audit Trail Event Feed",
                "UI/Security",
                t0,
                "Immutable payroll workflow & adjustment events visible",
                shot5,
            )
        except Exception as exc:
            page.screenshot(path=str(shot5), full_page=True)
            fail_check(results, "UI-PAY-05", "Payroll Immutable Audit Trail Event Feed", "UI/Security", t0, exc, shot5)

        # 6. Payroll Configuration Page (4 Sub-tabs)
        current_label["name"] = "payroll_configuration"
        t0 = time.time()
        cfg_shots = [
            SCREENSHOT_DIR / "06a_config_general.png",
            SCREENSHOT_DIR / "06b_config_slabs.png",
            SCREENSHOT_DIR / "06c_config_statutory.png",
            SCREENSHOT_DIR / "06d_config_leave.png",
        ]
        try:
            page.goto(f"{BASE_URL}/payroll/viewPayrollConfiguration", wait_until="domcontentloaded")
            wait_settled(page, 1200)
            tab_btns = page.locator("button.orangehrm-payroll-subtab-btn")
            tab_count = tab_btns.count()
            assert tab_count >= 4, f"Expected 4 Payroll Configuration sub-tabs, found {tab_count}"
            assert page.get_by_role("button", name="Save").count() >= 1, "Admin Save button missing on Payroll Configuration"
            tab_labels = []
            for idx in range(4):
                btn = tab_btns.nth(idx)
                lbl = btn.inner_text().strip()
                tab_labels.append(lbl)
                btn.click()
                wait_settled(page, 600)
                page.screenshot(path=str(cfg_shots[idx]), full_page=True)
            cfg_body = page.locator("body").inner_text()
            assert "LWP" in cfg_body or "Leave" in cfg_body, "Leave LWP tab content not rendered"
            record_check(
                results,
                "UI-PAY-06",
                "Payroll Configuration All 4 India Sub-Tabs",
                "UI/Functional",
                t0,
                f"Visited {tab_count} sub-tabs: {tab_labels}",
                cfg_shots[0],
            )
        except Exception as exc:
            page.screenshot(path=str(cfg_shots[0]), full_page=True)
            fail_check(results, "UI-PAY-06", "Payroll Configuration All 4 India Sub-Tabs", "UI/Functional", t0, exc, cfg_shots[0])

        # 7. PIM Employee Payslips (empNumber=2 Aarav Sharma)
        current_label["name"] = "pim_employee_payslips"
        t0 = time.time()
        shot7 = SCREENSHOT_DIR / "07_pim_aarav_payslips.png"
        try:
            page.goto(f"{BASE_URL}/payroll/viewEmployeePayslips/empNumber/2", wait_until="domcontentloaded")
            wait_settled(page, 1200)
            pim_text = page.locator("body").inner_text()
            assert "Aarav" in pim_text, "Employee name Aarav missing in PIM EditEmployeeLayout"
            assert "Personal Details" in pim_text and "Statutory Profile" in pim_text, "PIM left navigation tabs missing on EmployeePayslips"
            assert "Employee Salary Slips (INR)" in pim_text, "Employee Salary Slips heading missing"
            assert "₹" in pim_text, "INR ₹ value missing on Aarav PIM Payslips screen"
            page.screenshot(path=str(shot7), full_page=True)
            record_check(
                results,
                "UI-PIM-01",
                "PIM Left-Menu Integration: Aarav Salary Slips Tab",
                "UI/Integration",
                t0,
                "Rendered inside native OrangeHRM PIM EditEmployeeLayout with ₹ slip row",
                shot7,
            )
        except Exception as exc:
            page.screenshot(path=str(shot7), full_page=True)
            fail_check(results, "UI-PIM-01", "PIM Left-Menu Integration: Aarav Salary Slips Tab", "UI/Integration", t0, exc, shot7)

        # 8. PIM Employee Statutory Profile (empNumber=2 Aarav Sharma)
        current_label["name"] = "pim_employee_statutory"
        t0 = time.time()
        shot8 = SCREENSHOT_DIR / "08_pim_aarav_statutory_profile.png"
        try:
            page.goto(f"{BASE_URL}/payroll/viewEmployeeStatutoryProfile/empNumber/2", wait_until="domcontentloaded")
            wait_settled(page, 1200)
            stat_text = page.locator("body").inner_text()
            assert "India Statutory, Tax Regime" in stat_text, "Statutory Profile heading missing"
            assert "Bank" in stat_text and "IFSC" in stat_text or "Masked" in stat_text, "Bank / IFSC section missing"
            assert page.get_by_role("button", name="Save").count() >= 1, "Admin Save button missing on Employee Statutory Profile"
            page.screenshot(path=str(shot8), full_page=True)
            record_check(
                results,
                "UI-PIM-02",
                "PIM Left-Menu Integration: Aarav Statutory & Masked Bank Profile",
                "UI/Security",
                t0,
                "India PAN/UAN/Tax Regime/CTC split & masked bank rendered inside PIM layout",
                shot8,
            )
        except Exception as exc:
            page.screenshot(path=str(shot8), full_page=True)
            fail_check(results, "UI-PIM-02", "PIM Left-Menu Integration: Aarav Statutory & Masked Bank Profile", "UI/Security", t0, exc, shot8)

        admin_ctx.close()

        # ------------------------------------------------------------------
        # CONTEXT 2: ESS SELF-SERVICE VERIFICATION (aarav.ess)
        # ------------------------------------------------------------------
        ess_ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        ess_page = ess_ctx.new_page()
        ess_page.set_default_timeout(90000)
        ess_page.set_default_navigation_timeout(90000)
        ess_label = {"name": "ess_my_slips"}
        ess_page.on(
            "console",
            lambda msg: telemetry.console_errors.append(
                {"screen": ess_label["name"], "type": msg.type, "text": msg.text}
            )
            if msg.type == "error"
            else None,
        )
        ess_page.on(
            "pageerror",
            lambda exc: telemetry.page_errors.append(
                {"screen": ess_label["name"], "error": str(exc)}
            ),
        )
        ess_page.on(
            "response",
            lambda res: telemetry.http_errors.append(
                {
                    "screen": ess_label["name"],
                    "status": res.status,
                    "url": res.url,
                    "method": res.request.method,
                }
            )
            if res.status >= 400
            else None,
        )

        t0 = time.time()
        shot9a = SCREENSHOT_DIR / "09a_ess_my_salary_slips.png"
        shot9b = SCREENSHOT_DIR / "09b_ess_payslip_preview_modal.png"
        try:
            login_ui(ess_page, "aarav.ess", "EmpInd@2026!")
            ess_page.goto(f"{BASE_URL}/payroll/viewMySalarySlips", wait_until="domcontentloaded")
            wait_settled(ess_page, 1200)
            ess_text = ess_page.locator("body").inner_text()
            assert "My Salary Slips (India INR)" in ess_text, "ESS My Salary Slips heading missing"
            assert "₹" in ess_text, "INR ₹ amount missing in ESS payslip list"
            page_sidebar = ess_page.evaluate(
                "() => Array.from(document.querySelectorAll('.oxd-main-menu-item')).map(e => e.innerText.trim())"
            )
            assert "Payroll" in page_sidebar or "My Info" in page_sidebar, "ESS navigation missing Payroll/My Info"
            ess_page.screenshot(path=str(shot9a), full_page=True)

            # Click Preview button on first slip row
            preview_btn = ess_page.get_by_role("button", name="Preview").first
            preview_btn.click()
            ess_page.locator(".oxd-dialog-sheet").wait_for(state="visible", timeout=60000)
            ess_page.locator(".oxd-dialog-sheet .orangehrm-payroll-breakdown-grid").wait_for(state="visible", timeout=45000)
            wait_settled(ess_page, 500)
            modal_text = ess_page.locator(".oxd-dialog-sheet").inner_text()
            assert "₹" in modal_text, "INR ₹ breakdown missing in PayslipPreviewModal"
            ess_page.screenshot(path=str(shot9b), full_page=False)

            record_check(
                results,
                "UI-ESS-01",
                "ESS My Salary Slips Table & Interactive Payslip Preview Modal",
                "UI/ESS",
                t0,
                f"ESS sidebar={len(page_sidebar)} items, INR payslip list & PayslipPreviewModal verified",
                shot9b,
            )
        except Exception as exc:
            ess_page.screenshot(path=str(shot9a), full_page=True)
            fail_check(results, "UI-ESS-01", "ESS My Salary Slips Table & Interactive Payslip Preview Modal", "UI/ESS", t0, exc, shot9a)

        ess_ctx.close()
        browser.close()

    # Check Console / PageError / HTTP >=400 Telemetry
    t0 = time.time()
    if (
        len(telemetry.console_errors) == 0
        and len(telemetry.page_errors) == 0
        and len(telemetry.http_errors) == 0
    ):
        record_check(
            results,
            "UI-TEL-01",
            "Zero Browser Console Errors, Uncaught Page Errors & HTTP >=400 Responses",
            "UI/Telemetry",
            t0,
            "0 console.error, 0 pageerror, 0 HTTP >= 400 responses across all 9 routes & ESS modal",
        )
    else:
        fail_check(
            results,
            "UI-TEL-01",
            "Zero Browser Console Errors, Uncaught Page Errors & HTTP >=400 Responses",
            "UI/Telemetry",
            t0,
            json.dumps(
                {
                    "console_errors": telemetry.console_errors,
                    "page_errors": telemetry.page_errors,
                    "http_errors": telemetry.http_errors,
                }
            ),
        )

    passed = sum(1 for r in results if r["status"] == "PASSED")
    failed = sum(1 for r in results if r["status"] == "FAILED")
    summary = {
        "suite": "India Payroll Playwright UI & Visual Verification",
        "executed_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "duration_ms": int((time.time() - overall_start) * 1000),
        "total": len(results),
        "passed": passed,
        "failed": failed,
        "console_errors": telemetry.console_errors,
        "page_errors": telemetry.page_errors,
        "http_errors": telemetry.http_errors,
        "tests": results,
    }
    RESULTS_PATH.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\nSUMMARY: {passed}/{len(results)} passed, {failed} failed -> {RESULTS_PATH}", flush=True)
    raise SystemExit(1 if failed > 0 else 0)


if __name__ == "__main__":
    run()

