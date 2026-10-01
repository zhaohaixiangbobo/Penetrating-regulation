/** 专卖机关简称和公司色彩标签；完整名称在鼠标悬停时展示。 */
import { Tag } from 'antd';
import { getCompanyTagColor } from '@/utils/companyColor';

export function shortOrganization(name?: string) {
  // 市区各局使用“市区第…”简称，其他区局保留原有区名。
  return name?.replace(/^天津市/, '').replace(/烟草专卖局$/, '').replace(/^区第/, '市区第') || '-';
}

export default function IssuingOrgTag({ name }: { name?: string }) {
  const shortName = shortOrganization(name);
  return name ? <Tag title={name} color={getCompanyTagColor(shortName)}>{shortName}</Tag> : <>-</>;
}
