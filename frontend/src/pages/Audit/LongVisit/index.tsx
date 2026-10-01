/** 单次超长拜访明细：按可选分钟阈值筛选有效拜访，默认 300 分钟。 */
import { Tag } from 'antd';
import type { ProColumns } from '@ant-design/pro-components';
import { queryLongVisit, exportLongVisit } from '@/services/audit';
import type { LongVisitRow } from '@/services/audit';
import { getCompanyTagColor } from '@/utils/companyColor';
import AuditQueryPage from '../components/AuditQueryPage';

const columns: ProColumns<LongVisitRow>[] = [
  { title: '拜访日期', dataIndex: 'v_date', width: 125, sorter: true },
  { title: '公司', dataIndex: 'short_name', width: 100, render: (_, row) => row.short_name ? <Tag color={getCompanyTagColor(row.short_name)}>{row.short_name}</Tag> : '-' },
  { title: '营业部', dataIndex: 'sdpt_name', width: 200, ellipsis: true },
  { title: '客户经理', dataIndex: 'person_name', width: 100 },
  { title: '许可证号', dataIndex: 'license_code', width: 150, copyable: true },
  { title: '客户名称', dataIndex: 'cust_name', width: 230, ellipsis: true },
  { title: '单次拜访时长(分钟)', dataIndex: 'visit_minutes', width: 170, sorter: true,
    render: (_, row) => row.visit_minutes == null ? '-' : row.visit_minutes.toFixed(2) },
];

export default function LongVisitPage() {
  return <AuditQueryPage<LongVisitRow>
    title="单次超长拜访" description="客户经理对同一客户的单次有效拜访时长超过所选阈值（默认 300 分钟）"
    cacheKey="shenji_long_visit_v2" timeMode="date" minTime="2024-01-01" columns={columns}
    durationThreshold={{ field: 'threshold_minutes', label: '拜访时长阈值', unit: '分钟', options: [260, 280, 300, 320, 340], defaultValue: 300 }}
    exportColumns={columns.map((column) => ({ title: String(column.title), dataIndex: String(column.dataIndex) }))}
    formatExport={(row) => ({ ...row, visit_minutes: row.visit_minutes == null ? '' : row.visit_minutes.toFixed(2) })}
    // 记录 ID 以字符串返回，避免 bigint 精度丢失；空 ID 历史数据使用组合字段。
    rowKey={(row, index) => JSON.stringify([row.com_id, row.visit_id, row.visit_timestamp, row.cust_manager_person_uuid, row.visit_id == null ? [row.cust_uuid, row.visit_minutes, index] : null])}
    query={(payload) => queryLongVisit({ ...payload, start_date: payload.start_date!, end_date: payload.end_date!, sort_field: payload.sort_field as 'v_date' | 'visit_minutes' | undefined })}
    exportQuery={(payload) => exportLongVisit({ ...payload, start_date: payload.start_date!, end_date: payload.end_date!, sort_field: payload.sort_field as 'v_date' | 'visit_minutes' | undefined })}
  />;
}
