# Open MCP Skills - 产品需求文档 (PRD)

> **版本**: 1.0.0
> **最后更新**: 2026-01-20
> **状态**: 开发中

---

## 1. 项目愿景 (Project Vision)

构建一个**云原生、可动态扩展**的 MCP (Model Context Protocol) 服务器，提供 **Skills as a Service** 能力。

### 1.1 核心价值

- **标准化**: 完全兼容 [Claude Skills 标准](https://docs.anthropic.com/en/docs/claude-skills)，支持官方或自定义 Skills
- **云原生**: 容器化部署，支持弹性伸缩，多实例同步
- **实时管理**: 管理员通过 Web 界面实时管理、发布技能，无需重启服务
- **安全隔离**: 沙箱执行环境，密钥安全管理，认证授权

### 1.2 目标用户

| 角色 | 描述 | 主要功能 |
|------|------|----------|
| **平台管理员** | 管理 Skills 生命周期 | 上传、编辑、发布、监控 Skills |
| **MCP 客户端** | Claude Code、自定义 AI Agent | 通过 MCP 协议调用云端 Skills |
| **Skills 开发者** | 编写自定义 Skills | 使用标准格式开发、测试 Skills |

---

## 2. 系统架构 (System Architecture)

### 2.1 架构概览

```
┌─────────────────────────────────────────────────────────────────────┐
│                         MCP Clients                                  │
│              (Claude Code, AI Agents, Custom Apps)                   │
└─────────────────────────┬───────────────────────────────────────────┘
                          │ Streamable HTTP (MCP Protocol)
                          ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    Application Load Balancer                         │
│                         (AWS ALB / HTTPS)                            │
└─────────────────────────┬───────────────────────────────────────────┘
                          │
        ┌─────────────────┼─────────────────┐
        ▼                 ▼                 ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│  MCP Server  │  │  MCP Server  │  │  MCP Server  │
│  Instance 1  │  │  Instance 2  │  │  Instance N  │
│   (Fargate)  │  │   (Fargate)  │  │   (Fargate)  │
└──────┬───────┘  └──────┬───────┘  └──────┬───────┘
       │                 │                 │
       └────────────┬────┴────┬────────────┘
                    │         │
        ┌───────────▼───┐ ┌───▼───────────┐
        │     Redis     │ │   DynamoDB    │
        │   (Pub/Sub)   │ │  (Metadata)   │
        └───────────────┘ └───────────────┘
                    │
            ┌───────▼───────┐
            │      S3       │
            │ (Skills存储)  │
            └───────────────┘
```

### 2.2 技术栈

| 层级 | 技术选型 | 说明 |
|------|----------|------|
| **后端框架** | Python 3.11+ / FastAPI | 支持 async/await，MCP SDK 兼容 |
| **MCP 协议** | mcp-python SDK | 官方 Python SDK |
| **前端** | Next.js 14+ / React | Admin Dashboard |
| **代码编辑** | Monaco Editor | 在线 IDE |
| **容器化** | Docker / ECS Fargate | 无服务器容器 |
| **负载均衡** | AWS ALB | HTTPS 终止，健康检查 |
| **缓存/同步** | Redis 7 | Pub/Sub 多实例同步 |
| **元数据存储** | DynamoDB | Skills 元数据，会话状态 |
| **文件存储** | S3 | Skills 包存储 |
| **认证** | AWS Cognito | OAuth2 / JWT |
| **密钥管理** | AWS Secrets Manager | API Keys 安全存储 |
| **监控** | CloudWatch / Prometheus | 日志、指标、告警 |

### 2.3 通信协议

- **MCP over Streamable HTTP**: 核心协议，支持 JSON-RPC 2.0
- **Server-Sent Events (SSE)**: 服务端推送通知
- **WebSocket** (可选): 实时双向通信

---

## 3. 功能模块详细说明

### M1: MCP 执行引擎 (MCP Engine) ✅ 已实现

核心模块，实现 MCP 协议处理。

#### 3.1.1 功能清单

| 功能 | 状态 | 说明 |
|------|------|------|
| MCP 协议实现 | ✅ | 支持 initialize, tools/list, tools/call 等 |
| 动态加载 Skills | ✅ | 运行时加载/卸载，无需重启 |
| 热重载 | ✅ | 文件变更自动重载 (watchfiles) |
| 会话管理 | ✅ | 客户端会话状态跟踪 |
| 健康检查 | ✅ | /health, /ready 端点 |
| Admin API | ✅ | Skills CRUD 操作 |
| 多实例同步 | 🟡 | Redis Pub/Sub (代码已写，未集成); S3+DynamoDB 存储已实现 |

#### 3.1.2 API 端点

```yaml
# MCP 协议端点
POST /mcp              # MCP JSON-RPC 请求
GET  /mcp/sse          # Server-Sent Events
DELETE /mcp            # 关闭会话

# 健康检查
GET /health            # 存活检查
GET /ready             # 就绪检查
GET /info              # 服务器信息

# Admin API
GET    /admin/skills                    # 列出所有 Skills
GET    /admin/skills/{id}               # 获取 Skill 详情
GET    /admin/skills/{id}/instructions  # 获取 Skill 指令
POST   /admin/skills/reload-all         # 重载所有 Skills
POST   /admin/skills/{id}/reload        # 重载单个 Skill
DELETE /admin/skills/{id}               # 卸载 Skill
POST   /admin/skills/validate           # 验证 Skill 包
POST   /admin/skills/upload             # 上传 Skill 包
```

#### 3.1.3 MCP 协议支持

```yaml
支持的方法:
  - initialize          # 初始化握手
  - initialized         # 初始化完成通知
  - tools/list          # 列出可用工具
  - tools/call          # 调用工具
  - prompts/list        # 列出提示模板
  - prompts/get         # 获取提示内容
  - resources/list      # 列出资源
  - resources/read      # 读取资源
  - completion/complete # 自动完成
  - ping                # 保活

服务端能力:
  - tools: true
  - prompts: true
  - resources: true
```

---

### M2: 管理后台界面 (Admin Dashboard) 🔲 待开发

提供可视化的 Skills 全生命周期管理。

#### 3.2.1 功能清单

| 功能 | 优先级 | 说明 |
|------|--------|------|
| Skills 列表 | P0 | 查看所有 Skills，状态、调用统计 |
| Skill 详情 | P0 | 查看/编辑 Skill 配置 |
| 在线 IDE | P1 | Monaco 编辑器，编写 SKILL.md |
| 包上传 | P0 | 上传 .zip Skills 包 |
| 包验证 | P0 | 自动检查 Skills 标准合规性 |
| 发布管理 | P1 | 草稿 → 发布 → 下线 工作流 |
| 实时日志 | P1 | 查看 MCP 请求日志 |
| 调用统计 | P2 | 仪表盘，调用量、错误率 |
| 用户管理 | P2 | 管理员账户 CRUD |

#### 3.2.2 页面设计

```
/dashboard
├── /skills                 # Skills 列表
│   ├── /new               # 新建 Skill
│   ├── /{id}              # Skill 详情
│   │   ├── /edit          # 编辑 Skill
│   │   ├── /logs          # 调用日志
│   │   └── /stats         # 统计数据
│   └── /upload            # 上传 Skill 包
├── /logs                   # 全局日志
├── /analytics              # 数据分析
└── /settings               # 系统设置
    ├── /users             # 用户管理
    └── /secrets           # 密钥管理
```

#### 3.2.3 在线 IDE 规格

```yaml
编辑器: Monaco Editor
支持语言:
  - Markdown (SKILL.md)
  - Python (scripts/)
  - TypeScript (scripts/)
  - YAML (配置)
  - JSON (schema)

功能:
  - 语法高亮
  - 自动补全
  - 错误提示
  - 文件树导航
  - 实时预览
  - Git 集成 (可选)
```

---

### M3: 沙箱与插件管理 (Sandbox & Plugin) 🔲 待开发

安全隔离的 Skills 执行环境。

#### 3.3.1 功能清单

| 功能 | 优先级 | 说明 |
|------|--------|------|
| 依赖隔离 | P0 | 每个 Skill 独立的运行时环境 |
| 资源限制 | P0 | CPU、内存、执行时间限制 |
| 网络隔离 | P1 | 可配置的网络访问策略 |
| 密钥注入 | P0 | 安全注入 API Keys |
| LLM 调用 | P1 | 内置 LLM SDK 支持 |

#### 3.3.2 沙箱规格

```yaml
执行环境:
  类型: Docker 容器 / Deno 运行时
  基础镜像: python:3.11-slim / node:20-slim

资源限制:
  cpu: 0.5 vCPU (可配置)
  memory: 512MB (可配置)
  timeout: 30s (可配置)
  disk: 100MB 临时存储

网络策略:
  默认: 仅允许 HTTPS 出站
  可配置: 白名单域名
  禁止: 内网访问

依赖管理:
  Python: requirements.txt → pip install
  Node.js: package.json → npm install
  缓存: 依赖层缓存，加速冷启动
```

#### 3.3.3 密钥管理

```yaml
存储: AWS Secrets Manager
注入方式: 环境变量
访问控制:
  - 仅在沙箱内可用
  - 按 Skill 授权
  - 审计日志

支持的密钥类型:
  - API Keys (OpenAI, Anthropic, etc.)
  - Database 连接串
  - OAuth Tokens
  - 自定义密钥
```

#### 3.3.4 LLM SDK 支持

```yaml
内置 SDK: strands-agent-sdk (或自研)

支持的 LLM:
  - AWS Bedrock (Claude, Llama, etc.)
  - OpenAI (GPT-4, etc.)
  - Anthropic (Claude API)

功能:
  - 统一调用接口
  - Token 计费追踪
  - 错误重试
  - 流式响应
```

---

### M4: 认证与安全 (Auth & Security) 🔲 待开发

#### 3.4.1 功能清单

| 功能 | 优先级 | 说明 |
|------|--------|------|
| OAuth2 认证 | P0 | AWS Cognito 集成 |
| API Key 认证 | P0 | 简单 API Key 方式 |
| JWT 验证 | P0 | Token 验证 |
| 速率限制 | P0 | 请求频率控制 |
| 权限控制 | P1 | RBAC 角色权限 |
| 审计日志 | P1 | 操作审计 |

#### 3.4.2 认证流程

```
OAuth2 流程:
┌────────┐     ┌─────────┐     ┌──────────┐
│ Client │────▶│ Cognito │────▶│MCP Server│
└────────┘     └─────────┘     └──────────┘
    │               │               │
    │ 1. 登录请求   │               │
    │──────────────▶│               │
    │               │               │
    │ 2. JWT Token  │               │
    │◀──────────────│               │
    │               │               │
    │ 3. MCP 请求 + Token           │
    │──────────────────────────────▶│
    │               │               │
    │               │ 4. 验证 Token │
    │               │◀──────────────│
    │               │               │
    │ 5. 响应       │               │
    │◀──────────────────────────────│
```

#### 3.4.3 速率限制规格

```yaml
默认配置:
  requests_per_minute: 100
  requests_per_hour: 1000
  concurrent_requests: 10

按角色配置:
  free:
    rpm: 20
    rph: 200
  pro:
    rpm: 100
    rph: 2000
  enterprise:
    rpm: 1000
    rph: unlimited

限制响应:
  status: 429 Too Many Requests
  headers:
    - X-RateLimit-Limit
    - X-RateLimit-Remaining
    - X-RateLimit-Reset
```

---

## 4. 数据模型

### 4.1 Skill 模型

```yaml
Skill:
  id: string                    # 唯一标识 (skill name)
  manifest:
    name: string                # 技能名称
    description: string         # 描述
    license: string             # 许可证
    version: string             # 版本号
    author: string              # 作者
    tags: string[]              # 标签
    allowed_tools: string[]     # 允许的工具
    user_invocable: boolean     # 用户可调用
    model: string               # 指定模型
    context: string             # 上下文模式
  status: enum                  # DRAFT | ACTIVE | INACTIVE | ERROR
  source_path: string           # 源文件路径
  instructions: string          # Markdown 指令
  reference_files: string[]     # 参考文件
  script_files: string[]        # 脚本文件
  asset_files: string[]         # 资源文件
  created_at: datetime
  updated_at: datetime
  invocation_count: integer     # 调用次数
  last_invoked_at: datetime
  load_error: string            # 加载错误信息
```

### 4.2 Session 模型

```yaml
Session:
  id: string                    # UUID
  state: enum                   # INITIALIZING | ACTIVE | SUSPENDED | CLOSED
  client_name: string           # 客户端名称
  client_version: string        # 客户端版本
  protocol_version: string      # MCP 协议版本
  user_id: string               # 用户 ID
  auth_token: string            # 认证 Token
  scopes: string[]              # 权限范围
  client_capabilities: object   # 客户端能力
  server_capabilities: object   # 服务端能力
  created_at: datetime
  last_activity_at: datetime
  expires_at: datetime
  metadata: object              # 扩展元数据
```

### 4.3 InvocationLog 模型

```yaml
InvocationLog:
  id: string
  session_id: string
  skill_id: string
  method: string                # tools/call, prompts/get, etc.
  request_params: object
  response_result: object
  status: enum                  # SUCCESS | ERROR | TIMEOUT
  duration_ms: integer
  error_message: string
  created_at: datetime
  client_ip: string
  user_agent: string
```

---

## 5. Skills 标准规范

### 5.1 目录结构

```
skill-name/
├── SKILL.md              # 必需: 清单 + 指令
├── scripts/              # 可选: 执行脚本
│   ├── main.py
│   └── utils.py
├── references/           # 可选: 参考文档
│   └── api-docs.md
├── assets/               # 可选: 资源文件
│   └── template.json
├── requirements.txt      # 可选: Python 依赖
└── package.json          # 可选: Node.js 依赖
```

### 5.2 SKILL.md 格式

```markdown
---
name: skill-name                    # 必需: 小写字母和连字符
description: 技能描述               # 必需: 简短描述
license: Apache-2.0                 # 可选: 许可证
metadata:
  author: Author Name               # 可选
  version: "1.0.0"                  # 可选
  tags: [tag1, tag2]                # 可选
allowed-tools:                      # 可选: 允许使用的工具
  - Read
  - Write
  - Bash
user-invocable: true                # 可选: 是否用户可调用
model: claude-3-opus                # 可选: 指定模型
context: fork                       # 可选: fork 表示隔离上下文
---

# Skill 标题

## 使用场景

描述何时使用此 Skill...

## 使用方法

详细的使用指令...

## 示例

示例用法...
```

### 5.3 验证规则

```yaml
必需字段:
  - name: 非空，符合命名规范
  - description: 非空，最少 10 字符

命名规范:
  - 仅小写字母、数字、连字符
  - 以字母开头
  - 长度 3-50 字符
  - 正则: ^[a-z][a-z0-9-]{2,49}$

文件大小限制:
  - SKILL.md: 最大 100KB
  - 单个脚本: 最大 1MB
  - 整个包: 最大 10MB

安全检查:
  - 无恶意代码模式
  - 无硬编码密钥
  - 无危险系统调用
```

---

## 6. 部署架构

### 6.1 AWS 基础设施

```yaml
VPC:
  cidr: 10.0.0.0/16
  subnets:
    public:
      - 10.0.1.0/24 (us-east-1a)
      - 10.0.2.0/24 (us-east-1b)
    private:
      - 10.0.10.0/24 (us-east-1a)
      - 10.0.11.0/24 (us-east-1b)

ECS Cluster:
  name: open-mcp-skills
  capacity_providers:
    - FARGATE
    - FARGATE_SPOT

ECS Service:
  name: mcp-server
  task_definition: open-mcp-skills
  desired_count: 2 (可伸缩)
  launch_type: FARGATE
  cpu: 256
  memory: 512

ALB:
  name: open-mcp-skills-alb
  scheme: internet-facing
  listeners:
    - port: 443 (HTTPS)
    - port: 80 (重定向到 443)
  health_check:
    path: /health
    interval: 30s

Auto Scaling:
  min: 1
  max: 10
  target_cpu: 70%
  target_memory: 80%
```

### 6.2 CI/CD 流程

```yaml
触发条件:
  - push to main
  - pull request
  - manual trigger

Pipeline:
  1. 代码检出
  2. 单元测试
  3. 代码质量检查 (ruff, mypy)
  4. 构建 Docker 镜像
  5. 推送到 ECR
  6. 更新 ECS Task Definition
  7. 滚动部署
  8. 健康检查验证
  9. 通知 (Slack/Email)

环境:
  - dev: 自动部署
  - staging: 自动部署 + 手动批准
  - prod: 手动触发 + 多人批准
```

---

## 7. 监控与运维

### 7.1 指标 (Metrics)

```yaml
系统指标:
  - cpu_utilization
  - memory_utilization
  - disk_usage
  - network_io

应用指标:
  - mcp_requests_total
  - mcp_requests_duration_seconds
  - mcp_requests_errors_total
  - active_sessions
  - skills_loaded
  - skill_invocations_total
  - skill_invocations_errors_total

业务指标:
  - unique_users_daily
  - popular_skills_top10
  - error_rate_by_skill
```

### 7.2 告警规则

```yaml
Critical:
  - error_rate > 5% for 5min
  - response_time_p99 > 5s for 5min
  - service_unavailable for 1min

Warning:
  - error_rate > 1% for 10min
  - response_time_p95 > 2s for 10min
  - cpu_utilization > 80% for 10min
  - memory_utilization > 85% for 10min

Info:
  - new_skill_deployed
  - config_changed
  - scale_event
```

### 7.3 日志规范

```yaml
格式: JSON
字段:
  - timestamp: ISO 8601
  - level: DEBUG | INFO | WARNING | ERROR
  - logger: 模块名
  - message: 日志消息
  - trace_id: 请求追踪 ID
  - session_id: 会话 ID
  - skill_id: 技能 ID
  - duration_ms: 耗时
  - error: 错误详情

保留期:
  - CloudWatch: 30 天
  - S3 归档: 1 年
```

---

## 8. 开发路线图

### Phase 1: MVP ✅

- [x] MCP 协议引擎
- [x] 动态 Skills 加载
- [x] 文件热重载
- [x] 基础 Admin API
- [x] Docker 容器化
- [x] ECS Fargate 部署
- [x] ALB 负载均衡
- [x] MCP 多版本协议协商 (2025-11-25 / 2025-06-18 / 2025-03-26)
- [x] AgentCore Gateway 集成
- [x] CloudFront SSE 优化 + Origin Group failover
- [x] 自定义域名 (mcp.openmcpskills.click)

### Phase 2: 安全增强 🟡 部分完成

- [x] HTTPS 强制 (ALB 443 + ACM 证书)
- [ ] AWS Cognito 认证集成
- [ ] API Key 认证
- [ ] 速率限制
- [ ] Redis 多实例同步 (代码已写 redis_sync.py，未集成)

### Phase 3: 存储优化 ✅ (2026-02-08 完成)

- [x] S3 Skills 存储 (mcp-skills-bucket-383570952416，版本控制 + SSE 加密)
- [x] DynamoDB 元数据存储 (mcp-skills 表 + status-index GSI)
- [x] Skills 版本管理 (自动递增版本号，list_versions / rollback API)
- [x] 调用日志持久化 (mcp-invocation-logs 表，30天 TTL 自动过期)
- [x] 启动时从 S3 同步到本地缓存加载，无需重新构建镜像
- [x] ECS Task Role IAM 最小权限 (open-mcp-skills-task-role)
- [x] 现有 5 个 skills 迁移到 S3

### Phase 4: Admin Dashboard 🔲

- [ ] 前端框架搭建 (Next.js)
- [ ] Skills 列表/详情页面
- [ ] Skills 上传功能
- [ ] Monaco 在线编辑器
- [ ] 实时日志查看

### Phase 5: 沙箱执行 🔲

- [ ] 沙箱运行时设计
- [ ] 依赖隔离
- [ ] 资源限制
- [ ] 密钥注入
- [ ] LLM SDK 集成

### Phase 6: 企业功能 🔲

- [ ] 多租户支持
- [ ] 计费系统
- [ ] SLA 监控
- [ ] 高级分析

---

## 9. 附录

### 9.1 参考资料

- [MCP Specification](https://spec.modelcontextprotocol.io/)
- [Claude Skills Standard](https://docs.anthropic.com/en/docs/claude-skills)
- [Composio MCP Server](https://github.com/composio/composio)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)

### 9.2 术语表

| 术语 | 定义 |
|------|------|
| MCP | Model Context Protocol，模型上下文协议 |
| Skill | 可被 AI 调用的能力单元 |
| Tool | MCP 协议中的工具概念 |
| Prompt | MCP 协议中的提示模板 |
| Resource | MCP 协议中的资源 |
| Streamable HTTP | 支持流式响应的 HTTP 传输 |

### 9.3 变更记录

| 版本 | 日期 | 变更内容 |
|------|------|----------|
| 1.0.0 | 2026-01-20 | 初始版本，基于实现状态完善 |
| 1.1.0 | 2026-02-08 | Phase 3 存储优化完成 (S3 + DynamoDB + 版本管理 + 调用日志); Phase 1 补充 MCP 多版本协商、AgentCore Gateway、CloudFront; Phase 2 HTTPS 标记完成 |
