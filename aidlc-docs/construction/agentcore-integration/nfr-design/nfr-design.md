# NFR Design - AgentCore Code Interpreter 集成

## 概述

本文档补充 NFR 设计模式，基于 requirements.md 中定义的 NFR-1 到 NFR-4。

---

## 1. 安全性设计 (NFR-1)

### 1.1 网络隔离模式

```python
# 默认使用 SANDBOX 模式，代码无法访问网络
class NetworkMode(str, Enum):
    SANDBOX = "SANDBOX"  # 默认 - 无网络访问
    PUBLIC = "PUBLIC"    # 需要显式配置
```

**设计决策**:
- 所有新会话默认使用 SANDBOX 模式
- PUBLIC 模式需要在 Skill 元数据中显式声明
- 运行时不允许动态切换网络模式

### 1.2 IAM 最小权限策略

```yaml
# deploy/iam/code-interpreter-role.yaml
AWSTemplateFormatVersion: '2010-09-09'
Description: IAM Role for AgentCore Code Interpreter

Resources:
  CodeInterpreterExecutionRole:
    Type: AWS::IAM::Role
    Properties:
      RoleName: mcp-skills-code-interpreter-role
      AssumeRolePolicyDocument:
        Version: '2012-10-17'
        Statement:
          - Effect: Allow
            Principal:
              Service: bedrock.amazonaws.com
            Action: sts:AssumeRole
      
      Policies:
        - PolicyName: CodeInterpreterMinimalPolicy
          PolicyDocument:
            Version: '2012-10-17'
            Statement:
              # 仅允许执行代码，不允许访问其他 AWS 资源
              - Effect: Allow
                Action:
                  - logs:CreateLogStream
                  - logs:PutLogEvents
                Resource: !Sub 'arn:aws:logs:${AWS::Region}:${AWS::AccountId}:log-group:/aws/bedrock/code-interpreter/*'
```

### 1.3 输入验证

```python
# 所有用户输入必须验证
def validate_skill_arguments(arguments: dict) -> dict:
    """验证并清理用户输入"""
    # 限制参数大小
    MAX_ARG_SIZE = 1024 * 1024  # 1MB
    
    serialized = json.dumps(arguments)
    if len(serialized) > MAX_ARG_SIZE:
        raise ValueError(f"Arguments too large: {len(serialized)} > {MAX_ARG_SIZE}")
    
    # 移除潜在危险字符
    return sanitize_arguments(arguments)
```

---

## 2. 性能设计 (NFR-2)

### 2.1 会话池管理

```python
class SessionPool:
    """会话池 - 复用会话以减少启动延迟"""
    
    def __init__(self, max_size: int = 5, idle_timeout: int = 300):
        self.max_size = max_size
        self.idle_timeout = idle_timeout
        self._pool: Dict[str, SessionInfo] = {}
        self._lock = asyncio.Lock()
    
    async def acquire(self, network_mode: NetworkMode) -> str:
        """获取或创建会话"""
        async with self._lock:
            # 查找可复用的空闲会话
            for session_id, info in self._pool.items():
                if info.network_mode == network_mode and info.is_idle:
                    info.mark_active()
                    return session_id
            
            # 创建新会话
            if len(self._pool) < self.max_size:
                session_id = await self._create_session(network_mode)
                self._pool[session_id] = SessionInfo(network_mode)
                return session_id
            
            # 池已满，等待或创建临时会话
            return await self._create_temporary_session(network_mode)
    
    async def release(self, session_id: str):
        """释放会话回池"""
        async with self._lock:
            if session_id in self._pool:
                self._pool[session_id].mark_idle()
```

### 2.2 性能指标

| 指标 | 目标 | 监控方式 |
|------|------|----------|
| 会话启动时间 | < 5s | CloudWatch Metrics |
| 代码执行延迟 | < 2s (简单脚本) | 应用日志 |
| 并发会话数 | 支持 10+ | 会话池监控 |

---

## 3. 可靠性设计 (NFR-3)

### 3.1 超时处理

```python
async def execute_with_timeout(
    self,
    code: str,
    timeout: int,
) -> ExecutionResult:
    """带超时的代码执行"""
    try:
        result = await asyncio.wait_for(
            self._execute(code),
            timeout=timeout
        )
        return result
    except asyncio.TimeoutError:
        # 强制终止会话
        await self._force_terminate_session()
        return ExecutionResult(
            status=ExecutionStatus.TIMEOUT,
            exit_code=-1,
            stdout="",
            stderr=f"Execution timed out after {timeout} seconds",
            duration_ms=timeout * 1000,
        )
```

### 3.2 错误恢复策略

| 错误类型 | 恢复策略 | 重试次数 |
|----------|----------|----------|
| 会话创建失败 | 指数退避重试 | 3 |
| 执行超时 | 终止会话，返回错误 | 0 |
| AWS 服务错误 | 重试后降级 | 2 |
| 网络错误 | 重试 | 3 |

### 3.3 会话清理

```python
async def cleanup_stale_sessions(self):
    """定期清理过期会话"""
    async with self._lock:
        now = time.time()
        stale_sessions = [
            sid for sid, info in self._pool.items()
            if now - info.last_active > self.idle_timeout
        ]
        
        for session_id in stale_sessions:
            await self._close_session(session_id)
            del self._pool[session_id]
```

---

## 4. 成本控制设计 (NFR-4)

### 4.1 会话生命周期管理

```python
# 配置参数
DEFAULT_IDLE_TIMEOUT = 300      # 5 分钟空闲超时
MAX_SESSION_DURATION = 3600     # 1 小时最大会话时长
MAX_EXECUTION_TIME = 900        # 15 分钟最大执行时间
```

### 4.2 成本监控

```python
# 记录执行成本指标
async def log_execution_metrics(
    self,
    skill_id: str,
    duration_ms: int,
    network_mode: str,
):
    """记录执行指标用于成本分析"""
    metrics = {
        "skill_id": skill_id,
        "duration_ms": duration_ms,
        "network_mode": network_mode,
        "timestamp": datetime.utcnow().isoformat(),
    }
    
    # 发送到 CloudWatch
    await self._cloudwatch.put_metric_data(
        Namespace="MCPSkills/CodeInterpreter",
        MetricData=[
            {
                "MetricName": "ExecutionDuration",
                "Value": duration_ms,
                "Unit": "Milliseconds",
                "Dimensions": [
                    {"Name": "SkillId", "Value": skill_id},
                ]
            }
        ]
    )
```

---

## 5. 前端性能设计

### 5.1 流式渲染优化

```typescript
// 使用 requestAnimationFrame 优化渲染
const useStreamingText = (text: string) => {
  const [displayText, setDisplayText] = useState('')
  const bufferRef = useRef('')
  
  useEffect(() => {
    bufferRef.current += text
    
    // 批量更新，避免频繁重渲染
    const frame = requestAnimationFrame(() => {
      setDisplayText(bufferRef.current)
    })
    
    return () => cancelAnimationFrame(frame)
  }, [text])
  
  return displayText
}
```

### 5.2 虚拟滚动

对于长消息列表，使用虚拟滚动优化性能：

```typescript
// 仅渲染可见区域的消息
import { useVirtualizer } from '@tanstack/react-virtual'

const MessageList = ({ messages }) => {
  const virtualizer = useVirtualizer({
    count: messages.length,
    getScrollElement: () => containerRef.current,
    estimateSize: () => 100,
  })
  
  return (
    <div ref={containerRef}>
      {virtualizer.getVirtualItems().map((virtualRow) => (
        <MessageItem key={virtualRow.key} message={messages[virtualRow.index]} />
      ))}
    </div>
  )
}
```

---

## 总结

| NFR 类别 | 设计模式 | 实现优先级 |
|----------|----------|------------|
| 安全性 | 网络隔离 + 最小权限 + 输入验证 | P0 |
| 性能 | 会话池 + 批量渲染 | P1 |
| 可靠性 | 超时处理 + 错误恢复 + 会话清理 | P0 |
| 成本控制 | 生命周期管理 + 监控告警 | P1 |
