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
这是一段测试好的sql   营销系统里面的客户被定义为全商品客户，但在营销系统里没有每个自然月拜访记录进行提示
前端页面加一个公司和时间的筛选  然后对这一段sql进行筛选展示
他全商品评价应该是从2025年2月才开始的  根据uc_evaluation_m
所以前端最早开始日期是2025-02 给用户一些提示
前端展示字段中文名


with bf as (
select substr(plan_date,1,4) op_year, cust_uuid, DATE_FORMAT( plan_date , '%Y-%m-01') op_month, count(*) sl 
from crm_mcs_cust_visit_plan 
where plan_date >= '2025-09-01 00:00:00' and visit_status='03'  and deleted = '0' 
group by cust_uuid , substr(plan_date,1,4) , DATE_FORMAT( plan_date , '%Y-%m-01') ) , -- 客户拜访记录
list as (
SELECT
  DATE_FORMAT(a.sysupdatedate, '%Y%m') year_month,
  county_uuid,  cust_uuid, cust_code, cust_name, customer_manager_person_id mgr_id ,
  DATE_FORMAT(a.sysupdatedate, '%Y-%m-01') sqdate
FROM
  uc_evaluation_m a
  LEFT JOIN uc_evaluation_m_cust b ON a.evaluation_m_uuid = b.evaluation_m_uuid
  left join kc_customer_yz c on b.cust_uuid = c.id 
WHERE  evaluation_type_adj = '04' and a.status = '3' and  y_m >= '2025-09' ) ,  -- 根据评测生效日期生产全商品客户拜访月历
zh as (
select com_id , com_name , short_name , list.cust_uuid , cust_code , cust_name , mgr_id , sqdate , year_month , coalesce ( sl , 0 ) sl from list 
left join bf on list.cust_uuid = bf.cust_uuid and list.sqdate = bf.op_month 
left join t_comm_employee d on list.mgr_id = d.person_uuid )  -- 关联查出全商品客户月拜访次数

select year_month , zh.short_name , sdpt_name , person_name , cust_code , cust_name   
from zh left join t_comm_employee b on zh.mgr_id = b.person_uuid
where sl = 0  and zh.com_id = '11120101' 
order by year_month , short_name , sdpt_name , person_name ;


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

