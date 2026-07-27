import { useState } from 'react';
import { history, useModel } from '@umijs/max';
import { Button, Form, Input, message } from 'antd';
import { LockOutlined, UserOutlined } from '@ant-design/icons';
import { login } from '@/services/auth';
import styles from './index.less';

const TOKEN_KEY = 'shenji_token';

export default function LoginPage() {
    const [loading, setLoading] = useState(false);
    const { refresh } = useModel('@@initialState');

    const onFinish = async (values: { username: string; password: string }) => {
        setLoading(true);
        try {
            const res = await login(values);
            localStorage.setItem(TOKEN_KEY, res.access_token);
            message.success(`欢迎，${res.username}`);
            // 先跳转再 refresh，确保 getInitialState 读取的是新路径（非 /user/login）
            history.replace('/audit/short-visit');
            await refresh();
        } catch {
            // errorHandler 已弹窗
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className={styles.loginRoot}>
            <div className={`${styles.dot} ${styles.dot1}`} />
            <div className={`${styles.dot} ${styles.dot2}`} />
            <div className={styles.loginBox}>
                <div className={styles.card}>
                    <div className={styles.title}>审计监管系统</div>
                    <div className={styles.subtitle}>AUDIT MONITORING PLATFORM</div>
                    <Form layout="vertical" onFinish={onFinish} autoComplete="off" requiredMark={false}>
                        <Form.Item name="username" rules={[{ required: true, message: '请输入用户名' }]}>
                            <Input size="large" prefix={<UserOutlined />} placeholder="用户名" />
                        </Form.Item>
                        <Form.Item name="password" rules={[{ required: true, message: '请输入密码' }]}>
                            <Input.Password size="large" prefix={<LockOutlined />} placeholder="密码" />
                        </Form.Item>
                        <Form.Item>
                            <Button type="primary" htmlType="submit" loading={loading} className={styles.submit}>
                                登 录
                            </Button>
                        </Form.Item>
                    </Form>
                    <div className={styles.footer}>© {new Date().getFullYear()} 审计监管平台</div>
                </div>
            </div>
        </div>
    );
}
