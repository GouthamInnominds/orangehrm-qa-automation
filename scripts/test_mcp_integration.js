/**
 * MCP Integration Test Script for orangehrm-qa-automation
 *
 * Verifies that an AI Agent or CLI in this repository can:
 *   1. Communicate with qkg-intelligence over stdio JSON-RPC
 *   2. Fetch full Payroll context (rules, APIs, DB, existing tests, fixtures) to generate test cases
 *   3. Run Test Impact Analysis (TIA) for regression test selection
 *   4. Explain test selection evidence paths
 *   5. Propose a new test artifact into the QKG Review Queue
 */

const { spawn } = require('child_process');
const path = require('path');
const readline = require('readline');

const SERVER_SCRIPT = path.resolve(__dirname, 'mcp-bridge.js');

class McpClientTest {
  constructor() {
    this.child = spawn('node', [SERVER_SCRIPT], {
      cwd: path.resolve(__dirname, '..'),
      stdio: ['pipe', 'pipe', 'pipe']
    });

    this.rl = readline.createInterface({
      input: this.child.stdout,
      terminal: false
    });

    this.pending = new Map();
    this.requestId = 1;

    this.rl.on('line', (line) => {
      const trimmed = line.trim();
      if (!trimmed) return;
      try {
        const msg = JSON.parse(trimmed);
        if (msg.id && this.pending.has(msg.id)) {
          const { resolve, reject } = this.pending.get(msg.id);
          this.pending.delete(msg.id);
          if (msg.error) reject(msg.error);
          else resolve(msg.result);
        }
      } catch (err) {
        console.error('[Client] Failed to parse JSON-RPC line:', err);
      }
    });

    this.child.stderr.on('data', (data) => {
      // Diagnostic output from server
      const str = data.toString();
      if (process.env.DEBUG_MCP) console.error('[Server Stderr]', str.trim());
    });
  }

  send(method, params = {}) {
    return new Promise((resolve, reject) => {
      const id = this.requestId++;
      this.pending.set(id, { resolve, reject });
      const payload = JSON.stringify({ jsonrpc: '2.0', id, method, params }) + '\n';
      this.child.stdin.write(payload);
    });
  }

  close() {
    this.child.kill();
  }
}

async function runVerification() {
  console.log('================================================================');
  console.log('QKG MCP AGENT INTEGRATION TEST: orangehrm-qa-automation');
  console.log('================================================================\n');

  const client = new McpClientTest();

  try {
    // 1. Initialize Handshake
    console.log('[Step 1] Initializing MCP Handshake...');
    const initRes = await client.send('initialize', {
      clientInfo: { name: 'antigravity-qa-agent', version: '2.2.0' }
    });
    console.log('  ✔ Connected to server:', initRes.serverInfo.name, 'v' + initRes.serverInfo.version);
    console.log('  ✔ Protocol version:', initRes.protocolVersion);

    // 2. Discover Tools
    console.log('\n[Step 2] Listing Available MCP Tools...');
    const toolsRes = await client.send('tools/list', {});
    const tools = toolsRes.tools || [];
    console.log(`  ✔ Discovered ${tools.length} canonical tools:`);
    tools.forEach((t) => console.log(`     - ${t.name}: ${t.description.substring(0, 65)}...`));

    // 3. Fetch Full Payroll Test Generation Context
    console.log('\n[Step 3] Fetching Test Generation Context for Indian Payroll (WF_PAYROLL_RUN)...');
    const genContextRes = await client.send('tools/call', {
      name: 'get_test_generation_context',
      arguments: { workflow_id: 'WF_PAYROLL_RUN' }
    });

    const parsedGen = JSON.parse(genContextRes.content[0].text);
    console.log('  ✔ Analysis Status:', parsedGen.analysisStatus);
    console.log('  ✔ Workflow Name:', parsedGen.data.workflow.name);
    console.log('  ✔ Business Domain:', parsedGen.data.workflow.domain_name);
    console.log('  ✔ Business Rules retrieved:', parsedGen.data.business_rules.length);
    parsedGen.data.business_rules.slice(0, 4).forEach((r) => {
      console.log(`     * [${r.rule_id}] ${r.name}: ${r.description}`);
    });
    console.log('  ✔ API Endpoints discovered:', parsedGen.data.api_endpoints.length);
    parsedGen.data.api_endpoints.slice(0, 3).forEach((ep) => {
      console.log(`     * Route: ${ep.route_name || ep.route} (${ep.method})`);
    });
    console.log('  ✔ Existing Mapped Tests (for deduplication):', parsedGen.data.existing_tests.length);
    parsedGen.data.existing_tests.slice(0, 3).forEach((t) => {
      console.log(`     * Test: ${t.test_id || t.name} [${t.framework}]`);
    });
    console.log('  ✔ Synthetic Data Recommendations (zero PII):', parsedGen.data.synthetic_data_recommendations.length);
    parsedGen.data.synthetic_data_recommendations.forEach((rec) => {
      console.log(`     * Factory: ${rec.factory} -> ${rec.description}`);
    });

    // 4. Run Code Impact Analysis for Regression
    console.log('\n[Step 4] Running Code Impact Analysis for Regression...');
    const changedFiles = [
      'orange_hrm/src/plugins/orangehrmPimPlugin/Service/EmployeeService.php'
    ];
    const impactRes = await client.send('tools/call', {
      name: 'get_code_impact',
      arguments: { changed_files: changedFiles }
    });
    const parsedImpact = JSON.parse(impactRes.content[0].text);
    console.log('  ✔ Analysis Status:', parsedImpact.analysisStatus);
    const affectedCount = parsedImpact.data?.directImpacts?.methods?.length || parsedImpact.data?.summary?.impactedClassesCount || 0;
    console.log('  ✔ Directly Affected Methods in Graph:', affectedCount);

    // 5. Run Test Impact Analysis (TIA) for Regression Test Selection
    console.log('\n[Step 5] Running Test Impact Analysis (get_impacted_tests)...');
    const tiaRes = await client.send('tools/call', {
      name: 'get_impacted_tests',
      arguments: { changed_files: changedFiles }
    });
    const parsedTia = JSON.parse(tiaRes.content[0].text);
    console.log('  ✔ TIA Analysis Status:', parsedTia.analysisStatus);
    const impactedRegression = parsedTia.data?.impactedRegressionTests || [];
    console.log(`  ✔ Impacted Regression Tests Recommended: ${impactedRegression.length}`);
    impactedRegression.slice(0, 5).forEach((t) => {
      console.log(`     * [Tier ${t.evidenceTier || t.confidenceTier || 1}] ${t.canonicalId || t.name} (${t.framework || 'Unit'})`);
    });
    if (parsedTia.data?.riskAssessment) {
      console.log(`  ✔ Regression Risk Level: ${parsedTia.data.riskAssessment.overallRiskLevel || parsedTia.data.riskAssessment.level || 'Calculated'}`);
    }

    // 6. Propose a Generated Test Artifact into QKG Review Queue
    console.log('\n[Step 6] Submitting Generated Payroll Test Scenario to QKG Review Queue...');
    const proposeRes = await client.send('tools/call', {
      name: 'propose_test_artifact',
      arguments: {
        workflow_id: 'WF_PAYROLL_RUN',
        rule_id: 'BR_PAY_009',
        scenario_title: 'Verify EPF 12% deduction with Statutory Rs 15,000 ceiling cap and EPS 8.33% split',
        test_tier: 'E2E_PLAYWRIGHT',
        action_flow: '1. Login as Payroll Admin -> 2. Navigate to Monthly Run -> 3. Add employee with Rs 40,000 basic -> 4. Calculate Payroll -> 5. Verify EPF slip item',
        assertions: [
          'EPF Employee deduction equals exactly 1,800 INR (12% of 15,000 cap)',
          'EPS Employer contribution equals 1,250 INR (8.33% of 15,000)',
          'EPF Employer difference equals 550 INR (1,800 - 1,250)'
        ],
        synthetic_data_fixture: 'PayrollEmployeeFactory::createStandardSalaried({ basicSalary: 40000, epfCapped: true })'
      }
    });

    const parsedPropose = JSON.parse(proposeRes.content[0].text);
    console.log('  ✔ Proposed Artifact ID:', parsedPropose.artifact_id);
    console.log('  ✔ Lifecycle Status:', parsedPropose.status);
    console.log('  ✔ Governance Review URL:', parsedPropose.review_url);

    // 7. Inspect Review Queue
    console.log('\n[Step 7] Checking Staging Review Queue...');
    const queueRes = await client.send('tools/call', {
      name: 'list_review_queue',
      arguments: { status: 'PROPOSED' }
    });
    const parsedQueue = JSON.parse(queueRes.content[0].text);
    console.log(`  ✔ Total Proposed Scenarios Pending Review: ${parsedQueue.total}`);
    console.log(`  ✔ Latest Staged: ${parsedQueue.artifacts[0]?.scenario_title}`);

    console.log('\n================================================================');
    console.log('ALL MCP AGENT TEST STEPS PASSED SUCCESSFULLY!');
    console.log('The QA Automation repo can fetch full context, run TIA, and stage tests.');
    console.log('================================================================\n');
  } catch (err) {
    console.error('✖ MCP Integration Test Failed:', err);
    process.exitCode = 1;
  } finally {
    client.close();
  }
}

runVerification();
