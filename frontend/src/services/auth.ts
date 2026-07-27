import { request } from '@umijs/max';

export interface LoginRequest {
    username: string;
    password: string;
}

export interface LoginResponse {
    access_token: string;
    token_type: string;
    username: string;
}

export interface MeResponse {
    username: string;
}

export async function login(payload: LoginRequest) {
    return request<LoginResponse>('/api/auth/login', {
        method: 'POST',
        data: payload,
    });
}

export async function getMe() {
    return request<MeResponse>('/api/auth/me', { method: 'GET' });
}

export interface CompanyItem {
    com_id: string;
    short_name: string;
}

export async function listCompanies() {
    return request<CompanyItem[]>('/api/meta/companies', { method: 'GET' });
}

export interface EmployeeMember {
    person_uuid: string;
    person_name: string;
}

export interface EmployeeGroup {
    sdpt_name: string;
    members: EmployeeMember[];
}

export async function listEmployees(com_ids: string[]) {
    return request<EmployeeGroup[]>('/api/meta/employees', {
        method: 'GET',
        params: { com_ids: com_ids.join(',') },
    });
}
