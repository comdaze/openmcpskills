# Unit Test Execution

## 后端单元测试

### 1. 运行所有测试

```bash
cd backend
pytest tests/ -v
```

### 2. 运行特定模块测试

```bash
# 测试 CodeInterpreterService (需要 mock AWS)
pytest tests/test_code_interpreter.py -v

# 测试 Skill 模型
pytest tests/test_skill_model.py -v
```

### 3. 测试覆盖率

```bash
pytest tests/ --cov=app --cov-report=html
# 报告位置: htmlcov/index.html
```

## 前端单元测试

### 1. 运行测试

```bash
cd frontend
npm test
```

### 2. 测试组件

```bash
# 测试 chat 组件
npm test -- --testPathPattern="components/chat"
```

## 预期结果

### 后端
- **测试数量**: ~20+ 测试
- **覆盖率**: >80%
- **关键测试**:
  - SkillExecution 模型验证
  - CodeInterpreterService 初始化
  - MCP Engine 执行类型决策

### 前端
- **测试数量**: ~10+ 测试
- **关键测试**:
  - MessageRenderer 渲染
  - ToolCallsDisplay 状态显示
  - ExecutionResultDisplay 格式化

## 修复失败测试

1. 查看测试输出中的错误信息
2. 定位失败的测试文件和行号
3. 修复代码问题
4. 重新运行测试直到全部通过
