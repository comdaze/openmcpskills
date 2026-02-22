# Implementation Plan: AgentCore Code Interpreter 集成

## 概述

本实现计划将 AWS Bedrock AgentCore Code Interpreter 集成到 MCP Skills 平台，分为 4 个阶段：
1. 基础集成 - CodeInterpreterService 服务
2. Skill 集成 - 执行类型支持
3. 前端展示 - Admin Dashboard 扩展
4. Playground 美化 - 流式输出与渲染

## Tasks

- [ ] 1. 基础集成 - CodeInterpreterService
  - [ ] 1.1 创建 CodeInterpreterService 服务类
    - 创建 `backend/app/services/code_interpreter.py`
    - 实现 `NetworkMode`, `ExecutionStatus`, `ExecutionResult`, `UploadFile` 数据类
    - 实现 `CodeInterpreterService` 类基础结构
    - _Requirements: FR-1.1_

  - [ ] 1.2 实现 Code Interpreter 实例管理
    - 实现 `initialize()` 方法创建/获取 Code Interpreter 实例
    - 实现 `_find_existing_interpreter()` 查找已存在实例
    - 实现 `cleanup()` 资源清理方法
    - _Requirements: FR-1.1, FR-1.4_

  - [ ] 1.3 实现会话管理
    - 实现 `_start_session()` 启动执行会话
    - 实现 `_close_session()` 关闭会话
    - 实现会话池管理逻辑
    - _Requirements: FR-1.2, FR-1.4, FR-1.5_

  - [ ] 1.4 实现代码执行功能
    - 实现 `execute_code()` 方法
    - 实现 `_execute_in_session()` 会话内执行
    - 处理执行超时和错误
    - _Requirements: FR-1.3, FR-2.1, FR-2.3, NFR-3.1_

  - [ ] 1.5 实现文件上传功能
    - 实现 `_upload_file()` 方法
    - 支持最大 100MB 文件限制
    - _Requirements: FR-2.4_

  - [ ]* 1.6 编写 CodeInterpreterService 单元测试
    - 测试实例创建和管理
    - 测试会话生命周期
    - 测试错误处理
    - _Requirements: FR-1.1, FR-1.2, FR-1.3, FR-1.4_

  - [ ]* 1.7 编写属性测试 - 代码执行结果完整性
    - **Property 2: 代码执行结果完整性**
    - **Validates: Requirements FR-2.3, NFR-3.2**

- [ ] 2. Checkpoint - 基础集成验证
  - 确保所有测试通过，如有问题请询问用户

- [ ] 3. Skill 集成 - 执行类型支持
  - [ ] 3.1 扩展 Skill 数据模型
    - 在 `backend/app/models/skill.py` 添加 `SkillExecution` 模型
    - 扩展 `SkillManifest` 添加 `execution` 字段
    - _Requirements: FR-3.1_

  - [ ] 3.2 更新 SkillLoader 解析逻辑
    - 修改 `_parse_skill_md()` 解析 execution 字段
    - 处理默认值 (type=instruction)
    - _Requirements: FR-3.1, FR-3.5_

  - [ ]* 3.3 编写属性测试 - Skill 元数据解析
    - **Property 9: Skill 元数据解析正确性**
    - **Validates: Requirements FR-3.1**

  - [ ] 3.4 扩展 MCP Engine 执行决策
    - 修改 `_handle_tools_call()` 支持执行类型判断
    - 实现 `_execute_in_sandbox()` 方法
    - 实现 `_load_script_content()` 加载脚本
    - _Requirements: FR-3.2, FR-3.3, FR-3.4, FR-4.1_

  - [ ] 3.5 实现 Skill 脚本执行
    - 实现 `execute_skill_script()` 方法
    - 实现 `_build_execution_wrapper()` 构建执行代码
    - 支持参数注入和依赖安装
    - _Requirements: FR-4.2, FR-4.3_

  - [ ]* 3.6 编写属性测试 - 执行类型决策
    - **Property 1: 执行类型决策正确性**
    - **Validates: Requirements FR-3.2, FR-3.3, FR-3.4, FR-3.5**

  - [ ]* 3.7 编写属性测试 - 参数传递
    - **Property 4: 参数传递正确性**
    - **Validates: Requirements FR-4.3**

  - [ ] 3.8 更新服务注册
    - 在 `backend/app/services/__init__.py` 导出 CodeInterpreterService
    - 在 MCP Engine 初始化时注入 CodeInterpreterService
    - _Requirements: FR-1.1_

- [ ] 4. Checkpoint - Skill 集成验证
  - 确保所有测试通过，如有问题请询问用户

- [ ] 5. 前端展示 - Admin Dashboard 扩展
  - [ ] 5.1 更新 Skill 类型定义
    - 在 `frontend/src/types/` 添加 Skill 执行相关类型
    - 添加 `SkillExecution`, `ExecutionResult`, `OutputFile` 类型
    - _Requirements: FR-3.1_

  - [ ] 5.2 扩展 Skill 详情页
    - 修改 `frontend/src/pages/skill-detail.tsx`
    - 显示执行类型标签 (instruction / code_interpreter)
    - 显示运行时配置 (runtime, timeout, network)
    - _Requirements: FR-5.1_

  - [ ] 5.3 添加执行历史标签页
    - 在 Skill 详情页添加 "执行历史" Tab
    - 显示执行记录列表 (时间、状态、耗时)
    - 仅对 code_interpreter 类型显示
    - _Requirements: FR-5.2_

  - [ ]* 5.4 编写前端组件测试
    - 测试执行类型标签显示
    - 测试执行历史列表渲染
    - _Requirements: FR-5.1, FR-5.2_

- [ ] 6. Checkpoint - 前端展示验证
  - 确保所有测试通过，如有问题请询问用户

- [ ] 7. Playground 美化 - 流式输出与渲染
  - [ ] 7.1 安装前端依赖
    - 安装 `react-markdown`, `remark-gfm`, `react-syntax-highlighter`
    - 更新 `package.json`
    - _Requirements: FR-6.2, FR-6.3_

  - [ ] 7.2 创建 MessageRenderer 组件
    - 创建 `frontend/src/components/chat/message-renderer.tsx`
    - 集成 ReactMarkdown 渲染
    - 集成代码块语法高亮
    - 支持流式输出光标
    - _Requirements: FR-6.1, FR-6.2, FR-6.3_

  - [ ] 7.3 创建 ToolCallsDisplay 组件
    - 创建 `frontend/src/components/chat/tool-calls-display.tsx`
    - 显示 Tool 调用状态图标 (pending/running/success/error)
    - 支持展开/收起调用详情
    - _Requirements: FR-6.6_

  - [ ] 7.4 创建 ExecutionResultDisplay 组件
    - 创建 `frontend/src/components/chat/execution-result-display.tsx`
    - 显示 stdout/stderr 内容
    - 显示 exit_code 和执行时间
    - _Requirements: FR-6.7_

  - [ ] 7.5 创建 FilesDisplay 组件
    - 创建 `frontend/src/components/chat/files-display.tsx`
    - 显示文件图标、名称、大小
    - 提供下载链接
    - _Requirements: FR-6.8_

  - [ ] 7.6 创建 CopyButton 组件
    - 创建 `frontend/src/components/chat/copy-button.tsx`
    - 实现一键复制功能
    - 显示复制成功提示
    - _Requirements: FR-6.10_

  - [ ] 7.7 重构 Playground 页面
    - 修改 `frontend/src/pages/playground.tsx`
    - 集成新的消息渲染组件
    - 优化 WebSocket 消息处理
    - _Requirements: FR-6.1, FR-6.6, FR-6.7_

  - [ ]* 7.8 编写属性测试 - Markdown 渲染
    - **Property 8: Markdown 渲染正确性**
    - **Validates: Requirements FR-6.2, FR-6.3**

  - [ ]* 7.9 编写属性测试 - 流式消息
    - **Property 7: 流式消息顺序性**
    - **Validates: Requirements FR-6.1**

- [ ] 8. Checkpoint - Playground 验证
  - 确保所有测试通过，如有问题请询问用户

- [ ] 9. 集成与部署准备
  - [ ] 9.1 创建 IAM 角色配置
    - 创建 `deploy/iam/code-interpreter-role.yaml`
    - 配置最小权限策略
    - _Requirements: NFR-1.3_

  - [ ] 9.2 更新环境变量配置
    - 更新 `backend/.env.example`
    - 添加 AWS 区域、角色 ARN 等配置
    - _Requirements: FR-1.1_

  - [ ] 9.3 更新部署文档
    - 更新 `deploy/README.md`
    - 添加 AgentCore 配置说明
    - _Requirements: FR-1.1_

  - [ ]* 9.4 编写集成测试
    - 测试端到端执行流程
    - 测试 Playground 流式输出
    - _Requirements: FR-1.3, FR-6.1_

- [ ] 10. Final Checkpoint - 完整验证
  - 确保所有测试通过，如有问题请询问用户

## Notes

- 标记 `*` 的任务为可选测试任务，可跳过以加快 MVP 开发
- 每个任务都引用了具体的需求编号以便追溯
- Checkpoint 任务用于阶段性验证
- 属性测试验证普遍正确性属性
- 单元测试验证具体示例和边界情况
