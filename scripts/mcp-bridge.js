#!/usr/bin/env node
/**
 * Zero-Dependency Enterprise MCP Stdio-to-HTTP Bridge
 *
 * Location: orangehrm-qa-automation/scripts/mcp-bridge.js
 *
 * Allows any colleague or CI agent in this repository to communicate with the
 * QKG Intelligence Platform via standard stdio without needing local database
 * installations or local OrangeHRM backend clones.
 *
 * Configuration:
 *   Set QKG_SERVER_URL in your environment or .env file.
 *   Default: http://127.0.0.1:4500
 *   Enterprise Staging Example: https://qkg.internal.company.com
 */

const http = require('http');
const https = require('https');
const readline = require('readline');
const { URL } = require('url');

const QKG_SERVER_URL = process.env.QKG_SERVER_URL || 'http://127.0.0.1:4500';

function forwardToQkg(jsonRpcPayload) {
  return new Promise((resolve, reject) => {
    try {
      const u = new URL('/mcp', QKG_SERVER_URL);
      const isHttps = u.protocol === 'https:';
      const transport = isHttps ? https : http;

      const body = JSON.stringify(jsonRpcPayload);
      const req = transport.request(
        {
          hostname: u.hostname,
          port: u.port || (isHttps ? 443 : 80),
          path: u.pathname,
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Content-Length': Buffer.byteLength(body)
          },
          timeout: 10000
        },
        (res) => {
          let raw = '';
          res.on('data', (chunk) => (raw += chunk));
          res.on('end', () => {
            if (res.statusCode === 204) {
              return resolve(null);
            }
            try {
              const parsed = JSON.parse(raw);
              resolve(parsed);
            } catch {
              resolve({
                jsonrpc: '2.0',
                id: jsonRpcPayload.id || null,
                error: { code: -32700, message: `Invalid JSON response from QKG server: ${raw}` }
              });
            }
          });
        }
      );

      req.on('error', (err) => {
        resolve({
          jsonrpc: '2.0',
          id: jsonRpcPayload.id || null,
          error: {
            code: -32000,
            message: `QKG Server Unreachable at ${QKG_SERVER_URL}. Ensure QKG Platform is running or update QKG_SERVER_URL. (${err.message})`
          }
        });
      });

      req.on('timeout', () => {
        req.destroy();
        resolve({
          jsonrpc: '2.0',
          id: jsonRpcPayload.id || null,
          error: { code: -32000, message: `QKG Server request timed out at ${QKG_SERVER_URL}` }
        });
      });

      req.write(body);
      req.end();
    } catch (err) {
      resolve({
        jsonrpc: '2.0',
        id: jsonRpcPayload.id || null,
        error: { code: -32000, message: err.message }
      });
    }
  });
}

const rl = readline.createInterface({
  input: process.stdin,
  output: process.stdout,
  terminal: false
});

rl.on('line', async (line) => {
  const trimmed = line.trim();
  if (!trimmed) return;
  try {
    const rpc = JSON.parse(trimmed);
    const result = await forwardToQkg(rpc);
    if (result) {
      process.stdout.write(JSON.stringify(result) + '\n');
    }
  } catch (err) {
    process.stderr.write(`[MCP Bridge Error] ${err.message}\n`);
  }
});

process.stderr.write(`[QKG MCP Bridge] Active -> forwarding to ${QKG_SERVER_URL}/mcp\n`);
