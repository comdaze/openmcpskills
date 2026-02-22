# AgentCore Code Interpreter 集成 - 需求文档

## 意图分析

| 维度 | 分析结果 |
|------|----------|
| **用户请求** | 为 MCP Skills 平台集成 AWS Bedrock AgentCore Code Interpreter，让 Skills 中的脚本可以在托管沙箱中执行 |
| **请求类型** | 新功能 (New Feature) |
| **范围估计** | 多组件 (后端服务 + 前端展示) |
| **复杂度估计** | 中等 (AWS 服务集成) |
| **技术选型** | AWS Bedrock AgentCore Code Interpreter (托管沙箱) |

---

## 0. 核心概念：执行决策机制

### 0.1 执行类型定义

系统支持两种 Skill 执行类型，**由 Skill 元数据配置决定，而非 LLM 自动判断**：

| 执行类型 | 说明 | 是否调用沙箱 | 适用场景 |
|----------|------|--------------|----------|
| `instruction` | 纯指令型 Skill，只返回 prompt/instructions | ❌ 不调用 | 写作助手、知识问答、提示词模板 |
| `code_interpreter` | 代码执行型 Skill，需要运行脚本 | ✅ 调用 | 数据分析、文件生成 (pptx/xlsx)、图表绘制 |

### 0.2 执行决策流程

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    MCP Client (Quick Suite / Claude 等)                  │
│                                                                          │
│  用户: "帮我把这个 PDF 转成 PPT"                                          │
└─────────────────────────┬────────────────────────────────────────────────┘
                          │ MCP tools/call: pptx-generator
                          ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                       MCP Skills Server                                  │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │                        MCP Engine                                  │  │
│  │                                                                    │  │
│  │  1. 接收 tools/call 请求                                           │  │
│  │  2. 加载 Skill 元数据                                              │  │
│  │  3. 检查 execution.type 配置                                       │  │
│  │     ┌─────────────────────────────────────────────────────────┐   │  │
│  │     │  if execution.type == "code_interpreter":               │   │  │
│  │     │      → 调用 CodeInterpreterService 执行脚本 ✅           │   │  │
│  │     │      → 返回执行结果 + 生成的文件                         │   │  │
│  │     │  else:  # instruction (默认)                            │   │  │
│  │     │      → 直接返回 Skill 的 instructions ❌ 不调用沙箱      │   │  │
│  │     │      → 由 LLM 基于 instructions 生成回答                 │   │  │
│  │     └─────────────────────────────────────────────────────────┘   │  │
│  └───────────────────────────────────────────────────────────────────┘  │
└─────────────────────────┬────────────────────────────────────────────────┘
                          │ (仅当 type == "code_interpreter")
                          ▼
┌─────────────────────────────────────────────────────────────────────────┐
│              AWS Bedrock AgentCore Code Interpreter                      │
│                                                                          │
│  • 在隔离沙箱中执行 Python/JS 脚本                                        │
│  • 支持文件上传/下载                                                      │
│  • 返回 stdout, stderr, exit_code                                        │
└─────────────────────────────────────────────────────────────────────────┘
```

### 0.3 设计原则

| 原则 | 说明 |
|------|------|
| **配置驱动** | 执行方式由 Skill 元数据决定，行为可预测 |
| **成本优化** | 纯指令 Skill 不产生沙箱费用 |
| **性能优化** | 不需要执行的 Skill 响应更快 (无沙箱启动延迟) |
| **Skill 作者控制** | Skill 开发者自己决定是否需要代码执行 |

### 0.4 Skill 配置示例

```yaml
# 代码执行型 Skill (需要沙箱)
---
name: pptx-generator
description: 生成 PowerPoint 演示文稿
execution:
  type: code_interpreter    # ← 需要沙箱执行
  runtime: python
  entrypoint: scripts/generate_pptx.py
  timeout: 300
  network: sandbox
---

# 纯指令型 Skill (不需要沙箱)
---
name: writing-assistant
description: 写作助手
execution:
  type: instruction         # ← 不需要沙箱 (默认值)
---
```

---

## 1. 功能需求 (Functional Requirements)

### FR-1: Code Interpreter 集成

| ID | 需求 | 优先级 |
|----|------|--------|
| FR-1.1 | 系统能够创建和管理 AgentCore Code Interpreter 实例 | P0 |
| FR-1.2 | 系统能够启动 Code Interpreter 会话 | P0 |
| FR-1.3 | 系统能够在会话中执行代码并获取结果 | P0 |
| FR-1.4 | 系统能够关闭会话并释放资源 | P0 |
| FR-1.5 | 支持会话复用以提高性能 | P1 |

### FR-2: 代码执行能力

| ID | 需求 | 优先级 |
|----|------|--------|
| FR-2.1 | 支持执行 Python 代码 | P0 |
| FR-2.2 | 支持执行 JavaScript/TypeScript 代码 | P1 |
| FR-2.3 | 返回执行结果 (stdout, stderr, 返回值) | P0 |
| FR-2.4 | 支持上传文件到沙箱 (最大 100MB) | P1 |
| FR-2.5 | 支持从沙箱下载结果文件 | P1 |

### FR-3: Skill 执行类型支持

| ID | 需求 | 优先级 |
|----|------|--------|
| FR-3.1 | Skill 元数据支持 `execution.type` 字段 (`instruction` / `code_interpreter`) | P0 |
| FR-3.2 | MCP Engine 根据 `execution.type` 决定是否调用沙箱 | P0 |
| FR-3.3 | `instruction` 类型 Skill 直接返回 instructions，不调用沙箱 | P0 |
| FR-3.4 | `code_interpreter` 类型 Skill 调用 AgentCore 执行脚本 | P0 |
| FR-3.5 | 未配置 `execution.type` 时默认为 `instruction` | P0 |

### FR-4: Skill 脚本集成

| ID | 需求 | 优先级 |
|----|------|--------|
| FR-4.1 | Skill 包中的 scripts/ 目录可以在 Code Interpreter 中执行 | P0 |
| FR-4.2 | 支持通过 MCP tools/call 触发脚本执行 | P0 |
| FR-4.3 | 支持传递参数给脚本 | P0 |
| FR-4.4 | 支持脚本访问 Skill 的 references/ 和 assets/ 文件 | P1 |

### FR-5: 管理界面

| ID | 需求 | 优先级 |
|----|------|--------|
| FR-5.1 | Admin Dashboard 显示 Skill 的执行类型 (instruction / code_interpreter) | P1 |
| FR-5.2 | 显示执行历史和日志 (仅 code_interpreter 类型) | P1 |
| FR-5.3 | 支持手动触发执行测试 | P1 |

### FR-6: Playground 流式输出与渲染美化

| ID | 需求 | 优先级 |
|----|------|--------|
| FR-6.1 | Chat 消息支持流式输出 (Streaming)，实时显示 LLM 生成的文本 | P0 |
| FR-6.2 | 支持 Markdown 渲染 (标题、列表、粗体、斜体、链接等) | P0 |
| FR-6.3 | 支持代码块语法高亮 (Python, JavaScript, JSON, YAML 等) | P0 |
| FR-6.4 | 支持表格渲染 | P1 |
| FR-6.5 | 支持数学公式渲染 (LaTeX/KaTeX) | P2 |
| FR-6.6 | Tool 调用状态可视化 (调用中、成功、失败) | P0 |
| FR-6.7 | 代码执行结果展示 (stdout, stderr, exit_code) | P0 |
| FR-6.8 | 生成文件的下载链接和预览 | P1 |
| FR-6.9 | 打字机效果 (逐字显示) 可配置开关 | P2 |
| FR-6.10 | 消息复制功能 (一键复制代码块或整条消息) | P1 |

---

## 2. 非功能需求 (Non-Functional Requirements)

### NFR-1: 安全性

| ID | 需求 | 优先级 |
|----|------|--------|
| NFR-1.1 | 使用 AgentCore Sandbox 网络模式 (默认无网络) | P0 |
| NFR-1.2 | 可配置使用 Public 网络模式 (需要时) | P1 |
| NFR-1.3 | 配置最小权限 IAM 执行角色 | P0 |
| NFR-1.4 | 启用 CloudTrail 日志审计 | P1 |

### NFR-2: 性能

| ID | 需求 | 优先级 |
|----|------|--------|
| NFR-2.1 | 会话启动时间 < 5s | P1 |
| NFR-2.2 | 简单脚本执行延迟 < 2s | P1 |
| NFR-2.3 | 支持并发执行多个会话 | P1 |

### NFR-3: 可靠性

| ID | 需求 | 优先级 |
|----|------|--------|
| NFR-3.1 | 执行超时自动终止 (默认 15 分钟) | P0 |
| NFR-3.2 | 执行失败返回详细错误信息 | P0 |
| NFR-3.3 | 会话异常自动清理 | P0 |

### NFR-4: 成本控制

| ID | 需求 | 优先级 |
|----|------|--------|
| NFR-4.1 | 会话空闲超时自动关闭 | P0 |
| NFR-4.2 | 限制单次执行最大时长 | P0 |
| NFR-4.3 | 监控和告警执行成本 | P2 |

---

## 3. 技术设计

### 3.1 架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                      MCP Client (Claude等)                       │
└─────────────────────────┬───────────────────────────────────────┘
                          │ MCP Protocol
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Open MCP Skills Server                        │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │                    MCP Engine                                ││
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  ││
│  │  │ Skill Loader│  │Session Mgr  │  │ CodeInterpreter Svc │  ││
│  │  └─────────────┘  └─────────────┘  └──────────┬──────────┘  ││
│  └───────────────────────────────────────────────┼──────────────┘│
└──────────────────────────────────────────────────┼──────────────┘
                                                   │ AWS SDK
                                                   ▼
┌─────────────────────────────────────────────────────────────────┐
│              AWS Bedrock AgentCore Code Interpreter              │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │                    Sandbox Environment                       ││
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  ││
│  │  │ Python 3.11 │  │ Node.js 20  │  │ 预装常用库          │  ││
│  │  └─────────────┘  └─────────────┘  └─────────────────────┘  ││
│  └─────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 MCP Engine 执行决策逻辑

```python
# backend/app/services/mcp_engine.py

class MCPEngine:
    """MCP 协议引擎 - 处理 tools/call 请求"""
    
    def __init__(self):
        self.skill_loader = SkillLoader()
        self.code_interpreter = CodeInterpreterService()
    
    async def handle_tool_call(self, tool_name: str, arguments: dict) -> dict:
        """
        处理 MCP tools/call 请求
        根据 Skill 的 execution.type 配置决定执行方式
        """
        # 1. 加载 Skill 元数据
        skill = await self.skill_loader.get_skill(tool_name)
        
        # 2. 获取执行类型 (默认为 instruction)
        execution_type = skill.execution.get("type", "instruction")
        
        # 3. 根据执行类型决定处理方式
        if execution_type == "code_interpreter":
            # ✅ 需要沙箱执行 - 调用 AgentCore Code Interpreter
            result = await self._execute_in_sandbox(skill, arguments)
            return {
                "content": [{"type": "text", "text": result["stdout"]}],
                "execution": {
                    "status": result["status"],
                    "exit_code": result["exit_code"],
                    "duration_ms": result["duration_ms"]
                },
                "files": result.get("output_files", [])
            }
        
        else:  # instruction 类型 (默认)
            # ❌ 不需要沙箱 - 直接返回 Skill 的 instructions
            return {
                "content": [{"type": "text", "text": skill.instructions}],
                "execution": None  # 表示未执行代码
            }
    
    async def _execute_in_sandbox(self, skill, arguments: dict) -> dict:
        """在 AgentCore Code Interpreter 沙箱中执行脚本"""
        return await self.code_interpreter.execute_skill_script(
            skill_id=skill.id,
            script_path=skill.execution.get("entrypoint"),
            arguments=arguments,
            timeout=skill.execution.get("timeout", 300),
            network_mode=skill.execution.get("network", "sandbox")
        )
```

### 3.3 CodeInterpreterService 服务封装

```python
# backend/app/services/code_interpreter.py

import boto3
from typing import Optional

class CodeInterpreterService:
    """AgentCore Code Interpreter 服务封装"""
    
    def __init__(self, region: str = "us-east-1"):
        self.region = region
        self.control_client = boto3.client(
            'bedrock-agentcore-control',
            region_name=region
        )
        self.runtime_client = boto3.client(
            'bedrock-agentcore-runtime',
            region_name=region
        )
        self.interpreter_id: Optional[str] = None
    
    async def initialize(self, name: str = "mcp-skills-interpreter"):
        """初始化或获取 Code Interpreter"""
        # 检查是否已存在
        existing = await self._get_existing(name)
        if existing:
            self.interpreter_id = existing
            return
        
        # 创建新的 Code Interpreter
        response = self.control_client.create_code_interpreter(
            name=name,
            description="Code Interpreter for MCP Skills execution",
            networkConfiguration={"networkMode": "SANDBOX"},
            executionRoleArn=self._get_execution_role_arn()
        )
        self.interpreter_id = response["codeInterpreterId"]
    
    async def execute_code(
        self,
        code: str,
        language: str = "python",
        timeout: int = 300,
        files: list[dict] = None
    ) -> dict:
        """执行代码"""
        # 启动会话
        session = await self._start_session()
        
        try:
            # 上传文件 (如果有)
            if files:
                for file in files:
                    await self._upload_file(session, file)
            
            # 执行代码
            result = await self._execute(session, code, language, timeout)
            
            return {
                "status": "success" if result["exitCode"] == 0 else "error",
                "exit_code": result["exitCode"],
                "stdout": result.get("stdout", ""),
                "stderr": result.get("stderr", ""),
                "duration_ms": result.get("durationMs", 0),
            }
        finally:
            # 关闭会话
            await self._close_session(session)
    
    async def execute_skill_script(
        self,
        skill_id: str,
        script_path: str,
        arguments: dict,
        timeout: int = 300,
        network_mode: str = "sandbox"
    ) -> dict:
        """执行 Skill 脚本"""
        # 加载脚本内容
        script_content = await self._load_script(skill_id, script_path)
        
        # 构建执行代码
        code = self._build_execution_code(script_content, arguments)
        
        # 执行
        return await self.execute_code(code, timeout=timeout)
```

### 3.4 Skill 包格式扩展

```yaml
# SKILL.md 新增 execution 字段

# 示例 1: 代码执行型 Skill (pptx 生成)
---
name: pptx-generator
description: 根据内容生成 PowerPoint 演示文稿
execution:
  type: code_interpreter    # 需要沙箱执行
  runtime: python           # python | javascript
  entrypoint: scripts/generate_pptx.py
  timeout: 300              # 秒
  network: sandbox          # sandbox | public
dependencies:
  - python-pptx>=0.6.21
  - Pillow>=9.0.0
---

# 示例 2: 纯指令型 Skill (写作助手)
---
name: writing-assistant
description: 专业写作助手
execution:
  type: instruction         # 不需要沙箱 (默认值，可省略)
---

# 示例 3: 数据分析 Skill (需要网络访问)
---
name: stock-analyzer
description: 股票数据分析
execution:
  type: code_interpreter
  runtime: python
  entrypoint: scripts/analyze.py
  timeout: 600
  network: public           # 需要访问外部 API
---
```

### 3.5 execution 字段规范

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `type` | string | 否 | `instruction` | 执行类型: `instruction` 或 `code_interpreter` |
| `runtime` | string | 条件 | `python` | 运行时环境 (仅 code_interpreter 需要) |
| `entrypoint` | string | 条件 | - | 入口脚本路径 (仅 code_interpreter 需要) |
| `timeout` | int | 否 | 300 | 执行超时时间 (秒) |
| `network` | string | 否 | `sandbox` | 网络模式: `sandbox` (无网络) 或 `public` |
| `dependencies` | list | 否 | [] | Python/npm 依赖列表 |

### 3.6 MCP 协议扩展

```yaml
# tools/call 请求 (代码执行型 Skill)
{
  "method": "tools/call",
  "params": {
    "name": "pptx-generator",
    "arguments": {
      "content": "...",
      "template": "business"
    }
  }
}

# 响应 (代码执行型)
{
  "result": {
    "content": [{
      "type": "text",
      "text": "PPT 已生成，包含 10 页幻灯片"
    }],
    "execution": {
      "status": "success",
      "exit_code": 0,
      "stdout": "Generated presentation.pptx",
      "duration_ms": 2345
    },
    "files": [{
      "name": "presentation.pptx",
      "url": "https://s3.../output/presentation.pptx",
      "size": 1234567
    }]
  }
}

# 响应 (纯指令型 - execution 为 null)
{
  "result": {
    "content": [{
      "type": "text",
      "text": "这是写作助手的指导说明..."
    }],
    "execution": null
  }
}
```

### 3.7 Playground 流式输出与渲染设计

#### 3.7.1 技术选型

| 功能 | 技术方案 | 说明 |
|------|----------|------|
| Markdown 渲染 | `react-markdown` + `remark-gfm` | 支持 GFM (GitHub Flavored Markdown) |
| 代码高亮 | `react-syntax-highlighter` + `prism` | 支持 100+ 语言 |
| 数学公式 | `remark-math` + `rehype-katex` | LaTeX 语法支持 |
| 流式渲染 | WebSocket + React State | 已有基础实现 |

#### 3.7.2 消息渲染组件设计

```tsx
// frontend/src/components/chat/message-renderer.tsx

import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism'

interface MessageRendererProps {
  content: string
  isStreaming?: boolean
  toolCalls?: ToolCall[]
  execution?: ExecutionResult
  files?: OutputFile[]
}

export function MessageRenderer({ 
  content, 
  isStreaming, 
  toolCalls, 
  execution, 
  files 
}: MessageRendererProps) {
  return (
    <div className="message-content">
      {/* Markdown 渲染 */}
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          // 代码块高亮
          code({ node, inline, className, children, ...props }) {
            const match = /language-(\w+)/.exec(className || '')
            return !inline && match ? (
              <div className="relative group">
                <SyntaxHighlighter
                  style={oneDark}
                  language={match[1]}
                  PreTag="div"
                  {...props}
                >
                  {String(children).replace(/\n$/, '')}
                </SyntaxHighlighter>
                <CopyButton text={String(children)} />
              </div>
            ) : (
              <code className={className} {...props}>
                {children}
              </code>
            )
          },
          // 表格样式
          table({ children }) {
            return (
              <div className="overflow-x-auto">
                <table className="min-w-full border-collapse border">
                  {children}
                </table>
              </div>
            )
          }
        }}
      >
        {content}
      </ReactMarkdown>
      
      {/* 流式输出光标 */}
      {isStreaming && <span className="animate-pulse">▊</span>}
      
      {/* Tool 调用状态 */}
      {toolCalls && toolCalls.length > 0 && (
        <ToolCallsDisplay calls={toolCalls} />
      )}
      
      {/* 代码执行结果 */}
      {execution && (
        <ExecutionResultDisplay result={execution} />
      )}
      
      {/* 生成文件 */}
      {files && files.length > 0 && (
        <FilesDisplay files={files} />
      )}
    </div>
  )
}
```

#### 3.7.3 Tool 调用状态组件

```tsx
// frontend/src/components/chat/tool-calls-display.tsx

interface ToolCall {
  name: string
  input: any
  status: 'pending' | 'running' | 'success' | 'error'
  result?: string
  duration_ms?: number
}

export function ToolCallsDisplay({ calls }: { calls: ToolCall[] }) {
  return (
    <div className="mt-3 space-y-2 border-t pt-3">
      <div className="text-xs text-muted-foreground font-medium">
        Tool Calls
      </div>
      {calls.map((call, idx) => (
        <div 
          key={idx} 
          className="flex items-center gap-2 p-2 bg-slate-50 rounded text-sm"
        >
          {/* 状态图标 */}
          {call.status === 'running' && (
            <Loader2 className="h-4 w-4 animate-spin text-blue-500" />
          )}
          {call.status === 'success' && (
            <CheckCircle className="h-4 w-4 text-green-500" />
          )}
          {call.status === 'error' && (
            <XCircle className="h-4 w-4 text-red-500" />
          )}
          
          {/* Tool 名称 */}
          <span className="font-mono font-medium">{call.name}</span>
          
          {/* 执行时间 */}
          {call.duration_ms && (
            <span className="text-xs text-muted-foreground">
              {call.duration_ms}ms
            </span>
          )}
          
          {/* 展开/收起结果 */}
          <Collapsible>
            <CollapsibleTrigger>
              <ChevronDown className="h-4 w-4" />
            </CollapsibleTrigger>
            <CollapsibleContent>
              <pre className="mt-2 p-2 bg-slate-100 rounded text-xs overflow-x-auto">
                {JSON.stringify(call.input, null, 2)}
              </pre>
              {call.result && (
                <pre className="mt-1 p-2 bg-green-50 rounded text-xs overflow-x-auto">
                  {call.result}
                </pre>
              )}
            </CollapsibleContent>
          </Collapsible>
        </div>
      ))}
    </div>
  )
}
```

#### 3.7.4 代码执行结果组件

```tsx
// frontend/src/components/chat/execution-result-display.tsx

interface ExecutionResult {
  status: 'success' | 'error'
  exit_code: number
  stdout: string
  stderr: string
  duration_ms: number
}

export function ExecutionResultDisplay({ result }: { result: ExecutionResult }) {
  return (
    <div className="mt-3 border rounded-lg overflow-hidden">
      {/* 头部状态栏 */}
      <div className={`px-3 py-2 flex items-center justify-between ${
        result.status === 'success' ? 'bg-green-50' : 'bg-red-50'
      }`}>
        <div className="flex items-center gap-2">
          <Terminal className="h-4 w-4" />
          <span className="font-medium text-sm">Code Execution</span>
        </div>
        <div className="flex items-center gap-3 text-xs">
          <span>Exit: {result.exit_code}</span>
          <span>{result.duration_ms}ms</span>
        </div>
      </div>
      
      {/* stdout */}
      {result.stdout && (
        <div className="p-3 bg-slate-900 text-green-400 font-mono text-sm">
          <div className="text-xs text-slate-500 mb-1">stdout:</div>
          <pre className="whitespace-pre-wrap">{result.stdout}</pre>
        </div>
      )}
      
      {/* stderr */}
      {result.stderr && (
        <div className="p-3 bg-slate-900 text-red-400 font-mono text-sm">
          <div className="text-xs text-slate-500 mb-1">stderr:</div>
          <pre className="whitespace-pre-wrap">{result.stderr}</pre>
        </div>
      )}
    </div>
  )
}
```

#### 3.7.5 文件展示组件

```tsx
// frontend/src/components/chat/files-display.tsx

interface OutputFile {
  name: string
  url: string
  size: number
  type?: string
}

export function FilesDisplay({ files }: { files: OutputFile[] }) {
  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  }
  
  const getIcon = (name: string) => {
    if (name.endsWith('.pptx')) return <FilePresentation />
    if (name.endsWith('.xlsx')) return <FileSpreadsheet />
    if (name.endsWith('.pdf')) return <FileText />
    if (name.endsWith('.png') || name.endsWith('.jpg')) return <Image />
    return <File />
  }
  
  return (
    <div className="mt-3 space-y-2">
      <div className="text-xs text-muted-foreground font-medium">
        Generated Files
      </div>
      {files.map((file, idx) => (
        <a
          key={idx}
          href={file.url}
          download={file.name}
          className="flex items-center gap-3 p-3 border rounded-lg hover:bg-slate-50 transition-colors"
        >
          {getIcon(file.name)}
          <div className="flex-1">
            <div className="font-medium text-sm">{file.name}</div>
            <div className="text-xs text-muted-foreground">
              {formatSize(file.size)}
            </div>
          </div>
          <Download className="h-4 w-4 text-muted-foreground" />
        </a>
      ))}
    </div>
  )
}
```

---

## 4. 实现计划

### Phase 1: 基础集成 (1 周)
- [ ] 创建 CodeInterpreterService 服务类
- [ ] 实现 Code Interpreter 创建和管理
- [ ] 实现基础代码执行功能
- [ ] 添加 IAM 角色和权限配置

### Phase 2: Skill 集成 (1 周)
- [ ] 扩展 Skill 模型支持 execution 配置
- [ ] 修改 MCP Engine 支持代码执行
- [ ] 实现脚本文件上传和执行
- [ ] 添加执行结果返回

### Phase 3: 前端展示 (3-5 天)
- [ ] Skill 详情页显示执行类型
- [ ] 添加执行历史标签页
- [ ] 支持手动触发执行测试

### Phase 4: Playground 流式输出与渲染美化 (1 周)
- [ ] 集成 react-markdown 实现 Markdown 渲染
- [ ] 集成 react-syntax-highlighter 实现代码高亮
- [ ] 优化 WebSocket 流式输出的渲染性能
- [ ] 实现 Tool 调用状态可视化组件
- [ ] 实现代码执行结果展示组件
- [ ] 实现文件下载/预览组件
- [ ] 添加消息复制功能

---

## 5. 依赖和前置条件

| 依赖 | 说明 | 状态 |
|------|------|------|
| AWS Bedrock AgentCore | 需要在 AWS 账户中启用 | 待确认 |
| IAM 执行角色 | Code Interpreter 执行角色 | 待创建 |
| boto3 SDK | Python AWS SDK | 已安装 |
| 区域支持 | AgentCore 需要在支持的区域 | 待确认 |

---

## 6. 验收标准

### 6.1 执行决策验收

| 场景 | 预期结果 |
|------|----------|
| 调用 `execution.type = "instruction"` 的 Skill | 直接返回 instructions，**不调用** AgentCore |
| 调用 `execution.type = "code_interpreter"` 的 Skill | 调用 AgentCore 沙箱执行脚本 |
| 调用未配置 `execution` 字段的 Skill | 默认为 instruction 类型，不调用沙箱 |

### 6.2 代码执行验收

| 场景 | 预期结果 |
|------|----------|
| 上传包含 Python 脚本的 Skill | 系统识别为 code_interpreter 类型 |
| 通过 MCP 调用可执行 Skill | 脚本在 AgentCore 沙箱中执行，返回结果 |
| 脚本执行超时 | 会话被终止，返回超时错误 |
| 脚本尝试访问网络 (Sandbox 模式) | 被阻止，返回网络错误 |
| 并发调用多个 Skill | 各自独立执行，互不影响 |

### 6.3 管理界面验收

| 场景 | 预期结果 |
|------|----------|
| Admin Dashboard 查看 Skill 列表 | 显示每个 Skill 的执行类型标签 |
| 查看 code_interpreter 类型 Skill | 显示执行历史、日志、运行时配置 |
| 查看 instruction 类型 Skill | 不显示执行历史 (因为没有代码执行) |

### 6.4 Playground 流式输出与渲染验收

| 场景 | 预期结果 |
|------|----------|
| LLM 生成长文本 | 文本逐步显示，无明显卡顿 |
| 消息包含 Markdown 标题/列表 | 正确渲染为 HTML 格式 |
| 消息包含代码块 | 显示语法高亮，有复制按钮 |
| 消息包含表格 | 正确渲染为表格，支持横向滚动 |
| Tool 被调用 | 显示 Tool 名称、状态图标 (转圈/成功/失败) |
| 代码执行完成 | 显示 stdout/stderr、exit_code、执行时间 |
| 生成文件 | 显示文件名、大小、下载按钮 |
| 点击代码块复制按钮 | 代码复制到剪贴板，显示成功提示 |

---

## 7. 使用场景示例

### 场景: Quick Suite 用户生成 PPT

```
1. 用户在 Quick Suite 上传 PDF，说 "帮我把这个 PDF 转成 PPT"

2. Quick Suite Chat Agent 识别意图，调用 MCP Server:
   POST /mcp
   {
     "method": "tools/call",
     "params": {
       "name": "pptx-generator",
       "arguments": {"pdf_content": "..."}
     }
   }

3. MCP Skills Server 处理请求:
   - 加载 pptx-generator Skill
   - 检查 execution.type = "code_interpreter" ✅
   - 调用 CodeInterpreterService

4. AgentCore Code Interpreter 执行:
   - 在沙箱中运行 scripts/generate_pptx.py
   - 使用 python-pptx 库生成 PPT
   - 返回生成的文件

5. 结果返回给 Quick Suite:
   {
     "content": [{"type": "text", "text": "PPT 已生成"}],
     "execution": {"status": "success", "duration_ms": 2345},
     "files": [{"name": "presentation.pptx", "url": "..."}]
   }

6. 用户在 Quick Suite 下载 PPT 文件
```
