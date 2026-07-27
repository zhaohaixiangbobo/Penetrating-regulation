## 环境说明

- 所有 Python 命令默认直接使用解释器：`D:\3-anaconda\envs\py312\python.exe`。
- 以后所有需要安装的新包，都必须先询问用户；由用户手动安装，用户确认安装完成后再继续下一步。
- repo wiki 文档要实现完整
- 所有的功能必须要有测试案例，确保测试通过，前端能确保编译成功
- Node.js: v20.15.0 (LTS) npm: 10.7.0 Python: 3.12.12 选择合适我本地环境的
- 项目尽量不用动我的c盘 增加我的存储空间
-

## 服务器环境说明

StarRocks 已经部署
starrock
10.9.14.128
9030
root
TJycrock#lc2025

部署架构 一台机器足够
访问方式：用户用 IP 访问
需要开机自启和 systemd 守护

===== 1. 架构与系统 =====
aarch64
PRETTY_NAME="UOS Server 20"
NAME="UOS Server 20"
VERSION_ID="20"
VERSION="20"
ID=uos
HOME_URL="https://www.chinauos.com/"
BUG_REPORT_URL="https://bbs.chinauos.com/"
VERSION_CODENAME=fuyu
PLATFORM_ID="platform:uel20"
===== 2. 硬件资源 =====
8
total        used        free      shared  buff/cache   available
Mem:           14Gi       1.9Gi        10Gi       170Mi       2.7Gi        12Gi
Swap:         8.0Gi          0B       8.0Gi
文件系统              容量  已用  可用 已用% 挂载点
/dev/mapper/uos-root   70G  9.3G   61G   14% /
===== 3. 网络连通性 =====
不可联网/内网
===== 4. 编译工具链 =====
gcc (GCC) 7.3.0
GNU Make 4.3
===== 5. Python =====
Python 3.7.9
/usr/bin/python3
===== 6. Nginx =====
-bash: nginx：未找到命令
无nginx
===== 7. 当前用户与权限 =====
root
用户id=0(root) 组id=0(root) 组=0(root)
===== 8. 端口占用 =====
相关端口空闲

## 待实现

数据页面前端优化

1.功能2 换sql 这个日期有些说法
2.让chatgpt检查一下前端相应逻辑有没有啥问题
3.登录页面的ui可以在调整一下
4.增加一个数据导出功能

所有页面要加缓存
要记得数据库名
客户经理的联动选择表可能不太好

## 前端端要求

前端的版本根据我的node的版本确定
React	^18.3	稳定版，生态最成熟，Ant Design 5 完全兼容
TypeScript	^5.5	支持 3.12 风格更好的类型推导
UmiJS	^4.3	Ant Design Pro 的底层框架，UmiJS 4 原生支持 Vite
Ant Design	^5.22	当前最新大版本
@ant-design/pro-components	^2.7	Pro 组件全家桶
ECharts	^5.5	稳定版，React 集成用 echarts-for-react
echarts-for-react	^3.0	ECharts 的 React 封装
Vite	^5.4 或 ^6.x	UmiJS 4 内置处理，通常不需要手动管理

### 后端

后端的包尽量根据我的python版本来 如果有要下载的 提前跟我说 由我来确定

- FastAPI
- SQLAlchemy
- uvicorn

## 功能需求

1.查询功能
目前只有三个查询  后续会增加很多的查询
是每个查询一个界面比较好 还是单独的一个查询比较好
具体得查询得功能和前后端得要求都在 dababase.md中 仔细阅读

2.看板页面
待完善 暂时不实现

3.登录功能
有一个登录页面 输入用户密码的 设计的高端科技感一些 可以引用一些背景图 从别的地方下载 登录框要有半透明感
暂时实现在sqlite数据库中
用户admin 密码tjyc!2026
