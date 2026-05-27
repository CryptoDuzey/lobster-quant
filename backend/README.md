# 龙虾量化后端

后端负责行情、新闻、回测、策略保存、用户设置、AI Agent 和本地数据库。

## 启动

建议从项目根目录启动：

```powershell
.\scripts\start-dev.ps1
```

也可以只启动后端：

```powershell
cd backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

接口文档：

```text
http://127.0.0.1:8000/docs
```

## 本地数据库

默认数据库：

```text
backend/app/data/lobster_quant.db
```

后端启动时会自动创建数据库和表。数据库文件保存本机运行记录，不提交到 GitHub。

## 环境变量

复制示例：

```powershell
Copy-Item .env.example .env
```

主要配置：

- `DEEPSEEK_API_KEY`
- `DEEPSEEK_MODEL`
- `DEEPSEEK_API_URL`
- `LOBSTER_SECRET_KEY`
- `LOBSTER_DB_PATH`
- `RQALPHA_PYTHON`

`app.main` 会在启动时读取 `backend/.env`，所以用 `uvicorn app.main:app` 启动也能拿到本地配置。

## 持久化内容

- 回测记录
- 策略
- 用户设置
- 模型供应商配置
- Agent / Skill 配置
- 行情缓存
- 基准缓存

