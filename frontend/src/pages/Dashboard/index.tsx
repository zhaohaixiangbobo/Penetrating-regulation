import { PageContainer } from '@ant-design/pro-components';
import { Result } from 'antd';

export default function DashboardPage() {
  return (
    <PageContainer>
      <Result status="info" title="数据看板" subTitle="敬请期待——该模块将在后续版本上线" />
    </PageContainer>
  );
}
