# 龙虾量化 Lobster Quant

龙虾量化是一个面向中国 A 股市场的 AI 原生量化投研与回测工作站。项目目标不是做静态金融大屏，而是把真实行情、自然语言策略、rqalpha 回测、策略保存和 AI 分析串成一个可以本地运行的工作站。

## 当前能力

- 行情雷达：股票搜索、A 股 K 线、周期切换、消息面、AI 行情助手
- 策略工坊：自然语言对话、策略代码生成、触发真实回测
- 回测实验室：累计收益、基准收益、Alpha、Beta、Sharpe、最大回撤、年化收益、交易记录
- 策略广场：策略保存、发布、收藏、评论的基础结构
- AI 能力：DeepSeek Provider、金融 Agent、策略 Agent、Agent / Skill 管理入口
- 本地持久化：SQLite 保存回测记录、策略、用户设置、模型配置和缓存

## 技术栈

- 前端：Vue 3、Vite、Lightweight Charts
- 后端：FastAPI、rqalpha、akshare、东方财富 / 新浪数据适配
- 数据库：SQLite
- AI：DeepSeek 接口，后端代理调用，API Key 不放前端

## 目录结构

```text
rq_demo/
  backend/        后端接口、行情、回测、Agent、数据库
  front/          前端工作站
  scripts/        本地安装、启动、停止脚本
  docs/           项目说明
  archive/        本地参考资料，不提交
  logs/           本地运行日志，不提交
```

更详细的目录说明见 `docs/PROJECT_STRUCTURE.md`。

## 环境要求

建议环境：

- Windows 10 / 11
- Python 3.10 或 3.11
- Node.js 18+
- npm

说明：

- TA-Lib 不是硬性依赖。没有 TA-Lib 时，项目会使用 pandas / numpy 的指标计算兜底。
- 如果你需要原生 TA-Lib，可以自行安装，但不建议把它作为首次运行门槛。

## 首次安装

在项目根目录执行：

```powershell
.\scripts\setup-dev.ps1
```

这个脚本会做几件事：

- 创建本地 Python 虚拟环境 `.venv-rqsdk`
- 安装后端依赖
- 安装前端依赖
- 自动从 `.env.example` 复制出本地 `.env`

如果你的电脑上 `python` 命令不可用，可以指定 Python：

```powershell
.\scripts\setup-dev.ps1 -PythonCommand py
```

## 配置 AI Key

复制脚本会自动生成：

```text
backend/.env
```

如需使用真实 AI 对话，在 `backend/.env` 中填写：

```env
DEEPSEEK_API_KEY=你的 DeepSeek Key
DEEPSEEK_MODEL=deepseek-chat
DEEPSEEK_API_URL=https://api.deepseek.com/chat/completions
LOBSTER_SECRET_KEY=换成一段足够长的随机字符串
```

注意：

- DeepSeek Key 只放后端，不要放前端。
- `backend/.env` 已被 `.gitignore` 排除，不会上传 GitHub。
- 如果不配置 Key，行情和基础回测仍可运行，但 AI 对话会提示未配置或使用本地规则能力。

## 启动项目

```powershell
.\scripts\start-dev.ps1
```

启动后访问：

- 前端：http://127.0.0.1:5173
- 后端接口文档：http://127.0.0.1:8000/docs

停止服务：

```powershell
.\scripts\stop-dev.ps1
```

## 数据会不会丢？

不会。后端启动时会自动创建 SQLite 数据库，默认位置：

```text
backend/app/data/lobster_quant.db
```

这些内容会保存在本机：

- 回测运行记录
- 用户保存的策略
- 策略广场数据
- 用户和设置
- 模型供应商配置
- Agent / Skill 配置
- 行情缓存和基准缓存

也就是说，同一台机器下次打开项目时，不会像全新项目一样空白。

注意：数据库是本机运行数据，不适合提交到 GitHub。别人拉取项目后，会在自己的机器上自动生成新的本地数据库。

## GitHub 上传前检查

可以提交：

- `backend/` 源码
- `front/` 源码
- `scripts/`
- `docs/`
- `.env.example`
- `README.md`

不要提交：

- `backend/.env`
- `front/.env`
- `backend/app/data/lobster_quant.db`
- `backend/app/data/*.jsonl`
- `logs/`
- `front/node_modules/`
- `front/dist/`
- `.venv-rqsdk/`
- `archive/`

这些已经写入 `.gitignore`。

## 常用验证命令

前端构建：

```powershell
cd front
npm run build
```

后端基础检查：

```powershell
cd backend
python -m compileall app
```

检查接口是否在线：

```powershell
python -c "import requests; print(requests.get('http://127.0.0.1:8000/docs', timeout=8).status_code)"
```

## 重要边界

- 正式回测不应使用 mock 数据。
- 基准曲线缺失时，不应伪造成一条平线。
- Alpha / Beta 必须来自真实策略收益序列和真实基准收益序列。
- AI 不能直接在前端执行用户输入代码。
- 实盘交易权限当前不开放，项目重点是行情、投研、策略生成和回测验证。

