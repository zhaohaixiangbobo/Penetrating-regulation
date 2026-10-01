/** 营销审计查询契约：统一分页响应、业务请求以及对应导出请求。 */
import { request } from '@umijs/max';

export interface Paged<T> {
    total: number;
    page: number;
    page_size: number;
    items: T[];
}

export interface AuditQueryRequest {
    com_ids: string[];
    start_date: string; // YYYY-MM-DD
    end_date: string;
    page?: number;
    page_size?: number;
}

export interface DailyUnderHourRequest extends AuditQueryRequest {
    sdpt_name?: string;
    person_uuid?: string;
    threshold_minutes?: number;
    sort_field?: 'v_date';
    sort_order?: 'ascend' | 'descend';
}

export interface ShortVisitQueryRequest extends AuditQueryRequest {
    person_name?: string;
    threshold_seconds?: number;
    sort_field?: 'plan_date' | 'visit_time';
    sort_order?: 'ascend' | 'descend';
}

export interface MonthlyQueryRequest {
    com_ids: string[];
    start_month: string; // YYYY-MM-DD
    end_month: string;
    sdpt_name?: string;
    person_uuid?: string;
    page?: number;
    page_size?: number;
    sort_field?: 'year_month';
    sort_order?: 'ascend' | 'descend';
}

export interface ShortVisitRow {
    com_id?: string;
    short_name?: string;
    license_code?: string;
    cust_name?: string;
    sdpt_name?: string;
    person_name?: string;
    plan_date?: string;
    visit_time?: number;
}

export interface FullCustMissRow {
    year_month?: string; // 'YYYYMM'
    short_name?: string;
    cust_code?: string;
    cust_name?: string;
    sdpt_name?: string;
    person_name?: string;
}

export interface DailyUnderHourRow {
    v_date?: string;
    com_id?: string;
    short_name?: string;
    sdpt_name?: string;
    cust_manager_person_uuid?: string;
    person_name?: string;
    visit_minutes?: number;
}

export function queryShortVisit(payload: ShortVisitQueryRequest) {
    return request<Paged<ShortVisitRow>>('/api/audit/short-visit', { method: 'POST', data: payload });
}

export function queryFullCustMiss(payload: MonthlyQueryRequest) {
    return request<Paged<FullCustMissRow>>('/api/audit/full-cust-miss', { method: 'POST', data: payload });
}

export function queryDailyUnderHour(payload: DailyUnderHourRequest) {
    return request<Paged<DailyUnderHourRow>>('/api/audit/daily-under-hour', { method: 'POST', data: payload });
}

// ---------- 导出接口（全量数据） ----------

export function exportShortVisit(payload: ShortVisitQueryRequest) {
    return request<ShortVisitRow[]>('/api/audit/short-visit/export', { method: 'POST', data: payload });
}

export function exportFullCustMiss(payload: MonthlyQueryRequest) {
    return request<FullCustMissRow[]>('/api/audit/full-cust-miss/export', { method: 'POST', data: payload });
}

export function exportDailyUnderHour(payload: DailyUnderHourRequest) {
    return request<DailyUnderHourRow[]>('/api/audit/daily-under-hour/export', { method: 'POST', data: payload });
}

export interface LongVisitRequest extends AuditQueryRequest {
    threshold_minutes?: number;
    sdpt_name?: string;
    person_uuid?: string;
    sort_field?: 'v_date' | 'visit_minutes';
    sort_order?: 'ascend' | 'descend';
}

export interface LongVisitRow {
    visit_id?: string;
    v_date?: string;
    visit_timestamp?: string;
    com_id?: string;
    short_name?: string;
    sdpt_name?: string;
    cust_manager_person_uuid?: string;
    person_name?: string;
    cust_uuid?: string;
    license_code?: string;
    cust_name?: string;
    visit_minutes?: number;
}

export interface AutoCollectMissRow extends FullCustMissRow {
    com_id?: string;
    cust_uuid?: string;
    mgr_id?: string;
}

export function queryLongVisit(payload: LongVisitRequest) {
    return request<Paged<LongVisitRow>>('/api/audit/long-visit', { method: 'POST', data: payload });
}

export function exportLongVisit(payload: LongVisitRequest) {
    return request<LongVisitRow[]>('/api/audit/long-visit/export', { method: 'POST', data: payload });
}

export function queryAutoCollectMiss(payload: MonthlyQueryRequest) {
    return request<Paged<AutoCollectMissRow>>('/api/audit/auto-collect-miss', { method: 'POST', data: payload });
}

export function exportAutoCollectMiss(payload: MonthlyQueryRequest) {
    return request<AutoCollectMissRow[]>('/api/audit/auto-collect-miss/export', { method: 'POST', data: payload });
}
