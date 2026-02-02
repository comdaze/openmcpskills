#!/bin/bash
set -e

# =============================================================================
# 快速更新 CloudFront Origin 配置
# 用于已有 Distribution 的参数调整
# =============================================================================

DISTRIBUTION_ID="${1:-}"

if [ -z "$DISTRIBUTION_ID" ]; then
  echo "用法: $0 <distribution-id>"
  echo ""
  echo "示例: $0 E1234567890ABC"
  exit 1
fi

echo "🔍 获取当前配置: $DISTRIBUTION_ID"

# 获取当前配置
aws cloudfront get-distribution-config --id "$DISTRIBUTION_ID" > /tmp/cf-config.json
ETAG=$(jq -r '.ETag' /tmp/cf-config.json)
echo "  ETag: $ETAG"

# 提取 DistributionConfig
jq '.DistributionConfig' /tmp/cf-config.json > /tmp/cf-dist-config.json

echo ""
echo "🔧 更新 Origin 配置..."

# 更新 Origin 超时参数
# OriginKeepaliveTimeout: 60 秒 (最大值)
# OriginReadTimeout: 180 秒 (最大值，适合 SSE)
# ConnectionTimeout: 10 秒 (快速故障检测)
jq '
  .Origins.Items |= map(
    if .CustomOriginConfig then
      .CustomOriginConfig.OriginKeepaliveTimeout = 60 |
      .CustomOriginConfig.OriginReadTimeout = 180 |
      .ConnectionTimeout = 10 |
      .ConnectionAttempts = 3
    else
      .
    end
  )
' /tmp/cf-dist-config.json > /tmp/cf-dist-config-updated.json

echo "  ✅ Origin 参数已更新:"
echo "     - OriginKeepaliveTimeout: 60s"
echo "     - OriginReadTimeout: 180s"
echo "     - ConnectionTimeout: 10s"
echo "     - ConnectionAttempts: 3"

# 显示变更
echo ""
echo "📋 变更预览 (Origins):"
jq '.Origins.Items[] | {Id: .Id, KeepaliveTimeout: .CustomOriginConfig.OriginKeepaliveTimeout, ReadTimeout: .CustomOriginConfig.OriginReadTimeout, ConnTimeout: .ConnectionTimeout}' /tmp/cf-dist-config-updated.json

echo ""
read -p "是否应用更新? (y/n): " confirm

if [ "$confirm" = "y" ]; then
  echo ""
  echo "🚀 应用更新..."

  aws cloudfront update-distribution \
    --id "$DISTRIBUTION_ID" \
    --if-match "$ETAG" \
    --distribution-config file:///tmp/cf-dist-config-updated.json \
    --no-cli-pager

  echo ""
  echo "✅ 更新已提交!"
  echo ""
  echo "⏳ 等待部署完成..."
  echo "   aws cloudfront wait distribution-deployed --id $DISTRIBUTION_ID"
  echo ""
  echo "📊 检查状态:"
  echo "   aws cloudfront get-distribution --id $DISTRIBUTION_ID --query 'Distribution.Status'"
else
  echo ""
  echo "❌ 已取消"
  echo ""
  echo "手动应用命令:"
  echo "aws cloudfront update-distribution --id $DISTRIBUTION_ID --if-match $ETAG --distribution-config file:///tmp/cf-dist-config-updated.json"
fi
