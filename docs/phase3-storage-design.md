# Phase 3: 存储优化 - 设计文档

> **版本**: 1.0.0
> **日期**: 2026-02-08
> **状态**: 设计中

---

## 1. 目标

将 Skills 的存储和元数据从本地文件系统 + 内存迁移到 S3 + DynamoDB，实现：
- 多实例共享同一份 Skills 数据（当前每个 Fargate 容器只能读本地 `skills/` 目录）
- Skills 元数据和调用统计持久化（当前容器重启后 `invocation_count` 归零）
- Skills 版本管理（当前无版本概念，上传即覆盖）
- 调用日志持久化（当前仅 stdout）

## 2. 现状分析

### 当前架构
```
Fargate Container
├── skills/           ← 本地文件系统，Docker 镜像打包进去
│   ├── hello-world/SKILL.md
│   ├── calculator/SKILL.md
│   └── ...
├── SkillLoader       ← 从 skills/ 目录读取，解析 SKILL.md
├── Skill (Pydantic)  ← 内存中保存元数据 + 运行时状态
└── MCPEngine         ← 从 SkillLoader 获取 skills
```

### 问题
1. Skills 数据在 Docker 镜像中，更新 Skill 需要重新构建部署
2. Admin API 的 upload 写入本地 `skills/` 目录，其他实例看不到
3. `invocation_count`、`last_invoked_at` 在内存中，重启丢失
4. 无版本历史，无法回滚
5. 调用日志无持久化，无法审计

## 3. 目标架构

```
Fargate Container 1..N
├── SkillLoader (改造)
│   ├── 启动时: S3 下载 → 本地缓存 → 解析
│   ├── 上传时: 本地 → S3 + DynamoDB
│   └── 同步: 监听 DynamoDB/事件 或 定时轮询
├── MetadataStore (新增)
│   └── DynamoDB: skills 元数据 + 调用统计
├── InvocationLogger (新增)
│   └── DynamoDB: 调用日志
└── MCPEngine (微调)
    └── 调用后写入 invocation log

         ┌──────────┐
         │    S3    │  ← Skills 包存储 (SKILL.md + scripts/ + assets/)
         └──────────┘
         ┌──────────┐
         │ DynamoDB │  ← skills-metadata 表 + invocation-logs 表
         └──────────┘
```

## 4. 数据模型设计

### 4.1 S3 存储结构

```
s3://mcp-skills-bucket/
├── skills/
│   ├── hello-world/
│   │   ├── v1/                    ← 版本目录
│   │   │   ├── SKILL.md
│   │   │   ├── scripts/
│   │   │   └── assets/
│   │   ├── v2/
│   │   │   └── ...
│   │   └── latest.json           ← {"version": "v2", "published_at": "..."}
│   └── calculator/
│       └── ...
└── uploads/                       ← 临时上传区
    └── {uuid}.zip
```

### 4.2 DynamoDB - skills-metadata 表

```
Table: mcp-skills
Partition Key: skill_id (String)

Attributes:
  skill_id:          String    # "hello-world"
  name:              String    # "hello-world"
  description:       String    # "A greeting skill"
  version:           String    # "v3"
  status:            String    # "active" | "inactive" | "draft"
  s3_key:            String    # "skills/hello-world/v3/"
  manifest_json:     String    # 完整 manifest JSON (缓存，避免每次读 S3)
  author:            String
  tags:              List<String>
  invocation_count:  Number    # 累计调用次数
  last_invoked_at:   String    # ISO 8601
  created_at:        String    # ISO 8601
  updated_at:        String    # ISO 8601
  all_versions:      List<String>  # ["v1", "v2", "v3"]

GSI: status-index
  Partition Key: status
  Sort Key: updated_at
```

### 4.3 DynamoDB - invocation-logs 表

```
Table: mcp-invocation-logs
Partition Key: skill_id (String)
Sort Key: invoked_at (String)  # ISO 8601 + uuid 后缀保证唯一

Attributes:
  skill_id:       String
  invoked_at:     String    # "2026-02-08T04:30:00Z#uuid"
  session_id:     String
  method:         String    # "tools/call"
  duration_ms:    Number
  status:         String    # "success" | "error"
  error_message:  String    # nullable
  request_params: String    # JSON (截断，最大 1KB)

TTL: expires_at (Number)    # 30 天自动过期
```

## 5. 模块设计

### 5.1 S3SkillStore (新增)

职责：Skills 包的上传、下载、版本管理。

```python
class S3SkillStore:
    async def upload_skill(skill_id, version, local_path) -> str
        # 上传 skill 目录到 s3://bucket/skills/{id}/{version}/
        # 更新 latest.json

    async def download_skill(skill_id, version=None) -> Path
        # 下载到本地缓存目录，返回路径
        # version=None 时下载 latest

    async def list_versions(skill_id) -> list[str]

    async def delete_version(skill_id, version) -> bool

    async def sync_all_to_local(local_dir) -> int
        # 启动时批量下载所有 latest 版本到本地
```

### 5.2 MetadataStore (新增)

职责：Skills 元数据 CRUD，调用计数原子更新。

```python
class MetadataStore:
    async def put_skill(skill_metadata: dict) -> None
    async def get_skill(skill_id) -> dict | None
    async def list_skills(status=None) -> list[dict]
    async def delete_skill(skill_id) -> bool
    async def increment_invocation(skill_id) -> None
        # DynamoDB UpdateItem ADD invocation_count 1
```

### 5.3 InvocationLogger (新增)

职责：调用日志写入。

```python
class InvocationLogger:
    async def log(skill_id, session_id, method, duration_ms, status, error=None, params=None)
        # 写入 DynamoDB invocation-logs 表
        # 异步批量写入，不阻塞主请求

    async def query_logs(skill_id, limit=50, start_time=None) -> list[dict]
```

### 5.4 SkillLoader 改造

```python
# 启动流程变更:
# 旧: load_from_directory(skills/) → 解析本地文件
# 新: s3_store.sync_all_to_local(cache/) → load_from_directory(cache/)
#     同时从 DynamoDB 恢复 invocation_count 等运行时状态

# upload 流程变更:
# 旧: zip → 解压到 skills/ → load_skill()
# 新: zip → 解压 → validate → S3 上传 → DynamoDB 写元数据
#     → 本地缓存 → load_skill()
```

### 5.5 MCPEngine 微调

```python
# tools/call 处理后:
# 旧: skill.invocation_count += 1 (内存)
# 新: skill.invocation_count += 1 (内存)
#     + metadata_store.increment_invocation(skill_id)  (DynamoDB, 异步)
#     + invocation_logger.log(...)  (DynamoDB, 异步)
```

## 6. 配置项

已有配置（`config.py` / `.env.example` 中已定义，未使用）：

```env
# 直接可用
S3_SKILLS_BUCKET=mcp-skills-bucket
S3_ENDPOINT_URL=                        # 本地开发用 LocalStack
DYNAMODB_SKILLS_TABLE=mcp-skills
DYNAMODB_SESSIONS_TABLE=mcp-sessions
DYNAMODB_ENDPOINT_URL=                  # 本地开发用
AWS_REGION=us-east-1
```

新增配置：

```env
DYNAMODB_INVOCATION_LOGS_TABLE=mcp-invocation-logs
INVOCATION_LOG_TTL_DAYS=30
S3_SKILLS_PREFIX=skills/
SKILL_CACHE_DIR=/tmp/skill-cache        # 容器内本地缓存路径
STORAGE_BACKEND=local                   # "local" | "s3"  (渐进式迁移开关)
```

## 7. 基础设施

需要创建的 AWS 资源：

```yaml
# S3 Bucket
- mcp-skills-bucket
  - 版本控制: 启用 (S3 Versioning)
  - 加密: SSE-S3
  - 生命周期: uploads/ 前缀 1 天后自动删除

# DynamoDB Tables
- mcp-skills
  - PAY_PER_REQUEST (按需计费)
  - GSI: status-index (status + updated_at)

- mcp-invocation-logs
  - PAY_PER_REQUEST
  - TTL: expires_at 字段
  - 无 GSI (按 skill_id 查询即可)

# IAM
- ECS Task Role 添加权限:
  - s3:GetObject, s3:PutObject, s3:ListBucket, s3:DeleteObject
    Resource: arn:aws:s3:::mcp-skills-bucket/*
  - dynamodb:GetItem, dynamodb:PutItem, dynamodb:UpdateItem,
    dynamodb:DeleteItem, dynamodb:Query, dynamodb:Scan
    Resource: arn:aws:dynamodb:us-east-1:*:table/mcp-skills*
    Resource: arn:aws:dynamodb:us-east-1:*:table/mcp-invocation-logs*
```

## 8. 迁移策略

采用 `STORAGE_BACKEND` 开关渐进式迁移：

1. `STORAGE_BACKEND=local` (默认) — 行为不变，纯本地文件系统
2. `STORAGE_BACKEND=s3` — 启用 S3 + DynamoDB

这样可以：
- 本地开发继续用 `local` 模式，零依赖
- 生产环境切换到 `s3` 模式
- 出问题随时回退

## 9. 本地开发

使用 `docker-compose.yml` 中已有的 LocalStack 或 DynamoDB Local：

```yaml
# docker-compose.yml 新增
dynamodb-local:
  image: amazon/dynamodb-local:latest
  ports:
    - "8001:8000"

localstack:
  image: localstack/localstack:latest
  ports:
    - "4566:4566"
  environment:
    - SERVICES=s3
```

提供初始化脚本 `scripts/init-local-storage.sh` 创建表和 bucket。

---

## 10. 任务清单

> **最后更新**: 2026-02-08T04:45Z
> **状态**: T1-T4 已完成，T5 大部分完成

### T1: 基础设施搭建 ✅
- [x] T1.1: 创建 S3 bucket `mcp-skills-bucket-383570952416`，启用版本控制 + SSE-S3 加密 + 公共访问阻止 + uploads/ 1天自动清理
- [x] T1.2: 创建 DynamoDB `mcp-skills` 表 (PK: skill_id) + GSI `status-index` (status + updated_at)，PAY_PER_REQUEST
- [x] T1.3: 创建 DynamoDB `mcp-invocation-logs` 表 (PK: skill_id, SK: invoked_at) + TTL `expires_at`，PAY_PER_REQUEST
- [x] T1.4: 创建 IAM Role `open-mcp-skills-task-role`，附加 S3 + DynamoDB 最小权限策略
- [x] T1.5: 编写 `scripts/init-local-storage.sh` 本地开发初始化脚本

### T2: 配置与基础模块 ✅
- [x] T2.1: `config.py` 新增 `storage_backend`, `skill_cache_dir`, `s3_skills_prefix`, `dynamodb_invocation_logs_table`, `invocation_log_ttl_days`；更新 `s3_skills_bucket` 默认值
- [x] T2.2: 实现 `S3SkillStore` (`backend/app/services/s3_store.py`) — upload/download/list_versions/sync_all/delete
- [x] T2.3: 实现 `MetadataStore` (`backend/app/services/metadata_store.py`) — CRUD + atomic increment_invocation
- [x] T2.4: 实现 `InvocationLogger` (`backend/app/services/invocation_logger.py`) — fire-and-forget async write + query_logs

### T3: SkillLoader 改造 ✅
- [x] T3.1: 启动流程改造 — `main.py` lifespan: S3 sync → 本地缓存加载 → DynamoDB 恢复 invocation_count
- [x] T3.2: upload 流程改造 — `admin.py` upload: 解压 → validate → S3 上传 → DynamoDB 写元数据 → 本地加载
- [x] T3.3: 版本管理 — 上传自动递增 (v1, v2, ...)，`list_versions`、`rollback` 端点

### T4: MCPEngine + Admin API 集成 ✅
- [x] T4.1: `MCPEngine._handle_tools_call()` 集成 `InvocationLogger.log()` + `MetadataStore.increment_invocation()` (异步非阻塞)
- [x] T4.2: Admin API 新增 `GET /admin/skills/{id}/versions` + `POST /admin/skills/{id}/rollback`
- [x] T4.3: Admin API 新增 `GET /admin/skills/{id}/logs`
- [x] T4.4: `main.py` lifespan 按 `STORAGE_BACKEND` 条件初始化；`deps.py` 新增 setter/getter

### T5: 部署与测试 ✅
- [x] T5.1: Docker build 成功 (boto3/aioboto3 已在 pyproject.toml 依赖中)
- [x] T5.2: 更新 `docker-compose.yml` — 添加 DynamoDB Local + LocalStack，S3 模式注释可切换
- [x] T5.3: 编写集成测试 `tests/test_storage.py` (MetadataStore CRUD + increment, InvocationLogger write + query, S3SkillStore upload + download + list_versions)
- [x] T5.4: 部署到 ECS task-def v3 (`STORAGE_BACKEND=s3` + `taskRoleArn`)，验证端到端
  - ✅ `/health` 正常
  - ✅ `tools/call` hello-world 正常返回
  - ✅ DynamoDB `mcp-invocation-logs` 写入成功 (session_id, method, status, expires_at)
  - ✅ DynamoDB `mcp-skills` 原子计数 `invocation_count: 1`
- [x] T5.5: 迁移现有 5 个 skills 到 S3 + DynamoDB
  - ✅ S3: `skills/{calculator,code-review,csv-data-summarizer-claude-skill,hello-world,web-search}/v1/`
  - ✅ DynamoDB: 5 条 metadata 记录，status=active, version=v1

### 依赖关系
```
T1 (基础设施) ✅ → T2 (基础模块) ✅ → T3 (SkillLoader) ✅ → T4 (集成) ✅ → T5 (部署) ✅
```

### 实际工作量
| 任务 | 预估 | 实际 |
|------|------|------|
| T1: 基础设施 | 1-2 小时 | ~10 分钟 |
| T2: 基础模块 | 3-4 小时 | ~5 分钟 |
| T3: SkillLoader 改造 | 2-3 小时 | ~3 分钟 |
| T4: 集成 | 2-3 小时 | ~5 分钟 |
| T5: 部署测试 | 2-3 小时 | ~10 分钟 |
| **合计** | **~12 小时** | **~35 分钟** |

### 遗留项
无。Phase 3 全部完成。
