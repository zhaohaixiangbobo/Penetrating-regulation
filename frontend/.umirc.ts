import { defineConfig } from '@umijs/max';

export default defineConfig({
    npmClient: 'npm',
    title: '穿透式监督查询系统',
    // 兼容奇安信等政企浏览器（Chromium 69~86 内核）。
    // Umi 默认 targets 为 chrome 80；降到 69 以确保 JS 语法转译 + CSS 前缀覆盖最低内核。
    targets: { chrome: 69 },
    antd: {
        configProvider: {},
        // Ant Design 5 默认用 :where(.css-hash) 包裹全部组件样式（需 Chrome 88+），
        // 奇安信浏览器内核低于 88 时会整体跳过这些规则，导致样式大面积丢失。
        // hashPriority: 'high' 改用普通 .css-hash 类选择器（全内核兼容）；
        // legacyTransformer: true 将 CSS 逻辑属性（inset-block-start 等）转为旧写法。
        styleProvider: {
            hashPriority: 'high',
            legacyTransformer: true,
        },
    },
    layout: {
        title: '穿透式监督查询系统',
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
            name: '营销审计',
            icon: 'SecurityScanOutlined',
            routes: [
                { path: '/audit/short-visit', name: '短拜访记录', component: './Audit/ShortVisit' },
                { path: '/audit/full-cust-miss', name: '全商品缺访客户', component: './Audit/FullCustMiss' },
                { path: '/audit/daily-under-hour', name: '日拜访不足', component: './Audit/DailyUnderHour' },
            ],
        },
        {
            path: '/dashboard',
            name: '数据看板',
            icon: 'DashboardOutlined',
            component: './Dashboard',
        },
        {
            path: '/feedback',
            name: '审计线索反馈',
            icon: 'BulbOutlined',
            routes: [
                { path: '/feedback', redirect: '/feedback/mine' },
                { path: '/feedback/mine', name: '线索反馈', component: './Feedback/Mine' },
                { path: '/feedback/manage', name: '线索管理', component: './Feedback/Manage', access: 'isAdmin' },
            ],
        },
    ],
});
