# Phase 2 代码生成计划 - Skill 集成 (执行类型支持)

## 概述

本计划扩展 Skill 模型和 MCP Engine，支持基于配置的执行类型决策。

## 单元上下文

- **单元名称**: Phase 2 - Skill 集成
- **依赖**: Phase 1 (CodeInterpreterService)
- **输出**: 修改 `skill.py`, `skill_loader.py`, `mcp_engine.py`

## 代码生成步骤

### Step 1: 扩展 Skill 数据模型
- [x] 在 `backend/app/models/skill.py` 添加 `SkillExecution` 模型
- [x] 扩展 `SkillManifest` 添加 `execution` 字段
- **需求追溯**: FR-3.1

### Step 2: 更新 SkillLoader 解析逻辑
- [x] 修改 `_parse_skill_md()` 解析 execution 字段
- [x] 处理默认值 (type=instruction)
- **需求追溯**: FR-3.1, FR-3.5

### Step 3: 扩展 MCP Engine 执行决策
- [x] 修改 `_handle_tools_call()` 支持执行类型判断
- [x] 实现 `_execute_in_sandbox()` 方法
- [x] 实现 `_load_script_content()` 加载脚本
- **需求追溯**: FR-3.2, FR-3.3, FR-3.4, FR-4.1

### Step 4: 注入 CodeInterpreterService 到 MCP Engine
- [x] 修改 `MCPEngine.__init__()` 接受 CodeInterpreterService
- [x] 更新 `backend/app/main.py` 初始化逻辑
- **需求追溯**: FR-1.1

### Step 5: 创建代码摘要文档
- [x] 创建 `aidlc-docs/construction/agentcore-integration/code/phase2-summary.md`
- [x] 记录修改的文件和关键实现

## 验收标准

- SkillExecution 模型正确定义
- SkillLoader 正确解析 execution 字段
- MCP Engine 根据 execution.type 正确决策
- CodeInterpreterService 正确注入

## 预计范围

- 修改文件: 4 个 (`skill.py`, `skill_loader.py`, `mcp_engine.py`, `main.py`)
- 文档文件: 1 个 (`phase2-summary.md`)
