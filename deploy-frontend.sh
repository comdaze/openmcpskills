#!/bin/bash
set -e

echo "🚀 Starting frontend deployment..."

# Configuration
REGION="us-east-1"
CLUSTER="open-mcp-skills"
SERVICE="skillforge-frontend"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_REPO="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/skillforge-frontend"

# Build frontend
echo "📦 Building frontend..."
cd "$(dirname "$0")/frontend"
npm run build

# Build Docker image
echo "🐳 Building Docker image..."
docker build -t ${ECR_REPO}:latest .

# Login to ECR
echo "🔐 Logging in to ECR..."
aws ecr get-login-password --region ${REGION} | docker login --username AWS --password-stdin ${ECR_REPO}

# Push to ECR
echo "⬆️  Pushing to ECR..."
docker push ${ECR_REPO}:latest

# Force new deployment
echo "🔄 Triggering ECS deployment..."
aws ecs update-service \
  --cluster ${CLUSTER} \
  --service ${SERVICE} \
  --force-new-deployment \
  --region ${REGION} \
  --query 'service.serviceName' \
  --output text

echo "✅ Deployment triggered successfully!"
echo "📊 Check status: aws ecs describe-services --cluster ${CLUSTER} --services ${SERVICE} --region ${REGION}"
