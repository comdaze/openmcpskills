# 部署指南

## 快速部署

```bash
# 部署最新版本
./deploy/deploy-to-ecs.sh

# 部署指定标签
./deploy/deploy-to-ecs.sh v1.0.0
```

## 部署步骤说明

脚本会自动执行以下步骤：

1. **构建 Docker 镜像** - 从项目根目录构建
2. **登录 ECR** - 使用 AWS CLI 认证
3. **推送镜像** - 上传到 ECR 仓库
4. **更新 ECS 服务** - 强制重新部署

## 前置要求

- Docker 已安装并运行
- AWS CLI 已配置（`aws configure`）
- 有 ECR 和 ECS 的访问权限

## 验证部署

```bash
# 检查服务状态
aws ecs describe-services \
  --cluster open-mcp-skills \
  --services mcp-server-alb \
  --region us-east-1 \
  --query 'services[0].deployments'

# 测试协议版本
curl http://open-mcp-skills-alb-222909331.us-east-1.elb.amazonaws.com/info

# 应该返回: "protocol_version": "2025-11-25"
```

## 回滚

如果需要回滚到之前的版本：

```bash
# 查看任务定义历史
aws ecs list-task-definitions \
  --family-prefix open-mcp-skills \
  --region us-east-1

# 回滚到指定版本
aws ecs update-service \
  --cluster open-mcp-skills \
  --service mcp-server-alb \
  --task-definition open-mcp-skills:1 \
  --region us-east-1
```

## 故障排查

```bash
# 查看服务事件
aws ecs describe-services \
  --cluster open-mcp-skills \
  --services mcp-server-alb \
  --region us-east-1 \
  --query 'services[0].events[0:5]'

# 查看任务日志
aws logs tail /ecs/open-mcp-skills/mcp-server-alb \
  --follow \
  --region us-east-1
```

---

## CloudFront 配置 (SSE 优化)

### 创建新 Distribution

```bash
# 完整配置：创建 Cache Policy、Origin Request Policy、Distribution
./deploy/setup-cloudfront.sh
```

配置要点：
- **Origin 超时**: OriginKeepaliveTimeout=60s, OriginReadTimeout=180s
- **快速故障检测**: ConnectionTimeout=10s, ConnectionAttempts=3
- **SSE 端点**: 禁用缓存, 转发必要 Headers (Accept, Mcp-Session-Id)
- **静态资源**: 长 TTL 缓存 (1天-1年)

### 更新现有 Distribution Origin 参数

```bash
# 只更新 Origin 超时参数
./deploy/update-cloudfront-origin.sh <distribution-id>

# 示例
./deploy/update-cloudfront-origin.sh E1234567890ABC
```

### 添加 Origin Group (故障转移)

```bash
# 添加故障转移配置
./deploy/add-origin-group.sh <distribution-id> [backup-alb-dns]

# 示例: 使用同一 ALB (多 AZ)
./deploy/add-origin-group.sh E1234567890ABC

# 示例: 使用备用 ALB
./deploy/add-origin-group.sh E1234567890ABC my-backup-alb.us-east-1.elb.amazonaws.com
```

故障转移触发条件: 500, 502, 503, 504

### 手动配置关键参数

如果你已有 Distribution，以下是需要调整的关键参数：

```bash
# 1. 更新 Origin 超时 (通过 AWS Console 或 CLI)
#    Custom Origin Settings:
#    - Origin Keep-alive Timeout: 60 秒
#    - Origin Read Timeout: 180 秒
#    - Connection Timeout: 10 秒
#    - Connection Attempts: 3

# 2. 为 /mcp 路径创建 Cache Behavior
#    - Cache Policy: CachingDisabled
#    - Origin Request Policy: 转发 Accept, Mcp-Session-Id, Authorization
#    - Viewer Protocol Policy: HTTPS only

# 3. 检查部署状态
aws cloudfront get-distribution --id <distribution-id> --query 'Distribution.Status'
```

### CloudFront vs ALB 选择建议

| 场景 | 推荐 |
|-----|-----|
| 纯 SSE/Streaming API | ALB 直连 |
| 静态资源 + API 混合 | CloudFront (配置 Cache Behavior) |
| 全球用户分布 | CloudFront + 区域 ALB |
| 需要 WAF 防护 | CloudFront 或 ALB (都支持 WAF) |
