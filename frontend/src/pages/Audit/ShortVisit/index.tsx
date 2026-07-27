import { useEffect, useRef, useState } from 'react';
import { PageContainer, ProTable, QueryFilter } from '@ant-design/pro-components';
import type { ActionType, ProColumns, ProFormInstance } from '@ant-design/pro-components';
import { Button, DatePicker, Form, message, Select, Tag } from 'antd';
import { DownloadOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import CompanySelect from '@/components/CompanySelect';
import { queryShortVisit, exportShortVisit, ShortVisitRow } from '@/services/audit';
import { listEmployees, EmployeeGroup } from '@/services/auth';
import { loadCache, saveCache } from '@/utils/queryCache';
import { getCompanyTagColor } from '@/utils/companyColor';
import { exportToExcel } from '@/utils/exportExcel';

const MIN_DATE = dayjs('2024-01-01');
const CACHE_KEY = 'shenji_sv';

const DATE_PRESETS = [
  { label: '今天', value: [dayjs(), dayjs()] as [dayjs.Dayjs, dayjs.Dayjs] },
  { label: '过去一个月', value: [dayjs().subtract(1, 'month'), dayjs()] as [dayjs.Dayjs, dayjs.Dayjs] },
  { label: '过去一年', value: [dayjs().subtract(1, 'year'), dayjs()] as [dayjs.Dayjs, dayjs.Dayjs] },
];

interface Filter {
  com_ids?: string[];
  start_date?: string;
  end_date?: string;
  sdpt_name?: string;   // 仅前端联动筛选，不传后端
  person_name?: string;
}

export default function ShortVisitPage() {
  const actionRef = useRef<ActionType>();
  const formRef = useRef<ProFormInstance>();
  const filterRef = useRef<Filter>({});
  // 缓存引用：首次加载时使用，使用后清空
  const pendingCacheRef = useRef<{ items: ShortVisitRow[]; total: number } | null>(null);

  const [employeeGroups, setEmployeeGroups] = useState<EmployeeGroup[]>([]);
  const [loadingEmp, setLoadingEmp] = useState(false);
  const [selectedDept, setSelectedDept] = useState<string | undefined>();
  const [exporting, setExporting] = useState(false);

  // 挂载时恢复缓存
  useEffect(() => {
    const cache = loadCache<Filter, ShortVisitRow>(CACHE_KEY);
    if (cache?.filter?.com_ids?.length && cache.filter.start_date) {
      filterRef.current = cache.filter;
      pendingCacheRef.current = { items: cache.items, total: cache.total };

      // 加载对应公司的员工列表后再恢复表单
      listEmployees(cache.filter.com_ids)
        .then((groups) => {
          setEmployeeGroups(groups);
          setSelectedDept(cache.filter.sdpt_name);
          setTimeout(() => {
            formRef.current?.setFieldsValue({
              com_ids: cache.filter.com_ids,
              range: [dayjs(cache.filter.start_date), dayjs(cache.filter.end_date)],
              sdpt_name: cache.filter.sdpt_name,
              person_name: cache.filter.person_name,
            });
            actionRef.current?.reload();
          }, 100);
        })
        .catch(() => {
          setTimeout(() => {
            formRef.current?.setFieldsValue({
              com_ids: cache.filter.com_ids,
              range: [dayjs(cache.filter.start_date), dayjs(cache.filter.end_date)],
            });
            actionRef.current?.reload();
          }, 100);
        });
    }
  }, []);

  const handleComIdsChange = async (comIds: string[]) => {
    if (!comIds?.length) {
      setEmployeeGroups([]);
      setSelectedDept(undefined);
      formRef.current?.setFieldsValue({ sdpt_name: undefined, person_name: undefined });
      return;
    }
    setLoadingEmp(true);
    try {
      const groups = await listEmployees(comIds);
      setEmployeeGroups(groups);
    } catch {
      setEmployeeGroups([]);
    } finally {
      setLoadingEmp(false);
    }
    setSelectedDept(undefined);
    formRef.current?.setFieldsValue({ sdpt_name: undefined, person_name: undefined });
  };

  const deptOptions = employeeGroups.map((g) => ({ label: g.sdpt_name, value: g.sdpt_name }));

  const personOptions = selectedDept
    ? (employeeGroups.find((g) => g.sdpt_name === selectedDept)?.members ?? []).map((m) => ({
      label: m.person_name,
      value: m.person_name,
    }))
    : employeeGroups.flatMap((g) =>
      g.members.map((m) => ({ label: m.person_name, value: m.person_name })),
    );

  const handleExport = async () => {
    const { com_ids, start_date, end_date, person_name } = filterRef.current;
    if (!com_ids?.length || !start_date || !end_date) {
      message.warning('请先选择公司和日期范围并查询后再导出');
      return;
    }
    setExporting(true);
    try {
      const rows = await exportShortVisit({ com_ids, start_date, end_date, person_name });
      if (!rows?.length) {
        message.info('当前筛选条件下无数据可导出');
        return;
      }
      exportToExcel(
        `短拜访记录_${start_date}_${end_date}`,
        [
          { title: '公司', dataIndex: 'short_name' },
          { title: '许可证号', dataIndex: 'license_code' },
          { title: '客户名称', dataIndex: 'cust_name' },
          { title: '营业部', dataIndex: 'sdpt_name' },
          { title: '客户经理', dataIndex: 'person_name' },
          { title: '拜访日期', dataIndex: 'plan_date' },
          { title: '拜访时长(秒)', dataIndex: 'visit_time' },
        ],
        rows,
      );
      message.success(`已导出 ${rows.length} 条记录`);
    } catch {
      // errorHandler 已弹窗提示
    } finally {
      setExporting(false);
    }
  };

  const columns: ProColumns<ShortVisitRow>[] = [
    {
      title: '公司',
      dataIndex: 'short_name',
      width: 100,
      render: (_, r) =>
        r.short_name ? <Tag color={getCompanyTagColor(r.short_name)}>{r.short_name}</Tag> : '-',
    },
    { title: '许可证号', dataIndex: 'license_code', width: 150, copyable: true },
    { title: '客户名称', dataIndex: 'cust_name', width: 210, ellipsis: true },
    { title: '营业部', dataIndex: 'sdpt_name', width: 200, ellipsis: true },
    { title: '客户经理', dataIndex: 'person_name', width: 90 },
    {
      title: '拜访日期',
      dataIndex: 'plan_date',
      width: 125,
      sorter: true,
      render: (_, r) => r.plan_date || '-',
    },
    {
      title: '拜访时长(秒)',
      dataIndex: 'visit_time',
      width: 115,
      sorter: true,
      render: (_, r) => (r.visit_time ?? '-'),
    },
  ];

  return (
    <PageContainer
      header={{
        title: '功能1 · 短拜访记录 (< 1 分钟)',
        subTitle: '营销系统拜访记录不到 1 分钟但状态正常的零售户',
      }}
    >
      <QueryFilter
        formRef={formRef}
        layout="horizontal"
        onFinish={async (v) => {
          const [s, e] = v.range || [];
          filterRef.current = {
            com_ids: v.com_ids,
            start_date: s ? dayjs(s).format('YYYY-MM-DD') : undefined,
            end_date: e ? dayjs(e).format('YYYY-MM-DD') : undefined,
            sdpt_name: v.sdpt_name || undefined,
            person_name: v.person_name || undefined,
          };
          pendingCacheRef.current = null; // 主动查询时跳过缓存
          actionRef.current?.reload();
        }}
        submitter={{ searchConfig: { submitText: '查询', resetText: '重置' } }}
      >
        <Form.Item name="com_ids" label="公司" rules={[{ required: true, message: '请选择公司' }]}>
          <CompanySelect
            mode="multiple"
            onChange={(_val) => handleComIdsChange(_val as string[])}
          />
        </Form.Item>
        <Form.Item name="range" label="拜访日期" rules={[{ required: true, message: '请选择日期范围' }]}>
          <DatePicker.RangePicker
            format="YYYY-MM-DD"
            presets={DATE_PRESETS}
            disabledDate={(d) => !!d && d.isBefore(MIN_DATE, 'day')}
            style={{ width: '100%' }}
          />
        </Form.Item>
        <Form.Item name="sdpt_name" label="营业部">
          <Select
            placeholder="全部营业部"
            allowClear
            showSearch
            optionFilterProp="label"
            loading={loadingEmp}
            options={deptOptions}
            style={{ minWidth: 180 }}
            onChange={(val: string | undefined) => {
              setSelectedDept(val);
              formRef.current?.setFieldsValue({ person_name: undefined });
            }}
          />
        </Form.Item>
        <Form.Item name="person_name" label="客户经理">
          <Select
            placeholder="全部客户经理"
            allowClear
            showSearch
            optionFilterProp="label"
            options={personOptions}
            style={{ minWidth: 160 }}
          />
        </Form.Item>
      </QueryFilter>

      <ProTable<ShortVisitRow>
        actionRef={actionRef}
        columns={columns}
        rowKey={(r, idx) => `${r.license_code || ''}-${r.plan_date || ''}-${idx}`}
        search={false}
        toolBarRender={() => [
          <Button
            key="export"
            icon={<DownloadOutlined />}
            loading={exporting}
            onClick={handleExport}
          >
            导出 Excel
          </Button>,
        ]}
        loading={{ spinning: false }}
        scroll={{ x: 'max-content' }}
        pagination={{
          defaultPageSize: 20,
          showSizeChanger: true,
          showTotal: (total, range) => `第 ${range[0]}-${range[1]} 条/总共 ${total} 条`,
        }}
        request={async (p, sort) => {
          // 缓存恢复优先：切换回来时直接返回缓存数据
          if (pendingCacheRef.current) {
            const cached = pendingCacheRef.current;
            pendingCacheRef.current = null;
            console.log('[ShortVisit] 返回缓存', cached.items.length, '条');
            return { data: cached.items, total: cached.total, success: true };
          }

          const { com_ids, start_date, end_date, sdpt_name, person_name } = filterRef.current;
          if (!com_ids?.length || !start_date || !end_date) return { data: [], success: true, total: 0 };

          // 提取排序字段与方向（ProTable 传入的 sort 形如 { plan_date: 'descend' }）
          const sortField = Object.keys(sort || {})[0] as 'plan_date' | 'visit_time' | undefined;
          const sortOrder = sortField ? ((sort as Record<string, string>)[sortField] as 'ascend' | 'descend') : undefined;

          try {
            const res = await queryShortVisit({
              com_ids,
              start_date,
              end_date,
              person_name,
              sort_field: sortField,
              sort_order: sortOrder,
              page: p.current || 1,
              page_size: p.pageSize || 20,
            });
            console.log('[ShortVisit] response:', res);

            // 保存第 1 页到缓存
            if ((p.current || 1) === 1) {
              saveCache(CACHE_KEY, { com_ids, start_date, end_date, sdpt_name, person_name }, res.items, res.total, 1, p.pageSize || 20);
            }
            return { data: res.items, total: res.total, success: true };
          } catch (err) {
            console.error('[ShortVisit] request failed:', err);
            return { data: [], success: false, total: 0 };
          }
        }}
      />
    </PageContainer>
  );
}
