"""
Live HTTP End-to-End Integration, Cross-Module & RBAC/SoD/IDOR Verification
for OrangeHRM 5.8 India-Standard Payroll Extension v2.2 on http://127.0.0.1:5121.
Saves telemetry results to tools/qkg_engine/india_payroll_verification_results.json.
"""

import http.cookiejar
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = os.environ.get("OHRM_BASE_URL", "http://127.0.0.1:5121").rstrip("/")
OUT_JSON = os.path.join(os.path.dirname(__file__), "india_payroll_verification_results.json")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class SessionClient:
    def __init__(self, label: str):
        self.label = label
        self.cj = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cj), NoRedirect()
        )

    def login(self, username: str, password: str) -> str:
        req1 = urllib.request.Request(f"{BASE}/web/index.php/auth/login")
        with self.opener.open(req1, timeout=90) as r1:
            html = r1.read().decode("utf-8", "ignore")
        m = re.search(r':token="([^"]+)"', html)
        if not m:
            raise RuntimeError(f"[{self.label}] Could not find CSRF :token on login page")
        tok = m.group(1).replace("&quot;", "").replace('"', "")
        form = urllib.parse.urlencode(
            {"_token": tok, "username": username, "password": password}
        ).encode("utf-8")
        req2 = urllib.request.Request(
            f"{BASE}/web/index.php/auth/validate",
            data=form,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        try:
            with self.opener.open(req2, timeout=90) as r2:
                loc = r2.headers.get("Location", "")
        except urllib.error.HTTPError as e:
            loc = e.headers.get("Location", "")
        if not loc or "/auth/login" in loc or "changeWeakPassword" in loc:
            raise RuntimeError(f"[{self.label}] Login failed/redirected unexpectedly: {loc}")
        return loc

    def request_json(self, method: str, path: str, body=None):
        url = f"{BASE}{path}"
        headers = {"Accept": "application/json"}
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with self.opener.open(req, timeout=90) as resp:
                raw = resp.read().decode("utf-8", "ignore")
                try:
                    return resp.status, json.loads(raw)
                except json.JSONDecodeError:
                    return resp.status, raw
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", "ignore")
            try:
                return e.code, json.loads(raw)
            except json.JSONDecodeError:
                return e.code, raw

    def request_raw(self, method: str, path: str):
        url = f"{BASE}{path}"
        req = urllib.request.Request(url, method=method)
        try:
            with self.opener.open(req, timeout=90) as resp:
                return resp.status, dict(resp.headers), resp.read().decode("utf-8", "ignore")
        except urllib.error.HTTPError as e:
            return e.code, dict(e.headers), e.read().decode("utf-8", "ignore")


results = {
    "targetUrl": BASE,
    "executedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "checks": [],
    "summary": {},
    "entities": {},
}


def record_check(check_id: str, category: str, name: str, passed: bool, details: str, duration_ms: int):
    entry = {
        "id": check_id,
        "category": category,
        "name": name,
        "status": "PASSED" if passed else "FAILED",
        "details": details,
        "durationMs": duration_ms,
    }
    results["checks"].append(entry)
    print(f"[{'PASS' if passed else 'FAIL'}] {check_id}: {name} ({duration_ms}ms) -> {details}", flush=True)
    if not passed:
        raise AssertionError(f"Check {check_id} failed: {details}")


def timed_step(check_id: str, category: str, name: str, fn):
    t0 = time.time()
    ok, details = fn()
    dt = int((time.time() - t0) * 1000)
    record_check(check_id, category, name, ok, details, dt)


def main():
    admin = SessionClient("Admin")
    approver = SessionClient("PayrollApprover")
    ess_aarav = SessionClient("AaravESS")

    timed_step(
        "E2E-AUTH-01",
        "Authentication & RBAC",
        "Admin, PayrollApprover (fin.approver), and ESS (aarav.ess) login cleanly",
        lambda: (
            True,
            f"Admin->{admin.login('Admin', 'Admin@123456')}, "
            f"Approver->{approver.login('fin.approver', 'Approver@123')}, "
            f"ESS->{ess_aarav.login('aarav.ess', 'EmpInd@2026!')}",
        ),
    )

    def check_config():
        s1, cfg = admin.request_json("GET", "/web/index.php/api/v2/payroll/config")
        s2, slabs = admin.request_json("GET", "/web/index.php/api/v2/payroll/tax-brackets?financialYear=2026-27&taxRegime=NEW_115BAC")
        s3, rules = admin.request_json("GET", "/web/index.php/api/v2/payroll/statutory-rules")
        s4, pols = admin.request_json("GET", "/web/index.php/api/v2/payroll/leave-policies")
        d = cfg.get("data", {})
        ok = (
            s1 == 200
            and s2 == 200
            and s3 == 200
            and s4 == 200
            and d.get("jurisdictionCode") == "IN"
            and d.get("defaultCurrencyId") == "INR"
            and d.get("requireMakerCheckerApproval") is True
            and len(slabs.get("data", [])) >= 7
            and len(rules.get("data", [])) >= 10
            and len(pols.get("data", [])) >= 3
        )
        return ok, (
            f"jurisdiction={d.get('jurisdictionCode')}, currency={d.get('defaultCurrencyId')}, "
            f"makerChecker={d.get('requireMakerCheckerApproval')}, slabs={len(slabs.get('data', []))}, "
            f"rules={len(rules.get('data', []))}, leavePolicies={len(pols.get('data', []))}"
        )

    timed_step("E2E-CFG-01", "Configuration", "India Config, FY 2026-27 Slabs, Statutory Rules & Leave Policies", check_config)

    # Ensure clean Pay Period creation for November 2026 (if not yet present)
    def create_or_reuse_period():
        st, lst = admin.request_json("GET", "/web/index.php/api/v2/payroll/pay-periods")
        existing = [p for p in lst.get("data", []) if p.get("startDate") == "2026-11-01"]
        if existing:
            p = existing[0]
            results["entities"]["payPeriodId"] = p["id"]
            return True, f"Reused existing period id={p['id']} status={p.get('status')}"
        st2, created = admin.request_json(
            "POST",
            "/web/index.php/api/v2/payroll/pay-periods",
            {
                "name": "November 2026",
                "startDate": "2026-11-01",
                "endDate": "2026-11-30",
                "payDate": "2026-12-01",
                "frequency": "MONTHLY",
                "jurisdictionCode": "IN",
                "currencyId": "INR",
                "standardWorkingDays": 21,
            },
        )
        d = created.get("data", {})
        ok = st2 in (200, 201) and bool(d.get("id"))
        if ok:
            results["entities"]["payPeriodId"] = d["id"]
        return ok, f"POST /pay-periods status={st2}, id={d.get('id')}, fy={d.get('financialYear')}"

    timed_step("E2E-PER-01", "Pay Period Lifecycle", "Create India Monthly INR Pay Period (November 2026)", create_or_reuse_period)

    # Test Overlap rejection!
    def check_overlap_guard():
        st, resp = admin.request_json(
            "POST",
            "/web/index.php/api/v2/payroll/pay-periods",
            {
                "name": "November 2026 Overlap Test",
                "startDate": "2026-11-15",
                "endDate": "2026-12-10",
                "payDate": "2026-12-15",
                "frequency": "MONTHLY",
                "jurisdictionCode": "IN",
                "currencyId": "INR",
                "standardWorkingDays": 21,
            },
        )
        return st in (400, 409, 422), f"Overlapping date range rejected with HTTP {st}: {resp}"

    timed_step("E2E-PER-02", "Pay Period Validation", "Overlap Guard rejects overlapping date range", check_overlap_guard)

    # Create or get Run + verify Idempotency Key
    def create_idempotent_run():
        pid = results["entities"]["payPeriodId"]
        st1, r1 = admin.request_json(
            "POST",
            "/web/index.php/api/v2/payroll/runs",
            {"payPeriodId": pid, "runType": "REGULAR", "idempotencyKey": "nov-2026-in-reg-v2"},
        )
        st2, r2 = admin.request_json(
            "POST",
            "/web/index.php/api/v2/payroll/runs",
            {"payPeriodId": pid, "runType": "REGULAR", "idempotencyKey": "nov-2026-in-reg-v2"},
        )
        d1, d2 = r1.get("data", {}), r2.get("data", {})
        ok = st1 in (200, 201) and st2 in (200, 201) and d1.get("id") and d1.get("id") == d2.get("id")
        if ok:
            results["entities"]["runId"] = d1["id"]
        return ok, f"runId={d1.get('id')}, idempotentSameId={d1.get('id') == d2.get('id')}, status={d1.get('status')}"

    timed_step("E2E-RUN-01", "Payroll Run", "Create Draft Run with Idempotency Key deduplication", create_idempotent_run)

    # Trigger Batch Calculation
    def calculate_batch():
        rid = results["entities"]["runId"]
        st, resp = admin.request_json("POST", f"/web/index.php/api/v2/payroll/runs/{rid}/calculate", {})
        d = resp.get("data", {})
        ok = st == 200 and d.get("status") == "CALCULATED" and d.get("totalEmployees") == 4
        return ok, (
            f"status={d.get('status')}, eligible={d.get('totalEmployees')}, "
            f"exceptions={d.get('exceptionCount')}, gross={d.get('totalGross')}, net={d.get('totalNetPay')}"
        )

    timed_step("E2E-CALC-01", "Calculation Engine", "Calculate November 2026 Batch across 6 employees", calculate_batch)

    # Verify Run snapshots, calculations, cross-module LWP/OT/Claims, bank masking, skipped employees
    def verify_cross_module_records():
        rid = results["entities"]["runId"]
        st_run, run_resp = admin.request_json("GET", f"/web/index.php/api/v2/payroll/runs/{rid}")
        st_rec, rec_resp = admin.request_json("GET", f"/web/index.php/api/v2/payroll/runs/{rid}/records?limit=50")
        rows = rec_resp.get("data", [])
        by_code = {r.get("employeeId"): r for r in rows}

        aarav = by_code.get("EMP-IN-001", {})
        meera = by_code.get("EMP-IN-002", {})
        rajesh = by_code.get("EMP-IN-003", {})
        ananya = by_code.get("EMP-IN-004", {})

        results["entities"]["records"] = {k: v.get("id") for k, v in by_code.items()}
        results["entities"]["empNumbers"] = {k: v.get("empNumber") for k, v in by_code.items()}

        raw_blob = json.dumps(rec_resp)
        no_raw_acct_leak = (
            "50100987654321" not in raw_blob
            and "00450199887766" not in raw_blob
            and "301122334455" not in raw_blob
        )

        # Verify Aarav: 1 LWP day, 3450 Claim reimbursement, Sec 87A 0 tax, capped EPF 1800, KA PT 200
        aarav_ok = (
            float(aarav.get("lwpDays", 0)) == 1.0
            and float(aarav.get("reimbursementAmount", 0)) == 3450.0
            and float(aarav.get("epfEmployee", 0)) == 1800.0
            and float(aarav.get("professionalTax", 0)) == 200.0
            and aarav.get("taxRegime") == "NEW_115BAC"
        )
        # Verify Meera: Old Regime TDS > 0
        meera_ok = meera.get("taxRegime") == "OLD" and float(meera.get("totalTax", 0)) > 0
        # Verify Rajesh: ESIC <=21k + 8h Overtime
        rajesh_ok = (
            float(rajesh.get("overtimeHours", 0)) == 8.0
            and float(rajesh.get("overtimeAmount", 0)) > 0
            and float(rajesh.get("esicEmployee", 0)) > 0
        )
        # Verify Ananya: 0.5 LWP day + MISSING_BANK_ACCOUNT_DETAILS warning
        ananya_ok = (
            float(ananya.get("lwpDays", 0)) == 0.5
            and "MISSING_BANK_ACCOUNT_DETAILS" in (ananya.get("warnings") or [])
        )
        # Verify skipped snapshots (Vikram terminated + Sneha USD)
        skipped = (run_resp.get("meta") or {}).get("ineligibleEmployees") or []
        skipped_codes = {s.get("employeeId") for s in skipped}
        skipped_ok = {"EMP-IN-005", "EMP-IN-006"}.issubset(skipped_codes)

        ok = st_run == 200 and st_rec == 200 and no_raw_acct_leak and aarav_ok and meera_ok and rajesh_ok and ananya_ok and skipped_ok
        return ok, (
            f"Aarav(lwp={aarav.get('lwpDays')},claim={aarav.get('reimbursementAmount')},tax={aarav.get('totalTax')},net={aarav.get('netSalary')}), "
            f"Meera(regime={meera.get('taxRegime')},tax={meera.get('totalTax')}), "
            f"Rajesh(otHrs={rajesh.get('overtimeHours')},otAmt={rajesh.get('overtimeAmount')},esic={rajesh.get('esicEmployee')}), "
            f"Ananya(lwp={ananya.get('lwpDays')},warns={ananya.get('warnings')}), "
            f"Skipped={sorted(skipped_codes)}, MaskedBankOnly={no_raw_acct_leak}"
        )

    timed_step("E2E-CALC-02", "Cross-Module Accuracy & Masking", "Verify PIM/Leave/Time/Claim/EPF/ESIC/PT/TDS/Masking/Skips", verify_cross_module_records)

    # Apply manual adjustment on Rajesh record
    def apply_adjustment():
        rajesh_rec_id = results["entities"]["records"]["EMP-IN-003"]
        st, resp = admin.request_json(
            "PUT",
            f"/web/index.php/api/v2/payroll/records/{rajesh_rec_id}/adjustment",
            {"adjustmentAmount": 1000.00, "reason": "Night shift transport & attendance incentive (INR)"},
        )
        d = resp.get("data", {})
        ok = st == 200 and float(d.get("adjustmentAmount", 0)) == 1000.0 and d.get("isManualOverride") is True
        return ok, f"recordId={rajesh_rec_id}, adj={d.get('adjustmentAmount')}, net={d.get('netSalary')}"

    timed_step("E2E-ADJ-01", "Audit & Adjustments", "Apply audited INR manual adjustment to Rajesh Kumar", apply_adjustment)

    # ESS RBAC + IDOR negative tests BEFORE submission/lock
    def check_ess_security_blocks():
        rid = results["entities"]["runId"]
        rajesh_emp = results["entities"]["empNumbers"]["EMP-IN-003"]
        st1, _ = ess_aarav.request_json("POST", f"/web/index.php/api/v2/payroll/runs/{rid}/calculate", {})
        st2, _ = ess_aarav.request_json("GET", f"/web/index.php/api/v2/payroll/employees/{rajesh_emp}/payslips")
        st3, _ = ess_aarav.request_json("PUT", f"/web/index.php/api/v2/payroll/config", {"defaultPtStateCode": "MH"})
        ok = st1 == 403 and st2 == 403 and st3 == 403
        return ok, f"ESS calculate={st1}, otherEmpPayslips(IDOR)={st2}, modifyConfig={st3}"

    timed_step("E2E-SEC-01", "RBAC & IDOR", "ESS blocked (403) from Payroll calculate, cross-employee payslips & config", check_ess_security_blocks)

    # Submit -> Maker Self-Approve Blocked (403 SoD) -> Adjustment Immutable Blocked (409) -> Checker Reject -> Resubmit -> Approve -> Lock
    def governance_workflow_and_sod():
        rid = results["entities"]["runId"]
        rajesh_rec_id = results["entities"]["records"]["EMP-IN-003"]

        st_sub, r_sub = admin.request_json("POST", f"/web/index.php/api/v2/payroll/runs/{rid}/submit", {"comments": "Ready for Finance verification"})
        st_sod, r_sod = admin.request_json("POST", f"/web/index.php/api/v2/payroll/runs/{rid}/approve", {"comments": "Illegal self-approve"})
        st_imm, _ = admin.request_json("PUT", f"/web/index.php/api/v2/payroll/records/{rajesh_rec_id}/adjustment", {"adjustmentAmount": 500, "reason": "Must fail while submitted"})

        # Checker rejects once to test full audit trail, then Admin re-submits
        st_rej, r_rej = approver.request_json("POST", f"/web/index.php/api/v2/payroll/runs/{rid}/reject", {"reason": "Verify Rajesh attendance incentive documentation"})
        st_resub, _ = admin.request_json("POST", f"/web/index.php/api/v2/payroll/runs/{rid}/submit", {"comments": "Re-submitted with overtime log attached"})
        st_app, r_app = approver.request_json("POST", f"/web/index.php/api/v2/payroll/runs/{rid}/approve", {"comments": "Verified FY 2026-27 INR statutory totals"})
        st_lock, r_lock = approver.request_json("POST", f"/web/index.php/api/v2/payroll/runs/{rid}/lock", {"comments": "Finalized & published November 2026 payslips"})

        ok = (
            st_sub == 200
            and st_sod == 403
            and st_imm in (400, 403, 409, 422)
            and st_rej == 200
            and r_rej.get("data", {}).get("status") == "REJECTED"
            and st_resub == 200
            and st_app == 200
            and r_app.get("data", {}).get("status") == "APPROVED"
            and st_lock == 200
            and r_lock.get("data", {}).get("status") == "LOCKED"
        )
        return ok, f"submit={st_sub}, adminSelfApprove={st_sod} (SoD!), lockedAdj={st_imm}, reject={st_rej}, resubmit={st_resub}, approve={st_app}, lock={st_lock}"

    timed_step("E2E-WF-01", "Maker-Checker & State Machine", "Submit -> Self-Approve 403 -> Reject -> Resubmit -> Approve -> Lock", governance_workflow_and_sod)

    # Verify ESS My Salary Slips & Strict Slip IDOR + HTML Download
    def verify_ess_slips_and_idor():
        st_my, my_resp = ess_aarav.request_json("GET", "/web/index.php/api/v2/payroll/my-salary-slips")
        my_slips = my_resp.get("data", [])
        aarav_slip_id = my_slips[0]["id"] if my_slips else None
        results["entities"]["aaravSlipId"] = aarav_slip_id

        st_det, det_resp = ess_aarav.request_json("GET", f"/web/index.php/api/v2/payroll/slips/{aarav_slip_id}")
        st_dl, _, dl_html = ess_aarav.request_raw("GET", f"/web/index.php/payroll/slips/{aarav_slip_id}/download")

        # Lookup Meera's slip via Approver/Admin to test IDOR by Aarav
        meera_emp = results["entities"]["empNumbers"]["EMP-IN-002"]
        st_ms, ms_resp = admin.request_json("GET", f"/web/index.php/api/v2/payroll/employees/{meera_emp}/payslips")
        meera_slip_id = ms_resp.get("data", [{}])[0].get("id")
        st_idor_json, _ = ess_aarav.request_json("GET", f"/web/index.php/api/v2/payroll/slips/{meera_slip_id}")
        st_idor_dl, _, _ = ess_aarav.request_raw("GET", f"/web/index.php/payroll/slips/{meera_slip_id}/download")

        ok = (
            st_my == 200
            and len(my_slips) >= 1
            and my_slips[0].get("slipStatus") == "PUBLISHED"
            and st_det == 200
            and det_resp.get("data", {}).get("slipNumber", "").startswith("SLP-")
            and st_dl == 200
            and "Aarav Sharma" in dl_html
            and ("&#8377;" in dl_html or "\u20b9" in dl_html)
            and st_idor_json == 403
            and st_idor_dl == 403
        )
        return ok, f"aaravSlipId={aarav_slip_id}, downloadHTTP={st_dl}, meeraSlipId={meera_slip_id}, idorJson={st_idor_json}, idorDownload={st_idor_dl}"

    timed_step("E2E-ESS-01", "Self-Service & Slip IDOR", "ESS fetches/downloads own PUBLISHED slip and gets 403 on peer slip", verify_ess_slips_and_idor)

    # NEFT Payment Batch Creation -> Blocked Export on Missing Bank -> Update Ananya Statutory Profile -> Export NEFT CSV -> Reconcile UTR -> Verify Claim PAID
    def payment_export_reconcile_and_claim_paid():
        rid = results["entities"]["runId"]
        ananya_emp = results["entities"]["empNumbers"]["EMP-IN-004"]

        st_cb, cb_resp = approver.request_json("POST", "/web/index.php/api/v2/payroll/payment-batches", {"payrollRunId": rid, "paymentMode": "NEFT"})
        batch_id = cb_resp.get("data", {}).get("id")
        results["entities"]["batchId"] = batch_id

        # Must block CSV export while Ananya lacks bank account / IFSC!
        st_blk, blk_resp = approver.request_json("POST", f"/web/index.php/api/v2/payroll/payment-batches/{batch_id}/export", {})

        # Admin enters Ananya's WB SBI bank account via Statutory Profile API
        st_prof, prof_get = admin.request_json("GET", f"/web/index.php/api/v2/payroll/employees/{ananya_emp}/statutory-profile")
        p = prof_get.get("data", {})
        st_upd, _ = admin.request_json(
            "PUT",
            f"/web/index.php/api/v2/payroll/employees/{ananya_emp}/statutory-profile",
            {
                "panNumber": p.get("panNumber"),
                "uanNumber": p.get("uanNumber"),
                "ptStateCode": p.get("ptStateCode") or "WB",
                "taxRegime": p.get("taxRegime") or "NEW_115BAC",
                "epfOptedIn": p.get("epfOptedIn", True),
                "epfRestrictToCeiling": p.get("epfRestrictToCeiling", True),
                "esicApplicable": p.get("esicApplicable", False),
                "ptApplicable": p.get("ptApplicable", True),
                "basicPercentOfCtc": p.get("basicPercentOfCtc", 50),
                "hraPercentOfBasic": p.get("hraPercentOfBasic", 40),
                "declared80c": p.get("declared80c", 0),
                "declared80d": p.get("declared80d", 0),
                "declaredHraAnnual": p.get("declaredHraAnnual", 0),
                "otherExemptions": p.get("otherExemptions", 0),
                "bankAccountHolder": "Ananya Das",
                "bankName": "State Bank of India",
                "bankIfscCode": "SBIN0004321",
                "bankAccountNumber": "401122334455",
            },
        )

        # Retry NEFT Export -> succeeds cleanly with CSV content containing unmasked accounts + IFSC
        st_exp, exp_resp = approver.request_json("POST", f"/web/index.php/api/v2/payroll/payment-batches/{batch_id}/export", {})
        csv_text = exp_resp.get("data", {}).get("csvContent", "")
        csv_ok = st_exp == 200 and "BeneficiaryName,EmployeeCode,BankAccountNumber,IFSCCode" in csv_text and "HDFC0001234" in csv_text and "SBIN0004321" in csv_text

        # Reconcile with Bank UTR -> PAID_RECONCILED + transitions Claim REF-CLM-IN-001 APPROVED -> PAID!
        st_rec, rec_resp = approver.request_json(
            "POST",
            f"/web/index.php/api/v2/payroll/payment-batches/{batch_id}/reconcile",
            {"succeeded": True, "utrOrReason": "HDFCN20261201001"},
        )

        # Verify Claim status directly in MariaDB via WSL php check
        claim_row = subprocess.check_output(
            [
                "wsl",
                "-e",
                "php",
                "-r",
                "$p=new PDO('mysql:host=127.0.0.1;dbname=orangehrm_mysql','root','root');"
                "$c=$p->query(\"SELECT c.status AS c_status, l.settlement_status, l.reconciled_at FROM ohrm_claim_request c JOIN ohrm_payroll_claim_link l ON l.claim_request_id=c.id WHERE c.reference_id='REF-CLM-IN-001'\")->fetch(PDO::FETCH_ASSOC);"
                "echo json_encode($c);",
            ],
            text=True,
        ).strip()
        claim_data = json.loads(claim_row) if claim_row else {}

        ok = (
            st_cb in (200, 201)
            and batch_id is not None
            and st_blk in (400, 422)
            and st_prof == 200
            and st_upd == 200
            and csv_ok
            and st_rec == 200
            and rec_resp.get("data", {}).get("status") == "PAID_RECONCILED"
            and claim_data.get("c_status") == "PAID"
            and claim_data.get("settlement_status") == "PAID_RECONCILED"
        )
        return ok, (
            f"batchId={batch_id}, missingBankBlockedHTTP={st_blk}, ananyaProfileUpd={st_upd}, "
            f"exportCSV={st_exp} (rows={len(csv_text.splitlines())}), reconcile={st_rec} (UTR=HDFCN20261201001), "
            f"claimDB={claim_data}"
        )

    timed_step("E2E-PAY-01", "Payment & Claim Settlement", "NEFT Missing-Bank Guard -> Export CSV -> UTR Reconcile -> Claim PAID", payment_export_reconcile_and_claim_paid)

    # Verify Audit Trail logs
    def verify_audit_events():
        st, resp = admin.request_json("GET", "/web/index.php/api/v2/payroll/audit-events?limit=25")
        events = [e.get("eventType") for e in resp.get("data", [])]
        expected = {"PAY_PERIOD_CREATED", "RUN_CALCULATED", "MANUAL_ADJUSTMENT_APPLIED", "RUN_REJECTED", "RUN_APPROVED", "RUN_LOCKED", "PAYMENT_BATCH_EXPORTED", "PAYMENT_BATCH_RECONCILED_PAID"}
        missing = sorted(expected - set(events))
        return st == 200 and not missing, f"count={len(events)}, missingExpected={missing}"

    timed_step("E2E-AUD-01", "Audit Trail", "Verify immutable audit trail records full lifecycle", verify_audit_events)

    passed = sum(1 for c in results["checks"] if c["status"] == "PASSED")
    failed = sum(1 for c in results["checks"] if c["status"] == "FAILED")
    results["summary"] = {"total": len(results["checks"]), "passed": passed, "failed": failed}

    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"\nALL {passed}/{len(results['checks'])} E2E CHECKS PASSED! Saved -> {OUT_JSON}", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        results["summary"] = {
            "total": len(results["checks"]),
            "passed": sum(1 for c in results["checks"] if c["status"] == "PASSED"),
            "failed": sum(1 for c in results["checks"] if c["status"] == "FAILED") + 1,
            "error": str(exc),
        }
        with open(OUT_JSON, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)
        print(f"\nE2E FAILED: {exc}", file=sys.stderr, flush=True)
        sys.exit(1)

