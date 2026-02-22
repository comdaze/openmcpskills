# Build Instructions

## Prerequisites

### Backend
- **Python**: 3.11+
- **Poetry** 或 **pip**: 包管理
- **AWS CLI**: 配置 AWS 凭证 (可选，用于 AgentCore)

### Frontend
- **Node.js**: 18+
- **npm**: 9+

### 环境变量
```bash
# Backend (.env)
CODE_INTERPRETER_ENABLED=false  # 开发时可禁用
AWS_REGION=us-east-1
```

## Build Steps

### 1. 后端构建

```bash
cd backend

# 安装依赖
pip install -e .
# 或使用 poetry
poetry install

# 验证安装
python -c "from app.services.code_interpreter import CodeInterpreterService; print('OK')"
```

### 2. 前端构建

```bash
cd frontend

# 安装依赖 (包含新增的 react-syntax-highlighter, remark-gfm)
npm install

# 类型检查
npm run build
```

### 3. 验证构建成功

**后端验证**:
```bash
cd backend
python -c "
from app.models.skill import SkillExecution
from app.services.code_interpreter import CodeInterpreterService, ExecutionStatus
print('Backend imports OK')
"
```

**前端验证**:
```bash
cd frontend
# 构建成功会生成 dist/ 目录
ls dist/
```

## 构建产物

| 组件 | 产物位置 |
|------|----------|
| Backend | `backend/` (Python 包) |
| Frontend | `frontend/dist/` |

## 常见问题

### 后端: boto3 客户端错误
- **原因**: AWS 凭证未配置
- **解决**: 设置 `CODE_INTERPRETER_ENABLED=false` 或配置 AWS 凭证

### 前端: 类型错误
- **原因**: 缺少 @types/react-syntax-highlighter
- **解决**: `npm install @types/react-syntax-highlighter`
