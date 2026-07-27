import { defineConfig } from '@umijs/max';

export default defineConfig({
    npmClient: 'npm',
    title: '审计监管系统',
    antd: {
        configProvider: {},
    },
    layout: {
        title: '审计监管系统',
        locale: false,
    },
    request: {},
    initialState: {},
    model: {},
    access: {},
    hash: true,
    history: { type: 'browser' },
    mock: false,
    proxy: {
        '/api': {
            target: 'http://127.0.0.1:8000',
            changeOrigin: true,
        },
    },
    routes: [
        { path: '/', redirect: '/audit/short-visit' },
        { path: '/user/login', component: './User/Login', layout: false },
        {
            path: '/audit',
            name: '审计查询',
            icon: 'SecurityScanOutlined',
            routes: [
                { path: '/audit/short-visit', name: '短拜访记录', component: './Audit/ShortVisit' },
                { path: '/audit/full-cust-miss', name: '全商品缺访客户', component: './Audit/FullCustMiss' },
                { path: '/audit/daily-under-hour', name: '日拜访不足60分钟', component: './Audit/DailyUnderHour' },
            ],
        },
        {
            path: '/dashboard',
            name: '数据看板',
            icon: 'DashboardOutlined',
            component: './Dashboard',
        },
    ],
});
