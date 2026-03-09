#!/bin/bash
# Test MCP endpoint with Cognito S2S authentication
#
# Usage:
#   ./infrastructure/test_mcp_auth.sh [MCP_SERVER_URL] [CLIENT_ID] [CLIENT_SECRET]
#
# If CLIENT_ID/CLIENT_SECRET are not provided, reads from cognito.env.
# S2S credentials are managed via the frontend dashboard (Settings > Cognito Credentials).

set -e

# Load config
if [ -f "infrastructure/cognito.env" ]; then
  source infrastructure/cognito.env
else
  echo "Error: infrastructure/cognito.env not found"
  echo "Run ./infrastructure/setup_cognito.sh first"
  exit 1
fi

MCP_SERVER_URL="${1:-https://mcp.openmcpskills.click/mcp}"
CLIENT_ID="${2:-${COGNITO_CLIENT_ID:-}}"
CLIENT_SECRET="${3:-${COGNITO_CLIENT_SECRET:-}}"

if [ -z "$CLIENT_ID" ] || [ -z "$CLIENT_SECRET" ]; then
  echo "Error: CLIENT_ID and CLIENT_SECRET required"
  echo ""
  echo "Usage: $0 [MCP_URL] <CLIENT_ID> <CLIENT_SECRET>"
  echo ""
  echo "Create S2S credentials via the frontend dashboard:"
  echo "  Settings > Cognito Credentials > Request Credentials"
  exit 1
fi

echo "================================================"
echo "Testing MCP Server with Cognito S2S Auth"
echo "Server: $MCP_SERVER_URL"
echo "Client: $CLIENT_ID"
echo "================================================"

# Step 1: Get access token
echo ""
echo "[1/3] Obtaining access token..."
TOKEN_RESPONSE=$(curl -s -X POST "$COGNITO_TOKEN_ENDPOINT" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -u "${CLIENT_ID}:${CLIENT_SECRET}" \
  -d "grant_type=client_credentials&scope=${COGNITO_SCOPES//,/ }")

ACCESS_TOKEN=$(echo $TOKEN_RESPONSE | jq -r '.access_token')

if [ "$ACCESS_TOKEN" == "null" ] || [ -z "$ACCESS_TOKEN" ]; then
  echo "FAIL: Could not obtain token"
  echo $TOKEN_RESPONSE | jq
  exit 1
fi
echo "  Token obtained"

# Step 2: Test MCP initialize
echo ""
echo "[2/3] Testing MCP initialize..."
INIT_RESPONSE=$(curl -s -X POST "$MCP_SERVER_URL" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
      "protocolVersion": "2024-11-05",
      "capabilities": {},
      "clientInfo": {
        "name": "test-client",
        "version": "1.0.0"
      }
    }
  }')

if echo "$INIT_RESPONSE" | jq -e '.result' > /dev/null 2>&1; then
  echo "  Initialize successful"
  echo "$INIT_RESPONSE" | jq '.result.serverInfo'
else
  echo "FAIL: Initialize failed"
  echo "$INIT_RESPONSE" | jq
  exit 1
fi

# Get session ID
SESSION_ID=$(curl -s -D - -o /dev/null -X POST "$MCP_SERVER_URL" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}' \
  | grep -i 'mcp-session-id' | cut -d':' -f2 | tr -d ' \r')

# Step 3: Test tools/list
echo ""
echo "[3/3] Testing tools/list..."
TOOLS_RESPONSE=$(curl -s -X POST "$MCP_SERVER_URL" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Mcp-Session-Id: $SESSION_ID" \
  -d '{
    "jsonrpc": "2.0",
    "id": 2,
    "method": "tools/list"
  }')

if echo "$TOOLS_RESPONSE" | jq -e '.result.tools' > /dev/null 2>&1; then
  TOOL_COUNT=$(echo "$TOOLS_RESPONSE" | jq '.result.tools | length')
  echo "  tools/list successful - Found $TOOL_COUNT tools"
  echo ""
  echo "First 5 tools:"
  echo "$TOOLS_RESPONSE" | jq '.result.tools[:5] | .[].name'
else
  echo "FAIL: tools/list failed"
  echo "$TOOLS_RESPONSE" | jq
  exit 1
fi

echo ""
echo "================================================"
echo "All tests passed!"
echo "================================================"
