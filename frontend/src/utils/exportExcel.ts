/**
 * Excel 导出工具：基于 SheetJS (xlsx)，纯前端生成 .xlsx 并触发下载。
 */
import * as XLSX from 'xlsx';

export interface ExportColumn {
    /** 表头中文名 */
    title: string;
    /** 数据字段名 */
    dataIndex: string;
}

/** 计算单元格显示宽度（CJK 字符按 2 宽度计） */
function cellWidth(val: unknown): number {
    const s = String(val ?? '');
    let w = 0;
    for (const ch of s) {
        w += ch.charCodeAt(0) > 255 ? 2 : 1;
    }
    return w;
}

/**
 * 将行数据导出为 xlsx 文件。
 * @param filename 文件名（不含扩展名）
 * @param columns  列定义（表头 + 字段）
 * @param rows     数据行
 */
export function exportToExcel<T extends object>(
    filename: string,
    columns: ExportColumn[],
    rows: T[],
): void {
    const header = columns.map((c) => c.title);
    const data = rows.map((r) =>
        columns.map((c) => ((r as Record<string, unknown>)[c.dataIndex] ?? '') as string | number),
    );

    const ws = XLSX.utils.aoa_to_sheet([header, ...data]);

    // 自动列宽：取表头与前 200 行数据的最大宽度（上限 50）
    ws['!cols'] = columns.map((c, i) => {
        let max = cellWidth(c.title);
        for (let k = 0; k < Math.min(data.length, 200); k++) {
            max = Math.max(max, cellWidth(data[k][i]));
        }
        return { wch: Math.min(max + 2, 50) };
    });

    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, ws, 'Sheet1');
    XLSX.writeFile(wb, `${filename}.xlsx`);
}
