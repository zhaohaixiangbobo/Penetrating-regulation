/** 人工线索的反向预警关联，受风险模块能力及管理员权限控制。 */
import { useEffect, useState } from 'react';
import { history, useModel } from '@umijs/max';
import { Button, Divider, Typography } from 'antd';
import { alertNumber, riskGet, visitDateText } from '@/services/risk';
export default function RiskClueLinks({ clueId }: { clueId: number }) {
  const { initialState } = useModel('@@initialState');
  const [rows, setRows] = useState<any[]>([]);
  useEffect(() => { let active = true; setRows([]); if (initialState?.riskEnabled) riskGet<any[]>(`/clues/${clueId}/alerts`).then(r => { if (active) setRows(r); }).catch(() => {}); return () => { active = false; }; }, [clueId, initialState?.riskEnabled]);
  if (!initialState?.riskEnabled) return null;
  return <><Divider orientation="left">关联风险预警</Divider>{rows.length ? rows.map(r => <p key={r.id}><Button type="link" onClick={() => history.push(`/risk-alerts/ledger?alert=${r.id}`)}>{alertNumber(r.id)} {r.model_name} · {visitDateText(r.event_time)}</Button></p>) : <Typography.Text type="secondary">暂无关联预警</Typography.Text>}</>;
}
