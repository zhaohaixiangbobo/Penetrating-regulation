/** 同状态预警批量处置：逐条保留权限、版本校验及审计日志。 */
import { useState } from 'react';
import { Alert, Form, Input, Modal, Progress, Select, message } from 'antd';
import { labels, RiskAlert, riskPost, alertNumber } from '@/services/risk';

export const alertActions = (row: Pick<RiskAlert, 'status' | 'assigned_to'>, username?: string) => [
  ...(row.status === 'pending' ? ['start'] : []),
  ...(row.status === 'investigating' ? ['conclude'] : []),
  ...(row.status === 'rectifying' ? ['submit_rectification'] : []),
  ...(row.status === 'reviewing' ? [...(row.assigned_to !== username ? ['approve'] : []), 'return'] : []),
  ...(row.status === 'closed' ? ['reopen'] : []), 'supplement',
];
const actionLabels: Record<string, string> = { start: '开始核查', conclude: '提交核查结论', submit_rectification: '提交整改，申请复核', approve: '复核通过并关闭', return: '退回核查', reopen: '有新证据，重新核查', supplement: '补充说明' };

export default function RiskBatchAction({ rows, username, onClose, onDone }: {
  rows: RiskAlert[]; username?: string; onClose: () => void; onDone: () => void;
}) {
  const [form] = Form.useForm();
  const [running, setRunning] = useState(false);
  const [completed, setCompleted] = useState(0);
  const [result, setResult] = useState<{ success: number; failures: string[] }>();
  const chosen = Form.useWatch('action', form);
  const conclusion = Form.useWatch('conclusion', form);
  const sameStatus = rows.length > 0 && rows.every(r => r.status === rows[0].status);
  const actions = sameStatus ? alertActions(rows[0], username).filter(a => rows.every(r => alertActions(r, username).includes(a))) : [];
  const submit = async () => {
    if (!sameStatus) { message.warning('请选择同一状态的预警进行批量处理'); return; }
    const values = await form.validateFields();
    setRunning(true);
    const failures: string[] = []; let success = 0;
    // 单条提交保留已有服务端状态机与并发校验，明确报告部分成功，避免盲目重试成功项。
    for (let i = 0; i < rows.length; i++) {
      const row = rows[i];
      try { await riskPost(`/alerts/${row.id}/actions`, { ...values, revision: row.revision }); success++; }
      catch (error: any) { failures.push(`${alertNumber(row.id)}：${error?.response?.data?.detail || '提交失败，请刷新记录后重试'}`); }
      setCompleted(i + 1);
    }
    setResult({ success, failures }); setRunning(false); onDone();
  };
  return <Modal title={`批量处理 · ${rows.length} 条预警`} open onCancel={onClose} closable={!running} maskClosable={false}
    keyboard={!running} confirmLoading={running} okText={result ? '完成' : '提交处理'} okButtonProps={{ disabled: !result && !sameStatus }} cancelButtonProps={{ disabled: running }}
    onOk={result ? onClose : submit}>
    {result ? <Alert type={result.failures.length ? 'warning' : 'success'} showIcon message={`成功 ${result.success} 条，失败 ${result.failures.length} 条`}
      description={result.failures.map(text => <div key={text}>{text}</div>)} /> : <>
      <Alert type={sameStatus ? 'info' : 'warning'} showIcon message={sameStatus ? `所选预警均为“${labels[rows[0].status]}”，使用相同处理意见。` : '请选择同一状态的预警进行批量处理'} style={{ marginBottom: 16 }} />
      <Form form={form} layout="vertical" disabled={running}>
        <Form.Item name="action" label="处理操作" rules={[{ required: true }]}><Select options={actions.map(value => ({ value, label: actionLabels[value] }))} /></Form.Item>
        {chosen === 'conclude' && <Form.Item name="conclusion" label="核查结论" preserve={false} rules={[{ required: true }]}><Select options={['confirmed', 'reasonable', 'data_quality', 'insufficient', 'normal'].map(value => ({ value, label: labels[value] }))} /></Form.Item>}
        <Form.Item name="note" label="处理说明" rules={[{ required: true, min: 2, whitespace: true }]}><Input.TextArea rows={3} maxLength={5000} showCount /></Form.Item>
        <Form.Item name="measures" label="处置措施 / 数据修正要求" rules={[{ required: chosen === 'conclude' && ['confirmed', 'data_quality'].includes(conclusion), whitespace: true }]}><Input.TextArea rows={2} maxLength={5000} /></Form.Item>
      </Form>
    </>}
    {(running || result) && <Progress percent={Math.round(completed / rows.length * 100)} format={() => `${completed}/${rows.length}`} />}
  </Modal>;
}
