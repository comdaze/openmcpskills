#!/usr/bin/env node
/**
 * Lightweight stdio-to-HTTP MCP proxy.
 *
 * Reads JSON-RPC messages from stdin, forwards them to a remote MCP server
 * over Streamable HTTP with an API key header, and writes responses to stdout.
 *
 * Usage in mcp.json:
 *   {
 *     "command": "node",
 *     "args": ["/path/to/mcp-proxy.mjs"],
 *     "env": {
 *       "MCP_SERVER_URL": "https://mcp.openmcpskills.click/mcp",
 *       "MCP_API_KEY": "sk-mcp-xxx"
 *     }
 *   }
 *
 * For OAuth (Cognito Client Credentials), set:
 *   COGNITO_TOKEN_ENDPOINT, COGNITO_CLIENT_ID, COGNITO_CLIENT_SECRET, COGNITO_SCOPES
 */

const serverUrl = process.env.MCP_SERVER_URL;
const apiKey = process.env.MCP_API_KEY;

// OAuth (Cognito Client Credentials) config
const cognitoTokenEndpoint = process.env.COGNITO_TOKEN_ENDPOINT;
const cognitoClientId = process.env.COGNITO_CLIENT_ID;
const cognitoClientSecret = process.env.COGNITO_CLIENT_SECRET;
const cognitoScopes =
  process.env.COGNITO_SCOPES || "openmcpskills-api/mcp openmcpskills-api/read";

const useOAuth = !!(cognitoTokenEndpoint && cognitoClientId && cognitoClientSecret);

if (!serverUrl) {
  process.stderr.write("MCP_SERVER_URL environment variable is required\n");
  process.exit(1);
}

let sessionId = null;

// OAuth token cache
let cachedToken = null;
let tokenExpiresAt = 0;

async function getAccessToken() {
  const now = Date.now();
  // Refresh 60s before expiry
  if (cachedToken && now < tokenExpiresAt - 60_000) {
    return cachedToken;
  }

  const credentials = Buffer.from(
    `${cognitoClientId}:${cognitoClientSecret}`
  ).toString("base64");

  const res = await fetch(cognitoTokenEndpoint, {
    method: "POST",
    headers: {
      "Content-Type": "application/x-www-form-urlencoded",
      Authorization: `Basic ${credentials}`,
    },
    body: `grant_type=client_credentials&scope=${encodeURIComponent(cognitoScopes)}`,
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Token request failed (${res.status}): ${text}`);
  }

  const data = await res.json();
  cachedToken = data.access_token;
  tokenExpiresAt = now + data.expires_in * 1000;
  process.stderr.write("OAuth token acquired\n");
  return cachedToken;
}

async function sendToServer(message) {
  const headers = {
    "Content-Type": "application/json",
    Accept: "application/json",
  };

  if (useOAuth) {
    const token = await getAccessToken();
    headers["Authorization"] = `Bearer ${token}`;
  } else if (apiKey) {
    headers["X-API-Key"] = apiKey;
  }

  if (sessionId) headers["Mcp-Session-Id"] = sessionId;

  const res = await fetch(serverUrl, {
    method: "POST",
    headers,
    body: JSON.stringify(message),
  });

  // Capture session ID from response
  const sid = res.headers.get("mcp-session-id");
  if (sid) sessionId = sid;

  // Notifications return 202 with no body
  if (res.status === 202) return null;

  const text = await res.text();
  if (!text) return null;
  return JSON.parse(text);
}

// Read newline-delimited JSON from stdin
let buffer = "";

process.stdin.setEncoding("utf8");
process.stdin.on("data", (chunk) => {
  buffer += chunk;
  let newlineIdx;
  while ((newlineIdx = buffer.indexOf("\n")) !== -1) {
    const line = buffer.slice(0, newlineIdx).trim();
    buffer = buffer.slice(newlineIdx + 1);
    if (!line) continue;

    let msg;
    try {
      msg = JSON.parse(line);
    } catch {
      process.stderr.write(`Invalid JSON: ${line}\n`);
      continue;
    }

    sendToServer(msg)
      .then((response) => {
        if (response !== null) {
          process.stdout.write(JSON.stringify(response) + "\n");
        }
      })
      .catch((err) => {
        process.stderr.write(`Error: ${err.message}\n`);
        // Send JSON-RPC error response if the message had an id
        if (msg.id !== undefined) {
          const errResp = {
            jsonrpc: "2.0",
            id: msg.id,
            error: { code: -32603, message: err.message },
          };
          process.stdout.write(JSON.stringify(errResp) + "\n");
        }
      });
  }
});

process.stdin.on("end", () => process.exit(0));
