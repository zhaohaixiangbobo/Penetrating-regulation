import { request } from '@umijs/max';

// 线索类型与状态取值（与后端 config 常量保持一致）
export const CLUE_CATEGORIES = ['拜访异常', '资料造假', '违规经营', '其他'] as const;
export type ClueCategory = (typeof CLUE_CATEGORIES)[number];

export type ClueStatus = 'pending' | 'processing' | 'done';
export const CLUE_STATUS_LABELS: Record<ClueStatus, string> = {
    pending: '待处理',
    processing: '处理中',
    done: '已处理',
};

export interface Paged<T> {
    total: number;
    page: number;
    page_size: number;
    items: T[];
}

export interface ClueCreateRequest {
    title: string;
    category: ClueCategory;
    com_id?: string;
    involved_dept?: string;
    involved_manager?: string;
    involved_customer?: string;
    content: string;
}

export interface ClueHandleRequest {
    status: ClueStatus;
    handle_remark?: string;
}

export interface ClueAttachmentRow {
    id: number;
    original_name: string;
    size: number;
    content_type?: string;
    uploaded_by: string;
    created_at: string;
}

export interface ClueHandleLogRow {
    id: number;
    from_status?: string;
    to_status: string;
    remark?: string;
    handled_by: string;
    created_at: string;
}

export interface ClueRow {
    id: number;
    title: string;
    category: string;
    com_id?: string;
    short_name?: string;
    involved_dept?: string;
    involved_manager?: string;
    involved_customer?: string;
    status: ClueStatus;
    status_label: string;
    created_by: string;
    created_at: string;
    updated_at: string;
    handled_by?: string;
    handled_at?: string;
    attachment_count: number;
}

export interface ClueDetail extends ClueRow {
    content: string;
    handle_remark?: string;
    attachments: ClueAttachmentRow[];
    handle_logs: ClueHandleLogRow[];
}

// ---------- 线索 CRUD ----------

export function submitClue(payload: ClueCreateRequest) {
    return request<ClueDetail>('/api/feedback/clues', { method: 'POST', data: payload });
}

export function listMyClues(params: { status?: string; order?: 'asc' | 'desc'; page?: number; page_size?: number }) {
    return request<Paged<ClueRow>>('/api/feedback/clues/mine', { method: 'GET', params });
}

export function listAllClues(params: {
    status?: string;
    com_id?: string;
    created_by?: string;
    keyword?: string;
    order?: 'asc' | 'desc';
    page?: number;
    page_size?: number;
}) {
    return request<Paged<ClueRow>>('/api/feedback/clues', { method: 'GET', params });
}

export function getClue(id: number) {
    return request<ClueDetail>(`/api/feedback/clues/${id}`, { method: 'GET' });
}

/**
 * 统一格式化提交/处理时间：只保留到「年-月-日 时:分」。
 * 后端返回形如 2026-09-20T03:28:38.237036，这里按字符串截取，避免时区偏移。
 */
export function formatClueTime(s?: string): string {
    if (!s) return '-';
    return s.slice(0, 16).replace('T', ' ');
}

export function handleClue(id: number, payload: ClueHandleRequest) {
    return request<ClueDetail>(`/api/feedback/clues/${id}/handle`, { method: 'PATCH', data: payload });
}

// ---------- 附件：上传 / 下载 ----------

/**
 * 上传附件：传入已组装好的 FormData，并显式把 Content-Type 置空，
 * 让 axios/浏览器自动生成带 boundary 的 multipart/form-data，
 * 避开 app.tsx 中全局写死的 application/json。
 */
export function uploadClueAttachment(clueId: number, file: File) {
    const form = new FormData();
    form.append('file', file);
    return request<ClueAttachmentRow>(`/api/feedback/clues/${clueId}/attachments`, {
        method: 'POST',
        data: form,
        headers: { 'Content-Type': undefined as any },
    });
}

/** 下载附件：以 blob 方式携带 Authorization 拉取，再触发浏览器下载。 */
export async function downloadClueAttachment(
    clueId: number,
    attachmentId: number,
    filename: string,
) {
    const blob = await request<Blob>(
        `/api/feedback/clues/${clueId}/attachments/${attachmentId}`,
        { method: 'GET', responseType: 'blob' },
    );
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
}

/** 获取附件的 blob 预览地址（用于图片预览），调用方负责 revokeObjectURL。 */
export async function fetchAttachmentObjectURL(clueId: number, attachmentId: number) {
    const blob = await request<Blob>(
        `/api/feedback/clues/${clueId}/attachments/${attachmentId}`,
        { method: 'GET', responseType: 'blob' },
    );
    return URL.createObjectURL(blob);
}
