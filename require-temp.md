1. 项目愿景 (Project Vision)
构建一个云原生的、可动态扩展的 MCP 服务器，旨在提供 skills as a Service for AI 能力。平台允许管理员通过 Web 界面实时管理和发布“技能（Skills）”。这些 skills必须是按照claude skills的标准编写的，这个 MCP 服务器可以兼容 claude 发布的或者自定义标准的 claude skills。任何兼容 MCP 的客户端均可通过标准的 Streamable HTTP 连接，即时获得并执行这些云端技能。可以参考Composio Claude Skills MCP Server的实现方式。
2. 核心系统架构 (System Architecture)
通信协议：基于 Streamable HTTP 。这是核心要求，确保服务器与客户端之间的实时、双向（指令 POST，结果 Streaming）通信。
部署环境：云原生容器化部署（如 AWS ECS/Kubernetes）。
存储层：S3 或 EFS 存储技能脚本；aws dynamoDB 存储元数据。
执行环境：安全沙箱（如 Docker 容器或 Deno 运行时）执行用户定义的技能代码。
1. 功能模块详细说明
M1: Streamable HTTP MCP 执行引擎 (Streamable HTTP Engine)
这是项目的核心，必须支持 MCP 协议在 HTTP 流上的实现：

动态加载：
引擎能够在运行时动态加载、卸载技能，不依赖服务重启。
使用 Redis Pub/Sub 等机制确保在 ECS 集群多实例部署时，所有实例能同步最新的技能列表。
会话管理：管理客户端的会话状态，将指令准确路由回正确的客户端连接。
M2: 管理后台界面 (Admin Dashboard)
提供可视化的技能全生命周期管理：
在线 IDE：提供支持 Python/TypeScript 的 Monaco 在线编辑器，管理员可以直接编写和测试技能代码。
技能定义：通过表单或 YAML/JSON 编辑器定义技能的 manifest（名称、描述、JSON Schema 参数）。
发布与同步：提供“发布”按钮，触发 M1 引擎的热加载机制。
监控与日志：查看实时的 MCP 请求日志、技能调用统计和错误信息。
可以上传标准的skills 包，自动检查是否满足标准
M3: 插件与沙箱管理 (Sandbox & Plugin Management)
依赖隔离：系统自动管理每个技能的运行时依赖（requirements.txt 或 package.json），并在独立的沙箱环境中执行。
秘密管理：与 AWS Secrets Manager 或 HashiCorp Vault 集成，确保 API Keys 只在执行沙箱内可用，不在前端暴露。
LLM 调用支持：内置一个  strands agent SDK，允许技能脚本内部（即云端）调用第三方 LLM（如 /Bedrock/OpenAI/Anthropic），实现“Agentic Tools”能力。
M4: 认证与安全 (Auth & Security)
Token 认证：客户端必须使用auth2端点，确保只有授权的 MCP Client 可以使用云端技能。 默认支持 aws cognito auth2 认证
速率限制：实施请求速率限制以防止滥用。
1. 技术栈选型建议 (Spec-Driven Recommendations)
后端：Python 3.11+ 必须使用支持 Streamable HTTP 和 MCP SDK 的框架（如 fastapi 或 MCP TS SDK）。
前端：Next.js + Vercel AI SDK（用于测试客户端连接）。
部署：Docker + AWS ECS Fargate。
1. 核心提示 (AI Prompt Guidance)
"请基于以上 Spec，重点实现 M1 模块。提供一个支持 Streamable HTTP 的 Python FastAPI 服务器框架代码，并能动态加载本地 ./skills 目录中的技能定义。"