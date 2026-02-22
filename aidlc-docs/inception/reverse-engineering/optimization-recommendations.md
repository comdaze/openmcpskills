# Open MCP Skills 优化建议

基于 Composio 的设计理念，为您的项目提供以下优化建议：

---

## 🎯 建议 1: 实现 MCP Gateway 架构

### 问题
当前架构是单一 MCP 服务器，所有 Skills 在同一进程中运行，难以扩展。

### Composio 方案
MCP Gateway 作为统一入口，路由请求到不同的后端 MCP 服务器。

### 建议实现

```python
# backend/app/services/mcp_gateway.py

class MCPGateway:
    """MCP Gateway - 统一入口点，路由到多个后端 MCP 服务器"""
    
    def __init__(self):
        self.tool_registry: dict[str, ToolEndpoint] = {}
        self.auth_manager = AuthManager()
        self.rate_limiter = RateLimiter()
        self.tracer = OpenTelemetryTracer()
    
    async def route_request(self, request: MCPRequest) -> MCPResponse:
        # 1. 认证
        user = await self.auth_manager.authenticate(request)
        
        # 2. 速率限制
        await self.rate_limiter.check(user)
        
        # 3. 路由到对应的工具服务器
        tool_name = request.params.get("name")
        endpoint = self.tool_registry.get(tool_name)
        
        # 4. 追踪
        with self.tracer.span(f"tool_call:{tool_name}"):
            response = await endpoint.call(request)
        
        return response
```

### 架构图
```
┌─────────────────────────────────────────────────────────────┐
│                      MCP Gateway                             │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐           │
│  │  Auth   │ │  Rate   │ │ Router  │ │ Tracer  │           │
│  │ Manager │ │ Limiter │ │         │ │         │           │
│  └─────────┘ └─────────┘ └─────────┘ └─────────┘           │
└─────────────────────────┬───────────────────────────────────┘
                          │
        ┌─────────────────┼─────────────────┐
        ▼                 ▼                 ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│ Custom Skills│  │ GitHub Tools │  │ Slack Tools  │
│   (现有)     │  │   (新增)     │  │   (新增)     │
└──────────────┘  └──────────────┘  └──────────────┘
```

---

## 🎯 建议 2: 实现 Agent Auth 系统

### 问题
当前无认证机制，无法安全地暴露给外部用户。

### Composio 方案
- 托管认证：OAuth, API Keys, JWT
- 统一管理：单一仪表板管理所有认证
- 自动刷新：令牌自动刷新和轮换

### 建议实现

```python
# backend/app/services/auth_manager.py

from enum import Enum
from typing import Optional
import jwt
import hashlib

class AuthType(Enum):
    API_KEY = "api_key"
    JWT = "jwt"
    OAUTH = "oauth"

class AuthManager:
    """统一认证管理器"""
    
    def __init__(self, dynamodb_table: str = "mcp-auth"):
        self.table = dynamodb_table
    
    async def authenticate(self, request: Request) -> User:
        """认证请求"""
        # 1. 检查 API Key
        api_key = request.headers.get("X-API-Key")
        if api_key:
            return await self._auth_api_key(api_key)
        
        # 2. 检查 JWT
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header[7:]
            return await self._auth_jwt(token)
        
        raise AuthenticationError("No valid credentials provided")
    
    async def _auth_api_key(self, api_key: str) -> User:
        """API Key 认证"""
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        # 从 DynamoDB 查询
        user_data = await self._get_user_by_key_hash(key_hash)
        if not user_data:
            raise AuthenticationError("Invalid API key")
        return User(**user_data)
    
    async def create_api_key(self, user_id: str, name: str) -> str:
        """创建 API Key"""
        import secrets
        api_key = f"mcp_{secrets.token_urlsafe(32)}"
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        
        await self._store_api_key(user_id, name, key_hash)
        return api_key  # 只返回一次，之后无法恢复
```

### 数据模型
```yaml
# DynamoDB: mcp-auth 表
ApiKey:
  pk: "USER#{user_id}"
  sk: "APIKEY#{key_id}"
  key_hash: string      # SHA256 哈希
  name: string          # 密钥名称
  scopes: string[]      # 权限范围
  created_at: datetime
  last_used_at: datetime
  expires_at: datetime  # 可选过期时间
```

---

## 🎯 建议 3: 添加预构建工具集成

### 问题
当前只支持自定义 Skills，用户需要自己编写所有集成。

### Composio 方案
250+ 预构建工具，开箱即用。

### 建议实现

创建一个工具注册表，支持动态加载预构建工具：

```python
# backend/app/services/tool_registry.py

class ToolRegistry:
    """工具注册表 - 管理预构建和自定义工具"""
    
    BUILTIN_TOOLS = {
        "github": GitHubTool,
        "slack": SlackTool,
        "notion": NotionTool,
        "gmail": GmailTool,
    }
    
    def __init__(self):
        self.tools: dict[str, BaseTool] = {}
        self.custom_skills: dict[str, Skill] = {}
    
    async def register_builtin(self, tool_name: str, config: dict):
        """注册预构建工具"""
        tool_class = self.BUILTIN_TOOLS.get(tool_name)
        if not tool_class:
            raise ValueError(f"Unknown builtin tool: {tool_name}")
        
        tool = tool_class(config)
        await tool.initialize()
        self.tools[tool_name] = tool
    
    def get_all_tools(self) -> list[dict]:
        """获取所有可用工具 (预构建 + 自定义)"""
        tools = []
        
        # 预构建工具
        for name, tool in self.tools.items():
            tools.extend(tool.get_mcp_tools())
        
        # 自定义 Skills
        for skill in self.custom_skills.values():
            tools.append(skill_to_tool(skill))
        
        return tools
```

### 示例: GitHub 工具
```python
# backend/app/tools/github.py

class GitHubTool(BaseTool):
    """GitHub 工具集成"""
    
    ACTIONS = [
        "create_issue",
        "list_issues", 
        "create_pull_request",
        "list_repos",
        "star_repo",
        # ... 更多操作
    ]
    
    def __init__(self, config: dict):
        self.token = config.get("token")
        self.client = None
    
    async def initialize(self):
        from github import Github
        self.client = Github(self.token)
    
    def get_mcp_tools(self) -> list[dict]:
        """返回 MCP 工具定义"""
        return [
            {
                "name": f"github_{action}",
                "description": f"GitHub: {action.replace('_', ' ')}",
                "inputSchema": self._get_schema(action),
            }
            for action in self.ACTIONS
        ]
    
    async def execute(self, action: str, params: dict) -> dict:
        """执行 GitHub 操作"""
        handler = getattr(self, f"_do_{action}", None)
        if not handler:
            raise ValueError(f"Unknown action: {action}")
        return await handler(params)
```

---

## 🎯 建议 4: 增强可观测性

### 问题
当前只有基础调用日志，难以调试和优化。

### Composio 方案
原生追踪、日志、错误分析，支持 OpenTelemetry。

### 建议实现

```python
# backend/app/services/observability.py

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

class ObservabilityService:
    """可观测性服务"""
    
    def __init__(self):
        # 初始化 OpenTelemetry
        provider = TracerProvider()
        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter())
        )
        trace.set_tracer_provider(provider)
        self.tracer = trace.get_tracer(__name__)
    
    def trace_tool_call(self, tool_name: str):
        """追踪工具调用的装饰器"""
        def decorator(func):
            async def wrapper(*args, **kwargs):
                with self.tracer.start_as_current_span(
                    f"tool_call:{tool_name}",
                    attributes={
                        "tool.name": tool_name,
                        "tool.params": str(kwargs),
                    }
                ) as span:
                    try:
                        result = await func(*args, **kwargs)
                        span.set_attribute("tool.success", True)
                        return result
                    except Exception as e:
                        span.set_attribute("tool.success", False)
                        span.set_attribute("tool.error", str(e))
                        raise
            return wrapper
        return decorator
```

### 仪表板增强
```typescript
// frontend/src/pages/observability.tsx

interface TraceData {
  traceId: string;
  toolName: string;
  duration: number;
  status: 'success' | 'error';
  timestamp: Date;
  spans: Span[];
}

// 添加追踪视图到 Dashboard
export function ObservabilityPage() {
  const [traces, setTraces] = useState<TraceData[]>([]);
  
  return (
    <div>
      <h1>工具调用追踪</h1>
      <TraceTimeline traces={traces} />
      <ErrorAnalysis traces={traces.filter(t => t.status === 'error')} />
      <PerformanceMetrics traces={traces} />
    </div>
  );
}
```

---

## 🎯 建议 5: 实现 Tool Router (智能工具选择)

### 问题
当前工具调用是直接的，没有智能路由和优化。

### Composio 方案
Tool Router 动态加载工具，智能选择，30% 更少失败率。

### 建议实现

```python
# backend/app/services/tool_router.py

class ToolRouter:
    """智能工具路由器"""
    
    def __init__(self):
        self.tool_stats: dict[str, ToolStats] = {}
        self.fallback_tools: dict[str, list[str]] = {}
    
    async def route(self, tool_name: str, params: dict) -> dict:
        """智能路由工具调用"""
        # 1. 获取工具统计
        stats = self.tool_stats.get(tool_name, ToolStats())
        
        # 2. 如果失败率高，尝试备用工具
        if stats.failure_rate > 0.3:
            fallbacks = self.fallback_tools.get(tool_name, [])
            for fallback in fallbacks:
                try:
                    return await self._call_tool(fallback, params)
                except Exception:
                    continue
        
        # 3. 调用主工具
        try:
            result = await self._call_tool(tool_name, params)
            self._record_success(tool_name)
            return result
        except Exception as e:
            self._record_failure(tool_name, e)
            raise
    
    def _record_success(self, tool_name: str):
        """记录成功调用"""
        stats = self.tool_stats.setdefault(tool_name, ToolStats())
        stats.total_calls += 1
        stats.successful_calls += 1
        stats.update_failure_rate()
    
    def _record_failure(self, tool_name: str, error: Exception):
        """记录失败调用"""
        stats = self.tool_stats.setdefault(tool_name, ToolStats())
        stats.total_calls += 1
        stats.failed_calls += 1
        stats.last_error = str(error)
        stats.update_failure_rate()
```

---

## 🎯 建议 6: 多框架 SDK 支持

### 问题
当前只支持 MCP 协议，限制了使用场景。

### Composio 方案
支持 10+ Agent 框架：LangChain, OpenAI SDK, Claude SDK 等。

### 建议实现

创建 Python SDK：

```python
# sdk/python/open_mcp_skills/client.py

class OpenMCPSkillsClient:
    """Open MCP Skills Python SDK"""
    
    def __init__(self, api_key: str, base_url: str = "https://api.openmcpskills.click"):
        self.api_key = api_key
        self.base_url = base_url
        self.session = aiohttp.ClientSession()
    
    async def list_tools(self) -> list[Tool]:
        """列出所有可用工具"""
        response = await self._request("POST", "/mcp", {
            "jsonrpc": "2.0",
            "method": "tools/list",
            "id": 1,
        })
        return [Tool(**t) for t in response["result"]["tools"]]
    
    async def call_tool(self, name: str, arguments: dict) -> dict:
        """调用工具"""
        response = await self._request("POST", "/mcp", {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
            "id": 1,
        })
        return response["result"]
    
    # LangChain 集成
    def as_langchain_tools(self) -> list:
        """转换为 LangChain 工具"""
        from langchain.tools import StructuredTool
        
        tools = []
        for tool in self.list_tools_sync():
            tools.append(StructuredTool(
                name=tool.name,
                description=tool.description,
                func=lambda **kwargs: self.call_tool_sync(tool.name, kwargs),
            ))
        return tools
```

---

## 📊 实施优先级

| 优先级 | 建议 | 预估工时 | 影响 |
|--------|------|----------|------|
| P0 | API Key 认证 | 3-5 天 | 安全性 |
| P0 | 速率限制 | 2-3 天 | 稳定性 |
| P1 | MCP Gateway | 1-2 周 | 可扩展性 |
| P1 | 可观测性增强 | 1 周 | 可维护性 |
| P1 | 预构建工具 (GitHub) | 1 周 | 功能性 |
| P2 | OAuth 认证 | 2 周 | 企业功能 |
| P2 | Python SDK | 1 周 | 易用性 |
| P2 | Tool Router | 1 周 | 可靠性 |

---

## 下一步行动

1. **立即开始**: 实现 API Key 认证 + 速率限制
2. **短期目标**: 完成 MCP Gateway 架构重构
3. **中期目标**: 添加预构建工具和可观测性
4. **长期目标**: 多框架 SDK 和企业功能
