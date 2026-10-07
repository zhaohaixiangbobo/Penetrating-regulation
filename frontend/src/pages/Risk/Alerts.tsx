/** 预警台账与核查详情：证据、历史判定、处置日志、附件和人工线索关联。 */
import { useEffect, useRef, useState } from 'react';
import { useLocation, useModel } from '@umijs/max';
import { tableSearch, tableCards } from '@/components/UnifiedQueryFilter';
import { PageContainer, ProTable, ActionType } from '@ant-design/pro-components';
import { Alert, Button, Descriptions, Drawer, Form, Input, Select, Tabs, Tag, Timeline, Typography, Upload, message } from 'antd';
import { clueNumber } from '@/utils/clueNumber';
import { alertNumber, riskStatusColors, visitDateText, labels, RiskAlert, riskGet, riskPost, timeText, configText, uploadRiskFile, downloadRiskFile } from '@/services/risk';
import { getCompanyTagColor } from '@/utils/companyColor';
import ClueDetailDrawer from '@/pages/Feedback/components/ClueDetailDrawer';
import CompanySelect from '@/components/CompanySelect';
import RiskBatchAction from '@/components/RiskBatchAction';
import RiskCluePicker from '@/components/RiskCluePicker';
import { Evidence } from './Runs';

export default function Alerts() {
  const action = useRef<ActionType>(); const [id, setId] = useState<number | undefined>(() => Number(new URLSearchParams(window.location.search).get('alert')) || undefined); const [detail, setDetail] = useState<any>();
  const [saving, setSaving] = useState(false); const [form] = Form.useForm(); const [viewClue, setViewClue] = useState<number>();
  const [selected, setSelected] = useState<RiskAlert[]>([]);
  const [batchRows, setBatchRows] = useState<RiskAlert[]>();
  const location = useLocation();
  // 线索中的反向关联可能仍在同一路由内，查询参数变化时同步打开目标预警。
  useEffect(() => { setId(Number(new URLSearchParams(location.search).get('alert')) || undefined); setViewClue(undefined); }, [location.search]);
  const { initialState } = useModel('@@initialState'); const username = initialState?.currentUser?.username;
  const chosenAction = Form.useWatch('action', form);
  const reload = async (key: number) => { const d = await riskGet(`/alerts/${key}`); setDetail(d); };
  useEffect(() => { setDetail(undefined); if (id) reload(id); }, [id]);
  useEffect(() => { if (detail) form.resetFields(); }, [detail?.id]);
  const perform = async () => {
    const v = await form.validateFields(); if (!detail) return; setSaving(true);
    try { await riskPost(`/alerts/${detail.id}/actions`, { ...v, revision: detail.revision }); form.resetFields(); await reload(detail.id); action.current?.reload(); message.success('核查操作已保存'); }
    finally { setSaving(false); }
  };
  const options = detail ? [
    ...(detail.status === 'pending' ? [{ value: 'start', label: '开始核查' }] : []),
    ...(detail.status === 'investigating' ? [{ value: 'conclude', label: '提交核查结论' }] : []),
    ...(detail.status === 'rectifying' ? [{ value: 'submit_rectification', label: '提交整改，申请复核' }] : []),
    ...(detail.status === 'reviewing' ? [{ value: 'approve', label: '复核通过并关闭', disabled: detail.assigned_to === username }, { value: 'return', label: '退回核查' }] : []),
    ...(detail.status === 'closed' ? [{ value: 'reopen', label: '有新证据，重新核查' }] : []),
    { value: 'supplement', label: '补充说明' },
  ] : [];
  return <PageContainer title="预警台账" subTitle="查看风险证据，记录核查结论与整改复核过程">
    <ProTable<RiskAlert> search={tableSearch} cardBordered={tableCards} rowKey="id" actionRef={action} scroll={{ x: 1050 }} pagination={{ pageSize: 20 }}
      rowSelection={{ selectedRowKeys: selected.map(r => r.id), hideSelectAll: true,
        getCheckboxProps: row => ({ disabled: selected.length > 0 && row.status !== selected[0].status }),
        onChange: (_, rows) => {
          if (rows.length && rows.some(r => r.status !== rows[0].status)) { message.warning('请选择同一状态的预警'); return; }
          setSelected(rows);
        }, preserveSelectedRowKeys: false }}
      toolBarRender={() => [<Button key="batch" type="primary" disabled={!selected.length} onClick={() => setBatchRows([...selected])}>批量处理{selected.length ? `（${selected.length}）` : ''}</Button>]}
      locale={{ emptyText: '暂未查到符合条件的预警，可先在模型管理中正式运行' }}
      request={async p => { setSelected([]); const r = await riskGet('/alerts', { keyword: p.keyword, status: p.status, com_id: p.com_id, page: p.current, page_size: p.pageSize }); return { data: r.items, total: r.total, success: true }; }}
      columns={[
        { title: '客户名称/许可证号', dataIndex: 'keyword', hideInTable: true },
        { title: '预警编号', dataIndex: 'id', width: 150, hideInSearch: true, render: (_, r) => alertNumber(r.id) },
        { title: '公司', dataIndex: 'com_id', hideInTable: true, renderFormItem: () => <CompanySelect allowClear /> },
        { title: '风险模型', dataIndex: 'model_name', width: 140, hideInSearch: true },
        { title: '公司', dataIndex: 'short_name', width: 85, hideInSearch: true, render: (_, r) => <Tag color={getCompanyTagColor(r.short_name)}>{r.short_name || '-'}</Tag> },
        { title: '客户', dataIndex: 'cust_name', ellipsis: true, hideInSearch: true },
        { title: '许可证号', dataIndex: 'cust_code', width: 130, hideInSearch: true },
        { title: '客户经理', dataIndex: 'person_name', width: 95, hideInSearch: true },
        { title: '拜访日期', tooltip: '来源：计划拜访日期 plan_date', dataIndex: 'event_time', width: 115, hideInSearch: true, render: (_, r) => visitDateText(r.event_time) },
        { title: '状态', dataIndex: 'status', width: 100, valueType: 'select', valueEnum: Object.fromEntries(['pending', 'investigating', 'rectifying', 'reviewing', 'closed'].map(k => [k, { text: labels[k] }])), render: (_, r) => <Tag color={riskStatusColors[r.status]}>{labels[r.status]}</Tag> },
        { title: '操作', width: 105, fixed: 'right', hideInSearch: true, render: (_, r) => <Button type="link" onClick={() => setId(r.id)}>查看 / 核查</Button> },
      ]} />
    <Drawer title={detail ? `风险详情 · ${alertNumber(detail.id)}` : '风险详情'} open={!!id} onClose={() => setId(undefined)} width="min(1000px, 95vw)">
      {detail && <>
        <Descriptions column={2} size="small" items={[
          { key: 'model', label: '场景', children: detail.model_name }, { key: 'status', label: '状态', children: <Tag color={riskStatusColors[detail.status]}>{labels[detail.status]}</Tag> },
          { key: 'first', label: '首次发现', children: timeText(detail.first_seen) }, { key: 'last', label: '最近命中', children: timeText(detail.last_seen) },
          { key: 'version', label: '首次判断版本', children: `V${detail.first_run.version_number}` }, { key: 'conclusion', label: '核查结论', children: labels[detail.conclusion] || '尚未形成结论' },
        ]} />
        {detail.prior_alert_id && <Alert style={{ marginBottom: 12 }} type="warning" message={`${detail.recurrence ? '疑似复发' : '同类事件再次出现'}，历史事项 ${alertNumber(detail.prior_alert_id)}；本次仍需核查。`} />}
        <Tabs items={[
          { key: 'evidence', label: '命中原因与证据', children: <><Typography.Paragraph>{configText(detail.first_run.snapshot)}</Typography.Paragraph><Evidence item={detail.first_evidence} />
            <Typography.Title level={5}>历史判定记录</Typography.Title>
            <Timeline items={detail.occurrences.map((o: any) => ({ children: <span>运行 {o.run_id} · {labels[o.outcome]} · {o.reasons.map((r: any) => `${r.actual ?? '未知'} ${r.operator === 'lt' ? '＜' : '＞'} ${r.value}`).join('；')}</span> }))} />
            <Typography.Title level={5}>相关历史事件（背景信息）</Typography.Title>
            {detail.history.length ? detail.history.map((h: any) => <p key={h.id}><Button type="link" onClick={() => setId(h.id)}>{alertNumber(h.id)}</Button>{visitDateText(h.event_time)} · {labels[h.status]}</p>) : <Typography.Text type="secondary">暂无其他相关事件</Typography.Text>}
          </> },
          { key: 'action', label: '核查处置', forceRender: true, children: <>
            {detail.status === 'reviewing' && detail.assigned_to === username && <Alert type="info" showIcon message="本事项需由另一位管理员复核。" style={{ marginBottom: 16 }} />}
            <Form form={form} layout="vertical" onFinish={perform}>
              <Form.Item name="action" label="操作" rules={[{ required: true }]}><Select options={options} /></Form.Item>
              {chosenAction === 'conclude' && <Form.Item name="conclusion" label="核查结论" rules={[{ required: true }]}><Select options={['confirmed', 'reasonable', 'data_quality', 'insufficient', 'normal'].map(value => ({ value, label: labels[value] }))} /></Form.Item>}
              <Form.Item name="note" label="核查/操作说明" rules={[{ required: true, min: 2, whitespace: true }]}><Input.TextArea rows={3} maxLength={5000} showCount /></Form.Item>
              <Form.Item name="measures" label="处置措施 / 数据修正要求"><Input.TextArea rows={2} maxLength={5000} /></Form.Item>
              <Button htmlType="submit" type="primary" loading={saving}>保存核查记录</Button>
            </Form>
            <Typography.Title level={5}>处置时间线</Typography.Title>
            <Timeline items={detail.actions.map((a: any) => ({ children: <><div>{timeText(a.created_at)} · {a.actor} · {labels[a.from_status]} → {labels[a.to_status]}</div><div>{a.note}</div>{a.measures && <div>措施：{a.measures}</div>}</> }))} />
          </> },
          { key: 'files', label: '附件与审计线索', children: <>
            <Upload showUploadList={false} beforeUpload={async file => { await uploadRiskFile(detail.id, file); await reload(detail.id); return false; }}><Button>上传核查附件</Button></Upload>
            <Typography.Paragraph type="secondary">每条预警最多5个附件，单个最大10MB。</Typography.Paragraph>
            {detail.attachments.map((f: any) => <p key={f.id}><Button type="link" onClick={() => downloadRiskFile(detail.id, f)}>{f.original_name}</Button></p>)}
            <Typography.Title level={5}>关联审计线索</Typography.Title>
            <RiskCluePicker key={detail.id} alertId={detail.id} linkedIds={detail.clues.map((c: any) => c.id)} onLinked={() => reload(detail.id)} />
            {detail.clues.map((c: any) => <p key={c.id}><Button type="link" onClick={() => setViewClue(c.id)}>{clueNumber(c.id)} {c.title}</Button></p>)}
          </> },
        ]} />
      </>}
    </Drawer>
    {batchRows && <RiskBatchAction rows={batchRows} username={username} onClose={() => setBatchRows(undefined)} onDone={() => { setSelected([]); action.current?.reload(); if (id) void reload(id); }} />}
    <ClueDetailDrawer open={!!viewClue} clueId={viewClue} onClose={() => setViewClue(undefined)} />
  </PageContainer>;
}
