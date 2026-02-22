#!/bin/bash
set -e

# Load deployment configuration
if [ -f "$(dirname "$0")/.env.deploy" ]; then
  export $(grep -v '^#' "$(dirname "$0")/.env.deploy" | xargs)
fi

echo "🚀 Starting frontend deployment..."

# Configuration
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_REPO="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/${FRONTEND_TASK_FAMILY}"
SERVICE="${FRONTEND_SERVICE}"
TASK_FAMILY="${FRONTEND_TASK_FAMILY}"

# Build Docker image
echo "🐳 Building Docker image..."
cd "$(dirname "$0")/frontend"
docker build \
  --build-arg VITE_API_BASE_URL=${API_BASE_URL} \
  --build-arg VITE_MCP_SERVER_URL=${API_BASE_URL}/mcp \
  -t ${ECR_REPO}:latest .

# Login to ECR
echo "🔐 Logging in to ECR..."
aws ecr get-login-password --region ${REGION} | docker login --username AWS --password-stdin ${ECR_REPO}

# Push to ECR
echo "⬆️  Pushing to ECR..."
docker push ${ECR_REPO}:latest

# Register new task definition
echo "📝 Registering task definition..."
TASK_DEF=$(cat <<EOF
{
  "family": "${TASK_FAMILY}",
  "executionRoleArn": "arn:aws:iam::${ACCOUNT_ID}:role/${ECS_EXECUTION_ROLE}",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "${FRONTEND_CPU}",
  "memory": "${FRONTEND_MEMORY}",
  "containerDefinitions": [
    {
      "name": "frontend",
      "image": "${ECR_REPO}:latest",
      "essential": true,
      "portMappings": [
        {
          "containerPort": 80,
          "protocol": "tcp"
        }
      ],
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/${TASK_FAMILY}",
          "awslogs-create-group": "true",
          "awslogs-region": "${REGION}",
          "awslogs-stream-prefix": "ecs"
        }
      }
    }
  ]
}
EOF
)

aws ecs register-task-definition \
  --cli-input-json "${TASK_DEF}" \
  --region ${REGION} \
  --query 'taskDefinition.taskDefinitionArn' \
  --output text

# Update service
echo "🔄 Updating ECS service..."
aws ecs update-service \
  --cluster ${CLUSTER} \
  --service ${SERVICE} \
  --task-definition ${TASK_FAMILY} \
  --force-new-deployment \
  --region ${REGION} \
  --query 'service.serviceName' \
  --output text

echo "✅ Deployment complete!"
echo "   API_BASE_URL: ${API_BASE_URL}"
echo "📊 Check status: aws ecs describe-services --cluster ${CLUSTER} --services ${SERVICE} --region ${REGION}"
