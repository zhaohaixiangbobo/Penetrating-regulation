/**
 * Umi 运行时配置：
 *  - request: 统一附加 Authorization、401 拦截跳登录
 *  - layout: 顶部展示用户 & 退出
 *  - initialState: 拉 /api/auth/me 作为当前用户
 */
import { history, RequestConfig, RunTimeLayoutConfig } from '@umijs/max';
import { LogoutOutlined, DownOutlined, UserOutlined } from '@ant-design/icons';
import { Dropdown, message, Space } from 'antd';
import { getMe } from '@/services/auth';

const TOKEN_KEY = 'shenji_token';

export async function getInitialState(): Promise<{ currentUser?: { username: string } }> {
    if (history.location.pathname.startsWith('/user/login')) {
        return {};
    }
    const token = localStorage.getItem(TOKEN_KEY);
    if (!token) {
        history.replace('/user/login');
        return {};
    }
    try {
        const me = await getMe();
        return { currentUser: me };
    } catch {
        localStorage.removeItem(TOKEN_KEY);
        history.replace('/user/login');
        return {};
    }
}

export const request: RequestConfig = {
    timeout: 30000,
    headers: { 'Content-Type': 'application/json' },
    errorConfig: {
        errorHandler(error: any) {
            const status = error?.response?.status;
            const url: string = error?.response?.config?.url || error?.config?.url || '';
            const detail = error?.response?.data?.detail || error?.message || '请求失败';
            const detailText = typeof detail === 'string' ? detail : JSON.stringify(detail);
            // 登录接口 401：仅提示服务端返回的具体原因（如「密码错误，请重新输入」），不跳转
            if (status === 401 && url.includes('/api/auth/login')) {
                message.error(detailText);
                return;
            }
            // 其它接口 401：视为令牌失效，跳登录页
            if (status === 401) {
                localStorage.removeItem(TOKEN_KEY);
                message.warning('登录已过期，请重新登录');
                history.replace('/user/login');
                return;
            }
            message.error(detailText);
            console.error('[Request Error]', status, detail, error);
        },
    },
    requestInterceptors: [
        (config: any) => {
            const token = localStorage.getItem(TOKEN_KEY);
            if (token) {
                config.headers = config.headers || {};
                config.headers.Authorization = `Bearer ${token}`;
            }
            return config;
        },
    ],
    responseInterceptors: [
        (response: any) => {
            console.log('[Response]', response.config?.url, response.status, response.data);
            return response;
        },
    ],
};

const doLogout = () => {
    localStorage.removeItem(TOKEN_KEY);
    history.replace('/user/login');
};

export const layout: RunTimeLayoutConfig = ({ initialState }) => {
    return {
        title: '穿透式监督查询系统',
        logo: false,
        layout: 'side',
        fixedHeader: true,
        fixSiderbar: true,
        siderWidth: 220,
        // 自定义 sider 顶部标题：展开时「穿透式监督查询系统」居中放大；折叠时显示「穿透」两字
        menuHeaderRender: (_logo, _title, props) => {
            const collapsed = (props as any)?.collapsed;
            return (
                <div
                    style={{
                        width: '100%',
                        height: '100%',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        color: '#ffffff',
                        fontWeight: 700,
                        letterSpacing: collapsed ? '2px' : '1px',
                        fontSize: collapsed ? 18 : 20,
                        lineHeight: 1,
                        userSelect: 'none',
                    }}
                >
                    {collapsed ? '穿透' : '穿透式监督查询系统'}
                </div>
            );
        },
        // 菜单项用 span 渲染（不用 <a>），消除浏览器左下角的 URL 路由预览提示
        menuItemRender: (item: any, dom: any) => (
            <span
                onClick={() => {
                    if (item.path) history.push(item.path);
                }}
                style={{ display: 'block', cursor: 'pointer' }}
            >
                {dom}
            </span>
        ),
        // 深色侧边栏配色 —— 使用 token.sider 精确覆盖
        token: {
            sider: {
                colorMenuBackground: '#0f172a',
                colorTextMenu: 'rgba(226, 232, 240, 0.72)',
                colorTextMenuSelected: '#ffffff',
                colorBgMenuItemSelected: '#2563eb',
                // hover 完全无背景块，仅文字变亮（配合 global.css）
                colorBgMenuItemHover: 'transparent',
                colorTextMenuItemHover: '#ffffff',
                colorTextMenuActive: '#ffffff',
                colorBgMenuItemActive: '#2563eb',
                colorTextSubMenuSelected: '#ffffff',
                colorTextMenuTitle: '#ffffff',
                colorMenuItemDivider: 'rgba(255, 255, 255, 0.08)',
                // 折叠状态：完全去掉蓝色/高亮容器背景，只保留图标本身
                colorBgMenuItemCollapsedElevated: 'transparent',
                colorBgMenuItemCollapsedSelected: 'transparent',
                colorBgMenuItemCollapsedHover: 'transparent',
                colorBgCollapsedButton: 'transparent',
                colorTextCollapsedButton: 'rgba(226, 232, 240, 0.75)',
                colorTextCollapsedButtonHover: '#ffffff',
            },
        },
        // 右上角用户区改为下拉菜单，退出更醒目
        avatarProps: {
            icon: <UserOutlined />,
            size: 'small',
            title: initialState?.currentUser?.username || '未登录',
            render: (_props, dom) => (
                <Dropdown
                    menu={{
                        items: [
                            {
                                key: 'logout',
                                icon: <LogoutOutlined />,
                                label: '退出登录',
                                danger: true,
                                onClick: doLogout,
                            },
                        ],
                    }}
                    placement="bottomRight"
                >
                    <Space size={4} style={{ cursor: 'pointer', padding: '0 8px' }}>
                        {dom}
                        <DownOutlined style={{ fontSize: 10, color: '#94a3b8' }} />
                    </Space>
                </Dropdown>
            ),
        },
        // 退出登录已整合到头像下拉菜单，右上角不再重复按钮
        actionsRender: () => [],
    };
};

// antd 运行时主题：现代调色板、字体栈、表格精细化
export const antd = (memo: any) => {
    memo.theme ??= {};
    memo.theme.token ??= {};
    memo.theme.token.colorPrimary = '#2563eb';
    memo.theme.token.colorInfo = '#2563eb';
    memo.theme.token.colorText = '#1e293b';
    memo.theme.token.colorTextSecondary = '#64748b';
    memo.theme.token.borderRadius = 8;
    memo.theme.token.fontFamily =
        "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', 'Helvetica Neue', Helvetica, Arial, sans-serif";
    memo.theme.components ??= {};
    memo.theme.components.Table = {
        headerBg: '#f8fafc',
        headerColor: '#334155',
        headerSplitColor: 'transparent',
        borderColor: '#eef2f6',
        rowHoverBg: '#eff6ff',
        cellPaddingBlock: 15,
        ...(memo.theme.components.Table || {}),
    };
    return memo;
};
