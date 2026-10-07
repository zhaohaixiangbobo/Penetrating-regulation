/** 审计线索页面：统一展示业务编号，使用内部主键完成记录关联。 */
import { clueNumber } from '@/utils/clueNumber';
import { useRef, useState } from 'react';
import { PageContainer, ProTable, ProForm, ProFormSelect } from '@ant-design/pro-components';
import type { ActionType, ProColumns } from '@ant-design/pro-components';
import { Tag } from 'antd';
import QueryFilter from '@/components/UnifiedQueryFilter';
import CompanySelect from '@/components/CompanySelect';
import { getCompanyTagColor } from '@/utils/companyColor';
import { ClueRow, formatClueTime, listAllClues } from '@/services/feedback';
import ClueDetailDrawer, { statusColor } from '../components/ClueDetailDrawer';

interface QueryParams {
    status?: string;
    com_id?: string;
}

export default function FeedbackManagePage() {
    const actionRef = useRef<ActionType>();
    const [query, setQuery] = useState<QueryParams>({});
    const [detailId, setDetailId] = useState<number | undefined>();
    const [drawerOpen, setDrawerOpen] = useState(false);

    const openDetail = (id: number) => {
        setDetailId(id);
        setDrawerOpen(true);
    };

    const columns: ProColumns<ClueRow>[] = [
        { title: '线索编号', dataIndex: 'id', width: 145, render: (_, r) => clueNumber(r.id) },
        { title: '标题', dataIndex: 'title', width: 220, ellipsis: true },
        {
            title: '类型',
            dataIndex: 'category',
            width: 100,
            render: (_, r) => <Tag>{r.category}</Tag>,
        },
        {
            title: '关联公司',
            dataIndex: 'short_name',
            width: 100,
            render: (_, r) =>
                r.short_name ? <Tag color={getCompanyTagColor(r.short_name)}>{r.short_name}</Tag> : '-',
        },
        { title: '提交人', dataIndex: 'created_by', width: 110 },
        { title: '附件', dataIndex: 'attachment_count', width: 70 },
        {
            title: '状态',
            dataIndex: 'status',
            width: 90,
            render: (_, r) => <Tag color={statusColor(r.status)}>{r.status_label}</Tag>,
        },
        { title: '提交时间', dataIndex: 'created_at', width: 150, sorter: true, render: (_, r) => formatClueTime(r.created_at) },
        { title: '处理人', dataIndex: 'handled_by', width: 110, render: (_, r) => r.handled_by || '-' },
        {
            title: '操作',
            width: 90,
            fixed: 'right',
            render: (_, r) => <a onClick={() => openDetail(r.id)}>查看处理</a>,
        },
    ];

    return (
        <PageContainer header={{ title: '审计线索管理', subTitle: '查看并处理全部用户提交的审计线索' }}>
            <QueryFilter<QueryParams>
                onFinish={async (values) => {
                    setQuery(values);
                    actionRef.current?.reload();
                }}
                onReset={() => {
                    setQuery({});
                    actionRef.current?.reload();
                }}
            >
                <ProFormSelect
                    name="status"
                    label="状态"
                    valueEnum={{
                        pending: '待处理',
                        processing: '处理中',
                        done: '已处理',
                    }}
                    placeholder="全部状态"
                />
                <ProForm.Item name="com_id" label="关联公司">
                    <CompanySelect allowClear />
                </ProForm.Item>
            </QueryFilter>

            <ProTable<ClueRow>
                actionRef={actionRef}
                columns={columns}
                rowKey="id"
                search={false}
                scroll={{ x: 'max-content' }}
                pagination={{
                    defaultPageSize: 20,
                    showSizeChanger: true,
                    showTotal: (total, range) => `第 ${range[0]}-${range[1]} 条/总共 ${total} 条`,
                }}
                request={async (p, sort) => {
                    try {
                        const order = sort?.created_at === 'ascend' ? 'asc' : 'desc';
                        const res = await listAllClues({
                            ...query,
                            order,
                            page: p.current || 1,
                            page_size: p.pageSize || 20,
                        });
                        return { data: res.items, total: res.total, success: true };
                    } catch {
                        return { data: [], total: 0, success: false };
                    }
                }}
            />

            <ClueDetailDrawer
                clueId={detailId}
                open={drawerOpen}
                onClose={() => setDrawerOpen(false)}
                canHandle
                onHandled={() => actionRef.current?.reload()}
            />
        </PageContainer>
    );
}
