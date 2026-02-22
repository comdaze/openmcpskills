# Integration Test Instructions

## 目的

测试各组件之间的交互，确保端到端流程正常工作。

## 测试场景

### 场景 1: Skill 加载与执行类型解析

**描述**: 验证 SkillLoader 正确解析 execution 配置

**测试步骤**:
```bash
# 1. 创建测试 Skill
mkdir -p backend/skills/test-code-skill
cat > backend/skills/test-code-skill/SKILL.md << 'EOF'
---
name: test-code-skill
description: Test skill with code_interpreter
execution:
  type: code_interpreter
  runtime: python
  entrypoint: main.py
  timeout: 60
  network: sandbox
---
# Test Skill
This is a test skill.
EOF

# 2. 启动后端
cd backend
python -m app.main &

# 3. 验证 Skill 加载
curl http://localhost:8000/admin/skills | jq '.skills[] | select(.id=="test-code-skill")'
```

**预期结果**:
- Skill 正确加载
- execution.type = "code_interpreter"
- execution.timeout = 60

### 场景 2: MCP tools/call 执行类型决策

**描述**: 验证 MCP Engine 根据 execution.type 正确决策

**测试步骤**:
```bash
# 1. 调用 instruction 类型 Skill
curl -X POST http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {"name": "hello-world", "arguments": {}}
  }'

# 预期: 返回 instructions 内容，execution = null

# 2. 调用 code_interpreter 类型 Skill (需要启用 AgentCore)
# 预期: 返回 execution 结果
```

### 场景 3: 前端 Skill 详情页显示

**描述**: 验证前端正确显示执行配置

**测试步骤**:
1. 启动前端: `cd frontend && npm run dev`
2. 访问 http://localhost:5173/skills/test-code-skill
3. 验证显示:
   - 执行类型标签: "🚀 Code Interpreter"
   - Execution Configuration 卡片
   - Runtime: python
   - Timeout: 60s
   - Network: sandbox

### 场景 4: Playground 消息渲染

**描述**: 验证 Playground 正确渲染 Markdown 和代码

**测试步骤**:
1. 访问 http://localhost:5173/playground
2. 发送包含代码块的消息
3. 验证:
   - Markdown 正确渲染
   - 代码块有语法高亮
   - 复制按钮可用

## 环境设置

### 启动服务

```bash
# 终端 1: 后端
cd backend
python -m app.main

# 终端 2: 前端
cd frontend
npm run dev
```

### 清理

```bash
# 停止服务
pkill -f "python -m app.main"
# 删除测试 Skill
rm -rf backend/skills/test-code-skill
```
