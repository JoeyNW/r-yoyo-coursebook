# 悠悠课程本 — Agent 工作约定

开工合同是 `docs/DECISIONS.md`（V1.1）。背景在 `docs/PROJECT_CONTEXT.md`。进度在 `docs/PROGRESS.md`。与 V1.1 冲突时实现合同优先，并把偏差补进 `DECISIONS.md`。

当前：**尚未写应用代码**。只做本地 H5。不要连接日本 VPS，不要改 VPN。

## 不可放宽

- 余额只在服务端按 D5 公式计算。禁止 `localStorage` 记账，禁止前端 `remaining - 1`。
- 计划课按排课规则现算，不预插未来行。只有打卡、请假、取消、补课、撤销写入 `lesson_records`。
- 首页快捷打卡只打今天尚未记录的那一节；今天多节则进入列表；没有课不扣。
- 只扣 `current_package_id`。剩余不足则拒绝。不透支，不跨课包。
- 幂等键见 D6。未作废记录唯一。并发第二次返回原记录。撤销只填 `voided_at`。
- 改排课用生效日期截断旧时段。已写记录的日期和时间不变。
- `member` 不能改课程、排课、课包、邀请和成员。隔离做在查询里，不靠隐藏按钮。
- 写操作用事务。扣课用 `BEGIN IMMEDIATE`。SQLite 使用 WAL。

## 技术

- 前端 Vue 3 + Vite + TypeScript。后端 FastAPI + SQLAlchemy 2 同步 + 编号 SQL 迁移。
- 会话是 HttpOnly Cookie，页面和 API 同域。密码 argon2id。
- 本地：uvicorn + Vite 代理。生产（须授权）：systemd + 单进程 uvicorn + Caddy。不安装 Docker。
- Python：PEP 8、类型注解、英文注释和 docstring。界面简体中文，时区 `Asia/Shanghai`。

每完成一个里程碑就跑测试并更新 `docs/PROGRESS.md`。扣课规则和 VPS 上的新决定先问用户。
