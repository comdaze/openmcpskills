# Phase 1 代码生成计划 - 基础集成 (CodeInterpreterService)

## 概述

本计划实现 AWS Bedrock AgentCore Code Interpreter 的基础集成，创建 `CodeInterpreterService` 服务类。

## 单元上下文

- **单元名称**: Phase 1 - 基础集成
- **依赖**: 无外部单元依赖
- **输出**: `backend/app/services/code_interpreter.py`

## 代码生成步骤

### Step 1: 创建 CodeInterpreterService 服务类
- [x] 创建 `backend/app/services/code_interpreter.py`
- [x] 实现数据类: `NetworkMode`, `ExecutionStatus`, `ExecutionResult`, `UploadFile`
- [x] 实现 `CodeInterpreterService` 类基础结构
- **需求追溯**: FR-1.1

### Step 2: 实现 Code Interpreter 实例管理
- [x] 实现 `initialize()` 方法创建/获取 Code Interpreter 实例
- [x] 实现 `_find_existing_interpreter()` 查找已存在实例
- [x] 实现 `cleanup()` 资源清理方法
- **需求追溯**: FR-1.1, FR-1.4

### Step 3: 实现会话管理
- [x] 实现 `_start_session()` 启动执行会话
- [x] 实现 `_close_session()` 关闭会话
- [x] 实现会话池管理逻辑
- **需求追溯**: FR-1.2, FR-1.4, FR-1.5

### Step 4: 实现代码执行功能
- [x] 实现 `execute_code()` 方法
- [x] 实现 `_execute_in_session()` 会话内执行
- [x] 处理执行超时和错误
- **需求追溯**: FR-1.3, FR-2.1, FR-2.3, NFR-3.1

### Step 5: 实现文件上传功能
- [x] 实现 `_upload_file()` 方法
- [x] 支持最大 100MB 文件限制
- **需求追溯**: FR-2.4

### Step 6: 实现 Skill 脚本执行
- [x] 实现 `execute_skill_script()` 方法
- [x] 实现 `_build_execution_wrapper()` 构建执行代码
- [x] 支持参数注入和依赖安装
- **需求追溯**: FR-4.2, FR-4.3

### Step 7: 更新配置文件
- [x] 在 `backend/app/core/config.py` 添加 AgentCore 配置项
- [x] 添加 `code_interpreter_name`, `code_interpreter_role_arn` 等配置
- **需求追溯**: FR-1.1

### Step 8: 更新服务注册
- [x] 在 `backend/app/services/__init__.py` 导出 CodeInterpreterService
- **需求追溯**: FR-1.1

### Step 9: 更新环境变量示例
- [x] 更新 `backend/.env.example` 添加 AgentCore 配置
- **需求追溯**: FR-1.1

### Step 10: 创建代码摘要文档
- [x] 创建 `aidlc-docs/construction/agentcore-integration/code/phase1-summary.md`
- [x] 记录生成的文件和关键实现

## 验收标准

- CodeInterpreterService 类完整实现
- 所有方法符合设计文档规范
- 配置项正确添加
- 服务正确导出

## 预计范围

- 新建文件: 1 个 (`code_interpreter.py`)
- 修改文件: 3 个 (`config.py`, `__init__.py`, `.env.example`)
- 文档文件: 1 个 (`phase1-summary.md`)
