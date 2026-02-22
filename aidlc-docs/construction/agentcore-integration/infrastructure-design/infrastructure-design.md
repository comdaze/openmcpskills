# Infrastructure Design - AgentCore Code Interpreter 集成

## 概述

本文档定义 AgentCore Code Interpreter 集成所需的 AWS 基础设施配置。

---

## 1. 架构图

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           AWS Cloud                                      │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │                        VPC (existing)                              │  │
│  │  ┌─────────────────────────────────────────────────────────────┐  │  │
│  │  │                    ECS Fargate Cluster                       │  │  │
│  │  │  ┌─────────────────────────────────────────────────────────┐│  │  │
│  │  │  │              MCP Skills Server                          ││  │  │
│  │  │  │  • FastAPI Application                                  ││  │  │
│  │  │  │  • CodeInterpreterService                               ││  │  │
│  │  │  │  • boto3 SDK                                            ││  │  │
│  │  │  └──────────────────────┬──────────────────────────────────┘│  │  │
│  │  └─────────────────────────┼───────────────────────────────────┘  │  │
│  └────────────────────────────┼──────────────────────────────────────┘  │
│                               │                                          │
│                               │ AWS SDK (HTTPS)                          │
│                               ▼                                          │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │              AWS Bedrock AgentCore                                 │  │
│  │  ┌─────────────────────────────────────────────────────────────┐  │  │
│  │  │              Code Interpreter                                │  │  │
│  │  │  • Managed Sandbox Environment                              │  │  │
│  │  │  • Python 3.11 / Node.js 20                                 │  │  │
│  │  │  • Network Isolation (SANDBOX/PUBLIC)                       │  │  │
│  │  └─────────────────────────────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                                                          │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │                    Supporting Services                             │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐   │  │
│  │  │ CloudWatch  │  │ CloudTrail  │  │ S3 (Output Files)       │   │  │
│  │  │ Logs/Metrics│  │ Audit Logs  │  │ (Optional)              │   │  │
│  │  └─────────────┘  └─────────────┘  └─────────────────────────┘   │  │
│  └───────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 2. IAM 配置

### 2.1 ECS Task Role 扩展

现有 ECS Task Role 需要添加 AgentCore 权限：

```yaml
# deploy/iam/ecs-task-role-extension.yaml
AWSTemplateFormatVersion: '2010-09-09'
Description: IAM Policy extension for AgentCore Code Interpreter

Resources:
  AgentCorePolicy:
    Type: AWS::IAM::Policy
    Properties:
      PolicyName: AgentCoreCodeInterpreterAccess
      Roles:
        - !Ref ExistingECSTaskRole  # 引用现有角色
      PolicyDocument:
        Version: '2012-10-17'
        Statement:
          # Code Interpreter 管理权限
          - Sid: CodeInterpreterManagement
            Effect: Allow
            Action:
              - bedrock:CreateCodeInterpreter
              - bedrock:DeleteCodeInterpreter
              - bedrock:GetCodeInterpreter
              - bedrock:ListCodeInterpreters
            Resource: !Sub 'arn:aws:bedrock:${AWS::Region}:${AWS::AccountId}:code-interpreter/*'
          
          # Code Interpreter 运行时权限
          - Sid: CodeInterpreterRuntime
            Effect: Allow
            Action:
              - bedrock:StartCodeInterpreterSession
              - bedrock:StopCodeInterpreterSession
              - bedrock:InvokeCodeInterpreter
              - bedrock:UploadFileToSession
              - bedrock:DownloadFileFromSession
            Resource: !Sub 'arn:aws:bedrock:${AWS::Region}:${AWS::AccountId}:code-interpreter/*'
          
          # CloudWatch Logs 权限
          - Sid: CloudWatchLogs
            Effect: Allow
            Action:
              - logs:CreateLogGroup
              - logs:CreateLogStream
              - logs:PutLogEvents
            Resource: !Sub 'arn:aws:logs:${AWS::Region}:${AWS::AccountId}:log-group:/mcp-skills/code-interpreter/*'
          
          # CloudWatch Metrics 权限
          - Sid: CloudWatchMetrics
            Effect: Allow
            Action:
              - cloudwatch:PutMetricData
            Resource: '*'
            Condition:
              StringEquals:
                cloudwatch:namespace: 'MCPSkills/CodeInterpreter'
```

### 2.2 Code Interpreter 执行角色

```yaml
# deploy/iam/code-interpreter-execution-role.yaml
AWSTemplateFormatVersion: '2010-09-09'
Description: Execution role for Code Interpreter sandbox

Resources:
  CodeInterpreterExecutionRole:
    Type: AWS::IAM::Role
    Properties:
      RoleName: mcp-skills-code-interpreter-execution
      AssumeRolePolicyDocument:
        Version: '2012-10-17'
        Statement:
          - Effect: Allow
            Principal:
              Service: bedrock.amazonaws.com
            Action: sts:AssumeRole
      
      # 最小权限 - 仅允许日志写入
      Policies:
        - PolicyName: MinimalExecutionPolicy
          PolicyDocument:
            Version: '2012-10-17'
            Statement:
              - Effect: Allow
                Action:
                  - logs:CreateLogStream
                  - logs:PutLogEvents
                Resource: !Sub 'arn:aws:logs:${AWS::Region}:${AWS::AccountId}:log-group:/aws/bedrock/code-interpreter/*'

Outputs:
  ExecutionRoleArn:
    Description: ARN of the Code Interpreter execution role
    Value: !GetAtt CodeInterpreterExecutionRole.Arn
    Export:
      Name: CodeInterpreterExecutionRoleArn
```

---

## 3. 环境变量配置

### 3.1 后端环境变量

```bash
# backend/.env.example (新增)

# AgentCore Code Interpreter 配置
CODE_INTERPRETER_ENABLED=true
CODE_INTERPRETER_REGION=us-east-1
CODE_INTERPRETER_EXECUTION_ROLE_ARN=arn:aws:iam::ACCOUNT_ID:role/mcp-skills-code-interpreter-execution

# 会话配置
CODE_INTERPRETER_DEFAULT_TIMEOUT=300
CODE_INTERPRETER_IDLE_TIMEOUT=600
CODE_INTERPRETER_MAX_SESSIONS=10

# 网络模式 (sandbox | public)
CODE_INTERPRETER_DEFAULT_NETWORK_MODE=sandbox
```

### 3.2 ECS Task Definition 更新

```json
{
  "containerDefinitions": [
    {
      "name": "mcp-skills-server",
      "environment": [
        {
          "name": "CODE_INTERPRETER_ENABLED",
          "value": "true"
        },
        {
          "name": "CODE_INTERPRETER_REGION",
          "value": "us-east-1"
        }
      ],
      "secrets": [
        {
          "name": "CODE_INTERPRETER_EXECUTION_ROLE_ARN",
          "valueFrom": "arn:aws:ssm:us-east-1:ACCOUNT_ID:parameter/mcp-skills/code-interpreter-role-arn"
        }
      ]
    }
  ]
}
```

---

## 4. 监控配置

### 4.1 CloudWatch Dashboard

```yaml
# deploy/cloudwatch/code-interpreter-dashboard.yaml
AWSTemplateFormatVersion: '2010-09-09'
Description: CloudWatch Dashboard for Code Interpreter monitoring

Resources:
  CodeInterpreterDashboard:
    Type: AWS::CloudWatch::Dashboard
    Properties:
      DashboardName: MCP-Skills-CodeInterpreter
      DashboardBody: !Sub |
        {
          "widgets": [
            {
              "type": "metric",
              "properties": {
                "title": "Execution Duration",
                "metrics": [
                  ["MCPSkills/CodeInterpreter", "ExecutionDuration", {"stat": "Average"}],
                  ["...", {"stat": "p99"}]
                ],
                "period": 300
              }
            },
            {
              "type": "metric",
              "properties": {
                "title": "Active Sessions",
                "metrics": [
                  ["MCPSkills/CodeInterpreter", "ActiveSessions"]
                ],
                "period": 60
              }
            },
            {
              "type": "metric",
              "properties": {
                "title": "Execution Errors",
                "metrics": [
                  ["MCPSkills/CodeInterpreter", "ExecutionErrors"]
                ],
                "period": 300
              }
            }
          ]
        }
```

### 4.2 告警配置

```yaml
# deploy/cloudwatch/code-interpreter-alarms.yaml
Resources:
  HighExecutionDurationAlarm:
    Type: AWS::CloudWatch::Alarm
    Properties:
      AlarmName: CodeInterpreter-HighExecutionDuration
      MetricName: ExecutionDuration
      Namespace: MCPSkills/CodeInterpreter
      Statistic: Average
      Period: 300
      EvaluationPeriods: 3
      Threshold: 30000  # 30 seconds
      ComparisonOperator: GreaterThanThreshold
      AlarmActions:
        - !Ref AlertSNSTopic

  HighErrorRateAlarm:
    Type: AWS::CloudWatch::Alarm
    Properties:
      AlarmName: CodeInterpreter-HighErrorRate
      MetricName: ExecutionErrors
      Namespace: MCPSkills/CodeInterpreter
      Statistic: Sum
      Period: 300
      EvaluationPeriods: 2
      Threshold: 10
      ComparisonOperator: GreaterThanThreshold
      AlarmActions:
        - !Ref AlertSNSTopic
```

---

## 5. 区域支持

### 5.1 AgentCore 可用区域

| 区域 | 状态 | 备注 |
|------|------|------|
| us-east-1 | ✅ 可用 | 推荐 (主要区域) |
| us-west-2 | ✅ 可用 | 备选 |
| eu-west-1 | ⚠️ 待确认 | 需要验证 |
| ap-northeast-1 | ⚠️ 待确认 | 需要验证 |

### 5.2 区域选择逻辑

```python
# 根据 ECS 部署区域选择 AgentCore 区域
def get_code_interpreter_region() -> str:
    ecs_region = os.environ.get("AWS_REGION", "us-east-1")
    
    # AgentCore 可用区域映射
    region_mapping = {
        "us-east-1": "us-east-1",
        "us-east-2": "us-east-1",  # 回退到 us-east-1
        "us-west-1": "us-west-2",
        "us-west-2": "us-west-2",
        "eu-west-1": "eu-west-1",
        "eu-central-1": "eu-west-1",  # 回退
    }
    
    return region_mapping.get(ecs_region, "us-east-1")
```

---

## 6. 部署清单

### 6.1 部署前检查

- [ ] 确认 AWS 账户已启用 Bedrock AgentCore
- [ ] 确认目标区域支持 Code Interpreter
- [ ] 创建 IAM 执行角色
- [ ] 更新 ECS Task Role 权限
- [ ] 配置环境变量

### 6.2 部署步骤

```bash
# 1. 部署 IAM 角色
aws cloudformation deploy \
  --template-file deploy/iam/code-interpreter-execution-role.yaml \
  --stack-name mcp-skills-code-interpreter-iam \
  --capabilities CAPABILITY_NAMED_IAM

# 2. 更新 ECS Task Role
aws cloudformation deploy \
  --template-file deploy/iam/ecs-task-role-extension.yaml \
  --stack-name mcp-skills-ecs-role-extension \
  --capabilities CAPABILITY_IAM

# 3. 存储配置到 SSM
aws ssm put-parameter \
  --name "/mcp-skills/code-interpreter-role-arn" \
  --value "arn:aws:iam::ACCOUNT_ID:role/mcp-skills-code-interpreter-execution" \
  --type SecureString

# 4. 部署监控
aws cloudformation deploy \
  --template-file deploy/cloudwatch/code-interpreter-dashboard.yaml \
  --stack-name mcp-skills-code-interpreter-monitoring

# 5. 重新部署 ECS 服务
./deploy-backend.sh
```

---

## 7. 成本估算

| 资源 | 计费方式 | 预估月成本 |
|------|----------|------------|
| Code Interpreter 会话 | 按会话时长 | $50-200 |
| CloudWatch Logs | 按数据量 | $5-20 |
| CloudWatch Metrics | 按指标数 | $3-10 |
| **总计** | | **$58-230/月** |

*注：实际成本取决于使用量*
