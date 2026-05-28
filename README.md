# 龙虾量化 Lobster Quant

龙虾量化是一个面向中国 A 股市场的 AI 原生量化投研与回测工作站。项目目标不是静态金融大屏，而是把真实行情、自然语言策略、rqalpha 回测、策略保存、AI 分析和数据缓存串成一个可运行的产品闭环。

## 当前能力

- 行情雷达：股票搜索、A 股 K 线、周期切换、消息面、AI 行情助手
- 策略工坊：自然语言对话、策略代码生成、真实回测触发
- 回测实验室：累计收益、基准收益、Alpha、Beta、Sharpe、最大回撤、交易记录
- 基础机器学习实验：支持单只股票日线的滚动训练择时回测；结果来自真实行情，不冒充 XGBoost / 深度学习
- 策略广场：策略保存、发布、收藏、评论的基础结构
- AI 能力：DeepSeek Provider、金融 Agent、策略 Agent、Agent / Skill 管理入口
- 数据持久化：SQLite 保存回测记录、策略、用户配置、模型配置和行情缓存

## 技术栈

- 前端：Vue 3、Vite、Lightweight Charts
- 后端：FastAPI、rqalpha、akshare、东方财富 / 新浪数据适配
- 数据库：SQLite，后续可迁移 PostgreSQL
- AI：后端代理调用 DeepSeek，API Key 不放前端

## 目录结构

```text
rq_demo/
  backend/        后端接口、行情、回测、Agent、数据库
  front/          前端工作站
  scripts/        本地安装、启动、停止和测试脚本
  docs/           项目文档
```

## 作品集说明

如果你想快速了解这个项目能展示什么、哪些能力已经通过验证、哪些边界不能夸大，可以先看：

```text
docs/PORTFOLIO_REVIEW.md
```

## 本地启动

首次安装：

```powershell
.\scripts\setup-dev.ps1
```

启动：

```powershell
.\scripts\start-dev.ps1
```

访问：

- 前端：http://127.0.0.1:5173
- 后端文档：http://127.0.0.1:8000/docs
- 后端健康检查：http://127.0.0.1:8000/health

停止：

```powershell
.\scripts\stop-dev.ps1
```

## 配置 AI Key

本地复制 `backend/.env.example` 为 `backend/.env`，然后填写：

```env
DEEPSEEK_API_KEY=你的 DeepSeek Key
DEEPSEEK_MODEL=deepseek-chat
DEEPSEEK_API_URL=https://api.deepseek.com/chat/completions
LOBSTER_SECRET_KEY=换成一串长随机字符
```

注意：`backend/.env` 不要提交到 GitHub。

## 数据是否会丢

默认数据库位置：

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

数据库文件已经被 `.gitignore` 排除，不会提交到 GitHub。

## 魔搭社区部署

魔搭创空间请选择：

- 接入 SDK：Docker
- 资源：先选免费 CPU
- 端口：7860

详细说明见：

```text
docs/MODELSCOPE_DEPLOY.md
```

Docker 部署会使用：

```text
app.py
Dockerfile
```

云端建议配置：

```env
PORT=7860
DEEPSEEK_API_KEY=你的 DeepSeek Key
LOBSTER_SECRET_KEY=换成一串长随机字符
LOBSTER_DB_PATH=/mnt/workspace/lobster_quant.db
LOBSTER_CACHE_DIR=/mnt/workspace/cache
LOBSTER_FRONTEND_DIST=/home/user/app/front/dist
CORS_ORIGINS=*
```

## 验证命令

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

产品烟测：

```powershell
python scripts\qa_product_smoke.py
```

策略泛化测试：

```powershell
python scripts\qa_strategy_generalization.py
```

回测真实性测试：

```powershell
python scripts\verify_backtest_truth.py
```

## 重要边界

- 正式回测不允许使用 mock 数据
- 基准曲线缺失时，不伪造成一条水平线
- Alpha / Beta 必须来自真实策略收益序列和真实基准收益序列
- AI 不能直接在前端执行用户输入代码
- 当前不开放实盘交易权限，重点是行情、投研、策略生成和回测验证
- 分钟级行情会优先尝试东方财富、新浪、腾讯等真实接口；如果数据源不可用或覆盖不足，系统会报错或提示截断，不会用日线或假数据冒充分分钟数据
- 机器学习目前是基础实验模式：先做真实行情、无未来函数、滚动训练和真实回测；XGBoost、LSTM、Transformer 等深度模型需要单独接入训练流水线和样本外验证后才会开放

