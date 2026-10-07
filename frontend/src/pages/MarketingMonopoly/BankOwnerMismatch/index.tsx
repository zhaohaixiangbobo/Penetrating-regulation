/** 扣款户名不符页面：最新绑卡姓名与有效许可证持证人比较，支持筛选及导出。 */
import IssuingOrgTag, { shortOrganization } from '@/components/IssuingOrgTag';
import { useEffect, useRef, useState } from 'react';
import { useModel } from '@umijs/max';
import { PageContainer, ProTable } from '@ant-design/pro-components';
import type { ActionType, ProColumns, ProFormInstance } from '@ant-design/pro-components';
import { Alert, Button, DatePicker, Divider, Form, Input, message, Select } from 'antd';
import { DownloadOutlined } from '@ant-design/icons';
import QueryFilter from '@/components/UnifiedQueryFilter';
import dayjs from 'dayjs';
import { exportBankOwnerMismatch, listIssuingOrganizations, queryBankOwnerMismatch } from '@/services/marketingMonopoly';
import type { BankOwnerMismatchRequest, BankOwnerMismatchRow, IssuingOrganization } from '@/services/marketingMonopoly';
import { loadCache, saveCache } from '@/utils/queryCache';
import { exportToExcel } from '@/utils/exportExcel';

const exportColumns = [
  { title: '发证机关代码', dataIndex: 'issue_org_code' },
  { title: '发证机关', dataIndex: 'issue_org_name' },
  { title: '许可证号', dataIndex: 'lic_no' },
  { title: '客户名称', dataIndex: 'company_name' },
  { title: '持证人', dataIndex: 'manager_name' },
  { title: '绑卡持卡人', dataIndex: 'bankcard_owner' },
  { title: '绑定时间', dataIndex: 'sysupdatedt' },
];

export default function BankOwnerMismatchPage() {
  const { initialState } = useModel('@@initialState');
  const username = initialState?.currentUser?.username;
  const cacheKey = `shenji_bank_owner_mismatch_v1:${encodeURIComponent(username || '')}`;
  const [cache] = useState(() => username ? loadCache<BankOwnerMismatchRequest, BankOwnerMismatchRow>(cacheKey) : null);
  // null 表示尚未查询；空对象表示用户明确提交“全部”条件。
  const filterRef = useRef<BankOwnerMismatchRequest | null>(cache?.filter || null);
  const pendingCacheRef = useRef(cache);
  const sortRef = useRef<Pick<BankOwnerMismatchRequest, 'sort_field' | 'sort_order'>>({
    sort_field: cache?.filter.sort_field, sort_order: cache?.filter.sort_order,
  });
  const requestVersionRef = useRef(0);
  const actionRef = useRef<ActionType>();
  const formRef = useRef<ProFormInstance>();
  const [organizations, setOrganizations] = useState<IssuingOrganization[]>([]);
  const [loadingOrgs, setLoadingOrgs] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [pageSize, setPageSize] = useState(cache?.pageSize || 20);
  const [queryStatus, setQueryStatus] = useState<'idle' | 'loading' | 'success' | 'error'>(cache ? 'success' : 'idle');
  // 快捷范围以点击当天计算；日期留空时覆盖全部历史绑定记录。
  const presets = [
    { label: '过去一个月', value: () => [dayjs().subtract(1, 'month'), dayjs()] as [dayjs.Dayjs, dayjs.Dayjs] },
    { label: '过去三个月', value: () => [dayjs().subtract(3, 'month'), dayjs()] as [dayjs.Dayjs, dayjs.Dayjs] },
    { label: '过去半年', value: () => [dayjs().subtract(6, 'month'), dayjs()] as [dayjs.Dayjs, dayjs.Dayjs] },
    { label: '过去一年', value: () => [dayjs().subtract(1, 'year'), dayjs()] as [dayjs.Dayjs, dayjs.Dayjs] },
  ];

  useEffect(() => {
    let active = true;
    setLoadingOrgs(true);
    listIssuingOrganizations().then((rows) => {
      if (active) setOrganizations(rows);
    }).catch(() => { /* 请求错误由统一处理器提示。 */ }).finally(() => {
      if (active) setLoadingOrgs(false);
    });
    return () => { active = false; requestVersionRef.current += 1; };
  }, []);

  const columns: ProColumns<BankOwnerMismatchRow>[] = [
    { title: '发证机关', dataIndex: 'issue_org_name', width: 110, sorter: true, render: (_: unknown, row: BankOwnerMismatchRow) => <IssuingOrgTag name={row.issue_org_name} /> },
    { title: '许可证号', dataIndex: 'lic_no', width: 150, copyable: true, sorter: true },
    { title: '客户名称', dataIndex: 'company_name', width: 230, ellipsis: true },
    { title: '持证人', dataIndex: 'manager_name', width: 130 },
    { title: '绑卡持卡人', dataIndex: 'bankcard_owner', width: 150 },
    { title: '绑定时间', dataIndex: 'sysupdatedt', width: 190, sorter: true },
  ].map((column) => ({
    ...column,
    defaultSortOrder: column.dataIndex === cache?.filter.sort_field ? cache?.filter.sort_order : undefined,
  }));

  const clearCache = () => {
    try { localStorage.removeItem(cacheKey); } catch { /* 缓存受限时仍可查询。 */ }
  };

  const handleExport = async () => {
    const filter = filterRef.current;
    if (filter === null) {
      message.warning('请先查询后再导出');
      return;
    }
    setExporting(true);
    try {
      const rows = await exportBankOwnerMismatch({ ...filter, ...sortRef.current });
      if (!rows.length) {
        message.info('当前筛选条件下无数据可导出');
        return;
      }
      const range = filter.start_date ? `${filter.start_date}_${filter.end_date}` : '全部绑定日期';
      exportToExcel(`扣款户名不符_${range}_${dayjs().format('YYYYMMDD_HHmmss')}`, exportColumns, rows);
      if (rows.length >= 100000) message.warning('已导出 100000 条，达到导出上限；请缩小筛选范围继续导出');
      else message.success(`已导出 ${rows.length} 条记录`);
    } catch { /* 统一请求处理器展示失败原因。 */ }
    finally { setExporting(false); }
  };

  return (
    <PageContainer header={{ title: '扣款户名不符', subTitle: '营销系统最新扣款账号户名与有效许可证持证人姓名不一致' }}>
      <QueryFilter
        formRef={formRef} layout="horizontal"
        initialValues={{
          issue_org_codes: cache?.filter.issue_org_codes,
          lic_no: cache?.filter.lic_no,
          company_name: cache?.filter.company_name,
          range: cache?.filter.start_date && cache?.filter.end_date ? [dayjs(cache.filter.start_date), dayjs(cache.filter.end_date)] : undefined,
        }}
        onFinish={async (values) => {
          requestVersionRef.current += 1;
          const [start, end] = values.range || [];
          filterRef.current = {
            issue_org_codes: values.issue_org_codes || [],
            lic_no: values.lic_no?.trim() || undefined,
            company_name: values.company_name?.trim() || undefined,
            start_date: start ? dayjs(start).format('YYYY-MM-DD') : undefined,
            end_date: end ? dayjs(end).format('YYYY-MM-DD') : undefined,
          };
          pendingCacheRef.current = null;
          clearCache();
          actionRef.current?.reload(true);
        }}
        onReset={() => {
          requestVersionRef.current += 1;
          filterRef.current = null;
          setQueryStatus('idle');
          pendingCacheRef.current = null;
          clearCache();
          formRef.current?.setFieldsValue({ issue_org_codes: [], lic_no: undefined, company_name: undefined, range: undefined });
          actionRef.current?.reload(true);
        }}
        submitter={{ searchConfig: { submitText: '查询', resetText: '重置' } }}
      >
        <Form.Item name="issue_org_codes" label="发证机关">
          <Select mode="multiple" placeholder="全部发证机关" allowClear showSearch optionFilterProp="label"
            loading={loadingOrgs} maxTagCount="responsive" style={{ minWidth: 280 }}
            options={organizations.map((org) => ({ label: shortOrganization(org.issue_org_name), value: org.issue_org_code }))}
            dropdownRender={(menu) => <>
              <div style={{ padding: '4px 8px' }}>
                <Button type="link" size="small" onMouseDown={(event) => event.preventDefault()} onClick={() => formRef.current?.setFieldsValue({ issue_org_codes: organizations.map((org) => org.issue_org_code) })}>全选</Button>
                <Button type="link" size="small" onMouseDown={(event) => event.preventDefault()} onClick={() => formRef.current?.setFieldsValue({ issue_org_codes: [] })}>清空</Button>
              </div><Divider style={{ margin: 0 }} />{menu}
            </>}
          />
        </Form.Item>
        <Form.Item name="lic_no" label="许可证号"><Input placeholder="请输入完整许可证号" maxLength={20} allowClear /></Form.Item>
        <Form.Item name="company_name" label="客户名称"><Input placeholder="请输入客户名称关键词" maxLength={100} allowClear /></Form.Item>
        <Form.Item name="range" label="绑定日期"><DatePicker.RangePicker format="YYYY-MM-DD" presets={presets} placeholder={['开始日期（可留空）', '结束日期（可留空）']} style={{ width: '100%' }} /></Form.Item>
      </QueryFilter>
      {queryStatus === 'error' && <Alert style={{ marginBottom: 16 }} type="error" showIcon message="查询失败，请检查错误提示后重新查询。" />}
      <ProTable<BankOwnerMismatchRow>
        actionRef={actionRef} columns={columns} search={false} scroll={{ x: 'max-content' }}
        locale={{ emptyText: queryStatus === 'idle' ? '请设置筛选条件后点击查询，也可直接查询全部记录' : queryStatus === 'error' ? '查询失败，请重试' : queryStatus === 'loading' ? '正在查询，请稍候' : '暂未查到符合条件的数据，请调整筛选条件后重试' }}
        rowKey={(row) => JSON.stringify([row.retailer_uuid, row.custbank_uuid, row.issue_org_code, row.lic_no])}
        pagination={{ pageSize, showSizeChanger: true, onChange: (_, size) => setPageSize(size), showTotal: (total, range) => `第 ${range[0]}-${range[1]} 条/总共 ${total} 条` }}
        toolBarRender={() => [<Button key="export" icon={<DownloadOutlined />} loading={exporting} onClick={handleExport}>导出 Excel</Button>]}
        request={async (params, sort) => {
          const version = ++requestVersionRef.current;
          const current = params.current || 1;
          const size = params.pageSize || 20;
          const field = Object.keys(sort || {})[0] as BankOwnerMismatchRequest['sort_field'];
          const order = field ? sort[field] : undefined;
          const requestSort = { sort_field: field, sort_order: order === 'ascend' || order === 'descend' ? order : undefined };
          sortRef.current = requestSort;
          const pending = pendingCacheRef.current;
          pendingCacheRef.current = null;
          if (pending && current === 1 && size === pending.pageSize && field === pending.filter.sort_field && order === pending.filter.sort_order) {
            return { data: pending.items, total: pending.total, success: true };
          }
          const filter = filterRef.current;
          if (filter === null) return { data: [], total: 0, success: true };
          setQueryStatus('loading');
          try {
            const result = await queryBankOwnerMismatch({ ...filter, ...requestSort, page: current, page_size: size });
            if (version !== requestVersionRef.current) return { data: [], total: 0, success: true };
            setQueryStatus('success');
            if (current === 1 && username) saveCache(cacheKey, { ...filter, ...requestSort }, result.items, result.total, 1, size);
            return { data: result.items, total: result.total, success: true };
          } catch {
            if (version === requestVersionRef.current) setQueryStatus('error');
            return { data: [], total: 0, success: false };
          }
        }}
      />
    </PageContainer>
  );
}
