/** 指标目录：展示版本、计算依据和数据质量边界。 */
import { useState } from 'react';
import { PageContainer, ProTable } from '@ant-design/pro-components';
import { Button, Descriptions, Drawer, Tag } from 'antd';
import { riskGet } from '@/services/risk';

export default function Indicators() {
  const [detail, setDetail] = useState<any>();
  return <PageContainer title="指标管理" subTitle="统一计算依据，模型分别配置判断条件">
    <ProTable rowKey="code" search={false} pagination={false} request={async () => ({ data: await riskGet('/indicators'), success: true })}
      columns={[
        { title: '指标名称', dataIndex: 'name' }, { title: '指标代码', dataIndex: 'code', copyable: true },
        { title: '单位', dataIndex: 'unit', width: 80 }, { title: '分析粒度', dataIndex: 'evaluation_unit', width: 120 },
        { title: '版本', dataIndex: 'version', width: 90, render: (_, r) => <Tag color="blue">V{r.version}</Tag> },
        { title: '操作', width: 100, render: (_, r) => <Button type="link" onClick={() => setDetail(r)}>查看定义</Button> },
      ]} />
    <Drawer title={detail?.name} width={620} open={!!detail} onClose={() => setDetail(undefined)}>
      {detail && <Descriptions column={1} bordered items={[
        { key: 'code', label: '代码', children: detail.code }, { key: 'version', label: '计算版本', children: `V${detail.version}` },
        { key: 'formula', label: '计算方式', children: detail.formula }, { key: 'source', label: '数据来源', children: detail.source },
        { key: 'quality', label: '数据口径', children: detail.quality },
        { key: 'threshold', label: '判断阈值', children: '由模型版本单独配置；指标版本固定计算逻辑。' },
      ]} />}
    </Drawer>
  </PageContainer>;
}
