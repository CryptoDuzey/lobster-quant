# 魔搭社区部署说明

龙虾量化不是 Gradio 小应用，而是 Vue 前端 + FastAPI 后端 + 本地数据缓存的完整工作站。魔搭创空间请选择 **Docker**。

## 创建空间时怎么选

- 接入 SDK：Docker
- 资源：先选免费 CPU（2v CPU / 16G 内存）
- 镜像：默认推荐镜像即可，实际运行以项目根目录 `Dockerfile` 为准

## 必填环境变量

在魔搭空间的环境变量里配置：

```bash
PORT=7860
DEEPSEEK_API_KEY=你的 DeepSeek Key
DEEPSEEK_MODEL=deepseek-chat
DEEPSEEK_API_URL=https://api.deepseek.com/chat/completions
LOBSTER_SECRET_KEY=换成一串长随机字符
LOBSTER_DB_PATH=/mnt/workspace/lobster_quant.db
LOBSTER_CACHE_DIR=/mnt/workspace/cache
LOBSTER_FRONTEND_DIST=/home/user/app/front/dist
CORS_ORIGINS=*
```

`DEEPSEEK_API_KEY` 不要写进代码，也不要提交到 GitHub。

## 持久化数据

MVP 阶段默认把数据写到：

- 数据库：`/mnt/workspace/lobster_quant.db`
- 行情缓存目录：`/mnt/workspace/cache`

这样重启后用户、策略、回测记录和已缓存行情不会像新项目一样丢失。

## 启动方式

Docker 会执行：

```bash
python -u app.py
```

服务会监听 `0.0.0.0:7860`。

## 上线后检查

部署成功后依次访问：

- `/health`：检查后端是否在线
- `/docs`：检查 API 文档
- `/`：打开龙虾量化前端

然后在页面里测试：

1. 股票搜索
2. K 线加载
3. AI 对话
4. 自然语言生成策略
5. 回测
6. 回测记录刷新后是否还在

## 数据缓存建议

不要一开始缓存全市场所有分钟线。更稳的方式：

1. 用户请求过的股票先缓存
2. 日线长期保存
3. 分钟线按需保存
4. 后续数据量大了，再迁移到对象存储或 PostgreSQL

