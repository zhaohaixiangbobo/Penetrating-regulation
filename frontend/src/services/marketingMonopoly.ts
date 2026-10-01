/** 营销专卖接口：发证机关字典、扣款户名与拜访定位查询及导出。 */
import { request } from '@umijs/max';
import type { Paged } from './audit';

export interface BankOwnerMismatchRequest {
  issue_org_codes?: string[];
  lic_no?: string;
  company_name?: string;
  start_date?: string;
  end_date?: string;
  sort_field?: 'sysupdatedt' | 'lic_no' | 'issue_org_name';
  sort_order?: 'ascend' | 'descend';
  page?: number;
  page_size?: number;
}

export interface BankOwnerMismatchRow {
  retailer_uuid?: string;
  custbank_uuid?: string;
  issue_org_code?: string;
  issue_org_name?: string;
  lic_no?: string;
  company_name?: string;
  manager_name?: string;
  bankcard_owner?: string;
  sysupdatedt?: string;
}

export interface IssuingOrganization {
  issue_org_code: string;
  issue_org_name: string;
}

export function listIssuingOrganizations() {
  return request<IssuingOrganization[]>('/api/marketing-monopoly/issuing-organizations', { method: 'GET' });
}

export function queryBankOwnerMismatch(payload: BankOwnerMismatchRequest) {
  return request<Paged<BankOwnerMismatchRow>>('/api/marketing-monopoly/bank-owner-mismatch', { method: 'POST', data: payload });
}

export function exportBankOwnerMismatch(payload: BankOwnerMismatchRequest) {
  return request<BankOwnerMismatchRow[]>('/api/marketing-monopoly/bank-owner-mismatch/export', { method: 'POST', data: payload });
}

export interface VisitLocationRequest extends Omit<BankOwnerMismatchRequest, 'sort_field' | 'start_date' | 'end_date'> {
  start_date: string;
  end_date: string;
  distance_meters?: number;
  sort_field?: 'plan_date' | 'distance_meters' | 'issue_org_name';
}

export interface VisitLocationRow {
  visit_id?: string;
  retailer_uuid?: string;
  issue_org_code?: string;
  issue_org_name?: string;
  person_name?: string;
  plan_date: string;
  cust_code?: string;
  cust_name?: string;
  longitude: number;
  latitude: number;
  gis_long: number;
  gis_lat: number;
  distance_meters: number;
}

export function queryVisitLocation(payload: VisitLocationRequest) {
  return request<Paged<VisitLocationRow>>('/api/marketing-monopoly/visit-location', { method: 'POST', data: payload });
}

export function exportVisitLocation(payload: VisitLocationRequest) {
  return request<VisitLocationRow[]>('/api/marketing-monopoly/visit-location/export', { method: 'POST', data: payload });
}
