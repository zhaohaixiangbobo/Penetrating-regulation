/** 审计查询共用页面：人员联动、可选时长阈值、分页排序、用户缓存和 Excel 导出。 */
import { useEffect, useRef, useState } from 'react';
import { useModel } from '@umijs/max';
import { PageContainer, ProTable, QueryFilter } from '@ant-design/pro-components';
import type { ActionType, ProColumns, ProFormInstance } from '@ant-design/pro-components';
import { Button, DatePicker, Form, message, Select } from 'antd';
import { DownloadOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import CompanySelect from '@/components/CompanySelect';
import { listEmployees } from '@/services/auth';
import type { EmployeeGroup } from '@/services/auth';
import type { Paged } from '@/services/audit';
import { loadCache, saveCache } from '@/utils/queryCache';
import { exportToExcel } from '@/utils/exportExcel';
import type { ExportColumn } from '@/utils/exportExcel';

export interface AuditPageRequest {
  com_ids: string[];
  start_date?: string;
  end_date?: string;
  start_month?: string;
  end_month?: string;
  sdpt_name?: string;
  person_uuid?: string;
  threshold_minutes?: number;
  threshold_seconds?: number;
  sort_field?: string;
  sort_order?: 'ascend' | 'descend';
  page?: number;
  page_size?: number;
}

interface Props<T extends object> {
  title: string;
  description: string;
  cacheKey: string;
  timeMode: 'date' | 'month';
  minTime: string;
  columns: ProColumns<T>[];
  exportColumns: ExportColumn[];
  rowKey: (row: T, index?: number) => string;
  query: (payload: AuditPageRequest) => Promise<Paged<T>>;
  exportQuery: (payload: AuditPageRequest) => Promise<T[]>;
  formatExport?: (row: T) => object;
  /** 时长型查询按业务配置阈值，单位和参数名同步声明。 */
  durationThreshold?: {
    field: 'threshold_minutes' | 'threshold_seconds';
    label: string;
    unit: '分钟' | '秒';
    options: number[];
    defaultValue: number;
  };
}

export default function AuditQueryPage<T extends object>(props: Props<T>) {
  const threshold = props.durationThreshold;
  const defaultThreshold = threshold ? { [threshold.field]: threshold.defaultValue } : {};
  const { initialState } = useModel('@@initialState');
  const username = initialState?.currentUser?.username;
  // 缓存属于当前用户和当前查询版本，切换账号后使用独立的缓存空间。
  const storageKey = `${props.cacheKey}:${encodeURIComponent(username || '')}`;
  const [cache] = useState(() => username ? loadCache<AuditPageRequest, T>(storageKey) : null);
  const filterRef = useRef<AuditPageRequest>({ com_ids: [], ...defaultThreshold, ...cache?.filter });
  const pendingCacheRef = useRef(cache);
  const sortRef = useRef<Pick<AuditPageRequest, 'sort_field' | 'sort_order'>>({
    sort_field: cache?.filter.sort_field, sort_order: cache?.filter.sort_order,
  });
  const actionRef = useRef<ActionType>();
  const formRef = useRef<ProFormInstance>();
  const employeeRequestRef = useRef(0);
  const queryVersionRef = useRef(0);
  const [groups, setGroups] = useState<EmployeeGroup[]>([]);
  const [selectedDept, setSelectedDept] = useState<string | undefined>(cache?.filter.sdpt_name);
  const [loadingEmployees, setLoadingEmployees] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [pageSize, setPageSize] = useState(cache?.pageSize || 20);
  const isMonth = props.timeMode === 'month';
  const minimum = dayjs(props.minTime);
  const lastMonth = dayjs().subtract(1, 'month').startOf('month');
  const cachedStart = isMonth ? cache?.filter.start_month : cache?.filter.start_date;
  const cachedEnd = isMonth ? cache?.filter.end_month : cache?.filter.end_date;
  const initialValues = {
    com_ids: cache?.filter.com_ids,
    range: cachedStart && cachedEnd ? [dayjs(cachedStart), dayjs(cachedEnd)] : isMonth ? [lastMonth, lastMonth] : undefined,
    sdpt_name: cache?.filter.sdpt_name,
    person_uuid: cache?.filter.person_uuid,
    ...(threshold ? { [threshold.field]: cache?.filter[threshold.field] ?? threshold.defaultValue } : {}),
  };

  // 序号确保快速切换公司时，仅最后一次字典请求生效。
  const loadEmployees = async (comIds: string[]) => {
    const requestId = ++employeeRequestRef.current;
    if (!comIds.length) {
      setGroups([]);
      setLoadingEmployees(false);
      return;
    }
    setLoadingEmployees(true);
    try {
      const result = await listEmployees(comIds);
      if (requestId === employeeRequestRef.current) setGroups(result);
    } catch {
      if (requestId === employeeRequestRef.current) setGroups([]);
    } finally {
      if (requestId === employeeRequestRef.current) setLoadingEmployees(false);
    }
  };

  useEffect(() => {
    if (cache?.filter.com_ids.length) void loadEmployees(cache.filter.com_ids);
    return () => { employeeRequestRef.current += 1; };
  }, []);

  const removeCache = () => {
    try { localStorage.removeItem(storageKey); } catch { /* 存储受限时仍可正常查询。 */ }
  };
  const presets = isMonth
    ? [1, 3, 6, 12].map((months) => ({
      label: months === 1 ? '上月' : `最近${months}个月`,
      value: [dayjs().subtract(months, 'month').startOf('month'), lastMonth] as [dayjs.Dayjs, dayjs.Dayjs],
    }))
    : [
      { label: '今天', value: [dayjs(), dayjs()] as [dayjs.Dayjs, dayjs.Dayjs] },
      { label: '过去一个月', value: [dayjs().subtract(1, 'month'), dayjs()] as [dayjs.Dayjs, dayjs.Dayjs] },
      { label: '过去一年', value: [dayjs().subtract(1, 'year'), dayjs()] as [dayjs.Dayjs, dayjs.Dayjs] },
    ];
  const departmentGroups = selectedDept ? groups.filter((g) => g.sdpt_name === selectedDept) : groups;
  const people = new Map(departmentGroups.flatMap((g) => g.members.map((m) => [m.person_uuid, m] as const)));
  const columns = props.columns.map((column) => ({
    ...column,
    defaultSortOrder: column.dataIndex === cache?.filter.sort_field ? cache?.filter.sort_order : undefined,
  }));

  const handleExport = async () => {
    const filter = filterRef.current;
    if (!filter.com_ids.length || !(filter.start_date || filter.start_month)) {
      message.warning('请先选择公司和时间范围并查询后再导出');
      return;
    }
    setExporting(true);
    try {
      const rows = await props.exportQuery({ ...filter, ...sortRef.current });
      if (!rows.length) {
        message.info('当前筛选条件下无数据可导出');
        return;
      }
      const start = (filter.start_date || filter.start_month || '').slice(0, isMonth ? 7 : 10);
      const end = (filter.end_date || filter.end_month || '').slice(0, isMonth ? 7 : 10);
      // 文件名记录已提交阈值，便于区分同一时间范围的不同筛选结果。
      const thresholdLabel = threshold ? `_${filter[threshold.field]}${threshold.unit}` : '';
      exportToExcel(`${props.title}_${start}_${end}${thresholdLabel}`, props.exportColumns, rows.map((row) => props.formatExport ? props.formatExport(row) : row));
      if (rows.length >= 100000) message.warning('已导出 100000 条，达到导出上限；可缩小查询范围继续导出');
      else message.success(`已导出 ${rows.length} 条记录`);
    } catch { /* 统一 request 错误处理器展示失败原因。 */ }
    finally { setExporting(false); }
  };

  return (
    <PageContainer header={{ title: props.title, subTitle: props.description }}>
      <QueryFilter
        formRef={formRef}
        layout="horizontal"
        initialValues={initialValues}
        onFinish={async (values) => {
          queryVersionRef.current += 1;
          const [start, end] = values.range;
          filterRef.current = {
            com_ids: values.com_ids,
            sdpt_name: values.sdpt_name || undefined,
            person_uuid: values.person_uuid || undefined,
            ...(threshold ? { [threshold.field]: values[threshold.field] ?? threshold.defaultValue } : {}),
            ...(isMonth
              ? { start_month: dayjs(start).startOf('month').format('YYYY-MM-DD'), end_month: dayjs(end).startOf('month').format('YYYY-MM-DD') }
              : { start_date: dayjs(start).format('YYYY-MM-DD'), end_date: dayjs(end).format('YYYY-MM-DD') }),
          };
          pendingCacheRef.current = null;
          removeCache();
          actionRef.current?.reload(true);
        }}
        onReset={() => {
          queryVersionRef.current += 1;
          filterRef.current = { com_ids: [], ...defaultThreshold };
          pendingCacheRef.current = null;
          removeCache();
          setSelectedDept(undefined);
          void loadEmployees([]);
          // 原缓存不作为重置默认值，重置后的表单和已提交条件同步清空。
          formRef.current?.setFieldsValue({ com_ids: [], sdpt_name: undefined, person_uuid: undefined, range: isMonth ? [lastMonth, lastMonth] : undefined, ...defaultThreshold });
          actionRef.current?.reload(true);
        }}
        submitter={{ searchConfig: { submitText: '查询', resetText: '重置' } }}
      >
        <Form.Item name="com_ids" label="公司" rules={[{ required: true, message: '请选择公司' }]}>
          <CompanySelect mode="multiple" onChange={(value) => {
            const ids = Array.isArray(value) ? value : value ? [value] : [];
            setSelectedDept(undefined);
            formRef.current?.setFieldsValue({ sdpt_name: undefined, person_uuid: undefined });
            void loadEmployees(ids);
          }} />
        </Form.Item>
        <Form.Item name="range" label={isMonth ? '月份范围' : '拜访日期'} rules={[{ required: true, message: '请选择时间范围' }]}>
          <DatePicker.RangePicker picker={isMonth ? 'month' : 'date'} format={isMonth ? 'YYYY-MM' : 'YYYY-MM-DD'} presets={presets}
            disabledDate={(value) => !!value && value.isBefore(minimum, isMonth ? 'month' : 'day')} style={{ width: '100%' }} />
        </Form.Item>
        {threshold && <Form.Item name={threshold.field} label={threshold.label} rules={[{ required: true, message: '请选择时长阈值' }]}>
          <Select style={{ minWidth: 140 }} options={threshold.options.map((value) => ({ label: `${value}${threshold.unit}`, value }))} />
        </Form.Item>}
        <Form.Item name="sdpt_name" label="营业部">
          <Select placeholder="全部营业部" allowClear showSearch optionFilterProp="label" loading={loadingEmployees}
            options={groups.map((g) => ({ label: g.sdpt_name, value: g.sdpt_name }))} style={{ minWidth: 180 }}
            onChange={(value) => { setSelectedDept(value); formRef.current?.setFieldsValue({ person_uuid: undefined }); }} />
        </Form.Item>
        <Form.Item name="person_uuid" label="客户经理">
          <Select placeholder="全部客户经理" allowClear showSearch optionFilterProp="label" style={{ minWidth: 160 }}
            options={Array.from(people.values()).map((m) => ({ label: m.person_name, value: m.person_uuid }))} />
        </Form.Item>
      </QueryFilter>
      <ProTable<T>
        locale={{ emptyText: '暂未查到符合条件的数据，请调整筛选条件后查询' }}
        actionRef={actionRef} columns={columns} rowKey={props.rowKey} search={false} scroll={{ x: 'max-content' }}
        pagination={{ pageSize, showSizeChanger: true, onChange: (_, size) => setPageSize(size),
          showTotal: (total, range) => `第 ${range[0]}-${range[1]} 条/总共 ${total} 条` }}
        toolBarRender={() => [<Button key="export" icon={<DownloadOutlined />} loading={exporting} onClick={handleExport}>导出 Excel</Button>]}
        request={async (params, sort) => {
          const current = params.current || 1;
          const size = params.pageSize || 20;
          const field = Object.keys(sort || {})[0];
          const order = field ? sort[field] : undefined;
          sortRef.current = { sort_field: field, sort_order: order === 'ascend' || order === 'descend' ? order : undefined };
          const pending = pendingCacheRef.current;
          pendingCacheRef.current = null;
          // 恢复时校验排序与每页条数，确保缓存数据对应表格状态。
          if (pending && current === 1 && size === pending.pageSize && field === pending.filter.sort_field && sortRef.current.sort_order === pending.filter.sort_order) {
            return { data: pending.items, total: pending.total, success: true };
          }
          const filter = filterRef.current;
          if (!filter.com_ids.length || !(filter.start_date || filter.start_month)) return { data: [], total: 0, success: true };
          try {
            const queryVersion = queryVersionRef.current;
            const result = await props.query({ ...filter, ...sortRef.current, page: current, page_size: size });
            // 重置或重新提交后，较早请求的结果不再进入页面及缓存。
            if (queryVersion !== queryVersionRef.current) return { data: [], total: 0, success: true };
            if (current === 1 && username) saveCache(storageKey, { ...filter, ...sortRef.current }, result.items, result.total, 1, size);
            return { data: result.items, total: result.total, success: true };
          } catch { return { data: [], total: 0, success: false }; }
        }}
      />
    </PageContainer>
  );
}
