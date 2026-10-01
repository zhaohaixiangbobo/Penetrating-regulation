# 穿透式监督查询系统

前后端分离的审计查询平台，基于 **FastAPI + StarRocks + UmiJS 4 + Ant Design Pro**。

- 后端：`backend/`（FastAPI + SQLAlchemy async + asyncmy + aiosqlite）
- 前端：`frontend/`（UmiJS 4 + Ant Design 5 + Pro Components + ECharts）
- 文档：`docs/`

后续新增营销审计查询，先参考 [审计查询页面开发模板](docs/11-审计查询页面开发模板.md)，其中包含现有三个页面的功能、实现链路、需求填写模板和验收步骤。

营销专卖模块已接入“扣款户名不符”，功能与业务口径见 [模块说明](docs/12-营销专卖-扣款户名不符.md)。

## 快速开始

### 1. 后端

```powershell
cd d:\2-code\shenji\backend
copy .env.example .env
D:\3-anaconda\envs\py312\python.exe -m pip install -r requirements.txt
D:\3-anaconda\envs\py312\python.exe -m scripts.init_db
D:\3-anaconda\envs\py312\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

- 默认账号：`admin` / `tjyc!2026`
- API 文档：[http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

cd d:\2-code\shenji\backend
copy .env.example .env
D:\3-anaconda\envs\py312\python.exe -m pip install -r requirements.txt
D:\3-anaconda\envs\py312\python.exe -m scripts.init_db
D:\3-anaconda\envs\py312\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

### 2. 前端

```powershell
cd d:\2-code\shenji\frontend
npm install
npm run dev
```

访问 [http://localhost:8000](http://localhost:8000)（Umi dev 默认端口，若冲突用 `PORT=3000 npm run dev`）。

### 3. 测试

```powershell
cd d:\2-code\shenji\backend
D:\3-anaconda\envs\py312\python.exe -m pytest -q


```

```powershell
cd d:\2-code\shenji\frontend
npm run build
```

## 目录一览

见 [docs/01-架构总览.md](docs/01-架构总览.md)。
