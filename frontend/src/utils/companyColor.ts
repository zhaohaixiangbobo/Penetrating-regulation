/**
 * 公司标签配色：根据公司名/编码稳定映射到 antd Tag 预设色。
 * 同一公司在任意页面、任意会话中都得到同一颜色；不同公司自动错开。
 */

// antd Tag 支持的预设色板（去掉过浅/过深的），按视觉区分度排序
const PALETTE = [
    'geekblue',
    'magenta',
    'volcano',
    'green',
    'purple',
    'orange',
    'cyan',
    'gold',
    'blue',
    'lime',
    'red',
] as const;

export type CompanyTagColor = (typeof PALETTE)[number];

/**
 * 简单字符串哈希（djb2 变种），保证同一入参恒定输出到同一色。
 */
function hashString(input: string): number {
    let h = 5381;
    for (let i = 0; i < input.length; i++) {
        h = ((h << 5) + h) ^ input.charCodeAt(i); // h * 33 XOR c
    }
    return h >>> 0; // 转无符号 32 位整数
}

export function getCompanyTagColor(key?: string | null): CompanyTagColor {
    if (!key) return 'geekblue';
    return PALETTE[hashString(key) % PALETTE.length];
}
