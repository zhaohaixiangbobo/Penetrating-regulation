/** 从可搜索、分页的审计线索列表选择关联，免去人工复制编号。 */
import { useState } from 'react';
import { Button, Modal, message } from 'antd';
import { ProTable } from '@ant-design/pro-components';
import { ClueRow, listAllClues, CLUE_STATUS_LABELS } from '@/services/feedback';
import { clueNumber } from '@/utils/clueNumber';
import { riskPost } from '@/services/risk';
import { tableSearch } from './UnifiedQueryFilter';

export default function RiskCluePicker({ alertId, linkedIds, onLinked }: { alertId: number; linkedIds: number[]; onLinked: () => Promise<void> }) {
  const [open, setOpen] = useState(false); const [saving, setSaving] = useState<number>();
  return <><Button onClick={() => setOpen(true)}>选择审计线索</Button>
    <Modal title="选择要关联的审计线索" open={open} width={900} footer={null} onCancel={() => setOpen(false)} destroyOnClose>
      <ProTable<ClueRow> rowKey="id" search={tableSearch} pagination={{ defaultPageSize: 10 }} options={false}
        locale={{ emptyText: '暂未查到符合条件的审计线索' }}
        request={async p => { const r = await listAllClues({ keyword: p.keyword, page: p.current, page_size: p.pageSize }); return { data: r.items, total: r.total, success: true }; }}
        columns={[
          { title: '线索标题/内容', dataIndex: 'keyword', hideInTable: true },
          { title: '线索编号', width: 145, hideInSearch: true, render: (_, r) => clueNumber(r.id) },
          { title: '标题', dataIndex: 'title', hideInSearch: true, ellipsis: true },
          { title: '公司', dataIndex: 'short_name', hideInSearch: true, width: 100 },
          { title: '状态', hideInSearch: true, width: 85, render: (_, r) => CLUE_STATUS_LABELS[r.status] },
          { title: '操作', hideInSearch: true, width: 90, render: (_, r) => <Button type="link" disabled={saving !== undefined || linkedIds.includes(r.id)} loading={saving === r.id}
            onClick={async () => { setSaving(r.id); try { await riskPost(`/alerts/${alertId}/clues/${r.id}`); await onLinked(); message.success('线索已关联'); setOpen(false); } finally { setSaving(undefined); } }}>{linkedIds.includes(r.id) ? '已关联' : '关联'}</Button> },
        ]} />
    </Modal></>;
}
