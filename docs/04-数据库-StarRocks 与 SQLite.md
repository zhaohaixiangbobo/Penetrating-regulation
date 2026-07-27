# 04 · 数据库 · StarRocks 与 SQLite

## StarRocks

- 地址：`10.9.14.128:9030`
- 账号：`root` / `TJycrock#lc2025`
- 协议：MySQL 协议；Python 端使用 `asyncmy` 驱动
- 连接串（注意 `#` 需 URL 编码为 `%23`）：
  ```
  mysql+asyncmy://root:TJycrock%23lc2025@10.9.14.128:9030/?charset=utf8mb4
  ```
- 引擎设置：`pool_pre_ping=True`, `pool_recycle=1800` 防止长连接被服务器关闭

### 涉及表

| 表名 | 用途 |
| ---- | ---- |
| `crm_mcs_cust_visit_plan` | 拜访计划/记录 |
| `t_comm_emp_yx` | 员工/客户经理 |
| `t_comm_company` | 公司字典 |
| `uc_evaluation_m` / `uc_evaluation_m_cust` | 评测主表 / 客户明细 |
| `kc_customer_qsp` | 全商品客户白名单 |

### SQL 原文与参数化

见 `backend/app/api/audit.py` 中三个常量 `SQL_SHORT_VISIT` / `SQL_FULL_CUST_MISS` / `SQL_DAILY_UNDER_HOUR`。所有参数通过 `text().bindparams()` 传入，禁止字符串拼接。

### 公司代码字典

| com_id | 简称 | com_id | 简称 |
| ------ | ---- | ------ | ---- |
| 11120101 | 第一 | 11120111 | 武清 |
| 11120102 | 第二 | 11120112 | 宝坻 |
| 11120103 | 第三 | 11120113 | 滨海 |
| 11120104 | 东丽 | 11120201 | 蓟州 |
| 11120105 | 西青 | 11120202 | 静海 |
| 11120106 | 津南 | 11120203 | 宁河 |
| 11120107 | 北辰 |    |      |

## SQLite

- 位置：`backend/data/app.db`
- 表：`users(id, username, password_hash, created_at)`
- 默认账号：`admin` / `tjyc!2026`（密码走 bcrypt hash）
- 初始化脚本：`backend/scripts/init_db.py`

## 故障排查

- **密码含 `#` 未编码**：SQLAlchemy 会把 `#` 之后当作 URL fragment 解析，连接失败。务必使用 `%23`。
- **中文乱码**：确保 URL 带 `?charset=utf8mb4`。
- **时区**：StarRocks 侧统一使用 `Asia/Shanghai`；FastAPI 侧接收 ISO 8601（如 `2024-06-01T00:00:00`），透传即可。
- **长连接断开**：已启用 `pool_pre_ping`；若仍报 `Lost connection to MySQL server`，将 `pool_recycle` 调小到 600。
