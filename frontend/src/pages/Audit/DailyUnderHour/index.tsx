/** 审计查询页面：条件筛选、分页、空结果提示与导出。 */
import { useEffect, useRef, useState } from 'react';
import { PageContainer, ProTable } from '@ant-design/pro-components';
import type { ActionType, ProColumns, ProFormInstance } from '@ant-design/pro-components';
import { Button, DatePicker, Form, message, Select, Tag } from 'antd';
import { DownloadOutlined } from '@ant-design/icons';
import QueryFilter from '@/components/UnifiedQueryFilter';
import dayjs from 'dayjs';
import CompanySelect from '@/components/CompanySelect';
import { queryDailyUnderHour, exportDailyUnderHour, DailyUnderHourRow } from '@/services/audit';
import { listEmployees, EmployeeGroup } from '@/services/auth';
import { loadCache, saveCache } from '@/utils/queryCache';
import { getCompanyTagColor } from '@/utils/companyColor';
import { exportToExcel } from '@/utils/exportExcel';

const MIN_DATE = dayjs('2024-01-01');
const CACHE_KEY = 'shenji_duh';

// 拜访分钟数可选阈值，默认 60
const THRESHOLD_OPTIONS = [40, 50, 60, 70, 80, 90].map((n) => ({ label: `${n}分钟`, value: n }));

const DATE_PRESETS = [
    { label: '今天', value: [dayjs(), dayjs()] as [dayjs.Dayjs, dayjs.Dayjs] },
    { label: '过去一个月', value: [dayjs().subtract(1, 'month'), dayjs()] as [dayjs.Dayjs, dayjs.Dayjs] },
    { label: '过去一年', value: [dayjs().subtract(1, 'year'), dayjs()] as [dayjs.Dayjs, dayjs.Dayjs] },
];

interface Filter {
    com_ids?: string[];
    start_date?: string;
    end_date?: string;
    sdpt_name?: string;
    person_uuid?: string;
    threshold_minutes?: number;
}

export default function DailyUnderHourPage() {
    const actionRef = useRef<ActionType>();
    const formRef = useRef<ProFormInstance>();
    const filterRef = useRef<Filter>({});
    const pendingCacheRef = useRef<{ items: DailyUnderHourRow[]; total: number } | null>(null);

    const [employeeGroups, setEmployeeGroups] = useState<EmployeeGroup[]>([]);
    const [loadingEmp, setLoadingEmp] = useState(false);
    const [selectedDept, setSelectedDept] = useState<string | undefined>();
    const [exporting, setExporting] = useState(false);

    // 挂载时恢复缓存
    useEffect(() => {
        const cache = loadCache<Filter, DailyUnderHourRow>(CACHE_KEY);
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
                            person_uuid: cache.filter.person_uuid,
                            threshold_minutes: cache.filter.threshold_minutes ?? 60,
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
        const { com_ids, start_date, end_date, sdpt_name, person_uuid, threshold_minutes } = filterRef.current;
        if (!com_ids?.length || !start_date || !end_date) {
            message.warning('请先选择公司和日期范围并查询后再导出');
            return;
        }
        setExporting(true);
        try {
            const rows = await exportDailyUnderHour({ com_ids, start_date, end_date, sdpt_name, person_uuid, threshold_minutes });
            if (!rows?.length) {
                message.info('当前筛选条件下无数据可导出');
                return;
            }
            exportToExcel(
                `日拜访不足_${start_date}_${end_date}`,
                [
                    { title: '拜访日期', dataIndex: 'v_date' },
                    { title: '公司', dataIndex: 'short_name' },
                    { title: '营业部', dataIndex: 'sdpt_name' },
                    { title: '客户经理', dataIndex: 'person_name' },
                    { title: '拜访分钟数', dataIndex: 'visit_minutes' },
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

    const columns: ProColumns<DailyUnderHourRow>[] = [
        {
            title: '拜访日期',
            dataIndex: 'v_date',
            width: 125,
            sorter: true,
            render: (_, r) => r.v_date || '-',
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
        {
            title: '拜访分钟数',
            dataIndex: 'visit_minutes',
            width: 110,
            render: (_, r) => (r.visit_minutes == null ? '-' : r.visit_minutes.toFixed(2)),
        },
    ];

    return (
        <PageContainer
            header={{
                title: '功能3 · 客户经理日拜访不足',
                subTitle: '按工作日汇总客户经理拜访总时长不足情况',
            }}
        >
            <QueryFilter
                formRef={formRef}
                layout="horizontal"
                initialValues={{ threshold_minutes: 60 }}
                onFinish={async (v) => {
                    const [s, e] = v.range || [];
                    filterRef.current = {
                        com_ids: v.com_ids,
                        start_date: s ? dayjs(s).format('YYYY-MM-DD') : undefined,
                        end_date: e ? dayjs(e).format('YYYY-MM-DD') : undefined,
                        sdpt_name: v.sdpt_name || undefined,
                        person_uuid: v.person_uuid || undefined,
                        threshold_minutes: v.threshold_minutes ?? 60,
                    };
                    pendingCacheRef.current = null;
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
                <Form.Item name="threshold_minutes" label="拜访分钟数">
                    <Select options={THRESHOLD_OPTIONS} style={{ minWidth: 120 }} />
                </Form.Item>
            </QueryFilter>

            <ProTable<DailyUnderHourRow>
        locale={{ emptyText: '暂未查到符合条件的数据，请调整筛选条件后查询' }}
                actionRef={actionRef}
                columns={columns}
                rowKey={(r, idx) => `${r.v_date || ''}-${r.cust_manager_person_uuid || ''}-${idx}`}
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
                        console.log('[DailyUnderHour] 返回缓存', cached.items.length, '条');
                        return { data: cached.items, total: cached.total, success: true };
                    }

                    const { com_ids, start_date, end_date, sdpt_name, person_uuid, threshold_minutes } = filterRef.current;
                    if (!com_ids?.length || !start_date || !end_date) return { data: [], success: true, total: 0 };

                    // 提取排序字段与方向
                    const sortField = Object.keys(sort || {})[0] as 'v_date' | undefined;
                    const sortOrder = sortField ? ((sort as Record<string, string>)[sortField] as 'ascend' | 'descend') : undefined;

                    try {
                        const res = await queryDailyUnderHour({
                            com_ids,
                            start_date,
                            end_date,
                            sdpt_name,
                            person_uuid,
                            threshold_minutes,
                            sort_field: sortField,
                            sort_order: sortOrder,
                            page: p.current || 1,
                            page_size: p.pageSize || 20,
                        });
                        console.log('[DailyUnderHour] response:', res);
                        if ((p.current || 1) === 1) {
                            saveCache(CACHE_KEY, { com_ids, start_date, end_date, sdpt_name, person_uuid, threshold_minutes }, res.items, res.total, 1, p.pageSize || 20);
                        }
            return { data: res.items, total: res.total, success: true };
                    } catch (err) {
                        console.error('[DailyUnderHour] request failed:', err);
                        return { data: [], success: false, total: 0 };
                    }
                }}
            />
        </PageContainer>
    );
}
