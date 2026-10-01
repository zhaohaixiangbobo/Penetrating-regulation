/** 自动信息采集户缺访：评价类型 03，检查评价生效月份的有效拜访次数。 */
import { Tag } from 'antd';
import type { ProColumns } from '@ant-design/pro-components';
import { queryAutoCollectMiss, exportAutoCollectMiss } from '@/services/audit';
import type { AutoCollectMissRow } from '@/services/audit';
import { getCompanyTagColor } from '@/utils/companyColor';
import AuditQueryPage from '../components/AuditQueryPage';

const formatMonth = (value?: string) => value ? `${value.slice(0, 4)}-${value.slice(4, 6)}` : '-';
const columns: ProColumns<AutoCollectMissRow>[] = [
  { title: '月份', dataIndex: 'year_month', width: 110, sorter: true, render: (_, row) => formatMonth(row.year_month) },
  { title: '公司', dataIndex: 'short_name', width: 100, render: (_, row) => row.short_name ? <Tag color={getCompanyTagColor(row.short_name)}>{row.short_name}</Tag> : '-' },
  { title: '营业部', dataIndex: 'sdpt_name', width: 200, ellipsis: true },
  { title: '客户经理', dataIndex: 'person_name', width: 100 },
  { title: '客户编码', dataIndex: 'cust_code', width: 150, copyable: true },
  { title: '客户名称', dataIndex: 'cust_name', width: 230, ellipsis: true },
];

export default function AutoCollectMissPage() {
  return <AuditQueryPage<AutoCollectMissRow>
    title="自动信息采集户缺访" description="自动信息采集户在评价生效月份内的有效拜访次数为零"
    cacheKey="shenji_auto_collect_miss_v1" timeMode="month" minTime="2025-09-01" columns={columns}
    exportColumns={columns.map((column) => ({ title: String(column.title), dataIndex: String(column.dataIndex) }))}
    formatExport={(row) => ({ ...row, year_month: formatMonth(row.year_month) })}
    rowKey={(row) => JSON.stringify([row.year_month, row.com_id, row.cust_uuid, row.mgr_id, row.cust_code, row.short_name, row.sdpt_name, row.person_name, row.cust_name])}
    query={(payload) => queryAutoCollectMiss({ ...payload, start_month: payload.start_month!, end_month: payload.end_month!, sort_field: payload.sort_field as 'year_month' | undefined })}
    exportQuery={(payload) => exportAutoCollectMiss({ ...payload, start_month: payload.start_month!, end_month: payload.end_month!, sort_field: payload.sort_field as 'year_month' | undefined })}
  />;
}
