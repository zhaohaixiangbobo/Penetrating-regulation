import { useEffect, useRef, useState } from 'react';
import { PageContainer, ProTable, QueryFilter } from '@ant-design/pro-components';
import type { ActionType, ProColumns, ProFormInstance } from '@ant-design/pro-components';
import { Button, DatePicker, Form, message, Select, Tag } from 'antd';
import { DownloadOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import CompanySelect from '@/components/CompanySelect';
import { queryFullCustMiss, exportFullCustMiss, FullCustMissRow } from '@/services/audit';
import { listEmployees, EmployeeGroup } from '@/services/auth';
import { loadCache, saveCache } from '@/utils/queryCache';
import { getCompanyTagColor } from '@/utils/companyColor';
import { exportToExcel } from '@/utils/exportExcel';

const MIN_MONTH = dayjs('2025-09-01');
const CACHE_KEY = 'shenji_fcm_v2';

const DEFAULT_MONTH = dayjs().subtract(1, 'month').startOf('month').format('YYYY-MM-DD');

/** 'YYYYMM' -> 'YYYY-MM' */
const fmtMonth = (ym?: string | null) => (ym && ym.length >= 6 ? `${ym.slice(0, 4)}-${ym.slice(4)}` : '-');

interface Filter {
  com_ids?: string[];
  start_month?: string;
  end_month?: string;
  sdpt_name?: string;
  person_uuid?: string;
}

export default function FullCustMissPage() {
  const actionRef = useRef<ActionType>();
  const formRef = useRef<ProFormInstance>();
  const filterRef = useRef<Filter>({});
  // 缓存引用：首次加载时使用，使用后清空
  const pendingCacheRef = useRef<{ items: FullCustMissRow[]; total: number } | null>(null);

  const [employeeGroups, setEmployeeGroups] = useState<EmployeeGroup[]>([]);
  const [loadingEmp, setLoadingEmp] = useState(false);
  const [selectedDept, setSelectedDept] = useState<string | undefined>();
  const [exporting, setExporting] = useState(false);

  // 挂载时恢复缓存
  useEffect(() => {
    const cache = loadCache<Filter, FullCustMissRow>(CACHE_KEY);
    if (cache?.filter?.com_ids?.length && cache.filter.start_month) {
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
              month_range: [dayjs(cache.filter.start_month), dayjs(cache.filter.end_month)],
              sdpt_name: cache.filter.sdpt_name,
              person_uuid: cache.filter.person_uuid,
            });
            actionRef.current?.reload();
          }, 100);
        })
        .catch(() => {
          setTimeout(() => {
            formRef.current?.setFieldsValue({
              com_ids: cache.filter.com_ids,
              month_range: [dayjs(cache.filter.start_month), dayjs(cache.filter.end_month)],
            });
            actionRef.current?.reload();
          }, 100);
        });
    }
  }, []);

  // 公司变化时加载员工并按营业部分组
  const handleComIdsChange = async (value: string | string[]) => {
    const comIds = Array.isArray(value) ? value : value ? [value] : [];
    if (!comIds.length) {
      setEmployeeGroups([]);
      setSelectedDept(undefined);
      formRef.current?.setFieldsValue({ sdpt_name: undefined, person_uuid: undefined });
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
    formRef.current?.setFieldsValue({ sdpt_name: undefined, person_uuid: undefined });
  };

  const deptOptions = employeeGroups.map((g) => ({ label: g.sdpt_name, value: g.sdpt_name }));

  const personOptions = selectedDept
    ? (employeeGroups.find((g) => g.sdpt_name === selectedDept)?.members ?? []).map((m) => ({
      label: m.person_name,
      value: m.person_uuid,
    }))
    : employeeGroups.flatMap((g) =>
      g.members.map((m) => ({ label: m.person_name, value: m.person_uuid })),
    );

  const handleExport = async () => {
    const { com_ids, start_month, end_month, sdpt_name, person_uuid } = filterRef.current;
    if (!com_ids?.length || !start_month || !end_month) {
      message.warning('请先选择公司和月份范围并查询后再导出');
      return;
    }
    setExporting(true);
    try {
      const rows = await exportFullCustMiss({ com_ids, start_month, end_month, sdpt_name, person_uuid });
      if (!rows?.length) {
        message.info('当前筛选条件下无数据可导出');
        return;
      }
      exportToExcel(
        `全商品缺访客户_${start_month.slice(0, 7)}_${end_month.slice(0, 7)}`,
        [
          { title: '月份', dataIndex: 'year_month' },
          { title: '公司', dataIndex: 'short_name' },
          { title: '营业部', dataIndex: 'sdpt_name' },
          { title: '客户经理', dataIndex: 'person_name' },
          { title: '客户编码', dataIndex: 'cust_code' },
          { title: '客户名称', dataIndex: 'cust_name' },
        ],
        rows.map((r) => ({ ...r, year_month: fmtMonth(r.year_month) })),
      );
      message.success(`已导出 ${rows.length} 条记录`);
    } catch {
      // errorHandler 已弹窗提示
    } finally {
      setExporting(false);
    }
  };

  const columns: ProColumns<FullCustMissRow>[] = [
    {
      title: '月份',
      dataIndex: 'year_month',
      width: 110,
      sorter: true,
      render: (_, r) => fmtMonth(r.year_month),
    },
    {
      title: '公司',
      dataIndex: 'short_name',
      width: 100,
      render: (_, r) =>
        r.short_name ? <Tag color={getCompanyTagColor(r.short_name)}>{r.short_name}</Tag> : '-',
    },
    { title: '营业部', dataIndex: 'sdpt_name', width: 200, ellipsis: true },
    { title: '客户经理', dataIndex: 'person_name', width: 100 },
    { title: '客户编码', dataIndex: 'cust_code', width: 150, copyable: true },
    { title: '客户名称', dataIndex: 'cust_name', width: 230, ellipsis: true },
  ];

  return (
    <PageContainer
      header={{
        title: '功能2 · 全商品客户当月无拜访',
        subTitle: '全商品客户在评价生效月份内无任何有效拜访的记录',
      }}
    >
      <QueryFilter
        formRef={formRef}
        layout="horizontal"
        onFinish={async (values: any) => {
          const [start, end] = values.month_range || [];
          filterRef.current = {
            com_ids: values.com_ids ?? [],
            start_month: start ? dayjs(start).format('YYYY-MM-DD') : undefined,
            end_month: end ? dayjs(end).format('YYYY-MM-DD') : undefined,
            sdpt_name: values.sdpt_name || undefined,
            person_uuid: values.person_uuid || undefined,
          };
          pendingCacheRef.current = null;
          actionRef.current?.reload();
        }}
        submitter={{ searchConfig: { submitText: '查询', resetText: '重置' } }}
      >
        <Form.Item name="com_ids" label="公司" rules={[{ required: true, message: '请选择公司' }]}>
          <CompanySelect
            mode="multiple"
            onChange={handleComIdsChange}
          />
        </Form.Item>
        <Form.Item
          name="month_range"
          label="月份范围"
          rules={[{ required: true, message: '请选择月份范围' }]}
          initialValue={[dayjs(DEFAULT_MONTH), dayjs(DEFAULT_MONTH)]}
        >
          <DatePicker.RangePicker
            picker="month"
            format="YYYY-MM"
            style={{ width: '100%' }}
            disabledDate={(current) => current && current.isBefore(MIN_MONTH, 'month')}
            presets={[
              { label: '上月', value: [dayjs().subtract(1, 'month').startOf('month'), dayjs().subtract(1, 'month').startOf('month')] },
              { label: '最近3个月', value: [dayjs().subtract(3, 'month').startOf('month'), dayjs().subtract(1, 'month').startOf('month')] },
              { label: '最近6个月', value: [dayjs().subtract(6, 'month').startOf('month'), dayjs().subtract(1, 'month').startOf('month')] },
              { label: '最近12个月', value: [dayjs().subtract(12, 'month').startOf('month'), dayjs().subtract(1, 'month').startOf('month')] },
            ]}
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
              formRef.current?.setFieldsValue({ person_uuid: undefined });
            }}
          />
        </Form.Item>
        <Form.Item name="person_uuid" label="客户经理">
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

      <ProTable<FullCustMissRow>
        actionRef={actionRef}
        columns={columns}
        rowKey={(r, idx) => `${r.year_month || ''}-${r.cust_code || ''}-${idx}`}
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
            return { data: cached.items, total: cached.total, success: true };
          }

          const { com_ids, start_month, end_month, sdpt_name, person_uuid } = filterRef.current;
          if (!com_ids?.length || !start_month || !end_month) {
            return { data: [], success: true, total: 0 };
          }

          // 提取排序字段与方向（ProTable 传入的 sort 形如 { year_month: 'descend' }）
          const sortField = Object.keys(sort || {})[0] as 'year_month' | undefined;
          const sortOrder = sortField ? ((sort as Record<string, string>)[sortField] as 'ascend' | 'descend') : undefined;

          try {
            const res = await queryFullCustMiss({
              com_ids,
              start_month,
              end_month,
              sdpt_name,
              person_uuid,
              sort_field: sortField,
              sort_order: sortOrder,
              page: p.current || 1,
              page_size: p.pageSize || 20,
            });

            // 保存第 1 页到缓存
            if ((p.current || 1) === 1) {
              saveCache(CACHE_KEY, { com_ids, start_month, end_month, sdpt_name, person_uuid }, res.items, res.total, 1, p.pageSize || 20);
            }
            return { data: res.items, total: res.total, success: true };
          } catch (err) {
            console.error('[FullCustMiss] request failed:', err);
            return { data: [], success: false, total: 0 };
          }
        }}
      />
    </PageContainer>
  );
}
