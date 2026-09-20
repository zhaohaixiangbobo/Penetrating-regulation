import { useRef, useState } from 'react';
import { PageContainer, ProTable } from '@ant-design/pro-components';
import type { ActionType, ProColumns } from '@ant-design/pro-components';
import {
    Button,
    Form,
    Input,
    Modal,
    Radio,
    Select,
    Space,
    Tag,
    Upload,
    message,
} from 'antd';
import type { UploadFile } from 'antd';
import { PlusOutlined, UploadOutlined } from '@ant-design/icons';
import CompanySelect from '@/components/CompanySelect';
import { getCompanyTagColor } from '@/utils/companyColor';
import {
    ClueRow,
    CLUE_CATEGORIES,
    formatClueTime,
    listMyClues,
    submitClue,
    uploadClueAttachment,
} from '@/services/feedback';
import ClueDetailDrawer, { statusColor } from '../components/ClueDetailDrawer';

const STATUS_TABS = [
    { label: '全部', value: '' },
    { label: '待处理', value: 'pending' },
    { label: '处理中', value: 'processing' },
    { label: '已处理', value: 'done' },
];

export default function FeedbackMinePage() {
    const actionRef = useRef<ActionType>();
    const [statusFilter, setStatusFilter] = useState<string>('');
    const [modalOpen, setModalOpen] = useState(false);
    const [submitting, setSubmitting] = useState(false);
    const [fileList, setFileList] = useState<UploadFile[]>([]);
    const [form] = Form.useForm();

    const [detailId, setDetailId] = useState<number | undefined>();
    const [drawerOpen, setDrawerOpen] = useState(false);

    const openDetail = (id: number) => {
        setDetailId(id);
        setDrawerOpen(true);
    };

    const resetModal = () => {
        form.resetFields();
        setFileList([]);
    };

    const handleSubmit = async () => {
        const values = await form.validateFields();
        setSubmitting(true);
        try {
            // 先创建线索拿到 id，再逐个上传附件
            const created = await submitClue({
                title: values.title,
                category: values.category,
                com_id: values.com_id || undefined,
                involved_dept: values.involved_dept || undefined,
                involved_manager: values.involved_manager || undefined,
                involved_customer: values.involved_customer || undefined,
                content: values.content,
            });

            let failed = 0;
            for (const f of fileList) {
                const raw = (f.originFileObj || f) as File;
                try {
                    await uploadClueAttachment(created.id, raw);
                } catch {
                    failed += 1;
                }
            }
            if (failed > 0) {
                message.warning(`线索已提交，但有 ${failed} 个附件上传失败，可在详情中补传`);
            } else {
                message.success('线索提交成功');
            }
            setModalOpen(false);
            resetModal();
            actionRef.current?.reload();
        } catch (err: any) {
            if (err?.errorFields) return; // 表单校验错误
            // 其它错误 errorHandler 已提示
        } finally {
            setSubmitting(false);
        }
    };

    const columns: ProColumns<ClueRow>[] = [
        { title: '编号', dataIndex: 'id', width: 70 },
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
        { title: '附件', dataIndex: 'attachment_count', width: 70 },
        {
            title: '状态',
            dataIndex: 'status',
            width: 90,
            render: (_, r) => <Tag color={statusColor(r.status)}>{r.status_label}</Tag>,
        },
        { title: '提交时间', dataIndex: 'created_at', width: 150, sorter: true, render: (_, r) => formatClueTime(r.created_at) },
        {
            title: '操作',
            width: 80,
            fixed: 'right',
            render: (_, r) => (
                <a onClick={() => openDetail(r.id)}>详情</a>
            ),
        },
    ];

    return (
        <PageContainer header={{ title: '审计线索反馈', subTitle: '提交审计线索并查看处理进度' }}>
            <ProTable<ClueRow>
                actionRef={actionRef}
                columns={columns}
                rowKey="id"
                search={false}
                scroll={{ x: 'max-content' }}
                toolBarRender={() => [
                    <Radio.Group
                        key="status"
                        optionType="button"
                        buttonStyle="solid"
                        value={statusFilter}
                        options={STATUS_TABS}
                        onChange={(e) => {
                            setStatusFilter(e.target.value);
                            actionRef.current?.reload();
                        }}
                    />,
                    <Button
                        key="new"
                        type="primary"
                        icon={<PlusOutlined />}
                        onClick={() => {
                            resetModal();
                            setModalOpen(true);
                        }}
                    >
                        提交线索
                    </Button>,
                ]}
                pagination={{
                    defaultPageSize: 20,
                    showSizeChanger: true,
                    showTotal: (total, range) => `第 ${range[0]}-${range[1]} 条/总共 ${total} 条`,
                }}
                request={async (p, sort) => {
                    try {
                        const order = sort?.created_at === 'ascend' ? 'asc' : 'desc';
                        const res = await listMyClues({
                            status: statusFilter || undefined,
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

            <Modal
                title="提交审计线索"
                open={modalOpen}
                onCancel={() => setModalOpen(false)}
                onOk={handleSubmit}
                confirmLoading={submitting}
                okText="提交"
                cancelText="取消"
                width={640}
                destroyOnClose
            >
                <Form form={form} layout="vertical" preserve={false}>
                    <Form.Item
                        name="title"
                        label="线索标题"
                        rules={[{ required: true, message: '请输入线索标题' }, { max: 200 }]}
                    >
                        <Input placeholder="简要描述线索" maxLength={200} />
                    </Form.Item>
                    <Form.Item
                        name="category"
                        label="线索类型"
                        rules={[{ required: true, message: '请选择线索类型' }]}
                    >
                        <Select
                            placeholder="请选择类型"
                            options={CLUE_CATEGORIES.map((c) => ({ label: c, value: c }))}
                        />
                    </Form.Item>
                    <Form.Item name="com_id" label="关联公司">
                        <CompanySelect allowClear />
                    </Form.Item>
                    <Space size={12} style={{ display: 'flex' }}>
                        <Form.Item name="involved_dept" label="涉及营业部" style={{ flex: 1 }}>
                            <Input maxLength={200} placeholder="可选" />
                        </Form.Item>
                        <Form.Item name="involved_manager" label="涉及客户经理" style={{ flex: 1 }}>
                            <Input maxLength={200} placeholder="可选" />
                        </Form.Item>
                    </Space>
                    <Form.Item name="involved_customer" label="涉及客户">
                        <Input maxLength={200} placeholder="可选" />
                    </Form.Item>
                    <Form.Item
                        name="content"
                        label="线索详细描述"
                        rules={[{ required: true, message: '请输入线索详细描述' }, { max: 10000 }]}
                    >
                        <Input.TextArea rows={5} maxLength={10000} showCount placeholder="请详细描述线索内容" />
                    </Form.Item>
                    <Form.Item label="附件（最多 5 个，单个 ≤ 10MB）">
                        <Upload
                            fileList={fileList}
                            beforeUpload={(file) => {
                                if (fileList.length >= 5) {
                                    message.warning('最多上传 5 个附件');
                                    return Upload.LIST_IGNORE;
                                }
                                if (file.size > 10 * 1024 * 1024) {
                                    message.warning('单个附件不能超过 10MB');
                                    return Upload.LIST_IGNORE;
                                }
                                setFileList((prev) => [...prev, file as unknown as UploadFile]);
                                return false; // 阻止自动上传，提交时统一上传
                            }}
                            onRemove={(file) => {
                                setFileList((prev) => prev.filter((f) => f.uid !== file.uid));
                            }}
                            accept=".jpg,.jpeg,.png,.webp,.pdf,.doc,.docx,.xls,.xlsx,.zip"
                        >
                            <Button icon={<UploadOutlined />}>选择文件</Button>
                        </Upload>
                    </Form.Item>
                </Form>
            </Modal>

            <ClueDetailDrawer
                clueId={detailId}
                open={drawerOpen}
                onClose={() => setDrawerOpen(false)}
            />
        </PageContainer>
    );
}
