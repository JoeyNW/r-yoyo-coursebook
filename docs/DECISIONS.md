# 决策记录

> 版本：V1.1  
> 日期：2026-10-08  
> 这是开工合同。与 `PROJECT_CONTEXT.md` 正文里更早的句子冲突时，以本文为准。

状态：`已定` 直接实现；`待确认` 只影响真实数据录入或上线，不阻塞本地开发。

## 已定

### D1 — 先做同域 H5

手机优先的响应式网页，兼容 iOS、Android 浏览器和微信内置浏览器。静态页面与 `/api` 在同一域名，避免微信里第三方 Cookie 丢登录。

PWA、系统推送、WebSocket 都不做。另一位家人刷新后看到同一本账即可。不做原生 App。

### D2 — 前端 Vue 3 + Vite + TypeScript

不再评估 uni-app。小程序若以后要做，复用这里的 API 和数据，界面另写。

界面只依赖 Vue Router。样式自己写，不引入组件库。视口以 375px 为先，主操作不超过 3 次点击。

### D3 — 后端 FastAPI + SQLite

Python 3.11+。SQLAlchemy 2.0 同步引擎，单连接写入。迁移用仓库里按编号排列的 SQL 文件，启动时按 `PRAGMA user_version` 执行，不用 Alembic。

SQLite 打开时设置：

- `journal_mode=WAL`
- `foreign_keys=ON`
- `busy_timeout=5000`
- `synchronous=NORMAL`

扣课事务使用 `BEGIN IMMEDIATE`。撞上未作废的唯一键时返回已有记录，课时不变。

测试用 pytest，每个用例一个临时库文件。并发用例用两个线程打同一节。

### D4 — 生产用 systemd + Caddy

AlmaLinux 9 上不安装 Docker。进程模型：Caddy 提供 HTTPS 和静态文件，反代到一个 uvicorn。前端在本地 `npm run build` 后上传。

本地开发不依赖 Docker：后端 uvicorn，Vite 把 `/api` 代理到后端。Windows 本机可直接跑。

未获授权不动日本 VPS，不碰 VPN、防火墙和 SELinux。

### D5 — 账本公式

权威余额只在服务端计算：

```text
剩余 = total_units - opening_consumed_units - SUM(未作废 consumed_units)
已用 = total_units - 剩余
```

V1 保证 **已用 + 剩余 = 总课时**。首页文案用「已用 / 总 / 剩余」。已用包含启用前已用、已上课扣减，以及勾了「扣课时」的请假。

禁止前端自行减 1。禁止把剩余存成另一份权威数字。`localStorage` 只可以放界面偏好。

`opening_consumed_units` 在创建课包时填写，默认 0。之后修改必须写 `audit_logs`。它用来承接「这本书启用前已经上过的节数」，不伪造日历打卡。

每次上课默认 `consumed_units = 1`。V1 界面不配置一节扣 2 课时或赠送。

### D6 — 计划现算，事实才落库

`course_schedules` 表示每周重复：`weekday` 周一 = 0，与 Python `date.weekday()` 一致；`local_time` 为 `HH:MM`。一条课程多行。某天是否有计划课，由接口按日期范围展开，最多 42 天。

展开条件：星期匹配，且 `effective_from <= 日期`，且 `effective_to` 为空或 `日期 <= effective_to`。

`lesson_records` 只在发生事实时插入：

| 列 | 取值 |
|---|---|
| `source` | `planned`（对着课表打的）或 `manual`（临时补课） |
| `status` | `attended`、`leave`、`canceled` |
| `consumed_units` | `attended` 为 1；`canceled` 为 0；`leave` 默认 0，勾选扣课时才为 1 |
| `local_date` / `local_time` | 用户看到的上海日期和时间，写入后不随课表改变 |
| `package_id` | 扣课当时的课包，之后换当前课包也不改旧行 |
| `voided_at` | 撤销时间；空表示这条仍有效 |

计划课的幂等键：`plan:{course_id}:{YYYY-MM-DD}:{HH:MM}`。  
补课的幂等键：`manual:{uuid}`。同一天可以有多节补课。

部分唯一索引：`idempotency_key` 在 `voided_at IS NULL` 时唯一。撤销不删除行。撤销后同一键可以再插入一条有效记录。

日历合并：同一课程、日期、时间上，有效记录盖过推算出来的计划；没有记录才显示 `scheduled`。补课和已经对不上新课表的旧记录照常显示。

改排课：旧行 `effective_to` 设为变更日前一天，插入新行。已落库记录不动。

到期日只展示，不拦截打卡。停用课程不再出现在未来日历里，历史记录仍可查。

### D7 — 当前课包与快捷打卡

每门课有 `current_package_id`。第一份课包自动成为当前。再新建课包时不自动替换，由 owner 设为当前。

快捷打卡和日历打卡都只扣当前课包。剩余不足 1 时返回错误，提示更换或新建课包，不透支，不从其他课包拆扣。

首页按钮：

- 今天该课程只有一节尚未记录：打这一节，`attended`。
- 今天有多节尚未记录：不直接扣，打开当日列表。
- 今天没有未记录的计划课：不扣。补录必须在日历选择日期。

重复点击同一节返回原记录，已用和剩余不变。

### D8 — 角色

`owner`：打卡、纠错、课程、排课、课包、邀请、移除成员。  
`member`：查看，以及打卡、请假、取消、补课、撤销。  
不能靠改 URL 或请求体里的 `family_id` / `course_id` 访问其他家庭。每个查询都从当前会话的成员关系过滤。

只读角色不做。V1 界面按一个家庭来用，表结构仍带 `family_id`。

### D9 — 登录与邀请

用户名 + 密码。密码用 argon2id。用户名存小写后唯一。

会话放 `sessions` 表，Cookie 为 HttpOnly、SameSite=Lax。生产环境加 Secure。退出删除服务端会话。有效期 30 天，滑动延期可以不做。

邀请码用 `secrets.token_urlsafe` 生成，库存哈希。默认 7 天、一次有效。明文只在创建时返回给 owner。

注册后要么创建家庭，要么填写邀请码加入。没有邀请码不能进入别人的家庭。

### D10 — 时间、备份、导出

库内时间戳为 UTC。业务日期按 `Asia/Shanghai`。界面简体中文，24 小时制，日期 `YYYY-MM-DD`。

备份用 SQLite backup API（或 `VACUUM INTO`），不要直接拷贝正在写入的 db 文件。生产建议每日一次，保留 14 份，目录权限 700，不放在网站根目录。V1 提供 `GET /api/export` 下载 JSON，包含课程、课包、排课和上课记录。

低余额：剩余小于等于 3 时在卡片上提示。阈值写死为 3。

### D11 — 种子数据

开发种子可以有「英语 / 周一 16:30、周五 19:00」和一个标明 DEMO 的课包。节数用 10 这类整数，并在界面上能看出是示例。生产库从空库开始，不灌种子。

## 待确认

1. 英语、舞蹈的购买节数、启用前已用节数、开始日期。
2. 舞蹈每周的上课时间。
3. 机构是否规定请假也扣课。应用已支持单次勾选，不需要先定全局开关。
4. VPS 的 VPN 端口、80/443 是否空闲、有没有域名。不要索取密码或私钥。
5. 家庭成员名单。默认除创建者外都是 `member`。

## 明确推迟

原生 App、小程序、uni-app、PWA、AI、支付、短信、推送、WebSocket、费用统计、赠送课时界面、放假批量调课、只读角色、多家庭界面、Docker 生产部署。
