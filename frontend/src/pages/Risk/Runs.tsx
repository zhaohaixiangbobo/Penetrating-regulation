/** 运行记录：后台状态、结果明细、同批次参数差集与证据抽屉。 */
import { useEffect, useRef, useState } from 'react';
import { tableSearch, tableCards } from '@/components/UnifiedQueryFilter';
import { PageContainer, ProTable, ActionType } from '@ant-design/pro-components';
import { Alert, Button, Descriptions, Drawer, Space, Tag, Segmented, Typography, Spin, Progress, Table } from 'antd';
import { visitDateText, configText, labels, RiskRun, RiskItem, riskGet, riskPost, timeText, conditionText } from '@/services/risk';

export function Evidence({ item }: { item: RiskItem }) {
  return <>
    <Descriptions column={2} size="small" bordered items={[
      ['客户', item.evidence.cust_name], ['许可证号', item.evidence.cust_code], ['客户经理', item.evidence.person_name],
      ['拜访日期（计划）', visitDateText(item.evidence.event_time)], ['时长（秒）', item.evidence.visit_time], ['距离（米）', item.evidence.distance_meters],
      ['经营经纬度', `${item.evidence.longitude ?? '-'}, ${item.evidence.latitude ?? '-'}`],
      ['签到经纬度', `${item.evidence.gis_long ?? '-'}, ${item.evidence.gis_lat ?? '-'}`],
      ['源记录ID', item.evidence.source_id], ['机关', item.evidence.issue_org_name],
    ].map(([label, children]) => ({ key: label, label, children: children ?? '不可计算' }))} />
    <Typography.Title level={5}>判断依据</Typography.Title>
    {item.reasons.map((r, i) => <p key={i}><Tag color={r.outcome === 'hit' ? 'orange' : r.outcome === 'unknown' ? 'default' : 'green'}>{labels[r.outcome]}</Tag>
      {conditionText(r as any)}；实际值：{r.actual ?? '缺失或不可计算'}</p>)}
    <Typography.Text type="secondary">按当次读取的原始证据计算。经营位置来自当前许可证资料，源系统同步水位尚未提供，历史地址及坐标系需核实。</Typography.Text>
  </>;
}

export default function Runs() {
  const action = useRef<ActionType>();
  const [workerState, setWorkerState] = useState<any>();
  useEffect(() => { riskGet('/worker').then(setWorkerState); }, []);
  const [id, setId] = useState<string | undefined>(() => new URLSearchParams(window.location.search).get('run') || undefined);
  const [run, setRun] = useState<RiskRun>(); const [kind, setKind] = useState('hit'); const [evidence, setEvidence] = useState<RiskItem>(); const [attempts, setAttempts] = useState<any[]>();
  useEffect(() => {
    if (!id) { setRun(undefined); return; }
    let active = true; let timer: ReturnType<typeof setTimeout>;
    const load = async () => {
      try {
        const value = await riskGet<RiskRun>(`/runs/${id}`);
        if (!active) return; setRun(value);
        if (['queued', 'running'].includes(value.status)) timer = setTimeout(load, 2000);
        else action.current?.reload();
      } catch { /* 统一请求层提示错误，保留手动刷新入口。 */ }
    };
    setRun(undefined); setKind('hit'); load();
    return () => { active = false; clearTimeout(timer); };
  }, [id]);
  return <PageContainer title="运行记录" subTitle="查看每次运行的范围、版本、进度与计算结果">
    {workerState && (!workerState.alive || !workerState.run_enabled) && <Alert style={{ marginBottom: 16 }} type="warning" showIcon message={!workerState.alive ? '计算后台离线，任务将在后台恢复后执行' : '模型运行已暂停，待执行任务已保留'} />}
    <ProTable<RiskRun> rowKey="id" actionRef={action} search={tableSearch} cardBordered={tableCards} pagination={{ defaultPageSize: 10 }}
      locale={{ emptyText: '暂未查到符合条件的运行记录，请调整筛选条件' }}
      request={async p => { const r = await riskGet('/runs', { model_name: p.model_name, version_number: p.version_number, mode: p.mode, status: p.status, page: p.current, page_size: p.pageSize }); return { data: r.items, total: r.total, success: true }; }}
      columns={[
        { title: '模型名称', dataIndex: 'model_name' }, { title: '版本号', dataIndex: 'version_number', valueType: 'digit', fieldProps: { min: 1, precision: 0, placeholder: '如 1 表示 V1' }, width: 75, render: (_, r) => `V${r.version_number}` },
        { title: '运行方式', dataIndex: 'mode', valueType: 'select', valueEnum: Object.fromEntries(['trial', 'formal', 'compare'].map(k => [k, { text: labels[k] }])), width: 95, render: (_, r) => <Tag color={r.mode === 'formal' ? 'blue' : 'default'}>{labels[r.mode]}</Tag> },
        { title: '分析期间', hideInSearch: true, render: (_, r) => `${r.scope.start_date} ～ ${r.scope.end_date}` },
        { title: '运行状态', dataIndex: 'status', valueType: 'select', valueEnum: Object.fromEntries(['queued', 'running', 'succeeded', 'partial_failed', 'failed', 'cancelled'].map(k => [k, { text: labels[k] }])), width: 100, render: (_, r) => <Tag color={r.status === 'succeeded' ? 'green' : r.status === 'failed' ? 'red' : r.status === 'partial_failed' ? 'orange' : 'blue'}>{labels[r.status]}</Tag> },
        { title: '命中 / 扫描', hideInSearch: true, width: 110, render: (_, r) => r.counts.scanned !== undefined ? `${r.counts.hit} / ${r.counts.scanned}` : '-' },
        { title: '触发来源', hideInSearch: true, render: (_, r) => (r.scope as any).source === 'schedule' ? '定时计划' : (r.scope as any).source === 'schedule_manual' ? '计划立即执行' : '手动' },
        { title: '触发时间', hideInSearch: true, render: (_, r) => timeText(r.created_at) },
        { title: '操作', hideInSearch: true, width: 90, render: (_, r) => <Button type="link" onClick={() => setId(r.id)}>查看结果</Button> },
      ]} />
    <Drawer title="运行详情" width="min(1120px, 95vw)" open={!!id} onClose={() => setId(undefined)}
      extra={<Space>{run && ['failed', 'partial_failed'].includes(run.status) && <Button onClick={async () => { await riskPost(`/runs/${id}/retry`); setId(undefined); setTimeout(() => setId(run.id), 0); }}>仅补跑失败批次</Button>}{run && ['queued', 'running'].includes(run.status) && <Button disabled={run.cancel_requested} onClick={async () => { const r = await riskPost<RiskRun>(`/runs/${id}/cancel`); setRun(r); }}>{run.cancel_requested ? '取消中' : '取消运行'}</Button>}
        <Button onClick={async () => { if (id) setRun(await riskGet(`/runs/${id}`)); }}>刷新</Button></Space>}>
      {!run ? <Spin /> : <>
        <Alert type={run.status === 'failed' ? 'error' : run.status === 'partial_failed' ? 'warning' : 'info'} showIcon message={`${labels[run.status]} · ${run.stage}`} description={run.error} style={{ marginBottom: 16 }} />
        {run.counts.batches && <><Progress percent={Math.round((run.counts.batches.succeeded + run.counts.batches.failed + run.counts.batches.cancelled) / Math.max(1, run.counts.batches_total) * 100)}
          format={() => `${run.counts.batches.succeeded + run.counts.batches.failed + run.counts.batches.cancelled}/${run.counts.batches_total} 批结束，${run.counts.batches.succeeded} 成功`} />
          <Typography.Paragraph type="secondary">按公司和日期逐页发现后续批次，总数可能增长；已成功批次的结果已保留。</Typography.Paragraph></>}
        <ProTable rowKey="id" search={false} options={false} size="small" params={{ runId: run.id, updated: run.stage }} pagination={{ defaultPageSize: 5 }}
          request={async p => { const r = await riskGet(`/runs/${p.runId}/batches`, { page: p.current, page_size: p.pageSize }); return { data: r.items, total: r.total, success: true }; }}
          columns={[{ title: '公司', dataIndex: 'company' }, { title: '日期', dataIndex: 'day' }, { title: '页', dataIndex: 'page' },
            { title: '状态', render: (_, r) => labels[r.status] || r.status }, { title: '尝试次数', dataIndex: 'attempt' },
            { title: '错误', dataIndex: 'error', ellipsis: true }, { title: '操作', render: (_, r) => <Button type="link" onClick={async () => setAttempts(await riskGet(`/batches/${r.id}/attempts`))}>尝试记录</Button> }]} />
        <Descriptions column={2} size="small" items={[
          { key: 'model', label: '模型版本', children: `${run.model_name} V${run.version_number}` }, { key: 'mode', label: '运行方式', children: labels[run.mode] },
          { key: 'scope', label: '分析范围', children: `${run.scope.start_date} ～ ${run.scope.end_date} / ${run.scope.com_ids.join('、')}`, span: 2 },
          { key: 'config', label: '本次判断条件', children: configText(run.snapshot), span: 2 },
          ...(run.baseline ? [{ key: 'base', label: '基准条件', children: configText(run.baseline), span: 2 }] : []),
          { key: 'read', label: '证据读取时间范围', children: `${timeText(run.counts.read_started_at || run.counts.read_at)} ～ ${timeText(run.counts.read_at)}`, span: 2 },
          { key: 'water', label: '源数据截止', children: run.counts.data_cutoff || '未知，不能以任务时间替代', span: 2 },
          { key: 'start', label: '开始', children: timeText(run.started_at) }, { key: 'end', label: '结束', children: timeText(run.ended_at) },
        ]} />
        {run.counts.scanned !== undefined && <>
          <Space wrap style={{ marginBottom: 20 }}>
            <Tag>扫描 {run.counts.scanned} 次拜访</Tag><Tag color="orange">命中 {run.counts.hit}</Tag><Tag>不可判断 {run.counts.unknown}</Tag><Tag>指标资料不足 {run.counts.quality_unknown}</Tag>
            <Tag>涉及客户 {run.counts.customers}</Tag><Tag>涉及经理 {run.counts.managers}</Tag><Tag>新增预警 {run.counts.new_alerts}</Tag><Tag>已有预警 {run.counts.existing_alerts}</Tag><Tag>已关闭旧事件重命中 {run.counts.closed_rematches}</Tag>
            {run.baseline && <><Tag color="blue">基准命中 {run.counts.baseline_hit}</Tag><Tag color="orange">新增 {run.counts.new}</Tag><Tag color="green">减少 {run.counts.removed}</Tag><Tag>共同命中 {run.counts.common}</Tag></>}
          </Space>
          <Segmented value={kind} onChange={value => setKind(String(value))} options={[
            { label: '命中事件', value: 'hit' }, { label: '不可判断', value: 'unknown' }, { label: '全部事件', value: 'all' },
            ...(run.baseline ? [{ label: '相对基准新增', value: 'new' }, { label: '相对基准减少', value: 'removed' }] : []),
          ]} />
          <ProTable<RiskItem> rowKey="id" search={false} options={false} params={{ runId: run.id, kind }} pagination={{ pageSize: 10 }}
            locale={{ emptyText: '暂未查到符合条件的数据' }}
            request={async p => { const r = await riskGet(`/runs/${run.id}/items`, { kind: p.kind, page: p.current, page_size: p.pageSize }); return { data: r.items, total: r.total, success: true }; }}
            columns={[
              { title: '客户', render: (_, r) => r.evidence.cust_name, ellipsis: true }, { title: '客户经理', render: (_, r) => r.evidence.person_name, width: 90 },
              { title: '拜访日期', render: (_, r) => visitDateText(r.evidence.event_time), width: 115 }, { title: '时长（秒）', render: (_, r) => r.evidence.visit_time ?? '-', width: 100 },
              { title: '距离（米）', render: (_, r) => r.evidence.distance_meters?.toFixed(2) ?? '-', width: 105 },
              { title: '结果', render: (_, r) => labels[r.outcome], width: 85 }, { title: '操作', render: (_, r) => <Button type="link" onClick={() => setEvidence(r)}>证据</Button>, width: 65 },
            ]} />
        </>}
      </>}
    </Drawer>
    <Drawer title="批次尝试记录" open={!!attempts} onClose={() => setAttempts(undefined)} width={760}><Table rowKey="id" dataSource={attempts} columns={[{ title: '次数', dataIndex: 'number' }, { title: '状态', render: (_, r) => labels[r.status] || r.status }, { title: '开始', dataIndex: 'started_at', render: timeText }, { title: '错误', dataIndex: 'error' }]} /></Drawer>
    <Drawer title="事件证据" width={680} open={!!evidence} onClose={() => setEvidence(undefined)}>{evidence && <Evidence item={evidence} />}</Drawer>
  </PageContainer>;
}
