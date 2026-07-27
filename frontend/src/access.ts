// 权限控制：登录后（有 currentUser）才能访问业务页
export default function access(initialState: { currentUser?: { username: string } }) {
  const can = !!initialState?.currentUser;
  return {
    canView: can,
  };
}
