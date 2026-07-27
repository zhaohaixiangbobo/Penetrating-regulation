/**
 * 简单的 localStorage 查询结果缓存工具（有效期 1 小时，仅缓存第 1 页）。
 *
 * 存储结构：
 *   key → { filter, items, total, page, pageSize, ts }
 */

const TTL = 60 * 60 * 1000; // 1h in ms

export interface PageCache<F, T> {
    filter: F;
    items: T[];
    total: number;
    page: number;
    pageSize: number;
    ts: number;
}

export function loadCache<F, T>(key: string): PageCache<F, T> | null {
    try {
        const raw = localStorage.getItem(key);
        if (!raw) {
            console.log('[Cache]', key, '无缓存');
            return null;
        }
        const entry: PageCache<F, T> = JSON.parse(raw);
        if (Date.now() - entry.ts > TTL) {
            localStorage.removeItem(key);
            console.log('[Cache]', key, '已过期');
            return null;
        }
        console.log('[Cache]', key, '恢复', entry.items.length, '条');
        return entry;
    } catch (e) {
        console.error('[Cache]', key, '读取失败', e);
        return null;
    }
}

export function saveCache<F, T>(
    key: string,
    filter: F,
    items: T[],
    total: number,
    page: number,
    pageSize: number,
): void {
    try {
        const entry: PageCache<F, T> = { filter, items, total, page, pageSize, ts: Date.now() };
        localStorage.setItem(key, JSON.stringify(entry));
        console.log('[Cache]', key, '保存', items.length, '条');
    } catch (e) {
        console.error('[Cache]', key, '保存失败', e);
    }
}
