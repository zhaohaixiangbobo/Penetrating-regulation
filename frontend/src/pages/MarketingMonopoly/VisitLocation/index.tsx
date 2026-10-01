/** 拜访定位偏差页面：拜访签到位置与许可证经营位置比较，支持筛选及导出。 */
import IssuingOrgTag, { shortOrganization } from '@/components/IssuingOrgTag';
import { useEffect, useRef, useState } from 'react';
import { useModel } from '@umijs/max';
import { PageContainer, ProTable, QueryFilter } from '@ant-design/pro-components';
import type { ActionType, ProColumns, ProFormInstance } from '@ant-design/pro-components';
import { Alert, Button, DatePicker, Divider, Form, Input, message, Select } from 'antd';
import { DownloadOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import { exportVisitLocation, listIssuingOrganizations, queryVisitLocation } from '@/services/marketingMonopoly';
import type { VisitLocationRequest, VisitLocationRow, IssuingOrganization } from '@/services/marketingMonopoly';
import { loadCache, saveCache } from '@/utils/queryCache';
import { exportToExcel } from '@/utils/exportExcel';

const exportColumns = [
  { title: '发证机关', dataIndex: 'issue_org_name' },
  { title: '客户经理', dataIndex: 'person_name' },
  { title: '拜访日期', dataIndex: 'plan_date' },
  { title: '许可证号', dataIndex: 'cust_code' },
  { title: '客户名称', dataIndex: 'cust_name' },
  { title: '经营地址经度', dataIndex: 'longitude' },
  { title: '经营地址纬度', dataIndex: 'latitude' },
  { title: '签到经度', dataIndex: 'gis_long' },
  { title: '签到纬度', dataIndex: 'gis_lat' },
  { title: '距离（米）', dataIndex: 'distance_meters' },
];

export default function VisitLocationPage() {
  const { initialState } = useModel('@@initialState');
  const username = initialState?.currentUser?.username;
  const cacheKey = `shenji_visit_location_v1:${encodeURIComponent(username || '')}`;
  const [cache] = useState(() => username ? loadCache<VisitLocationRequest, VisitLocationRow>(cacheKey) : null);
  // null 表示尚未查询；空对象表示用户明确提交“全部”条件。
  const filterRef = useRef<VisitLocationRequest | null>(cache?.filter || null);
  const pendingCacheRef = useRef(cache);
  const sortRef = useRef<Pick<VisitLocationRequest, 'sort_field' | 'sort_order'>>({
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
  // 快捷日期以点击当天计算，后端统一验证业务起始日期。
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

  const columns: ProColumns<VisitLocationRow>[] = [
    { title: '发证机关', dataIndex: 'issue_org_name', width: 100, sorter: true, render: (_: unknown, row: VisitLocationRow) => <IssuingOrgTag name={row.issue_org_name} /> },
    { title: '客户经理', dataIndex: 'person_name', width: 85, ellipsis: true },
    { title: '拜访日期', dataIndex: 'plan_date', width: 110, sorter: true },
    { title: '许可证号', dataIndex: 'cust_code', width: 125 },
    { title: '客户名称', dataIndex: 'cust_name', width: 160, ellipsis: true },
    // 同一位置的经纬度分两行显示，保留原始精度并减少横向占用。
    { title: '经营位置（经/纬）', key: 'license_position', width: 125,
      render: (_: unknown, row: VisitLocationRow) => <div><div>经 {row.longitude}</div><div>纬 {row.latitude}</div></div> },
    { title: '签到位置（经/纬）', key: 'visit_position', width: 125,
      render: (_: unknown, row: VisitLocationRow) => <div><div>经 {row.gis_long}</div><div>纬 {row.gis_lat}</div></div> },
    { title: '距离（米）', dataIndex: 'distance_meters', width: 105, fixed: 'right' as const, sorter: true, render: (_: unknown, row: VisitLocationRow) => row.distance_meters.toFixed(2) },
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
      const rows = await exportVisitLocation({ ...filter, ...sortRef.current });
      if (!rows.length) {
        message.info('当前筛选条件下无数据可导出');
        return;
      }
      const range = filter.start_date ? `${filter.start_date}_${filter.end_date}` : '全部拜访日期';
      exportToExcel(`拜访定位偏差_${range}_${dayjs().format('YYYYMMDD_HHmmss')}`, exportColumns, rows);
      if (rows.length >= 100000) message.warning('已导出 100000 条，达到导出上限；请缩小筛选范围继续导出');
      else message.success(`已导出 ${rows.length} 条记录`);
    } catch { /* 统一请求处理器展示失败原因。 */ }
    finally { setExporting(false); }
  };

  return (
    <PageContainer header={{ title: '拜访定位偏差', subTitle: '客户经理有效拜访签到位置与许可证经营地址的距离超过设定阈值' }}>
      <QueryFilter
        formRef={formRef} layout="horizontal" defaultCollapsed={false}
        initialValues={{
          issue_org_codes: cache?.filter.issue_org_codes,
          lic_no: cache?.filter.lic_no,
          company_name: cache?.filter.company_name,
          distance_meters: cache?.filter.distance_meters || 200,
          range: cache?.filter.start_date && cache?.filter.end_date ? [dayjs(cache.filter.start_date), dayjs(cache.filter.end_date)] : [dayjs().subtract(1, 'month'), dayjs()],
        }}
        onFinish={async (values) => {
          requestVersionRef.current += 1;
          const [start, end] = values.range || [];
          filterRef.current = {
            issue_org_codes: values.issue_org_codes || [],
            distance_meters: values.distance_meters || 200,
            lic_no: values.lic_no?.trim() || undefined,
            company_name: values.company_name?.trim() || undefined,
            start_date: dayjs(start).format('YYYY-MM-DD'),
            end_date: dayjs(end).format('YYYY-MM-DD'),
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
          formRef.current?.setFieldsValue({ issue_org_codes: [], lic_no: undefined, company_name: undefined, distance_meters: 200, range: [dayjs().subtract(1, 'month'), dayjs()] });
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
        <Form.Item name="distance_meters" label="距离超过（米）"><Select options={[100, 150, 200, 250, 300, 500].map((value) => ({ label: `${value} 米`, value }))} /></Form.Item>
        <Form.Item name="range" label="拜访日期" rules={[{ required: true, message: '请选择拜访日期' }]}><DatePicker.RangePicker format="YYYY-MM-DD" presets={presets} allowClear={false} disabledDate={(date) => date.isBefore(dayjs('2024-01-01'), 'day')}  style={{ width: '100%' }} /></Form.Item>
      </QueryFilter>
      {queryStatus === 'error' && <Alert style={{ marginBottom: 16 }} type="error" showIcon message="查询失败，请检查错误提示后重新查询。" />}
      <ProTable<VisitLocationRow>
        actionRef={actionRef} columns={columns} search={false} size="small" tableLayout="fixed" scroll={{ x: 925 }}
        locale={{ emptyText: queryStatus === 'idle' ? '请设置拜访日期和距离阈值后点击查询' : queryStatus === 'error' ? '查询失败，请重试' : queryStatus === 'loading' ? '正在查询，请稍候' : '暂未查到符合条件的数据，请调整筛选条件后重试' }}
        rowKey={(row) => JSON.stringify([row.visit_id, row.retailer_uuid, row.person_name, row.plan_date])}
        pagination={{ pageSize, showSizeChanger: true, onChange: (_, size) => setPageSize(size), showTotal: (total, range) => `第 ${range[0]}-${range[1]} 条/总共 ${total} 条` }}
        toolBarRender={() => [<Button key="export" icon={<DownloadOutlined />} loading={exporting} onClick={handleExport}>导出 Excel</Button>]}
        request={async (params, sort) => {
          const version = ++requestVersionRef.current;
          const current = params.current || 1;
          const size = params.pageSize || 20;
          const field = Object.keys(sort || {})[0] as VisitLocationRequest['sort_field'];
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
            const result = await queryVisitLocation({ ...filter, ...requestSort, page: current, page_size: size });
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
