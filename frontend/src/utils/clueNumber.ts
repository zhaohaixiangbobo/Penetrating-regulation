/** 线索展示编号与内部主键转换：历史记录直接复用，关联接口继续使用数字主键。 */
export const clueNumber = (id: number) => `SJXS-${String(id).padStart(6, '0')}`;
export const parseClueNumber = (value: string): number | undefined => {
  const match = /^(?:SJXS-)?(\d+)$/i.exec(value.trim());
  const id = match ? Number(match[1]) : 0;
  return Number.isSafeInteger(id) && id > 0 ? id : undefined;
};
