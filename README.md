# 悠悠课程本

家庭自用的课时记录。本地是手机优先的网页，后端是 FastAPI + SQLite。不要把浏览器本地存储当成账本。

日本 VPS 还没有部署。上线步骤在 `docs/DEPLOY.md`，需要你明确授权后才能做。

## 本地运行

需要 Python 3.11 以上，以及 Node.js。在仓库里开两个终端。

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt -r requirements-dev.txt
copy .env.example .env
.\.venv\Scripts\python -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000
```

```powershell
cd frontend
npm install
npm run dev
```

浏览器打开 http://127.0.0.1:5173 。页面和 `/api` 在开发时由 Vite 代理到同一个来源，登录用 HttpOnly Cookie。

可选示例数据（课包上写着 DEMO，不是真实报名节数）：

```powershell
cd backend
.\.venv\Scripts\python -m app.seed
```

示例账号 `demo` / `demo-pass-123`，家人 `baba` / `demo-pass-123`。

## 测试

```powershell
cd backend
.\.venv\Scripts\python -m pytest
```

覆盖重复打卡、并发只扣一次、撤销后再打、请假是否扣课、不能提前打卡、快捷打卡不碰别的日期、改课表不改历史、第二期课包不会自动顶掉第一期、成员不能改课程、别的家庭不能靠改 ID 访问，以及 SQLite backup。

## 课时怎么算

```text
剩余 = 购买节数 - 启用前已用 - 未撤销记录扣掉的节数
已用 + 剩余 = 购买节数
```

日历上的计划课是按每周时间算出来的，不写进数据库。只有打卡、请假、取消、补课和撤销才落库。
