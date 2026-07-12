# SQL Gatekeeper

> 面向 LLM 生成 SQL 的 MySQL 生产网关：自动分库分表路由、SQL 改写、EXPLAIN 风险检查、只读执行、全链路审计。

SQL Gatekeeper 放在 AI Agent 和 MySQL 之间。调用方可以提交逻辑 SQL，网关负责判断 SQL 是否安全、根据元数据路由到真实物理分表、改写 SQL、检查执行计划，并记录审计日志。

![SQL Gatekeeper terminal demo](docs/assets/demo-terminal.png)

## 为什么需要它

让 LLM 直接执行 SQL 很方便，但生产环境里风险也很集中：

- 模型可能生成写操作、多语句、缺少 `LIMIT` 的查询，或者代价很高的扫描。
- 当模型可以控制整条 SQL 的结构时，传统 prepared statement 和 ORM 转义并不能完全解决问题。
- 真实业务库经常有逻辑表、分库分表、路由规则，这些细节不应该都暴露给模型。
- AI 生成 SQL 的通过、拒绝和执行结果都需要审计。

SQL Gatekeeper 就是为这条边界准备的。

## 核心能力

- 接收 LLM 或 Agent 生成的 MySQL `SELECT`。
- 支持逻辑表查询，例如 `select * from user where uid = 10001 limit 10`。
- 从 SQL 谓词或 `route_context` 中提取路由因子。
- 将逻辑表改写为已注册的物理表，例如 `user` 改写为 `user_1`。
- 拦截非 `SELECT`、多语句、缺少 `LIMIT`、超大 `LIMIT`、跨数据源 join 和高风险执行计划。
- 通过 MySQL `EXPLAIN` 拦截大表全表扫描、`Using temporary`、`Using filesort`。
- 使用只读账号执行通过检查的 SQL。
- 对校验和执行结果写入审计日志。

## 快速开始

克隆项目并启动完整 demo：

```bash
git clone https://github.com/TheCactuslxf/sql-gatekeeper.git
cd sql-gatekeeper
docker compose up --build
```

它会启动：

- `http://127.0.0.1:8080` 上的 SQL Gatekeeper API
- 一个元数据库 MySQL
- 一个 demo 用户库 MySQL
- 一个 demo 订单库 MySQL

API 容器启动时会自动创建元数据表，并写入 demo 路由规则。

检查服务：

```bash
curl -s http://127.0.0.1:8080/health
```

提交一条逻辑 SQL：

```bash
curl -s http://127.0.0.1:8080/api/v1/sql/check \
  -H "content-type: application/json" \
  -d '{
    "request_id": "demo-001",
    "operator": "ai-agent",
    "scene": "demo",
    "sql": "select uid, user_name from user where uid = 10001 limit 10",
    "route_context": {}
  }'
```

执行通过检查的 SQL：

```bash
curl -s http://127.0.0.1:8080/api/v1/sql/execute \
  -H "content-type: application/json" \
  -d '{
    "request_id": "demo-002",
    "operator": "ai-agent",
    "scene": "demo",
    "sql": "select uid, user_name from user where uid = 10001 limit 1",
    "route_context": {}
  }'
```

也可以直接运行 demo 脚本：

```bash
./scripts/demo.sh
```

Windows PowerShell：

```powershell
.\scripts\demo.ps1
```

停止 demo：

```bash
docker compose down -v
```

### 本地开发

如果你想在本机直接跑 API，可以只用 Docker 启动 MySQL：

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
docker compose up -d meta-db biz-user-db biz-order-db
python -m sql_gatekeeper.bootstrap.meta
uvicorn sql_gatekeeper.api.app:app --host 127.0.0.1 --port 8080
```

返回结果中会包含改写后的物理 SQL：

```json
{
  "allowed": true,
  "reason_code": "ALLOW",
  "rewritten_sql": "select uid, user_name from user_1 where uid = 10001 limit 10",
  "logical_tables": ["user"],
  "physical_tables": ["user_1"],
  "datasource_codes": ["biz_user_db"]
}
```

## 路由示例

当前 demo 元数据包含两张逻辑表：

| 逻辑表 | 路由因子 | 路由规则 | 物理表 |
| --- | --- | --- | --- |
| `user` | SQL 谓词 `uid` | `int(uid) % 2` | `user_0` 或 `user_1` |
| `order` | `route_context.biz_date` | `YYYY-MM` 转 `YYYY_MM` | `order_2025_06`、`order_2025_07` |

例如：

```sql
select order_id, amount from order where order_id = 'A1002' limit 1
```

配合：

```json
{"biz_date": "2025-07"}
```

会被改写为：

```sql
select order_id, amount from order_2025_07 where order_id = 'A1002' limit 1
```

## 适合谁

- 正在做 Text-to-SQL 或 AI Agent 数据库访问的团队。
- 需要给 LLM 生成 SQL 加安全边界的后端工程师。
- 有分库分表、逻辑表、路由元数据的业务系统。
- 需要审计 AI 数据库查询行为的平台团队。

## 开发

运行普通单测：

```bash
pytest tests
```

运行 Docker MySQL 相关测试：

```bash
RUN_DOCKER_TESTS=1 pytest tests
```

## Roadmap

- 使用 `sqlglot` 等 AST 解析器替换当前轻量正则解析器。
- 支持 PostgreSQL。
- 增加 MCP server 模式。
- 增加策略 DSL，支持租户条件、表白名单、列黑名单。
- 增加审计看板。
- 发布 Docker 镜像和 PyPI 包。

## License

MIT. See [LICENSE](LICENSE).
