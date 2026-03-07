#!/bin/bash
set -e

# Load deployment configuration
if [ -f "$(dirname "$0")/.env.deploy" ]; then
  export $(grep -v '^#' "$(dirname "$0")/.env.deploy" | xargs)
fi

echo "🚀 Starting backend deployment..."

# Configuration
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_REPO="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/${BACKEND_TASK_FAMILY}"
SERVICE="${BACKEND_SERVICE}"
TASK_FAMILY="${BACKEND_TASK_FAMILY}"

# Build Docker image
echo "📦 Building Docker image..."
cd "$(dirname "$0")"
docker build -f backend/Dockerfile -t ${ECR_REPO}:latest .

# Login to ECR
echo "🔐 Logging in to ECR..."
aws ecr get-login-password --region ${REGION} | docker login --username AWS --password-stdin ${ECR_REPO}

# Push to ECR
echo "⬆️  Pushing to ECR..."
docker push ${ECR_REPO}:latest

# Register new task definition
echo "📋 Registering task definition..."
CURRENT_TASK_DEF=$(aws ecs describe-services --cluster ${CLUSTER} --services ${SERVICE} --region ${REGION} \
  --query 'services[0].taskDefinition' --output text)

# Get existing task def as base, update env vars
python3 -c "
import json, subprocess

# Get current task definition
result = subprocess.run(
    ['aws', 'ecs', 'describe-task-definition', '--task-definition', '${CURRENT_TASK_DEF}',
     '--region', '${REGION}', '--query', 'taskDefinition', '--output', 'json'],
    capture_output=True, text=True
)
td = json.loads(result.stdout)

# Remote environment variables (production)
remote_env = {
    'ENVIRONMENT': '${ENVIRONMENT}',
    'DEBUG': '${DEBUG}',
    'LOG_LEVEL': '${LOG_LEVEL}',
    'AWS_REGION': '${REGION}',
    'STORAGE_BACKEND': '${STORAGE_BACKEND}',
    'S3_SKILLS_BUCKET': '${S3_SKILLS_BUCKET_NAME}-${ACCOUNT_ID}',
    'S3_SKILLS_PREFIX': '${S3_SKILLS_PREFIX}',
    'SKILLS_DIR': '${SKILLS_DIR}',
    'SKILL_CACHE_DIR': '${SKILL_CACHE_DIR}',
    'SKILLS_WATCH_ENABLED': '${SKILLS_WATCH_ENABLED}',
    'DYNAMODB_SKILLS_TABLE': '${DYNAMODB_SKILLS_TABLE}',
    'DYNAMODB_SESSIONS_TABLE': '${DYNAMODB_SESSIONS_TABLE}',
    'DYNAMODB_INVOCATION_LOGS_TABLE': '${DYNAMODB_INVOCATION_LOGS_TABLE}',
    'INVOCATION_LOG_TTL_DAYS': '${INVOCATION_LOG_TTL_DAYS}',
    'MCP_SERVER_URL': '${API_BASE_URL}/mcp',
    'CODE_INTERPRETER_ENABLED': '${CODE_INTERPRETER_ENABLED}',
    'CODE_INTERPRETER_ID': '${CODE_INTERPRETER_ID}',
    'CODE_INTERPRETER_DEFAULT_TIMEOUT': '${CODE_INTERPRETER_DEFAULT_TIMEOUT}',
    'CODE_INTERPRETER_SESSION_TIMEOUT': '${CODE_INTERPRETER_SESSION_TIMEOUT}',
    'CODE_INTERPRETER_S3_BUCKET': '${S3_SKILLS_BUCKET_NAME}-${ACCOUNT_ID}',
    'CODE_INTERPRETER_S3_PREFIX': '${S3_OUTPUT_PREFIX}',
    # Cognito S2S Authentication
    'COGNITO_ENABLED': '${COGNITO_ENABLED}',
    'COGNITO_USER_POOL_ID': '${COGNITO_USER_POOL_ID}',
    'COGNITO_REGION': '${COGNITO_REGION}',
    'COGNITO_ALLOWED_CLIENT_IDS': '${COGNITO_ALLOWED_CLIENT_IDS}',
    'COGNITO_TOKEN_ENDPOINT': '${COGNITO_TOKEN_ENDPOINT}',
    'COGNITO_CLIENT_ID': '${COGNITO_CLIENT_ID}',
    'COGNITO_SCOPES': '${COGNITO_SCOPES}',
    # Disable old API Key auth
    'MCP_AUTH_ENABLED': '${MCP_AUTH_ENABLED}',
}

# Replace all env vars
td['containerDefinitions'][0]['environment'] = [
    {'name': k, 'value': v} for k, v in remote_env.items()
]

# Keep only fields needed for registration
keep = ['family','containerDefinitions','taskRoleArn','executionRoleArn','networkMode',
        'requiresCompatibilities','cpu','memory','runtimePlatform']
out = {k: td[k] for k in keep if k in td}

# Fargate resources: 2 vCPU, 4 GB memory
out['cpu'] = '2048'
out['memory'] = '4096'

with open('/tmp/task-def.json', 'w') as f:
    json.dump(out, f)
"

NEW_TASK_DEF=$(aws ecs register-task-definition \
  --cli-input-json file:///tmp/task-def.json \
  --region ${REGION} \
  --query 'taskDefinition.taskDefinitionArn' --output text)
echo "   New task definition: ${NEW_TASK_DEF}"

# Update service with new task definition
echo "🔄 Updating ECS service..."
aws ecs update-service \
  --cluster ${CLUSTER} \
  --service ${SERVICE} \
  --task-definition ${NEW_TASK_DEF} \
  --force-new-deployment \
  --region ${REGION} \
  --query 'service.serviceName' \
  --output text

echo "✅ Deployment triggered!"
echo "📊 Check status: aws ecs describe-services --cluster ${CLUSTER} --services ${SERVICE} --region ${REGION}"
