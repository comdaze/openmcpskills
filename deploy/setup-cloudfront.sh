#!/bin/bash
set -e

# =============================================================================
# CloudFront 配置脚本 - 针对 MCP SSE 长连接优化
# =============================================================================

AWS_REGION="us-east-1"
ALB_DNS="open-mcp-skills-alb-222909331.us-east-1.elb.amazonaws.com"
# 备用 ALB (故障转移用，如有)
ALB_DNS_BACKUP=""

# CloudFront Distribution ID (如果已存在，填入此处进行更新)
DISTRIBUTION_ID=""

# =============================================================================
# 1. 创建 Cache Policy - SSE 端点 (无缓存)
# =============================================================================
echo "📦 创建 Cache Policy: MCP-SSE-NoCache..."

SSE_CACHE_POLICY=$(cat <<'EOF'
{
  "Name": "MCP-SSE-NoCache",
  "Comment": "No cache for SSE/streaming endpoints",
  "DefaultTTL": 0,
  "MaxTTL": 0,
  "MinTTL": 0,
  "ParametersInCacheKeyAndForwardedToOrigin": {
    "EnableAcceptEncodingGzip": false,
    "EnableAcceptEncodingBrotli": false,
    "HeadersConfig": {
      "HeaderBehavior": "whitelist",
      "Headers": {
        "Quantity": 3,
        "Items": ["Accept", "Mcp-Session-Id", "Authorization"]
      }
    },
    "CookiesConfig": {
      "CookieBehavior": "none"
    },
    "QueryStringsConfig": {
      "QueryStringBehavior": "all"
    }
  }
}
EOF
)

SSE_CACHE_POLICY_ID=$(aws cloudfront create-cache-policy \
  --cache-policy-config "$SSE_CACHE_POLICY" \
  --query 'CachePolicy.Id' \
  --output text 2>/dev/null || echo "")

if [ -z "$SSE_CACHE_POLICY_ID" ]; then
  echo "  ⚠️  Cache Policy 可能已存在，查询现有..."
  SSE_CACHE_POLICY_ID=$(aws cloudfront list-cache-policies \
    --type custom \
    --query "CachePolicyList.Items[?CachePolicy.CachePolicyConfig.Name=='MCP-SSE-NoCache'].CachePolicy.Id" \
    --output text)
fi
echo "  ✅ SSE Cache Policy ID: $SSE_CACHE_POLICY_ID"

# =============================================================================
# 2. 创建 Cache Policy - 静态资源 (长 TTL)
# =============================================================================
echo "📦 创建 Cache Policy: MCP-Static-LongTTL..."

STATIC_CACHE_POLICY=$(cat <<'EOF'
{
  "Name": "MCP-Static-LongTTL",
  "Comment": "Long TTL for static assets and video segments",
  "DefaultTTL": 86400,
  "MaxTTL": 31536000,
  "MinTTL": 3600,
  "ParametersInCacheKeyAndForwardedToOrigin": {
    "EnableAcceptEncodingGzip": true,
    "EnableAcceptEncodingBrotli": true,
    "HeadersConfig": {
      "HeaderBehavior": "none"
    },
    "CookiesConfig": {
      "CookieBehavior": "none"
    },
    "QueryStringsConfig": {
      "QueryStringBehavior": "none"
    }
  }
}
EOF
)

STATIC_CACHE_POLICY_ID=$(aws cloudfront create-cache-policy \
  --cache-policy-config "$STATIC_CACHE_POLICY" \
  --query 'CachePolicy.Id' \
  --output text 2>/dev/null || echo "")

if [ -z "$STATIC_CACHE_POLICY_ID" ]; then
  STATIC_CACHE_POLICY_ID=$(aws cloudfront list-cache-policies \
    --type custom \
    --query "CachePolicyList.Items[?CachePolicy.CachePolicyConfig.Name=='MCP-Static-LongTTL'].CachePolicy.Id" \
    --output text)
fi
echo "  ✅ Static Cache Policy ID: $STATIC_CACHE_POLICY_ID"

# =============================================================================
# 3. 创建 Origin Request Policy - 转发所有必要头
# =============================================================================
echo "📦 创建 Origin Request Policy: MCP-AllHeaders..."

ORIGIN_REQUEST_POLICY=$(cat <<'EOF'
{
  "Name": "MCP-AllHeaders",
  "Comment": "Forward headers required for MCP SSE",
  "HeadersConfig": {
    "HeaderBehavior": "whitelist",
    "Headers": {
      "Quantity": 5,
      "Items": [
        "Accept",
        "Accept-Encoding",
        "Mcp-Session-Id",
        "Authorization",
        "Content-Type"
      ]
    }
  },
  "CookiesConfig": {
    "CookieBehavior": "none"
  },
  "QueryStringsConfig": {
    "QueryStringBehavior": "all"
  }
}
EOF
)

ORIGIN_REQUEST_POLICY_ID=$(aws cloudfront create-origin-request-policy \
  --origin-request-policy-config "$ORIGIN_REQUEST_POLICY" \
  --query 'OriginRequestPolicy.Id' \
  --output text 2>/dev/null || echo "")

if [ -z "$ORIGIN_REQUEST_POLICY_ID" ]; then
  ORIGIN_REQUEST_POLICY_ID=$(aws cloudfront list-origin-request-policies \
    --type custom \
    --query "OriginRequestPolicyList.Items[?OriginRequestPolicy.OriginRequestPolicyConfig.Name=='MCP-AllHeaders'].OriginRequestPolicy.Id" \
    --output text)
fi
echo "  ✅ Origin Request Policy ID: $ORIGIN_REQUEST_POLICY_ID"

# =============================================================================
# 4. 创建 Response Headers Policy
# =============================================================================
echo "📦 创建 Response Headers Policy: MCP-CORS..."

RESPONSE_HEADERS_POLICY=$(cat <<'EOF'
{
  "Name": "MCP-CORS-Headers",
  "Comment": "CORS and cache headers for MCP",
  "CorsConfig": {
    "AccessControlAllowOrigins": {
      "Quantity": 1,
      "Items": ["*"]
    },
    "AccessControlAllowHeaders": {
      "Quantity": 4,
      "Items": ["Accept", "Content-Type", "Mcp-Session-Id", "Authorization"]
    },
    "AccessControlAllowMethods": {
      "Quantity": 4,
      "Items": ["GET", "POST", "DELETE", "OPTIONS"]
    },
    "AccessControlAllowCredentials": false,
    "AccessControlExposeHeaders": {
      "Quantity": 1,
      "Items": ["Mcp-Session-Id"]
    },
    "OriginOverride": true
  },
  "CustomHeadersConfig": {
    "Quantity": 0
  }
}
EOF
)

RESPONSE_HEADERS_POLICY_ID=$(aws cloudfront create-response-headers-policy \
  --response-headers-policy-config "$RESPONSE_HEADERS_POLICY" \
  --query 'ResponseHeadersPolicy.Id' \
  --output text 2>/dev/null || echo "")

if [ -z "$RESPONSE_HEADERS_POLICY_ID" ]; then
  RESPONSE_HEADERS_POLICY_ID=$(aws cloudfront list-response-headers-policies \
    --type custom \
    --query "ResponseHeadersPolicyList.Items[?ResponseHeadersPolicy.ResponseHeadersPolicyConfig.Name=='MCP-CORS-Headers'].ResponseHeadersPolicy.Id" \
    --output text)
fi
echo "  ✅ Response Headers Policy ID: $RESPONSE_HEADERS_POLICY_ID"

# =============================================================================
# 5. 输出 Distribution 配置 JSON
# =============================================================================
echo ""
echo "📋 生成 CloudFront Distribution 配置..."

cat > /tmp/cloudfront-distribution.json <<EOF
{
  "CallerReference": "mcp-skills-$(date +%s)",
  "Comment": "MCP Skills Server - SSE Optimized",
  "Enabled": true,
  "PriceClass": "PriceClass_100",
  "HttpVersion": "http2and3",
  "IsIPV6Enabled": true,
  "Origins": {
    "Quantity": 2,
    "Items": [
      {
        "Id": "ALB-Primary",
        "DomainName": "${ALB_DNS}",
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
      },
      {
        "Id": "ALB-Backup",
        "DomainName": "${ALB_DNS_BACKUP:-$ALB_DNS}",
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
      }
    ]
  },
  "OriginGroups": {
    "Quantity": 1,
    "Items": [
      {
        "Id": "ALB-FailoverGroup",
        "FailoverCriteria": {
          "StatusCodes": {
            "Quantity": 4,
            "Items": [500, 502, 503, 504]
          }
        },
        "Members": {
          "Quantity": 2,
          "Items": [
            {"OriginId": "ALB-Primary"},
            {"OriginId": "ALB-Backup"}
          ]
        }
      }
    ]
  },
  "DefaultCacheBehavior": {
    "TargetOriginId": "ALB-FailoverGroup",
    "ViewerProtocolPolicy": "redirect-to-https",
    "AllowedMethods": {
      "Quantity": 7,
      "Items": ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"],
      "CachedMethods": {
        "Quantity": 2,
        "Items": ["GET", "HEAD"]
      }
    },
    "CachePolicyId": "${SSE_CACHE_POLICY_ID}",
    "OriginRequestPolicyId": "${ORIGIN_REQUEST_POLICY_ID}",
    "ResponseHeadersPolicyId": "${RESPONSE_HEADERS_POLICY_ID}",
    "Compress": true
  },
  "CacheBehaviors": {
    "Quantity": 3,
    "Items": [
      {
        "PathPattern": "/mcp",
        "TargetOriginId": "ALB-FailoverGroup",
        "ViewerProtocolPolicy": "https-only",
        "AllowedMethods": {
          "Quantity": 7,
          "Items": ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"],
          "CachedMethods": {
            "Quantity": 2,
            "Items": ["GET", "HEAD"]
          }
        },
        "CachePolicyId": "${SSE_CACHE_POLICY_ID}",
        "OriginRequestPolicyId": "${ORIGIN_REQUEST_POLICY_ID}",
        "ResponseHeadersPolicyId": "${RESPONSE_HEADERS_POLICY_ID}",
        "Compress": false
      },
      {
        "PathPattern": "/health",
        "TargetOriginId": "ALB-FailoverGroup",
        "ViewerProtocolPolicy": "allow-all",
        "AllowedMethods": {
          "Quantity": 2,
          "Items": ["GET", "HEAD"],
          "CachedMethods": {
            "Quantity": 2,
            "Items": ["GET", "HEAD"]
          }
        },
        "CachePolicyId": "${SSE_CACHE_POLICY_ID}",
        "Compress": false
      },
      {
        "PathPattern": "/static/*",
        "TargetOriginId": "ALB-FailoverGroup",
        "ViewerProtocolPolicy": "redirect-to-https",
        "AllowedMethods": {
          "Quantity": 2,
          "Items": ["GET", "HEAD"],
          "CachedMethods": {
            "Quantity": 2,
            "Items": ["GET", "HEAD"]
          }
        },
        "CachePolicyId": "${STATIC_CACHE_POLICY_ID}",
        "Compress": true
      }
    ]
  }
}
EOF

echo "  ✅ 配置已保存到: /tmp/cloudfront-distribution.json"

# =============================================================================
# 6. 创建或更新 Distribution
# =============================================================================
echo ""
if [ -n "$DISTRIBUTION_ID" ]; then
  echo "🔄 更新现有 Distribution: $DISTRIBUTION_ID"
  echo "  ⚠️  更新需要先获取 ETag，请手动执行以下命令："
  echo ""
  echo "  # 获取当前配置和 ETag"
  echo "  aws cloudfront get-distribution-config --id $DISTRIBUTION_ID > /tmp/current-config.json"
  echo "  ETAG=\$(jq -r '.ETag' /tmp/current-config.json)"
  echo ""
  echo "  # 更新配置"
  echo "  aws cloudfront update-distribution --id $DISTRIBUTION_ID --if-match \$ETAG --distribution-config file:///tmp/cloudfront-distribution.json"
else
  echo "🚀 创建新的 CloudFront Distribution..."
  echo ""
  read -p "是否现在创建? (y/n): " confirm
  if [ "$confirm" = "y" ]; then
    RESULT=$(aws cloudfront create-distribution \
      --distribution-config file:///tmp/cloudfront-distribution.json \
      --output json)

    NEW_DIST_ID=$(echo "$RESULT" | jq -r '.Distribution.Id')
    NEW_DOMAIN=$(echo "$RESULT" | jq -r '.Distribution.DomainName')

    echo ""
    echo "  ✅ Distribution 创建成功!"
    echo "  📍 Distribution ID: $NEW_DIST_ID"
    echo "  🌐 Domain Name: $NEW_DOMAIN"
    echo ""
    echo "  ⚠️  部署需要几分钟，使用以下命令检查状态:"
    echo "  aws cloudfront get-distribution --id $NEW_DIST_ID --query 'Distribution.Status'"
  else
    echo ""
    echo "  手动创建命令:"
    echo "  aws cloudfront create-distribution --distribution-config file:///tmp/cloudfront-distribution.json"
  fi
fi

# =============================================================================
# 7. 输出配置摘要
# =============================================================================
echo ""
echo "=============================================="
echo "📊 配置摘要"
echo "=============================================="
echo ""
echo "Origin 设置:"
echo "  • OriginKeepaliveTimeout: 60 秒"
echo "  • OriginReadTimeout: 180 秒 (最大值)"
echo "  • ConnectionTimeout: 10 秒 (快速故障检测)"
echo "  • ConnectionAttempts: 3 次"
echo ""
echo "故障转移:"
echo "  • Origin Group: ALB-FailoverGroup"
echo "  • 触发条件: 500, 502, 503, 504"
echo "  • Primary: ${ALB_DNS}"
echo "  • Backup: ${ALB_DNS_BACKUP:-'(同 Primary)'}"
echo ""
echo "Cache Behaviors:"
echo "  • /mcp (SSE): 无缓存, HTTPS only"
echo "  • /health: 无缓存, 健康检查"
echo "  • /static/*: 长 TTL (1天-1年)"
echo "  • 默认: 无缓存"
echo ""
echo "Policy IDs (保存供后续使用):"
echo "  • SSE Cache Policy: $SSE_CACHE_POLICY_ID"
echo "  • Static Cache Policy: $STATIC_CACHE_POLICY_ID"
echo "  • Origin Request Policy: $ORIGIN_REQUEST_POLICY_ID"
echo "  • Response Headers Policy: $RESPONSE_HEADERS_POLICY_ID"
echo ""
