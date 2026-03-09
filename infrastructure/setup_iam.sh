#!/bin/bash

# Open MCP Skills - IAM Permissions Setup
# Configures ECS task role with required permissions for:
#   - DynamoDB (skills, sessions, invocation logs, API keys)
#   - Cognito (client management for self-service provisioning)

set -e

REGION="${1:-us-east-1}"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
TASK_ROLE="open-mcp-skills-task-role"

# Load deployment config for Cognito User Pool ID
if [ -f "$(dirname "$0")/../.env.deploy" ]; then
  export $(grep -v '^#' "$(dirname "$0")/../.env.deploy" | xargs)
fi

COGNITO_POOL_ID="${COGNITO_USER_POOL_ID:-}"

echo "================================================"
echo "Setting up IAM Permissions"
echo "Account: $ACCOUNT_ID"
echo "Region: $REGION"
echo "Task Role: $TASK_ROLE"
echo "Cognito Pool: ${COGNITO_POOL_ID:-(not configured)}"
echo "================================================"

# 1. DynamoDB + S3 storage access (includes mcp-api-keys table)
echo ""
echo "[1/2] Updating storage access policy..."
aws iam put-role-policy \
  --role-name "$TASK_ROLE" \
  --policy-name mcp-skills-storage-access \
  --policy-document "{
  \"Version\": \"2012-10-17\",
  \"Statement\": [
    {
      \"Effect\": \"Allow\",
      \"Action\": [
        \"s3:GetObject\",
        \"s3:PutObject\",
        \"s3:ListBucket\",
        \"s3:DeleteObject\"
      ],
      \"Resource\": [
        \"arn:aws:s3:::mcp-skills-bucket-${ACCOUNT_ID}\",
        \"arn:aws:s3:::mcp-skills-bucket-${ACCOUNT_ID}/*\"
      ]
    },
    {
      \"Effect\": \"Allow\",
      \"Action\": [
        \"dynamodb:GetItem\",
        \"dynamodb:PutItem\",
        \"dynamodb:UpdateItem\",
        \"dynamodb:DeleteItem\",
        \"dynamodb:Query\",
        \"dynamodb:Scan\",
        \"dynamodb:CreateTable\",
        \"dynamodb:DescribeTable\"
      ],
      \"Resource\": [
        \"arn:aws:dynamodb:${REGION}:${ACCOUNT_ID}:table/mcp-skills\",
        \"arn:aws:dynamodb:${REGION}:${ACCOUNT_ID}:table/mcp-skills/index/*\",
        \"arn:aws:dynamodb:${REGION}:${ACCOUNT_ID}:table/mcp-invocation-logs\",
        \"arn:aws:dynamodb:${REGION}:${ACCOUNT_ID}:table/mcp-sessions\",
        \"arn:aws:dynamodb:${REGION}:${ACCOUNT_ID}:table/mcp-api-keys\"
      ]
    }
  ]
}"
echo "  Updated: mcp-skills-storage-access (added mcp-api-keys table)"

# 2. Cognito client management (for self-service credential provisioning)
echo ""
echo "[2/2] Updating Cognito client management policy..."
if [ -n "$COGNITO_POOL_ID" ]; then
  aws iam put-role-policy \
    --role-name "$TASK_ROLE" \
    --policy-name cognito-client-management \
    --policy-document "{
    \"Version\": \"2012-10-17\",
    \"Statement\": [
      {
        \"Effect\": \"Allow\",
        \"Action\": [
          \"cognito-idp:CreateUserPoolClient\",
          \"cognito-idp:DeleteUserPoolClient\",
          \"cognito-idp:ListUserPoolClients\",
          \"cognito-idp:DescribeUserPoolClient\"
        ],
        \"Resource\": [
          \"arn:aws:cognito-idp:${REGION}:${ACCOUNT_ID}:userpool/${COGNITO_POOL_ID}\"
        ]
      }
    ]
  }"
  echo "  Updated: cognito-client-management (pool: ${COGNITO_POOL_ID})"
else
  echo "  Skipped: COGNITO_USER_POOL_ID not set in .env.deploy"
fi

# Verify
echo ""
echo "================================================"
echo "Verifying policies on role: $TASK_ROLE"
echo "================================================"
aws iam list-role-policies --role-name "$TASK_ROLE" --output json | \
  python3 -c "import sys,json; [print(f'  - {p}') for p in json.load(sys.stdin)['PolicyNames']]"

echo ""
echo "Done. Policies take effect immediately (no ECS restart needed)."
