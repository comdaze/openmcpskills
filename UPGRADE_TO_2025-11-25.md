# MCP Protocol Upgrade: 2024-11-05 → 2025-11-25

## 升级内容

已将 MCP 服务器从旧版 HTTP+SSE 传输协议升级到新的 Streamable HTTP 协议。

## 主要变更

### 1. 协议版本
- **旧版**: `2024-11-05`
- **新版**: `2025-11-25`

### 2. HTTP 头名称
- **旧版**: `mcp-session-id` (小写)
- **新版**: `Mcp-Session-Id` (驼峰式)

### 3. 兼容性
- ✅ **Claude Code**: 支持（使用 2025-11-25 协议）
- ✅ **Kiro CLI**: 支持（使用新的 Streamable HTTP）
- ✅ **向后兼容**: 服务器仍支持旧客户端

## 修改的文件

1. `backend/app/services/mcp_engine.py` - 协议版本更新
2. `backend/app/models/session.py` - 默认协议版本
3. `backend/app/api/mcp.py` - HTTP 头名称更新
4. `backend/app/main.py` - CORS 配置更新
5. `backend/app/api/health.py` - 健康检查端点
6. `backend/tests/test_mcp.py` - 测试用例更新

## 部署步骤

### 1. 测试
```bash
cd backend
pytest tests/test_mcp.py -v
```

### 2. 重新构建
```bash
docker-compose build
```

### 3. 部署
```bash
docker-compose up -d
```

### 4. 验证
```bash
# 测试健康检查
curl http://localhost:8000/info

# 应该返回: "protocol_version": "2025-11-25"
```

## 测试连接

### Kiro CLI
```bash
# 在 mcp.json 中配置
{
  "mcpServers": {
    "open-mcp-skills": {
      "type": "http",
      "url": "http://open-mcp-skills-alb-222909331.us-east-1.elb.amazonaws.com/mcp",
      "headers": {
        "Content-Type": "application/json"
      }
    }
  }
}
```

### Claude Code
保持现有配置不变，应该继续正常工作。

## 回滚方案

如果需要回滚到旧版本：

```bash
git revert HEAD
docker-compose build
docker-compose up -d
```

## 参考文档

- [MCP Specification 2025-11-25](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports)
- [Streamable HTTP Transport](https://modelcontextprotocol.io/specification/2025-03-26/basic/transports#streamable-http)
