# Open MCP Skills - Cognito S2S 认证配置

## 已创建的 AWS 资源

### Cognito User Pool
- **Pool ID**: `us-east-1_RYpe4hEx9`
- **Region**: `us-east-1`
- **Domain**: `openmcpskills-1772838404`

### App Client (S2S)
- **Client ID**: `2lcii6j6hq4cf9pahfni8v44fr`
- **Client Secret**: `1gavc7htl3kcehj1vth95ss4jb6oeivf0rdba7ligirm35m1afqa`

### Endpoints
- **Token Endpoint**: `https://openmcpskills-1772838404.auth.us-east-1.amazoncognito.com/oauth2/token`
- **Discovery URL**: `https://cognito-idp.us-east-1.amazonaws.com/us-east-1_RYpe4hEx9/.well-known/openid-configuration`

### Resource Server
- **Identifier**: `openmcpskills-api`
- **Scopes**: 
  - `openmcpskills-api/mcp` - MCP 协议访问
  - `openmcpskills-api/read` - 读取访问
  - `openmcpskills-api/admin` - 管理员访问

## Quick Suite MCP 集成配置

在 Quick Suite 中添加 MCP Integration 时使用以下配置：

```
MCP Server URL: https://mcp.openmcpskills.click/mcp
Authentication Type: OAuth 2.0 / Service Account
Token URL: https://openmcpskills-1772838404.auth.us-east-1.amazoncognito.com/oauth2/token
Client ID: 2lcii6j6hq4cf9pahfni8v44fr
Client Secret: 1gavc7htl3kcehj1vth95ss4jb6oeivf0rdba7ligirm35m1afqa
Scopes: openmcpskills-api/mcp openmcpskills-api/read
```

## 本地测试

```bash
# 获取 Access Token
TOKEN=$(curl -s -X POST "https://openmcpskills-1772838404.auth.us-east-1.amazoncognito.com/oauth2/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -u "2lcii6j6hq4cf9pahfni8v44fr:1gavc7htl3kcehj1vth95ss4jb6oeivf0rdba7ligirm35m1afqa" \
  -d "grant_type=client_credentials&scope=openmcpskills-api/mcp openmcpskills-api/read" | jq -r '.access_token')

# 测试 MCP 端点
curl -X POST http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```

## 环境变量配置

在 `.env` 或 ECS Task Definition 中添加：

```
COGNITO_ENABLED=true
COGNITO_USER_POOL_ID=us-east-1_RYpe4hEx9
COGNITO_REGION=us-east-1
COGNITO_ALLOWED_CLIENT_IDS=2lcii6j6hq4cf9pahfni8v44fr
```

## 下一步

1. 更新生产环境 ECS Task Definition 添加 Cognito 环境变量
2. 在 Quick Suite 中配置 MCP Integration
3. 测试端到端连接

---
生成时间: 2026-03-07
