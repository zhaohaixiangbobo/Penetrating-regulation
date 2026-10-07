/** 风险一期接口与展示词典；请求复用现有登录鉴权和错误处理。 */
import { request } from '@umijs/max';
export interface RiskCondition { indicator: string; version: number; operator: 'lt' | 'gt'; value: number }
export interface RiskConfig { evaluation_unit: 'visit_event'; combination: 'ALL' | 'ANY' | 'AT_LEAST_N'; minimum: number; conditions: RiskCondition[] }
export interface RiskVersion { id: number; model_id: number; number: number; published: boolean; config: RiskConfig; created_by: string; published_at?: string }
export interface RiskModel { id: number; name: string; enabled: boolean; versions: RiskVersion[] }
export interface RiskRun { id: string; model_id: number; model_name: string; version_number: number; mode: string; snapshot: RiskConfig; baseline?: RiskConfig; scope: { start_date: string; end_date: string; com_ids: string[] }; status: string; stage: string; error?: string; counts: Record<string, any>; created_by: string; created_at: string; started_at?: string; ended_at?: string; cancel_requested: boolean }
export interface RiskItem { id: number; outcome: string; baseline_outcome?: string; evidence: Record<string, any>; reasons: Record<string, any>[] }
export interface RiskAlert { id: number; model_name: string; cust_name: string; cust_code: string; person_name: string; short_name: string; event_time: string; status: string; conclusion?: string; revision: number; first_seen: string; last_seen: string; assigned_to?: string; recurrence: boolean; prior_alert_id?: number }
export const labels: Record<string, string> = { queued: '等待执行', running: '运行中', succeeded: '已完成', failed: '失败', cancelled: '已取消', pending: '待核查', investigating: '核查中', rectifying: '待整改', reviewing: '待复核', closed: '已关闭', confirmed: '确认问题', reasonable: '合理业务情形', data_quality: '数据质量问题', insufficient: '证据不足', normal: '核实正常', trial: '试算', formal: '正式运行', compare: '参数对比', hit: '命中', clear: '未命中', unknown: '不可判断' };
export const indicatorNames: Record<string, string> = { visit_duration_seconds: '拜访时长（秒）', visit_location_distance_meters: '定位距离（米）' };
export const conditionText = (c: RiskCondition) => `${indicatorNames[c.indicator]} ${c.operator === 'lt' ? '＜' : '＞'} ${c.value}`;
export const configText = (c: RiskConfig) => `${c.combination === 'ALL' ? '全部满足' : c.combination === 'ANY' ? '任一满足' : `至少满足 ${c.minimum} 项`}：${c.conditions.map(conditionText).join('；')}`;
export const riskGet = <T = any>(path: string, params?: any) => request<T>(`/api/risk${path}`, { params });
export const riskPost = <T = any>(path: string, data?: any, params?: any) => request<T>(`/api/risk${path}`, { method: 'POST', data, params });
export const timeText = (s?: string) => s ? s.replace('T', ' ').slice(0, 19) : '-';
export async function uploadRiskFile(id: number, file: File) {
  const data = new FormData(); data.append('file', file);
  return request(`/api/risk/alerts/${id}/attachments`, { method: 'POST', data, headers: { 'Content-Type': undefined as any } });
}
export async function downloadRiskFile(id: number, file: any) {
  const blob = await request<Blob>(`/api/risk/alerts/${id}/attachments/${file.id}`, { responseType: 'blob' });
  const url = URL.createObjectURL(blob); const a = document.createElement('a'); a.href = url; a.download = file.original_name; a.click(); URL.revokeObjectURL(url);
}

/** 台账与看板共用状态色，颜色与中文状态同时展示。 */
export const riskStatusColors: Record<string, string> = { pending: '#d48806', investigating: '#1677ff', rectifying: '#d46b08', reviewing: '#722ed1', closed: '#389e0d', failed: '#cf1322' };
/** 当前事件日期来自 plan_date，按日期精度展示；原始证据和事件主键保持完整。 */
export const visitDateText = (value?: string) => value ? value.slice(0, 10) : '-';

/** 预警展示编号稳定映射原主键，不影响历史关联及去重。 */
export const alertNumber = (id: number) => `FXYJ-${String(id).padStart(6, '0')}`;
