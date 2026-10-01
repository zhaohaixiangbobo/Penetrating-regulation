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

## 新增营销审计查询（2026-09-30）

以下接口沿用审计路由登录校验。公司列表通过白名单校验，分页默认 20 条、最大 200 条；分页响应为 `total/page/page_size/items`。日期范围包含结束日，月份范围包含结束月。

### POST /api/audit/long-visit

查询单条有效拜访严格超过所选分钟阈值的记录。`threshold_minutes` 支持 260、280、300、320、340，默认 300；原始秒数比较为 `visit_time > threshold_minutes * 60`，等于阈值的记录通过规则。最早查询日期为 2024-01-01。非法阈值返回 422。

```json
{
  "com_ids": ["11120101"],
  "start_date": "2024-06-01",
  "end_date": "2024-06-30",
  "threshold_minutes": 300,
  "sdpt_name": "营业部甲",
  "person_uuid": "经理UUID",
  "sort_field": "visit_minutes",
  "sort_order": "descend",
  "page": 1,
  "page_size": 20
}
```

- 公司、开始及结束日期必填；营业部名称、经理 UUID、排序及分页可选。
- 可排序字段：`v_date`、`visit_minutes`。默认日期倒序，追加完整拜访时间及客户/经理字段排序；分钟排序使用原始秒数。
- 行字段：`visit_id / v_date / visit_timestamp / com_id / short_name / sdpt_name / cust_manager_person_uuid / person_name / cust_uuid / license_code / cust_name / visit_minutes`。`visit_id` 为源表 `id` 的字符串形式，保留 bigint 精度，用于行标识与次级排序。
- `visit_minutes` 为秒数除以 60，保留两位小数；单条记录直接判断，保持原始记录粒度。

### POST /api/audit/auto-collect-miss

查询自动信息采集户在评价生效月份内有效拜访次数为零的记录。评价条件为 `evaluation_type_adj = '03' AND status = '3' AND y_m >= '2025-09'`；输出月份取评价主表 `sysupdatedate`。

```json
{
  "com_ids": ["11120101"],
  "start_month": "2025-09-01",
  "end_month": "2025-12-01",
  "sdpt_name": "营业部甲",
  "person_uuid": "经理UUID",
  "sort_field": "year_month",
  "sort_order": "ascend",
  "page": 1,
  "page_size": 20
}
```

- 公司与起止月份必填，月份参数必须为每月第一天，最早为 2025-09-01。
- 营业部、经理 UUID 可选，精确筛选；可排序字段为 `year_month`，默认月份升序。
- 行字段：`year_month / com_id / short_name / sdpt_name / person_name / cust_uuid / mgr_id / cust_code / cust_name`。月份为 `YYYYMM`。
- 按输出行字段 `DISTINCT` 合并重复评价；人员归属通过 `t_comm_employee` 一次关联取得。
- 按提供 SQL 的拜访次数口径实现：有有效拜访但时长为零的客户通过规则。检查范围为评价生效月；历史逐月月历与许可证状态排除需另行定义。

### 对应导出接口

- `POST /api/audit/long-visit/export`
- `POST /api/audit/auto-collect-miss/export`

接收相同的业务筛选和排序，返回相同类型的行数组，最多 100000 行；页码和每页条数不参与导出范围。分页与导出共用 SQL 构建器和结果转换。

## 营销专卖 · 扣款户名不符

- `GET /api/marketing-monopoly/issuing-organizations`：有效许可证的发证机关字典。
- `POST /api/marketing-monopoly/bank-owner-mismatch`：当前最新绑卡户名与有效许可证持证人不符记录，统一分页响应。
- `POST /api/marketing-monopoly/bank-owner-mismatch/export`：同一筛选和排序的行数组，最多 100000 行。

请求可选字段：`issue_org_codes`（机关代码数组）、`lic_no`（精确查询）、`company_name`（文字包含）、`start_date/end_date`（最新绑定日期范围）、`sort_field/sort_order`、`page/page_size`。全部筛选为空时查询全部当前异常；日期成对提供。排序字段支持 `sysupdatedt / lic_no / issue_org_name`。

响应业务字段：`issue_org_code / issue_org_name / lic_no / company_name / manager_name / bankcard_owner / sysupdatedt`，另返回源记录标识 `retailer_uuid/custbank_uuid`。所有接口需登录，字段和规则详见 [营销专卖 · 扣款户名不符](12-营销专卖-扣款户名不符.md)。
