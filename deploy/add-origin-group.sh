#!/bin/bash
set -e

# =============================================================================
# 添加 Origin Group 实现故障转移
# =============================================================================

DISTRIBUTION_ID="${1:-}"
BACKUP_ALB_DNS="${2:-}"

if [ -z "$DISTRIBUTION_ID" ]; then
  echo "用法: $0 <distribution-id> [backup-alb-dns]"
  echo ""
  echo "示例:"
  echo "  $0 E1234567890ABC"
  echo "  $0 E1234567890ABC my-backup-alb.us-east-1.elb.amazonaws.com"
  exit 1
fi

echo "🔍 获取当前配置: $DISTRIBUTION_ID"

aws cloudfront get-distribution-config --id "$DISTRIBUTION_ID" > /tmp/cf-config.json
ETAG=$(jq -r '.ETag' /tmp/cf-config.json)
jq '.DistributionConfig' /tmp/cf-config.json > /tmp/cf-dist-config.json

# 获取现有 Origin ID
PRIMARY_ORIGIN_ID=$(jq -r '.Origins.Items[0].Id' /tmp/cf-dist-config.json)
PRIMARY_ORIGIN_DOMAIN=$(jq -r '.Origins.Items[0].DomainName' /tmp/cf-dist-config.json)

echo "  Primary Origin: $PRIMARY_ORIGIN_ID ($PRIMARY_ORIGIN_DOMAIN)"
echo "  ETag: $ETAG"

# 如果没有提供备用 ALB，使用相同的 (同区域多 AZ 场景)
BACKUP_ALB_DNS="${BACKUP_ALB_DNS:-$PRIMARY_ORIGIN_DOMAIN}"
BACKUP_ORIGIN_ID="${PRIMARY_ORIGIN_ID}-backup"

echo ""
echo "🔧 配置 Origin Group..."

# 添加备用 Origin 和 Origin Group
jq --arg backupId "$BACKUP_ORIGIN_ID" \
   --arg backupDomain "$BACKUP_ALB_DNS" \
   --arg primaryId "$PRIMARY_ORIGIN_ID" \
   '
  # 添加备用 Origin
  .Origins.Items += [{
    "Id": $backupId,
    "DomainName": $backupDomain,
    "CustomOriginConfig": {
      "HTTPPort": 80,
      "HTTPSPort": 443,
      "OriginProtocolPolicy": "http-only",
      "OriginSslProtocols": {
        "Quantity": 1,
        "Items": ["TLSv1.2"]
      },
      "OriginReadTimeout": 180,
      "OriginKeepaliveTimeout": 60
    },
    "ConnectionAttempts": 3,
    "ConnectionTimeout": 10
  }] |
  .Origins.Quantity = (.Origins.Items | length) |

  # 添加 Origin Group
  .OriginGroups = {
    "Quantity": 1,
    "Items": [{
      "Id": "failover-group",
      "FailoverCriteria": {
        "StatusCodes": {
          "Quantity": 4,
          "Items": [500, 502, 503, 504]
        }
      },
      "Members": {
        "Quantity": 2,
        "Items": [
          {"OriginId": $primaryId},
          {"OriginId": $backupId}
        ]
      }
    }]
  } |

  # 更新 DefaultCacheBehavior 使用 Origin Group
  .DefaultCacheBehavior.TargetOriginId = "failover-group" |

  # 更新所有 CacheBehaviors 使用 Origin Group
  if .CacheBehaviors.Items then
    .CacheBehaviors.Items |= map(.TargetOriginId = "failover-group")
  else
    .
  end
' /tmp/cf-dist-config.json > /tmp/cf-dist-config-failover.json

echo ""
echo "📋 Origin Group 配置:"
echo "  • Primary: $PRIMARY_ORIGIN_ID"
echo "  • Backup: $BACKUP_ORIGIN_ID ($BACKUP_ALB_DNS)"
echo "  • Failover 触发: 500, 502, 503, 504"
echo ""

echo "Origins:"
jq '.Origins.Items[] | {Id: .Id, Domain: .DomainName}' /tmp/cf-dist-config-failover.json

echo ""
echo "Origin Group:"
jq '.OriginGroups' /tmp/cf-dist-config-failover.json

echo ""
read -p "是否应用更新? (y/n): " confirm

if [ "$confirm" = "y" ]; then
  echo ""
  echo "🚀 应用更新..."

  aws cloudfront update-distribution \
    --id "$DISTRIBUTION_ID" \
    --if-match "$ETAG" \
    --distribution-config file:///tmp/cf-dist-config-failover.json \
    --no-cli-pager

  echo ""
  echo "✅ Origin Group 配置完成!"
  echo ""
  echo "⏳ 部署状态:"
  echo "   aws cloudfront get-distribution --id $DISTRIBUTION_ID --query 'Distribution.Status'"
else
  echo ""
  echo "❌ 已取消"
  echo ""
  echo "配置文件: /tmp/cf-dist-config-failover.json"
fi
