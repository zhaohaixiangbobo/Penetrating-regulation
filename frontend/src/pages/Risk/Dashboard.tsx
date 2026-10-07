/** 风险看板：工作状态、风险分布、发现趋势与已复核结论。 */
import { useEffect, useState } from 'react';
import { PageContainer } from '@ant-design/pro-components';
import { Button, Card, Col, Empty, Row, Spin, Statistic, Table, Typography } from 'antd';
import ReactECharts from 'echarts-for-react';
import { riskStatusColors, labels, riskGet } from '@/services/risk';

export default function Dashboard() {
  const [data, setData] = useState<any>(); const [loading, setLoading] = useState(false);
  const load = async () => { setLoading(true); try { setData(await riskGet('/dashboard')); } finally { setLoading(false); } };
  useEffect(() => { load(); }, []);
  return <PageContainer title="风险看板" subTitle="预警事项按事件去重，统计范围为管理员试点数据" extra={<Button onClick={load}>刷新</Button>}>
    <Spin spinning={loading}>{data && <>
      <Row gutter={[16, 16]}>{['pending', 'investigating', 'rectifying', 'reviewing', 'closed'].map(key => <Col xs={12} md={8} xl={4} key={key}><Card><Statistic valueStyle={{ color: riskStatusColors[key] }} title={labels[key]} value={data.statuses[key] || 0} /></Card></Col>)}
        <Col xs={12} md={8} xl={4}><Card><Statistic valueStyle={{ color: riskStatusColors.failed }} title="失败运行" value={data.failed_runs} /></Card></Col></Row>
      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} lg={14}><Card title="新增预警趋势（发现日期）">{data.trends.length ? <ReactECharts style={{ height: 280 }} option={{ color: ['#2563eb'], tooltip: { trigger: 'axis' }, grid: { left: 45, right: 15, bottom: 35, top: 20 }, xAxis: { type: 'category', data: data.trends.map((d: any) => d.date) }, yAxis: { type: 'value', minInterval: 1 }, series: [{ type: 'bar', barMaxWidth: 36, data: data.trends.map((d: any) => d.total) }] }} /> : <Empty description="暂无预警数据" />}</Card></Col>
        <Col xs={24} lg={10}><Card title="核查结论分布"><Table size="small" rowKey="name" pagination={false} dataSource={Object.entries(data.conclusions).map(([k, total]) => ({ name: labels[k], total }))} columns={[{ title: '结论', dataIndex: 'name' }, { title: '事项数', dataIndex: 'total' }]} />
          <Statistic style={{ marginTop: 20 }} title="已关闭事项确认问题率" value={data.confirmed_rate ?? '-'} suffix={data.confirmed_rate === null ? undefined : '%'} />
          <Typography.Text type="secondary">已复核确认问题 {data.confirmed} / 已关闭 {data.closed}。未核查和证据不足不计作正常。</Typography.Text>
        </Card></Col>
        <Col span={24}><Card title="模型预警分布"><Table size="small" rowKey="name" pagination={false} dataSource={data.models} columns={[{ title: '风险模型', dataIndex: 'name' }, { title: '预警事项数', dataIndex: 'total' }]} /></Card></Col>
      </Row>
    </>}</Spin>
  </PageContainer>;
}
