import { useEffect, useState } from 'react';
import {
    Button,
    Descriptions,
    Divider,
    Drawer,
    Form,
    Image,
    Input,
    Select,
    Space,
    Tag,
    Timeline,
    Typography,
    message,
} from 'antd';
import { DownloadOutlined, EyeOutlined, PaperClipOutlined } from '@ant-design/icons';
import { getCompanyTagColor } from '@/utils/companyColor';
import {
    ClueDetail,
    ClueStatus,
    CLUE_STATUS_LABELS,
    downloadClueAttachment,
    fetchAttachmentObjectURL,
    formatClueTime,
    getClue,
    handleClue,
} from '@/services/feedback';

const IMAGE_EXTS = ['.jpg', '.jpeg', '.png', '.webp'];

/** 状态标签颜色。 */
export function statusColor(status: ClueStatus): string {
    return status === 'done' ? 'green' : status === 'processing' ? 'blue' : 'gold';
}

function isImage(name: string): boolean {
    const lower = name.toLowerCase();
    return IMAGE_EXTS.some((e) => lower.endsWith(e));
}

interface Props {
    clueId?: number;
    open: boolean;
    onClose: () => void;
    /** 是否展示处理表单（仅管理员管理页传 true） */
    canHandle?: boolean;
    /** 处理成功后回调（供父级刷新列表） */
    onHandled?: () => void;
}

/** 线索详情抽屉：基本信息 / 涉及对象 / 线索内容 / 附件 / 处理记录 / (可选)处理表单。 */
export default function ClueDetailDrawer({ clueId, open, onClose, canHandle, onHandled }: Props) {
    const [detail, setDetail] = useState<ClueDetail | null>(null);
    const [loading, setLoading] = useState(false);
    const [submitting, setSubmitting] = useState(false);
    const [previewSrc, setPreviewSrc] = useState<string>('');
    const [previewVisible, setPreviewVisible] = useState(false);
    const [form] = Form.useForm();

    const reload = async () => {
        if (!clueId) return;
        setLoading(true);
        try {
            const d = await getClue(clueId);
            setDetail(d);
            form.setFieldsValue({ status: d.status, handle_remark: d.handle_remark });
        } catch {
            // errorHandler 已提示
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        if (open && clueId) reload();
        if (!open) setDetail(null);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [open, clueId]);

    const handleDownload = async (attId: number, name: string) => {
        try {
            await downloadClueAttachment(clueId!, attId, name);
        } catch {
            // errorHandler 已提示
        }
    };

    const handlePreview = async (attId: number) => {
        try {
            const url = await fetchAttachmentObjectURL(clueId!, attId);
            setPreviewSrc(url);
            setPreviewVisible(true);
        } catch {
            // errorHandler 已提示
        }
    };

    const onSubmitHandle = async () => {
        const values = await form.validateFields();
        setSubmitting(true);
        try {
            await handleClue(clueId!, { status: values.status, handle_remark: values.handle_remark });
            message.success('处理已保存');
            await reload();
            onHandled?.();
        } catch {
            // errorHandler 已提示
        } finally {
            setSubmitting(false);
        }
    };

    return (
        <Drawer
            title={detail ? `线索详情 · #${detail.id}` : '线索详情'}
            width={640}
            open={open}
            onClose={onClose}
            destroyOnClose
        >
            {detail && (
                <>
                    <Descriptions column={1} size="small" bordered>
                        <Descriptions.Item label="标题">{detail.title}</Descriptions.Item>
                        <Descriptions.Item label="类型">
                            <Tag>{detail.category}</Tag>
                        </Descriptions.Item>
                        <Descriptions.Item label="状态">
                            <Tag color={statusColor(detail.status)}>{detail.status_label}</Tag>
                        </Descriptions.Item>
                        <Descriptions.Item label="关联公司">
                            {detail.short_name ? (
                                <Tag color={getCompanyTagColor(detail.short_name)}>{detail.short_name}</Tag>
                            ) : (
                                '-'
                            )}
                        </Descriptions.Item>
                        <Descriptions.Item label="涉及营业部">{detail.involved_dept || '-'}</Descriptions.Item>
                        <Descriptions.Item label="涉及客户经理">{detail.involved_manager || '-'}</Descriptions.Item>
                        <Descriptions.Item label="涉及客户">{detail.involved_customer || '-'}</Descriptions.Item>
                        <Descriptions.Item label="提交人">{detail.created_by}</Descriptions.Item>
                        <Descriptions.Item label="提交时间">{formatClueTime(detail.created_at)}</Descriptions.Item>
                    </Descriptions>

                    <Divider orientation="left">线索内容</Divider>
                    <Typography.Paragraph style={{ whiteSpace: 'pre-wrap' }}>
                        {detail.content}
                    </Typography.Paragraph>

                    <Divider orientation="left">附件（{detail.attachments.length}）</Divider>
                    {detail.attachments.length === 0 ? (
                        <Typography.Text type="secondary">无附件</Typography.Text>
                    ) : (
                        <Space direction="vertical" style={{ width: '100%' }}>
                            {detail.attachments.map((a) => (
                                <Space key={a.id} size={8}>
                                    <PaperClipOutlined />
                                    <span>{a.original_name}</span>
                                    <Typography.Text type="secondary">
                                        ({(a.size / 1024).toFixed(1)} KB)
                                    </Typography.Text>
                                    {isImage(a.original_name) && (
                                        <Button
                                            size="small"
                                            type="link"
                                            icon={<EyeOutlined />}
                                            onClick={() => handlePreview(a.id)}
                                        >
                                            预览
                                        </Button>
                                    )}
                                    <Button
                                        size="small"
                                        type="link"
                                        icon={<DownloadOutlined />}
                                        onClick={() => handleDownload(a.id, a.original_name)}
                                    >
                                        下载
                                    </Button>
                                </Space>
                            ))}
                        </Space>
                    )}

                    <Divider orientation="left">处理记录</Divider>
                    {detail.handle_logs.length === 0 ? (
                        <Typography.Text type="secondary">暂无处理记录</Typography.Text>
                    ) : (
                        <Timeline
                            items={detail.handle_logs.map((l) => ({
                                color: statusColor(l.to_status as ClueStatus),
                                children: (
                                    <div>
                                        <div>
                                            <Tag color={statusColor(l.to_status as ClueStatus)}>
                                                {CLUE_STATUS_LABELS[l.to_status as ClueStatus] || l.to_status}
                                            </Tag>
                                            <Typography.Text type="secondary">
                                                {l.handled_by} · {formatClueTime(l.created_at)}
                                            </Typography.Text>
                                        </div>
                                        {l.remark && <div style={{ marginTop: 4 }}>{l.remark}</div>}
                                    </div>
                                ),
                            }))}
                        />
                    )}

                    {canHandle && (
                        <>
                            <Divider orientation="left">处理线索</Divider>
                            <Form form={form} layout="vertical">
                                <Form.Item
                                    name="status"
                                    label="处理状态"
                                    rules={[{ required: true, message: '请选择处理状态' }]}
                                >
                                    <Select
                                        options={[
                                            { label: '待处理', value: 'pending' },
                                            { label: '处理中', value: 'processing' },
                                            { label: '已处理', value: 'done' },
                                        ]}
                                    />
                                </Form.Item>
                                <Form.Item name="handle_remark" label="处理意见">
                                    <Input.TextArea rows={4} maxLength={5000} showCount placeholder="填写处理意见（可选）" />
                                </Form.Item>
                                <Button type="primary" loading={submitting} onClick={onSubmitHandle}>
                                    保存处理
                                </Button>
                            </Form>
                        </>
                    )}
                </>
            )}
            {loading && <Typography.Text type="secondary">加载中...</Typography.Text>}

            <Image
                style={{ display: 'none' }}
                preview={{
                    visible: previewVisible,
                    src: previewSrc,
                    onVisibleChange: (v) => {
                        setPreviewVisible(v);
                        if (!v && previewSrc) {
                            URL.revokeObjectURL(previewSrc);
                            setPreviewSrc('');
                        }
                    },
                }}
            />
        </Drawer>
    );
}
