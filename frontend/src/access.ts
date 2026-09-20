// 权限控制：登录后（有 currentUser）才能访问业务页；isAdmin 用于管理员专属功能
export default function access(initialState: { currentUser?: { username: string; role?: string } }) {
  const can = !!initialState?.currentUser;
  return {
    canView: can,
    isAdmin: can && initialState?.currentUser?.role === 'admin',
  };
}
