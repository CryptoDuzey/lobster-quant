# 本地运行数据目录

这里用于保存本机运行时数据，例如：

- `lobster_quant.db`：SQLite 数据库
- `*.db-wal` / `*.db-shm`：SQLite 运行辅助文件
- `agent_audit_logs.jsonl`：Agent 调用审计日志
- `community_strategies.json`：旧版本地策略广场缓存

这些文件包含本机数据或敏感调用记录，不提交到 GitHub。

后端启动时会自动创建需要的数据库和表。
