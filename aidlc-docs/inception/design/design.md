# AgentCore Code Interpreter 集成 - 设计文档

## 概述

本设计文档描述了如何将 AWS Bedrock AgentCore Code Interpreter 集成到 MCP Skills 平台中，使 Skills 能够在托管沙箱环境中执行代码脚本。

### 设计目标

1. **配置驱动执行**: 通过 Skill 元数据配置决定执行方式，而非 LLM 自动判断
2. **成本优化**: 纯指令型 Skill 不产生沙箱费用
3. **安全隔离**: 代码在 AWS 托管沙箱中执行，默认无网络访问
4. **流式体验**: Playground 支持流式输出和丰富的渲染效果

### 核心架构

```
┌─────────────────────────────────────────────────────────────────────────┐
│                      MCP Client (Claude / Quick Suite)                   │
└─────────────────────────┬───────────────────────────────────────────────┘
                          │ MCP Protocol (tools/call)
                          ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    MCP Skills Server (FastAPI)                           │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │                        MCP Engine                                  │  │
│  │  ┌─────────────────┐  ┌──────────────────┐  ┌──────────────────┐  │  │
│  │  │   SkillLoader   │  │  SessionManager  │  │ CodeInterpreter  │  │  │
│  │  │  (扩展 exec)    │  │                  │  │    Service       │  │  │
│  │  └─────────────────┘  └──────────────────┘  └────────┬─────────┘  │  │
│  └──────────────────────────────────────────────────────┼────────────┘  │
└─────────────────────────────────────────────────────────┼───────────────┘
                                                          │ AWS SDK (boto3)
                                                          ▼
┌─────────────────────────────────────────────────────────────────────────┐
│              AWS Bedrock AgentCore Code Interpreter                      │
│  ┌─────────────────────────────────────────────────────────────────────┐│
│  │                    Sandbox Environment                               ││
│  │  • Python 3.11 / Node.js 20                                         ││
│  │  • 预装常用库 (pandas, numpy, python-pptx 等)                        ││
│  │  • 网络隔离 (Sandbox) 或公网访问 (Public)                            ││
│  └─────────────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 组件与接口

### 1. CodeInterpreterService

负责与 AWS Bedrock AgentCore Code Interpreter 交互的核心服务。

```python
# backend/app/services/code_interpreter.py

from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from enum import Enum
import boto3
import asyncio
import logging

logger = logging.getLogger(__name__)


class NetworkMode(str, Enum):
    """沙箱网络模式"""
    SANDBOX = "SANDBOX"  # 无网络访问
    PUBLIC = "PUBLIC"    # 可访问公网


class ExecutionStatus(str, Enum):
    """执行状态"""
    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"


@dataclass
class ExecutionResult:
    """代码执行结果"""
    status: ExecutionStatus
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int
    output_files: List[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "exit_code": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "duration_ms": self.duration_ms,
            "output_files": self.output_files or []
        }


@dataclass
class UploadFile:
    """上传文件"""
    name: str
    content: bytes
    mime_type: str = "application/octet-stream"


class CodeInterpreterService:
    """AgentCore Code Interpreter 服务封装
    
    职责:
    - 管理 Code Interpreter 实例生命周期
    - 创建和管理执行会话
    - 执行代码并返回结果
    - 处理文件上传/下载
    """
    
    def __init__(
        self,
        region: str = "us-east-1",
        execution_role_arn: Optional[str] = None,
        default_timeout: int = 300,
        idle_timeout: int = 600,
    ):
        self.region = region
        self.execution_role_arn = execution_role_arn
        self.default_timeout = default_timeout
        self.idle_timeout = idle_timeout
        
        # AWS 客户端 (延迟初始化)
        self._control_client = None
        self._runtime_client = None
        
        # Code Interpreter 实例 ID
        self._interpreter_id: Optional[str] = None
        
        # 会话池 (用于会话复用)
        self._session_pool: Dict[str, str] = {}
        self._session_lock = asyncio.Lock()
    
    @property
    def control_client(self):
        """获取控制平面客户端"""
        if self._control_client is None:
            self._control_client = boto3.client(
                'bedrock-agentcore-control',
                region_name=self.region
            )
        return self._control_client
    
    @property
    def runtime_client(self):
        """获取运行时客户端"""
        if self._runtime_client is None:
            self._runtime_client = boto3.client(
                'bedrock-agentcore-runtime',
                region_name=self.region
            )
        return self._runtime_client
    
    async def initialize(self, name: str = "mcp-skills-interpreter") -> str:
        """初始化或获取 Code Interpreter 实例
        
        Returns:
            Code Interpreter ID
        """
        # 检查是否已存在同名实例
        existing_id = await self._find_existing_interpreter(name)
        if existing_id:
            self._interpreter_id = existing_id
            logger.info(f"Using existing Code Interpreter: {existing_id}")
            return existing_id
        
        # 创建新实例
        response = self.control_client.create_code_interpreter(
            name=name,
            description="Code Interpreter for MCP Skills execution",
            networkConfiguration={"networkMode": NetworkMode.SANDBOX.value},
            executionRoleArn=self.execution_role_arn,
        )
        
        self._interpreter_id = response["codeInterpreterId"]
        logger.info(f"Created new Code Interpreter: {self._interpreter_id}")
        return self._interpreter_id
    
    async def execute_code(
        self,
        code: str,
        language: str = "python",
        timeout: Optional[int] = None,
        files: Optional[List[UploadFile]] = None,
        network_mode: NetworkMode = NetworkMode.SANDBOX,
    ) -> ExecutionResult:
        """执行代码
        
        Args:
            code: 要执行的代码
            language: 编程语言 (python/javascript)
            timeout: 执行超时时间 (秒)
            files: 要上传的文件列表
            network_mode: 网络模式
            
        Returns:
            ExecutionResult 执行结果
        """
        if not self._interpreter_id:
            await self.initialize()
        
        timeout = timeout or self.default_timeout
        session_id = None
        
        try:
            # 启动会话
            session_id = await self._start_session(network_mode)
            
            # 上传文件 (如果有)
            if files:
                for file in files:
                    await self._upload_file(session_id, file)
            
            # 执行代码
            result = await self._execute_in_session(
                session_id, code, language, timeout
            )
            
            return result
            
        except Exception as e:
            logger.exception(f"Code execution failed: {e}")
            return ExecutionResult(
                status=ExecutionStatus.ERROR,
                exit_code=-1,
                stdout="",
                stderr=str(e),
                duration_ms=0,
            )
        finally:
            # 关闭会话
            if session_id:
                await self._close_session(session_id)
    
    async def execute_skill_script(
        self,
        skill_id: str,
        script_path: str,
        script_content: str,
        arguments: Dict[str, Any],
        timeout: int = 300,
        network_mode: str = "sandbox",
        dependencies: Optional[List[str]] = None,
    ) -> ExecutionResult:
        """执行 Skill 脚本
        
        Args:
            skill_id: Skill ID
            script_path: 脚本路径
            script_content: 脚本内容
            arguments: 传递给脚本的参数
            timeout: 执行超时
            network_mode: 网络模式
            dependencies: Python/npm 依赖列表
            
        Returns:
            ExecutionResult 执行结果
        """
        # 构建执行代码
        execution_code = self._build_execution_wrapper(
            script_content, arguments, dependencies
        )
        
        # 确定网络模式
        net_mode = (
            NetworkMode.PUBLIC if network_mode == "public" 
            else NetworkMode.SANDBOX
        )
        
        return await self.execute_code(
            code=execution_code,
            language="python",  # 目前主要支持 Python
            timeout=timeout,
            network_mode=net_mode,
        )
    
    def _build_execution_wrapper(
        self,
        script_content: str,
        arguments: Dict[str, Any],
        dependencies: Optional[List[str]] = None,
    ) -> str:
        """构建执行包装代码"""
        import json
        
        wrapper = []
        
        # 安装依赖 (如果有)
        if dependencies:
            deps_str = " ".join(dependencies)
            wrapper.append(f"import subprocess")
            wrapper.append(f"subprocess.run(['pip', 'install', '-q', {repr(deps_str)}])")
            wrapper.append("")
        
        # 注入参数
        wrapper.append("# Injected arguments")
        wrapper.append(f"SKILL_ARGUMENTS = {json.dumps(arguments)}")
        wrapper.append("")
        
        # 原始脚本
        wrapper.append("# Original script")
        wrapper.append(script_content)
        
        return "\n".join(wrapper)
    
    async def _find_existing_interpreter(self, name: str) -> Optional[str]:
        """查找已存在的 Code Interpreter"""
        try:
            response = self.control_client.list_code_interpreters()
            for interpreter in response.get("codeInterpreters", []):
                if interpreter.get("name") == name:
                    return interpreter.get("codeInterpreterId")
        except Exception as e:
            logger.warning(f"Failed to list interpreters: {e}")
        return None
    
    async def _start_session(self, network_mode: NetworkMode) -> str:
        """启动执行会话"""
        response = self.runtime_client.start_code_interpreter_session(
            codeInterpreterId=self._interpreter_id,
            sessionConfiguration={
                "networkMode": network_mode.value,
                "idleTimeoutSeconds": self.idle_timeout,
            }
        )
        return response["sessionId"]
    
    async def _execute_in_session(
        self,
        session_id: str,
        code: str,
        language: str,
        timeout: int,
    ) -> ExecutionResult:
        """在会话中执行代码"""
        import time
        start_time = time.monotonic()
        
        response = self.runtime_client.invoke_code_interpreter(
            codeInterpreterId=self._interpreter_id,
            sessionId=session_id,
            code=code,
            executionTimeout=timeout,
        )
        
        duration_ms = int((time.monotonic() - start_time) * 1000)
        
        exit_code = response.get("exitCode", -1)
        status = (
            ExecutionStatus.SUCCESS if exit_code == 0 
            else ExecutionStatus.ERROR
        )
        
        return ExecutionResult(
            status=status,
            exit_code=exit_code,
            stdout=response.get("stdout", ""),
            stderr=response.get("stderr", ""),
            duration_ms=duration_ms,
            output_files=response.get("outputFiles", []),
        )
    
    async def _upload_file(self, session_id: str, file: UploadFile) -> None:
        """上传文件到会话"""
        self.runtime_client.upload_file_to_session(
            codeInterpreterId=self._interpreter_id,
            sessionId=session_id,
            fileName=file.name,
            fileContent=file.content,
            contentType=file.mime_type,
        )
    
    async def _close_session(self, session_id: str) -> None:
        """关闭会话"""
        try:
            self.runtime_client.stop_code_interpreter_session(
                codeInterpreterId=self._interpreter_id,
                sessionId=session_id,
            )
        except Exception as e:
            logger.warning(f"Failed to close session {session_id}: {e}")
    
    async def cleanup(self) -> None:
        """清理资源"""
        # 关闭所有活跃会话
        async with self._session_lock:
            for session_id in list(self._session_pool.values()):
                await self._close_session(session_id)
            self._session_pool.clear()
```

### 2. Skill 模型扩展

扩展现有 Skill 模型以支持 `execution` 配置。

```python
# backend/app/models/skill.py (扩展)

from typing import Optional, List
from pydantic import BaseModel, Field


class SkillExecution(BaseModel):
    """Skill 执行配置"""
    
    type: str = Field(
        default="instruction",
        description="执行类型: instruction (默认) 或 code_interpreter"
    )
    runtime: Optional[str] = Field(
        default="python",
        description="运行时环境: python 或 javascript"
    )
    entrypoint: Optional[str] = Field(
        default=None,
        description="入口脚本路径 (相对于 scripts/ 目录)"
    )
    timeout: int = Field(
        default=300,
        description="执行超时时间 (秒)"
    )
    network: str = Field(
        default="sandbox",
        description="网络模式: sandbox (无网络) 或 public"
    )
    dependencies: List[str] = Field(
        default_factory=list,
        description="Python/npm 依赖列表"
    )


class SkillManifest(BaseModel):
    """扩展的 Skill Manifest"""
    
    # ... 现有字段 ...
    
    # 新增执行配置
    execution: SkillExecution = Field(
        default_factory=SkillExecution,
        description="执行配置"
    )
```

### 3. MCP Engine 扩展

修改 MCP Engine 以支持基于配置的执行决策。

```python
# backend/app/services/mcp_engine.py (扩展 _handle_tools_call)

async def _handle_tools_call(
    self,
    msg_id: Any,
    params: dict[str, Any],
    session_id: str | None,
) -> dict[str, Any]:
    """处理 tools/call 请求 - 支持代码执行"""
    
    tool_name = params.get("name")
    arguments = params.get("arguments", {})
    
    if not tool_name:
        return self._error_response(msg_id, -32602, "Missing tool name")
    
    # 获取 Skill
    skill = await self._skill_loader.get_skill(tool_name)
    if not skill:
        return self._error_response(msg_id, -32602, f"Skill not found: {tool_name}")
    
    if skill.status != SkillStatus.ACTIVE:
        return self._error_response(msg_id, -32602, f"Skill not active: {tool_name}")
    
    start = time.monotonic()
    
    # 获取执行类型
    execution_type = skill.manifest.execution.type
    
    if execution_type == "code_interpreter":
        # ✅ 代码执行型 - 调用 AgentCore
        result = await self._execute_in_sandbox(skill, arguments)
        
        duration_ms = int((time.monotonic() - start) * 1000)
        
        return self._success_response(msg_id, {
            "content": [{
                "type": "text",
                "text": result.stdout or "Execution completed",
            }],
            "execution": {
                "status": result.status.value,
                "exit_code": result.exit_code,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "duration_ms": result.duration_ms,
            },
            "files": result.output_files or [],
            "isError": result.status != ExecutionStatus.SUCCESS,
        })
    
    else:
        # ❌ 指令型 (默认) - 直接返回 instructions
        user_args = arguments.get("arguments", "")
        instruction_content = self._build_instruction_content(skill, user_args)
        
        duration_ms = int((time.monotonic() - start) * 1000)
        
        return self._success_response(msg_id, {
            "content": [{
                "type": "text",
                "text": instruction_content,
            }],
            "execution": None,  # 表示未执行代码
            "isError": False,
        })


async def _execute_in_sandbox(
    self,
    skill: Skill,
    arguments: dict[str, Any],
) -> ExecutionResult:
    """在沙箱中执行 Skill 脚本"""
    
    execution = skill.manifest.execution
    
    # 加载脚本内容
    script_content = await self._load_script_content(
        skill, execution.entrypoint
    )
    
    if not script_content:
        return ExecutionResult(
            status=ExecutionStatus.ERROR,
            exit_code=-1,
            stdout="",
            stderr=f"Script not found: {execution.entrypoint}",
            duration_ms=0,
        )
    
    # 执行脚本
    return await self._code_interpreter.execute_skill_script(
        skill_id=skill.id,
        script_path=execution.entrypoint,
        script_content=script_content,
        arguments=arguments,
        timeout=execution.timeout,
        network_mode=execution.network,
        dependencies=execution.dependencies,
    )


async def _load_script_content(
    self,
    skill: Skill,
    script_path: str,
) -> Optional[str]:
    """加载脚本内容"""
    if not script_path:
        return None
    
    # 在 skill 的 script_files 中查找
    for file_path in skill.script_files:
        if file_path.endswith(script_path):
            try:
                from pathlib import Path
                return Path(file_path).read_text(encoding="utf-8")
            except Exception as e:
                logger.error(f"Failed to read script {file_path}: {e}")
                return None
    
    return None
```

---

## 数据模型

### 1. Skill 执行配置 Schema

```yaml
# SKILL.md execution 字段规范

execution:
  type: string          # "instruction" | "code_interpreter", 默认 "instruction"
  runtime: string       # "python" | "javascript", 默认 "python"
  entrypoint: string    # 入口脚本路径, 如 "scripts/main.py"
  timeout: integer      # 执行超时 (秒), 默认 300
  network: string       # "sandbox" | "public", 默认 "sandbox"
  dependencies:         # 依赖列表
    - string
```

### 2. MCP 响应扩展

```typescript
// tools/call 响应格式

interface ToolCallResponse {
  content: Array<{
    type: "text"
    text: string
  }>
  
  // 代码执行结果 (仅 code_interpreter 类型)
  execution?: {
    status: "success" | "error" | "timeout"
    exit_code: number
    stdout: string
    stderr: string
    duration_ms: number
  } | null
  
  // 生成的文件 (仅 code_interpreter 类型)
  files?: Array<{
    name: string
    url: string
    size: number
    type?: string
  }>
  
  isError: boolean
}
```

### 3. 前端消息模型

```typescript
// frontend/src/types/chat.ts

interface Message {
  id: string
  role: "user" | "assistant"
  content: string
  timestamp: Date
  
  // Tool 调用信息
  toolCalls?: ToolCall[]
  
  // 代码执行结果
  execution?: ExecutionResult
  
  // 生成的文件
  files?: OutputFile[]
}

interface ToolCall {
  name: string
  input: Record<string, any>
  status: "pending" | "running" | "success" | "error"
  result?: string
  duration_ms?: number
}

interface ExecutionResult {
  status: "success" | "error" | "timeout"
  exit_code: number
  stdout: string
  stderr: string
  duration_ms: number
}

interface OutputFile {
  name: string
  url: string
  size: number
  type?: string
}
```

---

## 正确性属性

*正确性属性是系统应该在所有有效执行中保持为真的特性或行为——本质上是关于系统应该做什么的形式化陈述。属性作为人类可读规范和机器可验证正确性保证之间的桥梁。*



基于需求文档的验收标准，以下是系统需要满足的正确性属性：

### Property 1: 执行类型决策正确性

*For any* Skill 配置，MCP Engine 应根据 `execution.type` 字段正确决定执行方式：
- 当 `type == "code_interpreter"` 时，必须调用 AgentCore 沙箱执行脚本
- 当 `type == "instruction"` 或未配置时，必须直接返回 instructions，不调用沙箱

**Validates: Requirements FR-3.2, FR-3.3, FR-3.4, FR-3.5**

### Property 2: 代码执行结果完整性

*For any* 代码执行请求，返回的 ExecutionResult 必须包含所有必需字段：
- `status`: 执行状态 (success/error/timeout)
- `exit_code`: 退出码
- `stdout`: 标准输出
- `stderr`: 标准错误
- `duration_ms`: 执行时长

**Validates: Requirements FR-2.3, NFR-3.2**

### Property 3: 文件上传下载 Round-Trip

*For any* 上传到沙箱的文件，在沙箱中读取后内容应与原始内容一致；
*For any* 在沙箱中生成的文件，下载后内容应与沙箱中的内容一致。

**Validates: Requirements FR-2.4, FR-2.5**

### Property 4: 参数传递正确性

*For any* 传递给 Skill 脚本的参数，脚本内部应能通过 `SKILL_ARGUMENTS` 变量正确访问所有参数值。

**Validates: Requirements FR-4.3**

### Property 5: 默认网络模式安全性

*For any* 新创建的执行会话，如果未显式指定网络模式，应默认使用 SANDBOX 模式（无网络访问）。

**Validates: Requirements NFR-1.1**

### Property 6: 执行超时终止

*For any* 执行时间超过配置的 timeout 的代码，系统应自动终止执行并返回 timeout 状态。

**Validates: Requirements NFR-3.1**

### Property 7: 流式消息顺序性

*For any* 流式输出的消息序列，接收端拼接后的内容应与完整响应内容一致。

**Validates: Requirements FR-6.1**

### Property 8: Markdown 渲染正确性

*For any* 包含 Markdown 语法的消息内容，渲染后应正确转换为对应的 HTML 元素：
- 标题 (`#`) → `<h1>` - `<h6>`
- 代码块 (```) → `<pre><code>` 带语法高亮类名
- 列表 (`-`, `1.`) → `<ul>`, `<ol>`

**Validates: Requirements FR-6.2, FR-6.3**

### Property 9: Skill 元数据解析正确性

*For any* 包含 `execution` 字段的 SKILL.md 文件，解析后的 SkillManifest 应正确包含所有执行配置字段。

**Validates: Requirements FR-3.1**

---

## 错误处理

### 1. 代码执行错误

| 错误类型 | 处理方式 | 返回信息 |
|----------|----------|----------|
| 脚本不存在 | 返回错误响应 | `Script not found: {path}` |
| 执行超时 | 终止会话，返回超时状态 | `status: timeout` |
| 运行时错误 | 返回 stderr 内容 | `status: error, stderr: {error}` |
| AWS 服务错误 | 记录日志，返回通用错误 | `Code execution service unavailable` |

### 2. 会话管理错误

| 错误类型 | 处理方式 |
|----------|----------|
| 会话创建失败 | 重试 3 次，失败后返回错误 |
| 会话过期 | 自动创建新会话 |
| 会话关闭失败 | 记录警告日志，不影响主流程 |

### 3. 文件处理错误

| 错误类型 | 处理方式 |
|----------|----------|
| 文件过大 (>100MB) | 拒绝上传，返回错误 |
| 文件读取失败 | 返回错误，包含文件路径 |
| 输出文件不存在 | 返回空文件列表 |

---

## 测试策略

### 1. 单元测试

单元测试用于验证具体示例和边界情况：

| 测试目标 | 测试内容 |
|----------|----------|
| SkillExecution 模型 | 默认值、字段验证、序列化 |
| CodeInterpreterService | 客户端初始化、错误处理 |
| MCP Engine 扩展 | 执行类型判断、响应格式 |
| Skill 解析器 | execution 字段解析 |

### 2. 属性测试

属性测试用于验证普遍性质，每个属性测试至少运行 100 次迭代：

| 属性 | 测试库 | 生成器 |
|------|--------|--------|
| Property 1 | pytest + hypothesis | 随机 Skill 配置 |
| Property 2 | pytest + hypothesis | 随机代码片段 |
| Property 3 | pytest + hypothesis | 随机文件内容 |
| Property 4 | pytest + hypothesis | 随机参数字典 |
| Property 7 | jest + fast-check | 随机消息序列 |
| Property 8 | jest + fast-check | 随机 Markdown 内容 |

### 3. 集成测试

| 测试场景 | 验证内容 |
|----------|----------|
| 端到端执行流程 | MCP Client → Server → AgentCore → 返回结果 |
| Playground 流式输出 | WebSocket 连接、消息流、UI 更新 |
| 文件生成场景 | 上传 PDF → 执行脚本 → 下载 PPTX |

### 4. 测试配置

```python
# pytest.ini
[pytest]
markers =
    property: Property-based tests (run with --hypothesis-profile=ci)
    integration: Integration tests (require AWS credentials)
    slow: Slow tests (skip with -m "not slow")

# hypothesis profile
[hypothesis]
max_examples = 100
deadline = 5000  # 5 seconds per example
```

```typescript
// jest.config.js (前端)
module.exports = {
  testMatch: ['**/*.property.test.ts', '**/*.test.ts'],
  setupFilesAfterEnv: ['./jest.setup.ts'],
}
```

---

## 前端组件设计

### 1. MessageRenderer 组件

负责渲染聊天消息，支持 Markdown、代码高亮、Tool 调用状态等。

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

export function MessageRenderer(props: MessageRendererProps) {
  // 实现见需求文档 3.7.2
}
```

### 2. ToolCallsDisplay 组件

显示 Tool 调用状态和结果。

```tsx
// frontend/src/components/chat/tool-calls-display.tsx

interface ToolCallsDisplayProps {
  calls: ToolCall[]
}

export function ToolCallsDisplay({ calls }: ToolCallsDisplayProps) {
  // 实现见需求文档 3.7.3
}
```

### 3. ExecutionResultDisplay 组件

显示代码执行结果。

```tsx
// frontend/src/components/chat/execution-result-display.tsx

interface ExecutionResultDisplayProps {
  result: ExecutionResult
}

export function ExecutionResultDisplay({ result }: ExecutionResultDisplayProps) {
  // 实现见需求文档 3.7.4
}
```

### 4. FilesDisplay 组件

显示生成的文件列表和下载链接。

```tsx
// frontend/src/components/chat/files-display.tsx

interface FilesDisplayProps {
  files: OutputFile[]
}

export function FilesDisplay({ files }: FilesDisplayProps) {
  // 实现见需求文档 3.7.5
}
```

---

## 依赖项

### 后端依赖

```toml
# pyproject.toml 新增
[project.dependencies]
boto3 = ">=1.34.0"
```

### 前端依赖

```json
// package.json 新增
{
  "dependencies": {
    "react-markdown": "^9.0.0",
    "remark-gfm": "^4.0.0",
    "react-syntax-highlighter": "^15.5.0"
  }
}
```

### AWS 资源

| 资源 | 说明 |
|------|------|
| IAM Role | Code Interpreter 执行角色 |
| CloudTrail | 审计日志 (可选) |
| S3 Bucket | 输出文件存储 (可选) |

---

## 安全考虑

1. **网络隔离**: 默认使用 SANDBOX 模式，代码无法访问网络
2. **执行超时**: 强制执行超时限制，防止资源滥用
3. **最小权限**: IAM 角色仅授予必要权限
4. **输入验证**: 验证所有用户输入，防止注入攻击
5. **日志审计**: 记录所有代码执行操作

---

## 部署注意事项

1. **区域支持**: AgentCore Code Interpreter 目前仅在部分区域可用
2. **配额限制**: 注意 AWS 账户的并发会话限制
3. **成本监控**: 建议设置成本告警
4. **环境变量**: 需要配置 AWS 凭证和区域信息
