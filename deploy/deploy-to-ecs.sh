#!/bin/bash
set -e

# 配置
AWS_REGION="us-east-1"
AWS_ACCOUNT_ID="383570952416"
ECR_REPO="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/open-mcp-skills"
ECS_CLUSTER="open-mcp-skills"
ECS_SERVICE="mcp-server-alb"
IMAGE_TAG="${1:-latest}"

echo "🚀 开始部署 MCP 服务器到 ECS..."
echo "镜像标签: ${IMAGE_TAG}"
echo ""

# 1. 构建 Docker 镜像
echo "📦 步骤 1/4: 构建 Docker 镜像 (amd64 架构)..."
cd "$(dirname "$0")/.." || exit 1
docker buildx build --platform linux/amd64 -t open-mcp-skills:${IMAGE_TAG} -f backend/Dockerfile . --load

# 2. 登录 ECR
echo "🔐 步骤 2/4: 登录 ECR..."
aws ecr get-login-password --region ${AWS_REGION} | \
  docker login --username AWS --password-stdin ${ECR_REPO}

# 3. 推送镜像
echo "⬆️  步骤 3/4: 推送镜像到 ECR..."
docker tag open-mcp-skills:${IMAGE_TAG} ${ECR_REPO}:${IMAGE_TAG}
docker push ${ECR_REPO}:${IMAGE_TAG}

# 4. 更新 ECS 服务
echo "🔄 步骤 4/4: 更新 ECS 服务..."
aws ecs update-service \
  --cluster ${ECS_CLUSTER} \
  --service ${ECS_SERVICE} \
  --force-new-deployment \
  --region ${AWS_REGION} \
  --no-cli-pager

echo ""
echo "✅ 部署完成！"
echo ""
echo "查看部署状态:"
echo "  aws ecs describe-services --cluster ${ECS_CLUSTER} --services ${ECS_SERVICE} --region ${AWS_REGION}"
echo ""
echo "查看服务日志:"
echo "  aws logs tail /ecs/${ECS_CLUSTER}/${ECS_SERVICE} --follow --region ${AWS_REGION}"
echo ""
echo "测试服务:"
echo "  curl http://open-mcp-skills-alb-222909331.us-east-1.elb.amazonaws.com/info"
