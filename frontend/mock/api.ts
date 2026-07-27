// 前端联调用假数据：设置 NODE_ENV=development 并启用 mock 时生效
// UmiJS 4 mock：默认从 mock/ 目录读取
export default {
  'POST /api/auth/login': (_req: any, res: any) => {
    res.send({ access_token: 'mock-token', token_type: 'bearer', username: 'admin' });
  },
  'GET /api/auth/me': { username: 'admin' },
  'GET /api/meta/companies': [
    { com_id: '11120101', short_name: '第一' },
    { com_id: '11120102', short_name: '第二' },
    { com_id: '11120103', short_name: '第三' },
  ],
  'POST /api/audit/short-visit': {
    total: 1,
    page: 1,
    page_size: 20,
    items: [
      {
        com_id: '11120101',
        short_name: '第一',
        cust_code: 'MOCK001',
        license_code: 'L001',
        cust_name: '示例客户',
        terminal_level: '3',
        person_name: '张三',
        plan_date: '2024-06-01',
        visit_time: 45,
      },
    ],
  },
  'POST /api/audit/full-cust-miss': { total: 0, page: 1, page_size: 20, items: [] },
  'POST /api/audit/daily-under-hour': {
    total: 1,
    page: 1,
    page_size: 20,
    items: [
      {
        v_date: '2024-06-01',
        com_id: '11120101',
        short_name: '第一',
        sdpt_name: '营销部',
        cust_manager_person_uuid: 'u-1',
        person_name: '李四',
        visit_minutes: 30.5,
      },
    ],
  },
};
