/** 定时计划管理：固定版本、日期预览、启停留痕与独立执行器状态。 */
import { useEffect, useRef, useState } from 'react';
import { history, request } from '@umijs/max';
import { ActionType, PageContainer, ProTable } from '@ant-design/pro-components';
import { Button, Drawer, Form, Input, InputNumber, Modal, Select, Space, Switch, Table, Tag, message } from 'antd';
import CompanySelect from '@/components/CompanySelect';
import { tableCards, tableSearch } from '@/components/UnifiedQueryFilter';
import { RiskModel, riskGet, riskPost, timeText } from '@/services/risk';

export default function Schedules() {
  const action = useRef<ActionType>(); const [form] = Form.useForm();
  const [editing, setEditing] = useState<any>(); const [models, setModels] = useState<RiskModel[]>([]);
  const [worker, setWorker] = useState<any>(); const [saving, setSaving] = useState(false);
  const [preview, setPreview] = useState<any[]>([]); const [records, setRecords] = useState<any>();
  const frequency = Form.useWatch('frequency', form);
  const refresh = async () => { setWorker(await riskGet('/worker')); action.current?.reload(); };
  useEffect(() => { refresh(); riskGet<RiskModel[]>('/models').then(setModels); }, []);
  const open = (row?: any) => {
    setEditing(row || { id: 0 }); setPreview([]); form.resetFields();
    form.setFieldsValue(row ? { ...row.config, name: row.name, enabled: row.enabled } : { frequency: 'daily', weekday: 0, hour: 3, minute: 0, lookback_days: 3, batch_size: 1000, enabled: false });
  };
  const save = async () => {
    const values = await form.validateFields(); setSaving(true);
    try {
      if (editing.id) await request(`/api/risk/schedules/${editing.id}`, { method: 'PUT', data: { ...values, revision: editing.revision } });
      else await riskPost('/schedules', values);
      setEditing(undefined); await refresh(); message.success('计划已保存');
    } finally { setSaving(false); }
  };
  const workerOnline = worker?.alive === true;
  return <PageContainer title="定时计划" subTitle="按北京时间执行，固定模型版本，自动按公司和日期分批" extra={<Button type="primary" danger={worker !== undefined && !workerOnline}
    style={workerOnline ? { background: '#52c41a', borderColor: '#52c41a' } : undefined} onClick={refresh}>
    后台状态：{worker === undefined ? '加载中' : workerOnline ? '在线' : '离线'} · 刷新
  </Button>}>
    <ProTable rowKey="id" actionRef={action} search={tableSearch} cardBordered={tableCards} pagination={{ defaultPageSize: 10 }} scroll={{ x: 1050 }}
      toolBarRender={() => [<Button key="new" type="primary" onClick={() => open()}>新增计划</Button>]}
      request={async p => { const r = await riskGet('/schedules', { name: p.name, enabled: p.enabled, version_id: p.version_id, page: p.current, page_size: p.pageSize }); return { data: r.items, total: r.total, success: true }; }}
      locale={{ emptyText: '暂未查到符合条件的计划' }} columns={[
        { title: '计划名称', dataIndex: 'name', width: 150 },
        { title: '模型版本', dataIndex: 'version_id', hideInTable: true, valueType: 'select', fieldProps: { showSearch: true, optionFilterProp: 'label', options: models.flatMap(m => m.versions.map(v => ({ value: v.id, label: `${m.name} V${v.number}` }))) } },
        { title: '启停状态', dataIndex: 'enabled', valueType: 'select', valueEnum: { true: '启用', false: '暂停' }, width: 85, render: (_, r) => <Tag color={r.enabled ? 'green' : 'default'}>{r.enabled ? '启用' : '暂停'}</Tag> },
        { title: '执行规则', hideInSearch: true, render: (_, r) => `${r.config.frequency === 'daily' ? '每天' : `每周${['一','二','三','四','五','六','日'][r.config.weekday]}`} ${String(r.config.hour).padStart(2,'0')}:${String(r.config.minute).padStart(2,'0')}，回看${r.config.lookback_days}天` },
        { title: '模型版本', hideInSearch: true, render: (_, r) => { const m = models.find(m => m.versions.some(v => v.id === r.config.version_id)); const v = m?.versions.find(v => v.id === r.config.version_id); return m ? `${m.name} V${v?.number}` : `版本ID ${r.config.version_id}`; } },
        { title: '下次触发', hideInSearch: true, render: (_, r) => r.enabled ? timeText(r.next_fire) : '已暂停' },
        { title: '提示', dataIndex: 'note', hideInSearch: true, ellipsis: true },
        { title: '操作', hideInSearch: true, width: 260, render: (_, r) => <Space size={0} wrap>
          <Button type="link" onClick={() => open(r)}>编辑</Button>
          <Button type="link" onClick={async () => { await request(`/api/risk/schedules/${r.id}`, { method: 'PUT', data: { ...r.config, name: r.name, enabled: !r.enabled, revision: r.revision } }); await refresh(); }}>{r.enabled ? '暂停' : '启用'}</Button>
          <Button type="link" onClick={() => Modal.confirm({ title: '立即执行此计划？', content: '按照当前计划版本计算截至昨日的回看区间，命中后生成正式预警。', onOk: async () => { const run = await riskPost(`/schedules/${r.id}/run`); history.push(`/risk-models/runs?run=${run.id}`); } })}>立即执行</Button>
          <Button type="link" onClick={async () => setRecords(await riskGet(`/schedules/${r.id}/history`))}>记录</Button>
        </Space> },
      ]} />
    <Drawer title={editing?.id ? '编辑计划' : '新增计划'} width={650} open={!!editing} onClose={() => setEditing(undefined)} extra={<Button type="primary" loading={saving} onClick={save}>保存</Button>}>
      <Form form={form} layout="vertical">
        <Form.Item name="name" label="计划名称" rules={[{ required: true, whitespace: true }]}><Input maxLength={100} /></Form.Item>
        <Form.Item name="version_id" label="固定模型版本" rules={[{ required: true }]}><Select showSearch optionFilterProp="label" options={models.filter(m => m.enabled).flatMap(m => m.versions.filter(v => v.published).map(v => ({ value: v.id, label: `${m.name} V${v.number}` })))} /></Form.Item>
        <Form.Item name="com_ids" label="分析公司" rules={[{ required: true }]}><CompanySelect mode="multiple" /></Form.Item>
        <Form.Item name="frequency" label="执行周期"><Select options={[{ value: 'daily', label: '每天' }, { value: 'weekly', label: '每周' }]} /></Form.Item>
        {frequency === 'weekly' && <Form.Item name="weekday" label="星期"><Select options={['一','二','三','四','五','六','日'].map((s, value) => ({ value, label: `星期${s}` }))} /></Form.Item>}
        <Space align="baseline"><Form.Item name="hour" label="北京时间：时" rules={[{ required: true }]}><InputNumber min={0} max={23} precision={0} /></Form.Item><Form.Item name="minute" label="分" rules={[{ required: true }]}><InputNumber min={0} max={59} precision={0} /></Form.Item></Space>
        <Form.Item name="lookback_days" label="截至昨日，回看天数" rules={[{ required: true }]}><InputNumber min={1} max={31} precision={0} /></Form.Item>
        <Form.Item name="batch_size" label="每批事件数" rules={[{ required: true }]}><InputNumber min={1} max={5000} precision={0} /></Form.Item>
        <Form.Item name="enabled" label="启用计划" valuePropName="checked"><Switch /></Form.Item>
        <Button onClick={async () => setPreview(await riskPost('/schedules/preview', await form.validateFields()))}>预览未来五次执行</Button>
        <Table size="small" rowKey="fire_at" style={{ marginTop: 16 }} pagination={false} dataSource={preview} columns={[{ title: '北京时间', dataIndex: 'fire_at', render: timeText }, { title: '分析范围', render: (_, r) => `${r.start_date} ～ ${r.end_date}` }]} />
      </Form>
    </Drawer>
    <Drawer title="计划触发与修订记录（最近100条）" width={800} open={!!records} onClose={() => setRecords(undefined)}>
      <Table<any> rowKey="id" dataSource={records?.triggers} columns={[{ title: '触发时刻', dataIndex: 'fire_at', render: timeText }, { title: '结果', render: (_, r) => r.run_id ? <Button type="link" onClick={() => history.push(`/risk-models/runs?run=${r.run_id}`)}>查看运行</Button> : r.status === 'missed' ? '遗漏待补算' : '已阻止' }, { title: '说明', dataIndex: 'note' }]} />
      <Table<any> rowKey="id" dataSource={records?.revisions} columns={[{ title: '修订', dataIndex: 'revision' }, { title: '操作人', dataIndex: 'actor' }, { title: '时间', dataIndex: 'created_at', render: timeText }, { title: '状态', render: (_, r) => r.snapshot.enabled ? '启用' : '暂停' }]} />
    </Drawer>
  </PageContainer>;
}
