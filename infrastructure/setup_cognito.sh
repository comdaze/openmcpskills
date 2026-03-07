#!/bin/bash

# Open MCP Skills - Cognito S2S Authentication Setup
# Creates Cognito User Pool, Domain, Resource Server, and App Client

set -e

REGION="${1:-us-east-1}"
PROJECT_NAME="openmcpskills"

echo "================================================"
echo "Setting up Cognito S2S Authentication"
echo "Project: $PROJECT_NAME"
echo "Region: $REGION"
echo "================================================"

# 1. Create User Pool
echo ""
echo "[1/5] Creating User Pool..."
POOL_RESPONSE=$(aws cognito-idp create-user-pool \
  --pool-name "${PROJECT_NAME}-auth-pool" \
  --region $REGION)
POOL_ID=$(echo $POOL_RESPONSE | jq -r '.UserPool.Id')
echo "✓ User Pool ID: $POOL_ID"

# 2. Create Domain
echo ""
echo "[2/5] Creating Domain..."
DOMAIN_PREFIX="${PROJECT_NAME}-$(date +%s)"
aws cognito-idp create-user-pool-domain \
  --domain $DOMAIN_PREFIX \
  --user-pool-id $POOL_ID \
  --region $REGION
TOKEN_ENDPOINT="https://${DOMAIN_PREFIX}.auth.${REGION}.amazoncognito.com/oauth2/token"
echo "✓ Token URL: $TOKEN_ENDPOINT"

# 3. Create Resource Server
echo ""
echo "[3/5] Creating Resource Server..."
RESOURCE_SERVER_IDENTIFIER="${PROJECT_NAME}-api"
aws cognito-idp create-resource-server \
  --user-pool-id $POOL_ID \
  --identifier $RESOURCE_SERVER_IDENTIFIER \
  --name "Open MCP Skills API" \
  --scopes \
    ScopeName=mcp,ScopeDescription="MCP protocol access" \
    ScopeName=admin,ScopeDescription="Admin access" \
    ScopeName=read,ScopeDescription="Read access" \
  --region $REGION
echo "✓ Resource Server: $RESOURCE_SERVER_IDENTIFIER"

# 4. Create App Client (Service-to-Service)
echo ""
echo "[4/5] Creating App Client for Service-to-Service Auth..."
CLIENT_RESPONSE=$(aws cognito-idp create-user-pool-client \
  --user-pool-id $POOL_ID \
  --client-name "${PROJECT_NAME}-service-client" \
  --generate-secret \
  --allowed-o-auth-flows "client_credentials" \
  --allowed-o-auth-scopes \
    "${RESOURCE_SERVER_IDENTIFIER}/mcp" \
    "${RESOURCE_SERVER_IDENTIFIER}/read" \
  --allowed-o-auth-flows-user-pool-client \
  --region $REGION)
CLIENT_ID=$(echo $CLIENT_RESPONSE | jq -r '.UserPoolClient.ClientId')
CLIENT_SECRET=$(echo $CLIENT_RESPONSE | jq -r '.UserPoolClient.ClientSecret')
echo "✓ Client ID: $CLIENT_ID"
echo "✓ Client Secret: $CLIENT_SECRET"

# 5. Test obtaining token
echo ""
echo "[5/5] Testing token retrieval..."
TOKEN_RESPONSE=$(curl -s -X POST "$TOKEN_ENDPOINT" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -u "${CLIENT_ID}:${CLIENT_SECRET}" \
  -d "grant_type=client_credentials&scope=${RESOURCE_SERVER_IDENTIFIER}/mcp ${RESOURCE_SERVER_IDENTIFIER}/read")
ACCESS_TOKEN=$(echo $TOKEN_RESPONSE | jq -r '.access_token')

if [ "$ACCESS_TOKEN" != "null" ] && [ ! -z "$ACCESS_TOKEN" ]; then
  echo "✓ Token obtained successfully!"
  echo "Access Token (first 50 chars): ${ACCESS_TOKEN:0:50}..."
else
  echo "✗ Failed to obtain token"
  echo $TOKEN_RESPONSE | jq
fi

# Generate Discovery URL
DISCOVERY_URL="https://cognito-idp.${REGION}.amazonaws.com/${POOL_ID}/.well-known/openid-configuration"

# Write configuration to file
CONFIG_FILE="infrastructure/cognito-config.txt"
mkdir -p infrastructure

cat > $CONFIG_FILE << EOFCONFIG
================================================
Open MCP Skills S2S Authentication Configuration
================================================
User Pool ID: $POOL_ID
Region: $REGION
Domain Prefix: $DOMAIN_PREFIX
Token Endpoint: $TOKEN_ENDPOINT
Discovery URL: $DISCOVERY_URL
Resource Server: $RESOURCE_SERVER_IDENTIFIER

App Client (Service-to-Service):
  Client ID: $CLIENT_ID
  Client Secret: $CLIENT_SECRET

Scopes:
  - ${RESOURCE_SERVER_IDENTIFIER}/mcp
  - ${RESOURCE_SERVER_IDENTIFIER}/read
  - ${RESOURCE_SERVER_IDENTIFIER}/admin

Environment Variables for Open MCP Skills:
  COGNITO_ENABLED=true
  COGNITO_USER_POOL_ID=$POOL_ID
  COGNITO_REGION=$REGION
  COGNITO_ALLOWED_CLIENT_IDS=$CLIENT_ID
  COGNITO_TOKEN_ENDPOINT=$TOKEN_ENDPOINT
  COGNITO_DISCOVERY_URL=$DISCOVERY_URL
  COGNITO_RESOURCE_SERVER=$RESOURCE_SERVER_IDENTIFIER

Quick Suite MCP Integration Configuration:
  MCP Server URL: https://your-domain/mcp
  Authentication Type: OAuth 2.0 / Service Account
  Token URL: $TOKEN_ENDPOINT
  Client ID: $CLIENT_ID
  Client Secret: $CLIENT_SECRET
  Scopes: ${RESOURCE_SERVER_IDENTIFIER}/mcp ${RESOURCE_SERVER_IDENTIFIER}/read
================================================
EOFCONFIG

# Also write a .env snippet for easy copy
cat > infrastructure/cognito.env << EOFENV
# Cognito S2S Authentication
COGNITO_ENABLED=true
COGNITO_USER_POOL_ID=$POOL_ID
COGNITO_REGION=$REGION
COGNITO_ALLOWED_CLIENT_IDS=$CLIENT_ID
COGNITO_TOKEN_ENDPOINT=$TOKEN_ENDPOINT
COGNITO_DISCOVERY_URL=$DISCOVERY_URL
COGNITO_RESOURCE_SERVER=$RESOURCE_SERVER_IDENTIFIER
COGNITO_SCOPES=${RESOURCE_SERVER_IDENTIFIER}/mcp,${RESOURCE_SERVER_IDENTIFIER}/read

# For testing - Client credentials
COGNITO_CLIENT_ID=$CLIENT_ID
COGNITO_CLIENT_SECRET=$CLIENT_SECRET
EOFENV

echo ""
echo "✓ Configuration saved to:"
echo "  - $CONFIG_FILE (full config)"
echo "  - infrastructure/cognito.env (.env snippet)"

# Create cleanup script
cat > infrastructure/cleanup-cognito.sh << 'EOFCLEANUP'
#!/bin/bash
# Load config
source infrastructure/cognito.env

echo "Cleaning up Cognito resources..."
aws cognito-idp delete-user-pool-domain --domain $DOMAIN_PREFIX --user-pool-id $COGNITO_USER_POOL_ID --region $COGNITO_REGION 2>/dev/null || true
sleep 2
aws cognito-idp delete-user-pool --user-pool-id $COGNITO_USER_POOL_ID --region $COGNITO_REGION 2>/dev/null || true
echo "✓ Resources deleted"
EOFCLEANUP
chmod +x infrastructure/cleanup-cognito.sh

# Add DOMAIN_PREFIX to cognito.env for cleanup script
echo "DOMAIN_PREFIX=$DOMAIN_PREFIX" >> infrastructure/cognito.env

# Create token test script
cat > infrastructure/test-token.sh << 'EOFTEST'
#!/bin/bash
source infrastructure/cognito.env

echo "Retrieving access token..."
TOKEN_RESPONSE=$(curl -s -X POST "$COGNITO_TOKEN_ENDPOINT" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -u "${COGNITO_CLIENT_ID}:${COGNITO_CLIENT_SECRET}" \
  -d "grant_type=client_credentials&scope=${COGNITO_SCOPES//,/ }")

ACCESS_TOKEN=$(echo $TOKEN_RESPONSE | jq -r '.access_token')

if [ "$ACCESS_TOKEN" != "null" ] && [ -n "$ACCESS_TOKEN" ]; then
  echo "✓ Token obtained successfully!"
  echo ""
  echo "Access Token:"
  echo $ACCESS_TOKEN
  echo ""
  echo "Token payload:"
  echo $ACCESS_TOKEN | cut -d'.' -f2 | base64 -d 2>/dev/null | jq . 2>/dev/null || echo "(unable to decode)"
else
  echo "✗ Failed to obtain token"
  echo $TOKEN_RESPONSE | jq
fi
EOFTEST
chmod +x infrastructure/test-token.sh

echo ""
echo "================================================"
echo "Setup complete!"
echo "================================================"
echo ""
echo "Next steps:"
echo "  1. Add the environment variables from infrastructure/cognito.env to your .env file"
echo "  2. Start the MCP server with Cognito authentication enabled"
echo "  3. Test with: ./infrastructure/test-token.sh"
echo ""
echo "To cleanup: ./infrastructure/cleanup-cognito.sh"
echo ""
