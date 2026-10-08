/** 模型配置：版本追加、发布、同粒度组合、手动试算及正式运行。 */
import { useRef, useState } from 'react';
import { history } from '@umijs/max';
import { tableSearch, tableCards } from '@/components/UnifiedQueryFilter';
import { PageContainer, ProTable, ActionType } from '@ant-design/pro-components';
import { Alert, Button, DatePicker, Drawer, Form, Input, InputNumber, Modal, Select, Space, Tag, Typography, message } from 'antd';
import dayjs from 'dayjs';
import CompanySelect from '@/components/CompanySelect';
import { configText, indicatorNames, RiskVersion, riskGet, riskPost } from '@/services/risk';

const initialConfig = { evaluation_unit: 'visit_event', combination: 'ALL', minimum: 1, conditions: [
  { indicator: 'visit_duration_seconds', version: 1, operator: 'lt', value: 60 },
  { indicator: 'visit_location_distance_meters', version: 1, operator: 'gt', value: 200 },
] };
type VersionRow = RiskVersion & { model_name: string; enabled: boolean; version_count: number };
export default function Models() {
  const action = useRef<ActionType>();
  const [baselineVersions, setBaselineVersions] = useState<RiskVersion[]>([]);
  const [editing, setEditing] = useState<VersionRow | 'new'>();
  const [run, setRun] = useState<{ row: VersionRow; mode: string }>();
  const [form] = Form.useForm(); const [runForm] = Form.useForm();
  const [saving, setSaving] = useState(false); const [running, setRunning] = useState(false);
  const combination = Form.useWatch('combination', form);
  const openEdit = (row: VersionRow | 'new') => { setEditing(row); form.resetFields(); form.setFieldsValue(row === 'new' ? initialConfig : row.config); };
  const openRun = async (row: VersionRow, mode: string) => {
    // 基准选择读取该模型完整版本，独立于列表当前筛选与页码。
    const versions = mode === 'compare' ? await riskGet<RiskVersion[]>(`/models/${row.model_id}/versions`) : [];
    setBaselineVersions(versions); setRun({ row, mode }); runForm.resetFields(); runForm.setFieldsValue({ range: [dayjs().subtract(7, 'day'), dayjs()], com_ids: [] });
  };
  const submit = async () => {
    const values = await form.validateFields(); setSaving(true);
    try {
      const config = { evaluation_unit: 'visit_event', combination: values.combination, minimum: values.minimum || 1, conditions: values.conditions.map((c: any) => ({ ...c, version: 1 })) };
      if (editing === 'new') await riskPost('/models', { name: values.name, config });
      else if (editing) await riskPost(`/models/${editing.model_id}/versions`, config);
      setEditing(undefined); action.current?.reload(); message.success('已保存新草稿版本');
    } finally { setSaving(false); }
  };
  const submitRun = async () => {
    const v = await runForm.validateFields(); if (!run) return; setRunning(true);
    try {
      const result = await riskPost('/runs', { version_id: run.row.id, mode: run.mode, start_date: v.range[0].format('YYYY-MM-DD'), end_date: v.range[1].format('YYYY-MM-DD'), com_ids: v.com_ids, baseline_version_id: v.baseline_version_id });
      setRun(undefined); history.push(`/risk-models/runs?run=${result.id}`);
    } finally { setRunning(false); }
  };
  return <PageContainer title="模型管理" subTitle="配置、试算和发布风险模型；历史版本保留原始判断条件">
    <ProTable<VersionRow> rowKey="id" actionRef={action} search={tableSearch} cardBordered={tableCards} pagination={{ defaultPageSize: 10 }} scroll={{ x: 880 }}
      locale={{ emptyText: '暂未查到符合条件的模型版本，请调整筛选条件' }}
      toolBarRender={() => [<Button key="new" type="primary" onClick={() => openEdit('new')}>新增模型</Button>]}
      request={async p => { const r = await riskGet('/model-versions', { model_name: p.model_name, published: p.published, enabled: p.enabled, version_number: p.version_number, page: p.current, page_size: p.pageSize }); return { data: r.items, total: r.total, success: true }; }}
      columns={[
        { title: '模型名称', dataIndex: 'model_name', width: 150 },
        { title: '版本状态', dataIndex: 'published', hideInTable: true, valueType: 'select', valueEnum: { true: { text: '已发布' }, false: { text: '草稿' } } },
        { title: '版本号', dataIndex: 'version_number', hideInTable: true, valueType: 'digit', fieldProps: { min: 1, precision: 0, placeholder: '如 1 表示 V1' } },
        { title: '版本', width: 90, hideInSearch: true, render: (_, r) => <Tag color={r.published ? 'green' : 'gold'}>V{r.number} {r.published ? '已发布' : '草稿'}</Tag> },
        { title: '判断条件 · 单次拜访', hideInSearch: true, render: (_, r) => <Typography.Paragraph style={{ margin: 0 }}>{configText(r.config)}</Typography.Paragraph> },
        { title: '启停状态', dataIndex: 'enabled', valueType: 'select', valueEnum: { true: { text: '启用' }, false: { text: '停用' } }, width: 85, render: (_, r) => <Tag>{r.enabled ? '启用' : '停用'}</Tag> },
        { title: '操作', hideInSearch: true, width: 280, render: (_, r) => <Space size={0} wrap>
          <Button type="link" onClick={() => openEdit(r)}>新版本</Button>
          <Button type="link" disabled={!r.enabled} onClick={() => openRun(r, 'trial')}>试算</Button>
          <Button type="link" disabled={!r.enabled || r.version_count < 2} onClick={() => openRun(r, 'compare')}>对比</Button>
          {r.published ? <Button type="link" disabled={!r.enabled} onClick={() => openRun(r, 'formal')}>正式运行</Button> : <Button type="link" onClick={async () => { await riskPost(`/versions/${r.id}/publish`); action.current?.reload(); message.success('版本已发布'); }}>发布</Button>}
          <Button type="link" onClick={async () => { await riskPost(`/models/${r.model_id}/enabled`, undefined, { enabled: !r.enabled }); action.current?.reload(); }}>{r.enabled ? '停用' : '启用'}</Button>
        </Space> },
      ]} />
    <Drawer forceRender title={editing === 'new' ? '新增风险模型' : '保存为新版本'} width={760} open={!!editing} onClose={() => setEditing(undefined)}
      extra={<Button type="primary" loading={saving} onClick={submit}>保存草稿</Button>}>
      <Form form={form} layout="vertical">
        {editing === 'new' && <Form.Item name="name" label="模型名称" rules={[{ required: true, whitespace: true }]}><Input maxLength={100} /></Form.Item>}
        <Form.Item label="分析粒度"><Tag color="blue">单次拜访</Tag></Form.Item>
        <Form.Item name="combination" label="满足方式" rules={[{ required: true }]}><Select options={[{ value: 'ALL', label: '全部满足' }, { value: 'ANY', label: '任一满足' }, { value: 'AT_LEAST_N', label: '至少满足 N 项' }]} /></Form.Item>
        {combination === 'AT_LEAST_N' && <Form.Item name="minimum" label="至少满足项数" rules={[{ required: true }]}><InputNumber min={1} max={8} /></Form.Item>}
        <Form.List name="conditions">{(fields, { add, remove }) => <>
          {fields.map(field => <Space key={field.key} align="baseline" wrap>
            <Form.Item name={[field.name, 'indicator']} rules={[{ required: true }]}><Select style={{ width: 220 }} options={Object.entries(indicatorNames).map(([value, label]) => ({ value, label }))} /></Form.Item>
            <Form.Item name={[field.name, 'operator']} rules={[{ required: true }]}><Select style={{ width: 100 }} options={[{ value: 'lt', label: '小于' }, { value: 'gt', label: '大于' }]} /></Form.Item>
            <Form.Item name={[field.name, 'value']} rules={[{ required: true }]}><InputNumber min={0.01} max={1000000} /></Form.Item>
            <Button disabled={fields.length === 1} type="link" onClick={() => remove(field.name)}>移除</Button>
          </Space>)}
          <Button disabled={fields.length >= 8} onClick={() => add({ indicator: 'visit_duration_seconds', operator: 'gt', value: 18000, version: 1 })}>增加条件</Button>
        </>}</Form.List>
        <Typography.Paragraph type="secondary" style={{ marginTop: 20 }}>时长以秒、距离以米判断。新版本保留独立参数，已发布版本保持原定义。</Typography.Paragraph>
      </Form>
    </Drawer>
    <Modal forceRender title={run?.mode === 'formal' ? '正式运行模型' : run?.mode === 'compare' ? '同批数据参数对比' : '试算模型'} open={!!run} onCancel={() => setRun(undefined)} onOk={submitRun} confirmLoading={running} okText="开始运行" cancelText="取消">
      <Alert type="info" showIcon style={{ marginBottom: 16 }} message={run?.mode === 'formal' ? '完成后生成预警台账，同一事件重复运行自动去重。' : '试算和对比仅保存计算结果，不生成正式预警。'} />
      <Form form={runForm} layout="vertical">
        <Form.Item name="com_ids" label="分析公司" rules={[{ required: true, message: '请选择公司' }]}><CompanySelect mode="multiple" /></Form.Item>
        <Form.Item name="range" label="拜访日期（最多366天，自动分批）" rules={[{ required: true }]}><DatePicker.RangePicker allowClear={false} disabledDate={d => d.isBefore('2024-01-01', 'day')} /></Form.Item>
        {run?.mode === 'compare' && <Form.Item name="baseline_version_id" label="基准版本" rules={[{ required: true }]}><Select options={baselineVersions.filter(v => v.id !== run.row.id).map(v => ({ value: v.id, label: `V${v.number} ${configText(v.config)}` }))} /></Form.Item>}
      </Form>
    </Modal>
  </PageContainer>;
}
