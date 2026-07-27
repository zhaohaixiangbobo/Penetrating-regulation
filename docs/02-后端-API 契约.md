# 02 · 后端 API 契约

所有接口除 `POST /api/auth/login` 和 `GET /api/health` 外，均需在 Header 中携带 `Authorization: Bearer <access_token>`。返回错误统一为 `{"detail": "..."}`。

## 认证

### POST /api/auth/login

- Request:
  ```json
  { "username": "admin", "password": "tjyc!2026" }
  ```
- Response 200:
  ```json
  { "access_token": "eyJ...", "token_type": "bearer", "username": "admin" }
  ```
- 401：用户名或密码错误

### GET /api/auth/me

返回当前用户信息，用于前端 initialState。

- Response 200：`{ "username": "admin" }`

## 元数据

### GET /api/meta/companies

返回 13 个公司字典。

```json
[{ "com_id": "11120101", "short_name": "第一" }, ...]
```

## 审计查询

三个接口共用分页响应结构：

```json
{
  "total": 123,
  "page": 1,
  "page_size": 20,
  "items": [ ... ]
}
```

### POST /api/audit/short-visit （功能 1）

拜访时长 < 60 秒但状态正常的记录。

- Request:
  ```json
  {
    "com_id": "11120101",
    "start_date": "2024-01-01T00:00:00",
    "end_date": "2024-12-31T23:59:59",
    "page": 1,
    "page_size": 20
  }
  ```
- 校验：`com_id` 必须在字典中；`start_date >= 2024-01-01`
- Item：`com_id / short_name / cust_code / license_code / cust_name / terminal_level / person_name / plan_date / visit_time (秒)`

### POST /api/audit/full-cust-miss （功能 2）

全商品客户当自然月无有效拜访。

- Request:
  ```json
  {
    "com_id": "11120101",
    "start_month": "2025-02-01",
    "end_month": "2025-06-01",
    "page": 1,
    "page_size": 20
  }
  ```
- 校验：`start_month >= 2025-02-01`
- Item：`sqdate / com_id / short_name / cust_code / cust_name`

### POST /api/audit/daily-under-hour （功能 3）

按工作日汇总客户经理拜访总时长 < 60 分钟。

- Request: 同 `/short-visit`
- Item：`v_date / com_id / short_name / sdpt_name / cust_manager_person_uuid / person_name / visit_minutes`
  - `visit_minutes`：`round(sum(visit_time) / 60, 2)`

## 健康检查

`GET /api/health` → `{ "status": "ok" }`（不需要鉴权）
