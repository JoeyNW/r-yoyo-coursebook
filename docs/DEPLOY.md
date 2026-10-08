# 部署到 AlmaLinux 9

还没有授权，不要在日本 VPS 上执行。机器上正在跑 VPN。不要重装系统，不要改 VPN、现有防火墙或 SELinux，也不要安装 Docker。

## 上线前只读检查

```bash
cat /etc/os-release
uname -m
free -h
df -h
ps aux --sort=-%mem | head -15
sudo ss -tulpn
getenforce
```

确认内存还够一个 Python 进程，以及 80/443 有没有被 VPN 占用。如果 443 已被占用，停下来再决定入口，不要直接把站点绑上去。

## 进程

前端在自己的电脑上构建，只上传 `frontend/dist`。服务器上是：

- Caddy：HTTPS、静态文件，并把 `/api` 反代到本机
- 一个 uvicorn 进程，只监听 `127.0.0.1:8000`
- SQLite 文件放在 `/var/lib/yoyo/yoyo.db`

示例 Caddy 站点。域名换成你自己的，页面和 API 必须同域：

```caddyfile
example.com {
    root * /var/www/yoyo
    encode gzip
    handle /api/* {
        reverse_proxy 127.0.0.1:8000
    }
    handle {
        try_files {path} /index.html
        file_server
    }
}
```

`/etc/yoyo.env`：

```text
DATABASE_PATH=/var/lib/yoyo/yoyo.db
COOKIE_SECURE=1
SESSION_DAYS=30
```

systemd 单元只作草稿。`User` 用一个专门的系统用户，工作目录放已经装好依赖的虚拟环境：

```ini
[Service]
WorkingDirectory=/opt/yoyo/backend
EnvironmentFile=/etc/yoyo.env
ExecStart=/opt/yoyo/backend/.venv/bin/uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000
Restart=on-failure
```

不要在服务器上跑 `npm run dev`。

## 备份

用 SQLite 自带的 backup，不要直接拷正在写入的 db 文件。每天一次，保留 14 天，目录权限 700，不要放在网站目录里。

```bash
python -m app.backup --dest /var/backups/yoyo/yoyo-$(date +%F).db
```

恢复时先停 uvicorn，再用备份文件换上数据库，然后启动。换完用两个账号看一眼课时是否还在。

## 上线后

用没开 VPN 的大陆手机打开 HTTPS。确认打卡、刷新后另一位家人能看到，并且原来的 VPN 还在。
