### database

starrock
10.9.14.128
9030
root
TJycrock#lc2025

### 功能1

这是一段测试好的sql   营销系统里面拜访记录不到一分钟的零售户，但在营销系统里面的状态是正常
前端页面加一个公司和时间的筛选  然后对这一段sql进行筛选展示
注意一下能最早开始筛选的时间 2024-01-01 00:00:00
公司代码
11120101 第一
11120102 第二
11120103 第三
11120104 东丽
11120105 西青
11120106 津南
11120107 北辰
11120111 武清
11120112 宝坻
11120113 滨海
11120201 蓟州
11120202 静海
11120203 宁河

select com_id , short_name as 公司, cust_code as 客户编码 , license_code as 许可证号,cust_name as 客户名称, terminal_level as 客户档位,person_name as 客户经理,
DATE_FORMAT(  plan_date , '%Y-%m-%d') as 拜访日期, visit_time as 拜访时长
from crm_mcs_cust_visit_plan a
left join t_comm_emp_yx t on a.cust_manager_person_uuid = t.person_uuid
where plan_date >= '2024-01-01 00:00:00' and visit_status='03'  and deleted = '0'
and visit_time < 60   and com_id = '11120101'

### 功能2

这是一段测试好的 SQL。营销系统中的客户被定义为全商品客户，但在营销系统里没有每个自然月拜访记录时进行提示。
前端页面提供公司和时间筛选，并按这段 SQL 的业务逻辑展示。
全商品评价从 2025 年 9 月开始，根据 `uc_evaluation_m` 判断，因此前端最早开始月份为 2025-09。
许可证发生歇业、停业整顿、收回、注销后，从最早决定月份起不再生成异常拜访。

```sql
WITH bf AS (
  SELECT cust_uuid, DATE_FORMAT(plan_date, '%Y-%m-01') AS op_month, count(*) AS sl
  FROM crm_mcs_cust_visit_plan
  WHERE plan_date >= '2025-09-01 00:00:00'
    AND visit_status = '03'
    AND deleted = '0'
  GROUP BY cust_uuid, DATE_FORMAT(plan_date, '%Y-%m-01')
),
list AS (
  SELECT
    DATE_FORMAT(a.sysupdatedate, '%Y%m') AS year_month,
    cust_uuid,
    cust_code,
    cust_name,
    customer_manager_person_id AS mgr_id,
    DATE_FORMAT(a.sysupdatedate, '%Y-%m-01') AS sqdate
  FROM uc_evaluation_m a
  LEFT JOIN uc_evaluation_m_cust b ON a.evaluation_m_uuid = b.evaluation_m_uuid
  LEFT JOIN kc_customer_yz c ON b.cust_uuid = c.id
  WHERE evaluation_type_adj = '04'
    AND a.status = '3'
    AND y_m >= '2025-09'
),
bg AS (
  SELECT
    lic_no,
    MIN(DATE_FORMAT(decide_date, '%Y-%m-01')) AS decide_month
  FROM tstg_zmglpt_std_l_rlic_handle_main
  WHERE handle_result IN ('02', '05')
    AND apply_type IN ('07', '10', '12', '18')
    AND decide_date >= '2025-09-01 00:00:00'
  GROUP BY lic_no
),
zh AS (
  SELECT
    d.com_id,
    d.com_name,
    d.short_name,
    list.cust_uuid,
    cust_code,
    cust_name,
    mgr_id,
    sqdate,
    year_month,
    d.sdpt_name,
    d.person_name,
    bg.decide_month,
    coalesce(sl, 0) AS sl
  FROM list
  LEFT JOIN bf ON list.cust_uuid = bf.cust_uuid AND list.sqdate = bf.op_month
  LEFT JOIN bg ON list.cust_code = bg.lic_no
  LEFT JOIN t_comm_employee d ON list.mgr_id = d.person_uuid
)
SELECT DISTINCT year_month, short_name, sdpt_name, person_name, cust_code, cust_name
FROM zh
WHERE sl = 0
  AND com_id = '11120103'
  AND (decide_month IS NULL OR sqdate < decide_month)
ORDER BY year_month, short_name, sdpt_name, person_name;
```

### 功能3

这是一段测试好的sql   营销系统中的一个客户经理单日的拜访记录需按工作日汇总全部拜访时长，对不足60分钟的进行提示
前端页面加一个公司和时间的筛选  然后对这一段sql进行筛选展示
前端展示字段中文名 tot是拜访时间 前端展示转为分钟 保留两位小数
时间也是从2024-01-01 00:00:00开始

tot
SELECT
substr(plan_date, 1, 10) v_date,
com_id,
short_name,
sdpt_name,
cust_manager_person_uuid,
person_name,
sum(visit_time) tot
FROM
crm_mcs_cust_visit_plan cms
LEFT JOIN t_comm_emp_yx emp ON cms.cust_manager_person_uuid = emp.person_uuid
WHERE
plan_date >= '2024-01-01 00:00:00'
AND visit_status = '03'
AND deleted = '0'
GROUP BY
substr(plan_date, 1, 10),
com_id,
short_name,
sdpt_name,
cust_manager_person_uuid,
person_name
HAVING
sum(visit_time) < 3600
AND com_id = '11120101'

### 功能4：单次超长拜访

业务口径：单条有效拜访时长严格超过所选阈值，可选 260、280、300、320、340 分钟，默认 300 分钟（18000 秒）。公司、营业部、经理与日期由页面传入；最早日期为 2024-01-01。包含查询结束日。

```sql
SELECT
  CAST(cms.id AS VARCHAR) AS visit_id,
  DATE_FORMAT(cms.plan_date, '%Y-%m-%d') AS v_date,
  DATE_FORMAT(cms.plan_date, '%Y-%m-%d %H:%i:%s') AS visit_timestamp,
  emp.com_id, emp.short_name, emp.sdpt_name,
  cms.cust_manager_person_uuid, emp.person_name,
  cms.cust_uuid, cms.license_code, cms.cust_name, cms.visit_time
FROM crm_mcs_cust_visit_plan cms
LEFT JOIN t_comm_emp_yx emp ON cms.cust_manager_person_uuid = emp.person_uuid
WHERE cms.plan_date >= :start_date
  AND cms.plan_date < DATE_ADD(:end_date, INTERVAL 1 DAY)
  AND cms.visit_status = '03' AND cms.deleted = '0'
  AND cms.visit_time > :threshold_seconds
  AND emp.com_id IN (<已校验公司列表>);
```

`threshold_seconds` 由已验证的请求参数 `threshold_minutes * 60` 得到；后端将 `visit_time` 除以 60 并保留两位小数，返回 `visit_minutes`。页面附带客户名称和许可证号，方便定位具体客户。分页与导出共用此逻辑。

### 功能5：自动信息采集户缺访

按用户提供 SQL 实现：评价类型为 `03`，评价状态为 `3`，评价计算月份固定从 2025-09 起；检查评价生效月份内有效拜访次数为零的客户。最早可查月份为 2025-09。

```sql
WITH bf AS (
  SELECT cust_uuid, DATE_FORMAT(plan_date, '%Y-%m-01') AS op_month, COUNT(*) AS sl
  FROM crm_mcs_cust_visit_plan
  WHERE plan_date >= :start_month
    AND plan_date < DATE_ADD(:end_month, INTERVAL 1 MONTH)
    AND visit_status = '03' AND deleted = '0'
  GROUP BY cust_uuid, DATE_FORMAT(plan_date, '%Y-%m-01')
),
list AS (
  SELECT DATE_FORMAT(a.sysupdatedate, '%Y%m') AS year_month,
    b.cust_uuid, cust_code, cust_name, customer_manager_person_id AS mgr_id,
    DATE_FORMAT(a.sysupdatedate, '%Y-%m-01') AS sqdate
  FROM uc_evaluation_m a
  LEFT JOIN uc_evaluation_m_cust b ON a.evaluation_m_uuid = b.evaluation_m_uuid
  LEFT JOIN kc_customer_yz c ON b.cust_uuid = c.id
  WHERE evaluation_type_adj = '03' AND a.status = '3' AND y_m >= '2025-09'
)
SELECT DISTINCT list.year_month, d.com_id, d.short_name, d.sdpt_name,
  d.person_name, list.cust_uuid, list.mgr_id, list.cust_code, list.cust_name
FROM list
LEFT JOIN bf ON list.cust_uuid = bf.cust_uuid AND list.sqdate = bf.op_month
LEFT JOIN t_comm_employee d ON list.mgr_id = d.person_uuid
WHERE COALESCE(bf.sl, 0) = 0
  AND list.sqdate >= :start_month
  AND list.sqdate < DATE_ADD(:end_month, INTERVAL 1 MONTH)
  AND d.com_id IN (<已校验公司列表>);
```

营业部和经理按需要追加绑定参数条件；月份参数必须为每月第一天。有效记录存在但时长为零时，该客户通过“拜访次数”规则；持续有效期间逐月缺访、零时长单独判定及许可证变更排除应作为明确的业务扩展。

本次小规模业务样本使用内存 SQLite 进行日期函数适配验证，并在真实 StarRocks 上完成两个查询的 `EXPLAIN` 解析检查；业务数据结果仍需环境联调抽样核验。

## 营销专卖：扣款户名不符

按营销系统最新绑卡记录与有效许可证持证人核对。核心 SQL 如下，可选机关、许可证号、客户名称和绑定日期条件在最终 WHERE 中追加。

```sql
WITH latest_bank AS (
  SELECT custbank_uuid, cust_code, bankcard_owner, sysupdatedt,
    ROW_NUMBER() OVER (
      PARTITION BY cust_code ORDER BY sysupdatedt DESC, custbank_uuid DESC
    ) AS rn
  FROM pc_pay_custbank
)
SELECT lic.retailer_uuid, bank.custbank_uuid,
  lic.issue_org_code, lic.issue_org_name, lic.lic_no, lic.company_name,
  lic.manager_name, bank.bankcard_owner,
  DATE_FORMAT(bank.sysupdatedt, '%Y-%m-%d %H:%i:%s') AS sysupdatedt
FROM r_license_info lic
JOIN latest_bank bank ON lic.lic_no = bank.cust_code AND bank.rn = 1
WHERE lic.lic_status = '10'
  AND TRIM(lic.manager_name) <> TRIM(bank.bankcard_owner)
  AND bank.bankcard_owner IS NOT NULL AND TRIM(bank.bankcard_owner) <> '';
```

最新记录选择发生在姓名、日期过滤之前。空绑卡户名（含纯空格）排除；同时间绑卡记录用 `custbank_uuid` 确定顺序；持证人字段按提供 SQL 使用 `manager_name`。字段与接口见 [营销专卖模块说明](docs/12-营销专卖-扣款户名不符.md)。
