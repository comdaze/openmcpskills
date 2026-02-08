#!/bin/bash
# Initialize local DynamoDB and S3 for development
# Requires: docker, aws cli

set -e

DYNAMODB_ENDPOINT="http://localhost:8001"
S3_ENDPOINT="http://localhost:4566"
REGION="us-east-1"

echo "=== Creating DynamoDB tables ==="

aws dynamodb create-table \
  --endpoint-url "$DYNAMODB_ENDPOINT" \
  --table-name mcp-skills \
  --attribute-definitions \
    AttributeName=skill_id,AttributeType=S \
    AttributeName=status,AttributeType=S \
    AttributeName=updated_at,AttributeType=S \
  --key-schema AttributeName=skill_id,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --global-secondary-indexes '[{"IndexName":"status-index","KeySchema":[{"AttributeName":"status","KeyType":"HASH"},{"AttributeName":"updated_at","KeyType":"RANGE"}],"Projection":{"ProjectionType":"ALL"}}]' \
  --region "$REGION" 2>/dev/null && echo "Created mcp-skills" || echo "mcp-skills already exists"

aws dynamodb create-table \
  --endpoint-url "$DYNAMODB_ENDPOINT" \
  --table-name mcp-invocation-logs \
  --attribute-definitions \
    AttributeName=skill_id,AttributeType=S \
    AttributeName=invoked_at,AttributeType=S \
  --key-schema AttributeName=skill_id,KeyType=HASH AttributeName=invoked_at,KeyType=RANGE \
  --billing-mode PAY_PER_REQUEST \
  --region "$REGION" 2>/dev/null && echo "Created mcp-invocation-logs" || echo "mcp-invocation-logs already exists"

echo "=== Creating S3 bucket ==="

aws s3api create-bucket \
  --endpoint-url "$S3_ENDPOINT" \
  --bucket mcp-skills-bucket \
  --region "$REGION" 2>/dev/null && echo "Created mcp-skills-bucket" || echo "mcp-skills-bucket already exists"

echo "=== Done ==="
