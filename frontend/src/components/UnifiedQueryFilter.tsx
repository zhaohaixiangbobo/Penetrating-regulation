/** 统一查询筛选卡片：默认收起高级条件，标签按实际长度排布。 */
import type { ComponentProps } from 'react';
import { ProCard, QueryFilter } from '@ant-design/pro-components';

export const tableSearch = { labelWidth: 'auto' as const, defaultCollapsed: true };
export const tableCards = { search: true, table: true };

export default function UnifiedQueryFilter<T = Record<string, any>>(props: ComponentProps<typeof QueryFilter<T>>) {
  return <ProCard bordered style={{ marginBottom: 16 }}><QueryFilter<T> {...props} labelWidth="auto" defaultCollapsed /></ProCard>;
}
