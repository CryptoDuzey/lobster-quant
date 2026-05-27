# 项目目录说明

当前项目按“前端、后端、脚本、文档、本地运行数据”分层。

```text
rq_demo/
  backend/        后端 FastAPI、行情、回测、Agent、数据库代码
  front/          前端 Vue 3 工作站
  scripts/        本地安装、启动、停止脚本
  docs/           项目文档
  archive/        本地参考资料目录，不提交到 GitHub
  logs/           本地运行日志，不提交到 GitHub
```

## 后端

```text
backend/app/
  api/            对外接口
  auth/           登录、注册、Token
  backtest/       回测校验、基准、指标、结果审计
  data/           本地数据缓存服务和运行数据目录
  data_providers/ 行情数据源适配
  db/             SQLite 初始化和连接
  agents/         金融 Agent、策略 Agent
  skills/         Agent 可调用能力
  providers/      模型供应商
  orchestration/  工具注册、审计日志
  strategies/     策略广场与策略保存
  settings/       用户设置与模型配置
```

## 前端

```text
front/src/
  api/            前端接口封装
  components/     通用组件
  pages/          行情、工坊、回测、广场、能力中心、设置等页面
  router/         路由
  stores/         全局状态
  styles/         主题样式
```

## 本地持久化数据

默认数据库：

```text
backend/app/data/lobster_quant.db
```

数据库保存：

- 回测记录
- 策略
- 评论与收藏
- 用户设置
- 模型供应商配置
- Agent / Skill 配置
- 行情缓存和基准缓存

数据库、日志、审计 JSONL 都是本地运行数据，不提交到 GitHub。

## 启动

首次安装：

```powershell
.\scripts\setup-dev.ps1
```

启动：

```powershell
.\scripts\start-dev.ps1
```

停止：

```powershell
.\scripts\stop-dev.ps1
```

